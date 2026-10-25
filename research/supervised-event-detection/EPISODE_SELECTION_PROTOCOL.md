# Episode-notification selection protocol (registered before runs)

**Experiment type:** objective-alignment correction for the synthetic pilot.  
**Not** a feature ablation. **Not** new simulations.

**Preserves:** original `outputs/pilot_*`, `PILOT_RESULTS.md`,
`TARGET_ALIGNMENT_BEFORE_ABLATION.md`, scenarios/splits/features/labels,
preprocessing procedure, L2 logistic family, and the registered
`C_GRID` / `TAU_GRID` candidate budget from `train_pilot.py`.

**Outputs (new only):** `outputs/episode_objective/`

---

## 1. Labels (unchanged — documented)

`y(t)=1` on synthetic leak scenarios for
`t ∈ [leak_start, leak_start + 6 h]` only.

This is the **registered recent-onset credit window**, **not** ongoing leak
presence. Times with the leak still open after +6 h remain `y=0`. Labels are
**not** edited in this experiment.

---

## 2. One notification pipeline (everywhere)

Identical causal semantics for synthetic DEV, synthetic test, and measured
2018 evaluation:

| Element | Rule |
|---------|------|
| Score | `q(t) = σ(z(t)·β + b)` with train-only StandardScaler |
| Notify | while inactive, first `q(t) ≥ τ` |
| Recover | after `RECOVER_STEPS=12` consecutive finite samples with `q < τ/2` |
| Missing `q` | hold; do not notify; do not advance recovery |

**Trajectory rule:** process each scenario’s **full chronological** score series
from `t=0`. Do **not** reset active/inactive state at leak onset or at credit-
window edges.

**Credit rule:** a leak scenario is a **6 h episode-notification hit** iff some
episode has `notify_idx ∈ [onset_idx, onset_idx + 6 h]` (inclusive).  
Pre-onset notifications (`notify_idx < onset_idx`) receive **no** onset credit.  
A positive label row while an episode is already active is **not** a new
detection.

---

## 3. Candidate budget (frozen; no post-hoc adds)

Identical to the original pilot:

- `C ∈ {0.01, 0.1, 1.0, 10.0, 100.0}`
- `τ ∈ {0.3, 0.5, 0.7, 0.85, 0.95}`
- Feature set: `pressure_context_v1` (all 53 features)
- One StandardScaler + logistic fit per `C` on **synthetic train** rows only

**Forbidden:** adding candidates after seeing synthetic test or measured results.

---

## 4. Synthetic DEV selection rule (declared before run)

For each `(C, τ)` evaluate on **synthetic_dev** scenarios (whole trajectories):

1. **episode_6h_recall** — fraction of leak scenarios with a notify in
   `[onset, onset+6h]` under the pipeline above.  
2. **control_episodes_per_week** — total notification episodes on control
   scenarios in the split, divided by
   `n_control_scenarios × (48 h) / (24×7)`  
   (same 48 h scenario duration as the pilot generator).  
3. **median_delay_h** — median of delays for 6 h hits (hours); missing if no hits.

**Provisional gates** (engineering; same spirit as FMR3C dual gates):

- `episode_6h_recall ≥ 2/3`  
- `control_episodes_per_week ≤ 3`

**Among candidates that pass both gates**, select by:

1. maximize `episode_6h_recall`  
2. minimize `control_episodes_per_week`  
3. minimize `median_delay_h` (missing sorts last)  
4. minimize `C`, then minimize `τ` (stability tie-break)

**Selection failure:** if **no** candidate passes both gates, report failure
honestly. Still record the full grid. For diagnostic follow-through only, freeze
the rank-best candidate **under the same ordering without requiring gates**,
with `gate_met=false` — not a claim of success.

---

## 5. Freeze and evaluate order

1. Freeze selected `{C, τ, coef, scaler}` (and `gate_met`).  
2. **Synthetic test** first (episode headline + row-credit side metrics).  
3. **Measured 2018 DEV/DIAG** diagnostically with the **same** notifier — no
   retune. Prior examination acknowledged.

Headline metrics are **episode** metrics. Row-credit metrics are reported only
to explain the original discrepancy.

---

## 6. Non-goals

- No feature ablation, new simulations, or 2019  
- No main merge, UI, Tiger, deployment  
- Original row-hit pilot remains the archived baseline  
