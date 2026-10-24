# Decision report — retrospective pairwise residual screening

Generated: 2026-10-24T19:38:58-04:00

Frozen detector, candidates, matching rules, and settings are **unchanged**. No new algorithm, merge rule, threshold, UI, or deployment.

Pre-registered Phase-2 headline remains in `outputs/RESULTS.md`. Matching semantics and chance audit remain in `outputs/AUDIT.md`.

## Scope of this decision

Question: does the frozen experiment show **useful temporal identification** beyond what its **candidate density** would produce by chance?

Method: existing circular-shift null (preserve relative candidate gaps; shift within DIAG post-training analysis bounds; identical one-to-one matching).

Tolerances: **±6 h** and **±24 h** only — already reported in the evaluation audit. Neither is selected after seeing these nulls; both are reported.

## Null procedure notes

- Valid shifts: **89** daily offsets (1–89 days).
- Shifts **overlap** (same pattern, sliding phase). Treat the set as a **descriptive ensemble**, not as independent trials or a formal p-value.
- Five DIAG events total — do **not** claim strong statistical confidence.

## Results by tolerance

### ±6 h

| Slice | Observed matches | Null median (min–max) | Fraction of shifts ≥ observed |
|-------|------------------|------------------------|----------------------------------|
| All (5 onsets) | 2 | 1 (0–3) | 0.27 |
| Abrupt (3) | 2 | 1 (0–2) | 0.20 |
| Incipient (2) | 0 | 0 (0–1) | 1.00 |

Observed median |change-time error| (h): overall 1.375, abrupt 1.375, incipient None.

### ±24 h

| Slice | Observed matches | Null median (min–max) | Fraction of shifts ≥ observed |
|-------|------------------|------------------------|----------------------------------|
| All (5 onsets) | 4 | 4 (1–4) | 0.83 |
| Abrupt (3) | 3 | 3 (0–3) | 0.84 |
| Incipient (2) | 1 | 1 (0–1) | 0.98 |

Observed median |change-time error| (h): overall 4.916666666666667, abrupt 2.6666666666666665, incipient 7.166666666666667.

## Estimated change time vs evidence available through

Retrospective **estimated change time** (\(\hat t_c\)) is the CUSUM last-zero before alarm. **Evidence available through** is the later bound used for candidate duration (next candidate or interval end) — *not* a real-time alert timestamp and *not* used for matching.

| Pipe | Type | Tolerance context | \(\hat t_c - t_0\) (h) | Alarm−change (h) | Evidence−change (h) | Evidence−onset (h) |
|------|------|-------------------|------------------------|-------------------|---------------------|--------------------|
| p654 | incipient | unmatched at ±6/±24 h | — | — | — | — |
| p810 | incipient | matched at ±24 h; not ±6 h | 7.17 | 1.08 | 1.08 | 8.25 |
| p183 | abrupt | matched at ±24 h; also ±6 h | -2.67 | 1.42 | 1.42 | -1.25 |
| p158 | abrupt | matched at ±24 h; not ±6 h | 15.83 | 2.08 | 12.25 | 28.08 |
| p369 | abrupt | matched at ±24 h; also ±6 h | -0.08 | 1.33 | 10.08 | 10.00 |

## Decision signals (descriptive)

| Tolerance | Observed | Null median | Frac. shifts ≥ obs | Beyond density? |
|-----------|----------|-------------|--------------------|-----------------|
| ±6 h | 2 | 1 | 0.27 | no |
| ±24 h | 4 | 4 | 0.83 | no |

### Limitations

- Only five DIAG onsets (3 abrupt, 2 incipient); descriptive counts only.
- Daily circular shifts (1–89 d) heavily overlap in structure; they are dependent probes of the same candidate pattern, not independent experiments.
- Null preserves clustering and density by design; it tests timing association against a density-matched alternative, not hydraulic truth.
- Frozen method/settings/matching unchanged; no post-hoc tolerance selection for the decision headline.

## Conclusion

**Verdict: unsuccessful**

This experiment does **not** supply evidence of useful temporal identification beyond its candidate density. At both already-reported ±6 h and ±24 h tolerances, circularly shifted candidates match as many (or nearly as many) DIAG onsets as the unshifted list under identical one-to-one rules. Combined with near-complete timeline coverage under the broad pre-registered window, the frozen operating point is closed as **unsuccessful** for retrospective change screening aimed at timed onset identification. Do not productize; do not treat RESULTS recall as validated leak detection.

## Product boundary

Ripple’s deployed investigation workspace remains without a validated automatic leak detector. This research approach is closed for productization on the frozen operating point. No UI/API work follows from this report.

