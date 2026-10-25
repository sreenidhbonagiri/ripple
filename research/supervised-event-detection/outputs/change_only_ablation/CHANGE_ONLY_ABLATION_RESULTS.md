# Change-only feature ablation (episode-notification objective)

Generated: 2026-10-24T23:01:40-04:00

**Question:** Does removing absolute operating-state features improve synthetic-to-measured transfer under the same episode-notification objective?

Preserves production, prior reports, and `outputs/episode_objective/`. No new simulations, labels, features, 2019, Tiger, UI, or main merge.

## Registered arms (before fit)

- Arm A: 53 features — `full_pressure_context_v1`
- Arm B: 43 features — `change_residual_only`
- Removed in B: ['P_median', 'P_p10', 'P_p90', 'P_max', 'P_min', 'F_p227', 'F_p235', 'F_PUMP_1', 'L_T1', 'pump1_on']

Selection rule (both arms):

on synthetic_dev full trajectories: among (C,τ) with episode_6h_recall>=0.666667 and control_episodes_per_week<=3, max episode_6h_recall, then min control_episodes_per_week, then min median_delay_h, then min C, then min τ. If no candidate passes gates: report selection_failure=true and freeze rank-best under the same ordering without gates (gate_met=false).

Arm A vs episode-objective baseline: **PASS** `{'C_match': True, 'tau_match': True, 'gate_met_match': True, 'selection_failure_match': True, 'dev_episode_6h_recall_match': True, 'dev_control_ep_per_week_match': True, 'n_grid_match': True, 'coef_allclose': True, 'all_passed': True}`

## Side-by-side headline (episode metrics)

| Metric | Arm A | Arm B |
|--------|-------|-------|
| Selected (C, τ) | 10.0, 0.7 | 100.0, 0.7 |
| gate_met | False | False |
| selection_failure | True | True |
| synthetic_dev episode_6h | 0.6 (3/5) | 0.8 (4/5) |
| synthetic_dev median_delay_h | 4.583333333333333 | 5.291666666666666 |
| synthetic_dev ctrl ep/wk | 7 | 16.33 |
| synthetic_dev blocked_preonset | 4 | 4 |
| synthetic_dev row_credit scen (side) | 0.8 | 0.8 |
| synthetic_test episode_6h | 0.4667 (7/15) | 0.3333 (5/15) |
| synthetic_test median_delay_h | 5.583333333333333 | 4.75 |
| synthetic_test ctrl ep/wk | 5.25 | 12.25 |
| synthetic_test blocked_preonset | 8 | 10 |
| synthetic_test row_credit scen (side) | 0.6 | 0.5333 |
| measured DEV abrupt6h | 0.0 (0/3) | 0.3333333333333333 (1/3) |
| measured DEV delays_h | [] | [1.3333333333333333] |
| measured DEV unmatched/wk | 6.42 | 30.44 |
| measured DEV dup24h | 151 | 787 |
| measured DEV union alarm % | 9.062 | 53.92 |
| measured DIAG abrupt6h | 0.6666666666666666 (2/3) | 0.3333333333333333 (1/3) |
| measured DIAG delays_h | [2.6666666666666665, 2.25] | [2.1666666666666665] |
| measured DIAG unmatched/wk | 8.484 | 30.78 |
| measured DIAG dup24h | 206 | 809 |
| measured DIAG union alarm % | 13.7 | 55.15 |

## Coefficient / pump-change shortcut check

### arm_A: pump_change_abs_share=0.02637; still_exploits_pump_change=False

| rank | feature | coef | share |
|------|---------|------|-------|
| 1 | `P_p90` | 7.849 | 0.05506 |
| 2 | `Pd_d24_topneg3` | -7.805 | 0.05475 |
| 3 | `F_p227` | 6.887 | 0.04831 |
| 4 | `Pd_d24_median` | -6.473 | 0.04541 |
| 5 | `P_p10` | 5.592 | 0.03923 |
| 6 | `Pd_d24_min` | 5.506 | 0.03862 |
| 7 | `Pd_d24_topneg1` | 5.506 | 0.03862 |
| 8 | `Pd_d6_min` | 5.168 | 0.03626 |
| 9 | `Pd_d6_topneg1` | 5.168 | 0.03626 |
| 10 | `Pd_d24_p90` | 4.422 | 0.03102 |

### arm_B: pump_change_abs_share=0.04263; still_exploits_pump_change=False

| rank | feature | coef | share |
|------|---------|------|-------|
| 1 | `Fd_p227_d24` | 20.58 | 0.1002 |
| 2 | `Fd_p235_d24` | -18.24 | 0.08883 |
| 3 | `Pd_d1_topneg5` | 12.13 | 0.05908 |
| 4 | `Pd_d24_topneg3` | -9.868 | 0.04807 |
| 5 | `Pd_d6_median` | -9.046 | 0.04406 |
| 6 | `Pd_d6_min` | 8.061 | 0.03926 |
| 7 | `Pd_d6_topneg1` | 8.061 | 0.03926 |
| 8 | `Pd_d6_topneg5` | 7.528 | 0.03667 |
| 9 | `Pd_d1_topneg4` | -6.473 | 0.03153 |
| 10 | `Pd_d6_max_abs` | 6.389 | 0.03112 |

## Paired synthetic-test leak outcomes

- both_miss `leak_000_p282` A_delay=None B_delay=None blocked A/B=True/True
- both_miss `leak_001_p299` A_delay=None B_delay=None blocked A/B=False/False
- both_hit `leak_002_p69` A_delay=5.833333333333333 B_delay=5.25 blocked A/B=False/True
- both_miss `leak_003_p435` A_delay=None B_delay=None blocked A/B=True/True
- both_miss `leak_005_p443` A_delay=None B_delay=None blocked A/B=False/False
- both_hit `leak_008_p576` A_delay=5.0 B_delay=4.75 blocked A/B=False/False
- both_hit `leak_009_p210` A_delay=1.5 B_delay=1.6666666666666667 blocked A/B=False/True
- A_hit_B_miss `leak_010_p607` A_delay=5.833333333333333 B_delay=None blocked A/B=True/True
- both_miss `leak_011_p19` A_delay=None B_delay=None blocked A/B=False/False
- both_miss `leak_012_p801` A_delay=None B_delay=None blocked A/B=True/True
- both_miss `leak_015_p655` A_delay=None B_delay=None blocked A/B=True/True
- both_hit `leak_017_p445` A_delay=5.083333333333333 B_delay=4.666666666666667 blocked A/B=False/False
- A_hit_B_miss `leak_018_p513` A_delay=6.0 B_delay=None blocked A/B=True/True
- both_hit `leak_021_p800` A_delay=5.583333333333333 B_delay=5.833333333333333 blocked A/B=True/True
- both_miss `leak_023_p891` A_delay=None B_delay=None blocked A/B=True/True

Pair counts: `{'both_miss': 8, 'both_hit': 5, 'A_hit_B_miss': 2}`

## Paired measured abrupt 6h outcomes

### DEV

- both_miss6 p673 onset=2018-03-05 15:45 A_delay=110.41666666666667 B_delay=7.5
- both_miss6 p538 onset=2018-05-18 08:35 A_delay=None B_delay=9.25
- A_miss6_B_hit6 p866 onset=2018-06-01 09:05 A_delay=21.25 B_delay=1.3333333333333333

Counts: `{'both_miss6': 2, 'A_miss6_B_hit6': 1}`

### DIAG

- both_miss6 p183 onset=2018-08-07 02:35 A_delay=21.416666666666668 B_delay=7.666666666666667
- A_hit6_B_miss6 p158 onset=2018-10-06 02:35 A_delay=2.6666666666666665 B_delay=12.666666666666666
- both_hit6 p369 onset=2018-10-26 02:05 A_delay=2.25 B_delay=2.1666666666666665

Counts: `{'both_miss6': 1, 'A_hit6_B_miss6': 1, 'both_hit6': 1}`

## Interpretation (separate claims)

**(a) Synthetic operating point improved?** **False** — lower synth-test episode_6h_recall; higher synth-test control ep/wk

**(b) Measured transfer improved (strict)?** **False** — DEV abrupt6h A=0.0 B=0.3333333333333333; DIAG A=0.6666666666666666 B=0.3333333333333333; unmatched/wk DEV A=6.42 B=30.44; DIAG A=8.484 B=30.78. One favorable DIAG recall alone does not establish transfer improvement.

Loose any-period recall up (not sufficient alone): True

## Non-goals

- No main merge, Tiger, UI, deployment
- No new simulations or model families
- Episode-objective artifacts preserved

