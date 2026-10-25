# Phase-matched leak/control pair audit

Generated: 2026-10-24T23:39:06-04:00

Frozen phase-correction model only — **no refit**. Ground truth aligns onset windows for diagnostics; it does not enter prediction.

Frozen: C=10.0, τ=0.7 (`outputs/phase_correction/frozen_model.json`).

## Method

- 16 matched pairs share `pattern_phase_offset_hours` (demand scales may differ).
- At each scenario timestamp t: compare leak vs control features, q, notifier state.
- Windows: pre = [onset−6h, onset), credit = [onset, onset+6h] (GT alignment only).
- “Exceed ordinary control”: |mean Δfeature| > 2× control’s within-window temporal std.
- Leak discharge not in NPZ; PUMP_1 is external-inflow proxy; effect = paired deltas.

## Train + synthetic_dev (decision basis)

```json
{
  "label": "train_and_synthetic_dev",
  "n_pairs": 8,
  "n_episode_6h_hit": 2,
  "episode_6h_recall": 0.25,
  "n_useful_physical_delta": 3,
  "n_classifier_ignores_delta": 1,
  "frac_useful_physical": 0.375,
  "frac_classifier_ignores": 0.125,
  "mean_abs_delta_change_feats": {
    "pre_mean": 0.21265537248728977,
    "credit_mean": 0.3188985544063456,
    "lift_credit_minus_pre": 0.10624318191905585
  },
  "frac_change_feats_exceed_2x_ctrl_std": {
    "pre_mean": 0.044642857142857144,
    "credit_mean": 0.026785714285714284,
    "lift_credit_minus_pre": -0.01785714285714286
  },
  "q_gap_leak_minus_ctrl": {
    "pre_mean": 0.011188871382477344,
    "credit_mean": 0.07613389469837173,
    "lift_credit_minus_pre": 0.06494502331589438
  },
  "sum_abs_logit_contrib_from_delta": {
    "pre_mean": 41.4353954318644,
    "credit_mean": 47.19934865359737,
    "lift_credit_minus_pre": 5.763953221732969
  },
  "net_logit_contrib_from_delta": {
    "pre_mean": 0.04511487594925106,
    "credit_mean": 0.31629931658400795,
    "lift_credit_minus_pre": 0.2711844406347569
  },
  "pump_delta_over_ctrl": {
    "pre_mean": -0.23979230647402822,
    "credit_mean": 0.15200830868119397
  }
}
```

## Synthetic_test (diagnostic only)

```json
{
  "label": "synthetic_test_diagnostic",
  "n_pairs": 8,
  "n_episode_6h_hit": 3,
  "episode_6h_recall": 0.375,
  "n_useful_physical_delta": 5,
  "n_classifier_ignores_delta": 3,
  "frac_useful_physical": 0.625,
  "frac_classifier_ignores": 0.375,
  "mean_abs_delta_change_feats": {
    "pre_mean": 0.30162690341119164,
    "credit_mean": 0.26499784842917506,
    "lift_credit_minus_pre": -0.03662905498201657
  },
  "frac_change_feats_exceed_2x_ctrl_std": {
    "pre_mean": 0.06845238095238095,
    "credit_mean": 0.05952380952380952,
    "lift_credit_minus_pre": -0.008928571428571425
  },
  "q_gap_leak_minus_ctrl": {
    "pre_mean": 0.0601928912349273,
    "credit_mean": 0.06986564851265029,
    "lift_credit_minus_pre": 0.009672757277722988
  },
  "sum_abs_logit_contrib_from_delta": {
    "pre_mean": 66.5555359806707,
    "credit_mean": 47.90060744588087,
    "lift_credit_minus_pre": -18.654928534789825
  },
  "net_logit_contrib_from_delta": {
    "pre_mean": 7.117319161674741,
    "credit_mean": 2.51667791784491,
    "lift_credit_minus_pre": -4.600641243829831
  },
  "pump_delta_over_ctrl": {
    "pre_mean": -0.1474723742586023,
    "credit_mean": 3.29229308500079
  }
}
```

## Per-pair credit-window snapshot

| pair | split | hit6 | phys | ignore | |Δ|chg pre→cred | q_gap pre→cred | exceed chg | pump Δ/|ctrl| |
|------|-------|------|------|--------|-----------------|----------------|------------|----------------|
| pair_000 | synthetic_dev | False | False | False | 0.10094433296767494→0.12081491038222951 | 0.17099503070713085→0.15424110507716116 | 0.14285714285714285 | -0.026158466571367826 |
| pair_001 | synthetic_test | True | True | False | 0.1931366828651426→0.6544639081048665 | 0.010255032632170369→0.22739729703988415 | 0.0 | -0.4983853844790269 |
| pair_002 | synthetic_test | True | True | False | 0.034693979000183214→0.11468947657714129 | -0.03505753601738332→0.03190441822166412 | 0.0 | 0.0 |
| pair_003 | synthetic_dev | False | True | True | 0.03859751679239765→0.5801022212370915 | -0.06358215060392147→-0.1422837856161533 | 0.0 | 0.3110095669132876 |
| pair_004 | synthetic_test | False | True | True | 0.010118733051789817→0.1673702738661733 | 0.11544327781403574→-0.10831307085807984 | 0.19047619047619047 | 25.076278828367002 |
| pair_005 | train | True | False | False | 0.23360406901372016→0.2495041352405987 | 0.020473744573716646→0.13840283612709214 | 0.0 | -0.3248104139224688 |
| pair_006 | train | False | True | False | 0.02617175747793187→0.18958695143382384 | 0.0686280512888659→0.24169846382775562 | 0.0 | 1.605119401704841 |
| pair_007 | synthetic_test | False | False | False | 0.20261414289701157→0.03698256094816817 | 0.02063171679892628→0.06297327224753657 | 0.0 | 0.0009540311050351993 |
| pair_008 | train | False | True | False | 0.31454511640800376→0.4612396502138051 | 0.0638625955230942→0.25689809600328933 | 0.0 | 0.0 |
| pair_009 | synthetic_test | False | True | True | 0.2838516809312361→0.8197034092649582 | -0.048223844736343→-0.052956033930686375 | 0.0 | 2.089407002607706 |
| pair_010 | train | True | False | False | 0.30230091821461447→0.3366988235798778 | -0.08286957845539078→-0.013460180463524374 | 0.0 | -0.350455353317301 |
| pair_011 | train | False | False | False | 0.13300167307573024→0.01975621434037017 | 0.11537942304106041→-0.034861659712926096 | 0.0 | 0.0 |
| pair_012 | synthetic_test | False | False | False | 0.5014332296001532→0.011930980527448273 | 0.07132822739123923→0.1030540772035361 | 0.07142857142857142 | 0.00148928079695369 |
| pair_013 | synthetic_test | False | False | False | 0.7917370254368001→0.16041771260335574 | 0.24575450305168595→0.19727585401071268 | 0.0 | -0.23597765495820103 |
| pair_014 | synthetic_dev | False | False | False | 0.5520775959482451→0.5934855288229686 | -0.203376145014737→0.0084362823442794 | 0.07142857142857142 | 0.0013617346425607677 |
| pair_015 | synthetic_test | True | True | True | 0.39542975350721643→0.1544244655412893 | 0.10141175294508714→0.09758937416663493 | 0.21428571428571427 | -0.0954214234331512 |

## Decision

**2. Existing features do not reliably distinguish leaks from operations**

Evidence:

- Train/DEV: mean fraction of change-features with |leak−ctrl| > 2× control temporal std in credit window = 0.0268.
- Train/DEV: lift in mean |Δ| change-features (credit−pre) = 0.1062.
- Train/DEV: lift in mean (q_leak−q_ctrl) (credit−pre) = 0.06495.
- Train/DEV: frac useful_physical=0.375; frac classifier_ignores=0.125 (n=8).
- Test diagnostic (not for decision): frac useful_physical=0.625; frac classifier_ignores=0.375; q_gap lift=0.009672757277722988.

### Recommended next intervention (not implemented)

Prioritize stronger leak-sensitive representations on phase-corrected matched pairs (global absolute/context features remain confounded with operations) — do not implement yet.

## Non-goals

- No refit, measured eval, 2019, UI, Tiger, deployment

