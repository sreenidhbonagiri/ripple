import ReactECharts from "echarts-for-react";
import { paddedValueExtent, type ReadingPoint } from "../investigation";
import { normalizeNaive } from "../time";
import type { Sensor } from "../types";

interface Props {
  sensor: Sensor;
  series: ReadingPoint[];
  loading: boolean;
  error: string | null;
}

function conciseTs(ts: string): string {
  const n = normalizeNaive(ts);
  return `${n.slice(5, 10)} ${n.slice(11, 16)}`;
}

export default function SensorChart({ sensor, series, loading, error }: Props) {
  const values = series.map((p) => p.value);
  const categories = series.map((p) => normalizeNaive(p.ts));
  const y = paddedValueExtent(values);

  const option = {
    animation: false,
    grid: { left: 56, right: 20, top: 16, bottom: 44, containLabel: false },
    tooltip: {
      trigger: "axis",
      confine: true,
      valueFormatter: (v: number | string) =>
        typeof v === "number" ? `${v.toFixed(2)} ${sensor.unit}` : String(v),
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
      name: sensor.unit,
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: "#3d555c", fontSize: 11 },
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
        type: "line",
        name: `${sensor.id} (${sensor.unit})`,
        data: values,
        showSymbol: series.length < 40,
        symbolSize: 5,
        lineStyle: { width: 2, color: "#1a6b7a" },
        itemStyle: { color: "#1a6b7a" },
        areaStyle: { color: "rgba(26,107,122,0.10)" },
      },
    ],
  };

  return (
    <div className="sensor-chart">
      <p className="chart-title">
        {sensor.id} · {sensor.unit}
      </p>
      {loading && <p className="chart-status">Loading series…</p>}
      {error && <p className="chart-status chart-error">{error}</p>}
      {!loading && !error && series.length === 0 && (
        <p className="chart-status">No readings at or before the cursor.</p>
      )}
      {!loading && !error && series.length > 0 && (
        <ReactECharts option={option} style={{ height: 240, width: "100%" }} />
      )}
    </div>
  );
}
