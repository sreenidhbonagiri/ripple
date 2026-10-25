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

Empirical DEV percentile threshold calibration (frozen LQ=2h, LR=48h; preserves
`RESULTS.md`): `EMPIRICAL_THRESHOLD_CALIBRATION.md`,
`outputs/EMPIRICAL_CALIBRATION_RESULTS.md`

```bash
.venv/bin/python research/finite-memory-relationship-change/run_empirical_calibration.py
```

DEV→DIAG transfer diagnosis (frozen τ; no new selection):
`outputs/TRANSFER_DIAGNOSIS.md`

```bash
.venv/bin/python research/finite-memory-relationship-change/diagnose_transfer.py
```

Matching-assignment audit (frozen notifications; views B/C post-hoc):
`outputs/MATCHING_ASSIGNMENT_AUDIT.md`

```bash
.venv/bin/python research/finite-memory-relationship-change/audit_matching_assignment.py
```

p369 reference-suppression diagnosis (diagnostic intervention only):
`outputs/REFERENCE_SUPPRESSION_DIAGNOSIS.md`

```bash
.venv/bin/python research/finite-memory-relationship-change/diagnose_reference_suppression.py
```

Frozen 2019 full-year evaluation (protocol before inference; no τ retune):
`YEAR2019_EVALUATION_PROTOCOL.md`, `outputs/YEAR2019_EVALUATION.md`

```bash
.venv/bin/python research/finite-memory-relationship-change/run_year2019_evaluation.py
```

## Boundary

No production/UI/Tiger/main changes. No CUSUM retuning. No feature addition from this evaluation.
