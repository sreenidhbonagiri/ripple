# Stage 3 calibration / generalization verdict (corrected)

**Verdict: `PASS_WITH_LIMITATIONS`**

Corrected signed-mean Area-C scale (bounds unchanged). Calibration improves FIT_W1 and multi-season validation pressure RMSE vs nominal; roughness mostly interior. Limitations: demand TSA is reconstructed; validation weeks contain ongoing leaks so q_v is not pure model error. Not detection-ready.

Generated: `2026-10-25T04:40:11.587503+00:00`  
TCV K frozen: `0.001` (nominal audit; not leak-tuned)  
Estimator: `signed_mean_residual_no_preclip_v2`  
frozen_calibration sha256: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
stage3_results sha256: `10d7d6566ca4d0bd1e02f4282fea10e29cb08d0fa76c8a2b2c7cfef5ada2d724`

Previous bugfix freeze retained under `superseded_by_bugfix/`.
No tuning from validation or leak-onset outcomes.

## Area-C scale (corrected vs previous)

| | Previous (bugfix) | Corrected |
|--|-------------------:|----------:|
| raw scale | 2.8049136614848265 | 0.9208320927182462 |
| clipped scale | 1.5 | 0.9208320927182462 |
| bound hit | upper | interior |
| physically_inconsistent | n/a (masked by clip) | `False` |

Signed mean residual: `1.695288715978` m³/h; frac negative samples: `0.3196029776674938`.

## Fit window (FIT_W1)

| Model | Pressure RMSE (m) | Ext. inflow bias (m³/h) | Tank RMSE (m) | Σq_v mean | mean|q_v| | cancel |
|-------|------------------:|------------------------:|--------------:|----------:|----------:|-------:|
| nominal | 0.6415122535965869 | 7.184552282605848 | 0.7679694608371858 | 2.679309037991375 | 2.7073564315662857 | 0.8889741632133891 |
| calibrated | 0.31552095395639684 | 23.599022887093682 | 0.36637380350338644 | -12.374004172667227 | 1.3841877083048757 | 0.542666893618945 |

### Calibrated FIT vs superseded bugfix

| Metric | Previous | Corrected |
|--------|---------:|----------:|
| P RMSE (m) | 0.2954917481904553 | 0.31552095395639684 |
| Ext bias (m³/h) | 24.38221683865502 | 23.599022887093682 |
| Tank RMSE (m) | 0.2747287376007576 | 0.36637380350338644 |
| Σq_v mean | -13.347212310884364 | -12.374004172667227 |
| mean|q_v| | 1.3806250953128114 | 1.3841877083048757 |
| cancel ratio | 0.5478232035777366 | 0.542666893618945 |

## Validation windows (frozen parameters)

| Window | Model | P RMSE (m) | Ext bias (m³/h) | Σq_v mean | mean|q_v| | cancel |
|--------|-------|----------:|----------------:|----------:|----------:|--------:|
| VAL_APR | nominal | 0.6651497442904457 | -22.132247524261473 | 33.39465094684105 | 2.9309313070443523 | 0.8301081108745713 |
| VAL_APR | calibrated | 0.3591409518068486 | 16.056786370050336 | -4.32809098578671 | 1.584559978187092 | 0.46136916144344947 |
| VAL_JUL | nominal | 0.8099196897165492 | -47.44804470970517 | 59.54176841510546 | 3.239280210168198 | 0.8746615869478296 |
| VAL_JUL | calibrated | 0.38328010014267483 | 10.920371349879671 | 2.5041169816058484 | 1.5714912194150812 | 0.5016967217881586 |
| VAL_OCT | nominal | 0.8031274501860084 | -52.756271657489584 | 65.49265543390804 | 3.3267837442267028 | 0.8352065885483967 |
| VAL_OCT | calibrated | 0.447737874910079 | -10.610766229175384 | 23.114033217669114 | 1.8096854812043632 | 0.5975583125241922 |
| VAL_DEC | nominal | 0.7347180554600105 | -35.79444990521385 | 47.909909587810816 | 3.088168278411237 | 0.82977072664071 |
| VAL_DEC | calibrated | 0.40293360822368063 | -2.034165004548572 | 14.396901433970578 | 1.6624206527066583 | 0.4909268486007066 |

VAL mean P RMSE calibrated: previous 0.37302139231900233 → corrected 0.39827313377082074.

## Roughness / parameter stability

- Success: `True`; nfev=10; fit RMSE≈0.3616 m
- Bound hits: `{'C_area_c': 'interior', 'B_area_b': 'interior', 'A_d100_c120': 'interior', 'A_d100_c140': 'interior', 'A_d150_200': 'interior', 'A_plastic_small': 'interior'}`
- Values: `{'C_area_c': 140.00000322473116, 'B_area_b': 120.00063764441457, 'A_d100_c120': 120.00064841594929, 'A_d100_c140': 140.00000223908245, 'A_d150_200': 139.99991743282894, 'A_plastic_small': 139.99997974498177}`
- Previous values: `{'C_area_c': 139.95679528760084, 'B_area_b': 120.1187428024681, 'A_d100_c120': 119.97727189630338, 'A_d100_c140': 140.07207825756058, 'A_d150_200': 139.9996634953247, 'A_plastic_small': 139.94741847864378}`
- ab_scale=1.0244

## Leak-onset diagnostics (recorded only; not used for tuning)

| Leak | Onset | ΔΣq_v (m³/h) | Dominant sensor Δ | Status |
|------|-------|-------------:|------------------:|--------|
| p673 | 2018-03-05 15:45:00 | 30.982424622189342 | 20.003472920416243 | ok |
| p538 | 2018-05-18 08:35:00 | 48.37145716724933 | 11.474741020083457 | ok |
| p866 | 2018-06-01 09:05:00 | 15.921740781296023 | 13.307692605872035 | ok |
| p183 | 2018-08-07 02:35:00 | 30.516669316975253 | 9.740976972170756 | ok |
| p158 | 2018-10-06 02:35:00 | 35.502814910439895 | 17.390586809233355 | ok |

Stop before detection. No 2019 / UI / Tiger / deploy / main merge.

