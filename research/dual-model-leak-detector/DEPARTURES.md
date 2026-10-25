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
| Network | Calibrated L-Town | Stages 1–2 use **synthetic** networks only (controlled truth). |

## Not implemented in stages 1–2 (deferred)

| Topic | Published method | Status here |
|-------|------------------|-------------|
| Demand TSA / AMR clustering | Multiplicative trend×seasonality; Area C AMR | Deferred (stage 3) |
| Roughness WLS / LM | Six HW clusters; week-1 2018; Huber *κ*=3 | Deferred (stage 3) |
| Closed-valve ID | During roughness calibration | Deferred |
| Detection CUSUM / LR | Thresholds from leak-free week-1 dual flows | Deferred (stage 4); thresholds must be declared before evaluation |
| HMC / DE leak-shape fitting | Start-time refinement | Deferred |
| Localization Pearson / sensitivities | Eqs. (13)–(19) | Out of scope for detection-first path |
| Pressure-driven leaks | BattLeDIM generation is PD; authors’ diagnosis often DD | Synthetic truth uses **known demand-driven leak discharge** so actual leak flow is exact; do not equate to emitter leaks |

## Intentional non-claims

- **`sum(q_v)` is not automatically true leak discharge.** It approximates leak size when the primal model is correctly specified; demand, roughness, and datum errors produce confounding `q_v` of similar magnitude (demonstrated in synthetic tests; consistent with Campbell et al. 2024).
- This is **not** a pressure-residual CUSUM or LILA MRE pipeline.
- Stages 1–2 do **not** use 2018/2019 measured SCADA for fitting or scoring.