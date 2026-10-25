# 2018 dual-model detection feasibility results

Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Generated: `2026-10-25T04:44:38.553090+00:00`  
Protocol: `DETECTION_PROTOCOL.md` (registered before run).

2018 events have already been examined; DIAG is protocol-bound diagnostic evaluation, not a first look.

**Any method passed DEV gates:** `False`

**Selection FAILED** for A, B, and C under the registered gates
(`abrupt_6h_recall ≥ 2/3` and `unmatched/week ≤ 3`). DIAG rows below use
protocol fallback τ values and are **diagnostic only** — not a frozen passing
detector.

Method B saturates (occupancy ≈ 1): the vector-change score stays above τ/2
almost continuously after the first notify, so the notifier never recovers.
That is a method failure under this normalization, not a quiet detector.

## DEV selection

| Method | selection_passed | τ | fallback | DEV recall | DEV unmatched/wk |
|--------|------------------|---:|----------|------------:|-----------------:|
| A | False | 1.5 | True | 0.6666666666666666 | 4.345 |
| B | False | 1.0 | True | 0.0 | 0.040 |
| C | False | 1.0 | True | 0.3333333333333333 | 14.161 |

## DIAG (frozen τ; diagnostic if selection failed)

| Method | τ | sel_ok | abrupt 6h recall | mean delay h | unmatched/wk | occupancy | trans. frac unmatched | null recall mean | true pct vs null |
|--------|---:|--------|-----------------:|-------------:|-------------:|----------:|---------------------:|-----------------:|-----------------:|
| A | 1.5 | False | 0.0 | None | 3.728 | 0.064 | 0.9795918367346939 | 0.0 | 1.0 |
| B | 1.0 | False | 0.0 | None | 0.038 | 1.000 | 0.0 | 0.0 | 1.0 |
| C | 1.0 | False | 0.6666666666666666 | 2.1666666666666665 | 14.152 | 0.545 | 0.9919354838709677 | 0.925 | 0.2 |

## Per-event DIAG

### Method A

| Pipe | Onset | Hit | Delay h |
|------|-------|-----|--------:|
| p183 | 2018-08-07 02:35:00 | False | None |
| p158 | 2018-10-06 02:35:00 | False | None |
| p369 | 2018-10-26 02:05:00 | False | None |

### Method B

| Pipe | Onset | Hit | Delay h |
|------|-------|-----|--------:|
| p183 | 2018-08-07 02:35:00 | False | None |
| p158 | 2018-10-06 02:35:00 | False | None |
| p369 | 2018-10-26 02:05:00 | False | None |

### Method C

| Pipe | Onset | Hit | Delay h |
|------|-------|-----|--------:|
| p183 | 2018-08-07 02:35:00 | False | None |
| p158 | 2018-10-06 02:35:00 | True | 2.4166666666666665 |
| p369 | 2018-10-26 02:05:00 | True | 1.9166666666666667 |

## Notes

- A = signed total q_v change; B = per-sensor vector L2 change; C = |external inflow| change.
- Virtual flow is not measured leak discharge.
- No event-specific sensor selection or post-hoc τ retuning.
- Stop: no 2019 / UI / Tiger / production / main.

