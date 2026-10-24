#!/usr/bin/env python3
"""Decision report: temporal ID vs density using existing circular-shift nulls.

Preserves frozen detector, candidates, matching rules, and settings.
Does not choose a new operating tolerance after seeing results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_evaluation import (  # noqa: E402
    NULL_SHIFT_DAYS,
    STEPS_PER_DAY,
    load_frozen,
    match_with_tolerance,
    shift_candidates,
)
from evaluate import DIAG, iso_now, onsets_in_period, period_indices  # noqa: E402
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402
from method import Candidate, run_interval  # noqa: E402

OUT = ROOT / "outputs"

# Already-reported tolerances from AUDIT (fixed a priori for this decision; not re-selected).
TOLERANCES = [
    {"label": "±6 h", "pre_hours": 6.0, "post_hours": 6.0},
    {"label": "±24 h", "pre_hours": 24.0, "post_hours": 24.0},
]


def _by_type(rows: list[dict], leak_type: str) -> list[dict]:
    return [m for m in rows if m["leak_type"] == leak_type]


def null_at_tolerance(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    onsets: list[Leakage],
    leakages: list[Leakage],
    analysis_start: int,
    analysis_end: int,
    pre_h: float,
    post_h: float,
) -> dict:
    """Same circular-shift null as audit_evaluation.null_comparison, with type splits."""
    obs, _ = match_with_tolerance(
        timestamps, candidates, onsets, leakages, pre_h, post_h
    )

    def count_matched(rows: list[dict], leak_type: str | None = None) -> int:
        xs = rows if leak_type is None else _by_type(rows, leak_type)
        return sum(1 for m in xs if m["matched"])

    def med_abs_err(rows: list[dict], leak_type: str | None = None) -> float | None:
        xs = rows if leak_type is None else _by_type(rows, leak_type)
        errs = [abs(m["error_hours"]) for m in xs if m["matched"]]
        return float(np.median(errs)) if errs else None

    obs_n = count_matched(obs)
    obs_abr = count_matched(obs, "abrupt")
    obs_inc = count_matched(obs, "incipient")
    n_abr = len(_by_type(obs, "abrupt"))
    n_inc = len(_by_type(obs, "incipient"))

    null_all: list[int] = []
    null_abr: list[int] = []
    null_inc: list[int] = []

    for day in NULL_SHIFT_DAYS:
        sc = shift_candidates(
            candidates, day * STEPS_PER_DAY, analysis_start, analysis_end
        )
        rows, _ = match_with_tolerance(
            timestamps, sc, onsets, leakages, pre_h, post_h
        )
        null_all.append(count_matched(rows))
        null_abr.append(count_matched(rows, "abrupt"))
        null_inc.append(count_matched(rows, "incipient"))

    def summarize(obs_count: int, null_counts: list[int], n_events: int) -> dict:
        arr = np.asarray(null_counts, dtype=float)
        return {
            "n_events": n_events,
            "observed_matches": obs_count,
            "null_n_valid_shifts": len(null_counts),
            "null_match_median": float(np.median(arr)),
            "null_match_min": int(arr.min()),
            "null_match_max": int(arr.max()),
            "null_match_mean": float(arr.mean()),
            "fraction_shifts_ge_observed": float(np.mean(arr >= obs_count)),
        }

    # Per-onset timing: change estimate vs evidence-available-through (alarm / next bound)
    timing_rows = []
    onset_by_pipe = {L.pipe: L for L in onsets}
    for m in obs:
        if not m["matched"]:
            timing_rows.append(
                {
                    "pipe": m["pipe"],
                    "leak_type": m["leak_type"],
                    "matched": False,
                    "change_error_hours": None,
                    "evidence_lag_from_change_hours": None,
                    "evidence_through_minus_onset_hours": None,
                }
            )
            continue
        # Recover candidate for evidence fields
        L = onset_by_pipe[m["pipe"]]
        # Rematch single to get idx — use change_time string compare
        cj = None
        for j, c in enumerate(candidates):
            if str(timestamps[c.change_idx]).replace("T", " ") == m["change_time"]:
                cj = j
                break
        assert cj is not None
        c = candidates[cj]
        change_err = float(
            (timestamps[c.change_idx] - L.start) / np.timedelta64(1, "h")
        )
        evid_lag = float((c.evidence_through_idx - c.change_idx) * 5 / 60.0)
        evid_from_onset = float(
            (timestamps[c.evidence_through_idx] - L.start) / np.timedelta64(1, "h")
        )
        alarm_lag = float((c.alarm_idx - c.change_idx) * 5 / 60.0)
        timing_rows.append(
            {
                "pipe": m["pipe"],
                "leak_type": m["leak_type"],
                "matched": True,
                "true_onset": str(L.start).replace("T", " "),
                "estimated_change_time": m["change_time"],
                "change_error_hours": change_err,
                "alarm_minus_change_hours": alarm_lag,
                "evidence_lag_from_change_hours": evid_lag,
                "evidence_through_minus_onset_hours": evid_from_onset,
                "note": (
                    "change_error uses retrospective CUSUM change estimate; "
                    "evidence_through is interval-bound availability, not a live alert."
                ),
            }
        )

    return {
        "tolerance_label": None,  # filled by caller
        "pre_hours": pre_h,
        "post_hours": post_h,
        "overall": summarize(obs_n, null_all, len(onsets)),
        "abrupt": summarize(obs_abr, null_abr, n_abr),
        "incipient": summarize(obs_inc, null_inc, n_inc),
        "observed_median_abs_change_error_hours": med_abs_err(obs),
        "observed_median_abs_change_error_abrupt": med_abs_err(obs, "abrupt"),
        "observed_median_abs_change_error_incipient": med_abs_err(obs, "incipient"),
        "per_onset_timing": timing_rows,
        "null_match_counts_all": null_all,
    }


def decide(results: list[dict], coverage_prereg: float) -> dict:
    """Close approach if nulls show no temporal ID beyond density at ±6h and ±24h."""
    # Decision uses both already-reported tolerances; neither is chosen post-hoc as headline.
    signals = []
    for r in results:
        frac = r["overall"]["fraction_shifts_ge_observed"]
        obs = r["overall"]["observed_matches"]
        med = r["overall"]["null_match_median"]
        # "Beyond density" would require observed matches clearly above typical null
        beyond = obs > med and frac <= 0.10
        signals.append(
            {
                "tolerance": r["tolerance_label"],
                "observed": obs,
                "null_median": med,
                "fraction_ge_obs": frac,
                "suggests_beyond_density": beyond,
            }
        )
    any_beyond = any(s["suggests_beyond_density"] for s in signals)
    if not any_beyond:
        verdict = "unsuccessful"
        conclusion = (
            "This experiment does **not** supply evidence of useful temporal "
            "identification beyond its candidate density. At both already-reported "
            "±6 h and ±24 h tolerances, circularly shifted candidates match as many "
            "(or nearly as many) DIAG onsets as the unshifted list under identical "
            "one-to-one rules. Combined with near-complete timeline coverage under the "
            "broad pre-registered window, the frozen operating point is closed as "
            "**unsuccessful** for retrospective change screening aimed at timed onset "
            "identification. Do not productize; do not treat RESULTS recall as validated "
            "leak detection."
        )
    else:
        verdict = "limited_signal"
        conclusion = (
            "Limited temporal association appears above the density null at least at "
            "one disclosed tolerance, but this is **not** validated leak detection. "
            "Any follow-up requires independent evaluation (new holdout protocol, "
            "pre-registered metrics) before productization. Do not deploy as alerting."
        )
    return {
        "verdict": verdict,
        "signals": signals,
        "preregistered_coverage_fraction_for_context": coverage_prereg,
        "conclusion": conclusion,
        "limitations": [
            "Only five DIAG onsets (3 abrupt, 2 incipient); descriptive counts only.",
            "Daily circular shifts (1–89 d) heavily overlap in structure; they are "
            "dependent probes of the same candidate pattern, not independent experiments.",
            "Null preserves clustering and density by design; it tests timing association "
            "against a density-matched alternative, not hydraulic truth.",
            "Frozen method/settings/matching unchanged; no post-hoc tolerance selection "
            "for the decision headline.",
        ],
    }


def render(summary: dict) -> str:
    lines = [
        "# Decision report — retrospective pairwise residual screening",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Frozen detector, candidates, matching rules, and settings are **unchanged**. "
        "No new algorithm, merge rule, threshold, UI, or deployment.",
        "",
        "Pre-registered Phase-2 headline remains in `outputs/RESULTS.md`. "
        "Matching semantics and chance audit remain in `outputs/AUDIT.md`.",
        "",
        "## Scope of this decision",
        "",
        "Question: does the frozen experiment show **useful temporal identification** "
        "beyond what its **candidate density** would produce by chance?",
        "",
        "Method: existing circular-shift null (preserve relative candidate gaps; "
        "shift within DIAG post-training analysis bounds; identical one-to-one matching).",
        "",
        "Tolerances: **±6 h** and **±24 h** only — already reported in the evaluation "
        "audit. Neither is selected after seeing these nulls; both are reported.",
        "",
        "## Null procedure notes",
        "",
        f"- Valid shifts: **{summary['n_valid_shifts']}** daily offsets "
        f"({summary['shift_day_min']}–{summary['shift_day_max']} days).",
        "- Shifts **overlap** (same pattern, sliding phase). Treat the set as a "
        "**descriptive ensemble**, not as independent trials or a formal p-value.",
        "- Five DIAG events total — do **not** claim strong statistical confidence.",
        "",
        "## Results by tolerance",
        "",
    ]
    for r in summary["null_by_tolerance"]:
        o, a, i = r["overall"], r["abrupt"], r["incipient"]
        lines += [
            f"### {r['tolerance_label']}",
            "",
            "| Slice | Observed matches | Null median (min–max) | "
            "Fraction of shifts ≥ observed |",
            "|-------|------------------|------------------------|----------------------------------|",
            f"| All ({o['n_events']} onsets) | {o['observed_matches']} | "
            f"{o['null_match_median']:.0f} ({o['null_match_min']}–{o['null_match_max']}) | "
            f"{o['fraction_shifts_ge_observed']:.2f} |",
            f"| Abrupt ({a['n_events']}) | {a['observed_matches']} | "
            f"{a['null_match_median']:.0f} ({a['null_match_min']}–{a['null_match_max']}) | "
            f"{a['fraction_shifts_ge_observed']:.2f} |",
            f"| Incipient ({i['n_events']}) | {i['observed_matches']} | "
            f"{i['null_match_median']:.0f} ({i['null_match_min']}–{i['null_match_max']}) | "
            f"{i['fraction_shifts_ge_observed']:.2f} |",
            "",
            f"Observed median |change-time error| (h): overall "
            f"{r['observed_median_abs_change_error_hours']}, "
            f"abrupt {r['observed_median_abs_change_error_abrupt']}, "
            f"incipient {r['observed_median_abs_change_error_incipient']}.",
            "",
        ]

    lines += [
        "## Estimated change time vs evidence available through",
        "",
        r"Retrospective **estimated change time** (\(\hat t_c\)) is the CUSUM last-zero "
        "before alarm. **Evidence available through** is the later bound used for "
        "candidate duration (next candidate or interval end) — *not* a real-time alert "
        "timestamp and *not* used for matching.",
        "",
        r"| Pipe | Type | Tolerance context | \(\hat t_c - t_0\) (h) | "
        "Alarm−change (h) | Evidence−change (h) | Evidence−onset (h) |",
        "|------|------|-------------------|------------------------|"
        "-------------------|---------------------|--------------------|",
    ]
    # Timing table from ±24 h observed matches (same candidates; errors only defined if matched)
    # Use ±6 rows where matched else show from the wider disclosed tolerance for description.
    timing_6 = next(r for r in summary["null_by_tolerance"] if r["tolerance_label"] == "±6 h")
    timing_24 = next(r for r in summary["null_by_tolerance"] if r["tolerance_label"] == "±24 h")
    # Prefer listing each onset once with both match flags
    pipes_order = []
    for row in timing_24["per_onset_timing"]:
        pipes_order.append(row["pipe"])
    t6_by = {r["pipe"]: r for r in timing_6["per_onset_timing"]}
    t24_by = {r["pipe"]: r for r in timing_24["per_onset_timing"]}
    for pipe in pipes_order:
        r24 = t24_by[pipe]
        r6 = t6_by[pipe]
        if r24["matched"]:
            src = r24
            ctx = "matched at ±24 h" + ("; also ±6 h" if r6["matched"] else "; not ±6 h")
        elif r6["matched"]:
            src = r6
            ctx = "matched at ±6 h only"
        else:
            lines.append(
                f"| {pipe} | {r24['leak_type']} | unmatched at ±6/±24 h | — | — | — | — |"
            )
            continue
        lines.append(
            f"| {src['pipe']} | {src['leak_type']} | {ctx} | "
            f"{src['change_error_hours']:.2f} | "
            f"{src['alarm_minus_change_hours']:.2f} | "
            f"{src['evidence_lag_from_change_hours']:.2f} | "
            f"{src['evidence_through_minus_onset_hours']:.2f} |"
        )

    d = summary["decision"]
    lines += [
        "",
        "## Decision signals (descriptive)",
        "",
        "| Tolerance | Observed | Null median | Frac. shifts ≥ obs | Beyond density? |",
        "|-----------|----------|-------------|--------------------|-----------------|",
    ]
    for s in d["signals"]:
        lines.append(
            f"| {s['tolerance']} | {s['observed']} | {s['null_median']:.0f} | "
            f"{s['fraction_ge_obs']:.2f} | "
            f"{'yes' if s['suggests_beyond_density'] else 'no'} |"
        )
    lines += [
        "",
        "### Limitations",
        "",
    ]
    for lim in d["limitations"]:
        lines.append(f"- {lim}")
    lines += [
        "",
        "## Conclusion",
        "",
        f"**Verdict: {d['verdict']}**",
        "",
        d["conclusion"],
        "",
        "## Product boundary",
        "",
        "Ripple’s deployed investigation workspace remains without a validated automatic "
        "leak detector. This research approach is closed for productization on the frozen "
        "operating point. No UI/API work follows from this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
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
    analysis_start = start_i + settings["train_days"] * STEPS_PER_DAY
    analysis_end = end_i
    onsets = onsets_in_period(leakages, DIAG)

    # Coverage from prior audit (context only)
    audit = json.loads((OUT / "audit_summary.json").read_text())
    coverage = float(audit["coverage"]["fraction"])

    null_results = []
    for tol in TOLERANCES:
        r = null_at_tolerance(
            bundle.timestamps,
            cands,
            onsets,
            leakages,
            analysis_start,
            analysis_end,
            tol["pre_hours"],
            tol["post_hours"],
        )
        r["tolerance_label"] = tol["label"]
        null_results.append(r)

    decision = decide(null_results, coverage)
    summary = {
        "generated_at": iso_now(),
        "frozen_settings": settings,
        "n_diag_candidates": len(cands),
        "n_valid_shifts": len(NULL_SHIFT_DAYS),
        "shift_day_min": min(NULL_SHIFT_DAYS),
        "shift_day_max": max(NULL_SHIFT_DAYS),
        "shift_dependence_note": (
            "Circular daily shifts share the same candidate spacing pattern; "
            "overlapping phases are not independent experiments."
        ),
        "null_by_tolerance": null_results,
        "decision": decision,
        "preserved": {
            "detector": "frozen PairwiseOLS + offline CUSUM",
            "candidates": "raw DIAG candidate list unchanged",
            "matching_rules": "one-to-one earliest change-time; DESIGN.md windows",
            "settings": "outputs/frozen_settings.json",
        },
    }
    # Drop bulky per-shift arrays from markdown companion? keep in json for transparency
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decision_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "DECISION.md").write_text(render(summary) + "\n")
    print(decision["verdict"])
    print(decision["conclusion"])
    print(f"Wrote {OUT / 'DECISION.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
