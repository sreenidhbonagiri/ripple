# CUSUM-h calibration extension — original relationship signal

Generated: 2026-10-24T21:07:49-04:00

Continues DEV-only threshold calibration on `build_signals.z`. Does **not** overwrite `THRESHOLD_CALIBRATION_RESULTS.md`. Context correction not used.

Fixed: K=3, k=0.5, residual_recover_steps=12, train_days=14.
Provisional unmatched/week cap: **≤ 3** (not operator-validated).
Useful abrupt sensitivity: **≥ 0.6667** (6 h window).

## Input hashes

- `2018_SCADA_Pressures.csv`: `7782d890a7195699be94ddc01cba392da7ca285908afff619065a9616e04dcae`
- `2018_SCADA_Flows.csv`: `7f7e8625c9d92b083ee079a54cffb9ef803876de1e35017c1da0455968daf3ff`
- `2018_SCADA_Levels.csv`: `a1fc5f0229448a620b6220f4d079b3162a255b3070acdce448608fbfc760903c`
- DEV `z` sha256[:16]: `ad73a40a8a17d109`

## DEV grid extension (every setting)

| h | Abrupt 6h recall | Med delay 6h (h) | Unmatched/wk | Dup 24h | Union occ% | Sensor-alarm% | Active med/p90/max | Med ep (h) | Longest (h) | Censored | Episodes | Latch? |
|---|------------------|------------------|--------------|---------|-----------|---------------|-------------------|------------|-------------|----------|----------|--------|
| 512 | 0.67 | 0.500 | 4.99 | 103 | 92.48 | 12.34 | 2.0/10.0/12 | 59.83 | 976.5833333333334 | 1 | 137 | no |
| 1024 | 0.67 | 1.375 | 3.60 | 72 | 86.73 | 10.85 | 2.0/9.0/12 | 71.17 | 985.4166666666666 | 1 | 101 | no |
| 2048 | 1.00 | 3.250 | 2.48 | 44 | 80.71 | 9.37 | 1.0/9.0/10 | 127.08 | 923.0833333333334 | 1 | 72 | no |
| 4096 | 0.33 | 1.750 | 1.93 | 26 | 68.29 | 7.02 | 1.0/7.0/10 | 94.75 | 838.5 | 0 | 58 | no |
| 8192 | 0.00 |  | 1.47 | 15 | 51.30 | 4.64 | 1.0/5.0/8 | 88.21 | 722.75 | 0 | 44 | no |
| 16384 | 0.00 |  | 0.70 | 2 | 42.99 | 2.98 | 0.0/3.0/5 | 118.67 | 569.25 | 0 | 24 | no |

### Per-setting event notification times (post-training eligible)

#### h=512

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-01-29 17:55 delay_h=157.5 sensor=n1
- HIT p232 (incipient) onset=2018-01-31 02:35 notify=2018-02-01 20:40 delay_h=42.083333333333336 sensor=n1
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-18 11:35 delay_h=123.16666666666667 sensor=n114
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-05 16:30 delay_h=0.75 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-03 20:30 delay_h=29.583333333333332 sensor=n1
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-19 03:05 delay_h=18.5 sensor=n296
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-01 09:20 delay_h=0.25 sensor=n296
- HIT p31 (incipient) onset=2018-06-28 10:35 notify=2018-06-28 22:30 delay_h=11.916666666666666 sensor=n1
- Latch inspection: union=92.5% sensor=12.3% censored=1 longest_h=976.5833333333334 — No strong latched-only signature under declared heuristics.

#### h=1024

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-01-23 21:40 delay_h=17.25 sensor=n1
- HIT p232 (incipient) onset=2018-01-31 02:35 notify=2018-02-02 06:35 delay_h=52.0 sensor=n1
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-20 05:45 delay_h=165.33333333333334 sensor=n1
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-05 17:20 delay_h=1.5833333333333333 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-04 06:55 delay_h=40.0 sensor=n1
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-19 02:25 delay_h=17.833333333333332 sensor=n288
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-01 10:15 delay_h=1.1666666666666667 sensor=n296
- HIT p31 (incipient) onset=2018-06-28 10:35 notify=2018-06-29 13:15 delay_h=26.666666666666668 sensor=n1
- Latch inspection: union=86.7% sensor=10.8% censored=1 longest_h=985.4166666666666 — No strong latched-only signature under declared heuristics.

#### h=2048

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-01-30 22:40 delay_h=186.25 sensor=n1
- HIT p232 (incipient) onset=2018-01-31 02:35 notify=2018-02-02 21:10 delay_h=66.58333333333333 sensor=n1
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-13 18:25 delay_h=10.0 sensor=n1
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-05 19:00 delay_h=3.25 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-04 20:40 delay_h=53.75 sensor=n1
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-18 12:20 delay_h=3.75 sensor=n506
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-01 11:55 delay_h=2.8333333333333335 sensor=n296
- HIT p31 (incipient) onset=2018-06-28 10:35 notify=2018-06-30 06:35 delay_h=44.0 sensor=n1
- Latch inspection: union=80.7% sensor=9.4% censored=1 longest_h=923.0833333333334 — No strong latched-only signature under declared heuristics.

#### h=4096

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-01-25 06:55 delay_h=50.5 sensor=n1
- HIT p232 (incipient) onset=2018-01-31 02:35 notify=2018-02-01 17:20 delay_h=38.75 sensor=n1
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-15 11:20 delay_h=50.916666666666664 sensor=n1
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-05 22:15 delay_h=6.5 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-03 15:15 delay_h=24.333333333333332 sensor=n1
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-19 04:45 delay_h=20.166666666666668 sensor=n506
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-01 10:50 delay_h=1.75 sensor=n296
- HIT p31 (incipient) onset=2018-06-28 10:35 notify=2018-06-28 16:50 delay_h=6.25 sensor=n1
- Latch inspection: union=68.3% sensor=7.0% censored=0 longest_h=838.5 — No strong latched-only signature under declared heuristics.

#### h=8192

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-01-28 06:50 delay_h=122.41666666666667 sensor=n1
- MISS p232 (incipient) onset=2018-01-31 02:35 notify=None delay_h=None sensor=None
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-18 19:35 delay_h=131.16666666666666 sensor=n1
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-06 05:45 delay_h=14.0 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-06 12:00 delay_h=93.08333333333333 sensor=n1
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-20 03:10 delay_h=42.583333333333336 sensor=n288
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-01 17:15 delay_h=8.166666666666666 sensor=n296
- MISS p31 (incipient) onset=2018-06-28 10:35 notify=None delay_h=None sensor=None
- Latch inspection: union=51.3% sensor=4.6% censored=0 longest_h=722.75 — No strong latched-only signature under declared heuristics.

#### h=16384

- HIT p461 (incipient) onset=2018-01-23 04:25 notify=2018-02-03 18:05 delay_h=277.6666666666667 sensor=n1
- MISS p232 (incipient) onset=2018-01-31 02:35 notify=None delay_h=None sensor=None
- HIT p427 (incipient) onset=2018-02-13 08:25 notify=2018-02-18 05:20 delay_h=116.91666666666667 sensor=n1
- HIT p673 (abrupt) onset=2018-03-05 15:45 notify=2018-03-06 19:20 delay_h=27.583333333333332 sensor=n229
- HIT p628 (incipient) onset=2018-05-02 14:55 notify=2018-05-14 14:25 delay_h=287.5 sensor=n613
- HIT p538 (abrupt) onset=2018-05-18 08:35 notify=2018-05-19 04:30 delay_h=19.916666666666668 sensor=n188
- HIT p866 (abrupt) onset=2018-06-01 09:05 notify=2018-06-02 09:45 delay_h=24.666666666666668 sensor=n296
- MISS p31 (incipient) onset=2018-06-28 10:35 notify=None delay_h=None sensor=None
- Latch inspection: union=43.0% sensor=3.0% censored=0 longest_h=569.25 — No strong latched-only signature under declared heuristics.

## Selection

- gate_met: **True**
- selected h: **2048.0**
- rule: among unmatched/wk<=3 AND abrupt_6h_recall>=2/3 AND not latched_suspect: max abrupt_6h recall, then min median 6h delay, then min unmatched/wk; else selection failure at this range
- note: 

## DIAG (frozen h — diagnostic only)

- Abrupt 6h recall: **0.00** (0/3); delays_6h={'n': 0, 'median': None, 'max': None, 'values': []}
- Abrupt recall (registered window): **1.00** delays={'n': 3, 'median': 17.75, 'max': 91.75, 'values': [10.0, 17.75, 91.75]}
- Incipient recall: **1.00**
- Unmatched/wk: **0.88**; dup: 7
- Union occ%: 87.03; sensor-alarm%: 6.30
- Active sensors mean/med/p90/max: 2.08/1.00/6.00/7
- Median / longest episode (h): 110.5 / 3416.5833333333335; censored: 1
- Latch inspection: No strong latched-only signature under declared heuristics.

Per-event (post-training eligible):

- HIT p810 (incipient) onset=2018-07-28 03:05 notify=2018-07-30 12:30 delay_h=57.416666666666664 sensor=n4
- HIT p183 (abrupt) onset=2018-08-07 02:35 notify=2018-08-07 12:35 delay_h=10.0 sensor=n4
- HIT p158 (abrupt) onset=2018-10-06 02:35 notify=2018-10-06 20:20 delay_h=17.75 sensor=n644
- HIT p369 (abrupt) onset=2018-10-26 02:05 notify=2018-10-29 21:50 delay_h=91.75 sensor=n410

Prefix (separate):

- MISS p654 (incipient) notify=None delay_h=None

## 0–2 h notification-time shifted null (diagnostic)

- Observed abrupt matches: **0** / 3
- Null median (min–max): 0.0 (0–1)
- Frac shifts ≥ obs: **1.00** (n_shifts=89)

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

## Interpretation

Frozen h=2048 met both **DEV** gates (6 h abrupt recall 1.00; unmatched/wk 2.48) without a latched-only signature under the declared heuristics. On **DIAG** (diagnostic only): unmatched/wk fell to 0.88 and sensor-alarm% to 6.3, but **useful 6 h abrupt sensitivity collapsed to 0/3** (delays 10.0, 17.75, 91.75 h — still counted under the registered 7-day window). The 0–2 h shifted null observed 0 matches (frac ≥ obs = 1.00). Union occupancy remained high (87%) with a very long episode (3416 h), so workload thinning is not a clean timing-preserving success. Threshold calibration here does **not** preserve declared useful event timing while reducing nuisance.

## Recommendation

**No-go:** calibrated h loses useful six-hour abrupt sensitivity on DIAG.

