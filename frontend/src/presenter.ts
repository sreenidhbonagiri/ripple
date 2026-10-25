/**
 * Jan 12 illustrative investigation preset (Milestone 5).
 * Chosen after verifying fresh 30-minute pressure deltas in the window.
 * Observation walkthrough only — not a detected leak.
 */

export const PRESENTER = {
  label: "Illustrative investigation — Jan 12 afternoon",
  disclaimer:
    "Selected historical pressure pattern for walkthrough only. Not a detected leak, alert, or localization result.",
  windowStart: "2019-01-12 14:00:00",
  windowEnd: "2019-01-12 17:00:00",
  illustrativeSensorId: "n54",
  bookmarks: [
    {
      id: "window_start",
      label: "Start 14:00",
      cursor: "2019-01-12 14:00:00",
      selectSensor: false,
    },
    {
      id: "illustrative_pressure_change",
      label: "Illustrative Δ 15:00",
      cursor: "2019-01-12 15:00:00",
      selectSensor: true,
      note: "n54 · largest fresh 30-min pressure drop in this window (observation only)",
    },
    {
      id: "midpoint",
      label: "Midpoint 15:30",
      cursor: "2019-01-12 15:30:00",
      selectSensor: false,
    },
  ],
} as const;

export type WarningDemoId = "jan24_1830" | "jan15_2300";

/**
 * Experimental Method M warning demos (January frozen five-minute notifies).
 * Sensor IDs are argmax contributors from
 * artifacts/method_m_experimental_january/serving_hours.json — not guessed leak pipes.
 */
export const WARNING_DEMOS: Record<
  WarningDemoId,
  {
    id: WarningDemoId;
    label: string;
    buttonLabel: string;
    disclaimer: string;
    windowStart: string;
    windowEnd: string;
    cursor: string;
    sensorId: string;
    notifyTs: string;
    primary: boolean;
  }
> = {
  jan24_1830: {
    id: "jan24_1830",
    label: "Experimental Method M warning — 24 Jan 18:30",
    buttonLabel: "Method M notify 18:30 (24 Jan)",
    disclaimer:
      "Frozen Method M five-minute notification (24 Jan 18:30) for walkthrough only. Experimental anomaly warning — not a confirmed leak. Contributing sensors are dual-context evidence, not leak locations.",
    windowStart: "2019-01-24 16:30:00",
    windowEnd: "2019-01-24 20:30:00",
    cursor: "2019-01-24 18:30:00",
    /** Argmax from serving_hours.json at notify stamp */
    sensorId: "n726",
    notifyTs: "2019-01-24 18:30:00",
    primary: true,
  },
  jan15_2300: {
    id: "jan15_2300",
    label: "Experimental Method M warning — 15 Jan 23:00",
    buttonLabel: "Method M notify 23:00 (15 Jan)",
    disclaimer:
      "Frozen Method M five-minute notification (15 Jan 23:00) for walkthrough only. Experimental anomaly warning — not a confirmed leak. Contributing sensors are dual-context evidence, not leak locations.",
    windowStart: "2019-01-15 21:00:00",
    windowEnd: "2019-01-16 01:00:00",
    cursor: "2019-01-15 23:00:00",
    /** Argmax from serving_hours.json at notify stamp */
    sensorId: "n506",
    notifyTs: "2019-01-15 23:00:00",
    primary: false,
  },
};

/** @deprecated Prefer WARNING_DEMOS.jan24_1830 — kept for any residual imports */
export const WARNING_DEMO = WARNING_DEMOS.jan24_1830;

export function warningDemoForCursor(cursor: string | null | undefined) {
  if (!cursor) return null;
  for (const demo of Object.values(WARNING_DEMOS)) {
    if (demo.cursor === cursor || demo.notifyTs === cursor) return demo;
  }
  return null;
}

/** Match an active Method M demo by its playback window (survives mid-window seeking). */
export function warningDemoForWindow(
  windowStart: string | null | undefined,
  windowEnd: string | null | undefined,
) {
  if (!windowStart || !windowEnd) return null;
  for (const demo of Object.values(WARNING_DEMOS)) {
    if (demo.windowStart === windowStart && demo.windowEnd === windowEnd) {
      return demo;
    }
  }
  return null;
}
