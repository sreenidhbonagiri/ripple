#!/usr/bin/env python3
"""DEV-only CUSUM-h grid extension on build_signals.z; dual gates; freeze; DIAG once.

Does not overwrite outputs/THRESHOLD_CALIBRATION_RESULTS.md (first grid).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_occupancy_recovery import (  # noqa: E402
    null_at_post_hours,
    occupancy_report,
    split_eligible_onsets,
    train_end_time,
)
from detector import RECOVERY_RESIDUAL_LE_K, Episode, run_all_targets  # noqa: E402
from evaluate import (  # noqa: E402
    DEV,
    DIAG,
    iso_now,
    match_episodes,
    onsets_in_period,
    period_indices,
)
from io_data import DEFAULT_RAW, load_leakages, load_pressures  # noqa: E402
from residual import build_signals  # noqa: E402
from run_residual_recovery_variant import duplicate_unmatched, recall_block  # noqa: E402

OUT = ROOT / "outputs"
FROZEN_BASE = json.loads((OUT / "frozen_settings.json").read_text())["settings"]

# Predeclared extension only — do not silently add further values.
H_GRID = [512.0, 1024.0, 2048.0, 4096.0, 8192.0, 16384.0]
K = 0.5
RESIDUAL_RECOVER_STEPS = 12
UNMATCHED_CAP = 3.0
ABRUPT_6H_MIN = 2.0 / 3.0
ABRUPT_6H_HOURS = 6.0


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def abrupt_recall_within_hours(matches: list[dict], hours: float) -> dict:
    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    n = len(abrupt)
    hits = [
        m
        for m in abrupt
        if m["matched"]
        and m["delay_hours"] is not None
        and m["delay_hours"] <= hours + 1e-12
    ]
    delays = [m["delay_hours"] for m in hits]
    return {
        "hours": hours,
        "n_abrupt": n,
        "n_hit": len(hits),
        "recall": (len(hits) / n) if n else float("nan"),
        "delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
            "values": delays,
        },
        "per_event": [
            {
                "pipe": m["pipe"],
                "onset": m["onset"],
                "matched": m["matched"],
                "notify_time": m["notify_time"],
                "delay_hours": m["delay_hours"],
                "within_window": bool(
                    m["matched"]
                    and m["delay_hours"] is not None
                    and m["delay_hours"] <= hours + 1e-12
                ),
                "stream_id": m.get("stream_id"),
            }
            for m in abrupt
        ],
    }


def latch_inspection(row: dict) -> dict:
    """Flag low unmatched achieved mainly via persistent latching."""
    occ = row["occupancy"]
    union = occ["union_alarm_pct_of_analysis"]
    sensor = occ["summed_sensor_alarm_pct_of_eligible"]
    censored = occ["n_episodes_right_censored"]
    n_ep = row["n_episodes"]
    longest = occ["episode_length_hours"]["max"]
    median_len = occ["episode_length_hours"]["median"]
    um = row["unmatched_per_week"]
    # Signature: few notifications but near-saturated union / long / censored episodes
    latched_suspect = bool(
        um <= UNMATCHED_CAP
        and (
            union >= 90.0
            or (n_ep > 0 and censored / n_ep >= 0.25 and (longest or 0) >= 500)
            or ((median_len or 0) >= 168 and union >= 50.0)
        )
    )
    return {
        "union_alarm_pct": union,
        "sensor_alarm_pct": sensor,
        "n_episodes": n_ep,
        "n_right_censored": censored,
        "median_episode_h": median_len,
        "longest_episode_h": longest,
        "active_sensors": occ["active_sensors"],
        "latched_suspect": latched_suspect,
        "note": (
            "Low unmatched with high union occupancy / long censored episodes "
            "is consistent with latched alarms, not cleared nuisance."
            if latched_suspect
            else "No strong latched-only signature under declared heuristics."
        ),
    }


def evaluate_period(pressures, timestamps, sensor_ids, leakages, period, settings, sig=None):
    start_i, end_i = period_indices(timestamps, period)
    if sig is None:
        sig = build_signals(
            pressures,
            interval_start=start_i,
            interval_end=end_i,
            train_days=settings["train_days"],
            n_refs=settings["n_refs"],
        )
    t0 = time.perf_counter()
    episodes = run_all_targets(
        sig.z,
        sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=RESIDUAL_RECOVER_STEPS,
    )
    runtime = time.perf_counter() - t0
    train_end = train_end_time(timestamps, start_i, settings["train_days"])
    eligible, in_prefix = split_eligible_onsets(
        onsets_in_period(leakages, period), train_end
    )
    prim, used = match_episodes(timestamps, episodes, eligible, leakages)
    prefix, _ = match_episodes(timestamps, episodes, in_prefix, leakages)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(episodes) - len(used)
    occ = occupancy_report(
        timestamps, episodes, sig.analysis_offset, end_i, n_sensors=len(sensor_ids)
    )
    primary = recall_block(prim)
    abr6 = abrupt_recall_within_hours(prim, ABRUPT_6H_HOURS)
    row = {
        "settings": dict(settings),
        "period": period.name,
        "runtime_seconds": runtime,
        "n_episodes": len(episodes),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": primary,
        "abrupt_6h": abr6,
        "all_event_notification_times": [
            {
                "pipe": m["pipe"],
                "leak_type": m["leak_type"],
                "onset": m["onset"],
                "matched": m["matched"],
                "notify_time": m["notify_time"],
                "delay_hours": m["delay_hours"],
                "stream_id": m.get("stream_id"),
            }
            for m in prim
        ],
        "in_prefix_matches": prefix,
        "occupancy": {
            k: occ[k]
            for k in (
                "summed_sensor_alarm_pct_of_eligible",
                "union_alarm_pct_of_analysis",
                "n_notifications",
                "n_episodes_right_censored",
                "episode_length_hours",
                "active_sensors",
                "summed_sensor_alarm_hours",
                "union_alarm_hours",
            )
        },
        "episodes": episodes,
        "sig": sig,
        "analysis_start": sig.analysis_offset,
        "analysis_end": end_i,
        "train_end": str(train_end).replace("T", " "),
        "z_sha256_16": hashlib.sha256(np.ascontiguousarray(sig.z).tobytes()).hexdigest()[:16],
    }
    row["latch_inspection"] = latch_inspection(row)
    return row


def select_h(grid: list[dict]) -> tuple[dict | None, bool]:
    eligible = [
        g
        for g in grid
        if g["unmatched_per_week"] <= UNMATCHED_CAP
        and (g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1)
        >= ABRUPT_6H_MIN - 1e-12
        and not g["latch_inspection"]["latched_suspect"]
    ]
    if not eligible:
        return None, False

    def delay_key(g):
        d = g["abrupt_6h"]["delay_hours"]["median"]
        if d is None or not np.isfinite(d):
            d = g["primary"]["abrupt_delay_hours"]["median"]
        return d if d is not None and np.isfinite(d) else 1e9

    eligible = sorted(
        eligible,
        key=lambda g: (
            -(g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1),
            delay_key(g),
            g["unmatched_per_week"],
            g["settings"]["cusum_h"],
        ),
    )
    return eligible[0], True


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("episodes", "sig")}


def render(summary: dict) -> str:
    lines = [
        "# CUSUM-h calibration extension — original relationship signal",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Continues DEV-only threshold calibration on `build_signals.z`. "
        "Does **not** overwrite `THRESHOLD_CALIBRATION_RESULTS.md`. "
        "Context correction not used.",
        "",
        f"Fixed: K={summary['fixed']['n_refs']}, k={summary['fixed']['cusum_k']}, "
        f"residual_recover_steps={summary['fixed']['residual_recover_steps']}, "
        f"train_days={summary['fixed']['train_days']}.",
        f"Provisional unmatched/week cap: **≤ {UNMATCHED_CAP:g}** (not operator-validated).",
        f"Useful abrupt sensitivity: **≥ {ABRUPT_6H_MIN:.4f}** "
        f"({ABRUPT_6H_HOURS:g} h window).",
        "",
        "## Input hashes",
        "",
    ]
    for k, v in summary["input_hashes"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        f"- DEV `z` sha256[:16]: `{summary['dev_z_sha256_16']}`",
        "",
        "## DEV grid extension (every setting)",
        "",
        "| h | Abrupt 6h recall | Med delay 6h (h) | Unmatched/wk | Dup 24h | "
        "Union occ% | Sensor-alarm% | Active med/p90/max | Med ep (h) | "
        "Longest (h) | Censored | Episodes | Latch? |",
        "|---|------------------|------------------|--------------|---------|-----------|"
        "---------------|-------------------|------------|"
        "-------------|----------|----------|--------|",
    ]
    for g in summary["DEV_grid"]:
        d6 = g["abrupt_6h"]["delay_hours"]["median"]
        act = g["occupancy"]["active_sensors"]
        med_ep = g["occupancy"]["episode_length_hours"]["median"]
        lines.append(
            f"| {g['settings']['cusum_h']:g} | {g['abrupt_6h']['recall']:.2f} | "
            f"{'' if d6 is None else f'{d6:.3f}'} | {g['unmatched_per_week']:.2f} | "
            f"{g['duplicate_unmatched_within_24h']} | "
            f"{g['occupancy']['union_alarm_pct_of_analysis']:.2f} | "
            f"{g['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f} | "
            f"{act['median']:.1f}/{act['p90']:.1f}/{act['max']:.0f} | "
            f"{'' if med_ep is None else f'{med_ep:.2f}'} | "
            f"{g['occupancy']['episode_length_hours']['max']} | "
            f"{g['occupancy']['n_episodes_right_censored']} | {g['n_episodes']} | "
            f"{'yes' if g['latch_inspection']['latched_suspect'] else 'no'} |"
        )

    lines += ["", "### Per-setting event notification times (post-training eligible)", ""]
    for g in summary["DEV_grid"]:
        lines.append(f"#### h={g['settings']['cusum_h']:g}")
        lines.append("")
        for m in g["all_event_notification_times"]:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(
                f"- {tag} {m['pipe']} ({m['leak_type']}) onset={m['onset']} "
                f"notify={m['notify_time']} delay_h={m['delay_hours']} "
                f"sensor={m.get('stream_id')}"
            )
        li = g["latch_inspection"]
        lines.append(
            f"- Latch inspection: union={li['union_alarm_pct']:.1f}% "
            f"sensor={li['sensor_alarm_pct']:.1f}% censored={li['n_right_censored']} "
            f"longest_h={li['longest_episode_h']} — {li['note']}"
        )
        lines.append("")

    fr = summary["frozen"]
    lines += [
        "## Selection",
        "",
        f"- gate_met: **{fr['gate_met']}**",
        f"- selected h: **{fr.get('selected_h')}**",
        f"- rule: {fr['selection_rule']}",
        f"- note: {fr.get('note', '')}",
        "",
    ]
    if not fr["gate_met"]:
        lines += [
            "**Selection failure at this range:** no DEV setting in "
            f"{H_GRID} met both targets (6 h abrupt recall ≥ {ABRUPT_6H_MIN:.4f} and "
            f"unmatched/week ≤ {UNMATCHED_CAP:g}) without latched-only signature. "
            "No invented winner; grid not silently extended; DIAG not run under a new h.",
            "",
            "## Recommendation",
            "",
            summary["recommendation"],
            "",
        ]
        return "\n".join(lines)

    d = summary["DIAG"]
    lines += [
        "## DIAG (frozen h — diagnostic only)",
        "",
        f"- Abrupt 6h recall: **{d['abrupt_6h']['recall']:.2f}** "
        f"({d['abrupt_6h']['n_hit']}/{d['abrupt_6h']['n_abrupt']}); "
        f"delays_6h={d['abrupt_6h']['delay_hours']}",
        f"- Abrupt recall (registered window): **{d['primary']['abrupt_recall']:.2f}** "
        f"delays={d['primary']['abrupt_delay_hours']}",
        f"- Incipient recall: **{d['primary']['incipient_recall']:.2f}**",
        f"- Unmatched/wk: **{d['unmatched_per_week']:.2f}**; "
        f"dup: {d['duplicate_unmatched_within_24h']}",
        f"- Union occ%: {d['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
        f"sensor-alarm%: {d['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
        f"- Active sensors mean/med/p90/max: "
        f"{d['occupancy']['active_sensors']['mean']:.2f}/"
        f"{d['occupancy']['active_sensors']['median']:.2f}/"
        f"{d['occupancy']['active_sensors']['p90']:.2f}/"
        f"{d['occupancy']['active_sensors']['max']:.0f}",
        f"- Median / longest episode (h): "
        f"{d['occupancy']['episode_length_hours']['median']} / "
        f"{d['occupancy']['episode_length_hours']['max']}; "
        f"censored: {d['occupancy']['n_episodes_right_censored']}",
        f"- Latch inspection: {d['latch_inspection']['note']}",
        "",
        "Per-event (post-training eligible):",
        "",
    ]
    for m in d["all_event_notification_times"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) onset={m['onset']} "
            f"notify={m['notify_time']} delay_h={m['delay_hours']} "
            f"sensor={m.get('stream_id')}"
        )
    lines += ["", "Prefix (separate):", ""]
    for m in d["in_prefix_matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) notify={m['notify_time']} "
            f"delay_h={m.get('delay_hours')}"
        )
    n2 = summary["null_2h"]
    lines += [
        "",
        "## 0–2 h notification-time shifted null (diagnostic)",
        "",
        f"- Observed abrupt matches: **{n2['observed_abrupt_matches']}** / {n2['n_abrupt_onsets']}",
        f"- Null median (min–max): {n2['null_match_median']} "
        f"({n2['null_match_min']}–{n2['null_match_max']})",
        f"- Frac shifts ≥ obs: **{n2['fraction_shifts_ge_observed']:.2f}** "
        f"(n_shifts={n2['null_n_valid_shifts']})",
        "",
        n2["caveat"],
        "",
        "## Interpretation",
        "",
        summary["interpretation"],
        "",
        "## Recommendation",
        "",
        summary["recommendation"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading…", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()

    input_hashes = {
        "2018_SCADA_Pressures.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "2018_SCADA_Flows.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Flows.csv"),
        "2018_SCADA_Levels.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Levels.csv"),
    }
    # Cross-check vs first-calibration reconciliation if present
    recon_path = OUT / "baseline_reconciliation.json"
    if recon_path.exists():
        recon = json.loads(recon_path.read_text())
        assert input_hashes["2018_SCADA_Pressures.csv"] == recon["pressures_sha256"]
        print("Input pressure hash matches prior reconciliation.", flush=True)

    base_settings = {
        "train_days": FROZEN_BASE["train_days"],
        "n_refs": FROZEN_BASE["n_refs"],
        "cusum_k": K,
        "recover_hours": FROZEN_BASE["recover_hours"],
    }

    print("DEV build_signals once…", flush=True)
    d0, d1 = period_indices(pb.timestamps, DEV)
    sig_dev = build_signals(
        pb.pressures,
        interval_start=d0,
        interval_end=d1,
        train_days=base_settings["train_days"],
        n_refs=base_settings["n_refs"],
    )
    dev_z16 = hashlib.sha256(np.ascontiguousarray(sig_dev.z).tobytes()).hexdigest()[:16]

    grid = []
    for h in H_GRID:
        settings = {**base_settings, "cusum_h": h}
        print(f"DEV h={h}…", flush=True)
        row = evaluate_period(
            pb.pressures,
            pb.timestamps,
            pb.sensor_ids,
            leakages,
            DEV,
            settings,
            sig=sig_dev,
        )
        grid.append(row)
        print(
            f"  abrupt6h={row['abrupt_6h']['recall']:.2f} "
            f"unmatched/wk={row['unmatched_per_week']:.2f} "
            f"union%={row['occupancy']['union_alarm_pct_of_analysis']:.1f} "
            f"sum%={row['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f} "
            f"latch={row['latch_inspection']['latched_suspect']}",
            flush=True,
        )

    chosen, gate = select_h(grid)
    # Also note any settings that hit numeric gates but failed latch filter
    numeric_ok = [
        g
        for g in grid
        if g["unmatched_per_week"] <= UNMATCHED_CAP
        and (g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1)
        >= ABRUPT_6H_MIN - 1e-12
    ]
    latch_blocked = [g for g in numeric_ok if g["latch_inspection"]["latched_suspect"]]

    frozen = {
        "frozen_at": iso_now(),
        "gate_met": gate,
        "selected_h": None if not gate else chosen["settings"]["cusum_h"],
        "unmatched_cap": UNMATCHED_CAP,
        "abrupt_6h_min": ABRUPT_6H_MIN,
        "abrupt_6h_hours": ABRUPT_6H_HOURS,
        "h_grid": H_GRID,
        "selection_rule": (
            "among unmatched/wk<=3 AND abrupt_6h_recall>=2/3 AND not latched_suspect: "
            "max abrupt_6h recall, then min median 6h delay, then min unmatched/wk; "
            "else selection failure at this range"
        ),
        "signal": "build_signals.z",
        "input_hashes": input_hashes,
        "dev_z_sha256_16": dev_z16,
        "fixed": {
            **base_settings,
            "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
            "recovery_mode": RECOVERY_RESIDUAL_LE_K,
        },
        "dev_snapshot": None
        if not gate
        else {
            "abrupt_6h_recall": chosen["abrupt_6h"]["recall"],
            "unmatched_per_week": chosen["unmatched_per_week"],
            "median_delay_6h": chosen["abrupt_6h"]["delay_hours"]["median"],
            "n_episodes": chosen["n_episodes"],
            "union_occ_pct": chosen["occupancy"]["union_alarm_pct_of_analysis"],
        },
        "numeric_gate_met_count": len(numeric_ok),
        "latch_blocked_count": len(latch_blocked),
        "note": (
            ""
            if gate
            else (
                "No DEV setting in this extension range met both targets without "
                "latched-only signature; DIAG not run for a new h. "
                "Do not silently extend further."
            )
        ),
    }
    (OUT / "threshold_extension_frozen.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(f"Froze gate_met={gate} h={frozen['selected_h']}", flush=True)

    diag = None
    null2 = None
    interpretation = ""
    if gate:
        print("DIAG once at frozen h…", flush=True)
        settings = {**base_settings, "cusum_h": frozen["selected_h"]}
        diag_full = evaluate_period(
            pb.pressures, pb.timestamps, pb.sensor_ids, leakages, DIAG, settings
        )
        elig, _ = split_eligible_onsets(
            onsets_in_period(leakages, DIAG),
            train_end_time(
                pb.timestamps, period_indices(pb.timestamps, DIAG)[0], settings["train_days"]
            ),
        )
        null2 = null_at_post_hours(
            pb.timestamps,
            diag_full["episodes"],
            elig,
            leakages,
            diag_full["analysis_start"],
            diag_full["analysis_end"],
            post_hours=2.0,
        )
        diag = strip(diag_full)
        interpretation = (
            f"Frozen h={frozen['selected_h']} (diagnostic): abrupt_6h="
            f"{diag['abrupt_6h']['recall']:.2f}, unmatched/wk="
            f"{diag['unmatched_per_week']:.2f}, union occ%="
            f"{diag['occupancy']['union_alarm_pct_of_analysis']:.1f}, "
            f"sensor-alarm%={diag['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}, "
            f"censored={diag['occupancy']['n_episodes_right_censored']}. "
            f"{diag['latch_inspection']['note']} "
            "Assess whether useful notify timing is preserved while nuisance "
            "falls for reasons other than mere latching."
        )

    if not gate:
        recommendation = (
            "**Selection failure at this range / no-go:** no h in "
            f"{H_GRID} jointly achieved abrupt 6h recall ≥ {ABRUPT_6H_MIN:.4f} and "
            f"provisional unmatched/week ≤ {UNMATCHED_CAP:g} without a latched-alarm "
            "signature on DEV under fixed residual-recovery and original "
            "`build_signals.z`. Do not invent a winner; do not silently extend "
            "the grid; do not retune recovery or features here."
        )
    else:
        abr = diag["abrupt_6h"]["recall"]
        um = diag["unmatched_per_week"]
        union = diag["occupancy"]["union_alarm_pct_of_analysis"]
        frac_null = null2["fraction_shifts_ge_observed"]
        if (
            abr >= ABRUPT_6H_MIN
            and um <= UNMATCHED_CAP
            and not diag["latch_inspection"]["latched_suspect"]
            and union < 50
            and frac_null < 0.5
        ):
            recommendation = (
                "**Conditional research continue:** calibrated h meets DEV dual gates "
                "and shows a usable DIAG sensitivity/burden profile without relying on "
                "saturated latching alone; 0–2h null not dominated by chance. "
                "Still diagnostic — not validated detection."
            )
        elif diag["latch_inspection"]["latched_suspect"] or (
            union >= 90 and um <= UNMATCHED_CAP
        ):
            recommendation = (
                "**No-go:** apparent workload improvement is consistent with latched "
                "network occupancy rather than cleared nuisance structure."
            )
        elif abr < ABRUPT_6H_MIN:
            recommendation = (
                "**No-go:** calibrated h loses useful six-hour abrupt sensitivity on DIAG."
            )
        else:
            recommendation = (
                "**Mixed / no-go:** threshold extension does not clearly preserve "
                "useful timing while reducing nuisance under the declared criteria."
            )

    summary = {
        "generated_at": iso_now(),
        "extension_of": "THRESHOLD_CALIBRATION_RESULTS.md (first grid preserved)",
        "input_hashes": input_hashes,
        "dev_z_sha256_16": dev_z16,
        "fixed": {
            **base_settings,
            "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
        },
        "targets": {
            "unmatched_per_week_max": UNMATCHED_CAP,
            "abrupt_6h_min_recall": ABRUPT_6H_MIN,
            "abrupt_6h_hours": ABRUPT_6H_HOURS,
        },
        "DEV_grid": [strip(g) for g in grid],
        "frozen": frozen,
        "DIAG": diag,
        "null_2h": null2,
        "interpretation": interpretation,
        "recommendation": recommendation,
        "holdout_honesty": (
            "DIAG results are diagnostic given prior examination; not a new blind holdout. "
            "2019 not evaluated. Full grid not scored on DIAG."
        ),
    }
    (OUT / "threshold_calibration_extension_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (OUT / "THRESHOLD_CALIBRATION_EXTENSION_RESULTS.md").write_text(render(summary) + "\n")
    print(recommendation, flush=True)
    print(f"Wrote {OUT / 'THRESHOLD_CALIBRATION_EXTENSION_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
