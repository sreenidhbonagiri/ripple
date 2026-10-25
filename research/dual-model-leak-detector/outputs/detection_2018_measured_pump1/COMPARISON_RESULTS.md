# 2018 measured-PUMP_1 dual vs baseline (diagnostic)

Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Generated: `2026-10-25T04:59:25.811914+00:00`  
Formulation: `PUMP1_MEASURED_BOUNDARY.md`

**Diagnostic comparison only.** Same frozen calibration and baseline fallback τ (A=1.5, B=1.0, C=1.0). **No** threshold re-selection, **no** recalibration. Score distributions may shift under the new boundary.

Solver failures: **0** / 52 chunks.

## Headline vs baseline (same τ)

Baseline numbers from `outputs/detection_2018/DETECTION_RESULTS.md` (inp_controls).

| Method | Period | recall base→meas | unmatched/wk base→meas | occupancy base→meas |
|--------|--------|-----------------:|-----------------------:|--------------------:|
| A | DEV | 0.667→0.667 | 4.345→4.063 | 0.085→0.083 |
| A | DIAG | 0.0→0.0 | 3.728→3.652 | 0.064→0.064 |
| B | DEV | 0.0→0.0 | 0.040→0.040 | ~1→0.997 |
| B | DIAG | 0.0→0.0 | 0.038→0.038 | 1.0→1.0 |
| C | DEV | 0.333→0.333 | 14.161→14.161 | 0.540→0.540 |
| C | DIAG | 0.667→0.667 | 14.152→14.152 | 0.545→0.545 |

n54 switch mean \|Δq_v\|: **16.4 → 7.6** m³/h; frac switches where n54 dominates: **0.65 → 0.41**.
Method B remains saturated (chronically elevated vector score). Abrupt DIAG A credit maxima stay below τ=1.5.

## Virtual-flow excursions at pump switches

| Variant | n switches | mean\|Δn54\| switch | mean\|Δn54\| ordinary | mean\|ΔΣ\| switch | mean\|ΔΣ\| ordinary | frac n54 dominates |
|---------|----------:|---------------------:|-----------------------:|------------------:|--------------------:|-------------------:|
| baseline_inp_controls | 671 | 16.389653934204006 | 3.2219496252032926 | 28.278631904694283 | 22.122582701546477 | 0.6482861400894188 |
| measured_pump1 | 671 | 7.570627687997552 | 2.5019052933062498 | 23.494353740698585 | 21.882442902403973 | 0.4113263785394933 |

## DEV / DIAG at baseline τ (diagnostic)

### DEV

| Method | τ | recall | unmatched/wk | occupancy | gate_pass (info only) |
|--------|---:|-------:|-------------:|----------:|:---------------------:|
| A | 1.5 | 0.6666666666666666 | 4.063 | 0.083 | False |
| B | 1.0 | 0.0 | 0.040 | 0.997 | False |
| C | 1.0 | 0.3333333333333333 | 14.161 | 0.540 | False |

### DIAG

| Method | τ | recall | delay h | unmatched/wk | occupancy | trans.frac (corrected helper) |
|--------|---:|-------:|--------:|-------------:|----------:|------------------------------:|
| A | 1.5 | 0.0 | None | 3.652 | 0.064 | 0.8333333333333334 |
| B | 1.0 | 0.0 | None | 0.038 | 1.000 | 0.0 |
| C | 1.0 | 0.6666666666666666 | 2.1666666666666665 | 14.152 | 0.545 | 0.8440860215053764 |

## Per-event credit-window scores

| Pipe | Period | A max (base→meas) | B max (base→meas) | C max (base→meas) | A hit | B hit | C hit |
|------|--------|------------------:|------------------:|------------------:|:-----:|:-----:|:-----:|
| p673 | DEV | 1.959→2.062 | 13.583→14.940 | 1.361→1.361 | True | False | False |
| p538 | DEV | 1.787→1.791 | 10.884→10.628 | 0.921→0.921 | True | False | False |
| p866 | DEV | 0.534→0.531 | 15.237→16.084 | 1.291→1.291 | False | False | True |
| p183 | DIAG | 0.768→0.768 | 22.843→22.841 | 1.630→1.630 | False | False | False |
| p158 | DIAG | 0.962→1.167 | 15.317→14.928 | 2.006→2.006 | False | False | True |
| p369 | DIAG | 0.883→0.913 | 11.151→10.968 | 1.800→1.800 | False | False | True |

## Corrected transition statistics (actual hourly intervals)

Storage rate uses `A·Δh/Δt` with Δt from the index (no spurious ×12).

### Method A

| Period | n unmatched | frac pump\|Δ\|>10 | frac storage\|dV\|>15 | frac either | helper |
|--------|------------:|------------------:|----------------------:|------------:|-------:|
| DEV | 101 | 0.06930693069306931 | 0.9504950495049505 | 0.9900990099009901 | 0.9900990099009901 |
| DIAG | 96 | 0.052083333333333336 | 0.8020833333333334 | 0.8333333333333334 | 0.8333333333333334 |

### Method B

| Period | n unmatched | frac pump\|Δ\|>10 | frac storage\|dV\|>15 | frac either | helper |
|--------|------------:|------------------:|----------------------:|------------:|-------:|
| DEV | 1 | 0.0 | 1.0 | 1.0 | 1.0 |
| DIAG | 1 | 0.0 | 1.0 | 1.0 | 0.0 |

### Method C

| Period | n unmatched | frac pump\|Δ\|>10 | frac storage\|dV\|>15 | frac either | helper |
|--------|------------:|------------------:|----------------------:|------------:|-------:|
| DEV | 352 | 0.26988636363636365 | 0.7840909090909091 | 0.9460227272727273 | 0.9460227272727273 |
| DIAG | 372 | 0.24731182795698925 | 0.7204301075268817 | 0.8440860215053764 | 0.8440860215053764 |

## Notes

- Baseline artifacts under `outputs/detection_2018/` are preserved.
- PUMP_1 is an internal transfer only; Method C still uses p227+p235.
- Stop: no 2019 / UI / Tiger / production / main.

