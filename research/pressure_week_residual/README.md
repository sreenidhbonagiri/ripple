# Pressure week-residual experiment (research only)

Isolated offline detector study on branch `research/demand-context-audit`.

- **Design (locked before code):** [`DESIGN.md`](DESIGN.md)
- **Run:** from repo root, with local `data/raw/2018_SCADA_{Pressures,Flows,Levels}.csv` present (gitignored):

```bash
.venv/bin/python research/pressure_week_residual/run_experiment.py
.venv/bin/python -m pytest research/pressure_week_residual/tests -q
```

- **Outputs:** `outputs/frozen_settings.json`, `outputs/summary.json`, `outputs/RESULTS.md`
- Does **not** modify production/UI, import Tiger, or evaluate new settings on 2019.
