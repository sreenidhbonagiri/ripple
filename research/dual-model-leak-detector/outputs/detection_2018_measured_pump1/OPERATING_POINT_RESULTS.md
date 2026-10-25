# Measured-PUMP_1 operating-point evaluation (DEV selection)

Protocol: [`OPERATING_POINT_PROTOCOL.md`](OPERATING_POINT_PROTOCOL.md) (registered before run).  
Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Generated: `2026-10-25T05:03:14.362249+00:00`  

2018 events have already been examined; all measured findings are diagnostic.

**Any method passed DEV gates:** `True`

Gates: recall ≥ 2/3, unmatched/week ≤ 3, **occupancy ≤ 0.20** (rejects permanently active detectors).

## Score distributions (DEV, post-warmup)

| Method | n | mean | p50 | p90 | p99 | max |
|--------|--:|-----:|----:|----:|----:|----:|
| A | 4151 | -0.074 | 0.155 | 1.097 | 1.791 | 2.923 |
| B | 4151 | 6.670 | 5.587 | 10.999 | 19.747 | 30.925 |
| C | 4151 | 0.806 | 0.728 | 1.530 | 2.349 | 2.708 |

## DEV tradeoff (registered quantile grid)

### Method A (Σq_v change)

| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |
|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|
| 0.669 | 0.6666666666666666 | 18.265 | 0.420 | 2/3 | 456 | False |
| 1.097 | 0.6666666666666666 | 9.977 | 0.205 | 2/3 | 250 | False |
| 1.343 | 0.6666666666666666 | 5.673 | 0.112 | 2/3 | 143 | False |
| 1.791 | 0.6666666666666666 | 1.489 | 0.030 | 2/3 | 39 | True |

**Selection:** passed=`True` τ=`1.791` — largest_tau_passing_recall_burden_occupancy

Event-level (each τ):

- τ=0.669:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=2.0622887747774885
  - p538: hit=True delay=1.4166666666666667 pre_onset_blocked=True credit_max=1.7911248450692658
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=0.5310874592234005
- τ=1.097:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=2.0622887747774885
  - p538: hit=True delay=3.4166666666666665 pre_onset_blocked=False credit_max=1.7911248450692658
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=0.5310874592234005
- τ=1.343:
  - p673: hit=True delay=2.25 pre_onset_blocked=False credit_max=2.0622887747774885
  - p538: hit=True delay=3.4166666666666665 pre_onset_blocked=False credit_max=1.7911248450692658
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=0.5310874592234005
- τ=1.791:
  - p673: hit=True delay=3.25 pre_onset_blocked=False credit_max=2.0622887747774885
  - p538: hit=True delay=3.4166666666666665 pre_onset_blocked=False credit_max=1.7911248450692658
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=0.5310874592234005

### Method B (vector ‖Δq_v‖₂)

| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |
|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|
| 7.843 | 0.3333333333333333 | 9.535 | 0.662 | 1/3 | 238 | False |
| 10.999 | 0.6666666666666666 | 9.334 | 0.274 | 2/3 | 234 | False |
| 13.031 | 0.6666666666666666 | 5.954 | 0.150 | 2/3 | 150 | False |
| 19.747 | 0.0 | 1.690 | 0.028 | 0/3 | 42 | False |

**Selection:** passed=`False` τ=`None` — no_tau_passed_dev_gates

Event-level (each τ):

- τ=7.843:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=14.939733156137246
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=10.628247595449247
  - p866: hit=False delay=None pre_onset_blocked=True credit_max=16.08415622873911
- τ=10.999:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=14.939733156137246
  - p538: hit=False delay=None pre_onset_blocked=False credit_max=10.628247595449247
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=True credit_max=16.08415622873911
- τ=13.031:
  - p673: hit=True delay=0.25 pre_onset_blocked=False credit_max=14.939733156137246
  - p538: hit=False delay=None pre_onset_blocked=False credit_max=10.628247595449247
  - p866: hit=True delay=0.9166666666666666 pre_onset_blocked=True credit_max=16.08415622873911
- τ=19.747:
  - p673: hit=False delay=None pre_onset_blocked=False credit_max=14.939733156137246
  - p538: hit=False delay=None pre_onset_blocked=False credit_max=10.628247595449247
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=16.08415622873911

### Method C (inflow baseline |ΔQ_ext|)

| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |
|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|
| 1.103 | 0.3333333333333333 | 12.270 | 0.429 | 1/3 | 306 | False |
| 1.53 | 0.0 | 7.161 | 0.190 | 0/3 | 178 | False |
| 1.929 | 0.0 | 5.673 | 0.126 | 0/3 | 141 | False |
| 2.349 | 0.0 | 1.569 | 0.033 | 0/3 | 39 | False |

**Selection:** passed=`False` τ=`None` — no_tau_passed_dev_gates

Event-level (each τ):

- τ=1.103:
  - p673: hit=False delay=None pre_onset_blocked=True credit_max=1.3614120800651943
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=0.9208928969405438
  - p866: hit=True delay=3.9166666666666665 pre_onset_blocked=True credit_max=1.291425743503885
- τ=1.53:
  - p673: hit=False delay=None pre_onset_blocked=False credit_max=1.3614120800651943
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=0.9208928969405438
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=1.291425743503885
- τ=1.929:
  - p673: hit=False delay=None pre_onset_blocked=False credit_max=1.3614120800651943
  - p538: hit=False delay=None pre_onset_blocked=True credit_max=0.9208928969405438
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=1.291425743503885
- τ=2.349:
  - p673: hit=False delay=None pre_onset_blocked=False credit_max=1.3614120800651943
  - p538: hit=False delay=None pre_onset_blocked=False credit_max=0.9208928969405438
  - p866: hit=False delay=None pre_onset_blocked=False credit_max=1.291425743503885

## DIAG (frozen DEV settings only)

| Method | τ | recall | mean delay h | unmatched/wk | occupancy | trans.frac | null recall mean |
|--------|---:|-------:|-------------:|-------------:|----------:|----------:|-----------------:|
| A | 1.791 | 0.0 | None | 1.294 | 0.025 | 0.9117647058823529 | 0.0 |

### DIAG events — Method A

| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |
|------|:---:|--------:|:-----------------:|-----------:|
| p183 | False | None | False | 0.7679838769889281 |
| p158 | False | None | False | 1.1665834012526746 |
| p369 | False | None | False | 0.9131898663550483 |

## Notes

- Hourly dual limits notification timing to clock-hour granularity.
- Method C is the external-inflow baseline (p227+p235 only).
- No 2019 / new features / recalibration / recovery changes / UI / Tiger / main.

