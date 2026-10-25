# Baseline reconciliation — residual-recovery metrics

Generated as a **new** report. Does **not** overwrite `VARIANT_COMPARISON.md` or
`CONTEXT_COMPARISON.md`.

## Observed drift (reports as written)

| Metric (DIAG, residual-recovery policy) | `VARIANT_COMPARISON` (variant arm) | `CONTEXT_COMPARISON` (“baseline”) |
|-----------------------------------------|------------------------------------|-----------------------------------|
| Unmatched notifications/week | **77.23** | **89.0** |
| Summed sensor-alarm % of eligible | **25.72%** | **31.39%** |
| 0–2 h null frac ≥ observed | **0.47** | **0.16** |
| Episode count | 2034 | 2343 |

## Root cause (explained)

The context experiment’s “baseline” was **not** the same residual series as the
registered residual-recovery variant.

| Piece | Variant / original relationship signal | Context “baseline” |
|-------|----------------------------------------|--------------------|
| Pairwise fits / refs | `build_signals` training-only selection | Same `build_signals` refs/fits |
| Residual construction | Per-pair normalize \(\tilde e_{ij}\), then **median → \(z_i\)** | Aggregate raw \(r_i=\mathrm{median}_j e_{ij}\) (meters), then **one** loc/scale on \(r_i\) → \(z\) |
| Detector / matching / null | Residual-recovery; same eligibility | Same policy, but on the **different** \(z\) |
| Code | `run_residual_recovery_variant.py` → `sig.z` | `run_context_experiment.py` → `dual.z_base` from `context_residual.build_dual_signals` |

Input SCADA, timestamps, frozen `{K=3,k=0.5,h=8,recover_hours=24, residual_recover_steps=12}`,
episode construction, matching, and null procedures were otherwise aligned.
**No unexplained difference remains** once the signal path is distinguished.

## Reproduction check

Re-running DIAG on `build_signals(...).z` with residual-recovery reproduces the
variant arm **exactly** (Δ unmatched/wk = 0, Δ sensor occupancy = 0, Δ null frac = 0).
See `outputs/baseline_reconciliation.json`.

## Correction for subsequent work

- Treat **`VARIANT_COMPARISON.md` / `sig.z`** as the authoritative residual-recovery
  baseline for the original per-sensor relationship signal.
- Treat **`CONTEXT_COMPARISON.md` baseline** as a *different* aggregate-normalized
  series used only for pairing with context correction — **not** a revised reprint
  of the variant baseline.
- Threshold calibration below uses the **original `build_signals` \(z\)** path only.

## Historical reports

Left unchanged on purpose (no silent overwrite).
