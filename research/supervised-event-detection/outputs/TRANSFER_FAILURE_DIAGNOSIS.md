# Transfer-failure diagnosis — frozen synthetic pilot

Generated: 2026-10-24T22:37:37-04:00

Preserves frozen pilot model, predictions, `PILOT_RESULTS.md`, and production. **No** retuning, simulator expansion, or 2019 run.

## 1. Feature semantics (all 53)

- Feature set: `pressure_context_v1`
- Scaling: StandardScaler fit on synthetic train rows only (mean/var)
- (x - mean) / scale  then  logit = z·coef + intercept;  q=sigmoid(logit)
- Warm-up before usable rows: **144** steps (12 h)

### Identity checks (synthetic vs measured)

- **pressure_unit**: m junction pressure in both; sensor lists identical (33)
- **pressure_averaging**: Network-wide nanmedian / percentiles over the same PRESSURE_SENSORS order; not a single-sensor or nearest-to-leak average
- **flow_unit_and_direction**: Both domains use m³/h for ['p227', 'p235', 'PUMP_1']. Synthetic: WNTR m³/s×3600. Measured SCADA already m³/h. Empirical sign: no negative samples in either 2018 SCADA or pilot scenarios for these three links (direction encoding matches as non-negative magnitudes on these sensors)
- **tank_level**: Measured: SCADA Levels T1 in m. Synthetic: head(T1)−elevation. Ranges overlap (~2–4 m)
- **timestamp_grid**: 5-minute steps both; synthetic timestamps are scenario-relative seconds
- **feature_code_path**: Identical build_feature_matrix() for synthetic NPZ and measured arrays
- **bug_check_flow_conversion**: Present and consistent; not implicated as a unit bug
- **bug_check_sensor_mapping**: PRESSURE_SENSORS / FLOW_SENSORS / LEVEL_SENSORS shared schema

### Absolute vs change

- Absolute-level features: 9 (sum |coef_z| fraction = **0.364**)
- Change/delta features: 42 (sum |coef_z| fraction = **0.568**)
- Binary/other: 2

| # | Name | Kind | Unit | Window |
|---|------|------|------|--------|
| 0 | `P_median` | absolute_level | m | instant t |
| 1 | `P_p10` | absolute_level | m | instant t |
| 2 | `P_p90` | absolute_level | m | instant t |
| 3 | `P_max` | absolute_level | m | instant t |
| 4 | `P_min` | absolute_level | m | instant t |
| 5 | `P_spread_p90_p10` | spread | m | instant t |
| 6 | `Pd_d1_median` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 7 | `Pd_d1_p10` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 8 | `Pd_d1_p90` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 9 | `Pd_d1_min` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 10 | `Pd_d1_max_abs` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 11 | `Pd_d1_topneg1` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 12 | `Pd_d1_topneg2` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 13 | `Pd_d1_topneg3` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 14 | `Pd_d1_topneg4` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 15 | `Pd_d1_topneg5` | change | m | P(t)-P(t-1 steps) = 0.0833333 h causal delta per sensor, the |
| 16 | `Pd_d6_median` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 17 | `Pd_d6_p10` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 18 | `Pd_d6_p90` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 19 | `Pd_d6_min` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 20 | `Pd_d6_max_abs` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 21 | `Pd_d6_topneg1` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 22 | `Pd_d6_topneg2` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 23 | `Pd_d6_topneg3` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 24 | `Pd_d6_topneg4` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 25 | `Pd_d6_topneg5` | change | m | P(t)-P(t-6 steps) = 0.5 h causal delta per sensor, then aggr |
| 26 | `Pd_d24_median` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 27 | `Pd_d24_p10` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 28 | `Pd_d24_p90` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 29 | `Pd_d24_min` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 30 | `Pd_d24_max_abs` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 31 | `Pd_d24_topneg1` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 32 | `Pd_d24_topneg2` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 33 | `Pd_d24_topneg3` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 34 | `Pd_d24_topneg4` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 35 | `Pd_d24_topneg5` | change | m | P(t)-P(t-24 steps) = 2 h causal delta per sensor, then aggre |
| 36 | `F_p227` | absolute_level | m3/h | instant t |
| 37 | `Fd_p227_d1` | change | m3/h | F(t)-F(t-1) over 0.0833333 h |
| 38 | `Fd_p227_d6` | change | m3/h | F(t)-F(t-6) over 0.5 h |
| 39 | `Fd_p227_d24` | change | m3/h | F(t)-F(t-24) over 2 h |
| 40 | `F_p235` | absolute_level | m3/h | instant t |
| 41 | `Fd_p235_d1` | change | m3/h | F(t)-F(t-1) over 0.0833333 h |
| 42 | `Fd_p235_d6` | change | m3/h | F(t)-F(t-6) over 0.5 h |
| 43 | `Fd_p235_d24` | change | m3/h | F(t)-F(t-24) over 2 h |
| 44 | `F_PUMP_1` | absolute_level | m3/h | instant t |
| 45 | `Fd_PUMP_1_d1` | change | m3/h | F(t)-F(t-1) over 0.0833333 h |
| 46 | `Fd_PUMP_1_d6` | change | m3/h | F(t)-F(t-6) over 0.5 h |
| 47 | `Fd_PUMP_1_d24` | change | m3/h | F(t)-F(t-24) over 2 h |
| 48 | `pump1_on` | binary | {0,1} | instant t |
| 49 | `L_T1` | absolute_level | m | instant t |
| 50 | `Ld_T1_d1` | change | m | L(t)-L(t-1) over 0.0833333 h |
| 51 | `Ld_T1_d6` | change | m | L(t)-L(t-6) over 0.5 h |
| 52 | `Ld_T1_d24` | change | m | L(t)-L(t-24) over 2 h |

### Restart / warm-up / position cues

Scenarios run as continuous 48 h trajectories with leaks starting after 12 h warm-up (not at t=0 restart). Feature warm-up drops the first 12 h so early hydraulic transient is not labeled. However, leak credit windows still co-occur with diurnal pump/tank schedules inside the short scenarios; absolute level and pump-state features can act as **scenario-position / operating-state cues** without requiring a physical leak signature. No evidence that a hard 'restart spike' alone drives labels.

## 2. Frozen classifier

- C=0.01, τ_prob=0.3
- Intercept (logit): -0.6448833368681749

### Top |standardized coefficients|

| Rank | Feature | coef_z | coef / raw unit | train mean | train σ |
|------|---------|--------|-----------------|------------|---------|
| 1 | `Fd_PUMP_1_d24` | +0.4277 | 0.02398420013057796 | 2.446 | 17.83 |
| 2 | `P_median` | +0.4141 | 1.3349383812615716 | 47.37 | 0.3102 |
| 3 | `L_T1` | -0.3663 | -0.8453925703578112 | 2.994 | 0.4333 |
| 4 | `P_min` | -0.3013 | -0.6511052611814053 | 28.32 | 0.4628 |
| 5 | `P_p90` | +0.2793 | 0.9086395749906122 | 54.71 | 0.3073 |
| 6 | `P_max` | +0.2582 | 0.8918517551171583 | 56.31 | 0.2895 |
| 7 | `Pd_d6_p90` | -0.2339 | -2.415788217642454 | 0.03359 | 0.09681 |
| 8 | `P_spread_p90_p10` | +0.2068 | 0.8317938388277635 | 18.15 | 0.2486 |
| 9 | `Fd_PUMP_1_d6` | +0.1546 | 0.017214249411387026 | 0.6117 | 8.98 |
| 10 | `Ld_T1_d1` | +0.1543 | 15.210333052787334 | -3.628e-05 | 0.01014 |
| 11 | `Pd_d6_median` | -0.1436 | -1.7244560289180735 | 0.002874 | 0.08325 |
| 12 | `F_PUMP_1` | +0.1411 | 0.006402472058484068 | 21.1 | 22.04 |
| 13 | `pump1_on` | +0.1410 | 0.2823311782200733 | 0.4783 | 0.4995 |
| 14 | `Pd_d6_max_abs` | -0.1094 | -0.2660166706067938 | 0.1503 | 0.4111 |
| 15 | `Pd_d24_topneg4` | +0.1089 | 0.36754172276343344 | -0.09281 | 0.2962 |
| 16 | `Pd_d24_p10` | +0.1088 | 0.3698599956585985 | -0.08918 | 0.2942 |
| 17 | `Pd_d24_topneg5` | +0.1070 | 0.36914458639845654 | -0.07467 | 0.2899 |
| 18 | `Pd_d24_max_abs` | -0.1045 | -0.25175857382014294 | 0.4302 | 0.4151 |
| 19 | `Fd_p227_d24` | -0.1014 | -0.005242671236837386 | -0.2487 | 19.34 |
| 20 | `Ld_T1_d6` | +0.1001 | 1.6612551635806394 | -0.0009779 | 0.06025 |

### Train-label means (synthetic train rows)

Positive = abrupt credit window rows; negative = other post-warm-up rows in train scenarios (controls + pre/post leak). **Not** proven leak-free.

| Feature | Mean y=1 | Mean y=0 | Δ (pos−neg) |
|---------|----------|----------|-------------|
| `P_median` | 47.52 | 47.36 | +0.1612 |
| `P_min` | 28.35 | 28.32 | +0.0354 |
| `L_T1` | 2.986 | 2.994 | -0.008424 |
| `F_PUMP_1` | 28.82 | 20.6 | +8.213 |
| `pump1_on` | 0.6528 | 0.467 | +0.1857 |
| `Fd_PUMP_1_d24` | 4.147 | 2.336 | +1.811 |
| `Pd_d6_min` | -0.04834 | -0.1016 | +0.05329 |
| `Pd_d24_min` | -0.1631 | -0.2916 | +0.1286 |
| `Pd_d6_topneg1` | -0.04834 | -0.1016 | +0.05329 |
| `Pd_d6_max_abs` | 0.1098 | 0.1529 | -0.04312 |

## 3. Distributions and contributions

### Out-of-training-range (|z|>5) fractions

| Feature | Synthetic leak credit | Synthetic control | Measured event 0–6h | Measured control blocks |
|---------|----------------------|-------------------|---------------------|-------------------------|
| `Fd_PUMP_1_d24` | 0.000 | 0.000 | 0.000 | 0.000 |
| `P_median` | 0.000 | 0.000 | 0.000 | 0.000 |
| `L_T1` | 0.000 | 0.000 | 0.000 | 0.000 |
| `P_min` | 0.000 | 0.000 | 0.000 | 0.000 |
| `P_p90` | 0.000 | 0.000 | 0.000 | 0.000 |
| `P_max` | 0.000 | 0.000 | 0.000 | 0.000 |
| `Pd_d6_p90` | 0.000 | 0.004 | 0.023 | 0.005 |
| `P_spread_p90_p10` | 0.000 | 0.000 | 0.000 | 0.000 |
| `Fd_PUMP_1_d6` | 0.000 | 0.000 | 0.000 | 0.000 |
| `Ld_T1_d1` | 0.000 | 0.000 | 0.000 | 0.000 |
| `Pd_d6_median` | 0.000 | 0.000 | 0.043 | 0.010 |
| `F_PUMP_1` | 0.000 | 0.000 | 0.000 | 0.000 |
| `pump1_on` | 0.000 | 0.000 | 0.000 | 0.000 |
| `Pd_d6_min` | 0.000 | 0.012 | 0.000 | 0.000 |
| `Pd_d24_min` | 0.000 | 0.012 | 0.000 | 0.000 |
| `Pd_d6_topneg1` | 0.000 | 0.012 | 0.000 | 0.000 |
| `Pd_d6_max_abs` | 0.000 | 0.015 | 0.000 | 0.000 |

### Mean feature values (selected)

| Feature | Syn leak | Syn ctrl | Meas event | Meas ctrl |
|---------|----------|----------|------------|-----------|
| `Fd_PUMP_1_d24` | 0.9717 | 2.445 | -2.447 | 0.0004471 |
| `P_median` | 47.42 | 47.3 | 47.01 | 47.09 |
| `L_T1` | 3.079 | 2.993 | 3.143 | 3.123 |
| `P_min` | 28.42 | 28.31 | 28.18 | 28.2 |
| `P_p90` | 54.75 | 54.65 | 54.36 | 54.45 |
| `P_max` | 56.35 | 56.25 | 55.98 | 56.08 |
| `Pd_d6_p90` | 0.03032 | 0.03704 | 0.0339 | 0.06677 |
| `P_spread_p90_p10` | 18.1 | 18.15 | 18.09 | 18.11 |
| `Fd_PUMP_1_d6` | 0.1793 | 0.6114 | -0.6137 | 5.893e-05 |
| `Ld_T1_d1` | 0.001426 | 6.592e-05 | -0.003059 | 0 |
| `Pd_d6_median` | 0.003786 | 0.003291 | -0.04733 | 0.000312 |
| `F_PUMP_1` | 23.67 | 22.25 | 22.19 | 26.45 |
| `pump1_on` | 0.5365 | 0.5046 | 0.5046 | 0.6014 |
| `Pd_d6_min` | -0.06001 | -0.1125 | -0.1828 | -0.1216 |
| `Pd_d24_min` | -0.2294 | -0.299 | -0.4862 | -0.2818 |
| `Pd_d6_topneg1` | -0.06001 | -0.1125 | -0.1828 | -0.1216 |
| `Pd_d6_max_abs` | 0.113 | 0.1687 | 0.2529 | 0.2158 |

### Mean linear-score contributions (selected features)

Mean logit: syn_leak=-0.5735, syn_ctrl=-0.8902, meas_event=-2.669, meas_ctrl=-1.815

| Feature | Syn leak contrib | Syn ctrl | Meas event | Meas ctrl |
|---------|------------------|----------|------------|-----------|
| `Fd_PUMP_1_d24` | -0.03535 | -2.507e-05 | -0.1173 | -0.05865 |
| `P_median` | +0.05791 | -0.1012 | -0.4833 | -0.3767 |
| `L_T1` | -0.07229 | +0.0007452 | -0.1262 | -0.109 |
| `P_min` | -0.06209 | +0.008778 | +0.0903 | +0.08005 |
| `P_p90` | +0.03666 | -0.05988 | -0.3244 | -0.2377 |
| `P_max` | +0.03085 | -0.05351 | -0.2986 | -0.2093 |
| `Pd_d6_p90` | +0.007911 | -0.008322 | -0.0007257 | -0.08014 |
| `P_spread_p90_p10` | -0.04375 | -0.006192 | -0.0526 | -0.03555 |
| `Fd_PUMP_1_d6` | -0.007444 | -3.662e-06 | -0.02109 | -0.01053 |
| `Ld_T1_d1` | +0.02224 | +0.001555 | -0.04598 | +0.0005519 |
| `Pd_d6_median` | -0.001574 | -0.0007201 | +0.08657 | +0.004417 |
| `F_PUMP_1` | +0.01647 | +0.007367 | +0.007001 | +0.03423 |
| `pump1_on` | +0.01643 | +0.007439 | +0.007424 | +0.03476 |
| `Pd_d6_min` | +0.005165 | -0.001898 | -0.01135 | -0.003124 |
| `Pd_d24_min` | +0.003571 | -0.0009921 | -0.01328 | +0.000134 |
| `Pd_d6_topneg1` | +0.005165 | -0.001898 | -0.01135 | -0.003124 |
| `Pd_d6_max_abs` | +0.009915 | -0.004903 | -0.02731 | -0.01742 |

### What explains failed measured 6h timing

On measured abrupt 0–6 h windows, mean logit=-2.669 vs control=-1.815 (synthetic leak=-0.574, synthetic control=-0.890). Pilot notifications on 2018 often arrive after 6 h (HIT>6 in PILOT_RESULTS) while flooding unmatched episodes — consistent with a score driven by slow absolute operating-level / pump-context drift rather than a sharp onset-aligned pressure-drop feature. Train-label polarity for `Pd_d6_min` is **wrong-signed for a drop detector** (pos mean -0.04834 vs neg -0.1016: positives are *less* negative). `pump1_on` is higher on positives (0.653 vs 0.467). Absolute-level features carry **36%** of Σ|coef_z|.

## 4. Competing explanations — evidence

### unit_or_feature_implementation_mismatch

- Verdict: **not supported as primary cause**
- Shared feature builder; pressure/tank ranges overlap; flows converted m³/s→m³/h; no sign mismatch on the three SCADA flow channels. OOD |z|>5 rates on measured absolute levels are low for P_median-family relative to a pure unit-scale failure.

### absolute_operating_level_shift

- Verdict: **partially supported (important but incomplete)**
- Absolute features are 36% of coefficient mass; P_median, L_T1, P_min, P_p90 rank in the top coefficients. Measured vs synthetic means for P_median are close (~47 m), so a gross level offset alone does not explain transfer failure — but the *use* of absolute levels as leak proxies fails when measured diurnal/seasonal operating trajectories differ from 48 h nominal scenarios.

### unrealistic_simulated_leak_response

- Verdict: **supported for network-summary drop features**
- Across synthetic leak scenarios, network-wide `Pd_d6_min` is not reliably more negative in credit windows than outside them (train: positives less negative than negatives). Aggregate pressure-drop features therefore do not encode a strong, consistent leak onset signature in the pilot simulations — so even a perfect transfer of those features would be weak.

### simulation_specific_nuisance_shortcuts

- Verdict: **supported as a driver of synthetic metrics**
- Top coefficients include Fd_PUMP_1_d24, F_PUMP_1, pump1_on, L_T1, and absolute pressure levels. Synthetic scenario recall can rise when credit windows correlate with pump/tank state even though pressure-drop polarity is wrong-signed. That is a nuisance shortcut relative to the stated leak-change question — not proof of physical leak detection.

### inadequate_feature_separation

- Verdict: **supported**
- Change features that should separate leaks (Pd_*_min / topneg) do not separate train positives from negatives in the expected direction; synthetic_dev selection still picked τ=0.3 with high FP row rate (~0.49). Inadequate separation in the intended residual/change subspace plus shortcut features jointly explain high synthetic scenario recall without measured 6 h sensitivity.

## 5. Recommended controlled intervention (one)

**One controlled intervention:** replace absolute pressure/flow/tank *levels* with an identical causal **change/residual representation** in both domains — e.g. keep only Pd_*/Fd_*/Ld_* (and optionally z-scored deltas against a past-only rolling reference), drop P_median/P_*/F_*/L_T1 raw levels and pump1_on level proxies from the feature set; refit under the same L2 budget on synthetic data only. Apply the same builder to measured SCADA.

**Why this and not 'just normalize harder':** StandardScaler already removes gross mean/variance per feature on synthetic train; measured absolute means are already similar. The failure mode is **feature semantics / shortcut use of operating state**, not a simple affine domain shift. If simulated network-wide drop responses remain weak or wrong-signed after removing levels, normalization alone cannot create a transferable leak onset cue — that would require different simulation physics or different spatial summaries (out of scope here).

**No implementation bug found** that warrants a silent protocol correction rerun. Stop before another fit.

## Non-goals

- No model retune / budget expansion
- No simulator search
- No 2019
- Frozen pilot artifacts unchanged (diagnosis-only outputs)

