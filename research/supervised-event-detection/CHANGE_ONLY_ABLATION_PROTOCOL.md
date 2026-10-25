# Change-only feature ablation protocol (registered before fit)

**Experiment type:** isolated paired feature ablation under the
**episode-notification** selection objective.

**Question:** Does removing absolute operating-state features improve
synthetic-to-measured transfer under the same episode-notification objective?

**Preserves:** production; original `pilot_*`; `PILOT_RESULTS.md`;
`TRANSFER_FAILURE_DIAGNOSIS.md`; `TARGET_ALIGNMENT_BEFORE_ABLATION.md`;
`outputs/episode_objective/` (untouched).

**Outputs (new only):** `outputs/change_only_ablation/`

**Non-goals:** no new features, simulations, labels, scenarios, model families,
2019 evaluation, measured retuning, main merge, Tiger, UI, or deployment.

---

## Arms (feature sets only differ)

### Arm A — full `pressure_context_v1` (53 features)

Identical representation to the episode-objective baseline. Used as the
reproduction control.

### Arm B — change/residual only (43 features)

**Removed** (absolute operating-state / level proxies):

1. `P_median`
2. `P_p10`
3. `P_p90`
4. `P_max`
5. `P_min`
6. `F_p227`
7. `F_p235`
8. `F_PUMP_1`
9. `L_T1`
10. `pump1_on`

**Retained** (existing causal change/residual + absolute-derived spread only):

1. `P_spread_p90_p10`
2. `Pd_d1_median`
3. `Pd_d1_p10`
4. `Pd_d1_p90`
5. `Pd_d1_min`
6. `Pd_d1_max_abs`
7. `Pd_d1_topneg1`
8. `Pd_d1_topneg2`
9. `Pd_d1_topneg3`
10. `Pd_d1_topneg4`
11. `Pd_d1_topneg5`
12. `Pd_d6_median`
13. `Pd_d6_p10`
14. `Pd_d6_p90`
15. `Pd_d6_min`
16. `Pd_d6_max_abs`
17. `Pd_d6_topneg1`
18. `Pd_d6_topneg2`
19. `Pd_d6_topneg3`
20. `Pd_d6_topneg4`
21. `Pd_d6_topneg5`
22. `Pd_d24_median`
23. `Pd_d24_p10`
24. `Pd_d24_p90`
25. `Pd_d24_min`
26. `Pd_d24_max_abs`
27. `Pd_d24_topneg1`
28. `Pd_d24_topneg2`
29. `Pd_d24_topneg3`
30. `Pd_d24_topneg4`
31. `Pd_d24_topneg5`
32. `Fd_p227_d1`
33. `Fd_p227_d6`
34. `Fd_p227_d24`
35. `Fd_p235_d1`
36. `Fd_p235_d6`
37. `Fd_p235_d24`
38. `Fd_PUMP_1_d1`
39. `Fd_PUMP_1_d6`
40. `Fd_PUMP_1_d24`
41. `Ld_T1_d1`
42. `Ld_T1_d6`
43. `Ld_T1_d24`

No new feature definitions. Column subset of the existing builder only.
`P_spread_p90_p10` is retained (not listed for removal; not a raw absolute
level scalar). Pump **change** features `Fd_PUMP_1_*` remain available so the
report can check whether Arm B still exploits pump-change shortcuts.

---

## Held identical across arms

- Existing synthetic scenarios and whole-scenario splits
- Preprocessing: StandardScaler fit on **synthetic train rows only**
- Labels: registered 6 h recent-onset credit window (`y=1` not ongoing leak)
- L2 logistic (`class_weight=balanced`, `lbfgs`, `random_state=0`)
- Candidate budget: `C ∈ {0.01, 0.1, 1.0, 10.0, 100.0}`,
  `τ ∈ {0.3, 0.5, 0.7, 0.85, 0.95}` — **no post-hoc expansion**
- Notifier: notify `q≥τ` while inactive; recover after 12 steps with `q<τ/2`
- Continuous notifier state on full chronological trajectories — **never** reset
  at leak onset or credit-window edges
- Warm-up / eligibility / matching as in episode-objective measured eval

---

## Selection (independent per arm; same rule)

Identical to `EPISODE_SELECTION_PROTOCOL.md` / `train_episode_objective.py`:

- Gates: `episode_6h_recall ≥ 2/3` and `control_episodes_per_week ≤ 3` on
  synthetic DEV
- Among passers: max episode_6h_recall → min control ep/wk → min median_delay_h
  → min C → min τ
- If none pass: `selection_failure=true`, freeze rank-best with `gate_met=false`

---

## Evaluation order (per arm)

1. Fit + select on synthetic train / DEV
2. **Verify Arm A** reproduces the episode-objective baseline freeze
   (`C`, `τ`, DEV episode metrics within tight tolerance)
3. Freeze selected `(C, τ, coef, scaler)` for that arm
4. Synthetic test (episode headline; row-credit side-only)
5. Measured 2018 DEV/DIAG diagnostic transfer — **no retune**

Interpret separately: (a) synthetic operating-point change; (b) measured
transfer. One favorable DIAG recall does not establish either claim alone.
