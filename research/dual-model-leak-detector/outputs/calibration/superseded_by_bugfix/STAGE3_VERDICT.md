# Stage 3 calibration / generalization verdict

**Verdict: `PASS_WITH_LIMITATIONS`**

Demand calibration (FIT_W1 only) materially improves pressure RMSE on the fit
week and on four multi-season 2018 validation weeks versus the nominal INP.
Roughness cluster values remain essentially at their INP initials (weakly
identified). Virtual-flow magnitudes shrink, but signed Σq_v is **not** near
zero even on the leak-free fit week, and strong day/night operating-state bias
remains. **Do not treat this freeze as detection-ready.**

Generated: `2026-10-25T04:31:41.548859+00:00`  
TCV K frozen: `0.001` (nominal audit; not leak-tuned)

## Nominal solver audit (pre-calibration)

- 33/33 pressure sensors map into `L-TOWN.inp`; 82/82 AMRs lie in Area C.
- Head conversion: `H = P + z` (P in metres water).
- Flows: `p227`+`p235` external inflows; `PUMP_1` internal n54→T1.
- Tank init from SCADA; INP level controls retained.
- TCV K sweep on FIT snapshot (minimize mean|q_v|, not leak score) → **K=1e-3**.

## Fit window (FIT_W1) — calibration vs nominal

| Model | Pressure RMSE (m) | Ext. inflow bias (m³/h) | Tank RMSE (m) | Σq_v mean (m³/h) | mean\|q_v\| (m³/h) |
|-------|------------------:|------------------------:|--------------:|-----------------:|------------------:|
| nominal | 0.642 | +7.18 | 0.768 | +2.68 | 2.71 |
| calibrated | 0.295 | +24.38 | 0.275 | −13.35 | 1.38 |

Pressure and tank level improve. External-inflow bias **worsens** on the fit
week (demand scaling prioritizes AMR/Area-C mass balance and patterns over
matching p227+p235 exactly). Individual |q_v| drops ~2×; signed sum remains
biased (cancellation ratio 0.55 vs 0.89 nominal — less hiding, still imperfect).

Day vs night Σq_v (calibrated FIT): day ≈ −12.6 m³/h, night ≈ −25.7 m³/h.

## Validation windows (frozen parameters; no refit)

| Window | Model | P RMSE (m) | Ext bias (m³/h) | Σq_v mean | mean\|q_v\| | cancel ratio |
|--------|-------|----------:|----------------:|----------:|------------:|-------------:|
| VAL_APR | nominal | 0.665 | −22.1 | +33.4 | 2.93 | 0.83 |
| VAL_APR | calibrated | 0.341 | +17.1 | −5.43 | 1.57 | 0.46 |
| VAL_JUL | nominal | 0.810 | −47.4 | +59.5 | 3.24 | 0.87 |
| VAL_JUL | calibrated | 0.375 | +12.5 | +1.35 | 1.55 | 0.50 |
| VAL_OCT | nominal | 0.803 | −52.8 | +65.5 | 3.33 | 0.84 |
| VAL_OCT | calibrated | 0.431 | −9.30 | +21.7 | 1.81 | 0.59 |
| VAL_DEC | nominal | 0.735 | −35.8 | +47.9 | 3.09 | 0.83 |
| VAL_DEC | calibrated | 0.346 | −0.44 | +13.0 | 1.64 | 0.48 |

Mean validation pressure RMSE: nominal **0.753 m** → calibrated **0.373 m**.
Validation weeks are **not** leak-free; Σq_v includes background leaks plus
model error. Per-sensor means/stds are in `stage3_results.json`.

## Parameter stability / identifiability

| Parameter | Result |
|-----------|--------|
| Roughness (6 clusters, bounds [60,160]) | All **interior**; values ≈ x0 (ΔC < 0.2). Weakly identified under this demand model + weekly FIT — pressure gains are almost entirely from demand. |
| `ab_scale` | 1.024 (interior of [0.7, 1.3]) |
| `area_c_unmeasured_scale` | **1.50 upper bound** (raw estimate 2.80). Unmeasured Area-C demand (or FIT mass-balance residual) exceeds INP bases; clip prevents absorbing unexplained flow into uncapped demand. |
| Closed valves | Not estimated (departure). |

## Leak-onset diagnostics (frozen; not detection accuracy)

Abrupt 2018 onsets, ±24 h dual Σq_v under frozen calibration:

| Leak | Onset | ΔΣq_v (m³/h) | Dominant \|Δq_v\| (m³/h) | Note |
|------|-------|-------------:|------------------------:|------|
| p673 | 2018-03-05 15:45 | +30.9 | 20.0 (n229) | pre/post std ≈ 43 m³/h |
| p538 | 2018-05-18 08:35 | +48.5 | 11.5 (n332) | large diurnal noise |
| p866 | 2018-06-01 09:05 | +16.0 | 13.3 (n296) | |
| p183 | 2018-08-07 02:35 | +30.5 | 9.7 (n752) | |
| p158 | 2018-10-06 02:35 | +35.6 | 17.4 (n644) | |

Onsets often move Σq_v in the expected direction, but **pre-window std is
comparable to the delta** and ordinary day/night swings are tens of m³/h.
These are diagnostic only — **no threshold was fit; no claim of validated
detection.**

## Departures

See `DEPARTURES.md` (stage 3 section) and `CALIBRATION_WINDOWS.md`.

## Artifacts

- `outputs/calibration/NOMINAL_LTOWN_AUDIT.{md,json}`
- `outputs/calibration/frozen_calibration.json`
- `outputs/calibration/stage3_results.json`
- `outputs/calibration/STAGE3_VERDICT.md` (this file)
- `CALIBRATION_WINDOWS.md` (registered before fitting)

No detector threshold search. No 2019. No UI / Tiger / main / deploy.
