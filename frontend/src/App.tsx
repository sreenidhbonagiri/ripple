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
  const [series, setSeries] = useState<ReadingPoint[]>([]);
  const [seriesLoading, setSeriesLoading] = useState(false);
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
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Snapshot at cursor — ignore stale responses; clear while in-flight to avoid
  // showing a previous cursor's observations under a newer cursor label.
  useEffect(() => {
    if (!cursor) return;
    if (skipSnapshotCursorRef.current === cursor) {
      skipSnapshotCursorRef.current = null;
      return;
    }
    const id = ++snapshotReq.current;
    const controller = new AbortController();
    setObservations([]);
    fetchReplaySnapshot(cursor, controller.signal)
      .then((snap: ReplaySnapshotResponse) => {
        if (id !== snapshotReq.current) return;
        setObservations(snap.observations);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        if (id !== snapshotReq.current) return;
      });
    return () => controller.abort();
  }, [cursor]);

  // Shared series fetch for chart + 30-minute comparison (one request)
  useEffect(() => {
    if (!selectedSensor || !cursor || !windowStart || !windowEnd) {
      setSeries([]);
      setSeriesError(null);
      setSeriesLoading(false);
      return;
    }
    const id = ++seriesReq.current;
    const controller = new AbortController();
    setSeriesLoading(true);
    setSeriesError(null);
    const end = clampTs(cursor, windowStart, windowEnd);
    fetchSensorReadings(selectedSensor.id, windowStart, end, controller.signal)
      .then((res) => {
        if (id !== seriesReq.current) return;
        const points = res.readings
          .map((r) => ({ ts: normalizeNaive(r.ts), value: r.value }))
          .filter((p) => parseNaive(p.ts).getTime() <= parseNaive(cursor).getTime());
        setSeries(points);
        setSeriesLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== seriesReq.current) return;
        setSeriesError(err instanceof Error ? err.message : String(err));
        setSeriesLoading(false);
      });
    return () => controller.abort();
  }, [selectedSensor, cursor, windowStart, windowEnd]);

  const pressureComparison: PressureComparison | null = useMemo(() => {
    if (!selectedPressure || !cursor) return null;
    return pressureChange30m(series, cursor);
  }, [selectedPressure, cursor, series]);

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
        selectedPressure={selectedPressure}
        pressureSeries={series}
        pressureComparison={pressureComparison}
        seriesLoading={seriesLoading}
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
                observations={observations}
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
          observation={selectedObservation}
          windowStart={windowStart}
          windowEnd={windowEnd}
          cursor={cursor}
          series={series}
          seriesLoading={seriesLoading}
          seriesError={seriesError}
        />
      </main>
    </div>
  );
}
