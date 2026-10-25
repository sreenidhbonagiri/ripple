# Audit of the shared t≈199 pre-onset trigger

Generated: 2026-10-24T23:16:00-04:00

**Scope:** Diagnostic only. Frozen Arm A (`C=10`, `τ=0.7`). No refit, no
threshold sweep, no selection change, no 2019, no new simulations.

**Preserves:** Arm A/B freezes, change-only ablation reports, episode-objective
outputs, prior miss audit, production.

---

## Question

Is the synchronized notify near synthetic index **t=199** (~16.583 h):

1. an **implementation artifact**,  
2. a **legitimate operating transition misclassified as onset**, or  
3. **unresolved**?

Also: is leak timing coupled to scenario phase across train/dev/test?

---

## 1. What fires at t≈199

| Fact | Evidence |
|------|----------|
| Exact index mass | **20** notifies at `notify_idx==199`; **29** first `q≥τ` crossings in `[195,205]` out of 40 ok scenarios |
| Composition at 199 | **18/24** leak scenarios + **2** `control_demand` (no leak) |
| Crossing shape | For trigger scenarios, `q(198)≈0.69 → q(199)≈0.71` — **slow creep across τ**, not a one-step spike |
| Warm-up boundary | Feature scores start at `t=144` with mean `q≈0.23`, **frac≥τ = 0**; crossing is **~4.6 h later** — not first-finite / NaN edge |
| Max-lag window | `d24` features reference `t−24`; at 199 that is `t=175`, well after warm-up — not a “window just became valid” discontinuity |

**Not (1) as a coder bug:** notifier recovery, label indexing, and warm-up masking do not create a false edge at 199. The score is finite and rising for hours before the crossing.

---

## 2. Hydraulics around t=199 (leaks and controls)

Shared L-TOWN controls: pump opens when T1 level **&lt; 2.4 m**, closes when **&gt; 3.9 m**. All scenarios share the same INP patterns aligned at simulation `t=0`.

**Fleet-mean (all ok scenarios), t=190…210:**

- Tank level slowly falls (~2.56 → 2.49 m).  
- Pump-on fraction rises (~0.12 → 0.55) as individual tanks hit the open threshold.  
- Network median pressure drifts slightly down.  
- Mean `q` rises through ~0.48–0.55 (many individual scenarios sit near τ).

**Trigger examples (notify at 199):**

- Several leaks (e.g. `leak_004_p709`) have **pump still OFF** through 190–210 while T1 drains (~2.60 → 2.44 m) toward the 2.4 m open setpoint — notify occurs **before** that scenario’s pump-on.  
- Some others turn pump on shortly after 199 (e.g. transition near 202).  
- `ctrl_001_control_demand` can be pump-ON in the same window with rising tank — still can notify near the same clock hour in other controls (hour-16 cluster in prior miss audit).

So the common clock marks a **network operating-phase neighborhood** (evening demand / tank-drain / impending or ongoing pump cycle), not a leak orifice event.

---

## 3. Classifier feature contributions at the trigger

At `t=199` for all 20 exact-199 notifiers, top |contribution| features are dominated by **absolute operating state**:

| Feature | In top-10 | Mean contrib (z·β) |
|---------|-----------|--------------------|
| `P_p90` | 20/20 | +3.79 |
| `P_p10` | 20/20 | −3.16 |
| `P_min` | 20/20 | +2.79 |
| `pump1_on` | 20/20 | −2.74 |
| `Pd_d24_median` | 20/20 | −2.49 |
| `F_p227` | 20/20 | −2.41 |
| `L_T1` | 20/20 | +2.31 |

Largest **Δcontrib from t=198→199** (what tips `q` over τ):

- `Pd_d24_median` (+0.23), `Pd_d24_p90` (−0.21), `Fd_p227_d24`, `Fd_p235_d24`, `P_p10`  

Interpretation: the **level** of the score is set by absolute P/F/L/pump state shared by the diurnal phase; the **last step over τ** is a small update in 2 h / 30 min change features — consistent with a slow operating transition, not an abrupt leak onset signature.

Arm B (levels removed) previously still produced high control burden under episode selection — absolute levels amplify this latch, but the shared clock itself remains a scenario-design fact.

---

## 4. Leak timing vs scenario phase (train / dev / test)

Leak starts are sampled once from  
`uniform[WARMUP+2, DURATION−10] = [14 h, 38 h]` on a **fixed** pattern clock.

| Split | Onset after t=199 | Onset ≤199 | Mean start hour |
|-------|-------------------|------------|-----------------|
| train | 3/4 | 1/4 | 24.35 |
| synthetic_dev | 5/5 | 0/5 | 24.12 |
| synthetic_test | 15/15 | 0/15 | 25.53 |

**Coupling:** Across splits, almost every leak onset is **after** the shared ~16.6 h phase trigger. Therefore a notify at 199 is **systematically pre-onset** for nearly the entire leak set — then the recovery latch blocks a fresh credit-window notify (see miss audit).

Demand scale modulates who hits exactly 199 (triggers tend toward `demand_scale≤1.0`; non-trigger leaks often `≥1.03`), i.e. operating intensity shifts tank/pump timing — still phase/operating coupling, not pipe-leak identity.

Controls are **not** invented pairs; they share the same clock and also show hour-16 episode mass — confirming the trigger is not leak-specific.

**Control ep/wk denominator (unchanged disclosure):** each control is only 48 h (`≈0.286` weeks); rates over a handful of controls are short-horizon.

---

## 5. Decision

**2 — Legitimate operating transition misclassified as onset.**

- Not (1): warm-up / feature-window / notifier indexing artifacts ruled out.  
- Not (3): evidence is convergent across hydraulics, controls, absolute-feature attributions, and cross-split onset-after-199 coupling.

The transition is “real” in the simulator (tank/pump/demand phase on a shared clock). The **misclassification** is treating that phase as a leak-onset notification. Construction makes the error especially damaging by placing nearly all leaks after that shared latch time.

---

## 6. Recommended next correction (do not implement yet)

**One intervention:** when (re)building synthetic scenarios, **randomize each scenario’s pattern time origin** (independent phase offset into L-TOWN demand/pump/tank schedules) while keeping leak-area, pipe, demand-scale, and episode-notification labels/objective unchanged.

**Why this and not selection tweaks first:** the t≈199 mass is a **shared absolute clock** in the data generator; gating pre-onset latch on DEV would treat a symptom of that alignment. Phase randomization attacks the cause that also fires on controls. Absolute-feature ablation (Arm B) already showed that removing levels alone does not yield a clean episode operating point.

**Out of scope for now:** refit, τ search, 2019, measured retune, implementing the phase offset.

---

## Artifacts

Machine-readable companion: `summary.json` (same directory).
