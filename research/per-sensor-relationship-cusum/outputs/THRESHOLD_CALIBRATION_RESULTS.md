# CUSUM-h calibration — original relationship signal

Generated: 2026-10-24T20:48:21-04:00

Authoritative signal: `build_signals.z` (see `BASELINE_RECONCILIATION.md`). Context correction not used. Historical VARIANT/CONTEXT/RESULTS reports preserved.

Fixed: K=3, k=0.5, residual_recover_steps=12, train_days=14.
Provisional unmatched/week cap: **≤ 3** (not operator-validated).

## DEV grid (every setting)

| h | Abrupt recall | Median delay (h) | Unmatched/wk | Dup 24h | Union occ% | Sensor-alarm% | Longest (h) | Censored | Episodes |
|---|---------------|------------------|--------------|---------|-----------|---------------|-------------|----------|----------|
| 8 | 1.00 | 0.000 | 91.77 | 2373 | 99.98 | 33.54 | 1014.6666666666666 | 13 | 2381 |
| 16 | 1.00 | 0.000 | 69.73 | 1803 | 99.94 | 27.45 | 1013.9166666666666 | 10 | 1811 |
| 32 | 1.00 | 0.000 | 51.09 | 1321 | 99.79 | 22.69 | 1012.5833333333334 | 9 | 1329 |
| 64 | 1.00 | 0.083 | 27.73 | 717 | 98.58 | 18.30 | 1010.9166666666666 | 4 | 725 |
| 128 | 1.00 | 0.167 | 13.30 | 339 | 97.13 | 15.58 | 1006.9166666666666 | 2 | 352 |
| 256 | 1.00 | 0.333 | 7.93 | 191 | 95.49 | 13.85 | 991.5833333333334 | 2 | 213 |

## Selection

- gate_met: **False**
- selected h: **None**
- rule: among unmatched/wk<=3: max abrupt recall, then min median delay, then min unmatched/wk; else selection failure
- note: No DEV setting met provisional unmatched/week ≤ 3; DIAG not run for a new h.

**Selection failure:** no DEV setting met unmatched/week ≤ 3. No invented winner. DIAG not run under a new h.

## Timing vs nuisance (DEV grid only; no frozen DIAG)

Raising \(h\) monotonically cut unmatched/week (91.8→7.9) and sensor-alarm occupancy (33.5%→13.9%) while abrupt recall stayed 1.00; median delay rose only from 0 to 0.33 h. That pattern is consistent with preserving useful event timing while thinning some storm volume—but **union occupancy remained ≥95%** and the best unmatched/week (**7.93**) still missed the provisional ≤3 gate. Fewer notifications from longer latched alarms alone would not count as success; here the unmatched rate stayed high enough that **selection failed** and DIAG was not run under a new \(h\).

## Recommendation

**Selection failure / no-go on this calibration:** no h in [8.0, 16.0, 32.0, 64.0, 128.0, 256.0] achieved provisional unmatched/week ≤ 3 on DEV under the fixed residual-recovery policy and original relationship signal. Do not invent a winner; do not retune recovery or features here.

