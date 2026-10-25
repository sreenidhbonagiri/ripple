# Method M — network max \|standardized local q_v change\|

**Registered before evaluation.**  
**Comparison to Method B first (do not treat as a rename):**

| | Method B (existing) | Method M (this protocol) |
|--|---------------------|---------------------------|
| Per-sensor residual | \(q_{v,i}(t)-\mu_{\mathrm{ref},i}(t)\) | same causal residual \(\delta_i(t)\) |
| Scale | **One** rolling scale \(\bar\sigma_{\mathrm{ref}}(t)=\mathrm{mean}_i\sigma_{\mathrm{ref},i}(t)\) | **Fixed training** per-sensor \(\sigma_i\) from SCALE period only |
| Aggregation | \(\|\boldsymbol{\delta}(t)\|_2/\bar\sigma_{\mathrm{ref}}(t)\) | \(\max_i\|\delta_i(t)/\sigma_i\|\) after empirical max-calibration |
| Cancellation | L2 avoids sign cancel in the sum, but pools energy across sensors | Preserves the **largest local** standardized change |

Method B is **not** equivalent to M. Proceed with M as a separate score.

---

## Scope

- Dual: measured-PUMP_1 (`dual_qv_hourly` under frozen calibration).  
- Frozen calibration sha256: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
- **All** dual pressure-sensor columns (eligible = finite residual + finite \(\sigma_i\)); **no** sensor selection from leak examples / p866 / DIAG.  
- Acknowledge: 2018 findings are diagnostic.

---

## Fixed window pair (causal)

Identical to A/B reference construction:

| Role | Window |
|------|--------|
| **Reference** | 24 h ending **1 h before** \(t\) |
| **Recent** | the single hour \(t\) (hourly dual sample) |

\(\delta_i(t)=q_{v,i}(t)-\mu_{\mathrm{ref},i}(t)\).  
Require ≥12 finite ref samples for sensor \(i\); else \(i\) ineligible at \(t\).

---

## Training-only ordinary scales

| Item | Choice |
|------|--------|
| **SCALE period** | 2018-01-09 01:00 → 2018-01-21 23:00 (post warm-up; **before** first DEV abrupt onset; chronological) |
| \(\sigma_i\) | sample std (ddof=0) of \(\delta_i(t)\) over SCALE hours where \(i\) is eligible |
| Near-zero | \(\sigma_i\leftarrow\max(\sigma_i,\varepsilon)\), \(\varepsilon=10^{-3}\) m³/h |
| Missing scale | if fewer than 24 finite \(\delta_i\) in SCALE → sensor **dropped for all \(t\)** (ineligible) |

Scales are frozen after SCALE; never updated on DIAG or from event labels.

---

## Standardized local change and network maximum

\[
z_i(t)=\delta_i(t)/\sigma_i,\qquad
s_{\mathrm{raw}}(t)=\max_{i\in\mathcal{E}(t)}|z_i(t)|
\]

- \(\mathcal{E}(t)\): eligible sensors at \(t\). If \(\mathcal{E}(t)=\emptyset\), \(s=\mathrm{NaN}\) (no notify).  
- **Not probabilities.** Hourly \(z_i\) are strongly autocorrelated; max-over-sensors is a **search** statistic. Do not treat \(s\) as a p-value or assume independence across hours or sensors.

### Empirical calibration of the network maximum (DEV/SCALE ordinary)

To account for searching across \(n\) sensors, divide by the SCALE-period median of the raw maximum:

\[
s_M(t)=s_{\mathrm{raw}}(t)\,/\,\mathrm{median}_{\mathrm{SCALE}}(s_{\mathrm{raw}})
\]

If SCALE median \(< 10^{-6}\), leave \(s_M=s_{\mathrm{raw}}\) and flag.  
Under ordinary conditions \(s_M\) is order-1; thresholds are still chosen empirically (below), not from Gaussian tail formulas.

---

## Threshold budget, notify/recover, gates

Reuse measured-PUMP_1 operating-point rules (`OPERATING_POINT_PROTOCOL.md`):

- Notify \(s\ge\tau\); recover \(s<\tau/2\) for 1 h; NaN resets recovery.  
- DEV gates (all required): recall ≥ 2/3, unmatched/week ≤ 3, **occupancy ≤ 0.20**.  
- τ grid: DEV post-warmup **p75, p90, p95, p99** of finite \(s_M\), registered once **before** reading gate pass/fail (same bounded 4-point budget as A/B/C operating-point). **No grid expansion after results.**  
- Select largest passing τ on **DEV only**. No p866-specific or DIAG-based selection.

**Stop rule:** if no τ passes DEV → selection **FAILS**; **no** fallback DIAG.  
If pass → freeze τ and run diagnostic DIAG with timing nulls (\(N=200\)).

---

## Reporting

DEV tradeoff; event hits/delays/pre-onset blocking; unmatched/week; occupancy; DIAG only if selected.  
No 2019 / production / UI / Tiger / deploy / recalibration / recovery changes.
