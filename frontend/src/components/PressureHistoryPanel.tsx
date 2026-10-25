import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { fetchHourlyHistory } from "../api";
import { paddedValueExtent } from "../investigation";
import { normalizeNaive } from "../time";
import type { HourlyHistoryResponse, Sensor } from "../types";

interface Props {
  sensor: Sensor;
  cursor: string;
}

function conciseTs(ts: string): string {
  const n = normalizeNaive(ts);
  return `${n.slice(5, 10)} ${n.slice(11, 16)}`;
}

export default function PressureHistoryPanel({ sensor, cursor }: Props) {
  const [data, setData] = useState<HourlyHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    if (sensor.measurement_type !== "pressure") {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const id = ++reqId.current;
    const requestCursor = normalizeNaive(cursor);
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);
    fetchHourlyHistory(sensor.id, requestCursor, 30, controller.signal)
      .then((res) => {
        if (id !== reqId.current) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== reqId.current) return;
        setData(null);
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [sensor.id, sensor.measurement_type, cursor]);

  const dataMatched =
    Boolean(data) && normalizeNaive(data!.cursor) === normalizeNaive(cursor);

  const option = useMemo(() => {
    if (!data || !dataMatched) return null;
    const categories = data.hours.map((h) => normalizeNaive(h.hour_start));
    const means = data.hours.map((h) => h.mean_m);
    const mins = data.hours.map((h) => h.min_m);
    const maxs = data.hours.map((h) => h.max_m);
    const y = paddedValueExtent([...means, ...mins, ...maxs]);
    return {
      animation: false,
      grid: { left: 56, right: 20, top: 36, bottom: 48, containLabel: false },
      legend: {
        data: ["Hourly mean", "Observed min", "Observed max"],
        top: 0,
        left: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { fontSize: 10, color: "#3d555c" },
      },
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
        nameGap: 42,
        nameTextStyle: { fontSize: 10, color: "#3d555c" },
        min: y.min,
        max: y.max,
        axisLabel: {
          fontSize: 10,
          color: "#3d555c",
          formatter: (v: number) => v.toFixed(2),
        },
        splitLine: { lineStyle: { color: "rgba(18,34,38,0.08)" } },
      },
      series: [
        {
          name: "Hourly mean",
          type: "line",
          data: means,
          showSymbol: false,
          lineStyle: { width: 2, color: "#1a6b7a" },
        },
        {
          name: "Observed min",
          type: "line",
          data: mins,
          showSymbol: false,
          lineStyle: { width: 1, type: "dashed", color: "#6b5a8a" },
        },
        {
          name: "Observed max",
          type: "line",
          data: maxs,
          showSymbol: false,
          lineStyle: { width: 1, type: "dashed", color: "#b35c1e" },
        },
      ],
    };
  }, [data, dataMatched]);

  if (sensor.measurement_type !== "pressure") return null;

  return (
    <section className="history-panel" aria-label="Available pressure history">
      <header className="history-header">
        <div>
          <p className="eyebrow">Available history — up to 30 days</p>
          <p className="tiger-inline-note">
            Historical context powered by precomputed summaries.
          </p>
        </div>
        <p className="history-cursor">
          Investigation cursor {normalizeNaive(cursor)}
        </p>
      </header>
      <p className="chart-title">Hourly observed pressure (m)</p>
      {loading && <p className="chart-status">Loading historical context…</p>}
      {error && <p className="chart-status chart-error">{error}</p>}
      {dataMatched && data && !loading && (
        <>
          <p className="history-meta">
            Coverage:{" "}
            {data.coverage_start
              ? `${normalizeNaive(data.coverage_start)} → ${normalizeNaive(data.coverage_end ?? "")}`
              : "none before cursor"}
            {data.coverage_days !== null && data.coverage_days !== undefined
              ? ` (${data.coverage_days.toFixed(1)} days span)`
              : ""}
            {" · "}
            {data.hour_count} hourly points · source {String(data.aggregation.source)}
          </p>
          <p className="history-note">{data.limit_note}</p>
          {data.hour_count === 0 ? (
            <p className="chart-status">
              No completed 15-minute buckets at or before the cursor.
            </p>
          ) : (
            option && (
              <ReactECharts option={option} style={{ height: 260, width: "100%" }} />
            )
          )}
          <p className="history-footnote">
            Distinct from the detailed 5-minute replay chart. Built from
            precomputed historical summaries (continuous aggregates). Incomplete
            hours are included and labeled in the API; empty hours are omitted.
            Min/max are observed, not limits. Observation only — not a confirmed
            leak.
          </p>
        </>
      )}
    </section>
  );
}
