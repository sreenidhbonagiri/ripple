# Scenario-phase correction protocol (registered before fit)

**Experiment:** randomize hydraulic pattern time origin; independently sample
leak onset after warm-up. Same phase distribution for leak and no-leak
scenarios.

**Preserves:** original `outputs/synthetic_scenarios/`, all prior pilot /
episode-objective / ablation / audit artifacts, production.

**New outputs only:** `outputs/synthetic_scenarios_phase/`,
`outputs/phase_correction/`

**Stop after synthetic test.** No measured 2018/2019 evaluation in this run.

---

## What changes (exact)

| Element | Original pilot | This experiment |
|---------|----------------|-----------------|
| Pattern clock | All scenarios `pattern_start=0`, `start_clocktime=0` | Per-scenario `pattern_phase_offset_hours ~ Unif[0, 24)`; set `wn.options.time.pattern_start` and `start_clocktime` to that offset (seconds) |
| Leak onset | `Unif[14, 38]` h on the shared clock | **Independent** `Unif[14, 38]` h on **scenario wall time** (after 12 h warm-up) |
| Phase vs onset | Coupled (shared clock + late onsets → systematic pre-onset latch at ~16.6 h) | Phase and onset sampled independently |
| Matched pairs | None | 16 leak↔control pairs share `pair_id` and **identical** `pattern_phase_offset_hours`; forced into the **same** whole-scenario split |
| Tank/pump INP controls | Level-based (T1 &lt;2.4 open / &gt;3.9 close) | **Unchanged** — remain level-based, so they follow hydraulics under the shifted demand clock |
| Artificial `control_pump` SimTime blocks | Fixed scenario times after warm-up | Still scenario-wall times after warm-up (not pattern-shifted) |
| Features / labels / L2 / C·τ budget / notifier / episode DEV gates | As episode-objective | **Unchanged** |
| Model inputs | No scenario clock / onset | Still forbidden — no time or onset features |

## What does not change

- Feature set `pressure_context_v1` (53 dims), StandardScaler on train only
- L2 logistic, `C_GRID`, `TAU_GRID`, episode selection rule and gates
- Notifier: notify `q≥τ` while inactive; recover 12 steps below `τ/2`
- Label: `y=1` on `[onset, onset+6h]` only
- Original NPZs and reports (never overwritten)

## Selection and eval order

1. Simulate → write new scenario dir  
2. **Verify** phase and onset distributions (leaks vs controls; phase⊥onset) — abort fit if checks fail  
3. Fit + episode select on synthetic DEV  
4. Freeze → synthetic test  
5. **Stop** (no measured transfer this round)

## Master seed

`PHASE_MASTER_SEED = 20261025` (distinct from original `20261024`).
