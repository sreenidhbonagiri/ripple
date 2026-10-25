# Paired comparison — residual-normalization recovery variant

Generated: 2026-10-24T20:00:24-04:00

Original frozen detector/settings/RESULTS preserved. Variant registered in `VARIANT_RESIDUAL_RECOVERY.md` (12-step \(z\le k\) recovery; not swept).

Shared settings: `{'train_days': 14, 'n_refs': 3, 'cusum_k': 0.5, 'cusum_h': 8.0, 'recover_hours': 24.0}`
Variant residual_recover_steps: **12**

## DEV (recorded before DIAG; no retune)

### original_cusum_zero
- Post-training abrupt recall: **0.67** delays={'n': 2, 'median': 0.4583333333333333, 'max': 0.6666666666666666, 'values': [0.25, 0.6666666666666666]}
- Incipient recall: **0.80**
- Unmatched notifications/wk: **1.82**; dup unmatched 24h: 40
- Summed sensor-alarm: 113751.8 h (86.00%)
- Union occupancy: 4007.2 h (99.98%)
- Longest episode (h): 4007.1666666666665; right-censored: 31/53

### variant_residual_le_k
- Post-training abrupt recall: **1.00** delays={'n': 3, 'median': 0.0, 'max': 0.08333333333333333, 'values': [0.0, 0.08333333333333333, 0.0]}
- Incipient recall: **1.00**
- Unmatched notifications/wk: **91.77**; dup unmatched 24h: 2373
- Summed sensor-alarm: 44358.3 h (33.54%)
- Union occupancy: 4007.2 h (99.98%)
- Longest episode (h): 1014.6666666666666; right-censored: 13/2381

## DIAG (frozen; no retune)

### original_cusum_zero
- Post-training abrupt recall: **1.00** delays={'n': 3, 'median': 0.3333333333333333, 'max': 1.25, 'values': [1.25, 0.3333333333333333, 0.16666666666666666]}
- Incipient recall: **1.00**
- Unmatched/wk: **1.26**; dup: 28
- Summed sensor-alarm %: 78.22
- Union occupancy %: 99.93
- Longest (h): 4076.8333333333335; right-censored: 25

Per-event (primary eligible):

- HIT p810 (incipient) notify=2018-07-29 09:20 delay_h=30.25 sensor=n740
- HIT p183 (abrupt) notify=2018-08-07 03:50 delay_h=1.25 sensor=n726
- HIT p158 (abrupt) notify=2018-10-06 02:55 delay_h=0.3333333333333333 sensor=n288
- HIT p369 (abrupt) notify=2018-10-26 02:15 delay_h=0.16666666666666666 sensor=n410

Prefix onsets (separate; not in primary):

- HIT p654 (incipient) onset=2018-07-05 03:40 notify=2018-07-15 02:55

### variant_residual_le_k
- Post-training abrupt recall: **1.00** delays={'n': 3, 'median': 0.08333333333333333, 'max': 0.16666666666666666, 'values': [0.08333333333333333, 0.0, 0.16666666666666666]}
- Incipient recall: **1.00**
- Unmatched/wk: **77.23**; dup: 2030
- Summed sensor-alarm %: 25.72
- Union occupancy %: 99.85
- Longest (h): 3543.75; right-censored: 8

Per-event (primary eligible):

- HIT p810 (incipient) notify=2018-07-28 03:30 delay_h=0.4166666666666667 sensor=n54
- HIT p183 (abrupt) notify=2018-08-07 02:40 delay_h=0.08333333333333333 sensor=n54
- HIT p158 (abrupt) notify=2018-10-06 02:35 delay_h=0.0 sensor=n644
- HIT p369 (abrupt) notify=2018-10-26 02:15 delay_h=0.16666666666666666 sensor=n410

Prefix onsets (separate; not in primary):

- HIT p654 (incipient) onset=2018-07-05 03:40 notify=2018-07-15 02:55

### Hit retention (original → variant, primary eligible)
- Retained: [{'pipe': 'p810', 'type': 'incipient', 'orig_delay': 30.25, 'var_delay': 0.4166666666666667, 'orig_sensor': 'n740', 'var_sensor': 'n54'}, {'pipe': 'p183', 'type': 'abrupt', 'orig_delay': 1.25, 'var_delay': 0.08333333333333333, 'orig_sensor': 'n726', 'var_sensor': 'n54'}, {'pipe': 'p158', 'type': 'abrupt', 'orig_delay': 0.3333333333333333, 'var_delay': 0.0, 'orig_sensor': 'n288', 'var_sensor': 'n644'}, {'pipe': 'p369', 'type': 'abrupt', 'orig_delay': 0.16666666666666666, 'var_delay': 0.16666666666666666, 'orig_sensor': 'n410', 'var_sensor': 'n410'}]
- Lost: []
- Gained: []

## Chance comparison (variant DIAG, eligible abrupt)

### Registered 0–7 day window
{'n_abrupt_onsets': 3, 'observed_abrupt_matches': 3, 'null_n_valid_shifts': 89, 'null_match_median': 3.0, 'null_match_min': 3, 'null_match_max': 3, 'null_match_mean': 3.0, 'fraction_shifts_ge_observed': 1.0, 'caveat': 'Overlapping daily shifts are dependent probes; n abrupt events is small. Descriptive only — beating null is necessary, not sufficient.'}

### Diagnostic 0–2 hour window
{'window': '0–2 h post-onset (no pre-onset credit)', 'n_abrupt_onsets': 3, 'observed_abrupt_matches': 3, 'null_n_valid_shifts': 89, 'null_match_median': 2.0, 'null_match_min': 1, 'null_match_max': 3, 'null_match_mean': 2.3820224719101124, 'fraction_shifts_ge_observed': 0.47191011235955055, 'caveat': 'Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.', 'per_onset': [{'pipe': 'p810', 'leak_type': 'incipient', 'onset': '2018-07-28 03:05', 'matched': True, 'notify_time': '2018-07-28 03:30', 'delay_hours': 0.4166666666666667, 'stream_id': 'n54', 'already_active_at_onset': []}, {'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': True, 'notify_time': '2018-08-07 02:40', 'delay_hours': 0.08333333333333333, 'stream_id': 'n54', 'already_active_at_onset': []}, {'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 02:35', 'delay_hours': 0.0, 'stream_id': 'n644', 'already_active_at_onset': []}, {'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': True, 'notify_time': '2018-10-26 02:15', 'delay_hours': 0.16666666666666666, 'stream_id': 'n410', 'already_active_at_onset': []}]}

## Remaining problems (no normalization change)

{'targets_with_min_pair_scale_lt_0.05': [{'target': 'n4', 'min_scale': 0.03718095064724838, 'scales': [0.03718095064724838, 0.04125821652395399, 0.3068682543058696]}, {'target': 'n105', 'min_scale': 0.005064823402854322, 'scales': [0.005064823402854322, 0.006955504477095179, 0.009787347545989769]}, {'target': 'n114', 'min_scale': 0.010871721674126285, 'scales': [0.010871721674126285, 0.011369835481603668, 0.014401360593463631]}, {'target': 'n163', 'min_scale': 0.006133200876692425, 'scales': [0.006133200876692425, 0.009232638336804195, 0.009967327366390524]}, {'target': 'n188', 'min_scale': 0.009795044284294374, 'scales': [0.009795044284294374, 0.011579282198307415, 0.015538975565044352]}, {'target': 'n215', 'min_scale': 0.006047849898437494, 'scales': [0.006136132145144525, 0.006082780866824246, 0.006047849898437494]}, {'target': 'n229', 'min_scale': 0.022597529443887484, 'scales': [0.022597529443887484, 0.024524346175166002, 0.026157528203311284]}, {'target': 'n288', 'min_scale': 0.009989769039369755, 'scales': [0.009989769039369755, 0.011927633070999193, 0.01460609928011242]}, {'target': 'n296', 'min_scale': 0.006842721897660883, 'scales': [0.006842721897660883, 0.007915844266222298, 0.00847723725616304]}, {'target': 'n332', 'min_scale': 0.008525798778226543, 'scales': [0.009482231272840856, 0.008525798778226543, 0.01671376085122651]}, {'target': 'n342', 'min_scale': 0.012012460453905104, 'scales': [0.012012460453905104, 0.016153128568742046, 0.025485045647960357]}, {'target': 'n410', 'min_scale': 0.014370259408923433, 'scales': [0.014370259408923433, 0.06441488801572519, 0.06573468308521827]}, {'target': 'n415', 'min_scale': 0.015469048218876758, 'scales': [0.017758934096792373, 0.015469048218876758, 0.024635716078476658]}, {'target': 'n429', 'min_scale': 0.013892855823225945, 'scales': [0.013892855823225945, 0.06373119443111526, 0.06345036337985072]}, {'target': 'n458', 'min_scale': 0.012120744027026058, 'scales': [0.012120744027026058, 0.018734518344242654, 0.016412837821974984]}, {'target': 'n469', 'min_scale': 0.005255492230857072, 'scales': [0.005255492230857072, 0.009459330649596632, 0.01006582413836856]}, {'target': 'n495', 'min_scale': 0.005443911598981537, 'scales': [0.005443911598981537, 0.006728098615113057, 0.00925274936628309]}, {'target': 'n506', 'min_scale': 0.007615875364531224, 'scales': [0.007615875364531224, 0.010269613067138628, 0.011044474890388418]}, {'target': 'n516', 'min_scale': 0.012976615671475029, 'scales': [0.012976615671475029, 0.016151522243546722, 0.016697894122769355]}, {'target': 'n519', 'min_scale': 0.00877978267475275, 'scales': [0.00877978267475275, 0.010241666272037273, 0.015036438774947935]}, {'target': 'n549', 'min_scale': 0.00935787729358834, 'scales': [0.00935787729358834, 0.013009974692269485, 0.016951611306004314]}, {'target': 'n613', 'min_scale': 0.006238154269245694, 'scales': [0.006238154269245694, 0.012030369439746568, 0.010844317751309562]}, {'target': 'n636', 'min_scale': 0.013809774714381317, 'scales': [0.013809774714381317, 0.016749720965849764, 0.016949026648618373]}, {'target': 'n644', 'min_scale': 0.022629423479597458, 'scales': [0.025915089226920023, 0.022629423479597458, 0.028640900711564606]}, {'target': 'n679', 'min_scale': 0.013849307017001516, 'scales': [0.013849307017001516, 0.01800715018811247, 0.02005288952526265]}, {'target': 'n722', 'min_scale': 0.007304969252497163, 'scales': [0.007304969252497163, 0.008008662428777489, 0.007775989097632603]}, {'target': 'n726', 'min_scale': 0.005814637294701553, 'scales': [0.005814637294701553, 0.008030185404733763, 0.009151166321949794]}, {'target': 'n740', 'min_scale': 0.005328395232030392, 'scales': [0.0057269848249336475, 0.005328395232030392, 0.006198388335724954]}, {'target': 'n752', 'min_scale': 0.006034276658723611, 'scales': [0.006034276658723611, 0.00791448075828063, 0.011245449800123023]}, {'target': 'n769', 'min_scale': 0.005850500406492439, 'scales': [0.005850500406492439, 0.006311469977149693, 0.007408407720299914]}], 'n_targets_tiny_scale': 30, 'frac_finite_z_gt_k_on_notifying_streams': {'n1': 0.21942401960784313, 'n4': 0.298672385620915, 'n31': 0.24027777777777778, 'n54': 0.1679330065359477, 'n105': 0.23621323529411764, 'n114': 0.25214460784313725, 'n188': 0.5260825163398692, 'n215': 0.1991830065359477, 'n229': 0.3088235294117647, 'n288': 0.32681781045751634, 'n296': 0.07222222222222222, 'n332': 0.4030637254901961, 'n342': 0.49415849673202616, 'n410': 0.17222222222222222, 'n415': 0.10477941176470588, 'n429': 0.24076797385620916, 'n469': 0.194015522875817, 'n495': 0.14183006535947712, 'n506': 0.37118055555555557, 'n516': 0.315359477124183, 'n519': 0.05402369281045752, 'n549': 0.4329861111111111, 'n613': 0.9100898692810457, 'n636': 0.4456290849673203, 'n644': 0.5168300653594772, 'n679': 0.17567401960784312, 'n722': 0.08462009803921569, 'n726': 0.17949346405228758, 'n740': 0.183312908496732, 'n752': 0.5135008169934641, 'n769': 0.40753676470588235}, 'note': 'Normalization unchanged this round. Tiny scales and frequent z>k excursions may still dominate alert burden under residual recovery.'}

## Recommendation

**No-go for this residual-recovery operating point:** abrupt hits were retained, but clear/rearm under frequent residual excursions creates a notification storm (unmatched/wk ≫ original) while union network occupancy stays near saturation. The registered 7-day shift null is not beaten. Summed sensor-hours fell, but that is not usable under the alert burden. Tiny pair scales remain widespread; do not productize; do not sweep the 12-step constant next—address scale/excursion behavior first. DIAG abrupt recall original=1.00 vs variant=1.00; union occupancy 99.9% → 99.9%; summed sensor-alarm 78.2% → 25.7%; longest episode 4076.8333333333335 → 3543.75 h; unmatched/wk 1.26 → 77.23. Variant null 7d: obs=3 median=3.0 min–max=3–3 frac≥obs=1.00 (n_shifts=89). Null 0–2h: obs=3 median=2.0 min–max=1–3 frac≥obs=0.47.

