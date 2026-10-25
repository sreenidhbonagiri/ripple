# Multiscale Method M — DEV results

Protocol: [`METHOD_M_MULTISCALE_PROTOCOL.md`](METHOD_M_MULTISCALE_PROTOCOL.md)  
Generated: `2026-10-25T05:56:16.144351+00:00`  
Calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  

2018 events have already been examined; measured findings are diagnostic. No 2019 evaluation or tuning.

## Baseline reproduction (frozen Method M)

- Timescale **medium** REF=24 h (existing Method M definition)  
- Repro vs archived `score_M.csv`: max\|Δ\|=`0.000e+00`  
- Frozen τ=`4.347` DEV abrupt recall=`1.0` unm/wk=`0.201` occ=`0.028`  

## Registered timescales

| ID | Ref h | Role |
|----|------:|------|
| short | 12 | half-day (shortest with ≥12 hourly ref samples) |
| medium | 24 | **baseline Method M** |
| long | 72 | multi-day |

Combined score = max\|δ/σ\| over sensors **and** timescales, then SCALE median calibration. **One** notifier (not independent per-scale union).

Combined SCALE raw-max median=`1.9763`  
SCALE winner counts: `{'short': 115, 'medium': 86, 'long': 110}`  

Registered τ grid: `[1.276, 2.15, 3.155, 5.284]`

**DEV selection passed:** `True` — largest_tau_passing_recall_burden_occupancy (τ=`5.284`)

## DEV tradeoff (combined stream)

| τ | abrupt recall | unm/wk | occ | incip recall | n_notif | gate |
|--:|-------------:|-------:|----:|-------------:|--------:|:----:|
| 1.276 | 0.0 | 5.270 | 0.768 | 0.2 | 131 | False |
| 2.15 | 1.0 | 2.816 | 0.174 | 0.0 | 73 | True |
| 3.155 | 1.0 | 0.282 | 0.090 | 0.0 | 10 | True |
| 5.284 | 0.6666666666666666 | 0.121 | 0.043 | 0.0 | 5 | True |

### DEV abrupt events (selected / each τ)

- τ=1.276:
  - p673: hit=False delay=None pre_onset_blocked=True credit_max=6.105674100459567
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=4.868353700208772
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=6.1995686576056785
- τ=2.15:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.105674100459567
  - p538: hit=True delay=0.4166666666666667 pre_onset_blocked=False credit_max=4.868353700208772
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=True credit_max=6.1995686576056785
- τ=3.155:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.105674100459567
  - p538: hit=True delay=0.4166666666666667 pre_onset_blocked=False credit_max=4.868353700208772
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=False credit_max=6.1995686576056785
- τ=5.284:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=6.105674100459567
  - p538: hit=False delay=None pre_onset_blocked=False credit_max=4.868353700208772
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=False credit_max=6.1995686576056785

### DEV incipient (report only)

- τ=1.276: recall=0.2 (1/5)
  - p461: hit=False delay=None credit_max=1.3661365354274524
  - p232: hit=True delay=1.4166666666666667 credit_max=1.5536872765809164
  - p427: hit=False delay=None credit_max=1.074038973808832
  - p628: hit=False delay=None credit_max=0.995657621082715
  - p31: hit=False delay=None credit_max=1.1733937973099346
- τ=2.15: recall=0.0 (0/5)
  - p461: hit=False delay=None credit_max=1.3661365354274524
  - p232: hit=False delay=None credit_max=1.5536872765809164
  - p427: hit=False delay=None credit_max=1.074038973808832
  - p628: hit=False delay=None credit_max=0.995657621082715
  - p31: hit=False delay=None credit_max=1.1733937973099346
- τ=3.155: recall=0.0 (0/5)
  - p461: hit=False delay=None credit_max=1.3661365354274524
  - p232: hit=False delay=None credit_max=1.5536872765809164
  - p427: hit=False delay=None credit_max=1.074038973808832
  - p628: hit=False delay=None credit_max=0.995657621082715
  - p31: hit=False delay=None credit_max=1.1733937973099346
- τ=5.284: recall=0.0 (0/5)
  - p461: hit=False delay=None credit_max=1.3661365354274524
  - p232: hit=False delay=None credit_max=1.5536872765809164
  - p427: hit=False delay=None credit_max=1.074038973808832
  - p628: hit=False delay=None credit_max=0.995657621082715
  - p31: hit=False delay=None credit_max=1.1733937973099346

## vs baseline Method M (DEV, frozen τ vs selected τ)

- Burden: baseline unm/wk=`0.201` occ=`0.028` delay=`1.5277777777777777` → multiscale unm/wk=`0.121` occ=`0.043` delay=`0.5833333333333333`
- **Gains (miss→hit):** 0
- **Regressions (hit→miss):** 1
  - p538: base_delay=3.4166666666666665 ms_delay=None
- **Both hit:** 2
  - p673: base_delay=0.25 ms_delay=0.25
  - p866: base_delay=0.9166666666666666 ms_delay=0.9166666666666666
- **Both miss:** 0

## DIAG (frozen after DEV)

| | τ | abrupt recall | delay h | unm/wk | occ | null mean | pct |
|--|--:|-------------:|--------:|-------:|----:|----------:|----:|
| Multiscale | 5.284 | 0.3333333333333333 | 0.4166666666666667 | 0.000 | 0.010 | 0.006666666666666666 | 1.0 |
| Baseline M | 4.347 | 0.3333333333333333 | 0.4166666666666667 | 0.038 | 0.008 | 0.006666666666666666 | 1.0 |

### DIAG abrupt event compare

- Gains: []
- Regressions: []

DIAG incipient multiscale recall=`0.0` baseline=`0.0`


## Stop / isolation

- No 2019 / production / Tiger / main merge / deploy / recalibration.
- Deployed Method M and frozen calibration preserved.

