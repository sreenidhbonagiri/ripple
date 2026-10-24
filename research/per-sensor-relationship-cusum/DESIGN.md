# Per-sensor relationship residual CUSUM — design (locked before runs)

**Branch:** `research/per-sensor-relationship-cusum`  
**From:** `main` @ production investigation workspace (Tiger-backed).  
**Local only:** no production/UI/Tiger imports/merge/deploy.

**Product boundary:** Deployed Ripple has **no validated automatic leak detector**. This experiment studies **causal sequential detection** from pressure relationships. Outputs are research episodes — **not** confirmed leaks and **not** live product alerts.

**Prior negative result (preserved, not contradicted):**  
`research/retrospective-review` closed global Frobenius residual + offline CUSUM as **unsuccessful** for *timed* identification beyond candidate density (`DECISION.md`). This experiment asks a **different** question with a **different** signal path and **notification-time** metrics.

**Holdout honesty:** 2019 is **not** evaluated. 2018 DEV → freeze → DIAG only. Labels never select references or sensors.

**Attribution:** Inspired by relationship-residual ideas in Daniel et al. (2022) / LILA identification *concepts*. **Independent code.** Does **not** copy LILA/practice source and does **not** claim to reproduce published or competition results. See `refs/ATTRIBUTION.md`.

---

## Question

Does preserving **signed, per-target** pressure-relationship residuals improve **causal detection** compared with **global residual aggregation**, under equivalent development effort and matching rules?

---

## Differences from `research/retrospective-review` (precise)

| Aspect | Prior (closed) | This experiment |
|--------|----------------|-----------------|
| Residual | Squared / Frobenius magnitude over **all** directed pairs | **Signed** under-pressure residual per **target** vs selected references |
| Aggregation | One network-wide score \(S(t)\) | One trajectory \(z_i(t)\) **per target sensor** (median of normalized pair residuals) |
| Reference use | All pairs equally | Top-\(K\) references from **training** prediction error / stability / availability only |
| Detector | Offline CUSUM; candidate = estimated change time | **Sequential** one-sided CUSUM per target; episode **notification** = first threshold crossing at 5-min availability |
| Reset policy | Reset after alarm + min segment → repeated candidates on sustained elevation | **No** periodic re-alarm while episode active; rearm only after documented recovery |
| Primary time | Retrospective \(\hat t_c\) (backdated) | **Notification time** (not backdated to change estimate) |
| Matching | Allowed \(\hat t_c\) in \([t_0-6\mathrm{h},\,t_0+14\mathrm{d}]\) | Abrupt success only if notify \(\in[t_0,\,t_0+W]\); **pre-onset notify ≠ success** |
| Chance null | Circular shift of change times | Circular shift of **notification** times (same procedure family) |
| Comparison | (none within that package) | Global aggregation baseline with **equivalent** episode rules & matching |

---

## Signal construction

### Directed models

For target \(i\) and reference \(j\neq i\):

\[
\hat P_i^{(j)}(t) = a_{ij} + b_{ij}\, P_j(t)
\]

fit by OLS on the **training/calibration** window (finite pairs only).

### Signed residual (leak-oriented polarity)

\[
e_{ij}(t) = \hat P_i^{(j)}(t) - P_i(t)
\]

**Positive** \(e_{ij}\) means measured pressure is **below** relationship-based expectation (under-pressure relative to reference).

### Reference selection (training only; no leak locations)

For each target \(i\), score every \(j\neq i\) on the training window:

1. **Availability:** \(n_{ij}\) finite paired samples; require \(n_{ij} \ge n_{\min}\) (default 0.8 × training length).  
2. **Prediction error:** RMSE of \(\hat P_i^{(j)}\) vs \(P_i\) on train.  
3. **Residual stability:** MAD of \(e_{ij}\) on train (lower = more stable).  
4. Reject near-singular regressors (\(\mathrm{Var}(P_j)<\varepsilon\)).

**Composite rank** (lower better):  
\(\mathrm{rank}(\mathrm{RMSE}) + \mathrm{rank}(\mathrm{MAD})\), among eligible \(j\).  
Keep top \(K \in \{3,5\}\) (grid). **Never** use known leak pipes/nodes or event-specific picking.

### Normalization and per-target aggregate

On training residuals for each kept pair \((i,j)\):

- location: median \(m_{ij}\)  
- scale: \(\mathrm{MAD}_{ij}\) (fallback to sample std if MAD≈0; if still tiny, skip pair)

Normalized:

\[
\tilde e_{ij}(t) = (e_{ij}(t) - m_{ij}) / (c\cdot\mathrm{MAD}_{ij})
\]

with \(c=1.4826\) (normal consistency).  

**Target signal** at time \(t\):

\[
z_i(t) = \mathrm{median}\{\tilde e_{ij}(t) : j\in\mathcal{R}_i,\ \text{both sensors finite at }t\}
\]

Require at least \(n_{\mathrm{ref,min}}\) (default \(\lceil K/2\rceil\)) valid references at \(t\); else \(z_i(t)\) is missing.

Preserve all per-target \(z_i\) trajectories and which references contributed (logged at notification).

### Failure modes (documented; not assumed away)

- **Common-mode pressure drop:** if target and references drop together, \(\hat P_i\) tracks \(P_i\) → \(e_{ij}\approx 0\) → **leak signal can be suppressed**.  
- **Affected reference:** a disturbed reference biases \(\hat P_i\) and can create **false** under/over-pressure on the target or cancel a true drop.  
- **Demand / topology:** linear pairwise models do **not** cancel demand perfectly; seasonal and diurnal mismatch remain in \(z_i\).

---

## Training / calibration periods

| Period | Range | Role |
|--------|-------|------|
| DEV | 2018-01-01 → 2018-06-30 23:55 | Parameter selection only |
| DIAG | 2018-07-01 → 2018-12-31 23:55 | Frozen evaluation only |

Within each period analysis interval \([T_0,T_1]\):

- **Training/calibration** = first `train_days` ∈ `{14}` calendar days (grid may include 7 if budget allows).  
- **Not** labeled leak-free: 2018 has **background / already-open leaks** and limited seasonal coverage (winter–spring for DEV train; summer for DIAG train). Coefficients and MAD scales may be biased by those conditions.  
- Analysis / detection runs from training end through \(T_1\) at 5-minute steps. Never use \(t>T_1\).

2019: **not evaluated**.

---

## Sequential detector (per target)

One-sided CUSUM on positive under-pressure:

\[
C_i(t) = \max\bigl(0,\ C_i(t^-)+ z_i(t) - k\bigr)
\]

evaluated only when \(z_i(t)\) is finite (actual observation availability).

| Element | Specification |
|---------|----------------|
| Allowance \(k\) | Grid / fixed `{0.5}` |
| Threshold \(h\) | `{4.0, 6.0, 8.0}` |
| Min history | Training complete; pair \(n_{ij}\ge n_{\min}\) |
| Min refs at \(t\) | \(n_{\mathrm{ref,min}}\) or mark missing |
| Missing \(z_i\) | Do **not** update \(C_i\) (hold previous \(C_i\)); do not count as recovery steps |
| **Notification time** | First \(t\) with \(C_i(t)\ge h\) while **not** already in an active episode — **not** backdated to CUSUM last-zero |
| Confirmation | Crossing \(h\) itself (no extra delay beyond 5-min sample) |
| Active episode | Remains active while \(C_i>0\) or until recovery rule fires; **no** new notification while active |
| Recovery | \(N_{\mathrm{rec}}\) consecutive **finite** steps with \(C_i=0\) (default from `recover_hours`, 12 steps/hour) |
| Rearm | Allowed only after recovery completes |
| Episode fields | `target_sensor`, `notify_time`, `refs_used`, `end_time` (recovery or period end), `change_estimate` logged for diagnostics **only** (not primary metric) |
| Already-active at new onset | If an episode is active when a labeled onset occurs, that episode’s notify time is scored under matching rules as-is (may be pre-onset → **not** abrupt success); a **new** episode is **not** forced |

**Forbidden:** periodic CUSUM reset that turns one sustained elevation into repeated “new” incidents.  
**Forbidden:** flow/tank vetoes.

---

## Parameter budget (DEV only; ≤ 12 cells)

| Parameter | Values |
|-----------|--------|
| `train_days` | `{14}` |
| `n_refs` \(K\) | `{3, 5}` |
| `cusum_k` | `{0.5}` |
| `cusum_h` | `{4.0, 6.0, 8.0}` |
| `recover_hours` | `{12, 24}` |

→ 2×3×2 = **12** settings. Report **every** attempted setting.

**Selection rule (pre-registered):** among settings with **unmatched episodes/week ≤ 3.0** on DEV, maximize **abrupt notification recall**; ties → lower unmatched/week → larger \(h\) → larger \(K\).  
If none meet the unmatched cap, freeze best-of-pool with `gate_met=false` (document failure).  
Write `outputs/frozen_settings.json` **before** DIAG.

---

## Event matching (locked before results)

**Abrupt onsets** in period: official `startTime` in period, `type=abrupt`.

**Primary match window (abrupt):** notification \(t_n \in [t_0,\ t_0 + W]\) with \(W = 7\) days, and \(t_n \le t_e\) (leak end).  
**Pre-onset notifications are not successes** (even if close).

**Incipient / gradual:** report separately. Match if \(t_n \in [t_0,\ \min(t_0+14\mathrm{d},\ t_{\mathrm{peak}})]\) (explicit). Still no credit for \(t_n < t_0\).

**One-to-one:** onsets chronological; each onset and each episode used once; earliest eligible \(t_n\) wins.

**Network notify:** any target sensor’s episode may match (first eligible across sensors).

**Delay:** \(t_n - t_0\) in hours (matched abrupt only).

**Unmatched episodes** are not automatic false positives (background leaks / ops).

**We do not claim BattLeDIM economic scoring.**

---

## Global aggregation comparison (equivalent effort)

Baseline: same directed OLS fits on the same training window; aggregate

\[
S(t)=\sqrt{\sum_{i\neq j} e_{ij}(t)^2}
\]

over all valid directed pairs (no per-target reference selection), standardize with training median/MAD of \(S\), one sequential CUSUM with the **same** \(k,h,\) recovery/episode rules and **notification-time** matching.  
Parameter selection: **same grid dimensions** where applicable (`train_days`, `k`, `h`, `recover_hours`; `n_refs` N/A — one stream). Freeze independently on DEV under the same unmatched/week rule, then DIAG.

---

## Chance comparison

Circular-shift **notification times** (preserve inter-episode gaps) within post-training analysis span; identical matching/eligibility/boundaries.  
Report observed vs null match counts at the **pre-registered abrupt window**. Descriptive only (small \(n\)); beating null is **necessary**, not sufficient for operational usefulness.

---

## Metrics

- Abrupt recall; delay distribution  
- Incipient recall (separate definition)  
- Unmatched episodes / week; time-in-alarm; longest episode  
- Duplicate burden: unmatched episodes within 24 h of another  
- Per notification: target sensor + reference set  
- Ordinary controls: large ΔPUMP_1 / ΔT1 near notifications  
- Global baseline same metrics  
- Null fraction of shifts ≥ observed abrupt matches  

---

## Verification (before tuning)

Synthetic tests (behavior only, not BattLeDIM accuracy): target-only drop; common-mode move; reference disturbance; two incidents after recovery; sustained change → single episode; missing gaps; warmed prefix; check \(\hat P_i\) tracks expectation under target drop.
