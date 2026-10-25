# Method M — native five-minute resolution (isolated variant)

**Registered before evaluation.**  
Companion audit: [`HOURLY_PIPELINE_AUDIT.md`](HOURLY_PIPELINE_AUDIT.md).

Does **not** assume higher resolution improves sensitivity.  
No 2019 / calibration refit / production / Tiger / deploy.  
DIAG only if DEV passes declared gates.

---

## Relation to frozen hourly Method M

| Item | Hourly Method M (frozen) | This variant |
|------|--------------------------|--------------|
| Dual grid | On-the-hour subsample (`minute==0`) | Native SCADA **5-minute** stamps |
| EPANET `timestep_sec` | 3600 | **300** |
| Score / notify | Hourly | Every 5-minute sample |
| Frozen calibration | `5fab3acb…0c921` | **Same** (no refit) |
| Pump boundary | measured-PUMP_1 | **Same** |
| Score definition | \(s_M=\max_i\|\delta_i/\sigma_i\|/\mathrm{median}_{\mathrm{SCALE}}\) | **Same formula** |
| Physical windows | 24 h ref, 1 h gap, 6 h credit, 1 h recover | **Same durations** (sample counts scaled) |

Hourly τ (`4.347`) is **not** reused. Re-select τ on 5-minute DEV scores under the same bounded quantile budget.

---

## Why sample counts change

Reference construction uses **Timedelta hours** (already time-based). Eligibility
and recovery that were expressed as **sample counts** on the hourly grid must
scale so physical durations stay fixed:

| Constant | Physical meaning | Hourly | 5-minute |
|----------|------------------|--------|----------|
| Ref window | 24 h ending 1 h before \(t\) | Timedelta | Timedelta (unchanged) |
| Gap | 1 h | Timedelta | Timedelta (unchanged) |
| `REF_MIN_SAMPLES` | ≥12 h of finite ref stamps | 12 | **144** (= 12 × 12) |
| SCALE min σ samples | ≥24 h eligible δ | 24 | **288** (= 24 × 12) |
| Recover | \(s<\tau/2\) for **1 h** | `RECOVER_STEPS=1` | **`RECOVER_STEPS=12`** |
| Credit | 6 h after onset | Timedelta | Timedelta (unchanged) |
| Warmup | 25 h | Timedelta | Timedelta (unchanged) |

Occupancy remains **fraction of scoring steps** inside an active episode (grid-
invariant definition). Unmatched/week is calendar-time normalized (unchanged
gate ≤ 3). More scoring opportunities can raise unmatched/week or occupancy
even if per-event sensitivity is unchanged — τ selection must absorb that.

---

## Dual construction (causal)

1. Load full 5-minute pressures, flows, levels, AMR (no `subsample_hourly`).
2. Per chunk: intersect indices across P/F/L/AMR (timestamp alignment).
3. `run_dual_window(..., timestep_sec=300, pump_boundary=measured_pump1)`.
4. Tank `init_level` from first measured T1 in the chunk.
5. Pressure gaps: **causal `ffill(limit=2)` only** — no linear `interpolate`
   (avoids using future observations across gaps). Pump series remains causal
   ffill via `prepare_pump_series_causal`.
6. Storage-rate diagnostics use `storage_rate_m3h` (actual elapsed Δt).

Verify before scoring: median index step = 5 min; dual `q_v` index equals the
aligned measurement index; solver convergence notes recorded per chunk.

---

## SCALE / sensors / τ budget

- **SCALE:** 2018-01-09 01:00 → 2018-01-21 23:00 (same calendar bounds; all
  5-minute stamps in range). σ_i and median raw-max estimated on this period
  only — **not** transferred from hourly Method M σ.
- All dual pressure-sensor columns; no event-/DIAG-based sensor selection.
- **τ grid:** DEV post-warmup finite \(s_M\) quantiles **p75, p90, p95, p99**
  (four points, registered once before gate outcomes). No expansion after
  results. Select **largest** τ passing all DEV gates.

---

## DEV gates (all required)

Same as hourly Method M operating point:

1. Abrupt 6 h recall ≥ 2/3  
2. Unmatched / week ≤ 3  
3. Occupancy ≤ 0.20  

**Stop:** if no τ passes → selection FAILS; **no** DIAG.  
If pass → freeze τ for this variant; DIAG deferred until explicitly requested
after freeze note (this investigation stops at DEV compare unless gates pass
and freeze is recorded).

---

## Baseline and comparison

1. **Reproduce** hourly Method M DEV metrics at frozen τ=`4.347` from existing
   hourly `score_M` / dual (sanity check).
2. Run 5-minute Method M on 2018 DEV under this protocol.
3. Compare: recall, delays, unmatched/week, occupancy, event-level hits /
   pre-onset blocking. Report regressions vs hourly without claiming
   resolution-driven improvement.

Scope cutoff: **2018 DEV only** for this investigation unless DEV passes and
a freeze note authorizes DIAG.
