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

Change-only ablation gate (target alignment) — **stopped before fit**:
`outputs/TARGET_ALIGNMENT_BEFORE_ABLATION.md`

Episode-notification selection objective (same scenarios/features/labels;
not an ablation):

```bash
.venv/bin/python research/supervised-event-detection/run_episode_objective_pilot.py
```

Protocol: `EPISODE_SELECTION_PROTOCOL.md`  
Results: `outputs/episode_objective/EPISODE_OBJECTIVE_RESULTS.md`

Change-only feature ablation (paired Arms A/B; episode-notification objective):

```bash
.venv/bin/python research/supervised-event-detection/run_change_only_ablation.py
```

Protocol: `CHANGE_ONLY_ABLATION_PROTOCOL.md`  
Results: `outputs/change_only_ablation/CHANGE_ONLY_ABLATION_RESULTS.md`

Arm A synthetic-test miss audit (diagnostic; no refit):

```bash
.venv/bin/python research/supervised-event-detection/audit_arm_a_synth_misses.py
```

Results: `outputs/arm_a_synth_miss_audit/ARM_A_SYNTH_MISS_AUDIT.md`

Shared t≈199 pre-onset trigger audit (diagnostic; no refit):
`outputs/t199_trigger_audit/T199_TRIGGER_AUDIT.md`

## Boundary

- Preserves production and frozen FMR3C evaluations
- No Tiger imports, UI, main merge, or deployment
- No training/tuning on 2019
- Stop after the pilot — no simulator/model search expansion
- Diagnosis does not retune; no fit unless a concrete bug fix is required
