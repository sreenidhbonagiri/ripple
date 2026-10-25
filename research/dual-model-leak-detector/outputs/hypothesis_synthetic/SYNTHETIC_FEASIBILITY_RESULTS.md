# Uncertainty-aware H0/H1 — synthetic feasibility results

Generated: `2026-10-25T07:34:54.622740+00:00`

Branch: `research/uncertainty-aware-hypothesis`  
Corrected calibration ref: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Selected `tau_dev`: **0.0** (dev only)  
Signature `τ_|Σqv|`: **3.0** m³/h  
Method M–style `σ_floor`: **1.875205759810683** m³/h; τ_ref=4.517

Protocol: `HYPOTHESIS_PROTOCOL.md`. Better fit ≠ proof of a leak. H1 nuisance bounds identical to H0.

## Test-split headline metrics (hypothesis test)

| Metric | Value |
|--------|------:|
| Detection TPR | 0.6666666666666666 |
| Control FPR / burden | 0.0 |
| Inconclusive rate | 0.4 |
| Ambiguous-family admit rate (dev+test amb rows in split metrics; see rows) | see per-split |
| Mean candidate region size (among detects) | 1.0 |
| Region coverage of true leak (among detects) | 0.5 |
| Exact-match localization among detects (not sole headline) | 0.5 |
| Localization error among detects | 0.5 |

## Baselines on the same test scenarios

| Method | TPR | FPR | Exact loc among detects | Inconclusive |
|--------|----:|----:|-------------------------:|-------------:|
| H0/H1 hypothesis | 0.6666666666666666 | 0.0 | 0.5 | 0.4 |
| Dual signature | 1.0 | 0.0 | 1.0 | n/a |
| Method M–style steady | 0.0 | 0.0 | None | n/a |

Baselines do not admit ambiguity; elevated FPR on demand-mismatch controls is expected (see prior `demand_mismatch_no_leak` synthetic verification).

## Per-scenario rows

| ID | Split | Seed | Truth leak | Decision | ΔJ | Best c | Region | Sig detect | MM detect |
|----|-------|-----:|:----------:|----------|---:|:------:|--------|:----------:|:---------:|
| `nl_nominal` | train | 0 | — | **no_new_leak** | 0.0000 | J1 | 3:J1,J2,J3 | False | False |
| `leak_nominal_J3` | train | 0 | J3 | **leak** | 0.3626 | J3 | 1:J3 | True | False |
| `nl_demand_scale` | train | 0 | — | **inconclusive** | 0.0995 | J3 | 1:J3 | True | False |
| `nl_noise` | dev | 0 | — | **no_new_leak** | 0.0000 | J1 | 3:J1,J2,J3 | False | False |
| `nl_noise` | dev | 1 | — | **no_new_leak** | 0.0000 | J1 | 3:J1,J2,J3 | False | False |
| `nl_noise` | dev | 2 | — | **no_new_leak** | 0.0000 | J1 | 3:J1,J2,J3 | False | False |
| `leak_noise_J3` | dev | 0 | J3 | **leak** | 0.3481 | J3 | 1:J3 | True | False |
| `leak_noise_J3` | dev | 1 | J3 | **leak** | 0.3483 | J3 | 1:J3 | True | False |
| `leak_noise_J3` | dev | 2 | J3 | **leak** | 0.3757 | J3 | 1:J3 | True | False |
| `ambiguous_demand_J1` | dev | 0 | — | **inconclusive** | 0.0005 | J1 | 3:J1,J2,J3 | False | False |
| `nl_roughness` | dev | 0 | — | **no_new_leak** | 0.0000 | J1 | 3:J1,J2,J3 | False | False |
| `leak_demand_var_J2` | test | 0 | J2 | **leak** | 0.1525 | J3 | 1:J3 | True | False |
| `nl_pump_transition` | test | 0 | — | **no_new_leak** | 0.0000 | J1 | 2:J1,J2 | False | False |
| `leak_pump_J1` | test | 0 | J1 | **inconclusive** | 0.0000 | J1 | 2:J1,J2 | True | False |
| `leak_roughness_J3` | test | 0 | J3 | **leak** | 0.4468 | J3 | 1:J3 | True | False |
| `nl_demand_node_J1` | test | 0 | — | **inconclusive** | 0.0001 | J1 | 3:J1,J2,J3 | False | False |

## Split metrics detail

```json
{
  "train_hypothesis": {
    "n": 3,
    "n_leak": 1,
    "n_control": 2,
    "tpr_detect": 1.0,
    "fpr_detect": 0.0,
    "control_burden_fpr": 0.0,
    "false_detect_count_controls": 0,
    "inconclusive_rate": 0.3333333333333333,
    "ambiguous_admit_rate": null,
    "n_ambiguous": 0,
    "localization_exact_among_detects": 1.0,
    "localization_error_rate_among_detects": 0.0,
    "mean_candidate_region_size_among_detects": 1.0,
    "region_coverage_among_detects": 1.0,
    "note": "Exact-match localization is reported only among detects and is not the sole headline. Inconclusive and region coverage are first-class."
  },
  "dev_hypothesis": {
    "n": 8,
    "n_leak": 3,
    "n_control": 5,
    "tpr_detect": 1.0,
    "fpr_detect": 0.0,
    "control_burden_fpr": 0.0,
    "false_detect_count_controls": 0,
    "inconclusive_rate": 0.125,
    "ambiguous_admit_rate": 1.0,
    "n_ambiguous": 1,
    "localization_exact_among_detects": 1.0,
    "localization_error_rate_among_detects": 0.0,
    "mean_candidate_region_size_among_detects": 1.0,
    "region_coverage_among_detects": 1.0,
    "note": "Exact-match localization is reported only among detects and is not the sole headline. Inconclusive and region coverage are first-class."
  },
  "test_hypothesis": {
    "n": 5,
    "n_leak": 3,
    "n_control": 2,
    "tpr_detect": 0.6666666666666666,
    "fpr_detect": 0.0,
    "control_burden_fpr": 0.0,
    "false_detect_count_controls": 0,
    "inconclusive_rate": 0.4,
    "ambiguous_admit_rate": null,
    "n_ambiguous": 0,
    "localization_exact_among_detects": 0.5,
    "localization_error_rate_among_detects": 0.5,
    "mean_candidate_region_size_among_detects": 1.0,
    "region_coverage_among_detects": 0.5,
    "note": "Exact-match localization is reported only among detects and is not the sole headline. Inconclusive and region coverage are first-class."
  },
  "test_signature": {
    "tpr_detect": 1.0,
    "fpr_detect": 0.0,
    "localization_exact_among_detects": 1.0,
    "inconclusive_rate": null,
    "note": "Baselines force a detect/no-detect bit; they do not admit inconclusive."
  },
  "test_method_m_style": {
    "tpr_detect": 0.0,
    "fpr_detect": 0.0,
    "localization_exact_among_detects": null,
    "inconclusive_rate": null,
    "note": "Baselines force a detect/no-detect bit; they do not admit inconclusive."
  }
}
```

## Review gate

Synthetic feasibility only. Stop for review before measured evaluation. No 2019 tuning, main merge, Tiger, UI, or deployment in this stage.

