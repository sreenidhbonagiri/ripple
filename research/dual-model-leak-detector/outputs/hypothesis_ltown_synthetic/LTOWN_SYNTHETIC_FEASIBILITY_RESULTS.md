# Calibrated L-Town H0/H1 — synthetic feasibility

Generated: `2026-10-25T08:06:18.404374+00:00`

Frozen calibration: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Candidates: **33** pressure-sensor junctions (all represented eval leaks)  
DEV-frozen: `tau_dev=0.05`, `region_eps=0.0` (not a probability; intended coverage 0.9)  
Signature (DEV-matched burden): `tau_lo=0.5`, `tau=5.6947152472275775`

Toy stage preserved under `outputs/hypothesis_synthetic/` (see `AUDIT_TOY_SYNTHETIC.md`).  
**Method M temporal comparison: inapplicable** vs isolated steady snapshots.

## Generator / bounds

- Obs and H0/H1: same nonlinear EPANET on calibrated L-Town (no linear approx for reported J).
- H1 nested: nuisance frozen at H0 MLE; only q_c>=0 added (no extra flexibility).
- Scenario perturbations designed inside scale/rho/q boxes (see per-row `bound_notes`).

## DEV freeze check (exact counts in JSON)

- Hypothesis DEV: TPR=0.3333333333333333 FPR=0.0 abstain=0.8571428571428571 region_cov=1.0 (n_detects=1) mean_|R|=1.0

## TEST metrics (fresh scenarios; not used for eps/tau)

| Method | n | TPR | FPR | Abstention | mean |R| | Coverage | Exact loc / detects |
|--------|--:|----:|----:|-----------:|--------:|---------:|--------------------:|
| H0/H1 | 6 | 0.25 | 0.0 | 0.6666666666666666 | 1.0 | 1.0 | 1.0 |
| Signature (matched) | 6 | 0.25 | 0.0 | 0.5 | 1 (singleton) | n/a (singleton) | 1.0 |

Counts hypothesis test: `{'tp': 1, 'fp': 0, 'n_pos': 4, 'n_neg': 2, 'abstain': 4, 'region_cover_num': 1, 'region_cover_den': 1}`  
Counts signature: `{'tp': 1, 'fp': 0, 'n_pos': 4, 'n_neg': 2, 'abstain': 3}`

## Per-scenario

| ID | Split | Truth | Decision | dJ | Best | |R| | Cover | Sig |
|----|-------|-------|----------|---:|------|----:|:----:|-----|
| `lt_nl_nominal` | train | — | **no_new_leak** | -0.0000 | n31 | 1 | — | no_new_leak |
| `lt_leak_only_n506` | train | n506 | **inconclusive** | 0.0176 | n506 | 1 | — | inconclusive |
| `lt_demand_only_areaC` | train | — | **inconclusive** | 0.0002 | n31 | 1 | — | inconclusive |
| `lt_nl_noise` | dev | — | **inconclusive** | 0.0004 | n740 | 1 | — | inconclusive |
| `lt_nl_noise` | dev | — | **inconclusive** | 0.0017 | n613 | 1 | — | inconclusive |
| `lt_leak_noise_n726` | dev | n726 | **inconclusive** | 0.0302 | n679 | 1 | — | inconclusive |
| `lt_leak_noise_n726` | dev | n726 | **inconclusive** | 0.0272 | n752 | 1 | — | inconclusive |
| `lt_demand_only_areaA` | dev | — | **inconclusive** | 0.0424 | n342 | 1 | — | inconclusive |
| `lt_mismatch_roughness` | dev | — | **inconclusive** | 0.0480 | n342 | 1 | — | inconclusive |
| `lt_combined_demand_leak_n644` | dev | n644 | **leak** | 0.0833 | n644 | 1 | Y | leak |
| `lt_leak_only_n342` | test | n342 | **inconclusive** | 0.0342 | n342 | 1 | — | inconclusive |
| `lt_demand_only_areaB` | test | — | **inconclusive** | 0.0000 | n229 | 1 | — | no_new_leak |
| `lt_combined_n519` | test | n519 | **inconclusive** | 0.0159 | n519 | 1 | — | inconclusive |
| `lt_pump_transition_nl` | test | — | **no_new_leak** | -0.0000 | n31 | 1 | — | no_new_leak |
| `lt_pump_transition_leak_n54` | test | n54 | **inconclusive** | 0.0111 | n54 | 1 | — | inconclusive |
| `lt_mismatch_leak_n415` | test | n415 | **leak** | 0.2514 | n415 | 1 | Y | leak |

## Scope

Synthetic only. No measured evaluation, 2019, production, Tiger, UI, or deployment.

