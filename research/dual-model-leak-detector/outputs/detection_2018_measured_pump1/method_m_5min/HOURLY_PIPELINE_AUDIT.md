# How the existing hourly Method M pipeline uses SCADA

**Audit only — precedes five-minute Method M registration.**  
Does not change calibration, deployed Method M, or thresholds.

## SCADA native grid

BattLeDIM pressure, flow, tank level, and AMR demands are recorded on a
**5-minute** naive clock (`…:00, :05, …, :55`).

## What “hourly” does

`ltown_hydraulics.subsample_hourly` keeps rows with `index.minute == 0` only:

```python
def subsample_hourly(df):
    return df[df.index.minute == 0]
```

This is **subsampling / selection of on-the-hour samples**, not a mean/median
aggregate over the preceding hour. Eleven of twelve native samples per hour are
discarded before dual inference.

`dual_series.build_dual_qv_hourly` then:

1. Loads full 5-minute SCADA.
2. For each chunk, applies `subsample_hourly` to pressures, flows, levels, AMR.
3. Intersects those hourly indices.
4. Runs dual EPS with `timestep_sec=3600` on that hourly stamp list.
5. Sets tank `init_level` from the **first hourly** measured T1 in the chunk.
6. For `measured_pump1`, imposes PUMP_1 from the **hourly** pump series (causal
   ffill inside `prepare_pump_series_causal` for gaps on that series).

Detection / Method M scores and the notifier then run on the hourly `q_v` index
(`REF_HOURS=24`, `REF_GAP_HOURS=1`, `RECOVER_STEPS=1` ≈ 1 h).

Burden helpers (`storage_rate_m3h`) already scale by **actual elapsed time**
between index stamps (hourly vs 5-minute safe).

## Misalignment / information-loss risks

| Risk | Mechanism |
|------|-----------|
| Brief hydraulic / SCADA changes | Events or spikes only visible at :05–:55 never enter dual or Method M. |
| Onset timing | Abrupt catalog times (e.g. `08:35`) credit against scores stamped only at `:00`, so first eligible score hour can lag by up to ~55 min beyond the true SCADA change. |
| Pump / inflow transitions | Mid-hour PUMP_1 or reservoir flow changes are invisible; hourly sample may sit before or after a switch. |
| Tank trajectory | Only `:00` levels; within-hour filling/emptying is lost; storage-rate diagnostics on hourly use 1 h Δh. |
| Dual state vs reality | EPANET steps 3600 s using sparse boundary heads/demands; intra-hour pressure paths used in the field are not constrained. |
| Gap fill in dual heads | `run_dual_window` uses `DataFrame.interpolate(limit=2)` on pressures after reindex — linear fill can use neighboring stamps (see five-minute protocol: replace with **causal ffill** for native 5-minute runs). |

## Implication for a five-minute Method M variant

Native 5-minute dual + Method M keeps physical window **durations** (24 h ref,
1 h gap, 1 h recovery, 6 h credit) but converts them to the 5-minute sample
grid. It does **not** assume higher resolution improves sensitivity; DEV must
re-select τ under a registered budget that accounts for more scoring times.

No 2019 / production / Tiger / deploy in this audit.
