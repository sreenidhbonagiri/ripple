# Residual calibration & separability audit

Generated: 2026-10-24T20:07:37-04:00

Frozen detectors, RESULTS, variant comparison, and production are **preserved**. No recovery sweep, normalization floor, or new detector.

DIAG fits: train_days=14, K=3, k=0.5.

## 1. Normalization verification

Signed residual \(e = \hat P_i - P_i\) in **meters**. Scale = MAD(e)·1.4826 with std fallback if MAD scale < 1e-6.

- Selected pairs: **99**
- Train MAD < 0.05 m: **94** (94.9%)
- OOS MAD / train MAD > 2: **2** (2.0%)
- Scale fallback used: **0**

Interpretation counts:

- `genuinely_tight_in_sample_and_near_oos`: 94
- `underestimated_oos_uncertainty`: 2
- `moderate_or_mixed`: 3

Full per-pair table: `outputs/calibration_pairs.json`.

### Sample pairs (smallest train MAD)

| Target | Ref | a (m) | b | train MAD (m) | scale (m) | OOS MAD (m) | OOS/train | reading |
|--------|-----|-------|---|---------------|-----------|-------------|-----------|---------|
| n105 | n469 | 3.789 | 0.983 | 0.0034 | 0.0051 | 0.0034 | 1.00 | genuinely_tight_in_sample_and_near_oos |
| n469 | n105 | -3.842 | 1.017 | 0.0035 | 0.0053 | 0.0035 | 1.00 | genuinely_tight_in_sample_and_near_oos |
| n740 | n769 | 18.467 | 0.522 | 0.0036 | 0.0053 | 0.0038 | 1.06 | genuinely_tight_in_sample_and_near_oos |
| n495 | n332 | 17.866 | 0.599 | 0.0037 | 0.0054 | 0.0037 | 1.00 | genuinely_tight_in_sample_and_near_oos |
| n740 | n722 | 20.999 | 0.494 | 0.0039 | 0.0057 | 0.0040 | 1.04 | genuinely_tight_in_sample_and_near_oos |
| n726 | n752 | -0.688 | 0.972 | 0.0039 | 0.0058 | 0.0040 | 1.01 | genuinely_tight_in_sample_and_near_oos |
| n769 | n752 | 11.949 | 0.743 | 0.0039 | 0.0059 | 0.0038 | 0.96 | genuinely_tight_in_sample_and_near_oos |
| n752 | n726 | 0.715 | 1.028 | 0.0041 | 0.0060 | 0.0041 | 1.00 | genuinely_tight_in_sample_and_near_oos |

## 2. Ordinary excursions (train vs analysis)

Evidence-tag totals across 33 targets: {'isolated_spikes_common': 33, 'persistent_relationship_changes': 15, 'monthly_drift': 16, 'scale_mismatch': 1}

- Median frac(z>k): **0.240**
- Median lag-1 ACF(z): **0.678**
- Targets with max exceedance run ≥ 6 h: **15**

Unmatched / non-onset periods are **not** assumed leak-free (background leaks, ops).

Per-target details: `outputs/calibration_excursions.json`.

## 3. Signal separability (abrupt DIAG examples)

**Control rule:** equal-length windows (6 h pre + 24 h post = 360 steps). Candidate starts at analysis free-span quartiles {1/4, 2/4, 3/4}; reject if overlapping ±7 d around any labeled **onset** (not full leak lifetime); else advance +1 day until eligible. Controls are not assumed leak-free. Not chosen by visual convenience.

Labels identify event window timing only. No leak-location sensor picking. **Not validation.**

### p183 onset 2018-08-07 02:35
- Stands out before CUSUM (rule): **False**
- Plot: outputs/calibration_plots/separability_p183.png
- Controls: ['2018-08-26 04:30', '2018-10-13 09:00', '2018-11-18 13:30']

| Target | Δz | Δraw (m) | event post z | ctrl z | pct vs ctrl samples | beats all ctrl medians | refs |
|--------|----|----------|--------------|--------|---------------------|------------------------|------|
| n752 | 7.11 | 0.054 | 8.18 | 1.06 | 82 | False | ['n726', 'n769', 'n288'] |
| n288 | -3.51 | -0.039 | -3.24 | 0.27 | 19 | False | ['n726', 'n752', 'n679'] |
| n613 | -2.57 | -0.016 | 1.66 | 4.23 | 10 | False | ['n163', 'n188', 'n519'] |
| n726 | 2.02 | 0.017 | 1.53 | -0.49 | 91 | True | ['n752', 'n769', 'n288'] |
| n769 | -1.57 | -0.012 | -1.44 | 0.13 | 11 | False | ['n752', 'n726', 'n722'] |

### p158 onset 2018-10-06 02:35
- Stands out before CUSUM (rule): **False**
- Plot: outputs/calibration_plots/separability_p158.png
- Controls: ['2018-08-26 04:30', '2018-10-13 09:00', '2018-11-18 13:30']

| Target | Δz | Δraw (m) | event post z | ctrl z | pct vs ctrl samples | beats all ctrl medians | refs |
|--------|----|----------|--------------|--------|---------------------|------------------------|------|
| n644 | 7.87 | 0.183 | 10.21 | 2.34 | 78 | False | ['n636', 'n679', 'n332'] |
| n342 | 3.03 | 0.029 | 4.40 | 1.37 | 86 | True | ['n458', 'n415', 'n613'] |
| n613 | 2.54 | 0.023 | 6.77 | 4.23 | 82 | False | ['n163', 'n188', 'n519'] |
| n229 | 2.28 | 0.057 | 3.00 | 0.71 | 84 | True | ['n636', 'n613', 'n163'] |
| n679 | 2.25 | 0.024 | 0.90 | -1.34 | 87 | True | ['n288', 'n726', 'n296'] |

### p369 onset 2018-10-26 02:05
- Stands out before CUSUM (rule): **True**
- Plot: outputs/calibration_plots/separability_p369.png
- Controls: ['2018-08-26 04:30', '2018-10-13 09:00', '2018-11-18 13:30']

| Target | Δz | Δraw (m) | event post z | ctrl z | pct vs ctrl samples | beats all ctrl medians | refs |
|--------|----|----------|--------------|--------|---------------------|------------------------|------|
| n410 | 4.15 | 0.120 | 3.15 | -0.99 | 100 | True | ['n429', 'n415', 'n342'] |
| n636 | -3.14 | -0.049 | -0.03 | 3.11 | 14 | False | ['n188', 'n613', 'n163'] |
| n296 | 1.91 | 0.013 | -1.27 | -3.18 | 91 | True | ['n722', 'n726', 'n288'] |
| n679 | 1.85 | 0.022 | 0.51 | -1.34 | 86 | True | ['n288', 'n726', 'n296'] |
| n644 | -1.57 | -0.055 | 0.76 | 2.34 | 27 | False | ['n636', 'n679', 'n332'] |

## 4. Recommended next experiment

**Direction:** `calibration_unlikely_alone`

Ordinary and leak-timed residual changes overlap substantially under the documented controls; calibration alone is unlikely to solve detection. Revisit the sensing hypothesis, aggregation, or state-conditional features—without an arbitrary scale floor.

**Supported by:** abrupt events standing out before CUSUM: 1/3; weak-separability count=2; median OOS/train MAD=0.993; tags={'isolated_spikes_common': 33, 'persistent_relationship_changes': 15, 'monthly_drift': 16, 'scale_mismatch': 1}

Not implemented. No 2019 evaluation.

