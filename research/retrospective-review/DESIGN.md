# Retrospective pressure-pattern review — design (locked before runs)

**Branch:** `research/retrospective-review`  
**Sponsor context:** Tiger Data remains the production investigation store; this experiment is **offline / local only**.  
**Product boundary:** Ripple’s deployed workspace has **no validated automatic leak detector**. Outputs here are **candidate persistent pressure-pattern changes** for human review — **not** confirmed leaks and **not** live alerts.

**Holdout honesty:** 2019 has already been examined historically and **is not** a new blind holdout. This experiment uses **2018 only** (DEV → freeze → DIAG). Labels may guide documented evaluation matching; they **never** select nearest sensors or pairs at inference.

---

## Published method inspected (attribution)

Primary sources (read before implementation):

1. Daniel et al. (2022), *J. Water Resour. Plann. Manage.* 148(6):04022025 — **LILA** (leakage identification + localization). NSF public copy used for methods detail.  
2. Official identification code: [SWN-group-at-TU-Berlin/LILA](https://github.com/SWN-group-at-TU-Berlin/LILA) (GPLv3). Notebook `LI/2019_leakage_identification.ipynb`; utilities under `_utils/`.

**We do not vendor or copy LILA source into this repository** (GPLv3). This experiment is an **independent, simplified reimplementation** of identification *ideas* (pairwise pressure regression + residual change detection), cited for scientific attribution only. **It does not claim to reproduce Daniel et al. (2022) numerical results or BattLeDIM competition scores.**

### LILA identification (as published) — summary

| Piece | Published behavior |
|-------|-------------------|
| Pairs | Semisupervised **pairwise linear regression** of pressure sensors (Bernoulli / energy-motivated) |
| Training | Coefficients fit on a **manually selected** period argued to be free of *new* leaks |
| Residual | Model reconstruction error (MRE) \(P_i - \hat P_i\); aggregate via **Frobenius-type** magnitude over pairs |
| Change points | **CUSUM** on aggregated MRE; alarms / start-time estimates |
| Disaggregation | Paper notes simultaneous leaks aggregate; **manual per-leak node-pair selection** for clearer individual trajectories |
| Recalibration | After a leak becomes distinct, model may be **recalibrated** |
| Localization | Separate model-based step (out of scope here) |

### Manual / event-specific / future-dependent choices in the reference (must not copy via known leaks)

- Manual **leak-free** training window selection using analyst knowledge of the year.  
- Manual **per-leak sensor-pair** selection using knowledge of which leaks to disaggregate.  
- Notebook structure that investigates identified leaks **individually** after global visualization (event-conditioned analysis).  
- Competition-oriented 2019 evaluation and expert-annotated comparisons.

**Forbidden here:** using true leak pipe/node identity to choose sensors, pairs, or training windows.

---

## Our method (one justified approach): `PairwiseOLS + offline CUSUM`

**Name:** Retrospective Pairwise Residual Change Screening (RPRCS)  
**Justification:** Closest *automated* subset of LILA’s identification step that (a) needs only pressures, (b) admits a completed historical interval with hindsight *inside* the interval, and (c) avoids event-specific pair picking. Localization and hydraulic simulation are deferred.

### Interval semantics

For a selected closed interval \([T_0, T_1]\):

- **Hindsight allowed** for timestamps \(t \le T_1\).  
- **Never** use measurements with \(t > T_1\).  
- **Estimated change time** \(\hat t_c\): CUSUM-estimated onset inside the interval.  
- **Evidence available through:** \(T_1\) (and optionally the next candidate boundary).  
- \(\hat t_c\) is **not** a real-time notification timestamp.

### Training and sensor-pair selection

- Sensors: **all** configured pressure sensors present in the SCADA file (no location-based subset).  
- Pairs: **all unordered pairs** \(\{i,j\}\) with \(i < j\) (symmetric models: regress \(P_i\) on \(P_j\) and \(P_j\) on \(P_i\), both residuals kept).  
- Training window: **chronological prefix** of the analysis interval: first `train_days` calendar days in \([T_0, T_1]\), **not** chosen as leak-free via labels.  
  - *Documented limitation vs LILA:* prefix may contain background / new leaks (e.g. early 2018), which can bias residuals.

### Pressure preprocessing and residual construction

- Input: official 5-minute SCADA pressures (semicolon / decimal comma), units meters.  
- Preprocess: linear time index; missing values invalidate that sensor at \(t\) (pair skipped if either side missing).  
- No AMR / flow features in the score (flows/levels logged only for **ordinary-operation sensitivity** reporting).  
- Fit OLS \(P_i = a_{ij} + b_{ij} P_j\) on training rows where both finite.  
- Residual \(r_{ij}(t) = P_i(t) - (a_{ij} + b_{ij} P_j(t))\).  
- Aggregate score  
  \[
  S(t) = \sqrt{\sum_{i<j}\big(r_{ij}(t)^2 + r_{ji}(t)^2\big)}
  \]
  (Frobenius-like over directed pair residuals). If no valid pairs at \(t\), mark `missing_score` (not zero).

### Retrospective change-point method

- Standardize \(S(t)\) using **training-window** mean/std \(\mu_S, \sigma_S\) (frozen; no peeking past \(T_1\)).  
- One-sided CUSUM on \(z(t) = (S(t)-\mu_S)/\sigma_S\) for \(t\) after training end:  
  \(C_{t} = \max(0, C_{t-1} + z(t) - k)\), alarm when \(C_t \ge h\).  
- On alarm: **estimated change time** = time of last zero-crossing of \(C\) before the alarm (classic CUSUM change estimate), clipped to post-training analysis range.  
- Reset \(C\) after alarm; enforce **minimum segment length** `min_segment` before another candidate may start.  
- Boundary handling: no candidates with \(\hat t_c\) inside the training prefix; no use of \(t > T_1\).

### Parameter-selection budget (DEV only)

Small explicit grid (≤ 12 cells):

| Parameter | Values |
|-----------|--------|
| `train_days` | `{7, 14}` |
| `cusum_k` (allowance) | `{0.5}` fixed |
| `cusum_h` (threshold) | `{4.0, 6.0, 8.0}` |
| `min_segment_hours` | `{12, 24}` |

**Selection rule (pre-registered):** among settings with **unmatched candidates/week ≤ 3.0** on DEV, maximize **abrupt onset recall**; ties → higher overall onset recall → lower unmatched/week → larger `cusum_h`.  
Write `outputs/frozen_settings.json` **before** DIAG.

### Chronological splits (2018)

| Period | Range | Role |
|--------|-------|------|
| DEV | 2018-01-01 → 2018-06-30 23:55 | Parameter selection |
| DIAG | 2018-07-01 → 2018-12-31 23:55 | Frozen evaluation only |

2019: **not evaluated**.

---

## Event-matching rules (documented **before** results)

**Onset set:** leakages whose official `startTime` falls inside the evaluation period (abrupt and incipient reported separately).

**Match window (identification-oriented, not BattLeDIM \$ score):**  
A candidate with estimated change time \(\hat t_c\) matches an onset at \(t_0\) with end \(t_e\) if  
\[
\hat t_c \in [t_0 - 6\mathrm{h},\; \min(t_0 + 14\mathrm{d},\; t_e)].
\]  
Greedy: onsets ordered by \(t_0\); each onset and each candidate used at most once (earliest \(\hat t_c\) in window wins).

**Already-open / background leaks:** open-leak count at \(\hat t_c\) is reported; unmatched candidates are **not** automatically “false positives” (non-onset ≠ leak-free).

**Change-time error** (matched only): \(\hat t_c - t_0\) in hours (signed).

**We do not implement or claim official BattLeDIM economic scoring.**

---

## Metrics to report

- Abrupt / incipient onset recall (separate).  
- Unmatched candidates / week.  
- Candidate duration (evidence-through − \(\hat t_c\); here evidence-through = min(next candidate, \(T_1\))).  
- Duplicate burden: candidates within 24 h of another unmatched cluster (count).  
- Change-time error distribution for matches.  
- Ordinary controls: large |ΔPUMP_1| / |ΔT1| vs prior week — fraction near a candidate.  
- Wall-clock processing time and analyzed row×sensor volume.  
- Missed onsets listed explicitly.

---

## Differences from published LILA (explicit)

1. No hydraulic localization step.  
2. No manual leak-free training or per-leak pair picking.  
3. Offline CUSUM over a **completed** interval (retrospective), not online alerting.  
4. Fixed all-pairs aggregation only.  
5. No claim of paper/competition performance parity.  
6. Independent code (no GPL copy).

---

## Verification (implementation correctness)

Unit/smoke tests: interval-end bounds (no \(t>T_1\)), missing data, constant inputs → no candidates, synthetic step in \(S(t)\) recovered, reproducibility of scores given fixed settings.  
Synthetic tests **do not** measure BattLeDIM leak accuracy.
