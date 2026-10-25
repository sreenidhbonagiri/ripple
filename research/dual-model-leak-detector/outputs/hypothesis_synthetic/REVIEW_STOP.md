# Review stop — synthetic feasibility complete

**Status:** stop for review before measured evaluation.  
**Branch:** `research/uncertainty-aware-hypothesis`  
**Deployed five-minute Method M:** preserved (no main merge, no product/UI/Tiger/deploy changes).

## What was delivered

1. Protocol (`HYPOTHESIS_PROTOCOL.md`) — objective, constraints, regularization, complexity penalty, leak↔demand identifiability, candidate generation without eval leak peeking, whole-scenario splits, metrics.
2. Executable H0/H1 comparison with **identical** nuisance bounds; H1 adds only \(q_c\ge 0\).
3. Synthetic scenario suite (demand variation, noise, roughness mismatch, pump–tank analogue, indistinguishable demand).
4. Baselines: dual signature matching + Method M–style steady score (frozen τ ref 4.517 / cal `5fab3acb…`).
5. Results: `SYNTHETIC_FEASIBILITY_RESULTS.md` + JSON.

## Test-split snapshot (see results for full table)

| Metric | Hypothesis H0/H1 |
|--------|-----------------:|
| TPR | 0.67 |
| Control FPR | 0.00 |
| Inconclusive rate | 0.40 |
| Region coverage among detects | 0.50 |
| Exact loc among detects | 0.50 (not sole headline) |

Ambiguous demand-vs-leak (`ambiguous_demand_J1`): **inconclusive** (admits ambiguity).  
Pump-network leak snapshot (`leak_pump_J1`): **inconclusive** (ΔJ≈0 — method does not force a location).  
Demand+leak (`leak_demand_var_J2`): detect fires but best node wrong — localization error reported explicitly.

## Explicitly not done

- Measured-event tuning, 2019, main merge, Tiger, UI, deployment  
- Detector changes to frozen Method M
