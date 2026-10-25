# FMR3C frozen detector — 2019 full-year evaluation

Generated: 2026-10-24T22:14:18-04:00

Preserves production and all prior FMR3C / CUSUM research reports. **No** feature addition, τ retune, Tiger, UI, or deployment.

Honesty: prior 2019 examination is acknowledged — this is **not** an untouched holdout. Method and τ were frozen from 2018 DEV empirical calibration (`empirical_frozen.json`).

## 0. Pre-inference freeze

- Protocol: `YEAR2019_EVALUATION_PROTOCOL.md`
- Git at freeze: `fbcbd9007908eaf358adc87303843e95f71c9b42`
- Package+config sha256: `c9e1ec4b267fb690584f42f716f9761679266b589ecb4059a9649b696a174141`
- τ (exact loaded): **26.732944547756674** (LQ=2h, LR=48h)

### Input hashes

- `2019_SCADA_Pressures.csv`: `a4af6616059cc9b366bbab76d880b2c772df544970c6ff4d4a29a58704ce05b1`
- `2019_SCADA_Flows.csv`: `c709ea5ecc03197e1fe70cf4c2de7225f71015acb50a7445ed7765b5029f7f15`
- `2019_SCADA_Levels.csv`: `00624e97b72e63233beeccb48db528d43e59a87b116d0295d5c2a206ee0e75a8`
- `leakages_2018_2019.json`: `4b467db9f9c93cfc84a420ba4b2d8dd583158fee23fd271ede4c295f5933345f`
- `empirical_frozen.json`: `463a247e7c595e90508d678a0f4d296a01b425542963f95648bbb710ac51cc6d`
- `YEAR2019_EVALUATION_PROTOCOL.md`: `a408fc62dea0cd4df3069efd82055d93977e5a832bd6ef6a85eed55c86cf4fc9`

### Code file hashes

- `DESIGN.md`: `317767c6526ccf2ccc9f8c79d40c20f0b1db8bcfe62503d69d6da344be7f8a1b`
- `YEAR2019_EVALUATION_PROTOCOL.md`: `a408fc62dea0cd4df3069efd82055d93977e5a832bd6ef6a85eed55c86cf4fc9`
- `detector.py`: `df0c2fed831efe9c7dd4051cfebd3e9a8a7ce87b9672ee295c7dfd876e5556bb`
- `scale.py`: `67f7f22a5151640fe3c3a8c207de4dde5d124fdd0f799ab058567c7a474b6b0f`
- `windows.py`: `e442464420ba9c93f33c531a6f0f96293255e80b543d0aeff1b49a35e3aa3419`
- `signals.py`: `63071f2da010c2c14715ef8777e46cc280c2326d00deb3f52bc0d3835c76b831`
- `run_year2019_evaluation.py`: `eaa601441f3cb7c699edf1daa7ab5441f133f263fcf10946a1d3ffeea43b5e1d`
- `run_empirical_calibration.py`: `610ba105ce2255848eb7f33ccefd36066e9a56b53ac32918724ff849217397fc`

## 1. Fitting prefix (2019)

- Fit slice: **2019-01-01 00:00** → **2019-01-14 23:55** (exclusive end index at 2019-01-15 00:00)
- Fitting completion (`train_end`): **2019-01-15 00:00**
- Warm-up steps (n_Q+n_R-1): **599** (49.92 h)
- Earliest eligible notification: **2019-01-17 01:55**
- Eligible sensors: **33** / 33
- Analysis span steps: 101088
- z sha256[:16]: `3f955864b3c07f49`
- scores sha256: `49e738a4958fbbcd992e00441892689d6701b5a102eaf1eb6f88354a0acd15f6`
- notifications/episodes sha256: `3db05ac9472fffe4dab923a11cdf5801afd967356723a5b740782c7cb3fb7064`
- n_episodes (pre-GT): **74**
- Inference runtime_s: 4.35

Scores and notifications were hashed **before** loading ground truth into the evaluation stage.

## 2. Event strata

Counts: `{'carryover': 4, 'training_prefix_onsets': 0, 'warm_up_onsets': 1, 'post_fit_abrupt': 8, 'post_fit_incipient': 10, 'primary_eligible': 19, 'year_onsets': 19}`

### Carryover (open in 2019; onset before 2019)

- p257 (incipient) onset=2018-01-08 13:30 end=2019-12-31 23:55
- p427 (incipient) onset=2018-02-13 08:25 end=2019-12-31 23:55
- p654 (incipient) onset=2018-07-05 03:40 end=2019-12-31 23:55
- p810 (incipient) onset=2018-07-28 03:05 end=2019-12-31 23:55

### Training / warm-up onsets

- WARM-UP p523 (abrupt) 2019-01-15 23:00

### Post-fit abrupt

- p827 onset=2019-01-24 18:30
- p280 onset=2019-02-10 13:05
- p710 onset=2019-03-24 14:15
- p514 onset=2019-04-02 20:40
- p331 onset=2019-04-20 10:10
- p142 onset=2019-06-12 19:55
- p680 onset=2019-07-10 08:45
- p426 onset=2019-10-25 13:25

### Post-fit incipient

- p653 onset=2019-03-03 13:10 peak=2019-04-21 19:00
- p193 onset=2019-05-19 10:40 peak=2019-07-25 03:20
- p277 onset=2019-05-30 21:55 peak=2019-08-11 15:05
- p586 onset=2019-07-26 14:40 peak=2019-08-28 07:55
- p721 onset=2019-08-02 03:00 peak=2019-09-23 05:40
- p800 onset=2019-08-16 14:00 peak=2019-09-07 21:05
- p123 onset=2019-09-13 20:05 peak=2019-11-29 22:10
- p455 onset=2019-10-03 14:00 peak=2019-12-16 05:25
- p762 onset=2019-10-09 10:15 peak=2019-12-03 01:15
- p879 onset=2019-11-20 11:55 peak=2019-12-31 23:55

### Development example p523

- p523 (abrupt) onset=2019-01-15 23:00 end=2019-02-01 09:50
  - stratum: `warm_up`
  - view A: HIT notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644
  - view B: HIT notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644
  - view C: HIT notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644

## 3. Matching views (primary eligible onsets)

Registered headline is **view A**. Views B/C are secondary. One notification never double-credits two events.

### View A: Registered joint chronological greedy

- Registered: **True**; post-hoc: False
- Onsets chronological; earliest unused notify in type window (abrupt 7d / incipient to peak∩14d).

- Abrupt recall (type window): **0.4444444444444444** (n=9)
- Abrupt 6h recall: **0.2222222222222222** (2/9)
- Incipient recall: 0.4
- Abrupt delays (matched, full window): {'n': 4, 'median': 4.208333333333333, 'max': 53.583333333333336, 'values': [53.583333333333336, 0.9166666666666666, 1.3333333333333333, 7.083333333333333]}
- Unmatched episodes: 66 (**1.266**/wk); dup24h: 57
- Union%: 7.71; sensor%: 0.3877
- Episode length h median/max: 14.166666666666668/31.0; right-censored: 0

Per-event assignments:

- HIT p523 (abrupt) onset=2019-01-15 23:00 notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644 ep=0
- HIT p827 (abrupt) onset=2019-01-24 18:30 notify=2019-01-24 19:25 delay_h=0.9166666666666666 sensor=n726 ep=7
- MISS p280 (abrupt) onset=2019-02-10 13:05 notify=None delay_h=None sensor=None ep=None
- MISS p653 (incipient) onset=2019-03-03 13:10 notify=None delay_h=None sensor=None ep=None
- MISS p710 (abrupt) onset=2019-03-24 14:15 notify=None delay_h=None sensor=None ep=None
- MISS p514 (abrupt) onset=2019-04-02 20:40 notify=None delay_h=None sensor=None ep=None
- MISS p331 (abrupt) onset=2019-04-20 10:10 notify=None delay_h=None sensor=None ep=None
- HIT p193 (incipient) onset=2019-05-19 10:40 notify=2019-05-23 16:00 delay_h=101.33333333333333 sensor=n644 ep=18
- HIT p277 (incipient) onset=2019-05-30 21:55 notify=2019-06-12 20:55 delay_h=311.0 sensor=n613 ep=20
- MISS p142 (abrupt) onset=2019-06-12 19:55 notify=None delay_h=None sensor=None ep=None
- HIT p680 (abrupt) onset=2019-07-10 08:45 notify=2019-07-10 10:05 delay_h=1.3333333333333333 sensor=n229 ep=22
- MISS p586 (incipient) onset=2019-07-26 14:40 notify=None delay_h=None sensor=None ep=None
- MISS p721 (incipient) onset=2019-08-02 03:00 notify=None delay_h=None sensor=None ep=None
- HIT p800 (incipient) onset=2019-08-16 14:00 notify=2019-08-28 09:40 delay_h=283.6666666666667 sensor=n296 ep=32
- HIT p123 (incipient) onset=2019-09-13 20:05 notify=2019-09-16 05:00 delay_h=56.916666666666664 sensor=n342 ep=54
- MISS p455 (incipient) onset=2019-10-03 14:00 notify=None delay_h=None sensor=None ep=None
- MISS p762 (incipient) onset=2019-10-09 10:15 notify=None delay_h=None sensor=None ep=None
- HIT p426 (abrupt) onset=2019-10-25 13:25 notify=2019-10-25 20:30 delay_h=7.083333333333333 sensor=n644 ep=73
- MISS p879 (incipient) onset=2019-11-20 11:55 notify=None delay_h=None sensor=None ep=None

Abrupt 6h detail:

- HIT>6 p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT6 p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- MISS p142 delay_h=None notify=None sensor=None
- HIT6 p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT>6 p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

Shifted null (same assignment as view A; abrupt match counts):

- Observed: **4** / 9
- Null median (min–max): 3.0 (0–6)
- Frac shifts ≥ obs: **0.11**
- Same assignment view on circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

### View B: Secondary: abrupt-only matching

- Registered: **False**; post-hoc: True
- Same greedy rule on abrupt onsets only. Incipient excluded from scoring.

- Abrupt recall (type window): **0.5555555555555556** (n=9)
- Abrupt 6h recall: **0.3333333333333333** (3/9)
- Incipient recall: None
- Abrupt delays (matched, full window): {'n': 5, 'median': 1.3333333333333333, 'max': 53.583333333333336, 'values': [53.583333333333336, 0.9166666666666666, 1.0, 1.3333333333333333, 7.083333333333333]}
- Unmatched episodes: 69 (**1.323**/wk); dup24h: 60
- Union%: 7.71; sensor%: 0.3877
- Episode length h median/max: 14.166666666666668/31.0; right-censored: 0

Per-event assignments:

- HIT p523 (abrupt) onset=2019-01-15 23:00 notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644 ep=0
- HIT p827 (abrupt) onset=2019-01-24 18:30 notify=2019-01-24 19:25 delay_h=0.9166666666666666 sensor=n726 ep=7
- MISS p280 (abrupt) onset=2019-02-10 13:05 notify=None delay_h=None sensor=None ep=None
- MISS p710 (abrupt) onset=2019-03-24 14:15 notify=None delay_h=None sensor=None ep=None
- MISS p514 (abrupt) onset=2019-04-02 20:40 notify=None delay_h=None sensor=None ep=None
- MISS p331 (abrupt) onset=2019-04-20 10:10 notify=None delay_h=None sensor=None ep=None
- HIT p142 (abrupt) onset=2019-06-12 19:55 notify=2019-06-12 20:55 delay_h=1.0 sensor=n613 ep=20
- HIT p680 (abrupt) onset=2019-07-10 08:45 notify=2019-07-10 10:05 delay_h=1.3333333333333333 sensor=n229 ep=22
- HIT p426 (abrupt) onset=2019-10-25 13:25 notify=2019-10-25 20:30 delay_h=7.083333333333333 sensor=n644 ep=73

Excluded incipient:
- p653 (incipient) 2019-03-03 13:10
- p193 (incipient) 2019-05-19 10:40
- p277 (incipient) 2019-05-30 21:55
- p586 (incipient) 2019-07-26 14:40
- p721 (incipient) 2019-08-02 03:00
- p800 (incipient) 2019-08-16 14:00
- p123 (incipient) 2019-09-13 20:05
- p455 (incipient) 2019-10-03 14:00
- p762 (incipient) 2019-10-09 10:15
- p879 (incipient) 2019-11-20 11:55

Abrupt 6h detail:

- HIT>6 p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT6 p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT6 p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT6 p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT>6 p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

Shifted null (same assignment as view B; abrupt match counts):

- Observed: **5** / 9
- Null median (min–max): 3.0 (0–6)
- Frac shifts ≥ obs: **0.08**
- Same assignment view on circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

### View C: Secondary: joint max-cardinality + min-sum-delay

- Registered: **False**; post-hoc: True
- Hungarian: max matched events, then min sum delay. One notify → one event.
- Tie-break: Primary max cardinality; secondary min sum delay_hours; tertiary deterministic solver.

- Abrupt recall (type window): **0.5555555555555556** (n=9)
- Abrupt 6h recall: **0.3333333333333333** (3/9)
- Incipient recall: 0.3
- Abrupt delays (matched, full window): {'n': 5, 'median': 1.3333333333333333, 'max': 53.583333333333336, 'values': [53.583333333333336, 0.9166666666666666, 1.0, 1.3333333333333333, 7.083333333333333]}
- Unmatched episodes: 66 (**1.266**/wk); dup24h: 57
- Union%: 7.71; sensor%: 0.3877
- Episode length h median/max: 14.166666666666668/31.0; right-censored: 0

Per-event assignments:

- HIT p523 (abrupt) onset=2019-01-15 23:00 notify=2019-01-18 04:35 delay_h=53.583333333333336 sensor=n644 ep=0
- HIT p827 (abrupt) onset=2019-01-24 18:30 notify=2019-01-24 19:25 delay_h=0.9166666666666666 sensor=n726 ep=7
- MISS p280 (abrupt) onset=2019-02-10 13:05 notify=None delay_h=None sensor=None ep=None
- MISS p653 (incipient) onset=2019-03-03 13:10 notify=None delay_h=None sensor=None ep=None
- MISS p710 (abrupt) onset=2019-03-24 14:15 notify=None delay_h=None sensor=None ep=None
- MISS p514 (abrupt) onset=2019-04-02 20:40 notify=None delay_h=None sensor=None ep=None
- MISS p331 (abrupt) onset=2019-04-20 10:10 notify=None delay_h=None sensor=None ep=None
- HIT p193 (incipient) onset=2019-05-19 10:40 notify=2019-05-23 16:00 delay_h=101.33333333333333 sensor=n644 ep=18
- MISS p277 (incipient) onset=2019-05-30 21:55 notify=None delay_h=None sensor=None ep=None
- HIT p142 (abrupt) onset=2019-06-12 19:55 notify=2019-06-12 20:55 delay_h=1.0 sensor=n613 ep=20
- HIT p680 (abrupt) onset=2019-07-10 08:45 notify=2019-07-10 10:05 delay_h=1.3333333333333333 sensor=n229 ep=22
- MISS p586 (incipient) onset=2019-07-26 14:40 notify=None delay_h=None sensor=None ep=None
- MISS p721 (incipient) onset=2019-08-02 03:00 notify=None delay_h=None sensor=None ep=None
- HIT p800 (incipient) onset=2019-08-16 14:00 notify=2019-08-28 09:40 delay_h=283.6666666666667 sensor=n296 ep=32
- HIT p123 (incipient) onset=2019-09-13 20:05 notify=2019-09-16 05:00 delay_h=56.916666666666664 sensor=n342 ep=54
- MISS p455 (incipient) onset=2019-10-03 14:00 notify=None delay_h=None sensor=None ep=None
- MISS p762 (incipient) onset=2019-10-09 10:15 notify=None delay_h=None sensor=None ep=None
- HIT p426 (abrupt) onset=2019-10-25 13:25 notify=2019-10-25 20:30 delay_h=7.083333333333333 sensor=n644 ep=73
- MISS p879 (incipient) onset=2019-11-20 11:55 notify=None delay_h=None sensor=None ep=None

Abrupt 6h detail:

- HIT>6 p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT6 p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT6 p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT6 p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT>6 p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

Shifted null (same assignment as view C; abrupt match counts):

- Observed: **5** / 9
- Null median (min–max): 3.0 (0–6)
- Frac shifts ≥ obs: **0.08**
- Same assignment view on circularly shifted notifications. Overlapping shifts; small n; diagnostic only.

## 4. Credit conflicts

Notifications co-eligible for ≥2 primary onsets (views still assign once):

- ep#20 n613 @ 2019-06-12 20:55: p277(incipient,d=311h), p142(abrupt,d=1h)

## 5. Notification-time nulls (0–2 h / 0–6 h, registered windows shortened)

### 0–2 h

- Observed abrupt matches: **3** / 9
- Null median (min–max): 0.0 (0–1)
- Frac shifts ≥ obs: **0.00**

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

### 0–6 h

- Observed abrupt matches: **3** / 9
- Null median (min–max): 0.0 (0–2)
- Frac shifts ≥ obs: **0.00**

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

## 6. Post-fit stratum under registered view A

- Post-fit abrupt 6h: **0.25** (2/8)
- Post-fit abrupt (full window): **0.375**
- Post-fit incipient: **0.4**

Post-fit abrupt detail:

- HIT6 p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25
- MISS p280 delay_h=None notify=None
- MISS p710 delay_h=None notify=None
- MISS p514 delay_h=None notify=None
- MISS p331 delay_h=None notify=None
- MISS p142 delay_h=None notify=None
- HIT6 p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05
- HIT>6 p426 delay_h=7.083333333333333 notify=2019-10-25 20:30

Warm-up onset results (view A primary set includes them):

- HIT p523 delay_h=53.583333333333336 notify=2019-01-18 04:35

## 7. Candid assessment

Registered view A on primary eligible 2019 onsets: abrupt 6h recall **0.22** (2/9), abrupt full-window **0.44**, incipient **0.4**, unmatched/wk **1.27**, union% **7.71**, dup24h=57, episodes=74. Secondary abrupt-only view B abrupt 6h **0.33** (not a joint-detection claim). View C abrupt 6h **0.33**. Post-fit-only abrupt 6h (onset ≥ earliest eligible notify): **0.25** (2/8). 0–6 h shortened-window null: observed 3/9, frac shifts≥obs=0.00. No strong latched-only signature under declared heuristics. **Candid:** burden looks manageable (low unmatched/wk / occupancy), but six-hour abrupt sensitivity on the broader year is **not** useful enough under the same provisional bar used on DEV (≥2/3). Do not treat low FP rate alone as success. Do not select a secondary view as the sole headline; registered view remains A.

## Non-goals / stop

- No threshold adjustment or selective rerun
- No feature addition (including p369-targeted)
- No main merge, UI, Tiger, or deployment
- Prior registered 2018 reports untouched

