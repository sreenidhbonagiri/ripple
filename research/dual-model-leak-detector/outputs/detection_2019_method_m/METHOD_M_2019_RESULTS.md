# Frozen Method M on 2019 — diagnostic evaluation

**Not a blind holdout.** 2019 has already been examined during previous research; this is a frozen diagnostic evaluation, not a blind holdout.

Generated: `2026-10-25T05:22:40.531735+00:00`  
τ=`4.347` (frozen). Calibration `5fab3acbf13f018d…`.  
Pre-label score hash `6578b9b04d073732…`; notify hash `3ae2528e1c832a06…`.

See `PRE_INFERENCE_FROZEN_BUNDLE.md` and `pre_inference_hashes.json`.

## Dual / availability

- Solver failures: **0** / 53 chunks
- 2019 score hours: 8760 (finite 8760, NaN 0)
- First finite score in 2019: `2019-01-01 00:00:00`
- Notifier: continuous across 2018→2019 concat; **no** reset at onsets/months

## Abrupt six-hour recall (2019 onsets)

| n eligible | n warmup excl. | recall | mean delay h | pre-onset blocked |
|----------:|---------------:|-------:|-------------:|------------------:|
| 9 | 0 | 0.3333333333333333 | 0.27777777777777773 | 0 |

| Pipe | Onset | Hit | Delay h | Pre-onset blocked | Credit max | Warm-up excl. |
|------|-------|:---:|--------:|:-----------------:|-----------:|:-------------:|
| p523 | 2019-01-15 23:00:00 | True | 0.0 | False | 9.53013995428885 | False |
| p827 | 2019-01-24 18:30:00 | True | 0.5 | False | 7.114499673759209 | False |
| p280 | 2019-02-10 13:05:00 | False | None | False | 1.0845335757552768 | False |
| p710 | 2019-03-24 14:15:00 | False | None | False | 1.9279210801797297 | False |
| p514 | 2019-04-02 20:40:00 | True | 0.3333333333333333 | False | 4.820457561442025 | False |
| p331 | 2019-04-20 10:10:00 | False | None | False | 3.2441876333515207 | False |
| p142 | 2019-06-12 19:55:00 | False | None | False | 3.9990978753334523 | False |
| p680 | 2019-07-10 08:45:00 | False | None | False | 1.3718546195865295 | False |
| p426 | 2019-10-25 13:25:00 | False | None | False | 1.0856344863348295 | False |

## Incipient (separate; 6 h from catalog startTime)

Eligible recall: **0.0** (0/10); warmup excluded 0.

| Pipe | Onset | Peak | Hit | Delay h | Pre-onset blocked | Credit max |
|------|-------|------|:---:|--------:|:-----------------:|-----------:|
| p653 | 2019-03-03 13:10:00 | 2019-04-21 19:00:00 | False | None | False | 1.1894481089849156 |
| p193 | 2019-05-19 10:40:00 | 2019-07-25 03:20:00 | False | None | False | 0.9443325081108277 |
| p277 | 2019-05-30 21:55:00 | 2019-08-11 15:05:00 | False | None | False | 0.9515895154712876 |
| p586 | 2019-07-26 14:40:00 | 2019-08-28 07:55:00 | False | None | False | 1.189631278994095 |
| p721 | 2019-08-02 03:00:00 | 2019-09-23 05:40:00 | False | None | False | 1.8498088188085515 |
| p800 | 2019-08-16 14:00:00 | 2019-09-07 21:05:00 | False | None | False | 1.091752365264904 |
| p123 | 2019-09-13 20:05:00 | 2019-11-29 22:10:00 | False | None | False | 1.4946472674432947 |
| p455 | 2019-10-03 14:00:00 | 2019-12-16 05:25:00 | False | None | False | 1.0308123845937502 |
| p762 | 2019-10-09 10:15:00 | 2019-12-03 01:15:00 | False | None | False | 1.2010957957021964 |
| p879 | 2019-11-20 11:55:00 | 2019-12-31 23:55:00 | False | None | False | 1.0317704856178709 |

## Burden

- Notifications (2019): **9**
- Unmatched/week: **0.115** (6 unmatched)
- Alarm occupancy (2019 hours): **0.0152**

## Carryover leaks (started before 2019-01-01)

| Pipe | Type | Start | End | n 2019 notifies while open |
|------|------|-------|-----|---------------------------:|
| p257 | incipient | 2018-01-08 13:30:00 | 2019-12-31 23:55:00 | 9 |
| p427 | incipient | 2018-02-13 08:25:00 | 2019-12-31 23:55:00 | 9 |
| p810 | incipient | 2018-07-28 03:05:00 | 2019-12-31 23:55:00 | 9 |
| p654 | incipient | 2018-07-05 03:40:00 | 2019-12-31 23:55:00 | 9 |

## Timing nulls (abrupt; identical matching rules)

- N replicates: **200**; |E|=**9**; onset draws=**1800**
- Fixed 2019 notifies used: **9**
- True recall: **0.3333333333333333**
- Null mean±std: **0.0083 ± 0.0293**
- Percentile (null≤true): **1.0** (200/200)
- Nulls with recall≥true: **0/200**
- Value counts: `{'0.0': 185, '0.111111': 15}`

For each of N replicates, sample |E| onsets from eligible eval hours matching each true event's hour-of-day; hit if any frozen notify lies in [onset, onset+6h]. Percentile = fraction of null recalls ≤ true recall.

## Stop

No parameter changes after results. No UI / Tiger / deployment / main merge. Artifacts preserved under `outputs/detection_2019_method_m/` for review.

