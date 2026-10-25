# Method M operating-point results (measured-PUMP_1)

Protocol: [`METHOD_M_PROTOCOL.md`](METHOD_M_PROTOCOL.md) (registered before run).  
Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Generated: `2026-10-25T05:14:10.420992+00:00`  

2018 events have already been examined; measured findings are diagnostic.

## vs Method B

Method B is **not** equivalent: B uses L2(delta)/mean rolling ref sigma; M uses training-only per-sensor sigma and max |z_i| with SCALE median max-calibration. Not a rename of B.

**DEV selection passed:** `True`  
Selection: τ=`4.347` — largest_tau_passing_recall_burden_occupancy

SCALE: `2018-01-09 01:00:00` → `2018-01-21 23:00:00`; sensors kept 33/33; raw-max median=1.8440.

Registered τ grid (DEV p75/p90/p95/p99): `[1.174, 1.594, 2.153, 4.347]`

Gates: recall≥2/3, unmatched/wk≤3, occupancy≤0.20.

## DEV tradeoff

| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |
|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|
| 1.174 | 0.0 | 6.356 | 0.774 | 0/3 | 158 | False |
| 1.594 | 0.6666666666666666 | 7.081 | 0.307 | 2/3 | 178 | False |
| 2.153 | 1.0 | 3.178 | 0.113 | 3/3 | 82 | False |
| 4.347 | 1.0 | 0.201 | 0.028 | 3/3 | 8 | True |

### DEV events (each τ)

- τ=1.174:
  - p673: hit=False delay=None pre_onset_blocked=True credit_max=6.532246161855244
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=4.853290243682559
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=6.450353429206096
- τ=1.594:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.532246161855244
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=4.853290243682559
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=True credit_max=6.450353429206096
- τ=2.153:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.532246161855244
  - p538: hit=True delay=0.4166666666666667 pre_onset_blocked=False credit_max=4.853290243682559
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=True credit_max=6.450353429206096
- τ=4.347:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.532246161855244
  - p538: hit=True delay=3.4166666666666665 pre_onset_blocked=False credit_max=4.853290243682559
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=False credit_max=6.450353429206096

## DIAG (frozen τ)

| τ | recall | delay h | unmatched/wk | occupancy | null recall mean | true pct vs null |
|--:|-------:|--------:|-------------:|----------:|-----------------:|-----------------:|
| 4.347 | 0.3333333333333333 | 0.4166666666666667 | 0.038 | 0.008 | 0.006666666666666666 | 1.0 |

| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |
|------|:---:|--------:|:-----------------:|-----------:|
| p183 | False | None | False | 2.496372231772623 |
| p158 | True | 0.4166666666666667 | False | 5.843872651815834 |
| p369 | False | None | False | 2.359763820269915 |

## Notes

- Standardized scores are not probabilities; hours and sensors are dependent.
- No 2019 / production / UI / Tiger / deploy / recalibration.

