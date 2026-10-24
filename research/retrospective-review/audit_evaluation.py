#!/usr/bin/env python3
"""Audit frozen DIAG matching (no retuning). Writes outputs/AUDIT.md + audit_summary.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate import (  # noqa: E402
    DIAG,
    MATCH_POST_DAYS,
    MATCH_PRE_HOURS,
    match_candidates,
    onsets_in_period,
    period_indices,
)
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402
from method import Candidate, run_interval  # noqa: E402

OUT = ROOT / "outputs"
FROZEN_PATH = OUT / "frozen_settings.json"

# Disclosed narrower tolerances (audit only; not selection criteria).
# Each is (label, pre_hours, post_hours).
NARROWER = [
    ("±6 h", 6.0, 6.0),
    ("±24 h", 24.0, 24.0),
    ("±72 h", 72.0, 72.0),
    ("−6 h … +7 d", 6.0, 7.0 * 24.0),
    ("pre-registered −6 h … +14 d", MATCH_PRE_HOURS, MATCH_POST_DAYS * 24.0),
]

NULL_SHIFT_DAYS = list(range(1, 90))  # daily shifts 1..89 days
STEPS_PER_DAY = 288


def load_frozen() -> dict:
    return json.loads(FROZEN_PATH.read_text())["settings"]


def window_bounds(onset: Leakage, pre_h: float, post_h: float) -> tuple[np.datetime64, np.datetime64]:
    lo = onset.start - np.timedelta64(int(pre_h * 60), "m")
    hi = min(onset.start + np.timedelta64(int(post_h * 60), "m"), onset.end)
    return lo, hi


def match_with_tolerance(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    onsets: list[Leakage],
    leakages_all: list[Leakage],
    pre_h: float,
    post_h: float,
) -> tuple[list[dict], set[int]]:
    """Same greedy one-to-one rule as evaluate.match_candidates, configurable window."""
    used: set[int] = set()
    results: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo, hi = window_bounds(L, pre_h, post_h)
        best_j = None
        best_t = None
        for j, c in enumerate(candidates):
            if j in used:
                continue
            t = timestamps[c.change_idx]
            if lo <= t <= hi:
                if best_j is None or t < best_t:
                    best_j = j
                    best_t = t
        if best_j is None:
            results.append(
                {
                    "pipe": L.pipe,
                    "leak_type": L.leak_type,
                    "onset": str(L.start).replace("T", " "),
                    "matched": False,
                    "change_time": None,
                    "error_hours": None,
                }
            )
            continue
        used.add(best_j)
        c = candidates[best_j]
        err_h = float((best_t - L.start) / np.timedelta64(1, "h"))
        results.append(
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "matched": True,
                "change_time": str(best_t).replace("T", " "),
                "error_hours": err_h,
                "candidate_idx": best_j,
                "duration_hours": float(
                    (c.evidence_through_idx - c.change_idx) * 5 / 60.0
                ),
            }
        )
    return results, used


def alternatives_in_window(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    onset: Leakage,
    matched_j: int | None,
    pre_h: float,
    post_h: float,
) -> int:
    lo, hi = window_bounds(onset, pre_h, post_h)
    n = 0
    for j, c in enumerate(candidates):
        t = timestamps[c.change_idx]
        if lo <= t <= hi:
            n += 1
    # "alternative" = others inside window besides the matched one
    if matched_j is not None and n > 0:
        return max(0, n - 1)
    return n


def coverage_fraction(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    analysis_start: int,
    analysis_end: int,
    pre_h: float,
    post_h: float,
) -> dict:
    """Fraction of eligible analysis times t where ≥1 candidate ĉ falls in [t−pre, t+post].

    Eligible = post-training DIAG analysis indices. Window clipped to analysis timestamps.
    """
    cand_times = np.array([timestamps[c.change_idx] for c in candidates])
    if cand_times.size == 0:
        return {"eligible_steps": analysis_end - analysis_start, "covered_steps": 0, "fraction": 0.0}

    pre = np.timedelta64(int(pre_h * 60), "m")
    post = np.timedelta64(int(post_h * 60), "m")
    t_min = timestamps[analysis_start]
    t_max = timestamps[analysis_end - 1]

    covered = 0
    eligible = analysis_end - analysis_start
    # Sample every step (5 min) — ~50k is fine
    for i in range(analysis_start, analysis_end):
        t = timestamps[i]
        lo = max(t - pre, t_min)
        hi = min(t + post, t_max)
        if np.any((cand_times >= lo) & (cand_times <= hi)):
            covered += 1
    return {
        "eligible_steps": eligible,
        "covered_steps": covered,
        "fraction": covered / eligible if eligible else float("nan"),
        "pre_hours": pre_h,
        "post_hours": post_h,
    }


def shift_candidates(
    candidates: list[Candidate],
    delta_steps: int,
    analysis_start: int,
    analysis_end: int,
) -> list[Candidate]:
    """Circular shift of change/alarm indices within [analysis_start, analysis_end).

    Preserves relative spacings (clustering). Evidence-through recomputed as next change / end.
    """
    span = analysis_end - analysis_start
    if span <= 0 or not candidates:
        return []
    shifted: list[Candidate] = []
    for c in candidates:
        # map relative to analysis window
        rel = c.change_idx - analysis_start
        alarm_rel = c.alarm_idx - analysis_start
        rel = (rel + delta_steps) % span
        alarm_rel = (alarm_rel + delta_steps) % span
        shifted.append(
            Candidate(
                change_idx=analysis_start + rel,
                alarm_idx=analysis_start + alarm_rel,
                score_at_change=c.score_at_change,
                evidence_through_idx=-1,
            )
        )
    shifted.sort(key=lambda x: x.change_idx)
    end_abs = analysis_end - 1
    for i, c in enumerate(shifted):
        if i + 1 < len(shifted):
            c.evidence_through_idx = shifted[i + 1].change_idx
        else:
            c.evidence_through_idx = end_abs
    return shifted


def null_comparison(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    onsets: list[Leakage],
    leakages: list[Leakage],
    analysis_start: int,
    analysis_end: int,
    pre_h: float,
    post_h: float,
) -> dict:
    obs, _ = match_with_tolerance(
        timestamps, candidates, onsets, leakages, pre_h, post_h
    )
    obs_n = sum(1 for m in obs if m["matched"])
    obs_errs = [m["error_hours"] for m in obs if m["matched"]]

    null_matches = []
    null_med_abs_err = []
    for day in NULL_SHIFT_DAYS:
        delta = day * STEPS_PER_DAY
        sc = shift_candidates(candidates, delta, analysis_start, analysis_end)
        rows, _ = match_with_tolerance(
            timestamps, sc, onsets, leakages, pre_h, post_h
        )
        n = sum(1 for m in rows if m["matched"])
        null_matches.append(n)
        errs = [abs(m["error_hours"]) for m in rows if m["matched"]]
        null_med_abs_err.append(float(np.median(errs)) if errs else None)

    arr = np.asarray(null_matches, dtype=float)
    return {
        "observed_matches": obs_n,
        "observed_n_onsets": len(onsets),
        "observed_median_abs_error_hours": float(np.median(np.abs(obs_errs)))
        if obs_errs
        else None,
        "null_shift_days": NULL_SHIFT_DAYS,
        "null_n_shifts": len(NULL_SHIFT_DAYS),
        "null_match_count_mean": float(arr.mean()),
        "null_match_count_median": float(np.median(arr)),
        "null_match_count_p10": float(np.quantile(arr, 0.1)),
        "null_match_count_p90": float(np.quantile(arr, 0.9)),
        "null_fraction_ge_observed": float(np.mean(arr >= obs_n)),
        "null_median_of_median_abs_error_hours": float(
            np.median([x for x in null_med_abs_err if x is not None])
        )
        if any(x is not None for x in null_med_abs_err)
        else None,
        "caveat": (
            "n=5 DIAG onsets; null comparison is descriptive only — "
            "do not treat as strong statistical confidence."
        ),
    }


def diagnose_duplicates(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    matched_idx: set[int],
) -> dict:
    """Characterize the duplicate-unmatched metric (within 24h of another candidate)."""
    change_times = [timestamps[c.change_idx] for c in candidates]
    gaps_h = []
    for i in range(1, len(candidates)):
        gaps_h.append(
            float((change_times[i] - change_times[i - 1]) / np.timedelta64(1, "h"))
        )

    dup_indices = []
    for j, c in enumerate(candidates):
        if j in matched_idx:
            continue
        t = change_times[j]
        near = False
        for k, t2 in enumerate(change_times):
            if k == j:
                continue
            if abs(float((t - t2) / np.timedelta64(1, "h"))) <= 24.0:
                near = True
                break
        if near:
            dup_indices.append(j)

    # Cluster unmatched by 24h chaining
    unmatched = [j for j in range(len(candidates)) if j not in matched_idx]
    clusters: list[list[int]] = []
    for j in unmatched:
        placed = False
        for cl in clusters:
            if any(
                abs(float((change_times[j] - change_times[k]) / np.timedelta64(1, "h")))
                <= 24.0
                for k in cl
            ):
                cl.append(j)
                placed = True
                break
        if not placed:
            clusters.append([j])

    # Gaps exactly ~ min_segment (24h): repeated alarms on sustained elevation
    near_24 = sum(1 for g in gaps_h if 23.0 <= g <= 25.0)
    near_48 = sum(1 for g in gaps_h if 47.0 <= g <= 49.0)
    short = sum(1 for g in gaps_h if g < 23.0)
    longish = sum(1 for g in gaps_h if g > 48.0)

    return {
        "duplicate_unmatched_within_24h": len(dup_indices),
        "n_candidates": len(candidates),
        "n_unmatched": len(unmatched),
        "n_unmatched_clusters_24h": len(clusters),
        "cluster_size_median": float(np.median([len(c) for c in clusters]))
        if clusters
        else None,
        "cluster_size_max": max((len(c) for c in clusters), default=0),
        "consecutive_gap_hours": {
            "median": float(np.median(gaps_h)) if gaps_h else None,
            "p10": float(np.quantile(gaps_h, 0.1)) if gaps_h else None,
            "p90": float(np.quantile(gaps_h, 0.9)) if gaps_h else None,
            "count_gap_23_to_25h": near_24,
            "count_gap_47_to_49h": near_48,
            "count_gap_lt_23h": short,
            "count_gap_gt_48h": longish,
            "n_gaps": len(gaps_h),
        },
        "interpretation": {
            "sensor_pairs": (
                "Unlikely as primary cause: score is already an all-pairs aggregate; "
                "candidates are CUSUM events on one series S(t), not per-pair alarms."
            ),
            "repeated_notifications": (
                "Likely dominant: min_segment_hours=24 forces ≥~24h spacing; "
                f"{near_24}/{len(gaps_h)} consecutive gaps sit in 23–25h — "
                "CUSUM re-arming while residual elevation persists."
            ),
            "distinct_close_changes": (
                f"{short} consecutive gaps <23h (if any) and larger gaps "
                f"({longish} >48h) indicate some separated episodes; "
                "cluster max size "
                f"{max((len(c) for c in clusters), default=0)} shows multi-day trains."
            ),
        },
        "proposed_consolidation_rule": {
            "name": "24h-gap episode merge (label-independent, not implemented)",
            "rule": (
                "Sort candidates by estimated change time. Merge into one review episode "
                "while successive change times differ by ≤ 24 h (same as the duplicate "
                "metric horizon and frozen min_segment). Episode change time = first "
                "change in the run; evidence-through = last evidence-through in the run. "
                "Report both raw candidate count and episode count. Do not use leak labels "
                "or sensor identity."
            ),
            "rationale": (
                "Duplicates appear driven by CUSUM re-triggers on a sustained aggregate "
                "score, not distinct pair-wise detections. A 24h merge matches the "
                "operating point already frozen in min_segment_hours."
            ),
            "status": "proposed only — not implemented or evaluated",
        },
    }


def recall_by_type(rows: list[dict]) -> dict:
    abrupt = [m for m in rows if m["leak_type"] == "abrupt"]
    incip = [m for m in rows if m["leak_type"] == "incipient"]

    def r(xs):
        return (sum(1 for m in xs if m["matched"]) / len(xs)) if xs else float("nan")

    return {
        "onset_recall": r(rows),
        "abrupt_recall": r(abrupt),
        "incipient_recall": r(incip),
        "n_matched": sum(1 for m in rows if m["matched"]),
        "median_abs_error_hours": float(
            np.median([abs(m["error_hours"]) for m in rows if m["matched"]])
        )
        if any(m["matched"] for m in rows)
        else None,
    }


def render_audit(summary: dict) -> str:
    lines = [
        "# Evaluation audit — retrospective review (DIAG)",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "This audit does **not** change the frozen method, settings, or Phase-2 RESULTS headline.",
        "Pre-registered DIAG result remains in `outputs/RESULTS.md` / `summary.json`.",
        "",
        "Deployed Ripple still has **no** validated automatic leak detector; candidates are not live alerts.",
        "",
        "## 1. Matching semantics (precise)",
        "",
        "### Window width",
        "",
        f"- Pre-registered window: **[{MATCH_PRE_HOURS:g} h before onset, "
        f"{MATCH_POST_DAYS:g} days after onset]**, clipped by the leak’s official end time.",
        "- The **14 days is a one-sided post-onset allowance**, not ±14 days "
        f"(total nominal width ≈ {MATCH_PRE_HOURS/24 + MATCH_POST_DAYS:g} days before clipping).",
        "- Matching uses the candidate’s **estimated change time** "
        r"(\(\hat t_c\) = CUSUM last-zero before alarm), **not** the alarm time, "
        "candidate interval midpoint, or evidence-available-through time.",
        "- **One-to-one:** onsets processed in chronological order; each onset and each "
        "candidate used at most once; among candidates in the window, the **earliest** "
        r"\(\hat t_c\) wins.",
        "",
        "### Duplicates, ongoing leaks, boundaries",
        "",
        "- **Duplicates:** metric counts unmatched candidates within 24 h of *any* other "
        "candidate (matched or not). Raw candidate list is preserved; no consolidation in RESULTS.",
        r"- **Ongoing / background leaks:** open-leak count at \(\hat t_c\) is reported; "
        "unmatched candidates are **not** labeled false positives.",
        r"- **Boundary:** only onsets with `startTime` inside DIAG; \(\hat t_c\) must lie in "
        "the post-training analysis span; no timestamps after interval end are used. "
        "Leak-end clipping can shorten the post window for short-lived leaks.",
        "",
        "### Per-onset DIAG table (pre-registered window)",
        "",
        r"| Pipe | Type | True onset | Matched \(\hat t_c\) | Signed err (h) | Cand. duration (h) | Alts in window |",
        "|------|------|------------|----------------------|----------------|--------------------|----------------|",
    ]
    for row in summary["per_onset"]:
        lines.append(
            f"| {row['pipe']} | {row['leak_type']} | {row['onset']} | "
            f"{row['change_time'] or '—'} | "
            f"{'' if row['error_hours'] is None else f'{row['error_hours']:.2f}'} | "
            f"{'' if row['duration_hours'] is None else f'{row['duration_hours']:.2f}'} | "
            f"{row['n_alternatives_in_window']} |"
        )
    lines += [
        "",
        f"Mean alternatives in window (matched onsets): "
        f"**{summary['mean_alternatives_in_window']:.1f}** "
        "(high values indicate dense candidates inside the broad window).",
        "",
        "## 2. Chance matching",
        "",
        "### Coverage of eligible diagnostic time",
        "",
        r"Eligible time = DIAG post-training 5-minute steps. A step \(t\) is *covered* if "
        r"≥1 candidate change time falls in \([t-\mathrm{pre},\, t+\mathrm{post}]\) "
        "(clipped to the analysis span).",
        "",
        f"- Pre-registered window coverage: "
        f"**{summary['coverage']['fraction']:.1%}** "
        f"({summary['coverage']['covered_steps']}/{summary['coverage']['eligible_steps']} steps).",
        "",
        "High coverage means a randomly placed onset would often find *some* candidate "
        "in-window even without a causal link.",
        "",
        "### Time-shift null (clustering preserved)",
        "",
        "Circularly shift all candidate timestamps together inside the analysis window "
        f"by {summary['null']['null_n_shifts']} daily offsets (1–89 days). "
        "Relative gaps preserved. Same greedy matching.",
        "",
        f"- Observed matches: **{summary['null']['observed_matches']}** / "
        f"{summary['null']['observed_n_onsets']}",
        f"- Null match-count mean / median / p10–p90: "
        f"{summary['null']['null_match_count_mean']:.2f} / "
        f"{summary['null']['null_match_count_median']:.1f} / "
        f"{summary['null']['null_match_count_p10']:.1f}–"
        f"{summary['null']['null_match_count_p90']:.1f}",
        f"- Fraction of null shifts with ≥ observed matches: "
        f"**{summary['null']['null_fraction_ge_observed']:.2f}**",
        f"- Observed median |error| (h): {summary['null']['observed_median_abs_error_hours']}",
        f"- Null median of per-shift median |error| (h): "
        f"{summary['null']['null_median_of_median_abs_error_hours']}",
        "",
        f"> {summary['null']['caveat']}",
        "",
        "### Narrower tolerances (disclosed; not headline selection)",
        "",
        "Pre-registered recall stays the RESULTS headline. Below is sensitivity only.",
        "",
        "| Tolerance | Abrupt recall | Incipient recall | Onset recall | n matched | Median |err| (h) |",
        "|-----------|---------------|------------------|--------------|-----------|-------------------|",
    ]
    for row in summary["tolerance_sweep"]:
        lines.append(
            f"| {row['label']} | {row['abrupt_recall']:.2f} | {row['incipient_recall']:.2f} | "
            f"{row['onset_recall']:.2f} | {row['n_matched']} | "
            f"{'' if row['median_abs_error_hours'] is None else f'{row['median_abs_error_hours']:.2f}'} |"
        )
    lines += [
        "",
        "## 3. Duplicate unmatched diagnosis",
        "",
        f"- Duplicate unmatched (within 24 h of another candidate): "
        f"**{summary['duplicates']['duplicate_unmatched_within_24h']}** "
        f"(of {summary['duplicates']['n_unmatched']} unmatched / "
        f"{summary['duplicates']['n_candidates']} raw candidates).",
        f"- Unmatched 24 h clusters: {summary['duplicates']['n_unmatched_clusters_24h']} "
        f"(median size {summary['duplicates']['cluster_size_median']}, "
        f"max {summary['duplicates']['cluster_size_max']}).",
        f"- Consecutive change gaps: median "
        f"{summary['duplicates']['consecutive_gap_hours']['median']:.2f} h; "
        f"{summary['duplicates']['consecutive_gap_hours']['count_gap_23_to_25h']} / "
        f"{summary['duplicates']['consecutive_gap_hours']['n_gaps']} gaps in 23–25 h.",
        "",
        "**Causes**",
        "",
        f"- Different sensor pairs: {summary['duplicates']['interpretation']['sensor_pairs']}",
        f"- Repeated notifications: {summary['duplicates']['interpretation']['repeated_notifications']}",
        f"- Distinct close changes: {summary['duplicates']['interpretation']['distinct_close_changes']}",
        "",
        "### Proposed consolidation (not implemented)",
        "",
        f"- **{summary['duplicates']['proposed_consolidation_rule']['name']}**",
        f"- Rule: {summary['duplicates']['proposed_consolidation_rule']['rule']}",
        f"- Rationale: {summary['duplicates']['proposed_consolidation_rule']['rationale']}",
        f"- Status: {summary['duplicates']['proposed_consolidation_rule']['status']}",
        "",
        "Raw candidate counts in RESULTS remain authoritative.",
        "",
        "## 4. Usefulness (three layers)",
        "",
        "| Layer | What it means | DIAG reading |",
        "|-------|---------------|--------------|",
        "| Broad event association | Some candidate falls in a wide post-onset window | "
        f"Pre-registered onset recall 1.00, but coverage "
        f"{summary['coverage']['fraction']:.0%} and null ≥-obs fraction "
        f"{summary['null']['null_fraction_ge_observed']:.2f} show association is "
        "easy under dense candidates |",
        r"| Reasonably timed change ID | \(\hat t_c\) near true onset (e.g. within ~24–72 h) | "
        "See tolerance sweep: abrupt/incipient recall drop under ±6–24 h; "
        "p654’s +243 h match is association, not tight timing |",
        "| Reviewer workload | Episodes a human would open | "
        f"~{summary['workload']['candidates_per_week']:.1f} raw candidates/week "
        f"(~{summary['workload']['unmatched_per_week']:.1f} unmatched/week); "
        f"~{summary['workload']['implied_episodes_per_week_if_24h_merge']:.1f}/week "
        "if 24 h merge were applied (illustrative only) |",
        "",
        "The **≤3 unmatched/week** DEV gate was a **provisional research budget**, not an "
        "operator SLA. Do not promote on recall alone; do not reject solely because that "
        "budget failed — weigh timing quality, coverage/chance, and workload together.",
        "",
        "## Bottom line",
        "",
        summary["bottom_line"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    from evaluate import iso_now

    settings = load_frozen()
    bundle = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()
    start_i, end_i = period_indices(bundle.timestamps, DIAG)
    _model, cands, _scores = run_interval(
        bundle.pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=settings["train_days"],
        cusum_k=settings["cusum_k"],
        cusum_h=settings["cusum_h"],
        min_segment_hours=settings["min_segment_hours"],
    )
    train_steps = settings["train_days"] * STEPS_PER_DAY
    analysis_start = start_i + train_steps
    analysis_end = end_i
    onsets = onsets_in_period(leakages, DIAG)

    # Pre-registered matches (must agree with evaluate.match_candidates)
    prereg, used = match_candidates(bundle.timestamps, cands, onsets, leakages)
    prereg2, _ = match_with_tolerance(
        bundle.timestamps,
        cands,
        onsets,
        leakages,
        MATCH_PRE_HOURS,
        MATCH_POST_DAYS * 24.0,
    )
    assert [m["matched"] for m in prereg] == [m["matched"] for m in prereg2]

    per_onset = []
    alts = []
    for m, L in zip(prereg2, sorted(onsets, key=lambda x: x.start), strict=True):
        mj = m.get("candidate_idx")
        n_alt = alternatives_in_window(
            bundle.timestamps,
            cands,
            L,
            mj,
            MATCH_PRE_HOURS,
            MATCH_POST_DAYS * 24.0,
        )
        alts.append(n_alt)
        per_onset.append(
            {
                "pipe": m["pipe"],
                "leak_type": m["leak_type"],
                "onset": m["onset"],
                "change_time": m["change_time"],
                "error_hours": m["error_hours"],
                "duration_hours": m.get("duration_hours"),
                "n_alternatives_in_window": n_alt,
                "matched": m["matched"],
            }
        )

    cov = coverage_fraction(
        bundle.timestamps,
        cands,
        analysis_start,
        analysis_end,
        MATCH_PRE_HOURS,
        MATCH_POST_DAYS * 24.0,
    )
    null = null_comparison(
        bundle.timestamps,
        cands,
        onsets,
        leakages,
        analysis_start,
        analysis_end,
        MATCH_PRE_HOURS,
        MATCH_POST_DAYS * 24.0,
    )
    dups = diagnose_duplicates(bundle.timestamps, cands, used)

    sweep = []
    for label, pre_h, post_h in NARROWER:
        rows, _ = match_with_tolerance(
            bundle.timestamps, cands, onsets, leakages, pre_h, post_h
        )
        stats = recall_by_type(rows)
        stats["label"] = label
        stats["pre_hours"] = pre_h
        stats["post_hours"] = post_h
        sweep.append(stats)

    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(cands) - len(used)
    # Illustrative episode count under proposed 24h merge (not a new metric claim)
    change_times = [bundle.timestamps[c.change_idx] for c in cands]
    episodes = 0
    last = None
    for t in change_times:
        if last is None or float((t - last) / np.timedelta64(1, "h")) > 24.0:
            episodes += 1
        last = t

    bottom = (
        "DIAG 100% pre-registered recall is **not** strong evidence of precise onset "
        "identification: candidate density covers most of the eligible timeline, "
        f"many alternatives sit in each onset window (mean {float(np.mean(alts)):.1f}), "
        "and time-shifted nulls often achieve similar match counts. "
        "Usefulness for a reviewer is closer to a dense change list (~"
        f"{len(cands)/weeks:.1f}/week raw) than to a sparse leak detector. "
        "Keep RESULTS as documentation; do not promote UI on this matching story alone."
    )

    summary = {
        "generated_at": iso_now(),
        "frozen_settings": settings,
        "n_diag_candidates": len(cands),
        "per_onset": per_onset,
        "mean_alternatives_in_window": float(np.mean(alts)) if alts else 0.0,
        "coverage": cov,
        "null": null,
        "tolerance_sweep": sweep,
        "duplicates": dups,
        "workload": {
            "candidates_per_week": len(cands) / weeks,
            "unmatched_per_week": unmatched / weeks,
            "implied_episodes_per_week_if_24h_merge": episodes / weeks,
            "raw_candidates": len(cands),
            "illustrative_episodes_24h_merge": episodes,
            "note": "Episode count is illustrative for the proposed rule only",
        },
        "bottom_line": bottom,
        "preregistered_headline_unchanged": True,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "AUDIT.md").write_text(render_audit(summary) + "\n")
    print(bottom)
    print(f"Wrote {OUT / 'AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
