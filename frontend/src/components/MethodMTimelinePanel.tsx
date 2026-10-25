import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { fetchMethodMTimeline, fetchSensorReadings } from "../api";
import { paddedValueExtent } from "../investigation";
import { normalizeNaive } from "../time";
import type {
  MethodMTimelineResponse,
  SensorReadingsResponse,
} from "../types";

interface Props {
  /** Selected replay cursor (may differ from loaded response until match). */
  cursor: string | null;
  selectedSensorId: string | null;
  onSeek: (ts: string, bounds: { start: string; end: string }) => void;
}

function conciseTs(ts: string): string {
  const n = normalizeNaive(ts);
  return `${n.slice(5, 10)} ${n.slice(11, 16)}`;
}

export default function MethodMTimelinePanel({
  cursor,
  selectedSensorId,
  onSeek,
}: Props) {
  const [timeline, setTimeline] = useState<MethodMTimelineResponse | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [pressure, setPressure] = useState<SensorReadingsResponse | null>(null);
  const [pressureError, setPressureError] = useState<string | null>(null);
  const [pressureLoading, setPressureLoading] = useState(false);
  const scoreReq = useRef(0);
  const pressureReq = useRef(0);

  useEffect(() => {
    if (!cursor) {
      setTimeline(null);
      setTimelineError(null);
      setTimelineLoading(false);
      return;
    }
    const id = ++scoreReq.current;
    const requestCursor = normalizeNaive(cursor);
    const controller = new AbortController();
    setTimelineLoading(true);
    setTimelineError(null);
    // Drop previous response so a backward seek cannot keep future stamps painted.
    setTimeline(null);
    fetchMethodMTimeline(requestCursor, controller.signal)
      .then((res) => {
        if (id !== scoreReq.current) return;
        setTimeline(res);
        setTimelineLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== scoreReq.current) return;
        setTimeline(null);
        setTimelineError(err instanceof Error ? err.message : String(err));
        setTimelineLoading(false);
      });
    return () => controller.abort();
  }, [cursor]);

  const timelineMatched =
    Boolean(timeline) &&
    Boolean(cursor) &&
    normalizeNaive(timeline!.cursor) === normalizeNaive(cursor!);

  useEffect(() => {
    if (!timelineMatched || !timeline || !selectedSensorId) {
      setPressure(null);
      setPressureError(null);
      setPressureLoading(false);
      return;
    }
    const id = ++pressureReq.current;
    const controller = new AbortController();
    setPressureLoading(true);
    setPressureError(null);
    setPressure(null);
    fetchSensorReadings(
      selectedSensorId,
      normalizeNaive(timeline.window_start),
      normalizeNaive(timeline.window_end),
      controller.signal,
    )
      .then((res) => {
        if (id !== pressureReq.current) return;
        setPressure(res);
        setPressureLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== pressureReq.current) return;
        setPressure(null);
        setPressureError(err instanceof Error ? err.message : String(err));
        setPressureLoading(false);
      });
    return () => controller.abort();
  }, [timelineMatched, timeline, selectedSensorId]);

  const pressureMatched =
    Boolean(pressure) &&
    timelineMatched &&
    Boolean(selectedSensorId) &&
    pressure!.sensor_id === selectedSensorId &&
    normalizeNaive(String(pressure!.end)) ===
      normalizeNaive(timeline!.window_end);

  const categories = useMemo(() => {
    if (!timelineMatched || !timeline) return [] as string[];
    return timeline.points.map((p) => normalizeNaive(p.ts));
  }, [timeline, timelineMatched]);

  const notifyIndex = useMemo(() => {
    if (!timelineMatched || !timeline) return new Set<number>();
    const idx = new Set<number>();
    const catSet = new Map(categories.map((c, i) => [c, i]));
    for (const n of timeline.notifications) {
      const i = catSet.get(normalizeNaive(n.notify_ts));
      if (i !== undefined) idx.add(i);
    }
    return idx;
  }, [timeline, timelineMatched, categories]);

  const scoreOption = useMemo(() => {
    if (!timelineMatched || !timeline || categories.length === 0) return null;
    const scores = timeline.points.map((p) => p.score);
    const numeric = scores.filter((v): v is number => v !== null && !Number.isNaN(v));
    const y = paddedValueExtent([...numeric, timeline.threshold, timeline.recover_threshold]);
    const markPoints = timeline.notifications.map((n) => ({
      name: "Notify",
      coord: [normalizeNaive(n.notify_ts), timeline.threshold],
      value: "N",
      itemStyle: { color: "#c45c26" },
      label: { formatter: "notify", color: "#c45c26", fontSize: 10 },
    }));
    return {
      animation: false,
      grid: { left: 56, right: 20, top: 28, bottom: 36, containLabel: false },
      tooltip: {
        trigger: "axis",
        confine: true,
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const first = list[0] as { axisValue?: string; data?: number | null };
          const ts = first?.axisValue ? conciseTs(String(first.axisValue)) : "";
          const score =
            typeof first?.data === "number" ? first.data.toFixed(3) : "missing";
          const i = categories.indexOf(normalizeNaive(String(first?.axisValue ?? "")));
          const notify = i >= 0 && notifyIndex.has(i) ? "<br/>Notification marker" : "";
          return `${ts}<br/>Score ${score}${notify}`;
        },
      },
      xAxis: {
        type: "category",
        data: categories,
        boundaryGap: false,
        axisLabel: {
          fontSize: 10,
          color: "#3d555c",
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
          formatter: (value: string) => conciseTs(value),
        },
      },
      yAxis: {
        type: "value",
        name: "score",
        nameLocation: "middle",
        nameGap: 40,
        nameTextStyle: { fontSize: 10, color: "#3d555c" },
        min: y.min,
        max: y.max,
        axisLabel: { fontSize: 10, color: "#3d555c", formatter: (v: number) => v.toFixed(1) },
        splitLine: { lineStyle: { color: "rgba(18,34,38,0.08)" } },
      },
      series: [
        {
          name: "Anomaly score",
          type: "line",
          data: scores,
          connectNulls: false,
          showSymbol: categories.length < 80,
          symbolSize: 4,
          lineStyle: { width: 2, color: "#0d4a3a" },
          itemStyle: { color: "#0d4a3a" },
          markLine: {
            symbol: "none",
            label: { fontSize: 10, color: "#c45c26" },
            data: [
              {
                yAxis: timeline.threshold,
                name: "Warning threshold",
                lineStyle: { color: "#c45c26", type: "solid", width: 1.5 },
                label: { formatter: "threshold" },
              },
            ],
          },
          markPoint: {
            symbol: "diamond",
            symbolSize: 10,
            data: markPoints,
          },
        },
      ],
    };
  }, [timeline, timelineMatched, categories, notifyIndex]);

  const pressureOption = useMemo(() => {
    if (!pressureMatched || !pressure || !timelineMatched || !timeline) return null;
    const byTs = new Map(
      pressure.readings.map((r) => [normalizeNaive(String(r.ts)), r.value]),
    );
    // Align to Method M five-minute categories (same axis).
    const values = categories.map((ts) => {
      const v = byTs.get(ts);
      return v === undefined ? null : v;
    });
    const numeric = values.filter((v): v is number => v !== null);
    if (numeric.length === 0) {
      return null;
    }
    const y = paddedValueExtent(numeric);
    return {
      animation: false,
      grid: { left: 56, right: 20, top: 16, bottom: 36, containLabel: false },
      tooltip: {
        trigger: "axis",
        confine: true,
        valueFormatter: (v: number | string) =>
          typeof v === "number" ? `${v.toFixed(2)} m` : String(v),
      },
      xAxis: {
        type: "category",
        data: categories,
        boundaryGap: false,
        axisLabel: {
          fontSize: 10,
          color: "#3d555c",
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
          formatter: (value: string) => conciseTs(value),
        },
      },
      yAxis: {
        type: "value",
        name: "m",
        nameLocation: "middle",
        nameGap: 40,
        nameTextStyle: { fontSize: 10, color: "#3d555c" },
        min: y.min,
        max: y.max,
        axisLabel: { fontSize: 10, color: "#3d555c", formatter: (v: number) => v.toFixed(2) },
        splitLine: { lineStyle: { color: "rgba(18,34,38,0.08)" } },
      },
      series: [
        {
          name: `${pressure.sensor_id} pressure`,
          type: "line",
          data: values,
          connectNulls: false,
          showSymbol: categories.length < 80,
          symbolSize: 4,
          lineStyle: { width: 2, color: "#1a6b7a" },
          itemStyle: { color: "#1a6b7a" },
          areaStyle: { color: "rgba(26,107,122,0.10)" },
        },
      ],
    };
  }, [pressure, pressureMatched, timeline, timelineMatched, categories]);

  const onChartClick = (params: { name?: string; data?: unknown }) => {
    if (!timelineMatched || !timeline) return;
    const ts =
      typeof params.name === "string" && params.name
        ? normalizeNaive(params.name)
        : null;
    if (!ts || !categories.includes(ts)) return;
    onSeek(ts, {
      start: normalizeNaive(timeline.window_start),
      end: normalizeNaive(timeline.window_end),
    });
  };

  if (!cursor) {
    return (
      <section
        id="panel-timeline"
        className="method-m-timeline app-panel"
        aria-label="Experimental warning timeline"
      >
        <p className="channel-note">
          Set a replay cursor to load the preceding 24-hour experimental score
          timeline.
        </p>
      </section>
    );
  }

  return (
    <section
      id="panel-timeline"
      className="method-m-timeline app-panel"
      aria-label="Experimental warning timeline"
    >
      <header className="method-m-timeline-header">
        <h2 className="method-m-timeline-title">Anomaly score timeline</h2>
        <p className="tiger-inline-note">
          Preceding 24 hours from Tiger Data, ending at the replay cursor.
        </p>
        <p className="method-m-timeline-cursor">
          Selected cursor {normalizeNaive(cursor)}
          {timelineMatched
            ? ` · loaded through ${normalizeNaive(timeline!.window_end)}`
            : timelineLoading
              ? " · loading…"
              : ""}
        </p>
      </header>

      {timelineLoading && !timelineMatched && (
        <p className="channel-note" role="status">
          Loading experimental score timeline…
        </p>
      )}
      {timelineError && (
        <p className="state-copy" role="alert">
          {timelineError}
        </p>
      )}

      {timelineMatched && timeline && (
        <>
          <p className="method-m-meta">
            Window {normalizeNaive(timeline.window_start)} →{" "}
            {normalizeNaive(timeline.window_end)} · {timeline.points.length} stamps
            {" · "}
            source <code>{timeline.source}</code> · store{" "}
            <strong>{timeline.store}</strong> · run <code>{timeline.run_id}</code>
            {timeline.missingness.null_scores > 0
              ? ` · ${timeline.missingness.null_scores} missing scores`
              : ""}
          </p>
          <p className="chart-title">Anomaly score (five-minute)</p>
          {timeline.points.length === 0 ? (
            <p className="chart-status">{timeline.status}: no scores in window.</p>
          ) : (
            scoreOption && (
              <ReactECharts
                option={scoreOption}
                style={{ height: 240, width: "100%" }}
                onEvents={{ click: onChartClick }}
              />
            )
          )}
          <p className="channel-note">
            Click a five-minute stamp to seek the replay cursor. Warning threshold
            line is frozen at {timeline.threshold.toFixed(3)}.
          </p>

          <p className="chart-title">
            Selected pressure · same time axis
            {selectedSensorId ? ` (${selectedSensorId})` : ""}
          </p>
          {!selectedSensorId && (
            <p className="channel-note">
              Inspect a contributing pressure sensor to align raw readings on this
              axis. Longer historical context uses precomputed historical summaries
              in the details panel.
            </p>
          )}
          {selectedSensorId && pressureLoading && (
            <p className="channel-note">Loading aligned pressure readings…</p>
          )}
          {selectedSensorId && pressureError && (
            <p className="chart-status chart-error">{pressureError}</p>
          )}
          {selectedSensorId && pressureMatched && pressureOption && (
            <ReactECharts
              option={pressureOption}
              style={{ height: 220, width: "100%" }}
              onEvents={{ click: onChartClick }}
            />
          )}
          {selectedSensorId &&
            pressureMatched &&
            !pressureOption &&
            !pressureLoading && (
              <p className="chart-status">
                No pressure readings on the score stamps in this window.
              </p>
            )}

          <details className="method-m-tech">
            <summary>Method and evaluation</summary>
            <p className="channel-note">{timeline.score_interpretation}</p>
            <p className="channel-note">
              Frozen Method M scores from Tiger. {timeline.resolution_note}{" "}
              Notification markers are five-minute stamps at or before the cursor.
              Provenance run <code>{timeline.provenance.run_id}</code> ·
              serving_hours sha256{" "}
              <code>
                {timeline.provenance.serving_hours_sha256?.slice(0, 16) ?? "—"}…
              </code>
              . Missingness: returned {timeline.missingness.returned_stamps} /{" "}
              {timeline.missingness.expected_stamps_in_method_coverage} expected in
              coverage
              {timeline.missingness.coverage_complete ? " (complete)" : " (partial)"}.
              Warning threshold is τ in the frozen research protocol.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
