# Retrospective pressure-pattern review (research)

Offline feasibility experiment on branch `research/retrospective-review`.

- **Design (locked before runs):** [`DESIGN.md`](DESIGN.md)
- **Attribution:** [`refs/ATTRIBUTION.md`](refs/ATTRIBUTION.md)
- **Not** a live leak detector; candidates are for human investigation only.
- Local official `data/raw/2018_SCADA_*.csv` only — no Tiger imports / production migrations / UI.

```bash
.venv/bin/python -m pytest research/retrospective-review/tests -q
.venv/bin/python research/retrospective-review/run_experiment.py
```

Outputs: `outputs/frozen_settings.json`, `outputs/summary.json`, `outputs/RESULTS.md`, regenerable plots under `outputs/plots/` (gitignored).

Evaluation audit (frozen method unchanged): `outputs/AUDIT.md` — run via

```bash
.venv/bin/python research/retrospective-review/audit_evaluation.py
```

Decision report (nulls at ±6 h / ±24 h; no retuning): `outputs/DECISION.md`

```bash
.venv/bin/python research/retrospective-review/decision_report.py
```
