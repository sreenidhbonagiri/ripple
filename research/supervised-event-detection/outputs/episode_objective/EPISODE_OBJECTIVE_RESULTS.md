# Episode-objective alignment pilot

Generated: 2026-10-24T22:46:44-04:00

Corrects the **model/threshold selection objective** to match measured six-hour **episode-notification** semantics. Same scenarios, splits, features, labels, preprocessing, and L2 logistic family as the original synthetic pilot.

**Preserves** original `pilot_*` artifacts and `TARGET_ALIGNMENT_BEFORE_ABLATION.md`. **Not** a feature ablation; **no** new simulations; **no** 2019.

## Labels (unchanged)

y=1 is the registered 6h recent-onset credit window, not ongoing leak presence. Labels unchanged for this controlled comparison.

## Selection rule (declared before run)

on synthetic_dev full trajectories: among (C,τ) with episode_6h_recall>=0.666667 and control_episodes_per_week<=3, max episode_6h_recall, then min control_episodes_per_week, then min median_delay_h, then min C, then min τ. If no candidate passes gates: report selection_failure=true and freeze rank-best under the same ordering without gates (gate_met=false).

- Gates: episode_6h_recall ≥ 0.666667; control_episodes_per_week ≤ 3
- Budget: C∈[0.01, 0.1, 1.0, 10.0, 100.0], τ∈[0.3, 0.5, 0.7, 0.85, 0.95]
- Tests: passed

## DEV grid (all attempted settings)

| C | τ | ep6h recall | ctrl ep/wk | med delay h | row scen | blocked | disagree | gates |
|---|---|-------------|------------|-------------|----------|---------|----------|-------|
| 0.01 | 0.3 | 0.2 | 12.83 | 1.3333333333333333 | 0.8 | 4 | 3 | fail |
| 0.01 | 0.5 | 0.2 | 15.17 | 3.25 | 0.8 | 4 | 3 | fail |
| 0.01 | 0.7 | 0.4 | 3.5 | 5.208333333333333 | 0.4 | 1 | 0 | fail |
| 0.01 | 0.85 | 0 | 0 | None | 0 | 0 | 0 | fail |
| 0.01 | 0.95 | 0 | 0 | None | 0 | 0 | 0 | fail |
| 0.1 | 0.3 | 0.2 | 18.67 | 0.5833333333333334 | 0.8 | 4 | 3 | fail |
| 0.1 | 0.5 | 0.4 | 12.83 | 3.25 | 0.8 | 4 | 2 | fail |
| 0.1 | 0.7 | 0.4 | 5.833 | 4.958333333333334 | 0.6 | 3 | 1 | fail |
| 0.1 | 0.85 | 0 | 0 | None | 0 | 0 | 0 | fail |
| 0.1 | 0.95 | 0 | 0 | None | 0 | 0 | 0 | fail |
| 1.0 | 0.3 | 0 | 16.33 | None | 0.8 | 5 | 4 | fail |
| 1.0 | 0.5 | 0.4 | 14 | 3.25 | 0.8 | 4 | 2 | fail |
| 1.0 | 0.7 | 0.6 | 8.167 | 4.0 | 0.6 | 3 | 0 | fail |
| 1.0 | 0.85 | 0.2 | 5.833 | 5.833333333333333 | 0.2 | 1 | 0 | fail |
| 1.0 | 0.95 | 0 | 2.333 | None | 0 | 0 | 0 | fail |
| 10.0 | 0.3 | 0.2 | 16.33 | 2.9166666666666665 | 0.8 | 5 | 3 | fail |
| 10.0 | 0.5 | 0.4 | 12.83 | 2.666666666666667 | 0.8 | 4 | 2 | fail |
| 10.0 | 0.7 | 0.6 | 7 | 4.583333333333333 | 0.8 | 4 | 1 | fail |
| 10.0 | 0.85 | 0.4 | 5.833 | 3.8333333333333335 | 0.4 | 1 | 0 | fail |
| 10.0 | 0.95 | 0 | 2.333 | None | 0 | 0 | 0 | fail |
| 100.0 | 0.3 | 0.2 | 16.33 | 2.9166666666666665 | 0.8 | 5 | 3 | fail |
| 100.0 | 0.5 | 0.4 | 12.83 | 2.75 | 0.8 | 4 | 2 | fail |
| 100.0 | 0.7 | 0.4 | 8.167 | 4.125 | 0.8 | 4 | 2 | fail |
| 100.0 | 0.85 | 0.4 | 7 | 2.7083333333333335 | 0.4 | 1 | 0 | fail |
| 100.0 | 0.95 | 0 | 7 | None | 0 | 0 | 0 | fail |

## Freeze

- Selected: **C=10.0, τ=0.7**
- gate_met: **False**
- selection_failure: **True**
- DEV episode_6h_recall: 0.6
- DEV control_episodes_per_week: 7.0
- DEV median_delay_h: 4.583333333333333

**Selection failure:** no candidate met both provisional gates. Rank-best under the declared ordering was frozen with `gate_met=false` for diagnostic follow-through only — not a claim of success.

## Synthetic evaluation (episode headline; row-credit for discrepancy)

Synthetic metrics are **not** combined with measured accuracy.

| Split | episode_6h | row_credit scen | med delay h | ctrl ep/wk | blocked | disagree |
|-------|------------|-----------------|-------------|------------|---------|----------|
| synthetic_dev | 0.6 (3/5) | 0.8 | 4.583333333333333 | 7 | 4 | 1 |
| synthetic_test | 0.4667 (7/15) | 0.6 | 5.583333333333333 | 5.25 | 8 | 4 |

Original row-table metrics at frozen (C,τ) (not selection objective):

- synthetic_dev: scenario_recall(row)=0.8, row_recall=0.21666666666666667, fp_row_rate=0.13683602771362588
- synthetic_test: scenario_recall(row)=0.6, row_recall=0.175, fp_row_rate=0.1445067634444078

### Synthetic test per-leak

- MISS leak_000_p282 delay_h=None row_credit=False blocked=True n_ep=3 preonset=[200, 292]
- MISS leak_001_p299 delay_h=None row_credit=False blocked=False n_ep=3 preonset=[200, 292]
- HIT6 leak_002_p69 delay_h=5.833333333333333 row_credit=True blocked=False n_ep=2 preonset=[]
- MISS leak_003_p435 delay_h=None row_credit=False blocked=True n_ep=2 preonset=[199]
- MISS leak_005_p443 delay_h=None row_credit=False blocked=False n_ep=4 preonset=[199, 283]
- HIT6 leak_008_p576 delay_h=5.0 row_credit=True blocked=False n_ep=4 preonset=[199, 286]
- HIT6 leak_009_p210 delay_h=1.5 row_credit=True blocked=False n_ep=4 preonset=[199]
- HIT6 leak_010_p607 delay_h=5.833333333333333 row_credit=True blocked=True n_ep=3 preonset=[199]
- MISS leak_011_p19 delay_h=None row_credit=False blocked=False n_ep=3 preonset=[200, 292]
- MISS leak_012_p801 delay_h=None row_credit=True blocked=True n_ep=4 preonset=[199, 283]
- MISS leak_015_p655 delay_h=None row_credit=True blocked=True n_ep=2 preonset=[199]
- HIT6 leak_017_p445 delay_h=5.083333333333333 row_credit=True blocked=False n_ep=3 preonset=[200, 292]
- HIT6 leak_018_p513 delay_h=6.0 row_credit=False blocked=True n_ep=4 preonset=[199]
- HIT6 leak_021_p800 delay_h=5.583333333333333 row_credit=True blocked=True n_ep=4 preonset=[199]
- MISS leak_023_p891 delay_h=None row_credit=True blocked=True n_ep=3 preonset=[200, 292]

## Measured 2018 (diagnostic — no retune; prior examination)

Same notifier as synthetic. Headline = abrupt 6h episode notification. Not combined with synthetic figures into one accuracy.

### DEV

- Eligible onsets: 8
- Abrupt 6h recall: **0.0** (0/3)
- Delays (h): []
- Episodes: 173; unmatched/wk: 6.42; dup24h unmatched: 151
- Occupancy union%: 9.062

Per abrupt event:

- HIT>6 p673 delay_h=110.41666666666667 notify=2018-03-10 06:10
- MISS p538 delay_h=None notify=None
- HIT>6 p866 delay_h=21.25 notify=2018-06-02 06:20

Misses (all types):

- MISS p538 (abrupt) onset=2018-05-18 08:35

### DIAG

- Eligible onsets: 4
- Abrupt 6h recall: **0.6666666666666666** (2/3)
- Delays (h): [2.6666666666666665, 2.25]
- Episodes: 227; unmatched/wk: 8.484; dup24h unmatched: 206
- Occupancy union%: 13.7

Per abrupt event:

- HIT>6 p183 delay_h=21.416666666666668 notify=2018-08-08 00:00
- HIT6 p158 delay_h=2.6666666666666665 notify=2018-10-06 05:15
- HIT6 p369 delay_h=2.25 notify=2018-10-26 04:20

Misses (all types):


## Diagnosis

Selection gate_met=False selection_failure=True frozen C=10.0 τ=0.7. Synthetic test episode_6h_recall=0.4666666666666667 vs row_credit_scenario_recall=0.6 (disagree scenarios=4; blocked_preonset=8). Measured abrupt6h DEV=0.0 DIAG=0.6666666666666666 (diagnostic only; not retuned). Row-credit vs episode-notification discrepancy is present under the shared notifier — selection now targets the episode objective. No grid point met provisional gates; frozen candidate is rank-best without gates and must not be read as a successful gate pass.

## Non-goals

- No feature ablation, new simulations, or 2019
- No main merge, Tiger, UI, deployment
- Original row-hit pilot remains archived baseline

