# Synthetic dual-model verification results

Generated: `2026-10-25T04:23:09.136538+00:00`

Passed **7/7** scenario checks.

| ID | Passed | Actual leak (m³/h) | sum q_v (m³/h) | Distinguishes? |
|----|--------|--------------------:|---------------:|----------------|
| `no_leak_correct` | PASS | 0.00 | -0.0003 | n/a |
| `known_injected_leak` | PASS | 5.00 | 4.9997 | yes |
| `demand_change_matched` | PASS | 0.00 | 0.0000 | yes |
| `demand_mismatch_no_leak` | PASS | 0.00 | 4.9996 | no (confounder) |
| `roughness_mismatch_no_leak` | PASS | 0.00 | -2.5004 | no (confounder) |
| `sensor_datum_mismatch` | PASS | 0.00 | -0.0049 | no (confounder) |
| `pump_tank_transition` | PASS | 0.00 | max|Σ|=0.0011 | yes |

## Per-scenario interpretation

### `no_leak_correct`

No-leak, correctly specified dual model

sum(q_v) ≈ 0 when the hydraulic model matches the measured heads; residual is numerical (nonzero TCV loss), not a physical leak.

- Pass criterion: abs(sum_m3h) < 0.05
- Passed: **True**

### `known_injected_leak`

Known demand-driven leak of 5.0 m³/h at J3

With a correct demand/roughness model, sum(q_v) approximates the injected leak discharge and the largest |q_v| localizes near the leak. q_v is still a model imbalance, not a physical orifice flow.

- Pass criterion: abs(sum_m3h - leak_m3h) < 0.1 and dominant_sensor == leak_node
- Passed: **True**

### `demand_change_matched`

Uniform +50% demand in truth and in dual model; no leak

Ordinary demand operations that are represented in the dual model do not produce a virtual-leak signature (sum q_v ≈ 0).

- Pass criterion: abs(sum_m3h) < 0.05
- Passed: **True**

### `demand_mismatch_no_leak`

Truth demand +5 m³/h at J1; model unaware; no physical leak

Unmodeled demand produces sum(q_v) ≈ the demand error. Virtual flow cannot distinguish this from a real leak of the same magnitude. This is why demand calibration is required before measured-data use.

- Pass criterion: abs(sum_m3h - 5.0) < 0.2 (documents confounding, not a leak TP)
- Passed: **True**

### `roughness_mismatch_no_leak`

No leak; dual model roughness scaled by 0.9

Roughness error induces nonzero q_v even without leaks (Campbell et al. 2024). Magnitude depends on operating point; not automatically a leak.

- Pass criterion: abs(sum_m3h) > 0.05 (nonzero confounder documented)
- Passed: **True**

### `sensor_datum_mismatch`

No leak; +0.5 m datum bias on J2 head

A sensor elevation/datum error drives local q_v and can look like a nearby leak. Sensor-specific elevation calibration (Campbell et al. 2024) is needed before detection claims.

- Pass criterion: abs(sum_m3h) > 0.05 or abs(q_v[J2]) dominant
- Passed: **True**

### `pump_tank_transition`

Pump off at 6 h; tank level evolves; model matches truth; no leak

When pump status and tank boundaries are represented in the dual model and VR heads track the matching primal, sum(q_v) stays near zero across the transition. q_v does not flag ordinary pump/tank operations.

- Pass criterion: max_abs_sum_m3h < 0.2
- Passed: **True**

