# Context-conditioned residual experiment — paired results

Generated: 2026-10-24T20:13:23-04:00

Prior detectors and negative results preserved. Design: `CONTEXT_DESIGN.md`.
Notification policy: residual-recovery (`z≤k` ×12); **not swept**.

Frozen alpha (DEV chronological val): **0.1**
Alpha DEV scores (mean RMSE m): {0.1: 0.02543221880657986, 1.0: 0.025610327381963928, 10.0: 0.02565777247509768, 100.0: 0.02575490383687805, 1000.0: 0.026113364269456592}

## DEV (recorded before DIAG)

### baseline_raw_residual
- Abrupt recall: **1.00** delays={'n': 3, 'median': 0.0, 'max': 0.75, 'values': [0.0, 0.75, 0.0]}
- Incipient: **1.00**
- Unmatched/wk: **109.72**; dup: 2837
- Union occ%: 99.98; summed sensor-alarm%: 41.31
- Longest (h): 1014.6666666666666; censored: 17

### context_corrected
- Abrupt recall: **1.00** delays={'n': 3, 'median': 0.0, 'max': 1.25, 'values': [0.0, 1.25, 0.0]}
- Incipient: **1.00**
- Unmatched/wk: **91.43**; dup: 2364
- Union occ%: 99.98; summed sensor-alarm%: 39.56
- Longest (h): 1155.0; censored: 17

## DIAG (diagnostic — not independent validation)

### baseline_raw_residual
- Abrupt recall: **1.00** delays={'n': 3, 'median': 0.0, 'max': 0.25, 'values': [0.0, 0.0, 0.25]}
- Incipient: **1.00**
- Unmatched/wk: **88.98**; dup: 2339
- Union occ%: 99.95; summed%: 31.39
- Longest (h): 3544.0833333333335; censored: 11

- HIT p810 (incipient) notify=2018-07-28 03:35 delay_h=0.5 sensor=n54
- HIT p183 (abrupt) notify=2018-08-07 02:35 delay_h=0.0 sensor=n752
- HIT p158 (abrupt) notify=2018-10-06 02:35 delay_h=0.0 sensor=n644
- HIT p369 (abrupt) notify=2018-10-26 02:20 delay_h=0.25 sensor=n410

Prefix (separate):

- HIT p654 notify=2018-07-15 01:45

### context_corrected
- Abrupt recall: **1.00** delays={'n': 3, 'median': 0.0, 'max': 0.08333333333333333, 'values': [0.0, 0.0, 0.08333333333333333]}
- Incipient: **1.00**
- Unmatched/wk: **79.59**; dup: 2092
- Union occ%: 99.90; summed%: 33.82
- Longest (h): 3543.75; censored: 12

- HIT p810 (incipient) notify=2018-07-28 05:45 delay_h=2.6666666666666665 sensor=n1
- HIT p183 (abrupt) notify=2018-08-07 02:35 delay_h=0.0 sensor=n752
- HIT p158 (abrupt) notify=2018-10-06 02:35 delay_h=0.0 sensor=n644
- HIT p369 (abrupt) notify=2018-10-26 02:10 delay_h=0.08333333333333333 sensor=n410

Prefix (separate):

- HIT p654 notify=2018-07-15 03:25

Ordinary frac(z>k): baseline=0.312, context=0.324

## Signal preservation (abrupt DIAG)

### p183 — explains_away=False
| Target | Δz base | Δz ctx | Δraw base (m) | Δraw ctx (m) |
|--------|---------|--------|---------------|--------------|
| n752 | 9.66 | 10.79 | 0.057 | 0.059 |
| n288 | -4.18 | -6.17 | -0.035 | -0.038 |
| n726 | 3.19 | 2.85 | 0.016 | 0.015 |

### p158 — explains_away=False
| Target | Δz base | Δz ctx | Δraw base (m) | Δraw ctx (m) |
|--------|---------|--------|---------------|--------------|
| n644 | 9.49 | 10.33 | 0.198 | 0.202 |
| n342 | 3.37 | 2.92 | 0.039 | 0.031 |
| n613 | 2.82 | 3.00 | 0.019 | 0.019 |

### p369 — explains_away=False
| Target | Δz base | Δz ctx | Δraw base (m) | Δraw ctx (m) |
|--------|---------|--------|---------------|--------------|
| n410 | 3.52 | 9.32 | 0.229 | 0.178 |
| n636 | -3.00 | -3.03 | -0.048 | -0.043 |
| n679 | 2.08 | 2.57 | 0.032 | 0.021 |

## Pump transition vs stable (ordinary)
{'mean_abs_z_base_large_pump_delta': 1.3363561325428726, 'mean_abs_z_ctx_large_pump_delta': 1.5335789082262166, 'mean_abs_z_base_stable_pump': 1.334480247437406, 'mean_abs_z_ctx_stable_pump': 1.3715669815955005}

## 0–2 h notification shifted null
- Baseline: {'window': '0–2 h post-onset (no pre-onset credit)', 'n_abrupt_onsets': 3, 'observed_abrupt_matches': 3, 'null_n_valid_shifts': 89, 'null_match_median': 2.0, 'null_match_min': 0, 'null_match_max': 3, 'null_match_mean': 1.9662921348314606, 'fraction_shifts_ge_observed': 0.15730337078651685, 'caveat': 'Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.', 'per_onset': [{'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': True, 'notify_time': '2018-07-28 03:35', 'delay_hours': 0.5, 'stream_id': 'n54', 'already_active_at_onset': []}, {'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': True, 'notify_time': '2018-08-07 02:35', 'delay_hours': 0.0, 'stream_id': 'n752', 'already_active_at_onset': []}, {'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 02:35', 'delay_hours': 0.0, 'stream_id': 'n644', 'already_active_at_onset': []}, {'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': True, 'notify_time': '2018-10-26 02:20', 'delay_hours': 0.25, 'stream_id': 'n410', 'already_active_at_onset': []}]}
- Context: {'window': '0–2 h post-onset (no pre-onset credit)', 'n_abrupt_onsets': 3, 'observed_abrupt_matches': 3, 'null_n_valid_shifts': 89, 'null_match_median': 1.0, 'null_match_min': 0, 'null_match_max': 3, 'null_match_mean': 1.2696629213483146, 'fraction_shifts_ge_observed': 0.056179775280898875, 'caveat': 'Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.', 'per_onset': [{'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'already_active_at_onset': [{'stream': 'n114', 'notify': '2018-07-26 12:30'}, {'stream': 'n613', 'notify': '2018-07-26 23:15'}, {'stream': 'n296', 'notify': '2018-07-27 14:00'}, {'stream': 'n4', 'notify': '2018-07-27 21:40'}, {'stream': 'n215', 'notify': '2018-07-27 23:55'}, {'stream': 'n516', 'notify': '2018-07-28 00:10'}, {'stream': 'n229', 'notify': '2018-07-28 00:20'}, {'stream': 'n188', 'notify': '2018-07-28 00:40'}]}, {'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': True, 'notify_time': '2018-08-07 02:35', 'delay_hours': 0.0, 'stream_id': 'n752', 'already_active_at_onset': []}, {'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 02:35', 'delay_hours': 0.0, 'stream_id': 'n644', 'already_active_at_onset': []}, {'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': True, 'notify_time': '2018-10-26 02:10', 'delay_hours': 0.08333333333333333, 'stream_id': 'n410', 'already_active_at_onset': []}]}

## Recommendation

**No-go:** context correction fails to meaningfully reduce ordinary excursions / alert burden under the fixed residual-recovery policy. DIAG abrupt recall base=1.00 ctx=1.00; unmatched/wk 89.0→79.6; union occ% 100.0→99.9; summed sensor-alarm% 31.4→33.8; frac(z>k) 0.312→0.324. 0–2h null frac≥obs: base=0.16 (obs=3, null med=2.0, n_shifts=89); ctx=0.06 (obs=3, null med=1.0).

