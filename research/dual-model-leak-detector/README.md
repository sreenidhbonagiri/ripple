# Dual-model leak detector (physics / Under Pressure)

Isolated research package reconstructing the **pressure–leak dual model**
(Steffelbauer et al., *JWRPM* 2022; BattLeDIM “Under Pressure” report).

**Not** wired into production, Tiger, or UI. **Not** a residual-CUSUM detector.

| Stage | Status |
|-------|--------|
| 1 Dual hydraulic solver | **Implemented** |
| 2 Synthetic mechanism verification | **Implemented** |
| 3 Measured 2018 calibration | **Corrected freeze** (`PASS_WITH_LIMITATIONS`) |
| 4 Detection feasibility 2018 | **Ran** — DEV selection **failed** all methods; DIAG diagnostic only |

## Quick start

```bash
cd research/dual-model-leak-detector
../../.venv/bin/python -m pytest tests/ -q
../../.venv/bin/python scripts/run_synthetic_verification.py
../../.venv/bin/python scripts/run_nominal_ltown_audit.py
../../.venv/bin/python scripts/run_stage3_calibration.py
```

Requires `data/raw/2018_SCADA_{Pressures,Flows,Levels,Demands}.csv` (Demands from Zenodo 4017659 if missing).

## Docs

| File | Role |
|------|------|
| `ATTRIBUTION.md` | Method citations + licenses |
| `DEPARTURES.md` | Explicit departures from papers |
| `CALIBRATION_WINDOWS.md` | Fit/validation windows (declared before fitting) |
| `outputs/synthetic/SYNTHETIC_VERIFICATION_RESULTS.md` | Stage 2 results |
| `outputs/calibration/STAGE3_VERDICT.md` | Stage 3 verdict |
| `DETECTION_PROTOCOL.md` | 2018 detection protocol (pre-registered) |
| `outputs/detection_2018/DETECTION_RESULTS.md` | DEV/DIAG detection results |

## Layout

```
dual_model/           # solver + synthetic scenarios
tests/                # unit + mechanism tests
scripts/              # verification runner
outputs/synthetic/    # JSON + markdown results
```

## Next (not authorized until review)

Measured-data calibration on **2018 only**, chronological fit/validation, AMR Area C
constraints, tank storage, no event-specific leak fitting — then paper detection
procedure with pre-declared engineering choices and continuous notification metrics.