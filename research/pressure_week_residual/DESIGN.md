# Pressure week-residual detection experiment — design (locked before code)

**Branch:** `research/demand-context-audit`  
**Scope:** Isolated offline experiment. No production/UI/API changes. No Tiger imports. No 2019 settings evaluation in this run.  
**Hypothesis:** Pressure *decreases* relative to prior-week same-clock behavior can mark useful investigation intervals. External inflows, pump transfer, and tank level are recorded as context and **must not veto** alerts in this first experiment. AMR features are withheld until a separate comparison is justified.

**Holdout honesty:** All previously examined 2018/2019 leakage cases (including the demand-context audit examples p280/p710/p331/p680/p426) are **development or diagnostic** material, not a fresh blind holdout. This experiment uses **2018 only** for setting selection and frozen diagnostic evaluation.

---

## 1. Score

At each 5-minute timestamp \(t\) and pressure sensor \(s\):

\[
r_s(t) = P_s(t - 7\mathrm{d}) - P_s(t)
\]

Positive \(r_s\) means pressure is **lower** than the same clock time one week earlier.

**Network score** (causal, location-agnostic):

\[
S(t) = \max_{s \in \mathcal{S}_{\mathrm{valid}}(t)} r_s(t)
\]

**Strongest sensor evidence** after scoring: \(\arg\max_s r_s(t)\) among valid sensors (reported on notification; never used to *select* which sensors are evaluated — all configured pressure sensors are always scored when valid).

**Not in the score:** leak pipe/node identity, AMR, flows, pump, tank.

**Context channels (logged only, no veto):** for the same \(t\), prior-week deltas of `p227`, `p235`, `PUMP_1`, and `T1` are attached to notifications for later inspection.

**Raw-pressure baseline (comparison only):**

\[
b_s(t) = P_s(t - 30\mathrm{min}) - P_s(t), \quad B(t) = \max_{s} b_s(t)
\]

Same episode policy as the residual detector; threshold chosen on DEV for **comparable unmatched-episode burden**, not for matching residual recall.

---

## 2. Missing-data rules

- If \(P_s(t)\) or \(P_s(t-7\mathrm{d})\) is missing → sensor \(s\) is **invalid** at \(t\) (excluded from the max).
- If \(\mathcal{S}_{\mathrm{valid}}(t)=\emptyset\) → timestep is flagged `missing_history`; **do not** treat as score 0 / normal; **cannot** start or extend a confirm streak; an active episode may still clear only on valid low scores (see policy).
- **Warm prefix:** for all \(t\) before the first timestamp with a full 7-day lookback in the file, every step is `missing_history` (no scoring as normal).
- Baseline uses the same spirit: missing \(P_s(t)\) or \(P_s(t-30\mathrm{min})\) → invalid sensor; all-invalid → `missing_history`.

---

## 3. Confirmation / clear policy

Fixed structural hyperparameters (not swept broadly):

| Symbol | Value | Meaning |
|--------|-------|---------|
| `confirm_k` | 3 | Need \(S(t)\ge\tau\) on 3 consecutive *valid* steps to open an episode |
| `clear_m` | 6 | Need \(S(t)<\tau\) on 6 consecutive *valid* steps to close |
| Grid | 5 min | Official SCADA cadence |

- **Notification timestamp** = the timestamp of the confirming (k-th) valid exceedance. Only observations with time \(\le\) that timestamp enter the score (by construction).
- **Episode** = contiguous alarmed interval from notification through clear (exclusive of clear completion time as still alarmed through the last high step; duration measured notification → clear time).
- **Already-active episodes:** an onset is matched only by an episode whose **notification** falls in the match window. An episode that was already open before the onset does **not** count as detecting that onset.
- Context values are snapshotted at notification time; they never suppress confirmation.

---

## 4. Chronological development split (2018 only)

| Period | Clock range | Role |
|--------|-------------|------|
| Warm | 2018-01-01 00:00 → first scorable step | `missing_history`; stability check |
| **DEV** | 2018-01-08 00:00 → **2018-06-30 23:55** | Select residual \(\tau\) (and baseline \(\tau_b\) for burden parity) |
| **DIAG** | **2018-07-01 00:00 → 2018-12-31 23:55** | Frozen settings only; no re-tuning |

Settings selected on DEV are **written to** `outputs/frozen_settings.json` **before** DIAG is run in the same scripted sequence (fail if DIAG runs without freeze file).

**2019:** not used for setting selection or metric reporting in this experiment.

---

## 5. Event-matching rules

**Onset set (per period):** every leakage row in `dataset_configuration.yaml` whose `startTime` falls inside the period (abrupt and incipient). Report **overall** onset recall and **abrupt-only** onset recall.

**Match window:** notification \(t_n \in [t_{\mathrm{onset}},\, t_{\mathrm{onset}} + 24\mathrm{h}]\).

**Assignment:** each onset matches at most one episode (earliest notification in window); each episode matches at most one onset. Greedy by onset time.

**Unmatched episode:** notification not assigned to any onset in the period’s onset set.

**Important:** “Unmatched” ≠ “leak-free false alarm.” Other leaks may already be open; non-onset intervals include ordinary operations and ongoing leakage.

**Ongoing leaks:** tracked for reporting (count of open leaks at each notification) but do not auto-credit recall.

---

## 6. Metrics

For each method × period:

1. **Onset recall** — matched onsets / onsets in period (plus abrupt-only).
2. **Notification delays** — hours from onset to notification for matched onsets (median, p90, max).
3. **Unmatched episodes / week** — unmatched episode count / (period length in weeks).
4. **Time in alarm** — total episode duration / period duration.
5. **Longest episode** — max episode duration.

**DEV selection rule (single, pre-registered):** among residual thresholds in the small grid below with **unmatched episodes/week ≤ 2.0**, choose the \(\tau\) with highest **abrupt** onset recall; break ties by higher overall onset recall, then lower time-in-alarm, then larger \(\tau\).

Residual \(\tau\) grid (meters): `{0.25, 0.35, 0.50, 0.75, 1.00, 1.25, 1.50}`.

Baseline: after residual \(\tau^\star\) is frozen, choose \(\tau_b\) from
`{0.15, 0.25, 0.35, 0.50, 0.75, 1.00, 1.10, 1.25, 1.50}` minimizing
\(|u_b - u^\star|\) on DEV unmatched/week among candidates with
\(u_b \ge 0.5\,u^\star\) when any such exist (avoid a near-silent baseline that
only matches burden by extinguishing alerts); ties → lower time-in-alarm.

---

## 7. Causality & warm-prefix checks

- Unit test: score at \(t\) reads only indices \(\le t\) (and \(t-7\mathrm{d}\) / \(t-30\mathrm{min}\)); mutating future samples must not change \(S(t)\).
- Warm prefix: fraction of `missing_history` before first scorable step = 1.0; after warm-up, missing_history rate documented (expect ~0 on complete official files).
- No leak location enters sensor selection or candidate generation.

---

## 8. Out of scope (this experiment)

- Threshold sweeps beyond the grids above; ML models; AMR features; flow/pump/tank vetoes; 2019 evaluation of new settings; production deployment; Tiger imports.
