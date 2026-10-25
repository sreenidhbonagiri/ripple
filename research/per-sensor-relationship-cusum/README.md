# Per-sensor relationship residual CUSUM (research)

Branch `research/per-sensor-relationship-cusum` from `main`.

- **Design (locked):** [`DESIGN.md`](DESIGN.md)
- **Attribution:** [`refs/ATTRIBUTION.md`](refs/ATTRIBUTION.md)
- Independent of LILA source; does not reproduce published results.
- Prior `research/retrospective-review` negative decision is preserved elsewhere.

**CUSUM-family threshold tuning: closed.** Further \(h\) / recovery / context
sweeps on this detector family are not continued. Preserved results remain in
`outputs/` (including `THRESHOLD_CALIBRATION_*.md`). Next distinct question
(finite-memory recent–reference change) is design-only under
`research/finite-memory-relationship-change/` — not implemented from this package.

```bash
.venv/bin/python -m pytest research/per-sensor-relationship-cusum/tests -q
.venv/bin/python research/per-sensor-relationship-cusum/run_experiment.py
```

Outputs: `outputs/frozen_settings.json`, `outputs/RESULTS.md`, `outputs/summary.json`, regenerable plots.

Eligibility / occupancy / recovery audit (frozen settings unchanged): `outputs/AUDIT.md`

```bash
.venv/bin/python research/per-sensor-relationship-cusum/audit_occupancy_recovery.py
```

Residual-recovery variant (paired; original preserved): `VARIANT_RESIDUAL_RECOVERY.md`, `outputs/VARIANT_COMPARISON.md`

```bash
.venv/bin/python -m pytest research/per-sensor-relationship-cusum/tests -q
.venv/bin/python research/per-sensor-relationship-cusum/run_residual_recovery_variant.py
```

Calibration / separability audit: `outputs/CALIBRATION_AUDIT.md`

```bash
.venv/bin/python research/per-sensor-relationship-cusum/audit_calibration_separability.py
```

Operating-context residual correction (paired; residual-recovery policy fixed):
`CONTEXT_DESIGN.md`, `outputs/CONTEXT_COMPARISON.md`

```bash
.venv/bin/python -m pytest research/per-sensor-relationship-cusum/tests -q
.venv/bin/python research/per-sensor-relationship-cusum/run_context_experiment.py
```

Baseline reconciliation + DEV-only CUSUM-h calibration (original `build_signals.z`):
`outputs/BASELINE_RECONCILIATION.md`, `THRESHOLD_CALIBRATION.md`,
`outputs/THRESHOLD_CALIBRATION_RESULTS.md`

```bash
.venv/bin/python research/per-sensor-relationship-cusum/run_threshold_calibration.py
```

Grid extension (higher \(h\); dual 6 h sensitivity + unmatched gates):
`THRESHOLD_CALIBRATION_EXTENSION.md`,
`outputs/THRESHOLD_CALIBRATION_EXTENSION_RESULTS.md`

```bash
.venv/bin/python research/per-sensor-relationship-cusum/run_threshold_calibration_extension.py
```
