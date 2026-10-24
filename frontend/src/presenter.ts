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
