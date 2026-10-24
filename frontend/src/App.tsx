import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchNetwork,
  fetchReplaySnapshot,
  fetchReplayWindow,
  fetchSensorReadings,
  fetchSensors,
} from "./api";
import DetailsPanel from "./components/DetailsPanel";
import InvestigationPanels from "./components/InvestigationPanels";
import NetworkMap from "./components/NetworkMap";
import ReplayControls from "./components/ReplayControls";
import TigerEvidencePanel from "./components/TigerEvidencePanel";
import {
  chartSeriesInWindow,
  comparisonLookbackStart,
  earlierTs,
  midpointTimestamp,
  pressureChange30m,
  type PressureComparison,
  type ReadingPoint,
} from "./investigation";
import { PRESENTER } from "./presenter";
import { addSeconds, clampTs, normalizeNaive, parseNaive } from "./time";
import type {
  NetworkResponse,
  ReplaySnapshotResponse,
  Selection,
  Sensor,
  SnapshotObservation,
} from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; network: NetworkResponse };

type AsyncStatus = "idle" | "loading" | "ready" | "error";

function buildTimestamps(start: string, end: string, stepSeconds: number): string[] {
  const out: string[] = [];
  let cur = start;
  const endMs = parseNaive(end).getTime();
  while (parseNaive(cur).getTime() <= endMs) {
    out.push(cur);
    cur = addSeconds(cur, stepSeconds);
    if (out.length > 10000) break;
  }
  return out;
}

export default function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<Selection>(null);
  const [fitToken, setFitToken] = useState(0);
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [windowStart, setWindowStart] = useState<string | null>(null);
  const [windowEnd, setWindowEnd] = useState<string | null>(null);
  const [dataCoverage, setDataCoverage] = useState<{
    start: string | null;
    end: string | null;
    readingCount: number;
    readingCountEstimated: boolean;
    sensorCount: number;
  } | null>(null);
  const [stepSeconds, setStepSeconds] = useState(300);
  const [replayLabel, setReplayLabel] = useState("Historical benchmark replay");
  const [cursor, setCursor] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [observations, setObservations] = useState<SnapshotObservation[]>([]);
  const [snapshotStatus, setSnapshotStatus] = useState<AsyncStatus>("idle");
  const [snapshotForCursor, setSnapshotForCursor] = useState<string | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  /** Full fetch (may extend before presenter window) for −30 min comparison. */
  const [compareSeries, setCompareSeries] = useState<ReadingPoint[]>([]);
  /** Chart-only slice bounded to presenter window → cursor. */
  const [chartSeries, setChartSeries] = useState<ReadingPoint[]>([]);
  const [seriesStatus, setSeriesStatus] = useState<AsyncStatus>("idle");
  const [seriesForSensor, setSeriesForSensor] = useState<string | null>(null);
  const [seriesForCursor, setSeriesForCursor] = useState<string | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const snapshotReq = useRef(0);
  const seriesReq = useRef(0);
  const loadReq = useRef(0);
  /** When set, the next cursor-driven snapshot effect skips (bootstrap already fetched it). */
  const skipSnapshotCursorRef = useRef<string | null>(null);

  const timestamps = useMemo(() => {
    if (!windowStart || !windowEnd) return [];
    return buildTimestamps(windowStart, windowEnd, stepSeconds);
  }, [windowStart, windowEnd, stepSeconds]);

  const midpointTs = useMemo(() => midpointTimestamp(timestamps), [timestamps]);

  const cursorIndex = useMemo(() => {
    if (!cursor || timestamps.length === 0) return 0;
    const i = timestamps.indexOf(cursor);
    return i >= 0 ? i : 0;
  }, [cursor, timestamps]);

  const selectedSensor = selection?.kind === "sensor" ? selection.data : null;
  const selectedPressure =
    selectedSensor?.measurement_type === "pressure" ? selectedSensor : null;

  const load = useCallback(() => {
    const loadId = ++loadReq.current;
    setState({ status: "loading" });
    setSelection(null);
    setObservations([]);
    setSnapshotStatus("loading");
    setSnapshotForCursor(null);
    setSnapshotError(null);
    setCompareSeries([]);
    setChartSeries([]);
    setSeriesStatus("idle");
    setSeriesForSensor(null);
    setSeriesForCursor(null);
    setSeriesError(null);
    setPlaying(false);
    // Clear cursor so replay controls cannot seek while bootstrap is in flight
    // (avoids applying a parallel 14:00 snapshot over a newer cursor).
    setCursor(null);
    // Known presenter start — fetch initial snapshot in parallel with bootstrap
    // (avoids waiting for setCursor → effect waterfall). Tiger evidence stays lazy.
    // Snapshot is always for PRESENTER.windowStart; applied only if the API
    // playback preset still matches that cursor and this load was not superseded.
    const bootstrapCursor = PRESENTER.windowStart;
    skipSnapshotCursorRef.current = bootstrapCursor;
    Promise.all([
      fetchNetwork(),
      fetchSensors(),
      fetchReplayWindow(),
      fetchReplaySnapshot(bootstrapCursor),
    ])
      .then(([network, sensorsRes, windowRes, snap]) => {
        if (loadId !== loadReq.current) return;
        performance.mark("ripple-bootstrap-ready");
        setState({ status: "ready", network });
        setSensors(sensorsRes.sensors);
        // Playback uses the presenter preset — not the full imported data range.
        const start = normalizeNaive(
          windowRes.presenter_start || windowRes.start || "",
        );
        const end = normalizeNaive(windowRes.presenter_end || windowRes.end || "");
        setWindowStart(start);
        setWindowEnd(end);
        setStepSeconds(windowRes.step_seconds || 300);
        setReplayLabel(windowRes.label || "Historical benchmark replay");
        setDataCoverage({
          start: windowRes.data_start ? normalizeNaive(windowRes.data_start) : null,
          end: windowRes.data_end ? normalizeNaive(windowRes.data_end) : null,
          readingCount: windowRes.reading_count,
          readingCountEstimated: windowRes.reading_count_estimated !== false,
          sensorCount: windowRes.sensor_count,
        });
        // Apply parallel snapshot only when it still matches the selected preset
        // and skip token was not cleared. Bump snapshotReq so any stray in-flight
        // cursor fetch cannot overwrite these observations.
        const presetMatchesBootstrap = start === bootstrapCursor;
        const skipStillHeld = skipSnapshotCursorRef.current === bootstrapCursor;
        if (presetMatchesBootstrap && skipStillHeld) {
          snapshotReq.current += 1;
          setObservations(snap.observations);
          setSnapshotForCursor(bootstrapCursor);
          setSnapshotStatus("ready");
          setSnapshotError(null);
        } else {
          skipSnapshotCursorRef.current = null;
        }
        if (start) setCursor(start);
      })
      .catch((err: unknown) => {
        if (loadId !== loadReq.current) return;
        skipSnapshotCursorRef.current = null;
        const message = err instanceof Error ? err.message : String(err);
        setState({ status: "error", message });
        setSnapshotStatus("error");
        setSnapshotError(message);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Snapshot at cursor — ignore stale responses; show loading (not old/missing
  // values labeled as synchronized to the new cursor).
  useEffect(() => {
    if (!cursor) return;
    if (skipSnapshotCursorRef.current === cursor) {
      skipSnapshotCursorRef.current = null;
      return;
    }
    const id = ++snapshotReq.current;
    const requestCursor = cursor;
    const controller = new AbortController();
    setSnapshotStatus("loading");
    setSnapshotError(null);
    setObservations([]);
    setSnapshotForCursor(null);
    fetchReplaySnapshot(requestCursor, controller.signal)
      .then((snap: ReplaySnapshotResponse) => {
        if (id !== snapshotReq.current) return;
        setObservations(snap.observations);
        setSnapshotForCursor(requestCursor);
        setSnapshotStatus("ready");
        setSnapshotError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== snapshotReq.current) return;
        setObservations([]);
        setSnapshotForCursor(null);
        setSnapshotStatus("error");
        setSnapshotError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [cursor]);

  // Series: fetch enough pre-window history for −30 min comparison; chart slice
  // stays bounded to the presenter playback window.
  useEffect(() => {
    if (!selectedSensor || !cursor || !windowStart || !windowEnd) {
      setCompareSeries([]);
      setChartSeries([]);
      setSeriesError(null);
      setSeriesStatus("idle");
      setSeriesForSensor(null);
      setSeriesForCursor(null);
      return;
    }
    const id = ++seriesReq.current;
    const requestSensor = selectedSensor.id;
    const requestCursor = cursor;
    const controller = new AbortController();
    setSeriesStatus("loading");
    setSeriesError(null);
    setCompareSeries([]);
    setChartSeries([]);
    setSeriesForSensor(null);
    setSeriesForCursor(null);
    const end = clampTs(requestCursor, windowStart, windowEnd);
    const fetchStart = earlierTs(windowStart, comparisonLookbackStart(requestCursor));
    fetchSensorReadings(requestSensor, fetchStart, end, controller.signal)
      .then((res) => {
        if (id !== seriesReq.current) return;
        const points = res.readings
          .map((r) => ({ ts: normalizeNaive(r.ts), value: r.value }))
          .filter(
            (p) =>
              parseNaive(p.ts).getTime() <= parseNaive(requestCursor).getTime(),
          );
        setCompareSeries(points);
        setChartSeries(chartSeriesInWindow(points, windowStart, requestCursor));
        setSeriesForSensor(requestSensor);
        setSeriesForCursor(requestCursor);
        setSeriesStatus("ready");
        setSeriesError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== seriesReq.current) return;
        setCompareSeries([]);
        setChartSeries([]);
        setSeriesForSensor(null);
        setSeriesForCursor(null);
        setSeriesStatus("error");
        setSeriesError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [selectedSensor, cursor, windowStart, windowEnd]);

  const snapshotMatched =
    Boolean(cursor) &&
    snapshotStatus === "ready" &&
    snapshotForCursor === cursor;
  // Between setCursor and the effect flipping status→loading, treat mismatch as pending
  // so panels never show "missing" under a newer cursor label.
  const snapshotPending =
    Boolean(cursor) &&
    !snapshotMatched &&
    snapshotStatus !== "error";

  const seriesMatched =
    Boolean(selectedSensor) &&
    Boolean(cursor) &&
    seriesStatus === "ready" &&
    seriesForSensor === selectedSensor?.id &&
    seriesForCursor === cursor;
  const seriesPending =
    Boolean(selectedSensor) &&
    Boolean(cursor) &&
    !seriesMatched &&
    seriesStatus !== "error";

  const pressureComparison: PressureComparison | null = useMemo(() => {
    if (!selectedPressure || !cursor || !seriesMatched) return null;
    return pressureChange30m(compareSeries, cursor);
  }, [selectedPressure, cursor, seriesMatched, compareSeries]);

  // Play loop
  useEffect(() => {
    if (!playing || !cursor || !windowStart || !windowEnd) return;
    const intervalMs = Math.max(150, 1000 / speed);
    const handle = window.setInterval(() => {
      setCursor((prev) => {
        if (!prev || !windowStart || !windowEnd) return prev;
        const next = addSeconds(prev, stepSeconds);
        if (parseNaive(next).getTime() > parseNaive(windowEnd).getTime()) {
          setPlaying(false);
          return windowEnd;
        }
        return clampTs(next, windowStart, windowEnd);
      });
    }, intervalMs);
    return () => window.clearInterval(handle);
  }, [playing, speed, stepSeconds, cursor, windowStart, windowEnd]);

  const seekTo = (ts: string) => {
    if (!windowStart || !windowEnd) return;
    setPlaying(false);
    setCursor(clampTs(ts, windowStart, windowEnd));
  };

  const onStep = (direction: -1 | 1) => {
    if (!cursor || !windowStart || !windowEnd) return;
    seekTo(addSeconds(cursor, direction * stepSeconds));
  };

  const applyIllustrativeBookmark = () => {
    const sensor = sensors.find((s) => s.id === PRESENTER.illustrativeSensorId);
    seekTo(PRESENTER.bookmarks[1].cursor);
    if (sensor) {
      setSelection({ kind: "sensor", data: sensor });
    }
  };

  const selectedObservation =
    selection?.kind === "sensor"
      ? observations.find((o) => o.sensor_id === selection.data.id) ?? null
      : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <p className="product-tag">Historical benchmark replay</p>
          <h1 className="brand">Ripple</h1>
          <p className="tagline">
            BattLeDIM L-Town investigation workspace — not live monitoring.
            Pressure anomalies are not confirmed leaks.
          </p>
        </div>
        <div className="toolbar">
          <button
            type="button"
            className="btn"
            onClick={() => setFitToken((n) => n + 1)}
            disabled={state.status !== "ready"}
          >
            Fit network
          </button>
          <button type="button" className="btn btn-ghost" onClick={load}>
            Reload
          </button>
        </div>
      </header>

      {windowStart && windowEnd && cursor && (
        <>
          <ReplayControls
            label={replayLabel}
            cursor={cursor}
            windowStart={windowStart}
            windowEnd={windowEnd}
            playing={playing}
            speed={speed}
            stepSeconds={stepSeconds}
            onTogglePlay={() => setPlaying((p) => !p)}
            onStep={onStep}
            onSpeedChange={setSpeed}
            onSeek={seekTo}
            onWindowStart={() => seekTo(windowStart)}
            onMidpoint={() => {
              if (midpointTs) seekTo(midpointTs);
            }}
            onIllustrativeBookmark={applyIllustrativeBookmark}
            index={cursorIndex}
            totalSteps={timestamps.length}
            timestamps={timestamps}
            midpointTs={midpointTs}
          />
          {dataCoverage && (
            <p className="data-coverage">
              Presenter window {windowStart} → {windowEnd}
              {" · "}
              Database coverage{" "}
              {dataCoverage.start && dataCoverage.end
                ? `${dataCoverage.start} → ${dataCoverage.end}`
                : "empty"}
              {` (${dataCoverage.readingCount.toLocaleString()} ${
                dataCoverage.readingCountEstimated
                  ? "estimated readings"
                  : "readings"
              }, ${dataCoverage.sensorCount} sensors)`}
            </p>
          )}
        </>
      )}

      <InvestigationPanels
        cursor={cursor}
        observations={observations}
        snapshotStatus={snapshotPending ? "loading" : snapshotStatus}
        snapshotMatched={snapshotMatched}
        snapshotError={snapshotError}
        selectedPressure={selectedPressure}
        pressureComparison={pressureComparison}
        seriesStatus={seriesPending ? "loading" : seriesStatus}
        seriesMatched={seriesMatched}
        seriesError={seriesError}
      />

      <TigerEvidencePanel />

      <main className="workspace">
        <section className="map-stage">
          {state.status === "loading" && (
            <div className="state-panel" role="status">
              <p className="state-title">Loading network…</p>
              <p className="state-copy">Fetching model and replay window.</p>
            </div>
          )}

          {state.status === "error" && (
            <div className="state-panel state-error" role="alert">
              <p className="state-title">Could not load workspace</p>
              <p className="state-copy">{state.message}</p>
              <button type="button" className="btn" onClick={load}>
                Retry
              </button>
            </div>
          )}

          {state.status === "ready" && (
            <>
              <div className="map-meta">
                <span>{state.network.source}</span>
                <span>
                  {state.network.counts.nodes} nodes · {state.network.counts.links} links
                  {sensors.length ? ` · ${sensors.length} sensors` : ""}
                </span>
              </div>
              <NetworkMap
                nodes={state.network.nodes}
                links={state.network.links}
                sensors={sensors}
                observations={snapshotMatched ? observations : []}
                observationsPending={snapshotPending}
                onSelect={setSelection}
                fitToken={fitToken}
              />
              <div className="legend">
                <span><i className="swatch junction" /> Junction</span>
                <span><i className="swatch reservoir" /> Reservoir</span>
                <span><i className="swatch tank" /> Tank</span>
                <span><i className="swatch current" /> Current</span>
                <span><i className="swatch stale" /> Stale</span>
                <span><i className="swatch missing" /> Missing</span>
              </div>
            </>
          )}
        </section>

        <DetailsPanel
          selection={selection}
          counts={state.status === "ready" ? state.network.counts : null}
          networkName={state.status === "ready" ? state.network.name : null}
          source={state.status === "ready" ? state.network.source : null}
          coordinateSystem={
            state.status === "ready" ? state.network.coordinate_system : null
          }
          observation={snapshotMatched ? selectedObservation : null}
          observationStatus={
            !cursor
              ? "idle"
              : snapshotMatched
                ? "ready"
                : snapshotStatus === "error"
                  ? "error"
                  : "loading"
          }
          observationError={snapshotError}
          cursor={cursor}
          series={seriesMatched ? chartSeries : []}
          seriesStatus={
            !selectedSensor
              ? "idle"
              : seriesMatched
                ? "ready"
                : seriesStatus === "error"
                  ? "error"
                  : "loading"
          }
          seriesError={seriesError}
        />
      </main>
    </div>
  );
}
