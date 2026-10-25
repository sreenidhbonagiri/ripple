# Signal-preservation audit (diagnostic)

Protocol: [`SIGNAL_PRESERVATION_PROTOCOL.md`](../SIGNAL_PRESERVATION_PROTOCOL.md)  
Generated: `2026-10-25T05:09:30.262252+00:00`  
Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  

2018 events have already been examined; all contrasts are diagnostic.

Windows: PRE=[6h before onset), POST=[onset, +6h]. Controls: hour-of-day + PRE Q_ext / PUMP_1 matched (n≤25).

Miss flag (diagnostic only): Method A credit max < τ=1.791.

## Network-level contrasts vs ordinary controls (SNR)

| Pipe | Period | Miss? | Loss stage | SNR ΔP L2 | SNR ΔQext | SNR Δerr_cal L2 | SNR Δerr_nom L2 | SNR ΔΣq_v | SNR Δs_A | SNR credit max | credit max |
|------|--------|:-----:|------------|----------:|----------:|----------------:|----------------:|----------:|---------:|---------------:|-----------:|
| p673 | DEV | False | `not_missed_credit_max_ge_tau` | 2.35 | 1.17 | 1.76 | 2.06 | 2.70 | 1.63 | 1.35 | 2.062 |
| p538 | DEV | False | `not_missed_credit_max_ge_tau` | 0.55 | 0.65 | 0.54 | 0.14 | 1.48 | 0.83 | 1.98 | 1.791 |
| p866 | DEV | True | `canceled_by_signed_sum` | 1.12 | 1.49 | 0.45 | 0.78 | 0.54 | 0.34 | -0.40 | 0.531 |
| p183 | DIAG | True | `survives_to_score_below_tau` | -11.02 | 9.68 | -0.76 | -1.31 | 2.03 | 2.19 | 0.57 | 0.768 |
| p158 | DIAG | True | `survives_to_score_below_tau` | -0.77 | 1.42 | -1.33 | 0.25 | 2.57 | 2.00 | 1.75 | 1.167 |
| p369 | DIAG | True | `unclear` | -2.71 | 2.42 | -1.48 | 0.49 | 1.41 | 1.08 | 1.11 | 0.913 |

### Raw event Δ (not SNR)

| Pipe | ΔP L2 (m) | ΔQext (m³/h) | Δerr_cal L2 (m) | ΔΣq_v (m³/h) | Δs_A |
|------|----------:|-------------:|----------------:|-------------:|-----:|
| p673 | 2.535 | 26.77 | 2.560 | 54.76 | 1.392 |
| p538 | 5.303 | 116.27 | 2.673 | 55.41 | 1.573 |
| p866 | 5.760 | 120.97 | 3.075 | 38.08 | 1.465 |
| p183 | 0.687 | -15.89 | 1.334 | -4.32 | 0.093 |
| p158 | 3.451 | -70.09 | 0.922 | -5.72 | -0.448 |
| p369 | 3.380 | -76.99 | 1.129 | -19.23 | -0.811 |

## Per-event loss notes

### p673 (DEV)

- **Stage:** `not_missed_credit_max_ge_tau` (miss=False, n_ctrl=25)
- Top |SNR ΔP| sensors: n215=-36.7, n229=-5.5, n31=2.6, n1=2.1, n644=-2.0
- Top |SNR Δq_v| sensors: n229=28.7, n215=14.3, n740=-1.8, n726=1.7, n4=-1.3
- Measurement: SNR ΔP_L2=2.35, ΔQext=1.17; calibrated error SNR=1.76; Σq_v SNR=2.70; s_A SNR=1.63.

### p538 (DEV)

- **Stage:** `not_missed_credit_max_ge_tau` (miss=False, n_ctrl=25)
- Top |SNR ΔP| sensors: n506=-2.2, n332=-1.8, n105=-1.8, n516=-1.8, n469=-1.8
- Top |SNR Δq_v| sensors: n506=14.6, n332=12.5, n516=3.7, n105=3.4, n549=3.2
- Measurement: SNR ΔP_L2=0.55, ΔQext=0.65; calibrated error SNR=0.54; Σq_v SNR=1.48; s_A SNR=0.83.

### p866 (DEV)

- **Stage:** `canceled_by_signed_sum` (miss=True, n_ctrl=25)
- Top |SNR ΔP| sensors: n296=-7.0, n740=-4.1, n722=-4.0, n726=-2.1, n769=-2.1
- Top |SNR Δq_v| sensors: n296=32.3, n722=11.8, n549=-4.6, n613=-4.2, n740=3.8
- Measurement: SNR ΔP_L2=1.12, ΔQext=1.49; calibrated error SNR=0.45; Σq_v SNR=0.54; s_A SNR=0.34.

### p183 (DIAG)

- **Stage:** `survives_to_score_below_tau` (miss=True, n_ctrl=25)
- Top |SNR ΔP| sensors: n752=-13.5, n726=-12.4, n769=-12.2, n288=-11.9, n722=-11.8
- Top |SNR Δq_v| sensors: n752=13.6, n726=6.4, n288=4.6, n54=3.4, n495=3.1
- Measurement: SNR ΔP_L2=-11.02, ΔQext=9.68; calibrated error SNR=-0.76; Σq_v SNR=2.03; s_A SNR=2.19.

### p158 (DIAG)

- **Stage:** `survives_to_score_below_tau` (miss=True, n_ctrl=25)
- Top |SNR ΔP| sensors: n644=-3.7, n288=-2.1, n679=-2.0, n726=-2.0, n752=-1.9
- Top |SNR Δq_v| sensors: n644=27.0, n679=3.5, n288=3.2, n342=2.8, n726=2.5
- Measurement: SNR ΔP_L2=-0.77, ΔQext=1.42; calibrated error SNR=-1.33; Σq_v SNR=2.57; s_A SNR=2.00.

### p369 (DIAG)

- **Stage:** `unclear` (miss=True, n_ctrl=25)
- Top |SNR ΔP| sensors: n410=-4.3, n429=-3.2, n415=-2.9, n519=-2.7, n458=-2.6
- Top |SNR Δq_v| sensors: n410=12.4, n429=7.2, n54=2.4, n215=-1.5, n740=-1.0
- Measurement: SNR ΔP_L2=-2.71, ΔQext=2.42; calibrated error SNR=-1.48; Σq_v SNR=1.41; s_A SNR=1.08.

## Miss-stage counts

```
{
  "canceled_by_signed_sum": 1,
  "survives_to_score_below_tau": 2,
  "unclear": 1
}
```

## Recommendation

**No supported correction emerged.** Score contrasts exceed ordinary variability but remain below the frozen τ; that is a threshold/separability limit, and this audit does not change thresholds.

## Notes

- Sensors are the full pressure set; none chosen by leak pipe.
- `err_cal` = meas − frozen-calibrated primal; `err_nom` = meas − INP-nominal primal.
- No threshold changes, 2019, UI, Tiger, or deploy.

