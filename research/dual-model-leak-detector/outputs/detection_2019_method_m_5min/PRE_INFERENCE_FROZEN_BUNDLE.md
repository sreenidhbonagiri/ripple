# Pre-inference frozen bundle — five-minute Method M on 2019

**Diagnostic evaluation, not a blind holdout.**  
2019 has already been examined during previous research.

## Fixed before any 2019 inference

| Item | Source | Value |
|------|--------|-------|
| Calibration | `frozen_calibration.json` | sha256 `5fab3acb…0c921` |
| Pump boundary | measured-PUMP_1 | unchanged |
| Timestep | METHOD_M_5MIN | 300 s |
| τ | 2018 5-min DEV freeze | **4.517** |
| σ_i / raw-max median | 2018 SCALE on 5-min dual | from `method_m_5min_results.json` |
| REF / gap / credit | Timedelta hours | 24 h / 1 h / 6 h |
| REF_MIN_SAMPLES | 5-min protocol | 144 |
| RECOVER_STEPS | 1 h elapsed | 12 |
| Causal fill max age | protocol | 2 steps |

No τ selection, scale refit, or window changes on 2019.

## Continuity

2018 five-minute dual (`dual_qv_5min_dev` + `dual_qv_5min_diag`) is concatenated
with 2019 dual before scoring and notifying so causal refs and notifier state
carry across the year boundary (no reset at onsets or month starts).

## Hash order

1. Record artifact/code hashes (`pre_inference_hashes.json`) — **before** dual.
2. Build 2019 dual; score; notify.
3. Hash 2019 scores and notification list (`pre_label_hashes.json`) — **before**
   loading evaluation labels.
4. Load catalog labels; evaluate; compare to frozen hourly Method M (τ=4.347).

## Primary vs inclusive abrupt reporting

- **Primary:** abrupt 2019 onsets **excluding** development example **p523**.
- **Inclusive:** all abrupt 2019 onsets including p523.
