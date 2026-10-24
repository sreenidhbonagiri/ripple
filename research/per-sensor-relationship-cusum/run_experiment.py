#!/usr/bin/env python3
"""2018 DEV→DIAG per-sensor relationship CUSUM vs global aggregation."""

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

from detector import run_all_targets, run_global_stream  # noqa: E402
from evaluate import (  # noqa: E402
    DEV,
    DIAG,
    iso_now,
    match_episodes,
    null_notification_comparison,
    onsets_in_period,
    period_indices,
    period_metrics,
    select_settings,
)
from io_data import DEFAULT_RAW, load_context, load_leakages, load_pressures  # noqa: E402
from residual import build_signals  # noqa: E402

OUT = ROOT / "outputs"
GRID_K = [3, 5]
GRID_H = [4.0, 6.0, 8.0]
GRID_RECOVER = [12.0, 24.0]
TRAIN_DAYS = 14
CUSUM_K = 0.5


def ordinary_controls(timestamps, context, episodes, period, week_steps=2016):
    start_i, end_i = period_indices(timestamps, period)
    pump_j = context.flow_ids.index("PUMP_1")
    t1_j = context.level_ids.index("T1")
    cand_times = {timestamps[ep.notify_idx] for ep in episodes}
    hits = 0
    total = 0
    for i in range(max(start_i, week_steps), end_i, 12):
        d_pump = float(context.flows[i, pump_j] - context.flows[i - week_steps, pump_j])
        d_t1 = float(context.levels[i, t1_j] - context.levels[i - week_steps, t1_j])
        if abs(d_pump) < 15 and abs(d_t1) < 0.4:
            continue
        total += 1
        t = timestamps[i]
        if any(abs(float((t - ct) / np.timedelta64(1, "h"))) <= 6.0 for ct in cand_times):
            hits += 1
        if total >= 40:
            break
    return {
        "sampled_large_context_moves": total,
        "within_6h_of_notification": hits,
        "fraction": (hits / total) if total else None,
    }


def run_per_sensor(pressures, sensor_ids, timestamps, period, settings, leakages):
    start_i, end_i = period_indices(timestamps, period)
    t0 = time.perf_counter()
    bundle = build_signals(
        pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=settings["train_days"],
        n_refs=settings["n_refs"],
    )
    episodes = run_all_targets(
        bundle.z,
        sensor_ids,
        bundle.target_models,
        analysis_offset=bundle.analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
    )
    runtime = time.perf_counter() - t0
    onsets = onsets_in_period(leakages, period)
    matches, used = match_episodes(timestamps, episodes, onsets, leakages)
    metrics = period_metrics(
        timestamps,
        period,
        episodes,
        matches,
        used,
        settings=settings,
        runtime_s=runtime,
        method="per_sensor",
    )
    return metrics, episodes, bundle


def run_global(pressures, timestamps, period, settings, leakages):
    start_i, end_i = period_indices(timestamps, period)
    t0 = time.perf_counter()
    # n_refs unused for signal but needed for build; use 3 as dummy for pair cache
    n_refs = settings.get("n_refs") or 3
    bundle = build_signals(
        pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=settings["train_days"],
        n_refs=int(n_refs),
    )
    episodes = run_global_stream(
        bundle.global_s,
        analysis_offset=bundle.analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
    )
    runtime = time.perf_counter() - t0
    onsets = onsets_in_period(leakages, period)
    matches, used = match_episodes(timestamps, episodes, onsets, leakages)
    gsettings = {
        "train_days": settings["train_days"],
        "cusum_k": settings["cusum_k"],
        "cusum_h": settings["cusum_h"],
        "recover_hours": settings["recover_hours"],
        "n_refs": None,
    }
    metrics = period_metrics(
        timestamps,
        period,
        episodes,
        matches,
        used,
        settings=gsettings,
        runtime_s=runtime,
        method="global",
    )
    return metrics, episodes, bundle


def make_event_plots(timestamps, bundle, episodes, matches, sensor_ids, out_dir: Path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"plot skip: {exc}")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for m in matches:
        fig, axes = plt.subplots(2, 1, figsize=(11, 5.5), sharex=False)
        onset = np.datetime64(m["onset"].replace(" ", "T"))
        # window around onset
        i0 = int(np.searchsorted(timestamps, onset - np.timedelta64(2, "D")))
        i1 = int(np.searchsorted(timestamps, onset + np.timedelta64(10, "D")))
        # map to analysis-relative for z
        off = bundle.analysis_offset
        a0 = max(0, i0 - off)
        a1 = max(0, i1 - off)
        a1 = min(a1, bundle.z.shape[0])
        ax = axes[0]
        # plot a few target z streams (ones that notified near event, else first 4)
        plotted = set()
        for ep in episodes:
            if abs(float((timestamps[ep.notify_idx] - onset) / np.timedelta64(1, "h"))) <= 24 * 10:
                if 0 <= ep.target_idx < bundle.z.shape[1]:
                    ax.plot(
                        bundle.z[a0:a1, ep.target_idx],
                        lw=0.8,
                        label=ep.stream_id,
                    )
                    plotted.add(ep.target_idx)
        if not plotted:
            for ti in range(min(4, bundle.z.shape[1])):
                ax.plot(bundle.z[a0:a1, ti], lw=0.7, alpha=0.8, label=sensor_ids[ti])
        ax.axvline(max(0, int(np.searchsorted(timestamps, onset) - off) - a0), color="#333", ls="--")
        if m["matched"] and m["notify_time"]:
            nt = np.datetime64(m["notify_time"].replace(" ", "T"))
            ax.axvline(
                max(0, int(np.searchsorted(timestamps, nt) - off) - a0),
                color="#c45c26",
                ls="-",
            )
        ax.set_title(f"{m['pipe']} ({m['leak_type']}) z_i near onset")
        ax.set_ylabel("z")
        ax.legend(loc="upper right", fontsize=7, ncol=2)

        ax2 = axes[1]
        ax2.plot(bundle.global_s[a0:a1], color="#1a6b7a", lw=0.8)
        ax2.axvline(max(0, int(np.searchsorted(timestamps, onset) - off) - a0), color="#333", ls="--")
        ax2.set_title("Global standardized S(t)")
        ax2.set_ylabel("S")
        fig.tight_layout()
        p = out_dir / f"event_{m['pipe']}.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(str(p.relative_to(ROOT)))
    return paths


def recommend(per_diag: dict, glob_diag: dict, null: dict, gate_met: bool) -> str:
    lines = []
    if not gate_met:
        lines.append(
            "DEV unmatched/week ≤ 3.0 gate **not** met for per-sensor method "
            f"(selected unmatched/wk={per_diag.get('dev_unmatched_note', 'see freeze')})."
        )
    abr = per_diag["abrupt_recall"]
    gabr = glob_diag["abrupt_recall"]
    um = per_diag["unmatched_per_week"]
    gum = glob_diag["unmatched_per_week"]
    frac = null["fraction_shifts_ge_observed"]
    beat_null = abr > 0 and frac < 0.5 and per_diag["abrupt_delay_hours"]["n"] > 0

    better = abr > gabr + 1e-9 or (abr == gabr and um < gum)
    lines.append(
        f"Per-sensor DIAG abrupt_recall={abr:.2f} (unmatched/wk={um:.2f}) vs "
        f"global {gabr:.2f} (unmatched/wk={gum:.2f}). "
        f"Null frac≥obs abrupt matches={frac:.2f}."
    )
    if abr <= 0 and gabr <= 0:
        return (
            "**No-go / unsuccessful:** neither per-sensor nor global achieved abrupt "
            "notification recall on DIAG under pre-registered post-onset matching. "
            + " ".join(lines)
        )
    if not beat_null:
        return (
            "**No-go / unsuccessful on chance:** per-sensor abrupt matches are not "
            "clearly above the circular-shift notification null (necessary bar failed). "
            + " ".join(lines)
            + " Preserve as negative/diagnostic result; do not productize."
        )
    long_ep = per_diag.get("longest_episode_hours") or 0
    if better and um <= 5.0:
        burden = ""
        if long_ep > 24 * 14:
            burden = (
                f" Caveat: longest episode {long_ep:.0f} h and total time-in-alarm "
                f"{per_diag.get('time_in_alarm_hours', float('nan')):.0f} h show "
                "non-recovery / multi-sensor persistence — improvement is not free of burden."
            )
        return (
            "**Limited research signal:** per-sensor signed residuals improve abrupt "
            "notification metrics vs global aggregation under equivalent rules, and beat "
            "the descriptive null. **Not** validated leak detection — independent "
            "evaluation required before any productization. Alert burden must remain "
            "explicit." + burden + " " + " ".join(lines)
        )
    return (
        "**Mixed / no-go for product:** some detection movement but burden or "
        "comparison does not support a clear win. " + " ".join(lines)
    )


def render_report(summary: dict) -> str:
    fr = summary["frozen_per_sensor"]
    d = summary["DIAG_per_sensor"]
    g = summary["DIAG_global"]
    lines = [
        "# Per-sensor relationship CUSUM — results",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Independent experiment (not a LILA reproduction). Prior global offline "
        "retrospective screening remains a **preserved negative** result on its own question.",
        "",
        "Primary metric: **notification time** (CUSUM crossing), not backdated change estimates. "
        "Abrupt success requires notify ∈ [onset, onset+7d]; pre-onset ≠ success.",
        "",
        f"Frozen per-sensor settings: `{fr['settings']}` gate_met={fr['gate_met']}",
        f"Frozen global settings: `{summary['frozen_global']['settings']}` "
        f"gate_met={summary['frozen_global']['gate_met']}",
        "",
        "## DEV grid (every attempted setting)",
        "",
    ]
    for row in summary["DEV_grid_per_sensor"]:
        s = row["settings"]
        lines.append(
            f"- K={s['n_refs']} h={s['cusum_h']} recover={s['recover_hours']}h → "
            f"abrupt_recall={row['abrupt_recall']:.2f} unmatched/wk={row['unmatched_per_week']:.2f} "
            f"episodes={row['n_episodes']}"
        )
    lines += ["", "### Global DEV grid", ""]
    for row in summary["DEV_grid_global"]:
        s = row["settings"]
        lines.append(
            f"- h={s['cusum_h']} recover={s['recover_hours']}h → "
            f"abrupt_recall={row['abrupt_recall']:.2f} unmatched/wk={row['unmatched_per_week']:.2f} "
            f"episodes={row['n_episodes']}"
        )
    lines += [
        "",
        "## DIAG (frozen)",
        "",
        "### Per-sensor",
        f"- Abrupt recall: **{d['abrupt_recall']:.2f}** ({d['n_abrupt']} onsets) "
        f"delays={d['abrupt_delay_hours']}",
        f"- Incipient recall: **{d['incipient_recall']:.2f}** ({d['n_incipient']} onsets)",
        f"- Unmatched episodes/week: **{d['unmatched_per_week']:.2f}**",
        f"- Time in alarm (h): {d['time_in_alarm_hours']:.1f}; longest episode (h): {d['longest_episode_hours']:.1f}",
        f"- Duplicate unmatched within 24h: {d['duplicate_unmatched_within_24h']}",
        f"- Ordinary controls: {summary['DIAG_ordinary_controls_per_sensor']}",
        "",
        "#### Per-event",
        "",
    ]
    for m in d["matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"notify={m['notify_time']} delay_h={m['delay_hours']} "
            f"sensor={m['stream_id']} refs={m['refs_used']}"
        )
    lines += [
        "",
        "### Global comparison",
        f"- Abrupt recall: **{g['abrupt_recall']:.2f}**; unmatched/wk={g['unmatched_per_week']:.2f}",
        f"- Incipient recall: {g['incipient_recall']:.2f}",
        f"- Time in alarm (h): {g['time_in_alarm_hours']:.1f}; longest: {g['longest_episode_hours']:.1f}",
        f"- Delays: {g['abrupt_delay_hours']}",
        "",
        "#### Global per-event",
        "",
    ]
    for m in g["matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) notify={m['notify_time']} "
            f"delay_h={m['delay_hours']}"
        )
    lines += [
        "",
        "## Chance comparison (notification circular shift)",
        "",
        str(summary["null_per_sensor"]),
        "",
        "## Where it fails / burden",
        "",
        summary["failure_notes"],
        "",
        "## Recommendation",
        "",
        summary["recommendation"],
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading 2018…", flush=True)
    bundle_p = load_pressures(args.raw_dir / "2018_SCADA_Pressures.csv")
    context = load_context(args.raw_dir)
    leakages = load_leakages()
    assert np.array_equal(bundle_p.timestamps, context.timestamps)
    sensor_ids = bundle_p.sensor_ids
    pressures = bundle_p.pressures
    timestamps = bundle_p.timestamps

    # --- Per-sensor DEV grid ---
    print("DEV grid (per-sensor)…", flush=True)
    grid_ps = []
    for n_refs in GRID_K:
        for h in GRID_H:
            for recover in GRID_RECOVER:
                settings = {
                    "train_days": TRAIN_DAYS,
                    "n_refs": n_refs,
                    "cusum_k": CUSUM_K,
                    "cusum_h": h,
                    "recover_hours": recover,
                }
                metrics, _, _ = run_per_sensor(
                    pressures, sensor_ids, timestamps, DEV, settings, leakages
                )
                grid_ps.append(metrics)
                print(
                    f"  {settings} abrupt={metrics['abrupt_recall']:.2f} "
                    f"unmatched/wk={metrics['unmatched_per_week']:.2f}",
                    flush=True,
                )

    chosen_ps, gate_ps = select_settings(grid_ps)
    frozen_ps = {
        "frozen_at": iso_now(),
        "settings": chosen_ps["settings"],
        "gate_met": gate_ps,
        "unmatched_cap": 3.0,
        "selection_rule": (
            "max abrupt recall among unmatched/wk<=3 on DEV; "
            "ties: lower unmatched/wk, larger h, larger K; else best-of-pool gate_met=false"
        ),
        "dev_snapshot": {
            k: chosen_ps[k]
            for k in (
                "abrupt_recall",
                "incipient_recall",
                "unmatched_per_week",
                "n_episodes",
            )
        },
    }
    (args.out_dir / "frozen_settings.json").write_text(json.dumps(frozen_ps, indent=2) + "\n")
    print(f"Froze per-sensor {frozen_ps['settings']} gate_met={gate_ps}", flush=True)

    # --- Global DEV grid (equivalent: no K) ---
    print("DEV grid (global)…", flush=True)
    grid_g = []
    for h in GRID_H:
        for recover in GRID_RECOVER:
            settings = {
                "train_days": TRAIN_DAYS,
                "n_refs": 3,
                "cusum_k": CUSUM_K,
                "cusum_h": h,
                "recover_hours": recover,
            }
            metrics, _, _ = run_global(pressures, timestamps, DEV, settings, leakages)
            grid_g.append(metrics)
            print(
                f"  h={h} recover={recover} abrupt={metrics['abrupt_recall']:.2f} "
                f"unmatched/wk={metrics['unmatched_per_week']:.2f}",
                flush=True,
            )
    chosen_g, gate_g = select_settings(grid_g)
    frozen_g = {
        "frozen_at": iso_now(),
        "settings": chosen_g["settings"],
        "gate_met": gate_g,
        "unmatched_cap": 3.0,
    }
    (args.out_dir / "frozen_global_settings.json").write_text(
        json.dumps(frozen_g, indent=2) + "\n"
    )

    print("DIAG per-sensor…", flush=True)
    diag_ps, eps_ps, bundle_diag = run_per_sensor(
        pressures, sensor_ids, timestamps, DIAG, chosen_ps["settings"], leakages
    )
    print("DIAG global…", flush=True)
    diag_g, eps_g, _ = run_global(
        pressures, timestamps, DIAG, chosen_g["settings"], leakages
    )

    start_i, end_i = period_indices(timestamps, DIAG)
    analysis_start = start_i + TRAIN_DAYS * 288
    null = null_notification_comparison(
        timestamps, eps_ps, onsets_in_period(leakages, DIAG), leakages, analysis_start, end_i
    )
    controls = ordinary_controls(timestamps, context, eps_ps, DIAG)
    plots = make_event_plots(
        timestamps, bundle_diag, eps_ps, diag_ps["matches"], sensor_ids, args.out_dir / "plots"
    )

    failure_notes = (
        f"Missed abrupt/incipient listed above. "
        f"Per-sensor episodes={diag_ps['n_episodes']} vs global={diag_g['n_episodes']}. "
        f"Common-mode and reference disturbance can suppress or spur signals (see DESIGN). "
        f"Duplicate unmatched={diag_ps['duplicate_unmatched_within_24h']}."
    )

    slim = lambda grid: [
        {
            "settings": g["settings"],
            "abrupt_recall": g["abrupt_recall"],
            "incipient_recall": g["incipient_recall"],
            "unmatched_per_week": g["unmatched_per_week"],
            "n_episodes": g["n_episodes"],
        }
        for g in grid
    ]

    diag_ps_out = {k: v for k, v in diag_ps.items()}
    summary = {
        "generated_at": iso_now(),
        "holdout_honesty": "2019 not evaluated; 2018 DEV→DIAG only.",
        "frozen_per_sensor": frozen_ps,
        "frozen_global": frozen_g,
        "DEV_grid_per_sensor": slim(grid_ps),
        "DEV_grid_global": slim(grid_g),
        "DIAG_per_sensor": diag_ps_out,
        "DIAG_global": {k: v for k, v in diag_g.items()},
        "null_per_sensor": null,
        "DIAG_ordinary_controls_per_sensor": controls,
        "plots": plots,
        "failure_notes": failure_notes,
        "recommendation": recommend(
            {**diag_ps, "dev_unmatched_note": frozen_ps["dev_snapshot"]["unmatched_per_week"]},
            diag_g,
            null,
            gate_ps,
        ),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out_dir / "RESULTS.md").write_text(render_report(summary) + "\n")
    print(summary["recommendation"], flush=True)
    print(f"Wrote {args.out_dir / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
