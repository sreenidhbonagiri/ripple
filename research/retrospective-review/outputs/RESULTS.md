# Retrospective pressure-pattern review — Phase 2 report

Generated: 2026-10-24T19:31:24-04:00

Deployed Ripple remains an investigation workspace **without** a validated automatic
leak detector. Candidates below are **not** confirmed leaks and are **not** live alerts.

2019 is not evaluated; it has already been examined historically and is not a new blind holdout. 2018 labels are for documented DEV/DIAG matching only.

## Method (see DESIGN.md)

Independent LILA-inspired pairwise OLS residuals + offline CUSUM on Frobenius-like
aggregate score. No GPL code copied. No leak-location-based sensor/pair selection.

Frozen settings (DEV→lock): `{'train_days': 14, 'cusum_k': 0.5, 'cusum_h': 8.0, 'min_segment_hours': 24.0}`
DEV unmatched/wk ≤ 3.0 gate met: **False**

Unmatched candidates are **not** automatic false positives (background leaks / ops).
Estimated change times are retrospective within the interval — not real-time alerts.

## DEV selection summary

- train=7d h=4.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=11.87
- train=7d h=4.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.38
- train=7d h=6.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=11.76
- train=7d h=6.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.38
- train=7d h=8.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=11.56
- train=7d h=8.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.38
- train=14d h=4.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=10.52
- train=14d h=4.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.11
- train=14d h=6.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=10.40
- train=14d h=6.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.11
- train=14d h=8.0 min_seg=12.0h → abrupt_recall=1.00 unmatched/wk=10.33
- train=14d h=8.0 min_seg=24.0h → abrupt_recall=1.00 unmatched/wk=6.11

## DIAG (frozen)

- Abrupt recall: **1.00** (3 onsets)
- Incipient recall: **1.00** (2 onsets)
- Unmatched candidates/week: **5.14**
- Median candidate duration (h): 24.375
- Duplicate unmatched within 24h: 96
- Change-time error hours: {'n': 5, 'median': 7.166666666666667, 'p90': 152.23333333333335, 'max_abs': 243.16666666666666}
- Runtime: 0.4s · volume row×sensor=1748736
- Ordinary controls (large ΔPUMP_1/ΔT1 near candidate): {'sampled_large_context_moves': 40, 'within_6h_of_candidate': 0, 'fraction': 0.0}

### DIAG matches / misses

- HIT p654 (incipient) onset 2018-07-05 03:40 change=2018-07-15 06:50 err_h=243.16666666666666
- HIT p810 (incipient) onset 2018-07-28 03:05 change=2018-07-28 10:15 err_h=7.166666666666667
- HIT p183 (abrupt) onset 2018-08-07 02:35 change=2018-08-06 23:55 err_h=-2.6666666666666665
- HIT p158 (abrupt) onset 2018-10-06 02:35 change=2018-10-06 18:25 err_h=15.833333333333334
- HIT p369 (abrupt) onset 2018-10-26 02:05 change=2018-10-26 02:00 err_h=-0.08333333333333333

## Limitations

- Training prefix is chronological, not verified leak-free (unlike LILA’s manual period).
- All-pairs aggregation does not disaggregate overlapping leaks.
- No hydraulic localization; MAS not claimed.
- Not BattLeDIM economic scoring; not paper reproduction.
- 2019 not evaluated (already historically examined).

## Path to product (if go)

select historical interval → review candidate changes → inspect sensor/flow/tank
evidence in the existing investigation workspace → save investigation metadata.

## Recommendation

**No-go**: no DEV setting met the pre-registered unmatched/wk ≤ 3.0 gate (best DEV unmatched/wk=6.11). DIAG under fallback freeze: abrupt_recall=1.00, unmatched/wk=5.14. Do not build UI/API on this operating point; revisit with a new pre-registered method (e.g. pair subsetting without leak labels, recalibration, or stronger ordinary-ops filters).

