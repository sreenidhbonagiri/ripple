# Per-sensor relationship residual CUSUM (research)

Branch `research/per-sensor-relationship-cusum` from `main`.

- **Design (locked):** [`DESIGN.md`](DESIGN.md)
- **Attribution:** [`refs/ATTRIBUTION.md`](refs/ATTRIBUTION.md)
- Independent of LILA source; does not reproduce published results.
- Prior `research/retrospective-review` negative decision is preserved elsewhere.

```bash
.venv/bin/python -m pytest research/per-sensor-relationship-cusum/tests -q
.venv/bin/python research/per-sensor-relationship-cusum/run_experiment.py
```

Outputs: `outputs/frozen_settings.json`, `outputs/RESULTS.md`, `outputs/summary.json`, regenerable plots.

Eligibility / occupancy / recovery audit (frozen settings unchanged): `outputs/AUDIT.md`

```bash
.venv/bin/python research/per-sensor-relationship-cusum/audit_occupancy_recovery.py
```
