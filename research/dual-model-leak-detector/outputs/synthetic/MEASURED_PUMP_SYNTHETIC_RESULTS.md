# Measured PUMP_1 synthetic verification

Generated: `2026-10-25T04:58:14.176709+00:00`  
Formulation: `PUMP1_MEASURED_BOUNDARY.md`

**All passed:** `True`

| Scenario | Pass | Key metric |
|----------|------|------------|
| `measured_pump_matched_transition` | True | max|Σ|=0.0007 |

### `measured_pump_matched_transition`

With measured internal transfer matching the primal pump, Σq_v stays near zero across the pump-off transition.

Pass criterion: max_abs_sum_m3h < 0.5

| `measured_pump_leak_stable` | True | mean Σ=5.0015 |

### `measured_pump_leak_stable`

Virtual-flow sum should reflect the omitted leak under a matched pump BC.

Pass criterion: mean_sum_m3h within [2, 8] (tracks ~5 m³/h leak)

| `measured_pump_leak_coincident_transition` | True | before/after / switch Δ=5.002/5.002/Δ0.000 |

### `measured_pump_leak_coincident_transition`

Leak imprint in Σq_v should persist across the switch; measured Qp should prevent a large transition-only residual jump.

Pass criterion: before/after means in [2, 8] and |switch ΔΣ| < 3 (transition not a large artifact)

| `measured_pump_noisy_missing` | True | max|Σ| / converged=conv=True max|Σ|=1.9538315263162076 |

### `measured_pump_noisy_missing`

Causal fill must not look ahead; solver should still converge; Σq_v artifacts stay bounded versus a matched zero-leak case.

Pass criterion: converged and max_abs_sum_m3h < 5 (bounded artifact under noise/ffill)

## Notes

- Does not modify frozen calibration or baseline detection outputs.
- Stop: no 2019 / UI / Tiger / production / main.

