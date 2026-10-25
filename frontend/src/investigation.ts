/**
 * Coordinated investigation helpers (Milestone 3).
 *
 * Official L-TOWN.inp mappings:
 * - p227: R1 → n303 (external inflow)
 * - p235: R2 → n336 (external inflow)
 * - PUMP_1: n54 → T1 (internal pump transfer, not external supply)
 * - T1: tank level
 */

import { addSeconds, normalizeNaive, parseNaive } from "./time";
import type { FreshnessStatus, SnapshotObservation } from "./types";

export const FRESH_SECONDS = 300;
export const COMPARE_OFFSET_SECONDS = 30 * 60;

export const CONTEXT = {
  externalInflows: [
    {
      sensorId: "p227",
      role: "external_inflow",
      label: "Supply line p227",
      group: "External water supply",
      hint: "R1 → network · measured supply (m³/h)",
      unit: "m³/h",
    },
    {
      sensorId: "p235",
      role: "external_inflow",
      label: "Supply line p235",
      group: "External water supply",
      hint: "R2 → network · measured supply (m³/h)",
      unit: "m³/h",
    },
  ],
  internalTransfer: {
    sensorId: "PUMP_1",
    role: "internal_transfer",
    label: "Pump transfer",
    group: "Internal pump transfer",
    hint: "n54 → T1 · internal transfer, not external supply (m³/h)",
    unit: "m³/h",
  },
  tankLevel: {
    sensorId: "T1",
    role: "tank_level",
    label: "Tank level",
    group: "Tank level",
    hint: "Observed tank water level (m)",
    unit: "m",
  },
} as const;

export const DISCLAIMER =
  "Compare selected pressure with supply, pump transfer, and tank level at the same cursor.";

export interface ReadingPoint {
  ts: string;
  value: number;
}

export interface PressureComparison {
  available: boolean;
  cursor: string;
  priorCursor: string;
  currentValue: number | null;
  currentTs: string | null;
  currentStatus: FreshnessStatus;
  priorValue: number | null;
  priorTs: string | null;
  priorStatus: FreshnessStatus;
  deltaM: number | null;
  unavailableReason: string | null;
}

export function freshnessAt(observationTs: string | null, at: string): FreshnessStatus {
  if (!observationTs) return "missing";
  const obs = parseNaive(normalizeNaive(observationTs)).getTime();
  const cursor = parseNaive(normalizeNaive(at)).getTime();
  if (obs > cursor) {
    throw new Error("observation after comparison time");
  }
  const ageSec = (cursor - obs) / 1000;
  return ageSec <= FRESH_SECONDS ? "current" : "stale";
}

export function latestAtOrBefore(
  points: ReadingPoint[],
  at: string,
): ReadingPoint | null {
  const atMs = parseNaive(normalizeNaive(at)).getTime();
  let chosen: ReadingPoint | null = null;
  for (const p of points) {
    const ts = normalizeNaive(p.ts);
    if (parseNaive(ts).getTime() > atMs) break;
    chosen = { ts, value: p.value };
  }
  return chosen;
}

/** Earliest ts needed so a −30 min comparison can evaluate freshness. */
export function comparisonLookbackStart(cursor: string): string {
  return addSeconds(
    normalizeNaive(cursor),
    -(COMPARE_OFFSET_SECONDS + FRESH_SECONDS),
  );
}

export function earlierTs(a: string, b: string): string {
  const an = normalizeNaive(a);
  const bn = normalizeNaive(b);
  return parseNaive(an).getTime() <= parseNaive(bn).getTime() ? an : bn;
}

/** Detailed replay chart stays inside the presenter playback window. */
export function chartSeriesInWindow(
  points: ReadingPoint[],
  windowStart: string,
  cursor: string,
): ReadingPoint[] {
  const startMs = parseNaive(normalizeNaive(windowStart)).getTime();
  const endMs = parseNaive(normalizeNaive(cursor)).getTime();
  return points
    .map((p) => ({ ts: normalizeNaive(p.ts), value: p.value }))
    .filter((p) => {
      const t = parseNaive(p.ts).getTime();
      return t >= startMs && t <= endMs;
    })
    .sort((a, b) => parseNaive(a.ts).getTime() - parseNaive(b.ts).getTime());
}

/** Pad y-extent so small pressure changes remain visible without exaggeration. */
export function paddedValueExtent(
  values: number[],
  padRatio = 0.15,
): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 };
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { min: 0, max: 1 };
  if (lo === hi) {
    const pad = Math.max(Math.abs(lo) * 0.02, 0.25);
    return { min: lo - pad, max: hi + pad };
  }
  const pad = (hi - lo) * padRatio;
  return { min: lo - pad, max: hi + pad };
}

/** Concise category labels; most slots blank to reduce density. */
export function sparseCategoryLabels(
  timestamps: string[],
  maxLabels = 7,
): string[] {
  const n = timestamps.length;
  if (n === 0) return [];
  const step = Math.max(1, Math.ceil(n / maxLabels));
  return timestamps.map((ts, i) => {
    if (i !== 0 && i !== n - 1 && i % step !== 0) return "";
    const norm = normalizeNaive(ts);
    // MM-DD HH:mm
    return `${norm.slice(5, 10)} ${norm.slice(11, 16)}`;
  });
}

export function pressureChange30m(
  points: ReadingPoint[],
  cursor: string,
): PressureComparison {
  const cursorN = normalizeNaive(cursor);
  const priorCursor = addSeconds(cursorN, -COMPARE_OFFSET_SECONDS);
  const ordered = [...points]
    .map((p) => ({ ts: normalizeNaive(p.ts), value: p.value }))
    .filter((p) => parseNaive(p.ts).getTime() <= parseNaive(cursorN).getTime())
    .sort((a, b) => parseNaive(a.ts).getTime() - parseNaive(b.ts).getTime());

  const current = latestAtOrBefore(ordered, cursorN);
  const prior = latestAtOrBefore(ordered, priorCursor);
  const currentStatus = freshnessAt(current?.ts ?? null, cursorN);
  const priorStatus = freshnessAt(prior?.ts ?? null, priorCursor);

  if (currentStatus !== "current" || priorStatus !== "current") {
    const reasons: string[] = [];
    if (currentStatus === "missing") reasons.push("current observation missing");
    if (currentStatus === "stale") reasons.push("current observation stale");
    if (priorStatus === "missing") reasons.push("prior (−30 min) observation missing");
    if (priorStatus === "stale") reasons.push("prior (−30 min) observation stale");
    return {
      available: false,
      cursor: cursorN,
      priorCursor,
      currentValue: current?.value ?? null,
      currentTs: current?.ts ?? null,
      currentStatus,
      priorValue: prior?.value ?? null,
      priorTs: prior?.ts ?? null,
      priorStatus,
      deltaM: null,
      unavailableReason: reasons.join("; "),
    };
  }

  return {
    available: true,
    cursor: cursorN,
    priorCursor,
    currentValue: current!.value,
    currentTs: current!.ts,
    currentStatus,
    priorValue: prior!.value,
    priorTs: prior!.ts,
    priorStatus,
    deltaM: current!.value - prior!.value,
    unavailableReason: null,
  };
}

export function findObservation(
  observations: SnapshotObservation[],
  sensorId: string,
): SnapshotObservation | null {
  return observations.find((o) => o.sensor_id === sensorId) ?? null;
}

export function midpointTimestamp(timestamps: string[]): string | null {
  if (timestamps.length === 0) return null;
  return timestamps[Math.floor((timestamps.length - 1) / 2)] ?? null;
}
