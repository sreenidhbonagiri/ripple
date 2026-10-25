# Multiscale Method M — combined sensor×timescale search (registered before execution)

**Isolated research experiment.** Does not modify deployed Method M, frozen
calibration, SCALE σ artifacts, or prior Method M / 2019 results.

**Acknowledgement:** 2018 events have already been examined during previous
research; DEV/DIAG findings here are diagnostic. **No 2019** inspection or tuning.

---

## Existing temporal score (baseline)

Frozen Method M (`METHOD_M_PROTOCOL.md`) uses one causal window pair:

| Role | Window |
|------|--------|
| Reference | **24 h** ending **1 h** before analysis hour \(t\) |
| Recent | the single hour \(t\) |

Then \(\delta_i(t)=q_{v,i}(t)-\mu_{\mathrm{ref},i}(t)\), training-only \(\sigma_i\),
\(s_M=\max_i|\delta_i/\sigma_i|/\mathrm{median}_{\mathrm{SCALE}}(\mathrm{raw\ max})\).

**That 24 h / 1 h gap / 1 h recent pair is the registered baseline timescale
(`medium`).** Exact reproduction of frozen Method M is the comparison baseline
(same measured-PUMP_1 dual, same calibration hash, same SCALE period).

---

## Scope (unchanged hydraulics)

- Dual: measured-PUMP_1 `dual_qv_hourly.csv` under frozen calibration
  `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`
- All eligible dual pressure-sensor columns; no leak-guided sensor selection
- Causal data only (refs end before \(t\); no future hours)
- Chronological boundaries (unchanged):

| Period | Start | End |
|--------|-------|-----|
| SCALE (σ only) | 2018-01-09 01:00 | 2018-01-21 23:00 |
| DEV | 2018-01-08 00:00 | 2018-06-30 23:55 |
| DIAG | 2018-07-01 00:00 | 2018-12-31 23:55 |

Warm-up: 25 h after period start for event eligibility (same as Method M).

---

## Registered timescale set (small, physically justified)

All scales share: **gap = 1 h**, **recent = single hour \(t\)**, hourly dual grid.
Only the reference length changes.

| ID | Ref hours | Justification |
|----|----------:|---------------|
| **short** | **12** | Half-day ordinary; abrupt onset vs recent local regime. Chosen as the shortest ref that still satisfies the existing ≥12 finite hourly ref-sample eligibility rule (a 6 h ref cannot). |
| **medium** | **24** | **Baseline = frozen Method M temporal definition** |
| **long** | 72 | Multi-day ordinary; slower residual bias (incipient-relevant) without a full-week absorption window |

Eligibility: same `REF_MIN_SAMPLES=12` as Method M for every timescale.  
No other windows. No post-hoc expansion after results.

Per timescale \(w\), training-only \(\sigma_{i,w}\) = std of causal \(\delta_{i,w}\) on
SCALE (≥24 finite samples or sensor dropped for that \(w\)). \(\varepsilon=10^{-3}\) m³/h floor.

---

## Combined ONE notification stream (not a union of independent alerts)

At each hour \(t\), form the **joint search** statistic over sensors and timescales:

\[
s_{\mathrm{raw}}(t)=\max_{i\in\mathcal{E}_w(t),\,w\in\{S,M,L\}}
\bigl|\delta_{i,w}(t)/\sigma_{i,w}\bigr|
\]

\[
s_{\mathrm{MS}}(t)=s_{\mathrm{raw}}(t)\,/\,\mathrm{median}_{\mathrm{SCALE}}(s_{\mathrm{raw}})
\]

- If no eligible \((i,w)\) at \(t\), \(s_{\mathrm{MS}}=\mathrm{NaN}\) (no notify; recovery reset).
- **Forbidden:** independently thresholding short/medium/long and unioning notifies
  without measuring burden — that is not this experiment.
- **Duplicate handling:** a single notifier on \(s_{\mathrm{MS}}\) (notify \(s\ge\tau\);
  recover \(s<\tau/2\) for **1 h**; NaN resets recovery). One episode stream → no
  duplicate same-hour alerts from multiple scales.

---

## Selection budget (fixed, small)

DEV post-warmup finite \(s_{\mathrm{MS}}\) quantiles **p75, p90, p95, p99** → four τ
candidates, registered **before** reading gate pass/fail. **No grid expansion**
after results. Select **largest** τ that passes DEV abrupt gates.

---

## Objectives and gates (registered separately)

### Abrupt (primary selection)

- Credit: **6 h** from catalog abrupt onset (same as Method M)
- DEV gates (all required for selection): recall ≥ 2/3, unmatched/week ≤ 3,
  occupancy ≤ 0.20
- Matching: one-to-one earliest unused notify in the credit window

### Incipient (report only; not used to pick τ)

- Credit: **6 h** from catalog **startTime** (BattLeDIM configuration)
- Eligible starts in DEV/DIAG after warm-up
- Reported separately (recall, delays); **does not** enter DEV τ selection gates

### Burden / occupancy / recovery

- Unmatched/week: notifies not matched to any eligible **abrupt** credit window
  in the period (incipient matches do not clear unmatched for selection burden —
  same abrupt-centric burden as Method M operating point)
- Occupancy: fraction of hours inside any active episode
- Recovery: τ/2 for 1 consecutive finite hour below clear threshold

---

## Comparison baseline

Exact reproduction of frozen Method M on the same dual file:

1. Recompute medium-only \(s_M\) with REF=24; verify agreement with archived
   `score_M.csv` / SCALE median / selected τ=`4.347`
2. Evaluate frozen τ on DEV (and DIAG only if multiscale DEV selection passes)
3. Report event-level **gains and regressions** vs that baseline, delays,
   unmatched/week, occupancy, and density-matched timing nulls (\(N=200\) on DIAG
   if run; \(N=50\) on DEV tradeoff tables)

---

## Stop rules

- If **no** τ passes DEV abrupt gates → selection **FAILS**; **no** fallback DIAG;
  write failure report and stop.
- If pass → **freeze** τ, then run diagnostic DIAG (abrupt + incipient report +
  timing nulls). No retune after freeze.
- **No 2019.** No production / Tiger / main / deploy / calibration changes.

---

## Registered before any multiscale DEV evaluation

This file must exist before `run_method_m_multiscale_dev.py` executes gate
comparisons.
