# Measured PUMP_1 internal-transfer boundary (isolated dual variant)

Paper-aligned reconstruction: Steffelbauer et al. / BattLeDIM dual model updates
the **pump transfer from measurement** in the dual, rather than relying only on
tank-level open/close controls. This document freezes the hydraulic formulation
**before** implementation. It does **not** change frozen calibration or the
baseline detector artifacts under `outputs/detection_2018/`.

## Role of PUMP_1

| Item | Choice |
|------|--------|
| Topology (L-Town INP) | `PUMP_1`: start **`n54`** → end **`T1`** |
| Physical role | **Internal transfer** from Area A (at `n54`) into the tank / Area C |
| External supply | **`p227` + `p235` only** — never count `PUMP_1` as external inflow |
| Detection Method C | Unchanged: `|Δ(p227+p235)|` |

Positive SCADA `PUMP_1` (m³/h) means flow **n54 → T1** (filling / supplying Area C
via the tank inlet).

## Boundary formulation (dual only)

At each analysis timestamp \(t\) with measured pump flow \(Q_p(t)\) [m³/h]:

1. **Disable** INP tank-level controls that open/close `PUMP_1` (levels 2.4 / 3.9 m).
2. **Close** the `PUMP_1` head-pump link so its curve does not carry a second flow.
3. Impose an equal-and-opposite **demand pair** that realises the same transfer:
   - Extract \(Q_p(t)\) at **`n54`** (positive demand).
   - Inject \(Q_p(t)\) on the tank side via a short pipe from a dedicated junction
     `_PUMP1_TANK_INJ` → `T1` (negative demand at the junction).
4. Keep **tank `init_level`** from measured `T1` at the **chunk start** only; do
   **not** reset tank level every hour (mass balance evolves from \(Q_p\) − Area-C
   outflow).
5. Keep virtual reservoirs at pressure sensors (`H = P + z`) unchanged.

EPANET forbids an FCV directly on a tank; the demand-pair + short inlet pipe is
the EPS-compatible realisation of a measured internal transfer that preserves
tank mass balance.

### Units

| Quantity | Unit in code / patterns |
|----------|-------------------------|
| SCADA `PUMP_1` | m³/h |
| EPANET demand pattern multipliers | m³/s (`× 1/3600`) |
| Reported q_v | m³/h (detection) |

### Timestamp convention

- Dual series remain **hourly** samples at `minute == 0` (same as baseline).
- \(Q_p(t)\) is the SCADA value at that same hourly timestamp (no look-ahead).
- Pump on/off events that fall between hours are seen only through the hourly
  sample (documented smear; not corrected here).

### Missing / non-finite pump data

Causal handling only (no future values):

1. If \(Q_p(t)\) is finite → use it.
2. Else forward-fill from the last finite value **at or before** \(t\) within the
   chunk.
3. If no prior finite value exists → use `0.0` and flag `pump_imputed_zero`.
4. Record counts: `n_pump_finite`, `n_pump_ffill`, `n_pump_zero_impute`.

Do not invent flows from tank controls when measurement is missing.

## Constraints deliberately **not** combined

| Avoid | Why |
|-------|-----|
| Measured \(Q_p\) **and** INP open/close controls | Controls fight the measured on/off |
| Measured \(Q_p\) **and** active `PUMP_1` head curve | Double flow path / incompatible BC |
| Measured \(Q_p\) **and** hourly forced tank level | Over-constrains storage; breaks free mass balance |
| Treating \(Q_p\) as external inflow in Method C or mass-balance “inflow” metrics | Mis-labels internal transfer |

Tank min/max levels remain physical limits of the tank object; they are not used
as pump switches in this variant.

## Isolation

| Artifact | Status |
|----------|--------|
| `outputs/calibration/frozen_calibration.json` | Untouched |
| `outputs/detection_2018/*` baseline | Untouched |
| New dual path | `pump_boundary="measured_pump1"` |
| New outputs | `outputs/detection_2018_measured_pump1/` |
| Production / main / UI / Tiger / 2019 | Out of scope |

## Verification plan (synthetic)

1. Matched no-leak pump/tank transition with measured \(Q_p\) from primal → Σq_v ≈ 0.
2. Leak under stable pump → Σq_v tracks leak.
3. Leak coincident with pump transition → Σq_v tracks leak (transition not a false residual when \(Q_p\) is matched).
4. Noisy / missing \(Q_p\) → convergence flags + bounded artifacts; no future fill.

## 2018 comparison plan

Paired run under the **same** frozen calibration hash and **same** diagnostic τ
values from the baseline selection fallback (no re-selection, no recalibration).
Label as diagnostic comparison because the boundary change shifts score
distributions.
