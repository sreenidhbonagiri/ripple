# Five-minute Method M — freeze note

**Frozen after DEV gates passed.** Diagnostic DIAG run at the frozen τ.

| Item | Value |
|------|-------|
| Branch | `research/method-m-5min` |
| Protocol | `METHOD_M_5MIN_PROTOCOL.md` |
| Frozen calibration sha256 | `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921` |
| Pump boundary | measured-PUMP_1 |
| Timestep | 300 s (native 5-minute) |
| REF_MIN_SAMPLES | 144 |
| MIN_SCALE_SAMPLES | 288 |
| RECOVER_STEPS | 12 (1 h elapsed) |
| Causal fill max age | 2 steps |
| SCALE | 2018-01-09 01:00 → 2018-01-21 23:00 |
| Registered DEV τ grid | p75/p90/p95/p99 = `1.175, 1.565, 2.117, 4.517` |
| **Frozen τ** | **`4.517`** (largest passing) |

DEV at τ=4.517: recall=1.0 (3/3), unmatched/wk=0.201, occupancy=0.031.  
DIAG at τ=4.517: recall=1/3 (p158 only), unmatched/wk=0.038, occupancy=0.008.

Hourly baseline was reproduced from existing `score_M.csv` at τ=4.347 (hydraulics not re-run).

No 2019 / production / Tiger / deploy / main merge.
