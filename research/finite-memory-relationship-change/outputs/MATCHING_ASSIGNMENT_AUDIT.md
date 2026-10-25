# Matching-assignment audit — frozen FMR3C DIAG notifications

Generated: 2026-10-24T22:02:49-04:00

Preserves original registered evaluation, `EMPIRICAL_CALIBRATION_RESULTS.md`, scores, thresholds, and notification lists. **No** detector re-tuning.

Frozen notifications: LQ=2h, LR=48h, τ=26.7329 (DIAG replay for audit).

## 1. Matching conflict: p810 vs p183

Temporal proximity does **not** prove which leak caused a notification.

### p810

- Type / onset / end / peak: **incipient** / 2018-07-28 03:05 / 2019-12-31 23:55 / 2018-11-02 22:25
- Matching interval: `2018-07-28 03:05` → `2018-08-11 03:05`
- Original assignment (view A): {'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': True, 'notify_time': '2018-08-07 03:35', 'delay_hours': 240.5, 'stream_id': 'n752', 'episode_idx': 0}

Eligible notifications (full window):

- ep#0 n752 @ 2018-08-07 03:35 delay_h=240.5 — **assigned to this event under A**

### p183

- Type / onset / end / peak: **abrupt** / 2018-08-07 02:35 / 2018-09-01 17:10 / 2018-08-07 02:35
- Matching interval: `2018-08-07 02:35` → `2018-08-14 02:35`
- Original assignment (view A): {'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'episode_idx': None}

Eligible notifications (full window):

- ep#0 n752 @ 2018-08-07 03:35 delay_h=1 — **unavailable under A** (assigned to p810)

### Independent eligibility support for p810?

- n eligible for p810: 1
- shared with p183 window: 1
- exclusive to p810 window: 0
- exclusive list: []

If exclusive_to_p810_window is empty, p810's only eligible notifies also fall in p183's window (or there are none). Presence of exclusive notifies would be independent eligibility support for p810 — still not proof of causation.

### Does joint assignment resolve the conflict?

Joint max-cardinality (C) assigns a notify to p183 (2018-08-07 03:35, ep=0) while A left p183 unmatched. Under C, p810 matched=False (notify=None). This **reassigns credit** among competing eligibility windows — it does not prove the notification was caused by p183, nor that the conflict is 'resolved' in a causal sense; it shows the chronological greedy rule (A) chose a different one-to-one allocation (A: p810→2018-08-07 03:35, p183 unmatched).

## 2. Evaluation views

### View A: Original registered evaluation (unchanged)

- Post-hoc diagnostic: **False**
- Onsets chronological; each takes earliest unused notification in its type-specific eligibility window (abrupt 7d / incipient to peak∩14d).

- Abrupt recall: **0.3333333333333333** (n=3)
- Incipient recall: 1.0
- Abrupt delays: {'n': 1, 'median': 0.9166666666666666, 'values': [0.9166666666666666]}
- Unmatched episodes: 2 (0.07609/wk)

Assignments:

- HIT p810 (incipient) notify=2018-08-07 03:35 delay_h=240.5 sensor=n752 ep=0
- MISS p183 (abrupt) notify=None delay_h=None sensor=None ep=None
- HIT p158 (abrupt) notify=2018-10-06 03:30 delay_h=0.9166666666666666 sensor=n644 ep=1
- MISS p369 (abrupt) notify=None delay_h=None sensor=None ep=None

Shifted null (same assignment procedure as view A):

- Observed abrupt matches: **1** / 3
- Null median (min–max): 0.0 (0–2)
- Frac shifts ≥ obs: **0.30**
- Same assignment view applied to circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

### View B: Post-hoc diagnostic: abrupt-only matching

- Post-hoc diagnostic: **True**
- Same chronological greedy rule, but only abrupt onsets compete for notifications. Measures abrupt-onset sensitivity, not joint detection of all leaks. Incipient events are excluded (not scored as misses).

- Abrupt recall: **0.6666666666666666** (n=3)
- Incipient recall: None
- Abrupt delays: {'n': 2, 'median': 0.9583333333333333, 'values': [1.0, 0.9166666666666666]}
- Unmatched episodes: 2 (0.07609/wk)

Assignments:

- HIT p183 (abrupt) notify=2018-08-07 03:35 delay_h=1.0 sensor=n752 ep=0
- HIT p158 (abrupt) notify=2018-10-06 03:30 delay_h=0.9166666666666666 sensor=n644 ep=1
- MISS p369 (abrupt) notify=None delay_h=None sensor=None ep=None

Excluded from scoring (incipient):
- p810 (incipient) excluded_from_abrupt_only_view

Shifted null (same assignment procedure as view B):

- Observed abrupt matches: **2** / 3
- Null median (min–max): 0.0 (0–2)
- Frac shifts ≥ obs: **0.07**
- Same assignment view applied to circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

### View C: Post-hoc diagnostic: joint max-cardinality + min-sum-delay

- Post-hoc diagnostic: **True**
- Bipartite assignment over original eligibility windows. Maximize number of matched events; among maxima minimize sum of notification delays (Hungarian / linear_sum_assignment). One notification → at most one event. Does not prove causation from temporal proximity.
- Tie-break: Primary: maximum cardinality (dummy cost >> any delay). Secondary: minimize sum of delay_hours on assigned edges. Tertiary: deterministic solver output for the fixed cost matrix.

- Abrupt recall: **0.6666666666666666** (n=3)
- Incipient recall: 0.0
- Abrupt delays: {'n': 2, 'median': 0.9583333333333333, 'values': [1.0, 0.9166666666666666]}
- Unmatched episodes: 2 (0.07609/wk)

Assignments:

- MISS p810 (incipient) notify=None delay_h=None sensor=None ep=None
- HIT p183 (abrupt) notify=2018-08-07 03:35 delay_h=1.0 sensor=n752 ep=0
- HIT p158 (abrupt) notify=2018-10-06 03:30 delay_h=0.9166666666666666 sensor=n644 ep=1
- MISS p369 (abrupt) notify=None delay_h=None sensor=None ep=None

Shifted null (same assignment procedure as view C):

- Observed abrupt matches: **2** / 3
- Null median (min–max): 0.0 (0–2)
- Frac shifts ≥ obs: **0.07**
- Same assignment view applied to circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

## 3. Miss classification (primary period onsets)

p369 remains a **genuine unresolved signal failure** (weak score); matching corrections do not solve it.

- **p654** (incipient): `training_prefix_ineligibility` — Onset before pairwise-training end; excluded from primary recall. | A=None | B=None | C=None
- **p810** (incipient): `matched_under_A` — Matched under original view A. | A={'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': True, 'notify_time': '2018-08-07 03:35', 'delay_hours': 240.5, 'stream_id': 'n752', 'episode_idx': 0} | B=None | C={'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'episode_idx': None}
- **p183** (abrupt): `assignment_ambiguity_or_conflict` — Eligible notification(s) exist but chronological greedy assigned them elsewhere (or left unmatched under competition). | A={'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'episode_idx': None} | B={'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': True, 'notify_time': '2018-08-07 03:35', 'delay_hours': 1.0, 'stream_id': 'n752', 'refs_used': ['n726', 'n769', 'n288'], 'change_estimate_time': '2018-08-07 03:35', 'open_leaks_at_notify': 6, 'episode_end': '2018-08-08 05:25', 'episode_idx': 0} | C={'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': True, 'notify_time': '2018-08-07 03:35', 'delay_hours': 1.0, 'stream_id': 'n752', 'episode_idx': 0}
- **p158** (abrupt): `matched_under_A` — Matched under original view A. | A={'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 03:30', 'delay_hours': 0.9166666666666666, 'stream_id': 'n644', 'episode_idx': 1} | B={'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 03:30', 'delay_hours': 0.9166666666666666, 'stream_id': 'n644', 'refs_used': ['n636', 'n679', 'n332'], 'change_estimate_time': '2018-10-06 03:30', 'open_leaks_at_notify': 5, 'episode_end': '2018-10-07 05:30', 'episode_idx': 1} | C={'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 03:30', 'delay_hours': 0.9166666666666666, 'stream_id': 'n644', 'episode_idx': 1}
- **p369** (abrupt): `genuine_signal_failure_weak_score` — Preserved transfer diagnosis: 6 h network max ≪ τ and overlaps ordinary same-month controls. Matching views cannot create a score. | A={'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'episode_idx': None} | B={'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'refs_used': None, 'pre_onset_notifications_nearby': 0} | C={'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None, 'episode_idx': None}

## 4. Summary

View A (registered): abrupt_recall=0.3333333333333333, p183 matched=False, p810 matched=True. View B (abrupt-only, post-hoc): abrupt_recall=0.6666666666666666, p183 matched=True. View C (joint max-cardinality, post-hoc): abrupt_recall=0.6666666666666666, p183 matched=True, p810 matched=False. p369 remains unmatched across views when no eligible notify exists — signal failure. B/C must not replace A as the registered headline.

## Non-goals

- Original EMPIRICAL / RESULTS reports untouched as the registered headline
- No threshold change, 2019, UI, Tiger, deployment, or main merge

