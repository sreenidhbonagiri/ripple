# Finite-memory relationship-change experiment — design (locked before implementation)

**Status:** design only. **Do not implement or run** a detector from this document yet.  
**Branch context:** research tree under Ripple; production / UI / Tiger / main untouched.  
**Product boundary:** Deployed Ripple has **no validated automatic leak detector**. Candidates below would be research episodes only.

**Related closure:** further threshold tuning of the current per-target CUSUM family is **closed** (see `../per-sensor-relationship-cusum/` results). Historical reports there remain authoritative and must not be overwritten.

---

## Question

Can **recent changes** in signed per-target relationship residuals distinguish **new** events better than **accumulated departure** from a fitted baseline (CUSUM-style debt)?

In one sentence: does a **finite-memory** recent-vs-reference contrast on the reconciled `build_signals.z` path improve useful timing / burden tradeoffs relative to unbounded accumulation on the same residuals?

---

## 1. Review of existing experiments

Sources: this repo’s research markdown/results; retrospective package as committed historically; practice scanner **documentation only** (no practice code copied; practice alert lists are **not** in this repository and must not be treated as results of Ripple).

### A. Current per-target CUSUM (`research/per-sensor-relationship-cusum`)

| Piece | What was tried |
|-------|----------------|
| Signal | Directed OLS pressure relationships; signed under-pressure residuals; per-pair normalize → median → \(z_i\) |
| Detector | One-sided sequential CUSUM on \(z_i\); notification = first \(C\ge h\); no periodic re-alarm while active |
| Variants | CUSUM-zero recovery; residual-recovery (\(z\le k\) for 12 steps); context ridge correction (**no-go**); \(h\) calibration through 16384 |
| Outcome | Limited research signal at frozen \(h{=}8\) (notification-time recall vs global); residual-recovery storms; context no-go; extended \(h\) can meet DEV dual gates at \(h{=}2048\) but **DIAG loses 6 h abrupt sensitivity** and retains high union occupancy / long episodes |

**Core failure mode for this question:** CUSUM **accumulates** positive \(z-k\). Sustained ordinary elevation latches alarms; raising \(h\) delays useful notifies. Threshold tuning of this family is closed.

### B. Prior retrospective global method (`research/retrospective-review`)

| Piece | What was tried |
|-------|----------------|
| Signal | All-pairs OLS; Frobenius-like aggregate \(S(t)\) |
| Detector | Offline CUSUM; primary time = estimated change \(\hat t_c\) (backdated), not causal notify |
| Matching | Broad \(\hat t_c\) windows including pre-onset credit |
| Outcome | **Unsuccessful** vs density-matched circular-shift nulls at ±6 h / ±24 h (`outputs/DECISION.md`); unmatched burden never met provisional gate on DEV |

**Different question:** retrospective timed identification of global residual magnitude, not causal per-target notification of signed residuals. **Preserved negative.** Not revived here.

### C. Practice two-window relationship scanner (documentation only)

Available documentation (conversation / audit notes in this project’s history — **not** vendored practice source) characterizes a separate BattLeDIM **practice** detector that compared pressure **relationships across two time windows** (reference vs recent) to flag relationship change. Live Ripple practice notes also distinguish that scanner from simpler TOD-median baselines. Practice alert lists, suppression logic, and unmatched tallies are **absent** from this repository; prior “missed abrupt” examples (e.g. p280/p710/…) are already-examined development anecdotes, **not** a holdout and **not** Ripple results.

**Do not** copy practice code, thresholds, or claim to reproduce practice outcomes.

### What would actually be new

| Claimed element | New? |
|-----------------|------|
| Signed per-target \(z_i\) from training-only refs | **No** — already built and audited in the CUSUM package |
| Unbounded / long-memory CUSUM on \(z_i\) | **No** — family closed for further \(h\) tuning |
| Global Frobenius + offline CUSUM | **No** — retrospective negative |
| Finite-memory **recent vs reference** contrast on the **same reconciled \(z_i\)**, with **causal notification-time** matching, DEV→freeze→DIAG, occupancy/null discipline from the CUSUM package | **Yes** — not implemented in this repo |
| Exact practice two-window pipeline / thresholds | **Forbidden / not new** — documentation-only; would risk silent duplication of an external approach |

**Duplication check:** This proposal is **not** another CUSUM-\(h\) search and **not** a re-run of global offline screening. It **does** share the *idea* of two-window relationship change with the practice scanner. The research novelty claim is therefore **narrow**: apply one **pre-specified** finite-memory contrast to Ripple’s existing signed per-target residual path under this repo’s evaluation protocol — **not** “two-window detection has never been tried.” If implementation collapses to re-coding practice windows/thresholds, treat that as **duplicate of a prior approach** and stop.

---

## 2. One concrete method (specification)

**Name:** Finite-Memory Recent–Reference Residual Change (FMR3C)  
**Reuse:** identical `build_signals` fits, refs \(K{=}3\), train_days\(={}\)14, and \(z_i\) construction as in the authoritative residual-recovery / calibration path (`build_signals.z`). **No** context correction. **No** leak-location sensor picking.

### 2.1 Windows (fixed lengths; selected only on DEV)

At each analysis time \(t\) (5-minute grid), after training end + warm-up:

| Window | Definition | Predeclared DEV choices |
|--------|------------|-------------------------|
| **Recent** \(Q(t)\) | \((t-L_Q,\ t]\) | \(L_Q \in \{2\,\mathrm{h},\ 6\,\mathrm{h}\}\) |
| **Reference** \(R(t)\) | \((t-L_Q-L_R,\ t-L_Q]\) (immediately before recent; **no gap**) | \(L_R \in \{24\,\mathrm{h},\ 48\,\mathrm{h}\}\) |

Warm-up: first analysis time with both windows fully inside the post-training span.  
**Forbidden:** choosing \(L_Q,L_R\) from DIAG or from known leak times.  
**Forbidden:** unbounded accumulation; **forbidden:** periodic forced re-notification while an episode is active.

### 2.2 Per-target change statistic

Let \(z_i\) be the existing signed normalized target residual (positive = under-pressure vs refs).

\[
m_i^Q(t)=\mathrm{median}\{z_i(u):u\in Q(t),\ z_i(u)\ \mathrm{finite}\}
\]
\[
m_i^R(t)=\mathrm{median}\{z_i(u):u\in R(t),\ z_i(u)\ \mathrm{finite}\}
\]
\[
\delta_i(t)=m_i^Q(t)-m_i^R(t)
\]

**One-sided leak-oriented polarity:** interest in \(\delta_i>0\) (recent under-pressure **higher** than the immediate reference window).

Require minimum finite coverage: \(\ge 80\%\) of steps in \(Q\) and in \(R\); else \(\delta_i(t)\) is **missing**.

### 2.3 Normalization accounting for temporal dependence

Sliding medians of autocorrelated \(z_i\) are **not** independent. Do **not** treat \(\mathrm{Var}(\delta)\) as \(\propto 1/n_{\mathrm{raw}}\).

**Train-only scale (frozen per target before analysis):**

1. On the training/calibration prefix only, form the same \(\delta_i(t)\) series for the chosen \((L_Q,L_R)\) wherever both windows fit inside train.  
2. Estimate lag-1 autocorrelation \(\hat\rho_i\) of training \(z_i\) (finite pairs).  
3. Effective sample size for a window of \(n\) finite points (simple AR(1) inflation, clipped):

\[
n_{\mathrm{eff}}(n,\hat\rho)=\max\bigl(2,\ n\cdot(1-\hat\rho)/(1+\hat\rho)\bigr)
\quad\text{with }\hat\rho\in[0,0.95].
\]

4. Let \(\widehat{\mathrm{MAD}}_i\) be the training MAD of \(z_i\). Define a dependence-aware scale for \(\delta\):

\[
\sigma_i = c\cdot\widehat{\mathrm{MAD}}_i\cdot
\sqrt{\frac{1}{n_{\mathrm{eff}}(n_Q,\hat\rho_i)}+\frac{1}{n_{\mathrm{eff}}(n_R,\hat\rho_i)}}
\]

with \(c=1.4826\), \(n_Q,n_R\) = design lengths in steps. If \(\sigma_i\) is tiny, mark target ineligible.

5. Standardized score:

\[
s_i(t)=\delta_i(t)/\sigma_i
\]

(missing if \(\delta_i\) missing). **No** re-estimation of \(\sigma_i\) after training end.

### 2.4 Cross-sensor aggregation

**Primary (matches prior per-sensor package):** run an independent episode process **per target** \(i\). A labeled onset may be matched by **any** target’s notification (earliest eligible), same as CUSUM experiments.

**Network summary (reported, not a second detector):** at each \(t\), count how many eligible sensors have \(s_i(t)\ge\tau\) (active-sensor distribution / union occupancy use the same episode occupancy tools as before).

No leak-location-weighted fusion; no “nearest sensor to pipe” rules.

### 2.5 Missing-data behavior

| Case | Behavior |
|------|----------|
| \(z_i\) missing at a step inside \(Q\) or \(R\) | Exclude from that window’s median; coverage fraction still required |
| \(\delta_i\) / \(s_i\) missing at \(t\) | Do **not** notify; do **not** count toward recovery; hold active/inactive state |
| Target ineligible (\(\sigma_i\) undefined) | No episodes for that sensor |

### 2.6 Notification / recovery semantics

| Element | Rule |
|---------|------|
| Threshold \(\tau\) | DEV grid only: \(\{3,4,5,6\}\) (units of \(s_i\)) |
| **Notify** | First \(t\) with finite \(s_i(t)\ge\tau\) while **inactive** |
| Active episode | Remains active; **no** new notify while active |
| **Recovery** | \(N_{\mathrm{rec}}\) consecutive finite steps with \(s_i(t)<\tau_{\mathrm{clear}}\) where \(\tau_{\mathrm{clear}}=\tau/2\); default \(N_{\mathrm{rec}}=12\) (1 h) — **not** swept in the first run |
| Rearm | Only after recovery |
| Period end | Right-censor active episodes |
| Change estimate | Optional: start of recent window or first \(s\ge\tau\) — **diagnostic only**, not primary match time |

**Why this addresses latching:** when a level shift becomes common to **both** \(Q\) and \(R\), \(\delta_i\to 0\) and \(s_i\) falls — finite memory **forgets** a completed step change without requiring CUSUM return-to-zero. Abrupt **new** changes that affect \(Q\) but not yet \(R\) elevate \(\delta_i\).

**Forbidden:** resetting on a wall-clock schedule to mint duplicate notifications from one sustained condition.

### 2.7 Sensitivity (qualitative — to be tested, not assumed solved)

| Stress | Expected behavior |
|--------|-------------------|
| **Slow / incipient leaks** | If the rise is shared across \(Q\) and \(R\), \(\delta\) stays small → **reduced** sensitivity vs CUSUM (acceptable for the “new event” question; report incipient separately) |
| **Demand / diurnal shifts** | \(L_R{=}24\mathrm{h}\) aligns seasonality better than short refs; residual TOD mismatch can still spur \(\delta\). Context correction is **out of scope** for this first experiment |
| **Affected references** | Same structural risk as CUSUM: disturbed refs bias \(e_{ij}\) and \(z_i\); finite memory does not remove that |
| **Common-mode pressure drop** | Target and refs move together → \(z_i\) small → \(\delta\) small → **suppressed** signal (document; do not claim solved) |

---

## 3. Evaluation protocol (before implementation)

### Splits and honesty

| Period | Role |
|--------|------|
| DEV 2018 H1 | Selection only |
| DIAG 2018 H2 | **Once**, after freeze |
| 2019 | **Not** evaluated |

**Prior exposure (explicit):** DIAG labels, CUSUM results, residual-recovery / context / \(h\)-calibration outcomes, retrospective DECISION, and practice-scanner anecdotes have all been examined. DIAG findings are **diagnostic**, not a blind holdout.

### Selection (DEV)

Small predeclared grid (≤ 16 cells): \(L_Q\times L_R\times\tau\) with \(N_{\mathrm{rec}}\) fixed.

**Dual gates (provisional research targets — not operator-validated):**

1. Abrupt **6 h** notification recall \(\ge 2/3\) on eligible DEV abrupt onsets.  
2. Unmatched notifications/week \(\le 3\).

Among settings meeting both **and** not showing latched-only success (union occupancy \(\ge 90\%\) with low unmatched, or majority right-censored ultra-long episodes): maximize 6 h abrupt recall → minimize median delay → minimize unmatched/week.  
If none qualify → **selection failure**; do not silently enlarge the grid; do not invent a winner; **do not** run DIAG under a new setting.

### DIAG (only if frozen)

Same metrics as the CUSUM package:

- Abrupt / incipient recall; delays; **all** event notification times  
- Unmatched/week; duplicate unmatched within 24 h  
- Sensor-alarm %; network union occupancy; active-sensor distribution  
- Median / longest episode; right-censored count  
- Training-prefix events **separate**  
- Existing **0–2 h** notification-time circular-shift null (descriptive)  
- No broad-window headline as success; no already-active-at-onset credit  

### What would distinguish this from “more candidates”

A useful positive would show, **relative to the closed CUSUM family on the same \(z_i\)**, **jointly**:

1. Competitive **useful** abrupt timing (6 h recall not collapsed on DIAG), **and**  
2. Materially **lower** unmatched burden **and/or** union / sensor occupancy **without** relying on latched episodes, **and**  
3. Notification-time null not explained away by density alone (frac shifts ≥ obs not ≈ 1 when obs > 0).

Generating denser notifications that match by chance, or thinning alerts only by staying latched, is **failure** — same bar used when closing CUSUM \(h\) tuning.

---

## 4. Feasibility recommendation

| Assumption | Can 2018 DEV/DIAG test it? |
|------------|----------------------------|
| Finite-memory \(\delta\) clears after step changes enter the reference window | **Yes** — episode length / censoring / occupancy vs CUSUM |
| New abrupt events elevate recent vs reference medians of \(z_i\) | **Partially** — few abrupt onsets; descriptive only |
| Dependence-aware \(\sigma_i\) yields comparable scales across sensors | **Partially** — train-only; may mis-scale nonstationary DIAG seasons |
| Method beats chance timing | **Weakly** — small \(n\); null is descriptive |
| Operational workload acceptable to utilities | **No** — provisional ≤3/wk is research-only |
| Practice scanner performance parity | **No** — practice artifacts not in repo; not a goal |
| 2019 generalization | **Not tested** (by design) |
| Common-mode / affected-ref / demand robustness | **Document failure modes**; not separately identifiable as “solved” |

### Recommendation

**Conditionally feasible as one next research experiment** after closing CUSUM-\(h\) tuning: the question is distinct (finite memory vs accumulation on the **same** residual path), evaluation discipline already exists, and the method is fully specified without further parameter fishing.

**Not** a claim that the method will work.  
**Not** a license to re-tune CUSUM \(h\).  
**Not** a reproduction of the practice two-window scanner.  
**Stop** if implementation drifts into copying practice code or into another unbounded accumulator.

**Next step when authorized:** implement FMR3C only as specified here; run DEV grid → freeze or record failure → optional one DIAG; leave all prior reports untouched.

---

## Non-goals (this design package)

- No parameter runs, plots, or frozen settings yet  
- No 2019 evaluation  
- No UI, database, Tiger imports, deployment, or main merge  
- No further CUSUM family threshold / recovery / context search  
