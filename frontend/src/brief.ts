/**
 * Investigation brief helpers — cursor-matched snapshot for print / Save as PDF.
 * Client-only; does not create saved investigations.
 */

import { CONTEXT } from "./investigation";
import type { PressureComparison } from "./investigation";
import type { MethodMWarningResponse, SnapshotObservation } from "./types";

export function fmtNum(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function fmtTs(ts: string | null | undefined): string {
  if (!ts) return "—";
  return String(ts).replace("T", " ").slice(0, 19);
}

export function freshnessLabel(status: string | null | undefined): string {
  switch (status) {
    case "current":
      return "current (≤5 min before cursor)";
    case "stale":
      return "stale (>5 min before cursor)";
    case "missing":
      return "missing (no observation ≤ cursor)";
    default:
      return status ?? "unknown";
  }
}

export function findObs(
  observations: SnapshotObservation[],
  sensorId: string,
): SnapshotObservation | null {
  return observations.find((o) => o.sensor_id === sensorId) ?? null;
}

export function warningStatusLine(data: MethodMWarningResponse | null): string {
  if (!data) return "Unavailable at this cursor";
  if (data.warning_active) return "Experimental warning active";
  if (data.status === "before_coverage" || data.status === "missing") {
    return "No experimental warning evidence at this cursor";
  }
  return "No warning at this time";
}

export function pressureDeltaLine(cmp: PressureComparison | null): string {
  if (!cmp) return "—";
  if (!cmp.available) {
    return `Unavailable — ${cmp.unavailableReason ?? "insufficient history"}`;
  }
  const sign = (cmp.deltaM ?? 0) >= 0 ? "+" : "";
  return `${sign}${fmtNum(cmp.deltaM)} m`;
}

export const BRIEF_PRODUCT_LABEL =
  "Historical BattLeDIM L-Town benchmark replay — not live utility monitoring.";

export const BRIEF_CAUSE_LABEL =
  "Cause and location: unconfirmed. This brief does not identify a leak or pipe.";

export const BRIEF_CONTEXT_CHANNELS = [
  {
    id: CONTEXT.externalInflows[0].sensorId,
    title: "External water supply · p227",
    detail: "R1 → network (measured supply)",
    unit: "m³/h",
  },
  {
    id: CONTEXT.externalInflows[1].sensorId,
    title: "External water supply · p235",
    detail: "R2 → network (measured supply)",
    unit: "m³/h",
  },
  {
    id: CONTEXT.internalTransfer.sensorId,
    title: "Internal pump transfer · PUMP_1",
    detail: "n54 → T1 — internal transfer, not external supply",
    unit: "m³/h",
  },
  {
    id: CONTEXT.tankLevel.sensorId,
    title: "Tank level · T1",
    detail: "Observed tank water level",
    unit: "m",
  },
] as const;
