# Target / objective alignment audit — before change-only ablation

Generated: 2026-10-24 (audit of frozen pilot artifacts; no new fit)

**Decision: STOP.** Do **not** run the change-only feature ablation under the
claim of a feature-only experiment. Targets/objectives are misaligned with the
measured six-hour **notification** metric. Quietly changing labels would violate
the ablation contract; proceeding without fixing alignment would re-select on the
wrong synthetic objective.

Preserves original frozen model, predictions, `PILOT_RESULTS.md`, and production.

---

## 1. Exact positive labels (synthetic)

For every successful `leak_abrupt` scenario:

\[
y(t)=1 \iff t \in [t_{\mathrm{leak\_start}},\ t_{\mathrm{leak\_start}}+6\,\mathrm{h}]
\]

on the 5-minute grid (`STEP_SECONDS=300`). Documented in `simulate.py`
(`labels_abrupt_positive`).

| Fact | Value (pilot, all 24 leak scenarios) |
|------|--------------------------------------|
| Positive duration | **exactly 72 steps (6.0 h)** every scenario |
| Leak open duration | mean **~9.3 h** (area/end sampled longer than 6 h) |
| Steps with leak **open but y=0** | mean **71** per scenario; **100%** of leak scenarios have such steps |

So positives are **not** “leak present for the whole event.” After the first 6 h,
the leak often remains hydraulically open while labels flip to **negative**.

**Interpretation:** the supervised target is a **fixed 6 h post-onset credit
block** (early presence / credit window), **not**:

- a pure single-onset impulse, and  
- not ongoing leak presence until repair.

The classifier is trained to score rows inside that block vs everything else
(pre-leak, post-credit-while-still-leaking, and control scenarios).

### Control scenarios

All timestamps after warm-up are **y=0** (no positive credit). Negatives are
**not** certified leak-free measured network states; they are synthetic
no-new-leak controls plus non-credit times in leak scenarios.

---

## 2. What synthetic selection optimizes

Frozen protocol (`train_pilot.py`):

1. Fit L2 logistic on **row-level** `(X, y)`.  
2. On `synthetic_dev`, choose `(C, τ)` by maximizing:

   - **scenario_recall** = fraction of leak scenarios with **≥1 row** satisfying  
     `q(t) ≥ τ` **and** `y(t)=1`  
   - then row_recall, then min fp_row_rate  

This is a **row-hit inside the 6 h credit window**. It does **not**:

- run the episode / recovery notifier,  
- require `notify_time ∈ [onset, onset+6h]`,  
- penalize pre-onset latching that blocks a new notify at onset.

---

## 3. Measured six-hour objective (unchanged)

On measured 2018 DEV/DIAG (`evaluate_measured.py` / FMR3C-compatible matching):

1. Score continuous `q(t)`.  
2. Form episodes: notify when `q≥τ` while inactive; recover after 12 steps below `τ/2`.  
3. **Abrupt 6 h recall** = matched if some episode’s **notification time** lies in  
   `[onset, onset+6h]` (one-to-one greedy matching).

That is a **notification-time** criterion, not row-level credit-window hit rate.

---

## 4. Empirical disagreement on the frozen pilot

Same frozen model (`pilot_frozen_model.json`), synthetic_test leak scenarios (n=15):

| Metric | Value |
|--------|-------|
| Row-credit scenario recall (selection-style) | **0.867** (13/15) |
| Episode notify within 6 h of onset | **0.200** (3/15) |
| Scenarios where row-hit ≠ notify-6h | **10 / 15** |

Typical disagreement: `q` exceeds τ somewhere in the credit window (row-hit), but
episode notifies are **outside** `[onset, onset+6h]` (often earlier in the
trajectory, so the stream is already active or the first post-onset crossing is
late). Example: `leak_000_p282` — row-hit True, notifies at indices 165 and 458,
onset 341 → no notify in the 6 h onset window.

**Conclusion:** synthetic selection **does not reward the same six-hour
notification objective** used on measured data. High synthetic scenario_recall
in `PILOT_RESULTS.md` is therefore **not** evidence of synthetic 6 h
notification sensitivity under measured rules.

---

## 5. Onset vs ongoing presence

| Question | Answer for this pilot |
|----------|------------------------|
| Learns full ongoing leak presence? | **No** — post-credit open-leak times are labeled negative. |
| Learns a sharp onset-only event? | **No** — all 72 credit steps are equally positive. |
| Learns “early post-onset window / credit state”? | **Yes** — that is the literal target. |

A change-only feature ablation that keeps these labels and this selection rule
would still optimize row-hits in a 6 h credit block, not measured-style
notification delays.

---

## 6. Stop rule application

Per the ablation request:

> If targets/objectives are misaligned, stop and report the mismatch.  
> Do not quietly change labels while calling this a feature-only ablation.

**Misalignment found** between:

1. Label semantics (6 h credit block; open-leak negatives after 6 h), and  
2. Synthetic selection (row-hit in credit window), vs  
3. Measured evaluation (episode notification ≤ 6 h after onset).

**Actions taken:** report only. **No** change-only fit, **no** label edit, **no**
threshold retune, **no** new simulations, **no** 2019.

### What a later aligned experiment would need (out of scope here)

Register **before** fitting, explicitly — not as a silent patch inside a
“feature-only” ablation — one of:

- Selection metric = episode notify-in-6h on synthetic_dev (same notifier as
  measured), **or**  
- Labels redesigned to match the chosen objective (e.g. onset-centered), with
  a new registered protocol.

Until then, feature ablation under the current protocol would not answer whether
removing absolute levels improves **measured 6 h notification** transfer.

---

## Non-goals

- Original pilot artifacts untouched as the registered baseline  
- No main merge, UI, Tiger, deployment, or 2019 evaluation  
