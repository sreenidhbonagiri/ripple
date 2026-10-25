# Reference-induced signal suppression diagnosis — p369

Generated: 2026-10-24T22:07:19-04:00

Diagnostic only. Preserves detector outputs, frozen τ/LQ/LR, matching audits, and production. **Not** a threshold search or deployable feature.

Frozen signal: LQ=2h, LR=48h, τ=26.7329 (context only).

## Windows (identical for all cases)

- **PRE:** median over `[t0 − 2 h, t0)`
- **POST:** median over `[t0, t0 + 2 h]`
- Δ = POST − PRE. Signed residual e = hatP − P (under-pressure → e>0 when P falls vs prediction).
- Evidence ranked by **measured** ΔP (most negative first), never by true pipe proximity.

## 1. Decomposition — p369

- t0: 2018-10-26 02:05
- Network median ΔP: **0.16 m**
- Frac targets with ΔP < −0.05 m: 0.0
- Frac target/ref pairs same direction: 0.9191919191919192
- Median (Δe_held − Δe_normal): **-0.16943950367079808** (>0 ⇒ holding refs amplifies residual change)
- Max FMR3C score in POST: 6.547648958864513 (τ=26.73)

### Top targets by measured pressure drop

- **n410** ΔP=-0.03 m; med Δe=0.1958; med Δe_held=0.03; amp=-0.1657769717693842; score_max=5.1289168974507096; refs=[n429:ΔP=0.03,Δe=0.0611, n415:ΔP=0.14,Δe=0.196, n342:ΔP=0.16,Δe=0.212]
- **n215** ΔP=0 m; med Δe=0.003376; med Δe_held=0; amp=-0.0033764413660263798; score_max=1.0239313281035185; refs=[n469:ΔP=0.155,Δe=0.00338, n752:ΔP=0.195,Δe=0.00339, n740:ΔP=0.065,Δe=0.0029]
- **n54** ΔP=0.02 m; med Δe=0.01135; med Δe_held=-0.02; amp=-0.03134558709336066; score_max=0.8458365009415536; refs=[n429:ΔP=0.03,Δe=0.0113, n410:ΔP=-0.03,Δe=-0.0502, n679:ΔP=0.18,Δe=0.242]
- **n429** ΔP=0.03 m; med Δe=-0.011; med Δe_held=-0.03; amp=-0.01899715468355409; score_max=1.3119824495848906; refs=[n410:ΔP=-0.03,Δe=-0.0589, n54:ΔP=0.02,Δe=-0.011, n415:ΔP=0.14,Δe=0.13]
- **n740** ΔP=0.065 m; med Δe=0.004202; med Δe_held=-0.065; amp=-0.06920441663626851; score_max=-1.247164898156195; refs=[n722:ΔP=0.14,Δe=0.0042, n769:ΔP=0.145,Δe=0.0108, n296:ΔP=0.12,Δe=0.00351]
- **n495** ΔP=0.105 m; med Δe=-0.003092; med Δe_held=-0.105; amp=-0.10191110989880177; score_max=-1.6816169822123568; refs=[n332:ΔP=0.17,Δe=-0.00309, n549:ΔP=0.19,Δe=-0.00451, n506:ΔP=0.16,Δe=0.0016]
- **n296** ΔP=0.12 m; med Δe=0.008574; med Δe_held=-0.12; amp=-0.128576304206265; score_max=3.198204382763785; refs=[n722:ΔP=0.14,Δe=0.00115, n726:ΔP=0.19,Δe=0.0129, n288:ΔP=0.2,Δe=0.00857]
- **n722** ΔP=0.14 m; med Δe=0.01323; med Δe_held=-0.14; amp=-0.15322738725595664; score_max=0.19632133596441584; refs=[n726:ΔP=0.19,Δe=0.0135, n296:ΔP=0.12,Δe=-0.00142, n769:ΔP=0.145,Δe=0.0132]

Context Δ: {'delta_PUMP_1': -0.0800018310546875, 'delta_p227': -12.734992980957031, 'delta_p235': -13.604995727539062, 'delta_T1': 0.315000057220459, 'note': 'Δ = post-median − pre-median on identical windows. PUMP_1 = internal transfer; p227/p235 = recorded flow sensors; T1 = tank.'}

## 2. Comparison cases

### p158 (abrupt comparison)

- t0: 2018-10-06 02:35
- median ΔP=0.185; same-dir frac=0.9696969696969697; amp(held−normal)=-0.18789740359883705; score_max=72.9856353991769
- Context: {'delta_PUMP_1': -0.020000457763671875, 'delta_p227': -5.4550018310546875, 'delta_p235': -16.125, 'delta_T1': 0.3250000476837158, 'note': 'Δ = post-median − pre-median on identical windows. PUMP_1 = internal transfer; p227/p235 = recorded flow sensors; T1 = tank.'}

### p183 (abrupt comparison)

- t0: 2018-08-07 02:35
- median ΔP=0.12; same-dir frac=0.8080808080808081; amp(held−normal)=-0.13081556486180243; score_max=32.324039316974506
- Context: {'delta_PUMP_1': 0.049999237060546875, 'delta_p227': -2.3850021362304688, 'delta_p235': -14.174995422363281, 'delta_T1': -0.014999866485595703, 'note': 'Δ = post-median − pre-median on identical windows. PUMP_1 = internal transfer; p227/p235 = recorded flow sensors; T1 = tank.'}

### Ordinary operating controls (same month as p369)

In calendar month 2018-10, step every 2 h; reject if within ±7 d of any labeled onset; keep top 8 by |network median ΔP| (measurement-selected).

| t0 | median ΔP | same-dir | amp(held−normal) | score_max | ΔPUMP_1 | ΔT1 |
|----|-----------|----------|------------------|-----------|---------|-----|
| 2018-10-18 06:00 | -0.76 | 1.0 | 0.7346638917981088 | 12.687120666688061 | 0 | -0.23 |
| 2018-10-15 06:00 | -0.7 | 1.0 | 0.6716259857808758 | 9.066015008116302 | 0 | -0.275 |
| 2018-10-17 06:00 | -0.635 | 1.0 | 0.6336108798890926 | 10.489464191199659 | 0 | -0.215 |
| 2018-10-16 00:00 | 0.56 | 0.9696969696969697 | -0.5552549083073418 | 8.295004158677575 | 0.11 | 0.235 |
| 2018-10-15 08:00 | -0.52 | 1.0 | 0.5141201209875217 | 7.745257420252982 | 0 | -0.42 |
| 2018-10-14 06:00 | -0.535 | 1.0 | 0.5322340414660824 | 8.82435568484044 | 0 | -0.28 |
| 2018-10-17 08:00 | -0.54 | 1.0 | 0.5265054895647345 | 6.660975067138398 | 0 | -0.375 |
| 2018-10-16 08:00 | -0.5 | 1.0 | 0.4867857929204454 | 5.756288052894 | 0 | -0.35 |

## 3. Controlled diagnostic intervention

Using **frozen** DIAG OLS coefficients, compare normal Δe to Δe with each reference pressure **held at its PRE median** (ΔhatP=0 ⇒ Δe_held=−ΔP_target). Artificial diagnostic only — not causal proof, not a detector, not a performance claim. Applied equally to events and ordinary controls.

p369 amp(held−normal)=-0.1694; p158=-0.1879; p183=-0.1308; ordinary median/p90=0.5293697655154085/0.6905373575860457. If ordinary controls amplify as much as p369 when refs are held, the intervention is not leak-specific.

## 4. Decision

**No complementary common-mode feature proposed.** p369 does **not** contain distinctive coherent pressure *drop* that relationships suppress: network median ΔP = 0.16 m (rise, not drop); 0% of targets have ΔP < −0.05 m; strongest measured drop is only -0.03 m at n410. Same-direction motion (frac=0.919) is mostly co-movement upward. Ref-hold amp(held−normal) = -0.1694 (negative ⇒ holding refs does **not** amplify a leak-like residual; ordinary large-drop controls amp median 0.5294). By contrast p158 HIT has localized drop -0.165 m at n644 with score_max=72.99. Raw/context patterns for p369 overlap mild ordinary variability; inflow/tank Δ (PUMP_1=-0.08, T1=0.315) are not a distinctive leak signature. **Do not** claim removing references would recover p369. Retain it as a genuine unresolved signal failure under relationship residuals.

## Non-goals honored

- No event-specific reference re-picking, threshold change, 2019, UI, Tiger, deploy
- No production feature implementation

