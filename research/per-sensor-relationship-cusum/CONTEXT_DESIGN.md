# Operating-context residual correction — design (registered before runs)

**Branch:** `research/per-sensor-relationship-cusum`  
**Preserves:** production, prior detectors (original CUSUM-zero + residual-recovery), all frozen
negative / limited results (`RESULTS.md`, `VARIANT_COMPARISON.md`, `CALIBRATION_AUDIT.md`).

## Question

Can pump/tank (and calendar) **context** explain nuisance pressure-relationship
deviations **without suppressing** leak-related changes?

## Held identical

| Element | Choice |
|---------|--------|
| Pressure refs / pairwise OLS | Existing training-only selection (`K=3`, `train_days=14`) |
| Notification policy | **Residual-recovery variant** (`z≤k` for 12 steps; `k=0.5`, `h=8`) — not swept |
| Matching / eligibility | Post pairwise-training onsets; abrupt 0–7 d; prefix (p654) separate |
| Missing data | Same hold-C / break-recovery rules |
| Features **not** used | Future values, leak labels, leak locations, total inflow, AMR |

## Context model (associative — not causal explanation)

For each target \(i\), after pairwise fits, form the **raw aggregate residual** (meters):

\[
r_i(t)=\mathrm{median}_{j\in\mathcal{R}_i} e_{ij}(t),\quad
e_{ij}(t)=\hat P_i^{(j)}(t)-P_i(t)
\]

Predict an ordinary/context component \(\hat r_i^{\mathrm{ctx}}(t)=x(t)^\top\beta_i\) with
**ridge** regression. Corrected residual:

\[
r_i^{\mathrm{corr}}(t)=r_i(t)-\hat r_i^{\mathrm{ctx}}(t)
\]

### Features \(x(t)\) (units / availability verified)

| Feature | Definition | Unit / note |
|---------|------------|-------------|
| `sin_tod`, `cos_tod` | \(\sin,\cos(2\pi\,h/24)\) from SCADA timestamp hour | dimensionless |
| `is_weekend` | Saturday/Sunday | \{0,1\} |
| `pump1` | `PUMP_1` flow at \(t\) | same as SCADA Flows CSV |
| `pump1_on` | \(1\{\mathrm{PUMP\_1}(t)>\varepsilon\}\) with \(\varepsilon=1\) | \{0,1\} |
| `tank_T1` | `T1` level at \(t\) | same as SCADA Levels CSV |
| `d_tank_T1` | \(T1(t)-T1(t-1)\) (5-min causal lag) | level units / step; NaN at first analysis step |

All features use only measurements at times \(\le t\). Timestamps aligned across Pressures / Flows / Levels.

**Do not** interpret \(\beta_i\) as a causal effect of pumps/tanks on leaks.

## Chronological partitions

Within each period (DEV then DIAG):

1. **Pairwise train:** first 14 days (frozen).  
2. **Context fit:** next `context_fit_days=14` of post-pair analysis.  
3. **Context validation (DEV only):** following `context_val_days=14` — select ridge
   `alpha` by mean target RMSE of \(r_i\) prediction (**chronological prediction error only**).  
4. Detection series: full post-pair analysis span (same eligible onsets for both arms).

On DIAG: use **frozen** `alpha` from DEV; refit \(\beta_i\) on DIAG context-fit window only
(no DIAG alpha search).

Better DEV prediction error is **not** by itself success; detection metrics decide.

## Normalization (identical robust procedure)

Apply the same loc/scale recipe (median / MAD·1.4826, std fallback) to each series:

- **Baseline \(r_i\):** loc/scale from the pairwise-training window’s aggregate residuals.  
- **Corrected \(r_i^{\mathrm{corr}}\):** loc/scale from the chronological **context-fit**
  window of \(r_i^{\mathrm{corr}}\) (early corrected samples; context hat is defined
  after pairwise train).

\(z=(r-\mathrm{loc})/\mathrm{scale}\). Scales may differ; the *procedure* is identical.

## Controlled comparisons

| Arm | Signal | Detector |
|-----|--------|----------|
| Baseline | original \(z_i\) from \(r_i\) | residual-recovery CUSUM |
| Context | \(z_i\) from \(r_i^{\mathrm{corr}}\) | **identical** policy |

No recovery / floor / threshold / feature-set sweeps.

## Signal preservation

Three abrupt DIAG onsets + the documented equal-length onset-excluded controls from the
calibration audit. Report raw-meter and standardized contrasts before/after conditioning;
flag if context explains away an event. Inspect ordinary pump transitions and stable periods.

## Decision rule

Continue only if corrected signal improves **sensitivity/burden** (esp. 0–2 h notify
behavior / occupancy / unmatched burden) **without** relying on broad matching or
latched alarms. If it suppresses leak signals or fails to cut ordinary excursions,
report failure — **no follow-up sweep**.

2019: not evaluated. DIAG remains diagnostic, not independent validation.
