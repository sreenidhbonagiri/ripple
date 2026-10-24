# Audit — per-sensor relationship CUSUM (frozen DIAG)

Generated: 2026-10-24T19:55:41-04:00

Frozen settings, original `RESULTS.md` / `summary.json` headline, production, and other branches are **preserved**. No detector retuning.

## 0. Original registered result (preserved)

- Abrupt recall (original, all DIAG onsets): **1.00**
- Incipient recall: **1.00**
- Unmatched/wk: **1.22**
- Recommendation (original): **Limited research signal:** per-sensor signed residuals improve abrupt notification metrics vs global aggregation under equivalent rules, and beat the descriptive null. **Not** va…

## 1. Eligibility correction

Training/calibration prefix: first **14** days of DIAG (through **2018-07-15 00:00**). Onsets with `startTime` **before** this instant are **excluded** from primary post-training onset recall.

- In-prefix onsets (excluded from primary): ['p654']
- Primary-eligible onsets: ['p810', 'p183', 'p158', 'p369']

### Primary post-training recall (corrected)

- Abrupt recall: **1.00** (3 onsets)
- Incipient recall: **1.00** (1 onsets)
- Abrupt delays (h): {'n': 3, 'median': 0.3333333333333333, 'max': 1.25}

#### Eligible per-event

- HIT p810 (incipient) onset 2018-07-28 03:05 notify=2018-07-29 09:20 delay_h=30.25 sensor=n740
- HIT p183 (abrupt) onset 2018-08-07 02:35 notify=2018-08-07 03:50 delay_h=1.25 sensor=n726
- HIT p158 (abrupt) onset 2018-10-06 02:35 notify=2018-10-06 02:55 delay_h=0.3333333333333333 sensor=n288
- HIT p369 (abrupt) onset 2018-10-26 02:05 notify=2018-10-26 02:15 delay_h=0.16666666666666666 sensor=n410

#### In-prefix onsets (reported separately; not in primary recall)

- HIT p654 (incipient) onset 2018-07-05 03:40 notify=2018-07-15 02:55 delay_h=239.25 — excluded because onset is inside fitting prefix

## 2. Alarm occupancy

- Notifications (episode starts): **37**
- Summed sensor-alarm hours: **105317.6** (78.22% of eligible sensor-hours)
- Union alarm hours (any sensor): **4077.1** (99.93% of analysis hours)
- Active-sensor count: mean=25.81, median=26.00, p90=27.00, max=29
- Episode length (h): median=3800.6666666666665, p90=4063.4166666666665, max=4076.8333333333335
- Right-censored episodes: **25** / 37

Notifications count episode starts only. Occupancy counts ongoing alarm intervals; already-active alarms are not new detections.

Longest episodes:

- n54: 4076.8 h (right-censored) notify=2018-07-15 03:05 end=2018-12-31 23:55
- n1: 4074.0 h (right-censored) notify=2018-07-15 05:55 end=2018-12-31 23:55
- n636: 4071.4 h (right-censored) notify=2018-07-15 08:30 end=2018-12-31 23:55
- n506: 4070.7 h (right-censored) notify=2018-07-15 09:15 end=2018-12-31 23:55
- n188: 4058.6 h (right-censored) notify=2018-07-15 21:20 end=2018-12-31 23:55
- n469: 4057.1 h (right-censored) notify=2018-07-15 22:50 end=2018-12-31 23:55
- n215: 4057.0 h (right-censored) notify=2018-07-15 22:55 end=2018-12-31 23:55
- n4: 4053.3 h (right-censored) notify=2018-07-16 02:35 end=2018-12-31 23:55

## 3. Recovery diagnosis

Evidence vs hypotheses for longest episodes and abrupt hit streams. Implementation replay of CUSUM arithmetic checked on a prefix sample.

### longest_n54 — n54

- Duration 4076.8 h; right_censored=True; peak_C=24.3
- Refs: ['n429', 'n410', 'n679']
- Pair scales: [0.0661, 0.0801, 0.0818]
- Post-notify median z=-0.0593121312558651; frac|z|<0.5=0.47286552337346444; frac C>0=0.2142141732927253
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_longest_n54_n54.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=-0.0593121312558651
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 932; frac |z|<0.5=0.47286552337346444; frac C>0=0.2142141732927253
  - **restrictive_24h_recovery**: supported=True — recovery requires 288 consecutive steps with C==0; max recover_run in episode=271
  - **small_normalization_scales**: supported=False — pair scales=[0.0661, 0.0801, 0.0818]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

### longest_n1 — n1

- Duration 4074.0 h; right_censored=True; peak_C=359.8
- Refs: ['n31', 'n4', 'n114']
- Pair scales: [0.0621, 0.0612, 0.3167]
- Post-notify median z=-0.0810471624135971; frac|z|<0.5=0.4809057252142609; frac C>0=0.598662275767555
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_longest_n1_n1.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=-0.0810471624135971
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 13533; frac |z|<0.5=0.4809057252142609; frac C>0=0.598662275767555
  - **restrictive_24h_recovery**: supported=True — recovery requires 288 consecutive steps with C==0; max recover_run in episode=284
  - **small_normalization_scales**: supported=False — pair scales=[0.0621, 0.0612, 0.3167]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

### longest_n636 — n636

- Duration 4071.4 h; right_censored=True; peak_C=35175.0
- Refs: ['n188', 'n613', 'n163']
- Pair scales: [0.0138, 0.0167, 0.0169]
- Post-notify median z=0.2749826908111572; frac|z|<0.5=0.2883458184944124; frac C>0=0.9093700110524376
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_longest_n636_n636.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=0.2749826908111572
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 11947; frac |z|<0.5=0.2883458184944124; frac C>0=0.9093700110524376
  - **restrictive_24h_recovery**: supported=True — recovery requires 288 consecutive steps with C==0; max recover_run in episode=94
  - **small_normalization_scales**: supported=True — pair scales=[0.0138, 0.0167, 0.0169]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

### abrupt_hit_p183 — n726

- Duration 2321.2 h; right_censored=False; peak_C=3858.6
- Refs: ['n752', 'n769', 'n288']
- Pair scales: [0.0058, 0.008, 0.0092]
- Post-notify median z=-0.2855572998523712; frac|z|<0.5=0.35155801263641584; frac C>0=0.4992461229178633
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_abrupt_hit_p183_n726.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=-0.2855572998523712
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 4691; frac |z|<0.5=0.35155801263641584; frac C>0=0.4992461229178633
  - **restrictive_24h_recovery**: supported=False — recovery requires 288 consecutive steps with C==0; max recover_run in episode=287
  - **small_normalization_scales**: supported=True — pair scales=[0.0058, 0.008, 0.0092]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

### abrupt_hit_p158 — n288

- Duration 2085.0 h; right_censored=True; peak_C=8005.9
- Refs: ['n726', 'n752', 'n679']
- Pair scales: [0.01, 0.0119, 0.0146]
- Post-notify median z=0.45325303077697754; frac|z|<0.5=0.3517445345909436; frac C>0=1.0
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_abrupt_hit_p158_n288.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=0.45325303077697754
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 8801; frac |z|<0.5=0.3517445345909436; frac C>0=1.0
  - **restrictive_24h_recovery**: supported=False — recovery requires 288 consecutive steps with C==0; max recover_run in episode=0
  - **small_normalization_scales**: supported=True — pair scales=[0.01, 0.0119, 0.0146]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

### abrupt_hit_p369 — n410

- Duration 1605.7 h; right_censored=True; peak_C=7707.0
- Refs: ['n429', 'n415', 'n342']
- Pair scales: [0.0144, 0.0644, 0.0657]
- Post-notify median z=-0.1351993829011917; frac|z|<0.5=0.36416004982095596; frac C>0=0.5917795422699673
- Implementation replay ok: True
- Plots: ['outputs/audit_plots/recovery_abrupt_hit_p369_n410.png']

  - **sustained_observable_relationship_change**: supported=False — median post-notify z=-0.1351993829011917
  - **cusum_debt_despite_normalized_residual**: supported=True — steps with |z|<k and C>1: 3008; frac |z|<0.5=0.36416004982095596; frac C>0=0.5917795422699673
  - **restrictive_24h_recovery**: supported=True — recovery requires 288 consecutive steps with C==0; max recover_run in episode=267
  - **small_normalization_scales**: supported=True — pair scales=[0.0144, 0.0644, 0.0657]
  - **seasonal_model_mismatch**: supported=None — DIAG train is first 14 days of Jul; long late-year episodes may reflect drift of pairwise maps — hypothesis unless z stays elevated vs refs.

## 4. Tight-timing diagnostic (0–2 h) — not the registered headline

Registered abrupt window remains **0–7 days** (corrected primary abrupt recall=1.00).

### 0–2 h results

- Eligible abrupt matches: **3** / 3
- Null median (min–max): 0 (0–1)
- Fraction of shifts ≥ observed: **0.00**
- Valid shifts: 89 (overlapping — not independent)

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

Per-onset (0–2 h):

- HIT p183 delay_h=1.25 already_active=[]
- HIT p158 delay_h=0.3333333333333333 already_active=[]
- HIT p369 delay_h=0.16666666666666666 already_active=[]

## 5. Recommended next change (not implemented)

**Proposal:** Change recovery to require sustained **observable residual normalization** (e.g. N consecutive finite steps with z_i ≤ k or z_i ≤ 0), while keeping the episode active if z_i remains elevated — do **not** clear on wall-clock alone and do **not** periodically reset CUSUM to spawn repeated incidents.

**Supported by:** CUSUM-debt evidence on diagnosed episodes where |z| is small but C stays >0

Status: proposed only — not implemented

