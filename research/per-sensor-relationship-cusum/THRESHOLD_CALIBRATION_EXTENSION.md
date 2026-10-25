# DEV CUSUM-\(h\) grid extension (registered before runs)

Continues the existing DEV-only threshold experiment on the **reconciled**
original `build_signals.z` signal. Does **not** overwrite
`outputs/THRESHOLD_CALIBRATION_RESULTS.md` or other historical reports.

## Motivation

The first predeclared grid \(h\in\{8,16,32,64,128,256\}\) failed the provisional
workload gate; the best unmatched/week was at the **upper boundary** \(h=256\)
(7.93/wk). This extension continues the same experiment at higher \(h\) only.

## Held fixed (unchanged from first calibration)

| Element | Value |
|---------|--------|
| Signal | `build_signals.z` (authoritative; not context correction) |
| Refs / pairwise OLS / normalization | Existing `build_signals` |
| \(k\) | 0.5 |
| Recovery | Residual-recovery: 12 finite steps with \(z\le k\) |
| Eligibility / missing data / matching | Unchanged (post-training primary; prefix separate) |
| Sensors | Full 33-sensor notification pipeline |
| Inputs | Identical 2018 SCADA paths; record sha256 hashes |

## Varied (DEV only — this extension)

\[
h \in \{512, 1024, 2048, 4096, 8192, 16384\}
\]

Do **not** silently extend further if none qualify.

## DEV targets (both required)

1. **Useful abrupt sensitivity (declared):** at least **2/3** of eligible DEV
   abrupt events notified within **six hours** of onset
   (`abrupt_recall_6h ≥ 2/3`).
2. **Provisional workload:** unmatched notifications/week **≤ 3**
   (research budget — **not** operator-validated).

Low notification counts achieved only through **persistently latched** alarms
are **not** success. Inspect timelines (union occupancy, episode lengths,
right-censoring, active-sensor counts) before claiming burden reduction.

## Selection

Among settings meeting **both** targets: maximize `abrupt_recall_6h`, then
minimize median abrupt notification delay (among 6 h hits / matched delays),
then minimize unmatched/week.
If **none** qualify → report **failure at this range**; do not invent a winner;
do not silently extend the grid.

Freeze before DIAG. **Do not** select from DIAG or score the full grid on DIAG.
Do **not** run 2019.

## DIAG (only if a setting qualifies)

Run the frozen \(h\) **once**. Same metrics + existing 0–2 h notification-time
shifted null. Label **diagnostic** (prior examination). No broad-window headline;
no already-active-alarm credit as success.

## Reporting (every setting)

- Abrupt recall within six hours; all event notification times / delays
- Unmatched/week and duplicate burden
- Sensor occupancy; network union occupancy
- Active-sensor count distribution
- Median / longest episode; right-censored count
