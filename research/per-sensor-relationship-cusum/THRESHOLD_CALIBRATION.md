# Bounded CUSUM-\(h\) calibration (registered before runs)

**Signal:** original per-sensor relationship \(z_i\) from `build_signals`
(authoritative residual-recovery baseline after `BASELINE_RECONCILIATION.md`).

**Not used:** unsuccessful context correction; recovery sweeps; feature/model search.

## Held fixed

| Element | Value |
|---------|--------|
| Refs / pairwise OLS / normalization | Existing `build_signals` |
| \(k\) | 0.5 |
| Recovery | Residual-recovery: 12 finite steps with \(z\le k\) |
| Missing data / matching / eligibility | Unchanged (post-training primary; prefix separate) |
| Sensors | Full 33-sensor notification pipeline |

## Varied (DEV only)

\[
h \in \{8, 16, 32, 64, 128, 256\}
\]

## DEV selection (provisional)

Workload target: **unmatched notifications/week ≤ 3** (research budget — **not**
operator-validated).

Among settings meeting the target: maximize post-training **abrupt recall**, then
minimize median abrupt **notification delay**, then minimize unmatched/week.
If **none** qualify → record `gate_met=false` / selection failure (do not invent a winner).

Freeze before DIAG. **Do not** score the full grid on DIAG or pick from DIAG.

## DIAG

Run the frozen \(h\) **once**. Report the same metrics + 0–2 h notification-time
shifted null. Diagnostic label only (prior examination). No broad-window headline;
no already-active-alarm credit as success. Latched-alarm-only burden reduction ≠ success.
