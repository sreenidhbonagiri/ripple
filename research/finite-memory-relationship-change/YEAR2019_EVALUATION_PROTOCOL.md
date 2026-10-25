# FMR3C frozen detector — 2019 evaluation protocol

**Status:** written and frozen **before** 2019 inference / ground-truth evaluation.  
**Preserves:** production, all prior FMR3C reports (`RESULTS.md`, empirical calibration,
transfer / matching / reference-suppression diagnoses), CUSUM-family packages.  
**Does not:** add features, retune τ, pick event-specific sensors/refs/windows, import Tiger,
merge main, change UI, or deploy.

Honesty: prior examination of 2019 SCADA and labels is acknowledged. This run is
**not** an untouched holdout. It applies a **frozen** 2018-DEV empirical threshold to a
full continuous 2019 year under the fitting-prefix rules below.

---

## 1. Frozen method (no re-selection)

| Element | Value | Source |
|---------|-------|--------|
| Signal | FMR3C on `build_signals.z` | `DESIGN.md` / empirical experiment |
| \(L_Q\) | **2 h** | `outputs/empirical_frozen.json` → `signal.l_q_hours` |
| \(L_R\) | **48 h** | same → `signal.l_r_hours` |
| \(\tau\) | **exact saved float** from `selected.tau` | same file (≈26.732944547756674; load, do not retype) |
| Train days | **14** | empirical / DESIGN |
| Refs \(K\) | **3** | empirical / DESIGN |
| Recovery | \(N_{\mathrm{rec}}=12\), clear at \(\tau/2\) | `detector.RECOVER_STEPS` |
| Normalization | train-prefix AR(1)/MAD σ only | `scale.py` |
| Reference selection | training-only RMSE+MAD ranks | `residual.select_references` |

**Forbidden:** recomputing τ from 2019 score percentiles; fitting on the full year;
event-specific references, sensors, windows, or thresholds; features aimed at p369.

---

## 2. Fitting-prefix procedure (2019)

Same rule as DEV / DIAG independent period refits (`TRANSFER_DIAGNOSIS.md`):

1. Analysis period **YEAR2019**: timestamps with  
   `2019-01-01 00:00` ≤ \(t\) ≤ `2019-12-31 23:55` (inclusive end, 5-minute grid).
2. **Fit only** on the first 14 calendar days of that period:  
   pressures in absolute indices `[g0, g0 + 14×288)` → through **2019-01-14 23:55**.
3. Documented completion markers:
   - `train_end` = `timestamps[g0 + 14×288]` = **2019-01-15 00:00**
     (first analysis index; exclusive end of the fit slice).
   - Pairwise OLS, top-3 refs, residual loc/scale, and FMR3C σ are estimated on the
     fit slice **only**, then frozen for the rest of the year.
4. Analysis residual series \(z\) starts at `train_end` (no scores during the fit slice).
5. **Warm-up:** first local analysis index with both \(Q\) and \(R\) fully inside the
   post-training span: \(t_0 = n_Q + n_R - 1\) (`windows.first_valid_t`).  
   With \(L_Q{=}2\)h, \(L_R{=}48\)h → \(n_Q{=}24\), \(n_R{=}576\) → \(t_0{=}599\) steps
   (49 h 55 min after `train_end`).
6. **Earliest eligible notification time** = `timestamps[train_end_index + t_0]`  
   (expected **2019-01-17 01:55**). Scores are NaN before this; episodes cannot notify earlier.

Ambiguity resolution (locked here, not after seeing events):

- **Primary onset set for registered matching** = labeled onsets with  
  `onset ∈ [train_end, YEAR2019.end]` (same `split_eligible_onsets` rule as 2018).  
  Warm-up does **not** remove an onset from this set: a later notify inside the type
  window may still match (identical to DEV/DIAG semantics where warm-up also exists).
- **Training/warm-up reporting bucket** (separate from primary recall denominators):
  - *training prefix:* `onset < train_end` (none expected for pure 2019-onset labels;
    carryovers are not “onsets”).
  - *warm-up span:* `train_end ≤ onset < earliest_eligible_notification`.
- **Carryover leaks:** any leakage with `start < 2019-01-01` and `end ≥ 2019-01-01`
  (open during the year). Reported for context; **not** counted as 2019 onsets.
- **p523:** previously used development / presenter example. Always listed in its own
  subsection; still participates in matching if it falls in a primary set — never
  double-counted across views.

---

## 3. Inference stage (ground truth sealed)

Order of operations:

1. Record code / config / input sha256 hashes and the exact loaded τ.  
2. Load **2019 pressures only**. Fit prefix → score continuous year → episode pipeline.  
3. Persist and hash: score bundle (finite scores), notification/episode list.  
4. **Only then** load leakages for evaluation.

No event-specific settings. No Tiger imports.

---

## 4. Evaluation stage

### 4.1 Event strata (report separately)

| Stratum | Definition |
|---------|------------|
| Post-fit abrupt | Primary eligible (`onset ≥ train_end`), type abrupt, and `onset ≥ earliest_eligible_notification` |
| Post-fit incipient | Same with type incipient |
| Training/warm-up onsets | Onsets in training prefix or warm-up span (above) |
| Carryover | Open in 2019 with 2018 (or earlier) onset |
| p523 | Dedicated line item |

Abrupt **sensitivity** uses six-hour timing (`delay ≤ 6 h`) in addition to the
registered 7-day abrupt matching window.

### 4.2 Matching views (one notification → at most one event)

| View | Role |
|------|------|
| **A** Original chronological greedy | **Registered** joint view |
| **B** Abrupt-only greedy | Secondary; abrupt sensitivity only |
| **C** Joint max-cardinality + min-sum-delay | Secondary; Hungarian |

Credit conflicts (one notify eligible for ≥2 onsets) are listed explicitly. Views never
double-credit the same episode index.

For **each** applicable view report: recall and delays; unmatched notifications/week;
duplicate unmatched-within-24h burden; sensor/network occupancy; longest and
right-censored episodes. Individual delays and misses for abrupt (and incipient under A/C).

### 4.3 Null diagnostics

Apply the **same** assignment procedure to observed and circularly shifted notifications
(`NULL_SHIFT_DAYS` as in `evaluate.py`). Report **0–2 h** and **0–6 h** post-onset
nulls (and view-A/B/C shift nulls for abrupt match counts under each view’s windows).

Do **not** headline only the most favorable view.

### 4.4 Stop rule

After writing the evaluation report: **stop**. No threshold adjustments, selective
reruns, or feature proposals in this commit.

---

## 5. Outputs

- `outputs/year2019_freeze.json` — pre-inference hashes + protocol binding  
- `outputs/year2019_inference.json` — scores/notifications hashes (pre-GT)  
- `outputs/year2019_evaluation.json` — full metrics  
- `outputs/YEAR2019_EVALUATION.md` — human report  

Candid assessment required: useful sensitivity vs manageable burden across the year,
without claiming 2019 is untouched.
