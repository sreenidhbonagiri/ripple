# Pressure week-residual experiment — 2018 results

Generated: 2026-10-24T18:55:30-04:00

Previously examined 2018/2019 cases are development/diagnostic, not a blind holdout. 2019 is not evaluated for new settings in this run.

## Frozen settings (selected on DEV, then locked)

- Residual τ = **1.5** m (week residual), confirm_k=3, clear_m=6
- Baseline τ_b = **1.1** m (30‑minute raw drop), same episode policy
- Causality probe (future mutation): True
- Warm prefix all missing_history: True; post-warm missing fraction=0.0

## DEV (setting selection)

| Method | τ | Onset recall | Abrupt recall | Unmatched/wk | Time in alarm | Longest ep (h) |
|--------|---|--------------|---------------|--------------|---------------|----------------|
| week_residual | 1.50 | 0.22 | 0.67 | 0.44 | 0.003 | 2.4 |
| raw_30m_drop | 1.10 | 0.22 | 0.33 | 1.41 | 0.001 | 0.3 |

## DIAG (frozen only; not used for tuning)

| Method | τ | Onset recall | Abrupt recall | Unmatched/wk | Time in alarm | Longest ep (h) |
|--------|---|--------------|---------------|--------------|---------------|----------------|
| week_residual | 1.50 | 0.00 | 0.00 | 0.30 | 0.004 | 6.6 |
| raw_30m_drop | 1.10 | 0.00 | 0.00 | 2.13 | 0.002 | 0.3 |

### DIAG onset match detail (residual)

- MISS p654 (incipient) onset 2018-07-05 03:40 → notify None delay — strong=None open_leaks_at_notify=None
- MISS p810 (incipient) onset 2018-07-28 03:05 → notify None delay — strong=None open_leaks_at_notify=None
- MISS p183 (abrupt) onset 2018-08-07 02:35 → notify None delay — strong=None open_leaks_at_notify=None
- MISS p158 (abrupt) onset 2018-10-06 02:35 → notify None delay — strong=None open_leaks_at_notify=None
- MISS p369 (abrupt) onset 2018-10-26 02:05 → notify None delay — strong=None open_leaks_at_notify=None

### DIAG onset match detail (baseline)

- MISS p654 (incipient) onset 2018-07-05 03:40 → notify None delay — strong=None
- MISS p810 (incipient) onset 2018-07-28 03:05 → notify None delay — strong=None
- MISS p183 (abrupt) onset 2018-08-07 02:35 → notify None delay — strong=None
- MISS p158 (abrupt) onset 2018-10-06 02:35 → notify None delay — strong=None
- MISS p369 (abrupt) onset 2018-10-26 02:05 → notify None delay — strong=None

## Ordinary operating spotchecks (DEV, context only)

Large prior-week ΔPUMP_1 or ΔT1 samples — score may rise without implying a new onset.

- 2018-01-17 18:00: ΔPUMP_1=-43.89, ΔT1=-1.430, score=1.489999771118164, exceed_tau_next_h=True, open_leaks=1
- 2018-01-10 18:00: ΔPUMP_1=43.89, ΔT1=1.400, score=0.8799972534179688, exceed_tau_next_h=False, open_leaks=1
- 2018-01-10 19:00: ΔPUMP_1=-44.13, ΔT1=1.360, score=-0.009998321533203125, exceed_tau_next_h=False, open_leaks=1
- 2018-01-17 04:00: ΔPUMP_1=44.10, ΔT1=1.360, score=0.5099983215332031, exceed_tau_next_h=False, open_leaks=1
- 2018-01-17 19:00: ΔPUMP_1=44.14, ΔT1=-1.330, score=1.3699989318847656, exceed_tau_next_h=False, open_leaks=1
- 2018-01-17 07:00: ΔPUMP_1=-44.18, ΔT1=1.300, score=0.0, exceed_tau_next_h=False, open_leaks=1
- 2018-01-10 02:00: ΔPUMP_1=-44.06, ΔT1=-1.280, score=1.19000244140625, exceed_tau_next_h=False, open_leaks=1
- 2018-01-10 07:00: ΔPUMP_1=44.18, ΔT1=-1.210, score=1.220001220703125, exceed_tau_next_h=False, open_leaks=1
- 2018-01-09 13:00: ΔPUMP_1=43.80, ΔT1=1.210, score=1.0699996948242188, exceed_tau_next_h=False, open_leaks=1
- 2018-01-17 03:00: ΔPUMP_1=44.11, ΔT1=1.190, score=0.6300010681152344, exceed_tau_next_h=False, open_leaks=1
- 2018-01-17 17:00: ΔPUMP_1=-43.93, ΔT1=-1.180, score=1.260000228881836, exceed_tau_next_h=False, open_leaks=1
- 2018-01-10 17:00: ΔPUMP_1=43.93, ΔT1=1.160, score=0.8400001525878906, exceed_tau_next_h=False, open_leaks=1

## Comparison & recommendation

On frozen DIAG, both week-residual (τ=1.5) and the burden-targeted raw 30‑minute baseline (τ_b=1.1) achieve **0 abrupt onset recall** (unmatched/wk 0.30 vs 2.13; DEV had selected residual unmatched/wk=0.44 vs baseline 1.41). DEV abrupt hits (e.g. residual 0.67) did not transfer. **Recommendation:** do not promote this week-residual detector; the hypothesis is unsupported at the pre-registered operating point. Do not add AMR or veto gates until a new pre-registered score shows DIAG gains beyond the raw-drop baseline.

Flow/pump/tank were **not** used as vetoes. AMR was not used. Do not promote from a single attractive match. 2019 not evaluated here.

