# 2018 dual-model detection feasibility — registered protocol

**Registered before execution.**  
**Frozen calibration sha256:** `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
**Acknowledge:** 2018 leak events have already been examined in prior research;
DIAG metrics are diagnostic under this protocol, not a first look.

No event-specific calibration, sensor selection, or threshold retuning after freeze.
Virtual flow is **not** measured leak discharge.

---

## Chronological periods (exclude FIT from evaluation)

| ID | Start | End | Role |
|----|-------|-----|------|
| `FIT_W1` | 2018-01-01 00:00 | 2018-01-07 23:55 | Calibration only — **excluded** from DEV/DIAG scoring |
| `DEV` | 2018-01-08 00:00 | 2018-06-30 23:55 | Threshold selection (past data only) |
| `DIAG` | 2018-07-01 00:00 | 2018-12-31 23:55 | Frozen evaluation |

Eligible **abrupt** onsets (BattLeDIM `leakType=abrupt`) with onset inside the period:

- DEV: `p673` (2018-03-05), `p538` (2018-05-18), `p866` (2018-06-01)
- DIAG: `p183` (2018-08-07), `p158` (2018-10-06), `p369` (2018-10-26)

Incipient leaks are **not** counted in the primary six-hour abrupt recall gate
(recorded separately as diagnostic only if convenient).

---

## Methods (same protocol for all)

| ID | Score (before z-norm) | Rationale |
|----|----------------------|-----------|
| **A** | \(\Delta\Sigma(t)=\sum_i q_{v,i}(t)-\mu_{\mathrm{ref}}(\sum_i q_{v,i})\) | Signed total virtual-flow change |
| **B** | \(\|\mathbf{q}_v(t)-\boldsymbol{\mu}_{\mathrm{ref}}(\mathbf{q}_v)\|_2\) | Per-sensor vector change; no sign cancellation |
| **C** | \(\|Q_{\mathrm{ext}}(t)-\mu_{\mathrm{ref}}(Q_{\mathrm{ext}})\|\) with \(Q_{\mathrm{ext}}=q_{227}+q_{235}\) | External-inflow-change baseline |

Hydraulic `q_v` from dual model under **frozen** calibration only (hourly EPS chunks).

### Causal reference / normalization

- Reference window: the **24 h** ending **1 h before** \(t\) (causal gap; no contemporaneous leak peeking).
- Require ≥12 finite hourly samples in the reference; else score = NaN (no notify).
- \(\mu_{\mathrm{ref}}\), \(\sigma_{\mathrm{ref}}\) from that window (for A/C on scalar; for B, \(\boldsymbol{\mu}_{\mathrm{ref}}\) is the per-sensor mean vector; \(\sigma_{\mathrm{ref}}\) for B is the mean of per-sensor ref stds, floor \(\varepsilon=10^{-3}\) m³/h).
- Normalized score \(s(t)=(x(t)-\mu)/\max(\sigma,\varepsilon)\).  
  - A: one-sided — use \(s_A=\Delta\Sigma/\sigma\) (positive = increased total virtual outflow).  
  - B, C: already non-negative change magnitudes → \(s=x/\sigma\).

### Notification / recovery

- Hourly grid (matches dual eval cadence).
- Notify when inactive and \(s\ge\tau\).
- Recover when \(s<\tau/2\) for **1** consecutive hour (`RECOVER_STEPS=1` ≈ Ripple’s 1 h clearance).
- Missing/NaN: do not notify; reset recovery counter; do not extend episodes.

### Selection budget (DEV only; fixed a priori)

Threshold candidates (shared across methods):

\[
\tau\in\{1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0\}
\]

→ at most **7 × 3 = 21** DEV evaluations. No adaptive search beyond this set.

### DEV gates (identical for A, B, C)

Select the **largest** \(\tau\) that satisfies both (prefer specificity when tied):

1. Abrupt six-hour episode recall \(\ge 2/3\)
2. Unmatched notifications / week \(\le 3\)

If **no** \(\tau\) passes: selection **FAILS**; report explicitly. Any DIAG numbers under a
fallback \(\tau\) (largest recall among budget, else mid budget \(\tau=2.5\)) are
**diagnostic only**, labeled `selection_failed`.

Freeze chosen \((\mathrm{method},\tau)\) triples independently (each method picks its own \(\tau\)).

---

## Eligibility, matching, nulls

**Eligibility (primary):** abrupt onset in period; credit window \([t_0, t_0+6\mathrm{h}]\)
intersects the period; onset ≥ 25 h after period start (reference warm-up).

**One-to-one matching:** each eligible event matched to the earliest notify in its
6 h credit window. That notify is “matched.” All other notifies are **unmatched**
(burden). Occupancy = fraction of hourly steps with an active episode.

**Density-matched timing nulls:** for each method’s frozen \(\tau\), draw \(N=200\)
null onset sets: sample \(|E|\) timestamps uniformly from eligible hours in the
period that match the empirical hour-of-day distribution of the true abrupt
onsets (bootstrap hours from true onsets). Recompute abrupt 6 h recall. Report
null mean/std and percentile of the true recall among nulls.

**Operating-transition confounding:** mark hours where `|ΔPUMP_1| > 10` m³/h or
`|A dh/dt| > 15` m³/h; report fraction of unmatched notifies that fall on such
hours. `A dh/dt` must use the series timestep (hourly dual: `A·Δh/Δt` with
`Δt` in hours — do **not** apply the 5 min `×12` factor to hourly diffs).

---

## Reporting

DEV selection table; DIAG (or diagnostic-fallback) abrupt 6 h recall, delays,
unmatched/week, occupancy, transition confounding, timing nulls — for A, B, C.
Stop after 2018. No 2019.
