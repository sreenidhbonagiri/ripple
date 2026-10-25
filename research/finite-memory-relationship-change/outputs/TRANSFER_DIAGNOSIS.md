# FMR3C DEV→DIAG transfer diagnosis

Generated: 2026-10-24T21:57:38-04:00

Preserves frozen settings (`empirical_frozen.json`), prior reports, and production. **No** new threshold selection or detector grid. Score recomputation is for diagnosis only under the frozen LQ/LR and τ.

Frozen: LQ=2h, LR=48h, τ=26.7329 (DEV p99.5).

## 1. Score comparability

### Fitting protocol

Each period (DEV, DIAG) **independently** fits pairwise OLS, selects top-3 references, and estimates residual loc/scale + FMR3C train-only σ on its own first 14 calendar days. Analysis scores never reuse the other period's coefficients. Frozen τ was chosen from DEV pooled scores only and applied as a numeric cutoff on DIAG scores from DIAG's own refit.

### Hashes / fit windows

- Pressures sha256: `7782d890a7195699be94ddc01cba392da7ca285908afff619065a9616e04dcae`
- DEV train: 2018-01-01 00:00 → 2018-01-14 23:55 (fit on this prefix only)
- DEV analysis_offset / z sha16: 4032 / `ad73a40a8a17d109`
- DEV models fingerprint sha16: `3953fbbbd588e22e`
- DEV train_z sha16: `3bd6163e3c0f586a`
- DIAG train: 2018-07-01 00:00 → 2018-07-14 23:55
- DIAG analysis_offset / z sha16: 56160 / `97404bab2df615d8`
- DIAG models fingerprint sha16: `332a6c5cd90d57e1`
- DIAG train_z sha16: `47cd75c4e53eff45`
- Models identical across periods: **False**
- Reference sets identical: **False**

Because models, refs, and σ are **refit per period**, the same numeric τ=26.73 is **not** a stable probability threshold across DEV and DIAG. A score of 26.7 on DIAG is standardized by DIAG train MAD/ρ, not DEV's. Operating-season shift (DEV winter–spring train vs DIAG summer train) further changes the meaning of exceedances.

### Score / exceedance by period

| Period | n | median | p99 | p99.5 | frac ≥ τ |
|--------|---|--------|-----|-------|----------|
| DEV | 1567401 | 0.03331 | 16.94 | 26.73 | 0.005001 |
| DIAG | 1595913 | 0.02097 | 7.383 | 9.488 | 0.000419 |

### DIAG months (pooled scores)

| Month | n | median | p99 | p99.5 | frac ≥ τ |
|-------|---|--------|-----|-------|----------|
| 2018-07 | 141801 | 0.01999146875766547 | 4.339502670896546 | 5.259097431155922 | 0.0 |
| 2018-08 | 294624 | -0.0018424570931832695 | 9.16122898826169 | 13.041307296201571 | 0.0009775171065493646 |
| 2018-09 | 285120 | 0.040381130428042145 | 6.104819078616268 | 7.843908779049283 | 0.0 |
| 2018-10 | 294624 | 0.02460408880483648 | 9.89229055253057 | 12.229464712314904 | 0.0012931736722059304 |
| 2018-11 | 285120 | 0.02863567681847335 | 6.115213243824309 | 7.429937930892309 | 0.0 |
| 2018-12 | 294624 | 0.024700285605612576 | 6.3943460217411205 | 7.632999638168286 | 0.0 |

### Top DIAG sensors by frac ≥ τ

| Sensor | frac ≥ τ | p99 | p99.5 | max |
|--------|----------|-----|-------|-----|
| n644 | 0.006203345671098612 | 15.705491409327417 | 66.60364498546325 | 84.23648867951076 |
| n752 | 0.005955211844254668 | 7.592593013663709 | 32.563788952355594 | 46.76356176522131 |
| n636 | 0.0016335476933893012 | 13.714860817956003 | 20.634326056988666 | 32.40450939907667 |
| n342 | 4.1355637807324086e-05 | 10.617311593827468 | 14.771714987126801 | 26.853080214241484 |
| n1 | 0.0 | 7.357372623347772 | 8.60210730638455 | 12.2452736382938 |
| n4 | 0.0 | 9.159649902466628 | 11.166023850596442 | 19.975738012707968 |
| n31 | 0.0 | 2.2003067475933924 | 2.780696408725338 | 4.176289511444377 |
| n54 | 0.0 | 1.3490082085284052 | 1.49366365909759 | 2.0247400434074314 |
| n105 | 0.0 | 4.13593551471777 | 4.594363794373447 | 6.552171393345936 |
| n114 | 0.0 | 4.306859319512741 | 4.881729262220738 | 7.5458529336649205 |

## 2. Abrupt events (6 h post-onset)

### p183 (MISS under primary matching)

- Onset: 2018-08-07 02:35
- Peak network score in 6 h: **44.12581084144053** (τ=26.73; Δ=17.39286629368386; exceeds=True)
- Peak time: 2018-08-07 08:20
- Top sensors at peak: [{'sensor': 'n752', 'score': 44.12581084144053, 'refs': ['n726', 'n769', 'n288'], 'ge_tau': True}, {'sensor': 'n636', 'score': 19.68048461810945, 'refs': ['n188', 'n613', 'n163'], 'ge_tau': False}, {'sensor': 'n644', 'score': 16.143077742685094, 'refs': ['n636', 'n679', 'n332'], 'ge_tau': False}, {'sensor': 'n726', 'score': 11.541340223258388, 'refs': ['n752', 'n769', 'n288'], 'ge_tau': False}, {'sensor': 'n613', 'score': 5.200923804089209, 'refs': ['n163', 'n188', 'n519'], 'ge_tau': False}]
- Sensors crossing τ in window: [{'sensor': 'n752', 'max_in_window': 44.12581084144053, 'first_cross_local': 6667}]
- Notifications in window: [{'stream': 'n752', 'notify': '2018-08-07 03:35', 'delay_h': 1.0}]
- Already active at onset: []
- Episode logic: {'threshold_crossed_in_window': True, 'new_notification_in_window': True, 'blocked_by_active_episode': False, 'explanation': 'Threshold crossing produced a notification inside the 6 h window (see matching-attribution note if primary abrupt recall still MISS).'}
- Primary match (preserved EMPIRICAL DIAG): {'pipe': 'p183', 'leak_type': 'abrupt', 'onset': '2018-08-07 02:35', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None}
- Matching attribution: {'issue': 'in_window_notify_assigned_to_earlier_onset', 'detail': 'n752 notified 2018-08-07 03:35 (1 h after p183 onset) but primary one-to-one matching credited that episode to incipient p810 (onset 2018-07-28, delay 240.5 h under the 14-day incipient window).'}

### p369 (MISS under primary matching)

- Onset: 2018-10-26 02:05
- Peak network score in 6 h: **6.547648958864513** (τ=26.73; Δ=-20.18529558889216; exceeds=False)
- Peak time: 2018-10-26 03:25
- Top sensors at peak: [{'sensor': 'n163', 'score': 6.547648958864513, 'refs': ['n613', 'n519', 'n188'], 'ge_tau': False}, {'sensor': 'n410', 'score': 5.024378137622073, 'refs': ['n429', 'n415', 'n342'], 'ge_tau': False}, {'sensor': 'n415', 'score': 3.674227802972607, 'refs': ['n458', 'n342', 'n519'], 'ge_tau': False}, {'sensor': 'n519', 'score': 3.470424341561246, 'refs': ['n163', 'n613', 'n188'], 'ge_tau': False}, {'sensor': 'n229', 'score': 3.362288679500917, 'refs': ['n636', 'n613', 'n163'], 'ge_tau': False}]
- Sensors crossing τ in window: []
- Notifications in window: []
- Already active at onset: []
- Episode logic: {'threshold_crossed_in_window': False, 'new_notification_in_window': False, 'blocked_by_active_episode': False, 'explanation': 'No sensor score reached frozen τ in the 6 h window.'}
- Primary match (preserved EMPIRICAL DIAG): {'pipe': 'p369', 'leak_type': 'abrupt', 'onset': '2018-10-26 02:05', 'matched': False, 'notify_time': None, 'delay_hours': None, 'stream_id': None}
- Matching attribution: None

### p158 (HIT under primary matching)

- Onset: 2018-10-06 02:35
- Peak network score in 6 h: **72.9856353991769** (τ=26.73; Δ=46.252690851420226; exceeds=True)
- Peak time: 2018-10-06 04:15
- Top sensors at peak: [{'sensor': 'n644', 'score': 72.9856353991769, 'refs': ['n636', 'n679', 'n332'], 'ge_tau': True}, {'sensor': 'n342', 'score': 25.422514828025008, 'refs': ['n458', 'n415', 'n613'], 'ge_tau': False}, {'sensor': 'n636', 'score': 22.86156535867815, 'refs': ['n188', 'n613', 'n163'], 'ge_tau': False}, {'sensor': 'n613', 'score': 16.062748762878144, 'refs': ['n163', 'n188', 'n519'], 'ge_tau': False}, {'sensor': 'n229', 'score': 15.231075196138745, 'refs': ['n636', 'n613', 'n163'], 'ge_tau': False}]
- Sensors crossing τ in window: [{'sensor': 'n644', 'max_in_window': 72.9856353991769, 'first_cross_local': 23946}]
- Notifications in window: [{'stream': 'n644', 'notify': '2018-10-06 03:30', 'delay_h': 0.9166666666666666}]
- Already active at onset: []
- Episode logic: {'threshold_crossed_in_window': True, 'new_notification_in_window': True, 'blocked_by_active_episode': False, 'explanation': 'Threshold crossing produced a notification inside the 6 h window (see matching-attribution note if primary abrupt recall still MISS).'}
- Primary match (preserved EMPIRICAL DIAG): {'pipe': 'p158', 'leak_type': 'abrupt', 'onset': '2018-10-06 02:35', 'matched': True, 'notify_time': '2018-10-06 03:30', 'delay_hours': 0.9166666666666666, 'stream_id': 'n644'}
- Matching attribution: None

## 3. Local unusualness vs same-month controls (diagnostic only)

Retrospective percentiles — **not** tuned DIAG thresholds; not a performance claim.

### p183

- Rule: Non-overlapping 6h windows stepped every 6h within the event's calendar month inside the period analysis span; reject start if within ±7 d of any labeled leakage onset. Statistic = max_t max_i s_i(t). Controls are not assumed leak-free.
- n_controls: 71
- Control max median/p90/p99/max: 11.435552534683696 / 15.747422640730383 / 16.775513234341304 / 16.873493902501284
- Event 6 h network max: **44.12581084144053**
- Event percentile among controls: **100.0**

### p369

- Rule: Non-overlapping 6h windows stepped every 6h within the event's calendar month inside the period analysis span; reject start if within ±7 d of any labeled leakage onset. Statistic = max_t max_i s_i(t). Controls are not assumed leak-free.
- n_controls: 24
- Control max median/p90/p99/max: 9.855845760150588 / 12.174273101820534 / 12.823283635037237 / 12.86395569051816
- Event 6 h network max: **6.547648958864513**
- Event percentile among controls: **4.166666666666666**

### p158

- Rule: Non-overlapping 6h windows stepped every 6h within the event's calendar month inside the period analysis span; reject start if within ±7 d of any labeled leakage onset. Statistic = max_t max_i s_i(t). Controls are not assumed leak-free.
- n_controls: 24
- Control max median/p90/p99/max: 9.855845760150588 / 12.174273101820534 / 12.823283635037237 / 12.86395569051816
- Event 6 h network max: **72.9856353991769**
- Event percentile among controls: **100.0**

## 4. Recommendation

**p183 is not a score-transfer miss:** network max 44.1 ≥ τ with an in-window n752 notification (delay 1 h). Primary abrupt MISS is a **matching-attribution conflict** — the episode was consumed by earlier incipient p810 under the 14-day match window. Adaptive τ calibration would not fix this; a matching/eligibility rule change would. **p369: calibration is insufficient.** Peak network score 6.55 ≪ τ and only ~4.2th percentile vs same-month 6 h controls — ordinary excursions dominate. Missing information is not a higher DEV percentile; relationship residuals lack separable local structure (spatial/hydraulic consistency or operating context). Comparability: DEV/DIAG models independently refit (identical=False, refs_identical=False); DIAG frac≥τ 0.000419 vs DEV 0.005001 — numeric τ changes meaning across periods. p158 HIT peak=72.99 (local_pct=100.0). Do not retune τ or implement adaptive calibration in this diagnosis.

## Non-goals honored

- No parameter sweep, 2019, UI, Tiger, deployment, or main merge
- Frozen τ / LQ / LR unchanged; prior reports not overwritten

