# Frozen five-minute Method M on 2019 — diagnostic evaluation

**Not a blind holdout.** 2019 has already been examined during previous research; this is a frozen diagnostic evaluation of five-minute Method M, not a blind holdout.

Generated: `2026-10-25T06:49:13.907499+00:00`  
τ=`4.517` (frozen 5-min). Calibration `5fab3acbf13f018d…`.  
Pre-label score hash `569dc80acc4bad30…`; notify hash `7283a0963f8af2d5…`.

See `PRE_INFERENCE_FROZEN_BUNDLE.md`, `pre_inference_hashes.json`, `pre_label_hashes.json`, `REPRODUCIBILITY_MANIFEST.json`.

## Dual / freshness / availability

- Solver failures: **0** / 122 chunks
- 2019 score stamps: 105120 (finite 105120, NaN 0)
- First finite score in 2019: `2019-01-01 00:00:00`
- Notifier: continuous 2018→2019; recover_steps=`12`; **no** reset at onsets/months

```json
{
  "n_timestamps": 105120,
  "n_solver_failures": 0,
  "n_chunks": 122,
  "n_qv_cleared_stale_total": 0,
  "frac_qv_cleared_stale": 0.0,
  "median_index_step": "0 days 00:05:00",
  "pressure": {
    "n_cells": 3468960,
    "n_observed": 3468960,
    "n_filled": 0,
    "n_unavailable": 0,
    "frac_observed": 1.0,
    "frac_filled": 0.0,
    "frac_unavailable": 0.0
  },
  "pump": {
    "n_cells": 105120,
    "n_observed": 105120,
    "n_filled": 0,
    "n_unavailable": 0,
    "frac_observed": 1.0,
    "frac_filled": 0.0,
    "frac_unavailable": 0.0
  }
}
```

## Abrupt six-hour recall — **primary** (excl. p523)

| n eligible | recall | mean delay h | pre-onset blocked | multi-credit notifies |
|----------:|-------:|-------------:|------------------:|----------------------:|
| 8 | 0.25 | 0.041666666666666664 | 0 | 0 |

## Abrupt six-hour recall — **inclusive** (includes p523)

| n eligible | recall | mean delay h | pre-onset blocked |
|----------:|-------:|-------------:|------------------:|
| 9 | 0.3333333333333333 | 0.027777777777777776 | 0 |

| Pipe | Onset | Hit | Delay h | Pre-onset blocked | Credit max | Dev-ex |
|------|-------|:---:|--------:|:-----------------:|-----------:|:------:|
| p523 | 2019-01-15 23:00:00 | True | 0.0 | False | 9.861590406632889 | True |
| p827 | 2019-01-24 18:30:00 | True | 0.0 | False | 7.712434266807943 | False |
| p280 | 2019-02-10 13:05:00 | False | None | False | 2.207656408962638 | False |
| p710 | 2019-03-24 14:15:00 | False | None | False | 2.0846834182737695 | False |
| p514 | 2019-04-02 20:40:00 | True | 0.08333333333333333 | False | 4.8642126165187305 | False |
| p331 | 2019-04-20 10:10:00 | False | None | False | 3.5449650412173623 | False |
| p142 | 2019-06-12 19:55:00 | False | None | False | 4.315813239617662 | False |
| p680 | 2019-07-10 08:45:00 | False | None | False | 1.5072900194683942 | False |
| p426 | 2019-10-25 13:25:00 | False | None | False | 1.6789239730111596 | False |

## Incipient (separate; 6 h from catalog startTime)

Eligible recall: **0.0** (0/10); warmup excluded 0.

| Pipe | Onset | Peak | Hit | Delay h | Pre-onset blocked | Credit max |
|------|-------|------|:---:|--------:|:-----------------:|-----------:|
| p653 | 2019-03-03 13:10:00 | 2019-04-21 19:00:00 | False | None | False | 1.198849357259576 |
| p193 | 2019-05-19 10:40:00 | 2019-07-25 03:20:00 | False | None | False | 1.3013038470320153 |
| p277 | 2019-05-30 21:55:00 | 2019-08-11 15:05:00 | False | None | False | 1.178215672967439 |
| p586 | 2019-07-26 14:40:00 | 2019-08-28 07:55:00 | False | None | False | 1.3107206752551765 |
| p721 | 2019-08-02 03:00:00 | 2019-09-23 05:40:00 | False | None | False | 2.0604880176566027 |
| p800 | 2019-08-16 14:00:00 | 2019-09-07 21:05:00 | False | None | False | 1.3167615754291562 |
| p123 | 2019-09-13 20:05:00 | 2019-11-29 22:10:00 | False | None | False | 1.8341462508220077 |
| p455 | 2019-10-03 14:00:00 | 2019-12-16 05:25:00 | False | None | False | 1.2417174654139926 |
| p762 | 2019-10-09 10:15:00 | 2019-12-03 01:15:00 | False | None | False | 1.5027568258738044 |
| p879 | 2019-11-20 11:55:00 | 2019-12-31 23:55:00 | False | None | False | 1.2450624466994595 |

## Burden

- Notifications (2019): **9**
- Duplicate notify timestamps: **0**
- Events with >1 credit-window notify: **0**
- Unmatched/week: **0.115** (6 unmatched)
- Alarm occupancy (2019 stamps): **0.0188**

## vs frozen hourly Method M (τ=4.347)

| Metric | Hourly | Five-minute |
|--------|-------:|------------:|
| Abrupt recall (inclusive) | 0.3333333333333333 | 0.3333333333333333 |
| Abrupt recall (excl. p523) | 0.25 | 0.25 |
| Incipient recall | 0.0 | 0.0 |
| Unmatched/week | 0.115 | 0.115 |
| Occupancy | 0.0152 | 0.0188 |
| n notifications | 9 | 9 |

### Abrupt event gains / regressions

| Pipe | Hourly hit/delay | 5-min hit/delay | Gain | Regression | Delay Δh |
|------|-----------------:|----------------:|:----:|:----------:|---------:|
| p523* | True/0.0 | True/0.0 | False | False | 0.0 |
| p827 | True/0.5 | True/0.0 | False | False | -0.5 |
| p280 | False/None | False/None | False | False | None |
| p710 | False/None | False/None | False | False | None |
| p514 | True/0.3333333333333333 | True/0.08333333333333333 | False | False | -0.25 |
| p331 | False/None | False/None | False | False | None |
| p142 | False/None | False/None | False | False | None |
| p680 | False/None | False/None | False | False | None |
| p426 | False/None | False/None | False | False | None |

\* `p523` = development example (excluded from primary).

### Delays on events detected by both

n both-hit: **3**; mean (5-min − hourly) delay h: **-0.25**

## Timing nulls (identical matching rules)

### Primary (excl. p523)

- N=**200**; |E|=**8**; true recall=**0.25**
- Exceedances (null recall ≥ true): **1/200**
- Percentile (null≤true): **1.0**
- Null mean±std: **0.0056 ± 0.0288**

### Inclusive

- N=**200**; |E|=**9**; true recall=**0.3333333333333333**
- Exceedances (null recall ≥ true): **0/200**
- Percentile (null≤true): **1.0**
- Hourly exceedances (null≥true): **0/200**

For each of N replicates, sample |E| onsets from eligible eval stamps matching each true event's hour-of-day; hit if any frozen notify lies in [onset, onset+6h]. Percentile = fraction of null recalls ≤ true recall. Exceedance count = nulls with recall ≥ true.

## Carryover leaks (started before 2019-01-01)

| Pipe | Type | Start | End | n 2019 notifies while open |
|------|------|-------|-----|---------------------------:|
| p257 | incipient | 2018-01-08 13:30:00 | 2019-12-31 23:55:00 | 9 |
| p427 | incipient | 2018-02-13 08:25:00 | 2019-12-31 23:55:00 | 9 |
| p810 | incipient | 2018-07-28 03:05:00 | 2019-12-31 23:55:00 | 9 |
| p654 | incipient | 2018-07-05 03:40:00 | 2019-12-31 23:55:00 | 9 |

## Stop

No parameter changes after results. No UI / Tiger / deployment / main merge. Artifacts under `outputs/detection_2019_method_m_5min/`.

