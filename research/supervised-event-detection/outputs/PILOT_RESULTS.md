# Synthetic-trained detection pilot

Generated: 2026-10-24T22:29:19-04:00

Preserves production, frozen FMR3C, and all prior evaluations. **No** 2019 train/tune, Tiger, UI, or main merge.

> **Transfer diagnosis (no retune):** see `TRANSFER_FAILURE_DIAGNOSIS.md` — absolute/operating-state shortcuts and weak/wrong-signed network drop features; not a bare 'domain mismatch' label. Frozen pilot unchanged.

## Question

Can a simple L2 logistic classifier trained on varied hydraulic leak scenarios recognize event patterns in measured 2018 SCADA?

## 0. Feature pipeline

- Feature set: `pressure_context_v1` (53 dims)
- Units: {'pressure': 'm', 'flow': 'm3/h', 'tank_level': 'm'}
- Forbidden inputs: ['true_leak_pipe_id', 'nearest_sensor_to_leak', 'future_observations', '2019_labels_in_features']
- INP: `a7551b86745f4cc3…` (`L-TOWN.inp`)
- Tests: passed

## 1. Synthetic dataset (bounded pilot)

- Master seed: **20261024**
- Planned / ok / failed: 40 / 40 / 0
- Leak pipe sampling: Pipes sampled with MASTER_SEED from L-TOWN.inp pipe list; 2019 leak labels were not read or used for inclusion/exclusion.
- Similarity: All scenarios share the same nominal L-TOWN.inp topology and patterns; they differ by pipe, leak area, demand scale, operating_realization, and control interventions. Residual hydraulic similarity remains.

Failures (recorded, not dropped silently):

- *(none)*

### Splits (whole-scenario)

- Rules: Whole-scenario assignment only. No neighboring 5-minute row splits. Leak pipe_groups [3, 4] held out to synthetic_test. operating_realization 0–1 train, 2 synth_dev, 3 synth_test.
- Counts: `{'synthetic_test': 21, 'synthetic_dev': 8, 'train': 11}`
- Holdout pipe groups: [3, 4]

## 2. Synthetic performance (separate from measured)

- Selected: C=0.01, τ_prob=0.3
- Selection rule: on synthetic_dev: max scenario_recall, then row_recall, then min fp_row_rate
- Budget: {'C_grid': [0.01, 0.1, 1.0, 10.0, 100.0], 'tau_grid': [0.3, 0.5, 0.7, 0.85, 0.95], 'feature_sets': ['pressure_context_v1']}

| Split | Scenario recall | Row recall | FP row rate | n_pos rows | n_scen |
|-------|-----------------|------------|-------------|------------|--------|
| train_replay | 1.0 | 0.96875 | 0.5446147386101197 | 288 | 4 |
| synthetic_dev | 0.8 | 0.7277777777777777 | 0.4922055427251732 | 360 | 5 |
| synthetic_test | 0.8666666666666667 | 0.5407407407407407 | 0.5533927196744749 | 1080 | 15 |

Synthetic events are **not** additional independent real leak events.
Probability calibration is **not** claimed to transfer to measured data.

## 3. Measured 2018 transfer (diagnostic — prior examination)

Eligible onsets use the same post-14-day-prefix rule as FMR3C. Matching: joint chronological greedy (registered).

### DEV

Eligible onsets (n=8): p461(incipient), p232(incipient), p427(incipient), p673(abrupt), p628(incipient), p538(abrupt), p866(abrupt), p31(incipient)

| Detector | Abrupt 6h | Abrupt hits/n | Unmatched/wk | Dup24h | Union% | Episodes |
|----------|-----------|---------------|--------------|-------|--------|----------|
| Supervised pilot | **0.0** | 0/3 | 7.735 | 171 | 64.88 | 208 |
| Frozen FMR3C | **1.0** | 3/3 | 2.552 | 59 | 12.78 | 71 |

Supervised per-event (abrupt):

- HIT>6 p673 delay_h=8.25 notify=2018-03-06 00:00
- HIT>6 p538 delay_h=41.583333333333336 notify=2018-05-20 02:10
- HIT>6 p866 delay_h=17.583333333333332 notify=2018-06-02 02:40

Misses (all types under supervised):


### DIAG

Eligible onsets (n=4): p810(incipient), p183(abrupt), p158(abrupt), p369(abrupt)

| Detector | Abrupt 6h | Abrupt hits/n | Unmatched/wk | Dup24h | Union% | Episodes |
|----------|-----------|---------------|--------------|-------|--------|----------|
| Supervised pilot | **0.0** | 0/3 | 10.58 | 259 | 55.75 | 282 |
| Frozen FMR3C | **0.3333333333333333** | 1/3 | 0.07609 | 2 | 1.295 | 4 |

Supervised per-event (abrupt):

- HIT>6 p183 delay_h=20.166666666666668 notify=2018-08-07 22:45
- HIT>6 p158 delay_h=13.666666666666666 notify=2018-10-06 16:15
- HIT>6 p369 delay_h=10.583333333333334 notify=2018-10-26 12:40

Misses (all types under supervised):


## 4. Diagnosis

Synthetic test scenario recall=0.8666666666666667; DEV supervised abrupt6h=0.0 vs FMR3C=1.0; DIAG supervised=0.0 vs FMR3C=0.3333333333333333. **Transfer failure diagnosis: domain mismatch is the leading explanation** (separability exists under the nominal hydraulic model, but measured 2018 SCADA patterns are not recovered by the same linear score). Do not expand the simulator search in this pilot. Supervised unmatched/wk on DIAG=10.6 indicates burden may be unmanageable even if a few hits appear.

## Non-goals / stop

- No measured DIAG retuning
- No 2019 in this round
- No simulator/model search expansion
- FMR3C artifacts untouched

