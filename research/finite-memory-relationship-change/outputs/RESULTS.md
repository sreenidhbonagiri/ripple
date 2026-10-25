# FMR3C results — finite-memory recent–reference residual change

Generated: 2026-10-24T21:47:32-04:00

Preserves production and all prior detector reports. CUSUM-family results untouched. 2019 not evaluated.

Grid: LQ=[2.0, 6.0], LR=[24.0, 48.0], tau=[3.0, 4.0, 5.0, 6.0] (16 settings). recover_steps=12.
Provisional gates: abrupt 6h recall ≥ 0.6667, unmatched/week ≤ 3 (not operator-validated).

## Input hashes

- `2018_SCADA_Pressures.csv`: `7782d890a7195699be94ddc01cba392da7ca285908afff619065a9616e04dcae`
- `2018_SCADA_Flows.csv`: `7f7e8625c9d92b083ee079a54cffb9ef803876de1e35017c1da0455968daf3ff`
- `2018_SCADA_Levels.csv`: `a1fc5f0229448a620b6220f4d079b3162a255b3070acdce448608fbfc760903c`
- DEV z sha256[:16]: `ad73a40a8a17d109`

## Synthetic correlated no-change (not for tuning)

Honesty check on temporally correlated synthetic no-change inputs. Do not retune tau after DIAG.

- rho=0.0, LQ=2.0, LR=24.0: exceedance={'tau_3': 0.0036255065045851993, 'tau_4': 0.00021326508850501172, 'tau_5': 0.0, 'tau_6': 0.0}
- rho=0.0, LQ=6.0, LR=48.0: exceedance={'tau_3': 0.014932230645531817, 'tau_4': 0.0, 'tau_5': 0.0, 'tau_6': 0.0}
- rho=0.5, LQ=2.0, LR=24.0: exceedance={'tau_3': 0.0008530603540200469, 'tau_4': 0.0, 'tau_5': 0.0, 'tau_6': 0.0}
- rho=0.5, LQ=6.0, LR=48.0: exceedance={'tau_3': 0.0, 'tau_4': 0.0, 'tau_5': 0.0, 'tau_6': 0.0}
- rho=0.8, LQ=2.0, LR=24.0: exceedance={'tau_3': 0.0, 'tau_4': 0.0, 'tau_5': 0.0, 'tau_6': 0.0}
- rho=0.8, LQ=6.0, LR=48.0: exceedance={'tau_3': 0.0, 'tau_4': 0.0, 'tau_5': 0.0, 'tau_6': 0.0}

## DEV grid (every setting)

| LQ | LR | tau | Abrupt6h | Unmatched/wk | Dup | Union% | Sensor% | Med/Longest ep (h) | Censored | Episodes | Latch? |
|----|----|-----|----------|--------------|-----|--------|---------|--------------------|----------|----------|--------|
| 2 | 24 | 3 | 1.00 | 196.46 | 5080 | 98.87 | 22.24 | 4.8/45.25 | 9 | 5088 | no |
| 2 | 24 | 4 | 1.00 | 126.81 | 3279 | 93.29 | 14.65 | 4.9/44.333333333333336 | 6 | 3287 | no |
| 2 | 24 | 5 | 1.00 | 82.57 | 2135 | 82.85 | 10.09 | 5.2/44.25 | 3 | 2143 | no |
| 2 | 24 | 6 | 1.00 | 57.70 | 1492 | 71.33 | 7.37 | 5.3/44.083333333333336 | 2 | 1500 | no |
| 2 | 48 | 3 | 1.00 | 191.82 | 4960 | 98.23 | 22.71 | 4.8/92.83333333333333 | 10 | 4968 | no |
| 2 | 48 | 4 | 1.00 | 124.26 | 3213 | 93.59 | 15.31 | 4.9/92.41666666666667 | 5 | 3221 | no |
| 2 | 48 | 5 | 1.00 | 81.25 | 2101 | 83.44 | 10.80 | 5.2/92.16666666666667 | 4 | 2109 | no |
| 2 | 48 | 6 | 1.00 | 56.81 | 1469 | 73.48 | 8.13 | 5.4/92.0 | 3 | 1477 | no |
| 6 | 24 | 3 | 1.00 | 152.99 | 3956 | 98.70 | 24.87 | 7.6/64.58333333333333 | 12 | 3964 | no |
| 6 | 24 | 4 | 1.00 | 112.89 | 2919 | 95.23 | 17.93 | 7.2/64.58333333333333 | 9 | 2927 | no |
| 6 | 24 | 5 | 1.00 | 80.79 | 2089 | 87.45 | 13.13 | 7.2/63.25 | 4 | 2097 | no |
| 6 | 24 | 6 | 1.00 | 61.03 | 1578 | 78.47 | 10.01 | 7.2/52.666666666666664 | 2 | 1586 | no |
| 6 | 48 | 3 | 1.00 | 148.86 | 3849 | 98.26 | 25.77 | 7.7/114.41666666666667 | 13 | 3857 | no |
| 6 | 48 | 4 | 1.00 | 113.47 | 2934 | 95.66 | 19.24 | 7.2/114.33333333333333 | 9 | 2942 | no |
| 6 | 48 | 5 | 1.00 | 82.53 | 2134 | 89.18 | 14.33 | 7.2/114.33333333333333 | 4 | 2142 | no |
| 6 | 48 | 6 | 1.00 | 61.96 | 1602 | 81.70 | 11.17 | 7.2/114.16666666666667 | 3 | 1610 | no |

## Selection

- gate_met: **False**
- selected: **None**
- rule: among abrupt6h>=2/3 and unmatched/wk<=3: max abrupt6h recall, then min unmatched/wk, then min median 6h delay
- note: No DEV setting met both provisional gates; DIAG not run.

**Selection failure:** no DEV setting met both provisional gates. DIAG not run under a new setting.

## Recommendation

**Selection failure / no-go:** no setting in the registered 16-cell FMR3C grid met both provisional DEV gates (abrupt 6h recall ≥ 2/3 and unmatched/week ≤ 3). Do not invent a winner; do not enlarge the grid; do not retune from synthetic or DIAG.

