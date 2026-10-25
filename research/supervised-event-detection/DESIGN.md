# Supervised multivariate event detection — design only (no fits)

**Status:** design registered. A **bounded synthetic-trained pilot** was authorized
and implemented separately (`run_pilot.py`, `outputs/PILOT_RESULTS.md`). This
document remains the protocol reference; the pilot must not expand the §8 budget.  
**Preserves:** frozen FMR3C detector and all of its registered reports; production;
Tiger unused.  
**Development year:** **2018 only**. **2019 is sealed** for this experiment’s
training, tuning, thresholding, and model selection (may be reserved later as a
frozen apply-once evaluation under a separate protocol).

---

## 1. Question

Do **causal multivariate temporal features** (pressures + external flows + pump
transfer + tank) distinguish **new leak-related changes** from **ordinary
operating changes** better than **residual-threshold** detectors (including
frozen FMR3C), when evaluated as **continuous notifications** with delays,
unmatched burden, occupancy, and density-matched nulls?

Window-level classification accuracy alone is **not** success.

---

## 2. Held identical / forbidden

| Allowed | Forbidden |
|---------|-----------|
| Causal SCADA at times ≤ \(t\) | Future observations at any feature or label construction step |
| Network-wide pressure sensors (all 33) | True leak pipe / nearest-sensor selection / location weights |
| External inflows (`p227`, `p235`), `PUMP_1`, tank `T1` | Fitting or selecting on 2019 |
| Frozen FMR3C as a **baseline** (replay scores/episodes) | Changing FMR3C τ, windows, refs, or recovery |
| One simple regularized classifier + explicit baselines | Large model zoo / nested hyperparameter sweeps beyond budget (§8) |

---

## 3. Tasks (separate)

Two **separate** tasks; never pool labels into one “any leak” head for selection.

### 3.1 Abrupt task

- **Positive event:** labeled abrupt onset in 2018 with onset ≥ period fitting
  prefix end (same 14-day prefix rule as FMR3C periods).  
- **Detection credit:** notification in \([t_0,\ t_0+\Delta]\) with primary
  \(\Delta=6\,\mathrm{h}\) sensitivity (also report 2 h and registered 7 d).  
- **Unit of analysis for validation groups:** the **entire leak event** (one
  onset id), not 5-minute rows.

### 3.2 Incipient task

- **Positive event:** labeled incipient onset (post-prefix) in 2018.  
- **Credit window:** \([t_0,\ \min(t_0+14\,\mathrm{d},\ \mathrm{peak},\ \mathrm{end})]\)
  (same spirit as registered FMR3C incipient matching).  
- **Separate** metrics and selection; do not optimize abrupt thresholds on
  incipient recall or vice versa.

Carryover / already-open background leaks are **not** new positives; they
contaminate negatives (see §6).

---

## 4. Features (causal sketch)

All features use only measurements with timestamps ≤ decision time \(t\).
No leak labels enter features.

### 4.1 Pressure block

- Per-sensor pressure \(P_i(t)\) and short causal deltas (e.g. 5 min, 30 min, 2 h
  median change) — **network vector**, not a single “nearest” sensor.  
- Optional: frozen pairwise residual \(z_i(t)\) and FMR3C score \(s_i(t)\) as
  **input features** to the classifier (coefficients frozen from the period’s
  14-day prefix; τ not used inside the feature). Treating \(s_i\) as a feature is
  allowed; **re-tuning τ is not**.

### 4.2 External flow / pump / tank

Aligned 2018 Flows / Levels (same BattLeDIM CSV conventions as
`per-sensor-relationship-cusum`):

| Family | Examples (causal) |
|--------|-------------------|
| External inflows | `p227`, `p235` levels and short deltas |
| Pump transfer | `PUMP_1`, `1\{PUMP_1>\varepsilon\}`, short deltas |
| Tank | `T1`, \(\Delta T1\) over 5 min / 30 min / 2 h |
| Calendar (optional, weak) | \(\sin/\cos\) time-of-day; weekend flag |

Document units and alignment hashes at run time. Do not claim causal
identification of leak physics from coefficients.

### 4.3 Aggregation for a decision time

At each candidate decision time (5-minute grid after warm-up), form a fixed
dimension vector via **pre-declared** summaries (e.g. sensor-wise percentiles /
top-k magnitudes of pressure deltas and \(s_i\), plus context scalars). Exact
dimension list is frozen in the run protocol **before** fold fitting; fold-wise
**selection among that list** is allowed only inside training folds (§7).

---

## 5. Model and baselines (small, explicit)

### 5.1 Primary model (one)

**L2-regularized logistic regression** (or equivalent linear model with
probabilistic scores) on the feature vector at \(t\), with class weights or
intercept-only calibration **fit inside the training fold only**.

Output: score \(q(t)\). Notifications via a single threshold \(\tau_q\) chosen
on training-fold continuous metrics only (budgeted grid, §8), then frozen for
that fold’s validation apply. Episode semantics mirror FMR3C recovery
(\(N_{\mathrm{rec}}=12\), clear at \(\tau_q/2\)) unless a pre-registered simpler
hysteresis is documented before runs — **not** swept freely.

### 5.2 Baselines (required comparisons)

1. **Frozen FMR3C** (LQ=2h, LR=48h, τ from `empirical_frozen.json`) — residual
   threshold path.  
2. **Context-free residual magnitude** — e.g. max\(|z_i|\) or max \(s_i\) with a
   train-fold threshold (same notification wrapper).  
3. **Context-only linear score** — logistic / ridge on pump+tank+inflow+tod
   features **without** pressure residuals (negative control: operating change
   detector).  
4. **Intercept / rate-matched null** — notifications with the same empirical
   intensity process as the model (density-matched), for null diagnostics.

No deep nets, boosting ensembles, or large discrete architecture search in v1.

---

## 6. Labels, background leaks, negative uncertainty

- **Positives** are tied to official labeled **new onsets** (task-specific).  
- **Background / carryover leaks** open during a window make “negative” times
  **uncertain**: the network is not leak-free. Negatives are therefore
  **operational ordinary-change proxies**, not proven leak-absence.  
- Report fraction of negative candidate times with ≥1 open labeled leak.  
- Do not treat high negative accuracy as proof of leak specificity.  
- Ambiguous windows (onset ± purge radius overlapping another onset or heavy
  overlapping credit windows) are **excluded from training labels** and listed.

---

## 7. Validation protocol (no random 5-minute splits)

### 7.1 Grouping

- **Event groups:** each labeled leak onset is one group for leave-group-out /
  blocked CV on the **positive** side.  
- **Time blocks:** contiguous multi-day blocks for ordinary operating stretches
  (negatives), cut so that feature windows and label credit windows do not
  straddle train/validation.

### 7.2 Purge

Between any train and validation split, **purge** a buffer of at least
\(\max(L_{\mathrm{feature}}, L_{\mathrm{credit}})\) (pre-declare; suggested
≥ 48 h feature memory + task credit horizon) so overlapping feature/label
windows never appear on both sides.

### 7.3 Nested fitting

Inside each training fold only:

1. Imputation / standardization  
2. Optional univariate or L1 screening among the **pre-declared** feature list  
3. Classifier regularization strength (budgeted)  
4. Notification threshold on **continuous** train-fold metrics  

Validation fold: apply frozen fold pipeline once. **Never** randomly shuffle
5-minute rows into IID folds.

### 7.4 Development partitions (2018)

Mirror existing research honesty:

- **DEV** (2018 H1) for model development and the selection budget.  
- **DIAG** (2018 H2) as a **diagnostic** apply-once under frozen DEV choices —
  prior examination acknowledged; not an untouched holdout.  
- **2019:** not used for train/tune/select under this design.

---

## 8. Training / selection budget and failure criteria

### 8.1 Budget (hard caps)

| Knob | Cap |
|------|-----|
| Classifier family | **1** (L2 logistic) |
| Regularization grid | ≤ **5** values |
| Notification τ grid | ≤ **5** values per task |
| Feature-list variants | ≤ **3** pre-declared sets (full / no-calendar / pressure+residual-only) |
| Outer event-group folds (DEV) | ≤ leave-one-**abrupt**-event-out and separate leave-one-**incipient**-event-out (or blocked equivalent if events < 5) |
| Seeds | **1** (deterministic) |

If a proposed analysis exceeds this budget, **stop** and redesign — do not
quietly expand search.

### 8.2 Primary continuous metrics (selection)

For each task, on each validation fold / DIAG apply:

- Recall at 6 h (abrupt) or within incipient credit window  
- Individual delays and misses  
- Unmatched notifications / week  
- Duplicate unmatched within 24 h  
- Sensor and union occupancy; longest / right-censored episodes  
- Density-matched / shift nulls on the **same** matching view as the registered
  comparison (joint chronological greedy as headline; abrupt-only secondary)

**Do not** select on window ROC/AUC alone.

### 8.3 Failure criteria (pre-declared)

Declare **failure / no-go** if any of:

1. **Sample inadequacy (§9):** independent event count too small for stable
   selection under the budget → stop before claiming superiority.  
2. **No clear gain:** DEV event-grouped validation does not improve abrupt 6 h
   recall vs frozen FMR3C at unmatched/wk ≤ 3 without latching, **or** improves
   recall only by inflating unmatched/wk above 3.  
3. **Context-only wins:** context-only baseline matches the multivariate model on
   continuous metrics → evidence favors operating-change detection, not leak
   change detection.  
4. **DIAG collapse:** DEV-selected rule loses abrupt 6 h usefulness on DIAG
   under the same provisional bar (recall < 2/3 with unmatched/wk ≤ 3), without
   a pre-registered rescue path.  
5. **Budget breach** or leakage of 2019 into selection.

Success requires beating residual-threshold baselines on **continuous** metrics
with manageable burden — not a narrative win on a single missed pipe.

---

## 9. Feasibility: independent event count (2018)

Official BattLeDIM labels in `leakages_2018_2019.json` with onset in 2018:

| Type | Pipes (onset year 2018) | Count |
|------|-------------------------|-------|
| Abrupt | p673, p538, p866, p183, p158, p369 | **6** |
| Incipient | p257, p461, p232, p427, p628, p31, p810, p654 | **8** |
| **Total independent onsets** | | **14** |

After 14-day fitting prefixes per DEV/DIAG period, several onsets fall in
prefix or straddle partitions (e.g. early-January / early-July). Effective
**post-prefix abrupt events available for grouped CV on DEV alone** are on the
order of **~3**, and DIAG abrupt post-prefix **~3** — far below a comfortable
model-selection sample.

**Assessment:** the measured 2018 benchmark **does not** support meaningful
multi-knob supervised model selection for abrupt detection with event-grouped
purged CV. Incipient counts are similarly tight once prefixes and long credit
windows / purge are respected. A design-compliant run may still **document**
baselines and a single pre-registered classifier setting, but **must not** claim
robust hyperparameter selection from these 14 events.

### 9.1 If event count is inadequate — synthetic supplement (allowed design path)

Independently generated **hydraulic scenarios** (simulation / EPANET-class
ensembles with known leak injections and ordinary demand/pump schedules) may
**supplement training** under these rules:

1. **Train / select** on synthetic + optionally a frozen tiny measured DEV
   protocol — but **report synthetic metrics separately** from measured-benchmark
   metrics.  
2. **Never** mix synthetic and measured rows in one unlabeled pool for a single
   headline score.  
3. Measured 2018 DIAG (and later 2019, under a separate freeze) remain
   **apply-once** benchmarks; synthetic gains do not replace them.  
4. Scenario generators must not be tuned against measured 2019.  
5. Domain shift (sim ↔ SCADA) is a first-class risk; include a context-only and
   FMR3C baseline on both domains.

Without such supplementation, the honest outcome of this design is likely
**feasibility failure on selection**, not a trained production detector.

---

## 10. Evaluation outputs (when a future run is authorized)

- Continuous notification lists and episode occupancy (same style as FMR3C
  reports)  
- Per-event delays / misses for abrupt and incipient  
- Unmatched/week, duplicates, occupancy  
- Nulls **per matching view and eligible set** (apply the 2019 null-correction
  discipline from the start)  
- Explicit comparison table vs frozen FMR3C and baselines  
- Independent event counts actually used per fold  

Stop after design until an explicit “fit models” instruction.

---

## 11. Non-goals

- No production / UI / Tiger / main merge  
- No FMR3C retune or feature addition inside the frozen detector  
- No training or tuning on 2019  
- No fitting under this commit
