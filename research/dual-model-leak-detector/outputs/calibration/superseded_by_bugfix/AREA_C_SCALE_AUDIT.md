# Audit: `area_c_unmeasured_scale` (stop before detection / reruns)

**Date:** 2026-10-25  
**Scope:** Verify AMR mapping, units, demand allocation, double-counting, and
why the unconstrained estimate was reported as ~2.8.  
**Frozen calibration is not modified in this step.**

## What the scale is supposed to mean

For the 10 Area-C junctions **without** AMRs, the demand model sets

\[
d_i(t) = d^{\mathrm{INP}}_{i,\mathrm{base}} \cdot s_{\mathrm{C}} \cdot T(t) \cdot S_i(t)
\]

where \(s_{\mathrm{C}}\) = `area_c_unmeasured_scale`. It is the single multiplier
that maps INP base demands of unmeasured Area-C nodes onto the portion of
Area-C supply not already explained by the 82 AMR time series.

Area-C supply (paper “virtual inflow”) on FIT_W1:

\[
Q_C(t) = Q_{\mathrm{PUMP\_1}}(t) - A_{\mathrm{tank}}\frac{\mathrm{d}h}{\mathrm{d}t}
\]

Unmeasured residual:

\[
r(t) = Q_C(t) - \sum_{\mathrm{AMR}} q_{\mathrm{AMR}}(t)
\]

Estimator (intended):

\[
s_C^{\mathrm{raw}} = \frac{\overline{r}}{\sum_{i\notin\mathrm{AMR}} d^{\mathrm{INP}}_{i,\mathrm{base}}}
\]

then clip to the declared physical band \([0.5, 1.5]\).

## Checks that pass

| Check | Result |
|-------|--------|
| AMR config ↔ CSV columns | 82/82 match; no extras |
| AMR ⊂ Area C (tank-side of `PUMP_1`) | 82/82; 0 outside |
| Unmeasured Area C | 10 nodes: `n5,n12,n14,n15,n37,n38,n348,n359,n363,n380` |
| AMR units | SCADA L/h → m³/h via `/1000` (equiv. `/3.6e6` then ×3600) |
| Application double-count | AMR nodes get **only** measured series; INP bases cleared. Unmeasured get scaled INP only. No node gets AMR+INP together. |
| Pump role | `PUMP_1` internal n54→T1; not treated as external inflow |
| External inflow | `p227+p235` only (used in `ab_scale`, not in \(s_C\)) |

FIT_W1 mass-balance means (unbiased):

| Quantity | Mean (m³/h) |
|----------|------------:|
| `PUMP_1` | 15.66 |
| \(A\,dh/dt\) | −1.23 |
| \(Q_C\) | 16.89 |
| Σ AMR | 15.18 |
| \(\overline{r}\) (no clip) | **1.71** |
| Σ INP base (unmeasured) | 1.84 |
| Σ INP base (AMR nodes) | 17.74 |
| Measured AMR / AMR-node bases | 0.86 |

So unmeasured demand is a **small** fraction of Area C (~9% of INP Area-C base;
\(\overline{r}/Q_C \approx 10\%\)). Measured AMRs already track ~90% of \(Q_C\).

## Implementation error (why “2.8” appeared)

In `fit_demand_model`:

```python
residual_c = (q_area_c - amr_m3h).clip(lower=0.0)
raw_scale = mean(residual_c) / base_unmeas
```

**`.clip(lower=0.0)` before averaging is wrong for this estimator.**

- On FIT_W1, \(r(t)<0\) on **~32%** of 5-min steps (tank-level noise / pump cycling
  makes \(Q_C\) briefly below ΣAMR; \(|A\,dh/dt|\) mean ≈ 24 m³/h vs signal ~2 m³/h).
- Zeroing negatives **inflates** \(\overline{r}\): 1.71 → **5.16** m³/h.
- That produces `area_c_unmeasured_scale_raw = 5.16 / 1.84 ≈ 2.80`, which then
  hits the upper clip at **1.5**.

Unbiased (no clip):

\[
s_C^{\mathrm{raw,correct}} \approx 1.71 / 1.84 \approx 0.93
\]

which lies **inside** \([0.5, 1.5]\) and would **not** hit the bound.

Smoothed tank level (1 h rolling) still gives \(\overline{r}\approx 1.73\) →
scale ≈ 0.94 — same conclusion. The 2.8 figure is an artifact of positive-only
averaging, not evidence that unmeasured bases need a 2.8× physical uplift.

Meta field `mean_residual_c_m3h` in `frozen_calibration.json` also stored the
**clipped** mean (5.16), which is misleading.

## What this is not

- Not permission to raise the \([0.5, 1.5]\) band.
- Not a finding that Area C is 2.8× under-metered in the INP.
- Not double-counting of AMRs in the applied network (allocation path is fine).
- Not a unit error on AMR L/h.

## Related note (not a stop-ship for \(s_C\), but recorded)

`ab_scale` compares whole-network \((q_{227}+q_{235} - A dh/dt)\) to
**total** INP base (including Area C), then applies the scale only to A/B.
That is a coarse inconsistency in the A/B scale construction; it does not create
the 2.8 artifact for \(s_C\).

## Decision

**STOP.** Do not run the detection feasibility experiment, do not relax bounds,
and do not recalibrate around leaks until this estimator is fixed and Stage 3
is re-frozen under the same window rules (separate authorization / follow-up).

Detection protocol registration and 2018 DEV threshold work are **blocked** on
this audit.
