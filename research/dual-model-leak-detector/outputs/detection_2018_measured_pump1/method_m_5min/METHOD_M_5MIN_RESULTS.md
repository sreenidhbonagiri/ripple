# Method M five-minute DEV results (measured-PUMP_1)

Protocol: [`METHOD_M_5MIN_PROTOCOL.md`](METHOD_M_5MIN_PROTOCOL.md)  
Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Generated: `2026-10-25T06:34:30.590334+00:00`  

2018 events have already been examined; measured findings are diagnostic. Higher resolution is not assumed to improve sensitivity.

## Settings

- timestep_sec=`300`  
- REF_MIN_SAMPLES=`144`, MIN_SCALE_SAMPLES=`288`, RECOVER_STEPS=`12` (1 h)  
- causal_fill_max_age_steps=`2`  
- dual DEV runtime_s=`39.152007333002985`, score runtime_s=`90.06097425008193`, total_s=`286.15038333297707`  

### Measurement / fill / solver

```json
{
  "n_timestamps": 50112,
  "n_solver_failures": 0,
  "n_chunks": 58,
  "n_qv_cleared_stale_total": 0,
  "frac_qv_cleared_stale": 0.0,
  "median_index_step": "0 days 00:05:00",
  "pressure": {
    "n_cells": 1653696,
    "n_observed": 1653696,
    "n_filled": 0,
    "n_unavailable": 0,
    "frac_observed": 1.0,
    "frac_filled": 0.0,
    "frac_unavailable": 0.0
  },
  "pump": {
    "n_cells": 50112,
    "n_observed": 50112,
    "n_filled": 0,
    "n_unavailable": 0,
    "frac_observed": 1.0,
    "frac_filled": 0.0,
    "frac_unavailable": 0.0
  }
}
```

## Hourly baseline (reproduced from frozen score_M; hydraulics not re-run)

τ=`4.347`: recall=`1.0` unm/wk=`0.201` occ=`0.028` mean_delay_h=`1.5277777777777777`  

## Five-minute DEV

**DEV selection passed:** `True`  
Selection: τ=`4.517` — largest_tau_passing_recall_burden_occupancy

Registered τ grid (DEV p75/p90/p95/p99): `[1.175, 1.565, 2.117, 4.517]`

Gates: recall≥2/3, unmatched/wk≤3, occupancy≤0.20.

| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |
|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|
| 1.175 | 0.0 | 0.040 | 0.997 | 0/3 | 1 | False |
| 1.565 | 0.0 | 1.971 | 0.930 | 0/3 | 49 | False |
| 2.117 | 0.3333333333333333 | 4.747 | 0.324 | 1/3 | 119 | False |
| 4.517 | 1.0 | 0.201 | 0.031 | 3/3 | 8 | True |

### DEV events (each τ)

- τ=1.175:
  - p673: hit=False delay=None pre_onset_blocked=True credit_max=7.6215343566625515
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=5.006165215118364
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=6.913131113133562
- τ=1.565:
  - p673: hit=False delay=None pre_onset_blocked=True credit_max=7.6215343566625515
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=5.006165215118364
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=6.913131113133562
- τ=2.117:
  - p673: hit=True delay=0.0 pre_onset_blocked=False credit_max=7.6215343566625515
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=5.006165215118364
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=6.913131113133562
- τ=4.517:
  - p673: hit=True delay=0.0 pre_onset_blocked=False credit_max=7.6215343566625515
  - p538: hit=True delay=0.8333333333333334 pre_onset_blocked=False credit_max=5.006165215118364
  - p866: hit=True delay=0.0 pre_onset_blocked=False credit_max=6.913131113133562

## Paired hourly vs five-minute

Five-minute τ reported: `4.517` (selection_passed=`True`)

| Metric | Hourly | Five-minute |
|--------|-------:|------------:|
| Recall | 1.0 | 1.0 |
| Mean delay h | 1.5277777777777777 | 0.2777777777777778 |
| Unmatched/wk | 0.201 | 0.201 |
| Occupancy | 0.028 | 0.031 |

| Pipe | Hourly hit/delay | 5-min hit/delay | Gain | Regression | Delay Δh |
|------|-----------------:|----------------:|:----:|:----------:|---------:|
| p673 | True/0.25 | True/0.0 | False | False | -0.25 |
| p538 | True/3.4166666666666665 | True/0.8333333333333334 | False | False | -2.583333333333333 |
| p866 | True/0.9166666666666666 | True/0.0 | False | False | -0.9166666666666666 |

## DIAG (frozen τ)

| τ | recall | delay h | unmatched/wk | occupancy | null recall mean | true pct vs null |
|--:|-------:|--------:|-------------:|----------:|-----------------:|-----------------:|
| 4.517 | 0.3333333333333333 | 0.0 | 0.038 | 0.008 | 0.005 | 1.0 |

| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |
|------|:---:|--------:|:-----------------:|-----------:|
| p183 | False | None | False | 2.999284342707537 |
| p158 | True | 0.0 | False | 5.8830022139691325 |
| p369 | False | None | False | 2.6970451467669916 |

## Notes

- Hourly baseline is score-only reproduction, not a hydraulic re-solve.
- No 2019 / production / UI / Tiger / deploy / recalibration.

