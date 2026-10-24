#!/usr/bin/env python3
"""Run the locked 2018 DEV→DIAG pressure week-residual experiment.

Does not touch production APIs, UI, or Tiger. Does not evaluate 2019 settings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate import (  # noqa: E402
    DEV,
    DIAG,
    compute_metrics,
    iso_now,
    match_episodes,
    onsets_in_period,
    period_slice,
    select_baseline_tau,
    select_residual_tau,
    warm_prefix_report,
)
from detector import (  # noqa: E402
    CLEAR_M,
    CONFIRM_K,
    STEPS_PER_WEEK,
    build_episodes,
    context_deltas_at,
    raw_drop_scores,
    week_residual_scores,
)
from io_scada import DEFAULT_RAW, load_2018_bundle, load_leakages  # noqa: E402

OUT = ROOT / "outputs"

RESIDUAL_GRID = [0.25, 0.35, 0.50, 0.75, 1.00, 1.25, 1.50]
BASELINE_GRID = [0.15, 0.25, 0.35, 0.50, 0.75, 1.00, 1.10, 1.25, 1.50]


def _metrics_for(
    bundle,
    series,
    period,
    tau,
    leakages,
    method: str,
):
    start_i, end_i = period_slice(bundle, period)
    episodes = build_episodes(series, tau, CONFIRM_K, CLEAR_M, start_i, end_i)
    onsets = onsets_in_period(leakages, period)
    matches, used = match_episodes(
        bundle, episodes, onsets, series, leakages, bundle.pressure_ids
    )
    for m in matches:
        if m.matched and m.notify is not None:
            # recover notify idx
            ts = np.datetime64(m.notify.replace(" ", "T"))
            idx = int(np.where(bundle.timestamps == ts)[0][0])
            m.context_at_notify = context_deltas_at(bundle, idx)
    return compute_metrics(bundle, period, method, tau, episodes, matches, used), episodes


def _slim(m) -> dict:
    d = {
        "period": m.period,
        "method": m.method,
        "tau": m.tau,
        "n_onsets": m.n_onsets,
        "n_abrupt_onsets": m.n_abrupt_onsets,
        "onset_recall": m.onset_recall,
        "abrupt_onset_recall": m.abrupt_onset_recall,
        "matched_delays_hours": m.matched_delays_hours,
        "n_episodes": m.n_episodes,
        "n_matched_episodes": m.n_matched_episodes,
        "n_unmatched_episodes": m.n_unmatched_episodes,
        "unmatched_episodes_per_week": m.unmatched_episodes_per_week,
        "time_in_alarm_fraction": m.time_in_alarm_fraction,
        "longest_episode_hours": m.longest_episode_hours,
        "period_weeks": m.period_weeks,
        "matches": m.matches,
    }
    return d


def ordinary_operating_spotchecks(bundle, series, tau, leakages) -> list[dict]:
    """Sample large |ΔPUMP_1| / |ΔT1| vs prior week on DEV; note whether score nears τ."""
    start_i, end_i = period_slice(bundle, DEV)
    # Skip the first scorable day — early lookback compares against New Year operations.
    start_i = max(start_i, STEPS_PER_WEEK + 288)
    pump_j = bundle.flow_ids.index("PUMP_1")
    t1_j = bundle.level_ids.index("T1")
    candidates = []
    for i in range(start_i, end_i, 12):
        if series.missing_history[i]:
            continue
        d_pump = float(bundle.flows[i, pump_j] - bundle.flows[i - STEPS_PER_WEEK, pump_j])
        d_t1 = float(bundle.levels[i, t1_j] - bundle.levels[i - STEPS_PER_WEEK, t1_j])
        if abs(d_pump) < 15 and abs(d_t1) < 0.4:
            continue
        window = series.score[i : min(i + 12, end_i)]
        miss = series.missing_history[i : min(i + 12, end_i)]
        valid = window[~miss]
        max_s = float(np.nanmax(valid)) if valid.size else None
        candidates.append(
            {
                "timestamp": str(bundle.timestamps[i]).replace("T", " "),
                "delta_PUMP_1": d_pump,
                "delta_T1": d_t1,
                "score": None if series.missing_history[i] else float(series.score[i]),
                "max_score_next_hour": max_s,
                "would_exceed_tau_next_hour": bool(max_s is not None and max_s >= tau),
                "open_leaks": open_leak_helper(leakages, bundle.timestamps[i]),
                "_rank": abs(d_pump) + 40.0 * abs(d_t1),
            }
        )
    candidates.sort(key=lambda r: -r["_rank"])
    rows = []
    for c in candidates[:12]:
        c.pop("_rank", None)
        rows.append(c)
    return rows


def open_leak_helper(leakages, t):
    from io_scada import open_leak_count

    return open_leak_count(leakages, t)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = args.out_dir / "frozen_settings.json"
    summary_path = args.out_dir / "summary.json"
    report_path = args.out_dir / "RESULTS.md"

    print("Loading 2018 SCADA…", flush=True)
    bundle = load_2018_bundle(args.raw_dir)
    leakages = load_leakages()
    print(f"  timestamps={len(bundle.timestamps)} sensors={len(bundle.pressure_ids)}", flush=True)

    residual_series = week_residual_scores(bundle.pressures)
    baseline_series = raw_drop_scores(bundle.pressures)
    warm = warm_prefix_report(residual_series, STEPS_PER_WEEK)
    print(f"  warm_prefix={warm}", flush=True)
    if not warm["warm_all_missing"]:
        raise SystemExit("warm prefix stability check failed: expected all missing_history")

    # --- DEV selection ---
    print("DEV residual threshold grid…", flush=True)
    residual_dev_candidates = []
    for tau in RESIDUAL_GRID:
        m, _ = _metrics_for(bundle, residual_series, DEV, tau, leakages, "week_residual")
        residual_dev_candidates.append(m)
        print(
            f"  tau={tau:.2f} abrupt_recall={m.abrupt_onset_recall:.2f} "
            f"recall={m.onset_recall:.2f} unmatched/wk={m.unmatched_episodes_per_week:.2f} "
            f"tia={m.time_in_alarm_fraction:.3f}",
            flush=True,
        )
    chosen = select_residual_tau(residual_dev_candidates)
    print(
        f"Selected residual tau={chosen.tau} (abrupt_recall={chosen.abrupt_onset_recall:.3f}, "
        f"unmatched/wk={chosen.unmatched_episodes_per_week:.3f})",
        flush=True,
    )

    print("DEV baseline threshold grid (burden parity)…", flush=True)
    baseline_dev_candidates = []
    for tau in BASELINE_GRID:
        m, _ = _metrics_for(bundle, baseline_series, DEV, tau, leakages, "raw_30m_drop")
        baseline_dev_candidates.append(m)
        print(
            f"  tau_b={tau:.2f} abrupt_recall={m.abrupt_onset_recall:.2f} "
            f"unmatched/wk={m.unmatched_episodes_per_week:.2f} tia={m.time_in_alarm_fraction:.3f}",
            flush=True,
        )
    base_chosen = select_baseline_tau(baseline_dev_candidates, chosen.unmatched_episodes_per_week)
    print(
        f"Selected baseline tau_b={base_chosen.tau} "
        f"(unmatched/wk={base_chosen.unmatched_episodes_per_week:.3f} vs residual "
        f"{chosen.unmatched_episodes_per_week:.3f})",
        flush=True,
    )

    frozen = {
        "frozen_at": iso_now(),
        "confirm_k": CONFIRM_K,
        "clear_m": CLEAR_M,
        "match_horizon_hours": 24,
        "residual": {
            "method": "week_residual",
            "tau": chosen.tau,
            "selection_rule": "max abrupt recall among unmatched/wk <= 2.0 on DEV",
            "dev_metrics": _slim(chosen),
        },
        "baseline": {
            "method": "raw_30m_drop",
            "tau": base_chosen.tau,
            "selection_rule": "closest unmatched/wk to residual on DEV",
            "dev_metrics": _slim(base_chosen),
        },
        "warm_prefix": warm,
        "note": "Settings frozen before DIAG. Do not re-tune on DIAG or 2019.",
    }
    freeze_path.write_text(json.dumps(frozen, indent=2) + "\n")
    print(f"Wrote {freeze_path}", flush=True)

    # --- DIAG with frozen settings only ---
    if not freeze_path.exists():
        raise SystemExit("refusing DIAG without frozen_settings.json")

    print("DIAG with frozen settings…", flush=True)
    resid_diag, _ = _metrics_for(
        bundle, residual_series, DIAG, chosen.tau, leakages, "week_residual"
    )
    base_diag, _ = _metrics_for(
        bundle, baseline_series, DIAG, base_chosen.tau, leakages, "raw_30m_drop"
    )

    spotchecks = ordinary_operating_spotchecks(
        bundle, residual_series, chosen.tau, leakages
    )

    # Causality smoke: mutate far-future pressures; score at a mid DEV index must be unchanged.
    probe_i = period_slice(bundle, DEV)[0] + 5000
    before = float(residual_series.score[probe_i])
    mutated = bundle.pressures.copy()
    mutated[-100:] = mutated[-100:] + 50.0
    after_series = week_residual_scores(mutated)
    after = float(after_series.score[probe_i])
    causality_ok = before == after and np.isfinite(before)

    summary = {
        "generated_at": iso_now(),
        "design": "research/pressure_week_residual/DESIGN.md",
        "holdout_honesty": (
            "Previously examined 2018/2019 cases are development/diagnostic, not a blind holdout. "
            "2019 is not evaluated for new settings in this run."
        ),
        "frozen_settings_path": str(freeze_path.relative_to(ROOT.parent.parent)),
        "causality_probe": {
            "probe_idx": probe_i,
            "score_unchanged_after_future_mutation": causality_ok,
            "score": before,
        },
        "warm_prefix": warm,
        "DEV": {
            "residual": _slim(chosen),
            "baseline": _slim(base_chosen),
            "residual_grid": [_slim(m) for m in residual_dev_candidates],
            "baseline_grid": [_slim(m) for m in baseline_dev_candidates],
        },
        "DIAG": {
            "residual": _slim(resid_diag),
            "baseline": _slim(base_diag),
        },
        "ordinary_operating_spotchecks_DEV": spotchecks,
        "recommendation_inputs_only": True,
    }
    # Trim grid match detail to keep artifact small
    for block in (summary["DEV"]["residual_grid"], summary["DEV"]["baseline_grid"]):
        for row in block:
            row.pop("matches", None)

    summary_path.write_text(json.dumps(summary, indent=2, default=_json_default) + "\n")
    report_path.write_text(render_report(summary) + "\n")
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {report_path}", flush=True)
    print(
        f"DIAG residual abrupt_recall={resid_diag.abrupt_onset_recall:.3f} "
        f"unmatched/wk={resid_diag.unmatched_episodes_per_week:.3f} | "
        f"baseline abrupt_recall={base_diag.abrupt_onset_recall:.3f} "
        f"unmatched/wk={base_diag.unmatched_episodes_per_week:.3f}",
        flush=True,
    )
    return 0


def _json_default(obj):
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def render_report(summary: dict) -> str:
    fr = summary["DEV"]["residual"]
    fb = summary["DEV"]["baseline"]
    dr = summary["DIAG"]["residual"]
    db = summary["DIAG"]["baseline"]
    lines = [
        "# Pressure week-residual experiment — 2018 results",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        summary["holdout_honesty"],
        "",
        "## Frozen settings (selected on DEV, then locked)",
        "",
        f"- Residual τ = **{fr['tau']}** m (week residual), confirm_k=3, clear_m=6",
        f"- Baseline τ_b = **{fb['tau']}** m (30‑minute raw drop), same episode policy",
        f"- Causality probe (future mutation): "
        f"{summary['causality_probe']['score_unchanged_after_future_mutation']}",
        f"- Warm prefix all missing_history: {summary['warm_prefix']['warm_all_missing']}; "
        f"post-warm missing fraction={summary['warm_prefix']['post_warm_missing_fraction']}",
        "",
        "## DEV (setting selection)",
        "",
        "| Method | τ | Onset recall | Abrupt recall | Unmatched/wk | Time in alarm | Longest ep (h) |",
        "|--------|---|--------------|---------------|--------------|---------------|----------------|",
        _row("week_residual", fr),
        _row("raw_30m_drop", fb),
        "",
        "## DIAG (frozen only; not used for tuning)",
        "",
        "| Method | τ | Onset recall | Abrupt recall | Unmatched/wk | Time in alarm | Longest ep (h) |",
        "|--------|---|--------------|---------------|--------------|---------------|----------------|",
        _row("week_residual", dr),
        _row("raw_30m_drop", db),
        "",
        "### DIAG onset match detail (residual)",
        "",
    ]
    for m in dr["matches"]:
        status = "HIT" if m["matched"] else "MISS"
        delay = "—" if m["delay_hours"] is None else f"{m['delay_hours']:.2f}h"
        lines.append(
            f"- {status} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"→ notify {m['notify']} delay {delay} strong={m['strongest_sensor']} "
            f"open_leaks_at_notify={m['open_leaks_at_notify']}"
        )
    lines += [
        "",
        "### DIAG onset match detail (baseline)",
        "",
    ]
    for m in db["matches"]:
        status = "HIT" if m["matched"] else "MISS"
        delay = "—" if m["delay_hours"] is None else f"{m['delay_hours']:.2f}h"
        lines.append(
            f"- {status} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"→ notify {m['notify']} delay {delay} strong={m['strongest_sensor']}"
        )
    lines += [
        "",
        "## Ordinary operating spotchecks (DEV, context only)",
        "",
        "Large prior-week ΔPUMP_1 or ΔT1 samples — score may rise without implying a new onset.",
        "",
    ]
    for s in summary["ordinary_operating_spotchecks_DEV"]:
        lines.append(
            f"- {s['timestamp']}: ΔPUMP_1={s['delta_PUMP_1']:.2f}, ΔT1={s['delta_T1']:.3f}, "
            f"score={s['score']}, exceed_tau_next_h={s['would_exceed_tau_next_hour']}, "
            f"open_leaks={s['open_leaks']}"
        )
    lines += [
        "",
        "## Comparison & recommendation",
        "",
        _recommendation(fr, fb, dr, db),
        "",
        "Flow/pump/tank were **not** used as vetoes. AMR was not used. "
        "Do not promote from a single attractive match. 2019 not evaluated here.",
        "",
    ]
    return "\n".join(lines)


def _row(name: str, m: dict) -> str:
    return (
        f"| {name} | {m['tau']:.2f} | {m['onset_recall']:.2f} | {m['abrupt_onset_recall']:.2f} | "
        f"{m['unmatched_episodes_per_week']:.2f} | {m['time_in_alarm_fraction']:.3f} | "
        f"{m['longest_episode_hours']:.1f} |"
    )


def _recommendation(fr, fb, dr, db) -> str:
    # Prefer DIAG evidence. DEV may look better on a few abrupt hits — do not promote from that.
    if dr["abrupt_onset_recall"] <= 0.0 and db["abrupt_onset_recall"] <= 0.0:
        return (
            f"On frozen DIAG, both week-residual (τ={dr['tau']}) and the burden-targeted raw 30‑minute "
            f"baseline (τ_b={db['tau']}) achieve **0 abrupt onset recall** "
            f"(unmatched/wk {dr['unmatched_episodes_per_week']:.2f} vs {db['unmatched_episodes_per_week']:.2f}; "
            f"DEV had selected residual unmatched/wk={fr['unmatched_episodes_per_week']:.2f} vs baseline "
            f"{fb['unmatched_episodes_per_week']:.2f}). DEV abrupt hits (e.g. residual "
            f"{fr['abrupt_onset_recall']:.2f}) did not transfer. "
            f"**Recommendation:** do not promote this week-residual detector; the hypothesis is "
            f"unsupported at the pre-registered operating point. Do not add AMR or veto gates until a "
            f"new pre-registered score shows DIAG gains beyond the raw-drop baseline."
        )
    burden_gap = abs(dr["unmatched_episodes_per_week"] - db["unmatched_episodes_per_week"])
    better_abrupt = dr["abrupt_onset_recall"] > db["abrupt_onset_recall"] + 1e-9
    if better_abrupt and burden_gap <= 1.0:
        return (
            f"On DIAG, week-residual (τ={dr['tau']}) improves abrupt onset recall "
            f"({dr['abrupt_onset_recall']:.2f} vs {db['abrupt_onset_recall']:.2f}) with unmatched/wk "
            f"{dr['unmatched_episodes_per_week']:.2f} vs {db['unmatched_episodes_per_week']:.2f}. "
            f"**Recommendation:** keep as a research candidate only; do not deploy. Re-check burden "
            f"parity before any further feature work."
        )
    return (
        f"DIAG residual abrupt_recall={dr['abrupt_onset_recall']:.2f} unmatched/wk="
        f"{dr['unmatched_episodes_per_week']:.2f}; baseline {db['abrupt_onset_recall']:.2f}, "
        f"{db['unmatched_episodes_per_week']:.2f}/wk. "
        f"**Recommendation:** no promotion; inconclusive or unsupported relative to the raw-drop "
        f"baseline — not based on one DEV example."
    )


if __name__ == "__main__":
    raise SystemExit(main())
