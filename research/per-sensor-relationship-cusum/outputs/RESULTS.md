# Per-sensor relationship CUSUM — results

Generated: 2026-10-24T19:51:08-04:00

Independent experiment (not a LILA reproduction). Prior global offline retrospective screening remains a **preserved negative** result on its own question.

Primary metric: **notification time** (CUSUM crossing), not backdated change estimates. Abrupt success requires notify ∈ [onset, onset+7d]; pre-onset ≠ success.

Frozen per-sensor settings: `{'train_days': 14, 'n_refs': 3, 'cusum_k': 0.5, 'cusum_h': 8.0, 'recover_hours': 24.0}` gate_met=True
Frozen global settings: `{'train_days': 14, 'cusum_k': 0.5, 'cusum_h': 8.0, 'recover_hours': 12.0, 'n_refs': None}` gate_met=True

## DEV grid (every attempted setting)

- K=3 h=4.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=8.62 episodes=232
- K=3 h=4.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=1.97 episodes=56
- K=3 h=6.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=8.20 episodes=221
- K=3 h=6.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=1.86 episodes=54
- K=3 h=8.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=7.85 episodes=212
- K=3 h=8.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=1.78 episodes=53
- K=5 h=4.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=14.35 episodes=380
- K=5 h=4.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=2.24 episodes=63
- K=5 h=6.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=13.46 episodes=357
- K=5 h=6.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=2.20 episodes=63
- K=5 h=8.0 recover=12.0h → abrupt_recall=1.00 unmatched/wk=12.80 episodes=340
- K=5 h=8.0 recover=24.0h → abrupt_recall=0.67 unmatched/wk=2.24 episodes=63

### Global DEV grid

- h=4.0 recover=12.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=2
- h=4.0 recover=24.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=1
- h=6.0 recover=12.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=2
- h=6.0 recover=24.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=1
- h=8.0 recover=12.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=2
- h=8.0 recover=24.0h → abrupt_recall=0.00 unmatched/wk=0.00 episodes=1

## DIAG (frozen)

### Per-sensor
- Abrupt recall: **1.00** (3 onsets) delays={'n': 3, 'median': 0.3333333333333333, 'p90': 1.0666666666666667, 'max': 1.25}
- Incipient recall: **1.00** (2 onsets)
- Unmatched episodes/week: **1.22**
- Time in alarm (h): 105314.5; longest episode (h): 4076.8
- Duplicate unmatched within 24h: 27
- Ordinary controls: {'sampled_large_context_moves': 40, 'within_6h_of_notification': 0, 'fraction': 0.0}

#### Per-event

- HIT p654 (incipient) onset 2018-07-05 03:40 notify=2018-07-15 02:55 delay_h=239.25 sensor=n31 refs=['n1', 'n4', 'n549']
- HIT p810 (incipient) onset 2018-07-28 03:05 notify=2018-07-29 09:20 delay_h=30.25 sensor=n740 refs=['n722', 'n769', 'n296']
- HIT p183 (abrupt) onset 2018-08-07 02:35 notify=2018-08-07 03:50 delay_h=1.25 sensor=n726 refs=['n752', 'n769', 'n288']
- HIT p158 (abrupt) onset 2018-10-06 02:35 notify=2018-10-06 02:55 delay_h=0.3333333333333333 sensor=n288 refs=['n726', 'n752', 'n679']
- HIT p369 (abrupt) onset 2018-10-26 02:05 notify=2018-10-26 02:15 delay_h=0.16666666666666666 sensor=n410 refs=['n429', 'n415', 'n342']

### Global comparison
- Abrupt recall: **0.00**; unmatched/wk=0.00
- Incipient recall: 0.50
- Time in alarm (h): 4072.8; longest: 4072.8
- Delays: {'n': 0, 'median': None, 'p90': None, 'max': None}

#### Global per-event

- HIT p654 (incipient) notify=2018-07-15 07:10 delay_h=243.5
- MISS p810 (incipient) notify=None delay_h=None
- MISS p183 (abrupt) notify=None delay_h=None
- MISS p158 (abrupt) notify=None delay_h=None
- MISS p369 (abrupt) notify=None delay_h=None

## Chance comparison (notification circular shift)

{'n_abrupt_onsets': 3, 'observed_abrupt_matches': 3, 'null_n_valid_shifts': 89, 'null_match_median': 1.0, 'null_match_min': 0, 'null_match_max': 3, 'null_match_mean': 1.1910112359550562, 'fraction_shifts_ge_observed': 0.11235955056179775, 'caveat': 'Overlapping daily shifts are dependent probes; n abrupt events is small. Descriptive only — beating null is necessary, not sufficient.'}

## Where it fails / burden

Missed abrupt/incipient listed above. Per-sensor episodes=37 vs global=1. Common-mode and reference disturbance can suppress or spur signals (see DESIGN). Duplicate unmatched=27.

## Recommendation

**Limited research signal:** per-sensor signed residuals improve abrupt notification metrics vs global aggregation under equivalent rules, and beat the descriptive null. **Not** validated leak detection — independent evaluation required before any productization. Alert burden must remain explicit. Caveat: longest episode ~4077 h and total time-in-alarm ~105315 h show non-recovery / multi-sensor persistence — improvement is not free of burden. Per-sensor DIAG abrupt_recall=1.00 (unmatched/wk=1.22) vs global 0.00 (unmatched/wk=0.00). Null frac≥obs abrupt matches=0.11.

