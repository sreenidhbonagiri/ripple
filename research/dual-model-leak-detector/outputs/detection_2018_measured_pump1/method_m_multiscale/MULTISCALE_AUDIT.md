# Multiscale Method M — post-hoc audit (no fitting)

Generated: `2026-10-25T06:01:56.419291+00:00`  
2018 already examined; audit only. No fitting, τ changes, 2019, or deploy.

Frozen combined τ=`5.284`; baseline Method M τ=`4.347`.

## Method

- Per-scale scores: own SCALE σ and own median calibration (forensic).
- Combined stream: archived `score_MS_combined.csv` + frozen τ (unchanged).
- Event window: **6 h from onset/startTime** (same credit rule as evaluation).
- Controls: DEV 6 h windows, exclude ±72 h of all labeled onsets, every 24th start.
- No sensor/window selection per event; no τ retune; no 2019.

DEV score correlations: `{'short_medium': 0.8979110288374555, 'short_long': 0.6387615550492103, 'medium_long': 0.8022920177963991}`  
Notify-hour timescale winners (combined raw max): `{'short': 0, 'medium': 2, 'long': 4, 'unknown': 0}`

## Abrupt events — per-scale maxima and DEV percentiles

| Pipe | Period | short max (pct) | medium max (pct) | long max (pct) | combined max (pct) | hit M | hit MS | drivers |
|------|--------|----------------:|-----------------:|---------------:|-------------------:|:-----:|:------:|---------|
| p673 | DEV | 6.578 (100.0%) | 6.532 (99.9%) | 6.463 (99.8%) | 6.106 (99.8%) | True | True | medium |
| p538 | DEV | 4.280 (99.5%) | 4.853 (99.3%) | 5.153 (98.7%) | 4.868 (98.7%) | True | False | — |
| p866 | DEV | 6.196 (99.9%) | 6.450 (99.9%) | 6.562 (99.9%) | 6.200 (99.9%) | True | True | long |
| p183 | DIAG | 2.228 (96.4%) | 2.496 (96.5%) | 2.621 (92.3%) | 2.476 (92.2%) | False | False | — |
| p158 | DIAG | 5.098 (99.6%) | 5.844 (99.6%) | 5.852 (99.3%) | 5.529 (99.3%) | True | True | long |
| p369 | DIAG | 2.115 (95.9%) | 2.360 (95.8%) | 2.279 (90.2%) | 2.202 (90.2%) | False | False | — |

## Incipient events — same windows

| Pipe | Period | short max (pct) | medium max (pct) | long max (pct) | long frac≥p95 | vs ctrl pct | notified |
|------|--------|----------------:|-----------------:|---------------:|--------------:|------------:|:--------:|
| p461 | DEV | 1.498 (88.9%) | 1.291 (81.8%) | 1.283 (74.6%) | 0.000 | 96.0% | False |
| p232 | DEV | 1.704 (92.4%) | 1.580 (89.7%) | 1.609 (83.7%) | 0.000 | 96.0% | False |
| p427 | DEV | 0.986 (56.3%) | 1.005 (59.1%) | 1.137 (65.6%) | 0.000 | 96.0% | False |
| p810 | DIAG | 1.712 (92.6%) | 1.493 (88.2%) | 1.293 (74.9%) | 0.000 | 96.0% | False |
| p628 | DEV | 1.092 (67.6%) | 1.063 (64.7%) | 1.028 (54.9%) | 0.000 | 96.0% | False |
| p31 | DEV | 1.287 (81.4%) | 1.233 (78.9%) | 1.229 (71.9%) | 0.000 | 96.0% | False |
| p654 | DIAG | 1.208 (76.8%) | 1.030 (61.6%) | 1.165 (67.7%) | 0.000 | 96.0% | False |

## Was p538 lost because joint-max calibration raised the threshold?

- Medium (baseline) max in credit: `4.853` vs τ_M=`4.347` → hit `True`
- Combined max in credit: `4.868` vs τ_MS=`5.284` → hit `False`
- Counterfactual: medium max vs τ_MS → `False`
- Counterfactual: combined max vs τ_M → `True`
- Per-scale maxima: `{'short': 4.280481974648011, 'medium': 4.853290243682559, 'long': 5.153243074390375}`
- **Raised τ alone explains miss:** `True`
- **Joint score shape (not τ) explains miss:** `False`

Compare (medium max vs τ_MS) vs (combined max vs τ_M). If medium max < τ_MS, the higher selected τ alone would miss p538 even on the baseline medium score.

## Incipient long-scale sustained unusual vs controls?

- **p461** (DEV): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p232** (DEV): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p427** (DEV): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p810** (DIAG): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p628** (DEV): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p31** (DEV): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **p654** (DIAG): long_frac≥DEV_p95=`0.000`, vs controls pct=`96.0%`, sustained_unusual=`False`, notified=`False`
- **None** of the incipient 6 h windows met sustained-unusual criteria (≥50% hours ≥ DEV long p95 and that fraction ≥95th pct of controls).

## Redundancy vs distinct evidence

- DEV correlations: `{'short_medium': 0.8979110288374555, 'short_long': 0.6387615550492103, 'medium_long': 0.8022920177963991}`
- Event windows with unique scale leader: `{'short': ['p673', 'p461', 'p232', 'p810', 'p628', 'p31', 'p654'], 'medium': ['p369'], 'long': ['p538', 'p866', 'p183', 'p158', 'p427'], 'tie': []}`
- Notify drivers: `{'short': 0, 'medium': 2, 'long': 4, 'unknown': 0}`
- Distinct long-only incipient candidates: `[]`

## Gains and counterexamples (together)

- **Gain vs baseline abrupt notify:** none in the completed selection (see experiment results).
- **Counterexample / regression:** p538 DEV hit→miss under combined τ; DIAG abrupt identical (p158 only).
- **Incipient:** no notifies at selected τ; no distinct sustained long-only signal under audit rules.

## Recommendation

- Distinct useful evidence: **`False`**
- Close multiscale as unsuccessful: **`True`**
- Next experiment: `None`

No incipient 6h window showed sustained long-scale elevation (frac≥0.5 of hours ≥ DEV long p95) that was ≥95th percentile of ordinary controls. DEV per-scale correlations: {'short_medium': 0.8979110288374555, 'short_long': 0.6387615550492103, 'medium_long': 0.8022920177963991}. Notify drivers at τ=5.284: {'short': 0, 'medium': 2, 'long': 4, 'unknown': 0}. Joint selection raised τ (4.347→5.284) and lost p538; DIAG abrupt unchanged vs baseline. Close multiscale as unsuccessful.

## Stop

No threshold changes, new selection runs, 2019, production, or deployment.

