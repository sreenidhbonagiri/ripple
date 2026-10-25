# Region construction / calibration (train + DEV only)

**Applies to:** calibrated L-Town synthetic feasibility (`hypothesis_ltown_synthetic`).  
**Does not retune:** frozen toy results under `hypothesis_synthetic/`.  
**Fit-score gaps are not probabilities** unless a calibrated probabilistic model is stated (none here).

---

## 1. Intended coverage

Among scenarios with decision **`leak`** on the **development** split where a true leak node exists and that node is in the registered candidate set:

\[
\mathbb{P}(\text{true node} \in \mathcal{R} \mid \text{detect, DEV}) \ge 1 - \alpha
\]

with **\(\alpha = 0.10\)** → **intended coverage 90%**.

If DEV has too few detects to hit 90% with any finite ε, widen ε to cover all DEV detects and record **empirical DEV coverage** (may be 100% on a small DEV) plus the **ε** chosen; test coverage is then reported separately without further widening.

---

## 2. Region definition (not a posterior)

Let \(J_c\) be the H1 objective at candidate \(c\), \(J^\star = \min_c J_c\).

\[
\mathcal{R}(\varepsilon) = \{ c : J_c \le J^\star + \varepsilon \}
\]

- \(\varepsilon \ge 0\) has units of the objective (m² head residual + regularizers).  
- \(\varepsilon\) is **not** a probability, p-value, or credible level.  
- Point estimate \(\arg\min J_c\) is reported separately from \(\mathcal{R}\).

---

## 3. Calibration procedure (train → DEV → freeze → test)

1. **Train:** smoke / optimizer sanity; may inspect ΔJ distributions; **do not** freeze ε from train alone if DEV is available.  
2. **DEV:** among DEV leak rows with `decision=leak` under the frozen detection rule (`τ_dev`, penalty), choose the **smallest** \(\varepsilon\) such that empirical coverage \(\ge 1-\alpha\).  
   - Grid: `{0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, …}` in objective units.  
3. **Freeze** \(\varepsilon^\star\) (and detection `τ_dev`) before touching test.  
4. **Test:** apply frozen rules; report metrics; **never** refit ε on test.

Detection threshold `τ_dev` (complexity margin) is also selected on DEV only (maximize TPR−FPR with penalty for forcing leak on ambiguous/demand-only rows).

---

## 4. Abstention (separate from region size)

Declare **abstain / inconclusive** when any hold (after detection scoring):

| Rule | Meaning |
|------|---------|
| Ambiguity band | \(0 < \Delta J \le \pi + \tau_{\mathrm{dev}}\) |
| Demand–leak swap | H0 δ at best node ≈ H1 q and ΔJ not clearly above clear margin |
| Uninformative region | Would detect but \(\lvert\mathcal{R}\rvert > R_{\max}\) | 
| Empty evidence | ΔJ≈0 and q̂ < q_min → **no_new_leak** (not abstain) |

Default \(R_{\max} = \lceil n_{\mathrm{cand}}/2 \rceil\). Abstention rate is reported **separately** from mean region size and coverage (coverage only among non-abstaining detects).

---

## 5. Metrics (always separate)

| Metric | Definition |
|--------|------------|
| Region size | \(\lvert\mathcal{R}\rvert\) among detects |
| Coverage | fraction of detects with true node ∈ \(\mathcal{R}\) (candidate-represented truths only) |
| Abstention rate | fraction of rows with decision `inconclusive` |
| Detection TPR/FPR | leak decision vs labels (abstain ≠ detect) |

Do not collapse these into a single “accuracy.”

---

## 6. Signature matching comparison

Tune signature \(\tau_{\lvert\sum q_v\rvert}\) on DEV. Optional signature abstention: if \(\tau_{\mathrm{lo}} < \lvert\sum q_v\rvert \le \tau\) → abstain. Choose \((\tau_{\mathrm{lo}},\tau)\) so DEV **detection FPR** and **abstention rate** are comparable to the hypothesis test before reading test.

---

## 7. Method M

Frozen temporal five-minute Method M vs isolated steady L-Town snapshots: **inapplicable**. Do not report as a head-to-head score.
