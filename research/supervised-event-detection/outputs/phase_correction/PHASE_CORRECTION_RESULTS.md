# Scenario-phase correction — synthetic results

Generated: 2026-10-24T23:22:52-04:00

Randomized pattern time origin; independent leak onset after warm-up. Original `synthetic_scenarios/` preserved. **No measured evaluation** this round.

## Changes

- **pattern_phase**: Unif[0,24) hours → pattern_start and start_clocktime
- **leak_onset**: independent Unif[14,38] scenario-wall hours
- **matched_pairs**: first 16 leaks paired to controls with same phase
- **tank_pump_controls**: level-based unchanged

Master seed: `20261025`
Selection rule: on synthetic_dev full trajectories: among (C,τ) with episode_6h_recall>=0.666667 and control_episodes_per_week<=3, max episode_6h_recall, then min control_episodes_per_week, then min median_delay_h, then min C, then min τ. If no candidate passes gates: report selection_failure=true and freeze rank-best under the same ordering without gates (gate_met=false).

## Pre-fit distribution checks

Passed: **True**

```json
{
  "n_leak": 24,
  "n_control": 16,
  "phase_in_range_leaks": true,
  "phase_in_range_controls": true,
  "onset_after_warmup": true,
  "onset_before_horizon": true,
  "paired_phases_identical": true,
  "n_pairs_checked": 16,
  "corr_phase_onset": 0.024189508887035693,
  "corr_phase_onset_abs_lt_0_5": true,
  "leak_phase_mean": 10.856207824694605,
  "ctrl_phase_mean": 11.517856139832592,
  "leak_phase_std": 6.010126588544282,
  "ctrl_phase_std": 5.53974893163991,
  "onset_mean": 24.707702899864827,
  "onset_std": 6.521543461600503,
  "phase_means_within_6h": true,
  "all_passed": true
}
```

Splits: `{'synthetic_dev': 8, 'synthetic_test': 19, 'train': 13}`; pairs colocated=True

## Freeze

- Selected C=10.0, τ=0.7
- gate_met=False, selection_failure=True
- DEV metrics: `{'episode_6h_recall': 0.4, 'n_episode_6h_hit': 2, 'n_leak_scenarios': 5, 'median_delay_h': 3.0416666666666665, 'control_episodes_per_week': 9.333333333333334, 'n_control_episodes': 8, 'n_control_scenarios': 3, 'row_credit_scenario_recall': 0.8, 'n_row_vs_episode_disagree': 2, 'n_blocked_by_preonset_active': 2, 'gate_met': False}`

## Synthetic evaluation (headline = episode)

| Split | episode_6h | med delay h | ctrl ep/wk | ctrl exposure wk | preonset notifies | blocked | leak occ | ctrl occ | row_credit |
|-------|------------|-------------|------------|------------------|------------------|---------|----------|----------|------------|
| synthetic_dev | 0.4 (2/5) | 3.0416666666666665 | 9.333 | 0.8571 | 6 | 2 | 0.6896 | 0.6836 | 0.8 |
| synthetic_test | 0.2727 (3/11) | 1.75 | 11.38 | 2.286 | 17 | 8 | 0.7042 | 0.5534 | 0.9091 |

Each control scenario contributes 48 h (0.2857 weeks). ep/wk = n_episodes / (n_controls × 0.2857).

### Synthetic test per-leak

- HIT6 `leak_001_p567` phase=6.100h onset=24.657h delay=1.0833333333333333 blocked=False preonset_n=1 occ=0.455
- HIT6 `leak_002_p157` phase=15.156h onset=14.291h delay=3.75 blocked=False preonset_n=1 occ=0.686
- MISS `leak_004_p244` phase=10.763h onset=34.459h delay=None blocked=True preonset_n=2 occ=0.794
- MISS `leak_007_p886` phase=10.092h onset=25.606h delay=None blocked=True preonset_n=2 occ=0.767
- MISS `leak_009_p278` phase=8.077h onset=27.863h delay=None blocked=True preonset_n=2 occ=0.566
- MISS `leak_012_p489` phase=14.910h onset=25.980h delay=None blocked=True preonset_n=2 occ=0.591
- MISS `leak_013_p33` phase=16.291h onset=16.916h delay=None blocked=True preonset_n=1 occ=0.852
- HIT6 `leak_015_p73` phase=13.338h onset=19.697h delay=1.75 blocked=False preonset_n=1 occ=0.591
- MISS `leak_018_p272` phase=18.306h onset=28.331h delay=None blocked=True preonset_n=2 occ=0.804
- MISS `leak_022_p670` phase=10.567h onset=23.516h delay=None blocked=True preonset_n=2 occ=0.781
- MISS `leak_023_p490` phase=18.950h onset=14.808h delay=None blocked=True preonset_n=1 occ=0.859

## Stop

Synthetic results only — awaiting review before any measured evaluation.

## Non-goals this round

- No measured 2018/2019, production, UI, Tiger, deployment
- Original scenarios/results untouched

