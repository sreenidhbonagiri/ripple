# Method M scale-transfer audit

Generated: `2026-10-25T05:17:28.454999+00:00`  
No fitting, threshold changes, or Method M reruns. Preserves prior results.

Diagnostic audit only; no Method M refit, τ change, or dual rebuild. Non-onset neighborhoods are not treated as leak-free.

January SCALE: `2018-01-09 01:00:00` → `2018-01-21 23:00:00`. Monthly σ = std of causal δ_i on hours **outside** ±72 h of registered abrupt onsets (operating sample — **not** labeled leak-free).

## Per-month scale transfer (median over sensors of σ_month/σ_SCALE)

| Month | n sens | ratio median | p10 | p90 | frac>1.5 | frac<2/3 |
|-------|-------:|-------------:|----:|----:|---------:|---------:|
| 2018-01 | 33 | 0.964 | 0.940 | 0.988 | 0.00 | 0.00 |
| 2018-02 | 33 | 0.925 | 0.845 | 1.006 | 0.00 | 0.03 |
| 2018-03 | 33 | 0.881 | 0.806 | 0.990 | 0.03 | 0.03 |
| 2018-04 | 33 | 0.937 | 0.877 | 1.008 | 0.00 | 0.03 |
| 2018-05 | 33 | 0.946 | 0.840 | 1.020 | 0.00 | 0.03 |
| 2018-06 | 33 | 0.930 | 0.837 | 1.029 | 0.03 | 0.03 |
| 2018-07 | 33 | 0.977 | 0.776 | 1.071 | 0.00 | 0.06 |
| 2018-08 | 33 | 0.915 | 0.782 | 1.024 | 0.00 | 0.03 |
| 2018-09 | 33 | 0.923 | 0.840 | 0.986 | 0.00 | 0.03 |
| 2018-10 | 33 | 0.861 | 0.741 | 0.978 | 0.00 | 0.06 |
| 2018-11 | 33 | 0.852 | 0.781 | 0.959 | 0.00 | 0.03 |
| 2018-12 | 33 | 0.861 | 0.790 | 0.960 | 0.00 | 0.03 |

Numerator vs normalization: ratios >1 mean later ordinary |δ| dispersion exceeds January SCALE σ (January scales are **tight** relative to later months). Ratios <1 mean January scales are **loose** later.

## Focus misses p183 & p369

Contrasts: credit-window network max |δ|, max |δ|/σ_SCALE, max |δ|/σ_month vs operating-matched controls (HOD + PRE Q_ext/PUMP_1).

### p183 (2018-08-07 02:35:00)

- **Verdict:** `mixed_or_unclear`
- Credit max s_M=2.496 (τ=4.347); n_ctrl=25.
- Event max|δ|=11.508 (n342); max z_SCALE=4.603 (n752); max z_month=6.094 (n752).
- SNR vs controls — |δ|: -0.68; z_SCALE: 1.32; z_month: 2.45; s_M: 1.32.
- Ctrl means — |δ|=12.351, z_SCALE=3.667, z_month=4.091.
- Top |δ| sensors: [('n342', 11.508487034203426), ('n188', 10.114814037020551), ('n429', 8.666715932486113), ('n752', 8.568481255788356), ('n114', 7.102318912278861)]
- Top z_SCALE sensors: [('n752', 4.603308063798568), ('n519', 4.166034313392213), ('n644', 3.798266473621191), ('n342', 3.7927818068987964), ('n458', 3.7632071111243053)]
- Top z_month sensors: [('n752', 6.093618629443226), ('n458', 4.723278094810768), ('n636', 4.298237019608839), ('n342', 4.212796174826566), ('n519', 4.115809127700538)]

### p369 (2018-10-26 02:05:00)

- **Verdict:** `weak_vs_contemporaneous_ordinary`
- Credit max s_M=2.360 (τ=4.347); n_ctrl=25.
- Event max|δ|=13.871 (n429); max z_SCALE=4.351 (n410); max z_month=5.087 (n410).
- SNR vs controls — |δ|: 1.16; z_SCALE: 1.58; z_month: 1.01; s_M: 1.58.
- Ctrl means — |δ|=11.117, z_SCALE=3.154, z_month=3.848.
- Top |δ| sensors: [('n429', 13.871471753940568), ('n54', 7.355370077770203), ('n410', 5.9694379595748615), ('n105', 5.080067056696862), ('n342', 4.758113653748296)]
- Top z_SCALE sensors: [('n410', 4.351402280578654), ('n429', 2.923806448118123), ('n105', 2.4214417506433064), ('n679', 2.092280677599852), ('n740', 1.881975641666895)]
- Top z_month sensors: [('n410', 5.0870926824970155), ('n429', 3.609216372949811), ('n105', 2.642722043440182), ('n769', 2.3568140838150127), ('n679', 2.138693748396007)]

## DIAG timing nulls (actual counts — not only percentile)

- **N null replicates:** 200
- **|E| true DIAG abrupt events:** 3
- **Total onset timestamp draws:** 600 (= N × |E| = 200 × 3)
- **Fixed DIAG notifies at τ=4.347:** 2
- **True recall:** 0.3333333333333333
- **Null recall mean ± std:** 0.0067 ± 0.0467
- **Percentile definition:** fraction of nulls with recall ≤ true = 1.0 (200/200 nulls)
- **Nulls with recall ≥ true:** 4/200
- **Null recall value counts:** `{'0.0': 196, '0.333333': 4}`

### Assignment rules

Density-matched timing nulls: for each of N null replicates, sample |E| candidate onsets uniformly from DIAG eligible hours that match the empirical hour-of-day of the true abrupt onsets (one draw per true event HOD). Episodes/notifies are fixed from the score series at frozen τ; a null onset is a hit if any notify falls in [onset, onset+6h]. True percentile = fraction of null recalls ≤ true recall.

- Eligible hours: DIAG index hours with t >= DIAG_START + WARMUP_HOURS (25h)
- Matching: hour-of-day of each true abrupt onset
- Hit rule: any Method M notify in credit window [t0, t0+6h]
- RNG seed: 2031

## Recommendation

**Do not recommend causal scale adaptation** on this evidence.

Evidence does not cleanly support causal scale adaptation: focus verdicts=['mixed_or_unclear', 'weak_vs_contemporaneous_ordinary']; median Jul–Dec σ ratio≈0.90.

### Growing-leak absorption

Causal rolling/adapting σ_i estimated on a recent window that includes a slowly growing leak will inflate σ_i as |δ_i| grows, so |δ_i|/σ_i can remain ordinary even while the physical leak enlarges — adaptation can absorb growing leaks.

Even if SCALE transfer is imperfect, recommending adaptation requires that obscuring from stale January scales dominate, and that absorption risk is accepted or mitigated (e.g. floor σ, exclude high-|δ| hours from scale updates, or dual timescales). This audit does not implement adaptation.

## Notes

- Full sensor set; no leak-based sensor selection.
- Per-sensor month ratios: `per_sensor_month_scale_ratios.csv`.
- No 2019 / UI / Tiger / deployment / Method M parameter changes.

