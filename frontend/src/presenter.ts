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

/**
 * Separate Experimental Method M warning demo (January frozen notify).
 * Uses an actual frozen notification timestamp — not the Jan 12 preset.
 * Does not claim a confirmed leak or localize a pipe.
 */
export const WARNING_DEMO = {
  label: "Experimental Method M warning demo",
  disclaimer:
    "Frozen Method M five-minute notification for walkthrough only. Experimental anomaly warning — not a confirmed leak. Not pipe localization.",
  /** Short window around the frozen notify so the timeline can leave Jan 12. */
  windowStart: "2019-01-15 21:00:00",
  windowEnd: "2019-01-16 01:00:00",
  /** First frozen January Method M notification (five-minute grid). */
  cursor: "2019-01-15 23:00:00",
  /** Argmax contributing sensor at the notify stamp (measured dual context). */
  sensorId: "n506",
  notifyTs: "2019-01-15 23:00:00",
} as const;
