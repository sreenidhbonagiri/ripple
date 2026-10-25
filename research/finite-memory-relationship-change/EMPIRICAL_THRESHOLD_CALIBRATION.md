# Empirical DEV threshold calibration (registered before runs)

**Preserves:** `outputs/RESULTS.md` (original 16-cell heuristic-τ grid), all other
research packages, production. Does **not** overwrite those reports.

## Question

Are leak-associated score excursions sufficiently extreme relative to **actual
historical** score excursions to support useful notifications?

## Frozen signal (additional development decision)

| Element | Choice |
|---------|--------|
| \(L_Q\) | **2 h** |
| \(L_R\) | **48 h** |

Selected from the completed DEV experiment as the lowest unmatched/week setting
among the registered 16 cells that still kept abrupt 6 h recall = 1.00
(`outputs/RESULTS.md`: unmatched/wk **56.81** at heuristic τ=6). This is an
**additional development decision**, not a claim of optimality or operator
validation.

**Unchanged:** train-only AR(1)/MAD normalization (heuristic scale only — **not**
confidence levels), missing-data handling, recovery (\(N_{\mathrm{rec}}=12\),
clear at τ/2), per-target notification semantics, `build_signals.z` path.

## Empirical thresholds (DEV pooled scores only)

1. Compute finite post-training scores \(s_i(t)\) for all eligible sensors on DEV
   under the frozen windows.  
2. Pool all finite samples. Report **per-sensor contribution** (count / fraction).
   Warn if any sensor dominates (>25% of pooled mass). **Do not** silently drop
   difficult sensors.  
3. Derive one common numeric threshold at empirical percentiles:

\[
\{99,\ 99.5,\ 99.9,\ 99.95,\ 99.99\}
\]

**Caveats (explicit):**

- DEV includes labeled leaks and ordinary operating changes — percentiles are
  **not** a leak-free false-positive calibration.  
- Sample exceedance rate ≠ notification burden (temporal correlation; episode
  semantics). Run the full 33-sensor episode pipeline at each threshold.  
- Do **not** recompute thresholds from DIAG score percentiles.

## DEV selection

Provisional engineering targets (not operator-validated):

1. Abrupt 6 h recall ≥ 2/3  
2. Unmatched notifications/week ≤ 3  

Among qualifiers: max 6 h recall → min unmatched/week → min median 6 h delay.  
Latched / long-active burden reduction alone ≠ success.  
If none qualify → **stop**; no further threshold extension; no DIAG winner.

## DIAG (only if frozen)

One run at the frozen **numeric** threshold. Same metrics + 0–2 h and 0–6 h
notification-time shifted nulls. **Diagnostic** — prior examination; not an
untouched holdout. No 2019 / productization.

## Cumulative history to record

Original heuristic τ grid → selection failure → this empirical percentile
calibration on frozen \(L_Q{=}2,L_R{=}48\).
