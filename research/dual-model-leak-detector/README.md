# Dual-model leak detector (physics / Under Pressure)

Isolated research package reconstructing the **pressure–leak dual model**
(Steffelbauer et al., *JWRPM* 2022; BattLeDIM “Under Pressure” report).

**Not** wired into production, Tiger, or UI. **Not** a residual-CUSUM detector.

| Stage | Status |
|-------|--------|
| 1 Dual hydraulic solver | **Implemented** |
| 2 Synthetic mechanism verification | **Implemented — stop here for review** |
| 3 Measured 2018 calibration | Not started |
| 4 Detection + continuous metrics | Not started |

## Quick start

```bash
cd research/dual-model-leak-detector
# from repo root venv with wntr:
../../.venv/bin/python -m pytest tests/ -q
../../.venv/bin/python scripts/run_synthetic_verification.py
```

## Docs

| File | Role |
|------|------|
| `ATTRIBUTION.md` | Method citations + licenses |
| `DEPARTURES.md` | Explicit departures from papers |
| `outputs/synthetic/SYNTHETIC_VERIFICATION_RESULTS.md` | Scenario results after running the script |

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