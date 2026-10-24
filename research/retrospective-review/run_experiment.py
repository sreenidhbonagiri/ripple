#!/usr/bin/env python3
"""2018 DEV→DIAG retrospective pairwise residual screening (local only)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate import (  # noqa: E402
    DEV,
    DIAG,
    iso_now,
    match_candidates,
    onsets_in_period,
    period_indices,
    period_metrics,
    select_settings,
)
from io_data import DEFAULT_RAW, load_context, load_leakages, load_pressures  # noqa: E402
from method import run_interval  # noqa: E402

OUT = ROOT / "outputs"
GRID_TRAIN = [7, 14]
GRID_H = [4.0, 6.0, 8.0]
GRID_MIN_SEG = [12.0, 24.0]
CUSUM_K = 0.5


def _run_period(pressures, timestamps, period, settings, leakages):
    start_i, end_i = period_indices(timestamps, period)
    t0 = time.perf_counter()
    _model, cands, scores = run_interval(
        pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=settings["train_days"],
        cusum_k=settings["cusum_k"],
        cusum_h=settings["cusum_h"],
        min_segment_hours=settings["min_segment_hours"],
    )
    runtime = time.perf_counter() - t0
    onsets = onsets_in_period(leakages, period)
    matches, used = match_candidates(timestamps, cands, onsets, leakages)
    metrics = period_metrics(
        timestamps,
        period,
        cands,
        matches,
        used,
        settings=settings,
        runtime_s=runtime,
        n_rows=end_i - start_i,
        n_sensors=pressures.shape[1],
    )
    return metrics, cands, scores, start_i, end_i


def ordinary_controls(timestamps, pressures_unused, context, candidates, period, week_steps=2016):
    """Fraction of large pump/tank prior-week moves near a candidate (±6h)."""
    start_i, end_i = period_indices(timestamps, period)
    pump_j = context.flow_ids.index("PUMP_1")
    t1_j = context.level_ids.index("T1")
    cand_times = {timestamps[c.change_idx] for c in candidates}
    hits = 0
    total = 0
    for i in range(max(start_i, week_steps), end_i, 12):
        d_pump = float(context.flows[i, pump_j] - context.flows[i - week_steps, pump_j])
        d_t1 = float(context.levels[i, t1_j] - context.levels[i - week_steps, t1_j])
        if abs(d_pump) < 15 and abs(d_t1) < 0.4:
            continue
        total += 1
        t = timestamps[i]
        near = any(
            abs(float((t - ct) / np.timedelta64(1, "h"))) <= 6.0 for ct in cand_times
        )
        if near:
            hits += 1
        if total >= 40:
            break
    return {
        "sampled_large_context_moves": total,
        "within_6h_of_candidate": hits,
        "fraction": (hits / total) if total else None,
    }


def make_plots(timestamps, scores, analysis_offset, period_name, cands, matches, out_dir: Path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"plot skip: {exc}")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    # Aggregate score strip
    fig, ax = plt.subplots(figsize=(11, 3.2))
    x = np.arange(len(scores))
    ax.plot(x, scores, lw=0.6, color="#1a6b7a")
    for c in cands:
        loc = c.change_idx - analysis_offset
        if 0 <= loc < len(scores):
            ax.axvline(loc, color="#c45c26", alpha=0.5, lw=0.8)
    ax.set_title(f"{period_name}: aggregate pairwise residual magnitude S(t)")
    ax.set_ylabel("S(t)")
    ax.set_xlabel("steps after training prefix")
    fig.tight_layout()
    p = out_dir / f"{period_name.lower()}_score.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(ROOT)))

    # Per matched / missed table figure is text; plot first few match windows if any
    for m in matches[:4]:
        if not m["matched"] or not m["change_time"]:
            continue
        # small context already in score plot
    return paths


def render_report(summary: dict) -> str:
    fr = summary["frozen"]
    d = summary["DIAG"]
    lines = [
        "# Retrospective pressure-pattern review — Phase 2 report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Deployed Ripple remains an investigation workspace **without** a validated automatic",
        "leak detector. Candidates below are **not** confirmed leaks and are **not** live alerts.",
        "",
        summary["holdout_honesty"],
        "",
        "## Method (see DESIGN.md)",
        "",
        "Independent LILA-inspired pairwise OLS residuals + offline CUSUM on Frobenius-like",
        "aggregate score. No GPL code copied. No leak-location-based sensor/pair selection.",
        "",
        f"Frozen settings (DEV→lock): `{fr}`",
        f"DEV unmatched/wk ≤ 3.0 gate met: **{summary.get('gate_met')}**",
        "",
        "Unmatched candidates are **not** automatic false positives (background leaks / ops).",
        "Estimated change times are retrospective within the interval — not real-time alerts.",
        "",
        "## DEV selection summary",
        "",
    ]
    for row in summary["DEV_grid_slim"]:
        lines.append(
            f"- train={row['settings']['train_days']}d h={row['settings']['cusum_h']} "
            f"min_seg={row['settings']['min_segment_hours']}h → "
            f"abrupt_recall={row['abrupt_recall']:.2f} unmatched/wk={row['unmatched_per_week']:.2f}"
        )
    lines += [
        "",
        "## DIAG (frozen)",
        "",
        f"- Abrupt recall: **{d['abrupt_recall']:.2f}** ({d['n_abrupt']} onsets)",
        f"- Incipient recall: **{d['incipient_recall']:.2f}** ({d['n_incipient']} onsets)",
        f"- Unmatched candidates/week: **{d['unmatched_per_week']:.2f}**",
        f"- Median candidate duration (h): {d['median_candidate_duration_hours']}",
        f"- Duplicate unmatched within 24h: {d['duplicate_unmatched_within_24h']}",
        f"- Change-time error hours: {d['change_time_error_hours']}",
        f"- Runtime: {d['runtime_seconds']:.1f}s · volume row×sensor={d['volume_row_x_sensor']}",
        f"- Ordinary controls (large ΔPUMP_1/ΔT1 near candidate): {summary['DIAG_ordinary_controls']}",
        "",
        "### DIAG matches / misses",
        "",
    ]
    for m in d["matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"change={m['change_time']} err_h={m['error_hours']}"
        )
    lines += [
        "",
        "## Limitations",
        "",
        "- Training prefix is chronological, not verified leak-free (unlike LILA’s manual period).",
        "- All-pairs aggregation does not disaggregate overlapping leaks.",
        "- No hydraulic localization; MAS not claimed.",
        "- Not BattLeDIM economic scoring; not paper reproduction.",
        "- 2019 not evaluated (already historically examined).",
        "",
        "## Path to product (if go)",
        "",
        "select historical interval → review candidate changes → inspect sensor/flow/tank",
        "evidence in the existing investigation workspace → save investigation metadata.",
        "",
        "## Recommendation",
        "",
        summary["recommendation"],
        "",
    ]
    return "\n".join(lines)


def recommend(dev: dict, diag: dict, *, gate_met: bool) -> str:
    if not gate_met:
        return (
            "**No-go**: no DEV setting met the pre-registered unmatched/wk ≤ 3.0 gate "
            f"(best DEV unmatched/wk={dev['unmatched_per_week']:.2f}). "
            f"DIAG under fallback freeze: abrupt_recall={diag['abrupt_recall']:.2f}, "
            f"unmatched/wk={diag['unmatched_per_week']:.2f}. "
            "Do not build UI/API on this operating point; revisit with a new pre-registered method "
            "(e.g. pair subsetting without leak labels, recalibration, or stronger ordinary-ops filters)."
        )
    if diag["abrupt_recall"] >= 0.5 and diag["unmatched_per_week"] <= 4.0:
        return (
            "**Conditional go** for a *research* retrospective-review UI: DIAG abrupt recall "
            f"{diag['abrupt_recall']:.2f} with unmatched/wk {diag['unmatched_per_week']:.2f}. "
            "Do not market as live leak alerting; require human review and clear candidate language."
        )
    if diag["abrupt_recall"] <= 0.0:
        return (
            "**No-go** for productizing this operating point: DIAG abrupt recall is 0. "
            "Keep as documentation of a negative/feasibility result; do not build UI on these settings."
        )
    return (
        f"**No-go / revisit**: DIAG abrupt_recall={diag['abrupt_recall']:.2f}, "
        f"unmatched/wk={diag['unmatched_per_week']:.2f}, incipient_recall={diag['incipient_recall']:.2f}. "
        "Insufficient for a clear product path without a new pre-registered method."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading 2018 pressures…", flush=True)
    bundle = load_pressures(args.raw_dir / "2018_SCADA_Pressures.csv")
    context = load_context(args.raw_dir)
    leakages = load_leakages()
    assert np.array_equal(bundle.timestamps, context.timestamps)

    grid = []
    print("DEV grid…", flush=True)
    for train_days in GRID_TRAIN:
        for h in GRID_H:
            for min_seg in GRID_MIN_SEG:
                settings = {
                    "train_days": train_days,
                    "cusum_k": CUSUM_K,
                    "cusum_h": h,
                    "min_segment_hours": min_seg,
                }
                metrics, _, _, _, _ = _run_period(
                    bundle.pressures, bundle.timestamps, DEV, settings, leakages
                )
                grid.append(metrics)
                print(
                    f"  {settings} abrupt={metrics['abrupt_recall']:.2f} "
                    f"unmatched/wk={metrics['unmatched_per_week']:.2f}",
                    flush=True,
                )

    chosen, gate_met = select_settings(grid)
    frozen = {
        "frozen_at": iso_now(),
        "settings": chosen["settings"],
        "gate_met": gate_met,
        "unmatched_cap": 3.0,
        "selection_rule": (
            "max abrupt recall among unmatched/wk<=3 on DEV; "
            "ties: overall recall, then unmatched/wk, then larger h; "
            "if none eligible, freeze best-of-pool with gate_met=false"
        ),
        "dev_snapshot": {
            k: chosen[k]
            for k in (
                "abrupt_recall",
                "onset_recall",
                "unmatched_per_week",
                "n_candidates",
                "n_abrupt",
                "n_incipient",
            )
        },
    }
    freeze_path = args.out_dir / "frozen_settings.json"
    freeze_path.write_text(json.dumps(frozen, indent=2) + "\n")
    print(f"Froze {frozen['settings']} gate_met={gate_met}", flush=True)

    print("DIAG frozen…", flush=True)
    diag, diag_cands, diag_scores, d0, d1 = _run_period(
        bundle.pressures, bundle.timestamps, DIAG, chosen["settings"], leakages
    )
    train_steps = chosen["settings"]["train_days"] * 288
    analysis_offset = d0 + train_steps
    controls = ordinary_controls(
        bundle.timestamps, bundle.pressures, context, diag_cands, DIAG
    )
    plot_paths = make_plots(
        bundle.timestamps,
        diag_scores,
        analysis_offset,
        "DIAG",
        diag_cands,
        diag["matches"],
        args.out_dir / "plots",
    )
    # also DEV plot for frozen settings
    dev_m, dev_cands, dev_scores, v0, v1 = _run_period(
        bundle.pressures, bundle.timestamps, DEV, chosen["settings"], leakages
    )
    plot_paths += make_plots(
        bundle.timestamps,
        dev_scores,
        v0 + train_steps,
        "DEV",
        dev_cands,
        dev_m["matches"],
        args.out_dir / "plots",
    )

    slim_grid = []
    for g in grid:
        slim_grid.append(
            {
                "settings": g["settings"],
                "abrupt_recall": g["abrupt_recall"],
                "onset_recall": g["onset_recall"],
                "unmatched_per_week": g["unmatched_per_week"],
                "n_candidates": g["n_candidates"],
            }
        )

    summary = {
        "generated_at": iso_now(),
        "holdout_honesty": (
            "2019 is not evaluated; it has already been examined historically and is not a "
            "new blind holdout. 2018 labels are for documented DEV/DIAG matching only."
        ),
        "method": "PairwiseOLS + offline CUSUM (LILA-inspired independent implementation)",
        "frozen": frozen["settings"],
        "gate_met": gate_met,
        "DEV_selected": {
            k: v for k, v in chosen.items() if k != "matches" and k != "missed"
        },
        "DEV_grid_slim": slim_grid,
        "DIAG": diag,
        "DIAG_ordinary_controls": controls,
        "plots": plot_paths,
        "recommendation": recommend(chosen, diag, gate_met=gate_met),
    }
    # shrink DIAG matches already included; drop huge arrays
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out_dir / "RESULTS.md").write_text(render_report(summary) + "\n")
    print(summary["recommendation"], flush=True)
    print(f"Wrote {args.out_dir / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
