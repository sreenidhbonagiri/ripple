# Frozen Method M — 2019 pre-inference bundle

**Recorded before any 2019 dual/score/notify inference.**  
**Frozen diagnostic evaluation:** 2019 has already been examined in prior research; this is **not** a blind holdout.

No parameter retuning. τ, scales, calibration, hydraulics, and notify/recover rules are fixed from 2018 Method M.

---

## Artifact hashes (sha256)

Computed at bundle-registration time by `scripts/run_method_m_2019_frozen.py` and written to
`pre_inference_hashes.json` (byte hashes of the files below).

| Component | Path / value | Future observations? |
|-----------|--------------|----------------------|
| Calibration | `outputs/calibration/frozen_calibration.json` | **No** — fitted on 2018 FIT only |
| Sensor scales σᵢ + raw-max median | `method_m_results.json` → `scale` (2018 SCALE Jan 9–21) | **No** — frozen after 2018 SCALE |
| Threshold | **τ = 4.347** (2018 DEV p99 selection) | **No** — selected on 2018 DEV only |
| Hydraulic formulation | `PUMP1_MEASURED_BOUNDARY.md` + `dual_model/pump_boundary.py` | **No** — uses measured PUMP_1 / heads **at analysis timestamp** only (causal fill for missing pump) |
| Dual construction | `dual_model/dual_builder.py`, `ltown_hydraulics.run_dual_window` | **No** — VR heads from contemporaneous P; no look-ahead |
| Score Method M | `METHOD_M_PROTOCOL.md` + `detection_scores.score_M_*` | **No** — ref = 24 h ending 1 h before t |
| Notification / recovery | `dual_model/notifier.py` (notify ≥τ; recover &lt;τ/2 for 1 h) | **No** — causal on the score series |

---

## Causality checklist

1. Dual chunk tank init uses measured level at **chunk start** (past/present), not future.  
2. Measured PUMP_1 BC uses only values at/before t (causal ffill within chunk).  
3. Method M δᵢ uses q_v(t) vs μ_ref on [t−25h, t−1h].  
4. σᵢ and max-calibration median never updated on 2019.  
5. Notifier state carries continuously through 2019 (no reset at leak onsets or month boundaries). Prior-year score history (2018 measured-PUMP_1 q_v) is used only so early-2019 refs/notifier state are defined — **not** for retuning.

---

## Evaluation labels

Leak labels (`dataset_configuration.yaml` / 2019 leakages) are **not loaded** until scores and notification times are hashed and written under `pre_label_*.sha256`.
