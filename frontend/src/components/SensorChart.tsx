import ReactECharts from "echarts-for-react";
import type { ReadingPoint } from "../investigation";
import type { Sensor } from "../types";

interface Props {
  sensor: Sensor;
  series: ReadingPoint[];
  loading: boolean;
  error: string | null;
}

export default function SensorChart({ sensor, series, loading, error }: Props) {
  const option = {
    animation: false,
    grid: { left: 48, right: 16, top: 28, bottom: 40 },
    title: {
      text: `${sensor.id} (${sensor.unit})`,
      left: 0,
      textStyle: { fontSize: 13, fontWeight: 600, color: "#122226" },
    },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: series.map((p) => p.ts.replace("T", " ").slice(0, 19)),
      axisLabel: { fontSize: 10, color: "#3d555c" },
    },
    yAxis: {
      type: "value",
      name: sensor.unit,
      nameTextStyle: { color: "#3d555c", fontSize: 11 },
      axisLabel: { fontSize: 10, color: "#3d555c" },
      splitLine: { lineStyle: { color: "rgba(18,34,38,0.08)" } },
    },
    series: [
      {
        type: "line",
        data: series.map((p) => p.value),
        showSymbol: series.length < 40,
        symbolSize: 5,
        lineStyle: { width: 2, color: "#1a6b7a" },
        itemStyle: { color: "#1a6b7a" },
        areaStyle: { color: "rgba(26,107,122,0.12)" },
      },
    ],
  };

  return (
    <div className="sensor-chart">
      {loading && <p className="chart-status">Loading series…</p>}
      {error && <p className="chart-status chart-error">{error}</p>}
      {!loading && !error && series.length === 0 && (
        <p className="chart-status">No readings at or before the cursor.</p>
      )}
      {!loading && !error && series.length > 0 && (
        <ReactECharts option={option} style={{ height: 220, width: "100%" }} />
      )}
    </div>
  );
}
