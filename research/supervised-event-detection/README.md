# Supervised multivariate event detection (research)

Design: `DESIGN.md`  
Synthetic-trained **pilot** (this round): `outputs/PILOT_RESULTS.md`

## Pilot run

```bash
.venv/bin/python -m pytest research/supervised-event-detection/tests -q
.venv/bin/python research/supervised-event-detection/run_pilot.py
```

Requires: `wntr`, `scikit-learn`, official `data/L-TOWN.inp`, 2018 SCADA under `data/raw/`.

Transfer-failure diagnosis (frozen pilot unchanged):
`outputs/TRANSFER_FAILURE_DIAGNOSIS.md`

```bash
.venv/bin/python research/supervised-event-detection/diagnose_transfer_failure.py
```

## Boundary

- Preserves production and frozen FMR3C evaluations
- No Tiger imports, UI, main merge, or deployment
- No training/tuning on 2019
- Stop after the pilot — no simulator/model search expansion
- Diagnosis does not retune; no fit unless a concrete bug fix is required
