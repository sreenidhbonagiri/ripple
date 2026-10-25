# FMR3C empirical threshold calibration — DEV percentiles

Generated: 2026-10-24T21:52:06-04:00

Preserves `RESULTS.md` (heuristic τ grid) and all other experiments. Production untouched. 2019 not evaluated.

## Cumulative development history

1. Registered FMR3C design (finite-memory recent–reference on `build_signals.z`).
2. Original 16-cell heuristic τ∈{3,4,5,6} × LQ/LR grid → **selection failure** (abrupt 6h=1.00 but unmatched/wk ≥ 56.8); see `RESULTS.md`.
3. **This calibration:** freeze LQ=2h, LR=48h (additional DEV decision from lowest unmatched among that grid); derive common τ from DEV pooled score percentiles; full episode pipeline per threshold.

Frozen windows: LQ=2h, LR=48h. AR(1)-standardized scores are **not** confidence levels.
Provisional gates: abrupt 6h ≥ 0.6667, unmatched/wk ≤ 3.

## Input hashes

- `2018_SCADA_Pressures.csv`: `7782d890a7195699be94ddc01cba392da7ca285908afff619065a9616e04dcae`
- `2018_SCADA_Flows.csv`: `7f7e8625c9d92b083ee079a54cffb9ef803876de1e35017c1da0455968daf3ff`
- `2018_SCADA_Levels.csv`: `a1fc5f0229448a620b6220f4d079b3162a255b3070acdce448608fbfc760903c`
- DEV z sha256[:16]: `ad73a40a8a17d109`

## Pooled DEV score distribution

- n_pooled_finite: **1567401** across 33 eligible sensors
- pooled median / p90 / max: {'median': 0.03330766975101093, 'p90': 3.705784099640855, 'max': 293.1514892881597}
- Dominance: No sensor exceeds dominance warning fraction of pooled mass.

DEV pooled scores include leaks and operating changes; percentiles are not leak-free FP calibration. Sample exceedance ≠ notification burden under temporal correlation / episode semantics.

### Per-sensor contribution (top by count)

| Sensor | n_finite | fraction | median | p99 | max |
|--------|----------|----------|--------|-----|-----|
| n1 | 47497 | 0.030 | 0.1807658613275527 | 14.68171150262992 | 23.683298522317642 |
| n4 | 47497 | 0.030 | -0.006997469987224224 | 5.635339536505682 | 22.317067078568954 |
| n31 | 47497 | 0.030 | 0.04251496721230646 | 1.8462194314459532 | 2.2538362794832074 |
| n54 | 47497 | 0.030 | -0.024364515769197157 | 3.131198911250521 | 4.591995042719295 |
| n105 | 47497 | 0.030 | 0.04440228497261326 | 10.081280064558761 | 19.60832541287334 |
| n114 | 47497 | 0.030 | 0.25346708456401346 | 8.080803170488988 | 13.311947517012907 |
| n163 | 47497 | 0.030 | -0.06253608204592025 | 23.58338742823962 | 77.49793058666154 |
| n188 | 47497 | 0.030 | -0.0798701417818644 | 4.508662429021822 | 8.794971957243016 |
| n215 | 47497 | 0.030 | 0.12258187627615441 | 19.233747188425514 | 134.34934460081072 |
| n229 | 47497 | 0.030 | -0.14480112402661408 | 78.22191018400902 | 233.32027141338278 |
| n288 | 47497 | 0.030 | 0.5771822924962621 | 9.727212058840763 | 20.91920170188562 |
| n296 | 47497 | 0.030 | 0.026137701092690174 | 36.04326484164426 | 293.1514892881597 |
| n332 | 47497 | 0.030 | 0.196328292052246 | 6.927235775366249 | 16.020891406406637 |
| n342 | 47497 | 0.030 | 0.34410866647227917 | 28.917742733626902 | 54.66146901128564 |
| n410 | 47497 | 0.030 | 0.057450302661596404 | 6.267861146977854 | 10.231656719804793 |
| … | (18 more) | | | | |

### Empirical thresholds

| Percentile | τ |
|------------|---|
| 99 | 16.944854039600123 |
| 99.5 | 26.732944547756674 |
| 99.9 | 79.16551104763799 |
| 99.95 | 126.83428150435307 |
| 99.99 | 255.70314494112546 |

## DEV tradeoff (full episode pipeline)

| pct | τ | Emp. exceed | Abrupt6h | Unmatched/wk | Dup | Union% | Sensor% | Med/Longest (h) | Censored | Episodes | Latch? |
|-----|---|-------------|----------|--------------|-----|--------|---------|-----------------|----------|----------|--------|
| 99 | 16.9449 | 0.010001 | 1.00 | 6.57 | 162 | 23.56 | 1.55 | 6.8/40.083333333333336 | 0 | 178 | no |
| 99.5 | 26.7329 | 0.005001 | 1.00 | 2.55 | 59 | 12.78 | 0.77 | 10.7/38.5 | 0 | 71 | no |
| 99.9 | 79.1655 | 0.001000 | 0.67 | 0.23 | 5 | 2.54 | 0.15 | 26.4/31.0 | 0 | 8 | no |
| 99.95 | 126.834 | 0.000500 | 0.67 | 0.08 | 2 | 1.39 | 0.07 | 25.8/29.5 | 0 | 4 | no |
| 99.99 | 255.703 | 0.000100 | 0.33 | 0.00 | 0 | 0.64 | 0.02 | 25.5/25.5 | 0 | 1 | no |

## Selection

- gate_met: **True**
- selected: **{'percentile': 99.5, 'tau': 26.732944547756674}**
- rule: among abrupt6h>=2/3 and unmatched/wk<=3 and not latched_suspect: max abrupt6h recall, then min unmatched/wk, then min median 6h delay
- note: 

## DIAG (frozen numeric τ — diagnostic; prior examination)

- Threshold frozen from DEV: τ=26.732944547756674 (percentile 99.5); **not** recomputed on DIAG.
- Abrupt 6h recall: **0.33** (1/3)
- Abrupt recall (7d window): **0.33** delays={'n': 1, 'median': 0.9166666666666666, 'max': 0.9166666666666666, 'values': [0.9166666666666666]}
- Incipient: **1.00**
- Unmatched/wk: **0.08**; dup: 2
- Union%: 1.29; sensor%: 0.06
- Median/longest ep (h): 18.833333333333332/26.0; censored: 0
- Latch: No strong latched-only signature under declared heuristics.

Per-event (post-training):

- HIT p810 (incipient) onset=2018-07-28 03:05 notify=2018-08-07 03:35 delay_h=240.5 sensor=n752
- MISS p183 (abrupt) onset=2018-08-07 02:35 notify=None delay_h=None sensor=None
- HIT p158 (abrupt) onset=2018-10-06 02:35 notify=2018-10-06 03:30 delay_h=0.9166666666666666 sensor=n644
- MISS p369 (abrupt) onset=2018-10-26 02:05 notify=None delay_h=None sensor=None

Prefix (separate):

- MISS p654 (incipient) notify=None delay_h=None

## Notification-time shifted null — 0–2 h (diagnostic)

- Observed abrupt matches: **2** / 3
- Null median (min–max): 0.0 (0–1)
- Frac shifts ≥ obs: **0.00** (n_shifts=89)

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

## Notification-time shifted null — 0–6 h (diagnostic)

- Observed abrupt matches: **2** / 3
- Null median (min–max): 0.0 (0–1)
- Frac shifts ≥ obs: **0.00** (n_shifts=89)

Newly added diagnostic — not the registered 7-day headline. Overlapping shifts are dependent; n is small.

## Interpretation

Frozen τ≈26.73 from DEV p99.5 met both **DEV** provisional gates (abrupt 6h=1.00, unmatched/wk=2.55) with short episodes (no latch signature). On **DIAG** (diagnostic; prior examination): burden stayed low (unmatched/wk=0.08, union≈1.3%) but **useful abrupt 6h recall fell to 1/3** (p158 only; p183/p369 missed under primary matching). Null 0–2h/0–6h observed abrupt counts (2/3) can exceed primary abrupt-6h recall when long-window incipient matching consumes episodes that short-window null matching leaves free — primary post-training abrupt-6h recall remains the selection metric. Answer to the calibration question: high DEV historical percentiles can thin notifications, but leak-associated DIAG excursions are **not** reliably extreme enough vs that bar for useful timed alerts.

## Recommendation

**No-go:** frozen empirical τ loses useful six-hour abrupt sensitivity on DIAG.

