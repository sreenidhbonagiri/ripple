# Evaluation audit — retrospective review (DIAG)

Generated: 2026-10-24T19:36:06-04:00

This audit does **not** change the frozen method, settings, or Phase-2 RESULTS headline.
Pre-registered DIAG result remains in `outputs/RESULTS.md` / `summary.json`.

Deployed Ripple still has **no** validated automatic leak detector; candidates are not live alerts.

## 1. Matching semantics (precise)

### Window width

- Pre-registered window: **[6 h before onset, 14 days after onset]**, clipped by the leak’s official end time.
- The **14 days is a one-sided post-onset allowance**, not ±14 days (total nominal width ≈ 14.25 days before clipping).
- Matching uses the candidate’s **estimated change time** (\(\hat t_c\) = CUSUM last-zero before alarm), **not** the alarm time, candidate interval midpoint, or evidence-available-through time.
- **One-to-one:** onsets processed in chronological order; each onset and each candidate used at most once; among candidates in the window, the **earliest** \(\hat t_c\) wins.

### Duplicates, ongoing leaks, boundaries

- **Duplicates:** metric counts unmatched candidates within 24 h of *any* other candidate (matched or not). Raw candidate list is preserved; no consolidation in RESULTS.
- **Ongoing / background leaks:** open-leak count at \(\hat t_c\) is reported; unmatched candidates are **not** labeled false positives.
- **Boundary:** only onsets with `startTime` inside DIAG; \(\hat t_c\) must lie in the post-training analysis span; no timestamps after interval end are used. Leak-end clipping can shorten the post window for short-lived leaks.

### Per-onset DIAG table (pre-registered window)

| Pipe | Type | True onset | Matched \(\hat t_c\) | Signed err (h) | Cand. duration (h) | Alts in window |
|------|------|------------|----------------------|----------------|--------------------|----------------|
| p654 | incipient | 2018-07-05 03:40 | 2018-07-15 06:50 | 243.17 | 0.75 | 3 |
| p810 | incipient | 2018-07-28 03:05 | 2018-07-28 10:15 | 7.17 | 1.08 | 13 |
| p183 | abrupt | 2018-08-07 02:35 | 2018-08-06 23:55 | -2.67 | 1.42 | 13 |
| p158 | abrupt | 2018-10-06 02:35 | 2018-10-06 18:25 | 15.83 | 12.25 | 14 |
| p369 | abrupt | 2018-10-26 02:05 | 2018-10-26 02:00 | -0.08 | 10.08 | 13 |

Mean alternatives in window (matched onsets): **11.2** (high values indicate dense candidates inside the broad window).

## 2. Chance matching

### Coverage of eligible diagnostic time

Eligible time = DIAG post-training 5-minute steps. A step \(t\) is *covered* if ≥1 candidate change time falls in \([t-\mathrm{pre},\, t+\mathrm{post}]\) (clipped to the analysis span).

- Pre-registered window coverage: **99.8%** (48866/48960 steps).

High coverage means a randomly placed onset would often find *some* candidate in-window even without a causal link.

### Time-shift null (clustering preserved)

Circularly shift all candidate timestamps together inside the analysis window by 89 daily offsets (1–89 days). Relative gaps preserved. Same greedy matching.

- Observed matches: **5** / 5
- Null match-count mean / median / p10–p90: 5.00 / 5.0 / 5.0–5.0
- Fraction of null shifts with ≥ observed matches: **1.00**
- Observed median |error| (h): 7.166666666666667
- Null median of per-shift median |error| (h): 10.416666666666666

> n=5 DIAG onsets; null comparison is descriptive only — do not treat as strong statistical confidence.

### Narrower tolerances (disclosed; not headline selection)

Pre-registered recall stays the RESULTS headline. Below is sensitivity only.

| Tolerance | Abrupt recall | Incipient recall | Onset recall | n matched | Median |err| (h) |
|-----------|---------------|------------------|--------------|-----------|-------------------|
| ±6 h | 0.67 | 0.00 | 0.40 | 2 | 1.38 |
| ±24 h | 1.00 | 0.50 | 0.80 | 4 | 4.92 |
| ±72 h | 1.00 | 0.50 | 0.80 | 4 | 41.79 |
| −6 h … +7 d | 1.00 | 0.50 | 0.80 | 4 | 4.92 |
| pre-registered −6 h … +14 d | 1.00 | 1.00 | 1.00 | 5 | 7.17 |

## 3. Duplicate unmatched diagnosis

- Duplicate unmatched (within 24 h of another candidate): **96** (of 135 unmatched / 140 raw candidates).
- Unmatched 24 h clusters: 78 (median size 1.0, max 6).
- Consecutive change gaps: median 24.42 h; 47 / 139 gaps in 23–25 h.

**Causes**

- Different sensor pairs: Unlikely as primary cause: score is already an all-pairs aggregate; candidates are CUSUM events on one series S(t), not per-pair alarms.
- Repeated notifications: Likely dominant: min_segment_hours=24 forces ≥~24h spacing; 47/139 consecutive gaps sit in 23–25h — CUSUM re-arming while residual elevation persists.
- Distinct close changes: 31 consecutive gaps <23h (if any) and larger gaps (14 >48h) indicate some separated episodes; cluster max size 6 shows multi-day trains.

### Proposed consolidation (not implemented)

- **24h-gap episode merge (label-independent, not implemented)**
- Rule: Sort candidates by estimated change time. Merge into one review episode while successive change times differ by ≤ 24 h (same as the duplicate metric horizon and frozen min_segment). Episode change time = first change in the run; evidence-through = last evidence-through in the run. Report both raw candidate count and episode count. Do not use leak labels or sensor identity.
- Rationale: Duplicates appear driven by CUSUM re-triggers on a sustained aggregate score, not distinct pair-wise detections. A 24h merge matches the operating point already frozen in min_segment_hours.
- Status: proposed only — not implemented or evaluated

Raw candidate counts in RESULTS remain authoritative.

## 4. Usefulness (three layers)

| Layer | What it means | DIAG reading |
|-------|---------------|--------------|
| Broad event association | Some candidate falls in a wide post-onset window | Pre-registered onset recall 1.00, but coverage 100% and null ≥-obs fraction 1.00 show association is easy under dense candidates |
| Reasonably timed change ID | \(\hat t_c\) near true onset (e.g. within ~24–72 h) | See tolerance sweep: abrupt/incipient recall drop under ±6–24 h; p654’s +243 h match is association, not tight timing |
| Reviewer workload | Episodes a human would open | ~5.3 raw candidates/week (~5.1 unmatched/week); ~3.0/week if 24 h merge were applied (illustrative only) |

The **≤3 unmatched/week** DEV gate was a **provisional research budget**, not an operator SLA. Do not promote on recall alone; do not reject solely because that budget failed — weigh timing quality, coverage/chance, and workload together.

## Bottom line

DIAG 100% pre-registered recall is **not** strong evidence of precise onset identification: candidate density covers most of the eligible timeline, many alternatives sit in each onset window (mean 11.2), and time-shifted nulls often achieve similar match counts. Usefulness for a reviewer is closer to a dense change list (~5.3/week raw) than to a sparse leak detector. Keep RESULTS as documentation; do not promote UI on this matching story alone.

