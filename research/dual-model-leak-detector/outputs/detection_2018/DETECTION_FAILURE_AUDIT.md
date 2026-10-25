# Dual-model detection failure audit (no parameter search)

**Frozen results preserved.** No threshold sweep, no recovery retune, no 2019.

## 1. Calibration provenance

| Source | sha256 |
|--------|--------|
| Declared / required | `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921` |
| `outputs/calibration/frozen_calibration.json` (bytes on disk) | **identical** |
| `calibration_hashes.json` | identical |
| `detection_results.json` → `frozen_calibration_sha256` | identical (64 hex chars) |
| `REQUIRED_FROZEN_SHA256` in code | identical |

**Discrepancy with `5fab3acb…90e06`:** none in artifacts. That abbreviation was a
**chat-summary typo**. Correct short form is `5fab3acb…0c921` (suffix `0c921`, not
`90e06`). The detection run loaded and verified the full declared hash.

---

## 2. Pump / tank transition virtual-flow excursions

### Timestamp / interval conventions

- SCADA: 5 min. Dual detection series: **hourly** samples at `minute==0`.
- Pump on/off events (5 min `|ΔPUMP_1|>20`): **n=684** in 2018; only **~7%** fall
  exactly on `:00`. Hourly dual therefore usually sees a **smeared** pre/post
  state, not the exact switching instant.

### Tank init / storage / pump controls (dual)

- Each dual chunk: tank `init_level` from measured T1 at chunk start; EPANET
  tank–pump **controls** from INP (open below 2.4 m, close above 3.9 m).
- Measured `PUMP_1` is **not** imposed as a flow BC (documented Stage-3 departure).
- Storage rate for **mass-balance demand** on 5 min data uses
  `A · Δh · 12` (correct: Δh per 5 min → m/h).

### Concrete implementation bug (reporting metric)

`detection_eval.py` flagged transitions with

```text
dV = tank_area * (hourly_level.diff() * 12)
```

On an **hourly** index, `diff()` is already m/h; the extra `×12` inflates storage
rate ~12×.

| Estimator | mean \|dV\| (m³/h) | frac \|dV\|>15 |
|-----------|-------------------:|---------------:|
| Hourly wrong `×12` | ~278 | **0.99** |
| Hourly correct | ~23 | 0.82 |
| Pump-only `\|ΔPUMP\|>10` | — | **0.078** |

So the published “~98% unmatched notifies on transitions” is **not trustworthy**:
it is dominated by this bug (and a loose storage threshold even when corrected).
**Minimal correction (proposed, not executed here):** use
`dV = area * level.diff()` when the series timestep is 1 h; keep `×12` only for
5 min diffs. Do **not** re-interpret detection gates until that metric is fixed.

### Are switch q_v excursions physical, measurement, or model error?

Week of 2018-01-08 (13 clear pump switches), dual under frozen calibration:

- Dominant sensor for Δq_v at switches is usually **`n54`** (pump delivery node).
- Mean `|ΔΣq_v|` at switches ≈ 22 m³/h vs ordinary hour `|ΔΣq_v|` ≈ 28 m³/h —
  sum magnitude is **not** uniquely larger at switches.
- Per-sensor L2 jump at switches is often large and **localized at n54** when the
  pump steps ~0↔44 m³/h while the dual pump is still driven by tank rules / head
  solution rather than measured flow.

**Interpretation:** excursions are largely **model boundary mismatch** (pump not
tied to measured `PUMP_1`), amplified by hourly alignment smear — not evidence
that “true leaks never occur at transitions,” and not a reason to veto those
hours. Signed per-sensor structure (n54) matters; the sum alone hides it.

---

## 3. Missed abrupt events (consistent ±36 h rebuild; global scores/notifier)

Credit window = onset … onset+6 h. Control: same clock time −7 d where available
in the rebuilt window (often incomplete → `ctrl_delta` null).

### Method A (signed Σq_v change), τ=1.5 (fallback)

| Event | Period | credit max score | vs τ | Mechanism |
|-------|--------|-----------------:|------|-----------|
| p673 | DEV | 1.96 | above | **Hit** (notify in credit) |
| p538 | DEV | 1.79 | above | **Hit** |
| p866 | DEV | 0.53 | **below** | Miss: score never reaches τ |
| p183 | DIAG | 0.77 | **below** | Miss: below τ |
| p158 | DIAG | 0.96 | **below** | Miss: below τ |
| p369 | DIAG | 0.88 | **below** | Miss: below τ |

None of the A misses were blocked by a prior episode. Raw Σq_v mean shift
onset−24h→credit is **mixed** (e.g. p183 **negative** −17 m³/h; p158/p369
~+16 m³/h) and comparable to ordinary operating variability seen in the pump
week — so several misses are **signal below threshold / not separable**, not
cancellation inside the notifier.

### Method B (vector L2), τ=1.0 (fallback)

Every event: `blocked_by_prior_episode=True`, `n_credit_notifies=0`, while
credit max score ≫ τ (10–23). Misses are **blocked by a single year-long
active episode**, not “below threshold.”

### Method C (|Δ| external inflow), τ=1.0 (fallback)

| Event | credit max | Mechanism |
|-------|-----------:|-----------|
| p673 | 1.36 | Blocked by prior episode |
| p538 | 0.92 | Below τ |
| p866 | 1.29 | Hit |
| p183 | 1.63 | Blocked |
| p158 | 2.01 | Hit |
| p369 | 1.80 | Hit |

---

## 4. Method B ≈100% occupancy

| Quantity | Value |
|----------|------:|
| Episodes | **1** (notify idx 12 → end of series) |
| frac finite scores `≥ τ` | 0.999 |
| frac `≥ τ/2` | 0.999 |
| frac `< τ/2` | **0** |
| max consecutive hours `< τ/2` | **0** |
| mean score | ~6.8 (p50 ~5.3) |

**Primary cause: persistently elevated scores.**  
`‖q_v(t)−μ_ref‖₂ / σ_ref` with a 24 h ref is almost always ≫ 1 because ordinary
hour-to-hour spatial variability exceeds the ref-window scale (example:
`‖Δ‖≈10`, `σ_ref≈1.6` → score≈6.6).

**Secondary: recovery latching.**  
With recover = 1 h of `s<τ/2` and `s` never entering that region, the first notify
never clears — producing one episode and occupancy≈1. Latching does not create
the elevation; it only prevents episode turnover.

This is a **score-definition / normalization limitation**, not a τ-grid accident.

---

## Recommendation — ONE intervention

**Impose measured `PUMP_1` as a dual-model boundary (paper-aligned), instead of
relying only on INP tank-level pump controls.**

Supported by this audit:

1. Switch-time Δq_v is systematically dominated by **n54**, the pump node.
2. Measured pump steps (~44 m³/h) are not enforced in the dual (explicit Stage-3
   departure); hourly sampling already smears true switch times.
3. This targets a **hydraulic BC error** that injects virtual-flow structure
   unrelated to leaks, without vetoing transition hours (leaks can occur then)
   and without sweeping τ or softening recovery to chase metrics.

**Separately (minimal bugfix, not the detection intervention):** correct
hourly storage `dV` in the transition-confounding helper (`×12` only for 5 min
steps) before trusting those percentages; then recompute that diagnostic only.

### What not to do (per this audit)

- Do not veto pump/tank transition hours as a detection rule.
- Do not sweep τ or change recovery to raise reported recall/occupancy.
- Do not treat Method B’s occupancy as a quiet low-burden success.

### Physical / statistical limitation (if pump BC is fixed and failures remain)

Method A’s credit-window z-scores for several abrupt DIAG events stay `< 1.5`
while ordinary `|ΔΣq_v|` is already tens of m³/h — abrupt leak imprint in
**total** virtual flow may remain weak relative to demand/operations noise
under the current dual. That would be a statistical limitation of Σq_v change
detection, to be assessed only after the pump-BC intervention.
