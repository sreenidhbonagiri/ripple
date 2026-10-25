# Arm A synthetic-test miss audit (diagnostic only)

Generated: 2026-10-24T23:08:33-04:00

**Question:** Why does the full-feature classifier fail episode detection even on held-out synthetic scenarios?

Preserves Arm A/B freezes, ablation reports, episode-objective outputs, and production. **No** new fits, threshold searches, simulations, or 2019.

Frozen Arm A: C=10.0, τ=0.7 (from `outputs/change_only_ablation/arm_A_frozen_model.json`).

## Cause definitions (reproducible)

- **no_crossing_in_6h**: No finite q(t) ≥ τ for any t in [onset, onset+6h] (inclusive).
- **preonset_active_block**: Some episode has notify_idx < onset ≤ end_idx (notifier still active at onset), and no episode has notify_idx in [onset, onset+6h].
- **confirmation_not_met**: Reserved: this supervised notifier has no separate confirmation dwell beyond first q≥τ while inactive — always false for this pipeline.
- **warmup_missingness**: Onset index < feature warm-up, or every score in the credit window is non-finite, or >50% of credit-window scores are non-finite.

## Synthetic_test headline

- Leak scenarios: 15 (hits=7, misses=8)
- Episode_6h recall: 0.4666666666666667
- Row-credit scenario recall: 0.6
- Row-credit hit but episode miss: 3
- Pre-onset active at onset (any miss/hit flag): 8

### Miss primary classifications

- `no_crossing_in_6h`: 3
- `preonset_active_block`: 3
- `preonset_active_no_crossing`: 2

## Per-leak miss detail

| scenario | primary | crossed | blocked | max q credit | preonset notify hrs | recovery debt |
|----------|---------|---------|---------|--------------|--------------------|---------------|
| `leak_000_p282` | preonset_active_no_crossing | False | True | 0.44524310709981174 | [16.666666666666668, 24.333333333333332] | persist=True debt=False |
| `leak_001_p299` | no_crossing_in_6h | False | False | 0.5523219367247664 | [16.666666666666668, 24.333333333333332] | persist=None debt=None |
| `leak_003_p435` | preonset_active_no_crossing | False | True | 0.6438593542029368 | [16.583333333333332] | persist=True debt=False |
| `leak_005_p443` | no_crossing_in_6h | False | False | 0.23065705548243265 | [16.583333333333332, 23.583333333333332] | persist=None debt=None |
| `leak_011_p19` | no_crossing_in_6h | False | False | 0.2080603811036573 | [16.666666666666668, 24.333333333333332] | persist=None debt=None |
| `leak_012_p801` | preonset_active_block | True | True | 0.8854262225182277 | [16.583333333333332, 23.583333333333332] | persist=True debt=False |
| `leak_015_p655` | preonset_active_block | True | True | 0.8605251539513957 | [16.583333333333332] | persist=True debt=False |
| `leak_023_p891` | preonset_active_block | True | True | 0.9012548485566576 | [16.666666666666668, 24.333333333333332] | persist=True debt=False |

### Pre-onset blocked deep dive

- `leak_000_p282`: covering notify t=292 (24.3 h), end=354; context@notify: P_med=47.55, Pd_d6_min=0.0018157958984375, pump_on=True, L_T1=3.18; similar_control_notifies_near_hour=3
- `leak_003_p435`: covering notify t=199 (16.6 h), end=356; context@notify: P_med=47.58, Pd_d6_min=-0.051967620849609375, pump_on=False, L_T1=2.607; similar_control_notifies_near_hour=3
- `leak_012_p801`: covering notify t=283 (23.6 h), end=355; context@notify: P_med=47.46, Pd_d6_min=0.000885009765625, pump_on=True, L_T1=3.042; similar_control_notifies_near_hour=0
- `leak_015_p655`: covering notify t=199 (16.6 h), end=357; context@notify: P_med=47.59, Pd_d6_min=-0.05142974853515625, pump_on=False, L_T1=2.619; similar_control_notifies_near_hour=3
- `leak_023_p891`: covering notify t=292 (24.3 h), end=354; context@notify: P_med=47.56, Pd_d6_min=0.00177764892578125, pump_on=True, L_T1=3.175; similar_control_notifies_near_hour=3

## Controls (synthetic_test only — not invented pairs)

- n_control=6, n_episodes=9, ep/wk=5.25
- Denominator: Each control contributes only 48 h (0.2857 weeks). With few controls, ep/wk is a noisy rate over a short simulated denominator — not a year-scale burden estimate.

Control notify hours:

- `ctrl_000_control_pump` (control_pump): notify_hours=[16.75, 40.583333333333336]
- `ctrl_001_control_demand` (control_demand): notify_hours=[25.25]
- `ctrl_003_control_demand` (control_demand): notify_hours=[16.583333333333332, 40.5]
- `ctrl_010_control_pump` (control_pump): notify_hours=[24.833333333333332]
- `ctrl_012_control_demand` (control_demand): notify_hours=[25.25]
- `ctrl_013_control_demand` (control_demand): notify_hours=[16.75, 40.583333333333336]

## Scenario construction audit

- Hydraulic warm-up: 12 h; feature warm-up: 12.0 h; duration: 48 h
- Leak start sampling: uniform in [14, 38] hours

Leak covariates by split:

- **train**: `{"n": 4, "leak_area_m2": {"min": 5e-05, "max": 0.00035, "mean": 0.0002}, "demand_scale": {"min": 0.97, "max": 1.0, "mean": 0.9849999999999999}, "leak_start_hour": {"min": 15.545783803100907, "max": 36.83756182231506, "mean": 24.351219604049692}, "leak_duration_h": {"min": 8.79642046262461, "max": 16.86089046862947, "mean": 12.117695416022235}, "operating_realization_counts": {"0": 3, "1": 1}, "pipe_group_counts": {"1": 2, "2": 2}}`
- **synthetic_dev**: `{"n": 5, "leak_area_m2": {"min": 5e-05, "max": 0.0002, "mean": 9e-05}, "demand_scale": {"min": 0.92, "max": 1.0, "mean": 0.9620000000000001}, "leak_start_hour": {"min": 18.01901752127673, "max": 35.95390579763104, "mean": 24.120860927501834}, "leak_duration_h": {"min": 7.356561169539411, "max": 14.713322415650698, "mean": 11.025789114599997}, "operating_realization_counts": {"2": 5}, "pipe_group_counts": {"0": 1, "1": 3, "2": 1}}`
- **synthetic_test**: `{"n": 15, "leak_area_m2": {"min": 5e-05, "max": 0.00035, "mean": 0.00018333333333333336}, "demand_scale": {"min": 0.92, "max": 1.08, "mean": 0.9966666666666666}, "leak_start_hour": {"min": 17.62885483855029, "max": 35.5558534993813, "mean": 25.52943834917933}, "leak_duration_h": {"min": 7.735130708363837, "max": 17.356064791084236, "mean": 12.016432655441166}, "operating_realization_counts": {"0": 2, "1": 2, "2": 3, "3": 8}, "pipe_group_counts": {"0": 1, "1": 1, "2": 2, "3": 3, "4": 8}}`

Controls by split:

- **train**: `{"n": 7, "kinds": {"control_demand": 1, "control_pump": 2, "control_sensor": 2, "control_tank": 2}, "demand_scale": {"min": 0.85, "max": 1.2, "mean": 1.0214285714285716}}`
- **synthetic_dev**: `{"n": 3, "kinds": {"control_sensor": 2, "control_tank": 1}, "demand_scale": {"min": 1.1, "max": 1.15, "mean": 1.1166666666666667}}`
- **synthetic_test**: `{"n": 6, "kinds": {"control_pump": 2, "control_demand": 4}, "demand_scale": {"min": 0.85, "max": 1.2, "mean": 1.0166666666666666}}`

Positives are always the first 6 h after leak_start on a 48 h trajectory with leaks drawn uniformly in [14 h, 38 h]. Absolute operating features can correlate with scenario clock time / diurnal phase.

Pre-onset notify index histogram (all test leaks): `{'16': 14, '24': 5, '23': 3}`

## Onset-aligned physical signal (descriptive; GT windows only)

`{
  "hit_post_minus_pre_pd_min_mean": 0.05579387573968797,
  "miss_post_minus_pre_pd_min_mean": -0.052877051962746516,
  "control_clock_windows_pd_d6_min_mean": -0.040796151867619264,
  "note": "Ground-truth onset defines leak pre/post windows for description only. Control windows are clock-based (16 h and 24 h), not paired scenarios."
}`

## Decision

**D. Mixed or unresolved**

Evidence:

- 5/8 misses have no q≥τ in the 6 h credit window (insufficient score response at frozen τ).
- 5/8 misses are pre-onset-active blocked (notifier state prevents a new credit-window notify).
- 3 scenarios have row-credit hits but episode-6h misses (objective/notifier mismatch with row labels).
- 14 pre-onset notifies cluster at indices ~199 (~16.6 h scenario time) across leaks — shared operating/phase cue.
- Synthetic_test controls alone yield 5.25 ep/wk under the same freeze — false episodes without leaks.

Votes: `{'A': 2, 'B': 3, 'C': 3}`

### Recommended next intervention (not implemented)

Single next step: on synthetic DEV only, add an explicit preonset_active_block / inactive-at-onset constraint to the existing episode-selection gates (same C/τ budget; no post-hoc expansion), because the dominant miss pattern is a shared ~16.6 h operating-phase latch that also fires on controls and then blocks onset credit. Scenario-clock redesign is the alternate if gating cannot find any passing candidate. Do not implement in this audit.

## Artifacts

- Per-scenario timelines: `timelines/*.json`
- Machine-readable summary: `summary.json`

## Non-goals

- No new fits, grid expansion, simulations, 2019, main merge, Tiger, UI, deploy

