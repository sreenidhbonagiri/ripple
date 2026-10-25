# Variant registration — residual-normalization recovery

**Registered before evaluation.**  
**Branch:** `research/per-sensor-relationship-cusum`  
**Does not replace** the original frozen detector, settings, or `outputs/RESULTS.md`.

## Hypothesis

Observable residual normalization can clear CUSUM debt while preserving timely
notifications and avoiding repeated alarms during sustained residual elevation.

## Held identical to frozen original

| Element | Value |
|---------|--------|
| Training / calibration | First 14 days of each period (DEV / DIAG) |
| Directed fits / refs / normalization | Unchanged `build_signals` path |
| `n_refs` (K) | 3 |
| CUSUM allowance \(k\) | 0.5 |
| CUSUM threshold \(h\) | 8.0 |
| Notification | First \(t\) with \(C_i(t)\ge h\) while **inactive** (not backdated) |
| Event eligibility | Post-training onsets only for primary recall; prefix onsets (incl. p654) separate |
| Matching | Abrupt: notify \(\in[t_0,t_0+7\mathrm{d}]\); no pre-onset credit; one-to-one |

Original recovery (preserved, still available): 24 h consecutive **\(C_i=0\)** on finite \(z\).

## Sole change — recovery while active

**Fixed engineering hypothesis (not swept):** clear after **12** consecutive 5-minute
observations with **finite** \(z_i \le k\).

- Elevated residual (\(z_i > k\)) resets the consecutive recovery counter.  
- Missing \(z_i\): breaks the recovery run, **holds** \(C_i\), does **not** clear.  
- On clear: end episode at that sample, set \(C_i\leftarrow 0\), rearm (inactive).  
- No time-only clear, periodic reset, or forced new notification.

### Per-sample transition order (exact semantics)

For analysis step \(t\) on target \(i\):

1. If \(z_i(t)\) is **missing**: leave \(C_i\) unchanged; set `recover_run ← 0`;
   leave active/inactive unchanged; **stop** processing this sample.
2. If **active**:
   1. If \(z_i(t) \le k\): `recover_run ← recover_run + 1`; else `recover_run ← 0`.
   2. If `recover_run ≥ 12`: **clear** — record `end_idx = t`, append episode,
      set `active ← false`, `C_i ← 0`, `recover_run ← 0`; **do not** apply the
      CUSUM increment on this sample after clear; **stop**.
   3. Else: \(C_i \leftarrow \max(0, C_i + z_i(t) - k)\); update peak; **stop**.
3. If **inactive**:
   1. \(C_i \leftarrow \max(0, C_i + z_i(t) - k)\).
   2. If \(C_i = 0\): refresh last-zero index (diagnostic only).
   3. If \(C_i \ge h\): **notify** at \(t\) (episode start); `active ← true`;
      `recover_run ← 0`.

At period end, any still-active episode is closed as **right-censored** at the
last analysis index (same as original).

## Non-goals this round

- No recovery-length sweep  
- No normalization / scale changes  
- No 2019 evaluation  
- No UI / production / deploy
