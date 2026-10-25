# Measured-PUMP_1 operating-point protocol (DEV selection)

**Registered before evaluation.**  
**Dual variant:** `pump_boundary=measured_pump1` (`PUMP1_MEASURED_BOUNDARY.md`).  
**Frozen calibration sha256:** `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
**Scores:** reuse `outputs/detection_2018_measured_pump1/score_{A,B,C}.csv` (no dual rebuild, no recalibration).  
**Acknowledge:** 2018 events have already been examined; all measured findings are **diagnostic**.

Score definitions, causal reference (24 h + 1 h gap), and notify/recover rules are **unchanged**
from `DETECTION_PROTOCOL.md` / `dual_model/notifier.py`. This document only registers
units, timing limits, a **quantile-derived** τ grid, and DEV gates (including occupancy).

---

## Score units and normalization

| Method | Raw quantity | Units of raw | Normalized score \(s(t)\) | Units of \(s\) |
|--------|--------------|--------------|--------------------------|---------------|
| **A** | \(\Sigma_i q_{v,i}(t)-\mu_{\mathrm{ref}}(\Sigma q_v)\) | m³/h | \(\Delta\Sigma/\max(\sigma_{\mathrm{ref}},\varepsilon)\) | **dimensionless** (z-units of total \(q_v\)) |
| **B** | \(\|\mathbf{q}_v(t)-\boldsymbol{\mu}_{\mathrm{ref}}\|_2\) | m³/h | \(\|\Delta\|_2/\max(\bar\sigma_{\mathrm{ref}},\varepsilon)\) | **dimensionless** (L2 z-units; \(\bar\sigma\) = mean per-sensor ref std) |
| **C** | \(\|Q_{\mathrm{ext}}(t)-\mu_{\mathrm{ref}}\|\) with \(Q_{\mathrm{ext}}=q_{227}+q_{235}\) | m³/h | \(\|\Delta Q_{\mathrm{ext}}\|/\max(\sigma_{\mathrm{ref}},\varepsilon)\) | **dimensionless** (z-units of external inflow) |

- \(\varepsilon = 10^{-3}\) m³/h (score floor in the denominator only).
- A is **signed** (positive ⇒ total virtual outflow above ref). B and C are **non-negative** magnitudes.
- Virtual flow is **not** measured leak discharge. C does **not** include `PUMP_1` (internal transfer).

---

## Temporal resolution and notification timing

| Item | Value | Consequence |
|------|-------|-------------|
| Dual / score grid | **1 hour** (`minute==0`) | Notify timestamps snap to clock hours |
| Credit window | onset … onset+**6 h** | At most ~6 hourly chances to match |
| Earliest possible delay | up to **~1 h** after onset if onset is mid-hour | Sub-hour detection is impossible on this grid |
| Recovery | \(s<\tau/2\) for **1** consecutive hour | Episode clearance granularity = 1 h |
| Warm-up | 25 h after period start | First DEV/DIAG day+ is not scored for gates |

---

## DEV score quantiles (post-warmup, finite only)

Computed once to **register** the grid (not to expand it after seeing gate outcomes).

Period: DEV hours with \(t \ge\) 2018-01-08 00:00 + 25 h, \(t \le\) 2018-06-30 23:00; finite \(s\).

| Method | n | p50 | p75 | p90 | p95 | p99 |
|--------|--:|----:|----:|----:|----:|----:|
| A | 4151 | 0.155 | 0.669 | 1.097 | 1.343 | 1.791 |
| B | 4151 | 5.587 | 7.843 | 10.999 | 13.031 | 19.747 |
| C | 4151 | 0.728 | 1.103 | 1.530 | 1.929 | 2.349 |

---

## Registered τ grid (method-specific; fixed a priori)

For each method, evaluate exactly these four thresholds — the DEV **p75, p90, p95, p99**
rounded to three decimals. **No grid expansion after inspecting results.**

| Method | \(\tau\) candidates |
|--------|---------------------|
| A | `{0.669, 1.097, 1.343, 1.791}` |
| B | `{7.843, 10.999, 13.031, 19.747}` |
| C | `{1.103, 1.530, 1.929, 2.349}` |

→ **12** DEV evaluations total (4 × 3). Selection on **DEV only**.

---

## Notification / recovery (unchanged)

- Notify when inactive and \(s \ge \tau\).
- Recover when \(s < \tau/2\) for 1 consecutive hour.
- NaN: no notify; reset recovery; do not extend episodes.

---

## DEV gates (all required)

A candidate \((\mathrm{method},\tau)\) **passes** only if **all** hold on DEV:

1. **Recall:** abrupt 6 h episode recall \(\ge 2/3\) (2 of 3 eligible DEV abrupt events).
2. **Unmatched burden:** unmatched notifications / week \(\le 3\).
3. **Occupancy:** alarm occupancy \(\le 0.20\) (fraction of DEV hourly steps inside any active episode).

Gate 3 **rejects permanently active detectors** even when unmatched/week is low
(e.g. a single year-long episode with one notify).

**Selection rule:** among passing \(\tau\) for a method, choose the **largest** \(\tau\)
(prefer specificity). Methods are selected independently.

**If no \(\tau\) passes for a method:** that method’s selection **FAILS**.

**Global stop rule:** if **no method** has a passing DEV setting, report selection
failure and **stop** — **do not** run DIAG under a fallback \(\tau\).

**If at least one method passes:** freeze each passing method’s selected \(\tau\) and
run later-2018 DIAG **only** for those frozen settings (diagnostic framing).

---

## Reporting

- Full DEV tradeoff tables for A, B, and C (inflow baseline).
- Event-level hit/miss, delay, pre-onset blocking (episode already active at onset).
- Unmatched/week, occupancy, score distribution summaries.
- DIAG only if selection succeeds for ≥1 method.

No 2019, new features, recalibration, recovery changes, UI, Tiger, deployment, or main merge.
