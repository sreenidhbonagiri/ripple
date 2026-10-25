# Departures from the published dual-model method

This package reconstructs the dual hydraulic construction from Steffelbauer et al.
(2022) and the BattLeDIM report (2020), plus implementation notes from Campbell et
al. (2024). **No public solver code** was available; the following choices are
explicit engineering reconstructions or intentional scope limits.

## Dual construction (implemented)

| Topic | Published method | This package |
|-------|------------------|--------------|
| Virtual assets | Valve + virtual reservoir at each pressure sensor | **TCV** + reservoir (`VR_*` / `TCV_*`), matching Campbell et al. (2024) |
| Valve loss | “Sufficiently low but nonzero” minor loss; exact *K* unpublished | Declared default **`tcv_setting = 1e-3`** (TCV loss coefficient). Overridable via `DualModelSpec`. |
| Measured head | Fixed-head BC = measured pressure head at sensors | **`H = P + z`** with *P* in metres of water and *z* node elevation. Time-varying: EPANET pattern × `base_head=1` so pattern values are absolute heads. |
| Flow sign | `q_v = -q_in` at virtual reservoirs (outflow residual) | Positive `q_v` = EPANET flow **sensor → VR** (out of the physical network). |
| Solver | EPANET 2.00.12 + proprietary GUI (authors) | **WNTR → EPANET** toolkit. Demand-driven analysis only. |
| Network | Calibrated L-Town | Stages 1–2: synthetic. Stage 3: nominal `data/L-TOWN.inp` + 2018 SCADA. |

## Stage 3 calibration departures

| Topic | Published method | This package |
|-------|------------------|--------------|
| Demand TSA | Unsupervised AMR clusters → residential/commercial (+mixed); multiplicative T·S; R neglected | AMR→type by **correlation with INP weekly patterns**; T·S blended 50% AMR-derived / 50% INP; R neglected |
| Area C demands | Combined AMR + inferred unmeasured | Measured AMR (L/h→m³/s) at 82 nodes; unmeasured Area-C bases × `area_c_unmeasured_scale` from **signed** mean of (PUMP_1 − dV_tank/dt − AMR) on FIT only (aligned finite mask; **no** per-sample clip before averaging — see AREA_C_SCALE_AUDIT.md), then clip to unchanged bounds [0.5, 1.5]; nonpositive aggregate flagged `physically_inconsistent` |
| Areas A/B | Inferred from patterns / base demands | INP pattern shape × single `ab_scale` from FIT external-inflow mass balance, clipped [0.7, 1.3]; **no leak timeseries in the objective** |
| Diameter correction | OD→ID table for plastics | **Not applied** — use INP diameters as shipped |
| Roughness clusters | 6 clusters by material/diameter/zone with C₀∈{90,120,140,146} | 6 clusters on local INP (C₀∈{120,140}): Area C, Area B (PRV-3 downstream), Zone A partitions by diameter/C₀ |
| Roughness optimizer | Projected LM + Huber κ=3, α=0, bounds [60,160], analytical Jacobian | `scipy.optimize.least_squares` TRF + `soft_l1` (f_scale=3), same bounds; **finite-difference residuals** via WNTR EPS |
| Closed valves | Identified in calibration | **Not implemented** |
| Time resolution | 5 min SCADA | Hydraulics / dual eval at **1 h** subsample for tractability (SCADA still loaded at 5 min for demand TSA) |
| Pump BC | Authors update pump flow from measurement in dual | INP **tank-level controls** retained; measured PUMP_1 used in mass-balance demand scaling and flow metrics only |
| Validation | Competition narrative on 2019 | **2018 multi-season held-out weeks only**; 2019 sealed |
| TCV K | Unpublished | Audited on FIT snapshot mean|q_v|; **not** chosen by leak-detection score; default 1e-3 preferred when competitive |

## Still deferred (stage 4+)

| Topic | Status |
|-------|--------|
| Detection CUSUM / LR + thresholds | Not started — no threshold search in stage 3 |
| HMC / DE leak-shape fitting | Deferred |
| Localization Pearson / sensitivities | Out of scope for detection-first path |

## Intentional non-claims

- **`sum(q_v)` is not automatically true leak discharge.** It approximates leak size when the primal model is correctly specified; demand, roughness, and datum errors produce confounding `q_v` of similar magnitude (demonstrated in synthetic tests; consistent with Campbell et al. 2024).
- This is **not** a pressure-residual CUSUM or LILA MRE pipeline.
- Stages 1–2 do **not** use 2018/2019 measured SCADA for fitting or scoring.