# Finite-memory relationship-change (FMR3C)

Registered experiment from `DESIGN.md` (amended clarifications on AR(1) /
median-difference scale / heuristic τ). Reuses `build_signals.z` from
`research/per-sensor-relationship-cusum` without modifying that package’s
frozen results.

## Run

```bash
.venv/bin/python -m pytest research/finite-memory-relationship-change/tests -q
.venv/bin/python research/finite-memory-relationship-change/run_experiment.py
```

Outputs: `outputs/RESULTS.md`, `outputs/summary.json`, `outputs/frozen_settings.json`,
`outputs/synthetic_calibration.json`.

## Boundary

No production/UI/Tiger/main changes. No 2019. No CUSUM retuning.
