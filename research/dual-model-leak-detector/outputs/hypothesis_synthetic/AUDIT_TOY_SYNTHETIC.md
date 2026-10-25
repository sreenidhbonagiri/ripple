# Audit — frozen toy synthetic feasibility (do not retune)

**Preserved artifact:** `synthetic_feasibility_results.json` / `SYNTHETIC_FEASIBILITY_RESULTS.md`  
**Commit at freeze:** `69e940d`  
**This audit does not change decisions, thresholds, or metrics on that run.**

---

## 1. Exact counts behind every reported metric

### Row inventory (16 rows total)

| Split | Scenario IDs × seeds | Rows | Leak rows | Control rows |
|-------|----------------------|-----:|----------:|-------------:|
| train | `nl_nominal`×1, `leak_nominal_J3`×1, `nl_demand_scale`×1 | **3** | 1 | 2 |
| dev | `nl_noise`×3, `leak_noise_J3`×3, `ambiguous_demand_J1`×1, `nl_roughness`×1 | **8** | 3 | 5 |
| test | `leak_demand_var_J2`×1, `nl_pump_transition`×1, `leak_pump_J1`×1, `leak_roughness_J3`×1, `nl_demand_node_J1`×1 | **5** | 3 | 2 |

### Test hypothesis metrics — denominators

| Metric | Numerator | Denominator | Value |
|--------|----------:|------------:|------:|
| Detection TPR | 2 detects among leak rows (`leak_demand_var_J2`, `leak_roughness_J3`) | 3 leak rows | 2/3 ≈ 0.667 |
| Control FPR / burden | 0 `decision=leak` on controls | 2 control rows | 0/2 = 0 |
| Inconclusive rate | 2 rows (`leak_pump_J1`, `nl_demand_node_J1`) | 5 test rows | 2/5 = 0.40 |
| Mean region size among detects | sizes `{1, 1}` | 2 detects | 1.0 |
| Region coverage among detects | 1 cover (`leak_roughness_J3`) | 2 detects | 1/2 = 0.50 |
| Exact-match localization among detects | 1 exact (`leak_roughness_J3`) | 2 detects | 1/2 = 0.50 |
| Localization error among detects | 1 wrong (`leak_demand_var_J2` → J3) | 2 detects | 1/2 = 0.50 |

### Dev / train (for context only; not used to rewrite test)

| Split | TPR | FPR | Inconclusive | Region coverage among detects |
|-------|----:|----:|-------------:|------------------------------:|
| train | 1/1 | 0/2 | 1/3 | 1/1 |
| dev | 3/3 | 0/5 | 1/8 | 3/3 |
| Ambiguous admit (dev) | `ambiguous_demand_J1` → inconclusive | 1/1 | — | — |

### Baseline test metrics — denominators

| Method | TPR | FPR | Notes |
|--------|----:|----:|-------|
| Dual signature | 3/3 | 0/2 | No abstention channel |
| Method M–style steady | 0/3 | 0/2 | **Inapplicable as temporal Method M** (see §7) |

---

## 2. Network / model, candidates, coverage

| Item | Toy stage |
|------|-----------|
| Networks | `branched3` (R→J1→J2→J3) and `pump_tank` (R→pump→J1→J2→T1) |
| Hydraulics | WNTR/EPANET steady (or snapshot) primal; H0/H1 fit primal heads |
| Calibration lineage | Referenced corrected freeze `5fab3acb…` but **toy nets do not apply L-Town frozen HW/demand** |
| Sensors | All junctions with sensors: branched `{J1,J2,J3}`; pump `{J1,J2}` |
| Candidate set | Topology-fixed: branched 3; pump 2 |
| Candidate count | 3 or 2 |

**Injected locations vs candidates**

| Scenario | Injected node | In candidate set? |
|----------|---------------|:-----------------:|
| All branched leak scenarios | J2 or J3 | **Yes** |
| `leak_pump_J1` | J1 | **Yes** |
| Demand-only bumps | J1 (not labeled leak) | N/A |

**No candidate omission** on the frozen toy set: every true leak node was exactly representable.

---

## 3. Detection and localization per scenario (all splits)

| ID | Split | Truth | Decision | ΔJ | Best c | Region | Cover? | Sig detect / loc |
|----|-------|-------|----------|---:|:------:|--------|:------:|------------------|
| nl_nominal | train | none | no_new_leak | 0 | J1 | {J1,J2,J3} | — | F / — |
| leak_nominal_J3 | train | J3 leak 5 | **leak** | 0.363 | J3 | {J3} | Y | T / J3 |
| nl_demand_scale | train | none (×1.25 dem) | inconclusive | 0.100 | J3 | {J3} | — | T / J3 |
| nl_noise ×3 | dev | none | no_new_leak | 0 | J1 | all 3 | — | F |
| leak_noise_J3 ×3 | dev | J3 | **leak** | ~0.35–0.38 | J3 | {J3} | Y | T / J3 |
| ambiguous_demand_J1 | dev | none (+2.5 dem J1) | inconclusive | 0.0005 | J1 | all 3 | — | F |
| nl_roughness | dev | none (ρ_truth=0.95) | no_new_leak | 0 | J1 | all 3 | — | F |
| leak_demand_var_J2 | test | J2 leak 4 + dem×1.15 | **leak** | 0.153 | **J3** | **{J3}** | **N** | T / **J2** |
| nl_pump_transition | test | none | no_new_leak | 0 | J1 | {J1,J2} | — | F |
| leak_pump_J1 | test | J1 leak 4 | inconclusive | 0 | J1 | {J1,J2} | — | T / J1 |
| leak_roughness_J3 | test | J3 leak 5 + ρ=0.95 | **leak** | 0.447 | J3 | {J3} | Y | T / J3 |
| nl_demand_node_J1 | test | none (+1.5 dem J1) | inconclusive | 0.0001 | J1 | all 3 | — | F |

---

## 4. Generator identity (observations vs candidate responses)

| Aspect | Toy H0/H1 |
|--------|-----------|
| Observation generator | EPANET primal on truth clone |
| H0/H1 predictor | EPANET primal on model template + fitted δ, ρ, (H1) q_c |
| Same nonlinear generator family? | **Yes** (WNTR/EPANET) |
| Same nominal parameters? | Same pipe geometry; model starts from unperturbed template; truth may scale demand/roughness or add leak |
| Linear approximation? | **No** for toy H0/H1 (full nonlinear solves in the optimizer) |
| Dual signature baseline | Separate dual with VR heads = obs; not used inside H0/H1 J |

---

## 5. Do nuisance bounds contain simulated perturbations?

Config: δ∈[-3,+3] m³/h, ρ∈[0.92,1.08], q∈[0,12].

| Perturbation | Magnitude | Inside H0/H1 box? |
|--------------|-----------|:-----------------:|
| Demand ×1.25 (nl_demand_scale) | Δ≈+2.5,+2.5,+1.25 m³/h | **Yes** (as δ) |
| Demand ×1.15 + leak J2 (test) | Δ≈+1.5,+1.5,+0.75; q=4 | **Yes** |
| Node demand +1.5 / +2.5 | within ±3 | **Yes** |
| Roughness ×0.95 | ρ=0.95 | **Yes** |
| Leak 4–5 m³/h | ≤12 | **Yes** |
| Sensor noise σ=0.05 m | not a nuisance param (obs noise) | N/A |

Bound violation is **not** the explanation for the 50% region coverage.

---

## 6. Why detected singleton regions cover the true location only 50%

**Only two test detects** enter the coverage denominator:

1. `leak_roughness_J3` — singleton `{J3}` covers truth.  
2. `leak_demand_var_J2` — singleton `{J3}` **misses** truth J2.

### Diagnosis for the miss (mutually exclusive causes)

| Cause | Applies? | Evidence |
|-------|:--------:|----------|
| **Candidate omission** | **No** | J2 ∈ `{J1,J2,J3}` |
| **Model / identifiability + optimizer** | **Yes (primary for wrong best node)** | Combined demand scale + leak; H1 reported `best=J3`, `q̂=2` while signature Σq_v localized **J2**. Nonlinear landscape under equal δ-box did not recover the injected node. |
| **Unjustified region-construction rule** | **Yes (primary for confident singleton excluding truth)** | Region = `{c: J(c) ≤ J* + 0.02}` with **fixed** `region_eps_m2=0.02` never calibrated on train/DEV for coverage. Produced size-1 region around the wrong minimizer → coverage 0 on that detect. |

So the 50% figure is **not** “half the leaks omitted from the candidate list.” It is **1/2 detects** where a **calibratable region rule was never calibrated**, wrapping an **incorrect point estimate** under demand+leak confounding.

Fit-score gaps ΔJ / ε were **not** probabilities; treating ε=0.02 as a confidence set was unjustified.

---

## 7. Method M comparison on this stage

Frozen **temporal** five-minute Method M (τ=4.517, REF/SCALE windows) is **not comparable** to isolated steady dual snapshots. The toy “method_m_style_steady” column is a one-shot analogue only and is marked **inapplicable** for product Method M claims. Do not interpret its TPR=0 as Method M failure on BattLeDIM.

---

## 8. Implications (forward, without retuning this freeze)

1. Preserve these results as a cautionary baseline.  
2. Register region construction on **train/DEV only** with an explicit coverage target; report size, coverage, abstention separately.  
3. Move feasibility to **calibrated L-Town** with fresh whole-scenario test IDs after freeze.  
4. Compare signature matching at matched detection burden / abstention — not temporal Method M vs steady snapshots.
