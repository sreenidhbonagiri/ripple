import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { fetchHourlyHistory } from "../api";
import { normalizeNaive } from "../time";
import type { HourlyHistoryResponse, Sensor } from "../types";

interface Props {
  sensor: Sensor;
  cursor: string;
}

export default function PressureHistoryPanel({ sensor, cursor }: Props) {
  const [data, setData] = useState<HourlyHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    if (sensor.measurement_type !== "pressure") {
      setData(null);
      return;
    }
    const id = ++reqId.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchHourlyHistory(sensor.id, cursor, 30, controller.signal)
      .then((res) => {
        if (id !== reqId.current) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (id !== reqId.current) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [sensor.id, sensor.measurement_type, cursor]);

  const option = useMemo(() => {
    if (!data) return null;
    const labels = data.hours.map((h) =>
      normalizeNaive(h.hour_start).slice(0, 16),
    );
    return {
      animation: false,
      grid: { left: 48, right: 16, top: 36, bottom: 48 },
      title: {
        text: `${data.title} · ${data.sensor_id}`,
        left: 0,
        textStyle: { fontSize: 12, fontWeight: 600, color: "#122226" },
      },
      legend: {
        data: ["Hourly mean", "Observed min", "Observed max"],
        top: 18,
        textStyle: { fontSize: 10 },
      },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { fontSize: 9, color: "#3d555c", rotate: 45 },
      },
      yAxis: {
        type: "value",
        name: "m",
        nameTextStyle: { fontSize: 10, color: "#3d555c" },
        axisLabel: { fontSize: 10, color: "#3d555c" },
        splitLine: { lineStyle: { color: "rgba(18,34,38,0.08)" } },
      },
      series: [
        {
          name: "Hourly mean",
          type: "line",
          data: data.hours.map((h) => h.mean_m),
          showSymbol: false,
          lineStyle: { width: 2, color: "#1a6b7a" },
        },
        {
          name: "Observed min",
          type: "line",
          data: data.hours.map((h) => h.min_m),
          showSymbol: false,
          lineStyle: { width: 1, type: "dashed", color: "#6b5a8a" },
        },
        {
          name: "Observed max",
          type: "line",
          data: data.hours.map((h) => h.max_m),
          showSymbol: false,
          lineStyle: { width: 1, type: "dashed", color: "#b35c1e" },
        },
      ],
    };
  }, [data]);

  if (sensor.measurement_type !== "pressure") return null;

  return (
    <section className="history-panel" aria-label="Available pressure history">
      <header className="history-header">
        <p className="eyebrow">Available history — up to 30 days</p>
        <p className="history-cursor">Investigation cursor {normalizeNaive(cursor)}</p>
      </header>
      {loading && <p className="chart-status">Loading historical context…</p>}
      {error && <p className="chart-status chart-error">{error}</p>}
      {data && !loading && (
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
            <p className="chart-status">No completed 15-minute buckets at or before the cursor.</p>
          ) : (
            option && <ReactECharts option={option} style={{ height: 240, width: "100%" }} />
          )}
          <p className="history-footnote">
            Distinct from the detailed 5-minute replay chart. Incomplete hours are included and
            labeled in the API; empty hours are omitted. Min/max are observed, not limits.
          </p>
        </>
      )}
    </section>
  );
}
