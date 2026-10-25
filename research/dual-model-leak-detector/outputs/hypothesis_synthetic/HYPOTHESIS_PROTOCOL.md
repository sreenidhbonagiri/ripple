# Uncertainty-aware hydraulic leak hypothesis testing — protocol

**Branch:** `research/uncertainty-aware-hypothesis`  
**Stage:** synthetic feasibility only (stop for review before measured evaluation)  
**Calibration lineage:** corrected frozen calibration sha256 `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
**Pump boundary (when applicable):** measured-PUMP_1 dual path from existing research (synthetic pump–tank analogue here)  
**Preserved:** deployed five-minute Method M on `main` / production — this branch does not merge, deploy, or retune Method M.

This document is written **before** any measured-event or 2019 evaluation.

---

## 1. Objective

Compare two nested hydraulic explanations of the same observations:

| Hypothesis | Meaning |
|------------|---------|
| **H0** | No *new* leak. Observations explained by constrained demand uncertainty plus a bounded background model discrepancy. |
| **H1** | Identical nuisance assumptions as H0, plus a **nonnegative** candidate leak discharge at one candidate node. |

Report **discrimination**, **control burden**, **localization error**, **candidate-region size/coverage**, and **inconclusive rate**.  
Do **not** treat a lower residual alone as proof of a leak. Do **not** report only exact-match accuracy under a perfect model.

---

## 2. Observation model

Synthetic primal EPANET simulations produce sensor heads \(h^{\mathrm{obs}}\) (absolute hydraulic head, m). Optional additive Gaussian sensor noise is applied to heads after the primal run.

Fitting predicts heads \(h(\theta)\) from a **primal** model with parameters \(\theta\) (not dual virtual flows). Dual-model signature matching and a Method M–style score are **baselines only**, run on the same scenarios for comparable tasks.

---

## 3. Nuisance parameters (identical under H0 and H1)

| Symbol | Role | Constraint |
|--------|------|------------|
| \(\delta_j\) | Additive demand adjustment at junction \(j\) (m³/h) | \(\delta_j \in [\delta_{\min},\delta_{\max}]\) |
| \(\rho\) | Global pipe roughness scale | \(\rho \in [\rho_{\min},\rho_{\max}]\) |

Defaults for synthetic feasibility: \(\delta \in [-3,+3]\) m³/h, \(\rho \in [0.92, 1.08]\).

**Hard rule:** H1 does **not** receive wider demand or roughness bounds than H0. No extra demand nodes, no larger \(\|\delta\|_\infty\), no freer \(\rho\).

---

## 4. Leak parameter (H1 only)

| Symbol | Role | Constraint |
|--------|------|------------|
| \(q_c \ge 0\) | Candidate leak discharge (m³/h) at node \(c\) | Nonnegative; upper bound \(q_{\max}\) (synthetic default 12 m³/h) |

Leak is injected as a demand-driven outflow (same convention as existing synthetic dual verification).

---

## 5. Objective (fit) and regularization

Weighted squared head residual plus ridge on nuisances:

\[
J(\theta) = \sum_{s \in \mathcal{S}} \left(h_s(\theta) - h^{\mathrm{obs}}_s\right)^2
  + \lambda_\delta \sum_j \delta_j^2
  + \lambda_\rho (\rho - 1)^2
\]

Defaults: \(\lambda_\delta = 10^{-3}\), \(\lambda_\rho = 10^{-2}\) (mild; do not absorb leaks into unbounded demand).

H0 minimizes \(J\) over \((\delta,\rho)\).  
H1 minimizes \(J\) over \((\delta,\rho,q_c)\) for each candidate \(c\), then takes the best \(c\).

---

## 6. Complexity penalty (leak vs no-leak)

Better fit is **not** sufficient. Prefer H1 only if the improvement exceeds a complexity penalty for the extra leak degree of freedom:

\[
\Delta J = J_{\mathrm{H0}} - J_{\mathrm{H1}}^\star
\]

\[
\text{prefer H1 iff } \Delta J > \pi + \tau_{\mathrm{dev}}
\quad\text{and}\quad
\hat q_{c^\star} \ge q_{\min}
\]

- \(\pi = \pi_0 \cdot n_{\mathrm{sensors}}\) — synthetic default \(\pi_0 = 0.05\) m² (head² units).  
- \(\tau_{\mathrm{dev}}\) — margin selected on the **development** scenario split only (grid search); frozen before test.  
- \(q_{\min}\) — synthetic default 0.25 m³/h (ignore numerical dust).

If the rule fails → decision is **no_new_leak** (H0) or **inconclusive** (below).

---

## 7. Leak-versus-demand identifiability (explicit)

At a single junction, an unmeasured demand increase and a demand-driven leak of the same discharge produce **the same** primal head field under this network model. Therefore:

1. H0 can move \(\delta_j\) within bounds; H1 can place \(q_c\) at the same node.  
2. When truth is “extra customer demand” inside the demand box, H0 and H1 achieve nearly equal \(J\) → the method must return **inconclusive** (or no_new_leak), **not** a forced leak location.  
3. When truth is a leak **outside** what demand regularization prefers (e.g. leak at a node while demand ridge keeps \(\delta\) small, or leak magnitude beyond cheap \(\delta\) tradeoffs under the penalty), H1 may win — still reported with a **candidate region**, not a single forced pipe claim.  
4. Dual signature \(\sum q_v\) **cannot** resolve this confound either (documented in prior synthetic verification: `demand_mismatch_no_leak`). That limitation is a feature of the physics, not a bug to “fit away.”

---

## 8. Candidate generation (no evaluation leak locations)

Candidate nodes are fixed from **topology + sensor layout** before scenario truths are applied:

- Branched three-sensor net: `{J1, J2, J3}` (all junctions).  
- Pump–tank analogue: `{J1, J2}` (sensor junctions).

Evaluation leak locations may coincide with candidates by chance; candidates are **not** chosen by peeking at the evaluation leak set. No BattLeDIM pipe IDs are used at this stage.

**Candidate region** after a detect decision: all candidates \(c\) with

\[
J_{\mathrm{H1}}(c) \le J_{\mathrm{H1}}^\star + \varepsilon_{\mathrm{region}}
\]

(\(\varepsilon_{\mathrm{region}} = 0.02\) m² default). Region size = count; coverage = 1 if true leak node ∈ region (leak scenarios), else 0.

---

## 9. Inconclusive admissions

Declare **inconclusive** when any hold:

1. **Ambiguity band:** \(0 < \Delta J \le \pi + \tau_{\mathrm{dev}}\) (improvement neither clearly null nor clearly leak).  
2. **Demand–leak swap:** best H1 node \(c^\star\) has \(\hat q_{c^\star} > 0\) but H0’s \(\hat\delta_{c^\star}\) absorbs nearly the same mass (\(|\hat\delta_{c^\star} - \hat q_{c^\star}|\) small **and** \(\Delta J\) below a stricter clear-leak margin).  
3. **Uninformative region:** detect would fire but region size \(\ge\) half of all candidates **and** \(\Delta J\) only marginally above threshold (localization not identifiable).

Near-null cases (\(\Delta J \approx 0\) and \(\hat q < q_{\min}\)) resolve to **no_new_leak** (H0), not inconclusive.

Inconclusive is a valid outcome; forcing a location is a protocol violation.

---

## 10. Synthetic scenario factors

Matched leak / no-leak pairs under:

| Factor | No-leak control | Leak case |
|--------|-----------------|-----------|
| Nominal match | model = truth | leak + matched nuisances |
| Demand variation | truth demand scale / node bump inside or near bounds | leak + demand variation |
| Pump/tank transition | measured-PUMP_1–like synthetic, matched BC | leak coincident with transition window (snapshot) |
| Sensor noise | i.i.d. head noise | leak + noise |
| Model mismatch | roughness scale error in truth vs nominal template | leak + roughness error |
| Indistinguishable | customer demand bump ≡ leak at same node | (control) must admit ambiguity |

---

## 11. Train / development / test (whole scenario)

Splits assign **entire scenario IDs** (all replicates of that ID) to one split — no leaking samples across splits.

| Split | Role | Scenario IDs (synthetic feasibility) |
|-------|------|--------------------------------------|
| **train** | Sanity / optimizer smoke; not used for threshold cherry-picking on test | `nl_nominal`, `leak_nominal_J3`, `nl_demand_scale` |
| **dev** | Select \(\tau_{\mathrm{dev}}\) on a small grid | `nl_noise`, `leak_noise_J3`, `ambiguous_demand_J1`, `nl_roughness` |
| **test** | Frozen metrics | `leak_demand_var_J2`, `nl_pump_transition`, `leak_pump_J1`, `leak_roughness_J3`, `nl_demand_node_J1` |

Replicates: multiple seeds per ID where noise or stochasticity applies; all replicates of an ID stay in that ID’s split.

---

## 12. Baselines (comparable tasks only)

| Baseline | Task | Score |
|----------|------|-------|
| **Signature matching** | Dual model, baseline demands, VR heads = observed; detect if \(\lvert\sum q_v\rvert > \tau_{\mathrm{sig}}\) (τ from dev); localize \(\arg\max_s \lvert q_{v,s}\rvert\) | Prior synthetic dual mechanism |
| **Frozen Method M (style)** | On scenarios with a reference window: \(\max_s \lvert \delta_s / \sigma_s \rvert / \mathrm{median}(\mathrm{SCALE})\) with five-minute Method M freeze constants where a series exists; for **steady** snapshots, use \(\lvert\sum q_v\rvert / \sigma_{\mathrm{floor}}\) as a one-shot analogue | Comparable only as “anomaly vs control,” **not** as BattLeDIM 2018 operating-point transfer |

Neither baseline is retuned on measured 2019. Method M product freeze (\(\tau=4.517\), cal `5fab3acb…`) remains untouched.

---

## 13. Metrics (test split)

1. **Detection discrimination** — TPR on leak scenarios vs FPR on no-leak controls; optional ROC-style sweep on \(\Delta J\) for the hypothesis test.  
2. **Control burden** — FPR and rate of non-inconclusive false detects on no-leak controls.  
3. **Localization error** — among detected leak scenarios with a true node: fraction wrong \(\arg\min J_{\mathrm{H1}}\); hop proxy = 0 if correct else 1 on this tiny graph.  
4. **Candidate-region size / coverage** — mean region size; coverage of true node when a leak exists.  
5. **Inconclusive rate** — overall and on the ambiguous family specifically (expect high).  

**Forbidden as sole headline:** exact-match localization accuracy under perfect-model leak-only cases.

---

## 14. Out of scope this stage

- Measured SCADA / 2018–2019 event tuning  
- Merge to `main`, Tiger evidence, UI, deployment  
- Giving H1 extra nuisance flexibility  
- Claiming leak proof from fit alone  

---

## 15. Pass bar for synthetic feasibility (review gate)

Stage is **successful for review** if:

1. Clear matched leaks can beat H0 after penalty more often than chance.  
2. Nominal / noise no-leak controls do not all false-trigger.  
3. Ambiguous demand-vs-leak scenarios show **elevated inconclusive** (or H0), not confident wrong localizations.  
4. Metrics table includes discrimination, burden, region size/coverage, inconclusive — not only exact match.  
5. Baselines run on the same test IDs for side-by-side comparison.
