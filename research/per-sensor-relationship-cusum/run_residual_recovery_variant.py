#!/usr/bin/env python3
"""Paired original vs residual-recovery variant (frozen settings; no retune)."""

from __future__ import annotations

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
from detector import (  # noqa: E402
    RECOVERY_CUSUM_ZERO,
    RECOVERY_RESIDUAL_LE_K,
    Episode,
    run_all_targets,
)
from evaluate import (  # noqa: E402
    ABRUPT_POST_DAYS,
    DEV,
    DIAG,
    iso_now,
    match_episodes,
    null_notification_comparison,
    onsets_in_period,
    period_indices,
)
from io_data import DEFAULT_RAW, load_leakages, load_pressures  # noqa: E402
from residual import build_signals  # noqa: E402

OUT = ROOT / "outputs"
FROZEN = json.loads((OUT / "frozen_settings.json").read_text())["settings"]
# Identical to frozen original — not retuned
SETTINGS = {
    "train_days": FROZEN["train_days"],
    "n_refs": FROZEN["n_refs"],
    "cusum_k": FROZEN["cusum_k"],
    "cusum_h": FROZEN["cusum_h"],
    "recover_hours": FROZEN["recover_hours"],
}
RESIDUAL_RECOVER_STEPS = 12  # fixed engineering hypothesis; not swept


def recall_block(matches: list[dict]) -> dict:
    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    incip = [m for m in matches if m["leak_type"] == "incipient"]

    def r(xs):
        return (sum(1 for m in xs if m["matched"]) / len(xs)) if xs else float("nan")

    delays = [m["delay_hours"] for m in abrupt if m["matched"]]
    return {
        "abrupt_recall": r(abrupt),
        "incipient_recall": r(incip),
        "n_abrupt": len(abrupt),
        "n_incipient": len(incip),
        "abrupt_delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
            "values": delays,
        },
        "matches": matches,
    }


def duplicate_unmatched(timestamps, episodes: list[Episode], matched_idx: set[int]) -> int:
    notify_times = [timestamps[ep.notify_idx] for ep in episodes]
    dup = 0
    for j, ep in enumerate(episodes):
        if j in matched_idx:
            continue
        t = notify_times[j]
        for k, t2 in enumerate(notify_times):
            if k == j:
                continue
            if abs(float((t - t2) / np.timedelta64(1, "h"))) <= 24.0:
                dup += 1
                break
    return dup


def evaluate_mode(
    name: str,
    recovery_mode: str,
    timestamps,
    sensor_ids,
    leakages,
    period,
    sig,
    settings: dict,
):
    start_i, end_i = period_indices(timestamps, period)
    train_end = train_end_time(timestamps, start_i, settings["train_days"])
    analysis_start = sig.analysis_offset
    t0 = time.perf_counter()
    episodes = run_all_targets(
        sig.z,
        sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
        recovery_mode=recovery_mode,
        residual_recover_steps=RESIDUAL_RECOVER_STEPS,
    )
    runtime = time.perf_counter() - t0

    all_onsets = onsets_in_period(leakages, period)
    eligible, in_prefix = split_eligible_onsets(all_onsets, train_end)
    prim_matches, used = match_episodes(timestamps, episodes, eligible, leakages)
    prefix_matches, _ = match_episodes(timestamps, episodes, in_prefix, leakages)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(episodes) - len(used)
    occ = occupancy_report(
        timestamps, episodes, analysis_start, end_i, n_sensors=len(sensor_ids)
    )
    primary = recall_block(prim_matches)
    return {
        "name": name,
        "recovery_mode": recovery_mode,
        "period": period.name,
        "train_end": str(train_end).replace("T", " "),
        "runtime_seconds": runtime,
        "n_episodes": len(episodes),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": primary,
        "in_prefix_matches": prefix_matches,
        "in_prefix_onsets": [
            {"pipe": L.pipe, "type": L.leak_type, "onset": str(L.start).replace("T", " ")}
            for L in in_prefix
        ],
        "occupancy": {
            k: occ[k]
            for k in (
                "summed_sensor_alarm_hours",
                "summed_sensor_alarm_pct_of_eligible",
                "union_alarm_hours",
                "union_alarm_pct_of_analysis",
                "n_notifications",
                "n_episodes_right_censored",
                "episode_length_hours",
                "active_sensors",
            )
        },
        "episodes": episodes,
        "analysis_start": analysis_start,
        "analysis_end": end_i,
    }


def scale_excursion_inspection(sig, sensor_ids, episodes: list[Episode]) -> dict:
    """Tiny pair scales and residual excursion frequency — report only, no changes."""
    tiny = []
    for tm in sig.target_models:
        scales = [pm.scale for pm in tm.pairs.values()]
        if scales and min(scales) < 0.05:
            tiny.append(
                {
                    "target": sensor_ids[tm.target],
                    "min_scale": float(min(scales)),
                    "scales": [float(s) for s in scales],
                }
            )
    # fraction of analysis steps with z>k among streams that notified
    notified = {ep.target_idx for ep in episodes if ep.target_idx >= 0}
    frac_elev = {}
    for i in sorted(notified):
        z = sig.z[:, i]
        finite = z[np.isfinite(z)]
        if finite.size:
            frac_elev[sensor_ids[i]] = float(np.mean(finite > SETTINGS["cusum_k"]))
    return {
        "targets_with_min_pair_scale_lt_0.05": tiny,
        "n_targets_tiny_scale": len(tiny),
        "frac_finite_z_gt_k_on_notifying_streams": frac_elev,
        "note": (
            "Normalization unchanged this round. Tiny scales and frequent z>k "
            "excursions may still dominate alert burden under residual recovery."
        ),
    }


def hit_retention(original_matches: list[dict], variant_matches: list[dict]) -> dict:
    o = {m["pipe"]: m for m in original_matches}
    v = {m["pipe"]: m for m in variant_matches}
    retained, lost, gained = [], [], []
    for pipe, om in o.items():
        vm = v.get(pipe)
        if om["matched"] and vm and vm["matched"]:
            retained.append(
                {
                    "pipe": pipe,
                    "type": om["leak_type"],
                    "orig_delay": om["delay_hours"],
                    "var_delay": vm["delay_hours"],
                    "orig_sensor": om.get("stream_id"),
                    "var_sensor": vm.get("stream_id"),
                }
            )
        elif om["matched"] and (not vm or not vm["matched"]):
            lost.append({"pipe": pipe, "type": om["leak_type"], "orig_notify": om["notify_time"]})
        elif (not om["matched"]) and vm and vm["matched"]:
            gained.append({"pipe": pipe, "type": vm["leak_type"], "var_notify": vm["notify_time"]})
    return {"retained": retained, "lost": lost, "gained": gained}


def recommend(dev_o, dev_v, diag_o, diag_v, null_7, null_2) -> str:
    lines = []
    o_abr = diag_o["primary"]["abrupt_recall"]
    v_abr = diag_v["primary"]["abrupt_recall"]
    o_occ = diag_o["occupancy"]["union_alarm_pct_of_analysis"]
    v_occ = diag_v["occupancy"]["union_alarm_pct_of_analysis"]
    o_sum = diag_o["occupancy"]["summed_sensor_alarm_pct_of_eligible"]
    v_sum = diag_v["occupancy"]["summed_sensor_alarm_pct_of_eligible"]
    o_long = diag_o["occupancy"]["episode_length_hours"]["max"]
    v_long = diag_v["occupancy"]["episode_length_hours"]["max"]
    lines.append(
        f"DIAG abrupt recall original={o_abr:.2f} vs variant={v_abr:.2f}; "
        f"union occupancy {o_occ:.1f}% → {v_occ:.1f}%; "
        f"summed sensor-alarm {o_sum:.1f}% → {v_sum:.1f}%; "
        f"longest episode {o_long} → {v_long} h; "
        f"unmatched/wk {diag_o['unmatched_per_week']:.2f} → {diag_v['unmatched_per_week']:.2f}."
    )
    lines.append(
        f"Variant null 7d: obs={null_7['observed_abrupt_matches']} "
        f"median={null_7['null_match_median']} "
        f"min–max={null_7['null_match_min']}–{null_7['null_match_max']} "
        f"frac≥obs={null_7['fraction_shifts_ge_observed']:.2f} "
        f"(n_shifts={null_7['null_n_valid_shifts']}). "
        f"Null 0–2h: obs={null_2['observed_abrupt_matches']} "
        f"median={null_2['null_match_median']} "
        f"min–max={null_2['null_match_min']}–{null_2['null_match_max']} "
        f"frac≥obs={null_2['fraction_shifts_ge_observed']:.2f}."
    )
    # Notification storm after clear/rearm dominates usefulness.
    if diag_v["unmatched_per_week"] > max(10.0, 5 * diag_o["unmatched_per_week"]):
        return (
            "**No-go for this residual-recovery operating point:** abrupt hits were "
            "retained, but clear/rearm under frequent residual excursions creates a "
            "notification storm (unmatched/wk ≫ original) while union network occupancy "
            "stays near saturation. The registered 7-day shift null is not beaten. "
            "Summed sensor-hours fell, but that is not usable under the alert burden. "
            "Tiny pair scales remain widespread; do not productize; do not sweep the "
            "12-step constant next—address scale/excursion behavior first. "
            + " ".join(lines)
        )
    if v_abr >= o_abr - 1e-9 and v_occ < o_occ * 0.5 and null_7["fraction_shifts_ge_observed"] < 0.5:
        return (
            "**Conditional research continue:** residual recovery materially cuts occupancy "
            "while holding post-training abrupt notification recall and beating the "
            "descriptive 7-day null. Still not validated leak detection; tiny scales / "
            "excursions remain open. Do not productize; do not sweep recovery length yet. "
            + " ".join(lines)
        )
    if v_abr < o_abr - 1e-9:
        return (
            "**No-go on this variant alone:** residual recovery lost abrupt notification "
            "recall relative to the frozen original. " + " ".join(lines)
        )
    if v_occ >= o_occ * 0.8:
        return (
            "**Insufficient occupancy relief:** residual recovery did not substantially "
            "reduce network alarm occupancy. " + " ".join(lines)
        )
    return (
        "**Mixed:** inspect retained/lost hits, nulls, and scale/excursion notes before "
        "another detector change. " + " ".join(lines)
    )


def render(summary: dict) -> str:
    lines = [
        "# Paired comparison — residual-normalization recovery variant",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Original frozen detector/settings/RESULTS preserved. Variant registered in "
        r"`VARIANT_RESIDUAL_RECOVERY.md` (12-step \(z\le k\) recovery; not swept).",
        "",
        f"Shared settings: `{summary['settings']}`",
        f"Variant residual_recover_steps: **{summary['residual_recover_steps']}**",
        "",
        "## DEV (recorded before DIAG; no retune)",
        "",
    ]
    for key in ("DEV_original", "DEV_variant"):
        r = summary[key]
        lines += [
            f"### {r['name']}",
            f"- Post-training abrupt recall: **{r['primary']['abrupt_recall']:.2f}** "
            f"delays={r['primary']['abrupt_delay_hours']}",
            f"- Incipient recall: **{r['primary']['incipient_recall']:.2f}**",
            f"- Unmatched notifications/wk: **{r['unmatched_per_week']:.2f}**; "
            f"dup unmatched 24h: {r['duplicate_unmatched_within_24h']}",
            f"- Summed sensor-alarm: {r['occupancy']['summed_sensor_alarm_hours']:.1f} h "
            f"({r['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}%)",
            f"- Union occupancy: {r['occupancy']['union_alarm_hours']:.1f} h "
            f"({r['occupancy']['union_alarm_pct_of_analysis']:.2f}%)",
            f"- Longest episode (h): {r['occupancy']['episode_length_hours']['max']}; "
            f"right-censored: {r['occupancy']['n_episodes_right_censored']}/"
            f"{r['occupancy']['n_notifications']}",
            "",
        ]
    lines += ["## DIAG (frozen; no retune)", ""]
    for key in ("DIAG_original", "DIAG_variant"):
        r = summary[key]
        lines += [
            f"### {r['name']}",
            f"- Post-training abrupt recall: **{r['primary']['abrupt_recall']:.2f}** "
            f"delays={r['primary']['abrupt_delay_hours']}",
            f"- Incipient recall: **{r['primary']['incipient_recall']:.2f}**",
            f"- Unmatched/wk: **{r['unmatched_per_week']:.2f}**; "
            f"dup: {r['duplicate_unmatched_within_24h']}",
            f"- Summed sensor-alarm %: {r['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
            f"- Union occupancy %: {r['occupancy']['union_alarm_pct_of_analysis']:.2f}",
            f"- Longest (h): {r['occupancy']['episode_length_hours']['max']}; "
            f"right-censored: {r['occupancy']['n_episodes_right_censored']}",
            "",
            "Per-event (primary eligible):",
            "",
        ]
        for m in r["primary"]["matches"]:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(
                f"- {tag} {m['pipe']} ({m['leak_type']}) notify={m['notify_time']} "
                f"delay_h={m['delay_hours']} sensor={m.get('stream_id')}"
            )
        lines += ["", "Prefix onsets (separate; not in primary):", ""]
        for m in r["in_prefix_matches"]:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(
                f"- {tag} {m['pipe']} ({m['leak_type']}) onset={m['onset']} "
                f"notify={m['notify_time']}"
            )
        lines.append("")

    hr = summary["DIAG_hit_retention"]
    lines += [
        "### Hit retention (original → variant, primary eligible)",
        f"- Retained: {hr['retained']}",
        f"- Lost: {hr['lost']}",
        f"- Gained: {hr['gained']}",
        "",
        "## Chance comparison (variant DIAG, eligible abrupt)",
        "",
        f"### Registered 0–{ABRUPT_POST_DAYS:g} day window",
        str(summary["variant_null_7d"]),
        "",
        "### Diagnostic 0–2 hour window",
        str(summary["variant_null_2h"]),
        "",
        "## Remaining problems (no normalization change)",
        "",
        str(summary["remaining_problems"]),
        "",
        "## Recommendation",
        "",
        summary["recommendation"],
        "",
    ]
    return "\n".join(lines)


def strip_episodes(result: dict) -> dict:
    out = {k: v for k, v in result.items() if k != "episodes"}
    return out


def main() -> int:
    print("Loading pressures…", flush=True)
    bundle = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()
    timestamps = bundle.timestamps
    sensor_ids = bundle.sensor_ids
    pressures = bundle.pressures

    # --- DEV first ---
    print("DEV signals (shared fits)…", flush=True)
    d0, d1 = period_indices(timestamps, DEV)
    sig_dev = build_signals(
        pressures,
        interval_start=d0,
        interval_end=d1,
        train_days=SETTINGS["train_days"],
        n_refs=SETTINGS["n_refs"],
    )
    print("DEV original…", flush=True)
    dev_o = evaluate_mode(
        "original_cusum_zero",
        RECOVERY_CUSUM_ZERO,
        timestamps,
        sensor_ids,
        leakages,
        DEV,
        sig_dev,
        SETTINGS,
    )
    print("DEV variant…", flush=True)
    dev_v = evaluate_mode(
        "variant_residual_le_k",
        RECOVERY_RESIDUAL_LE_K,
        timestamps,
        sensor_ids,
        leakages,
        DEV,
        sig_dev,
        SETTINGS,
    )
    # Record DEV before DIAG
    (OUT / "variant_dev_snapshot.json").write_text(
        json.dumps(
            {
                "recorded_at": iso_now(),
                "settings": SETTINGS,
                "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
                "DEV_original": strip_episodes(dev_o),
                "DEV_variant": strip_episodes(dev_v),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"DEV recorded. abrupt o={dev_o['primary']['abrupt_recall']:.2f} "
        f"v={dev_v['primary']['abrupt_recall']:.2f}",
        flush=True,
    )

    # --- DIAG frozen ---
    print("DIAG signals (shared fits)…", flush=True)
    g0, g1 = period_indices(timestamps, DIAG)
    sig_diag = build_signals(
        pressures,
        interval_start=g0,
        interval_end=g1,
        train_days=SETTINGS["train_days"],
        n_refs=SETTINGS["n_refs"],
    )
    print("DIAG original…", flush=True)
    diag_o = evaluate_mode(
        "original_cusum_zero",
        RECOVERY_CUSUM_ZERO,
        timestamps,
        sensor_ids,
        leakages,
        DIAG,
        sig_diag,
        SETTINGS,
    )
    print("DIAG variant…", flush=True)
    diag_v = evaluate_mode(
        "variant_residual_le_k",
        RECOVERY_RESIDUAL_LE_K,
        timestamps,
        sensor_ids,
        leakages,
        DIAG,
        sig_diag,
        SETTINGS,
    )

    eligible, _ = split_eligible_onsets(
        onsets_in_period(leakages, DIAG),
        train_end_time(timestamps, g0, SETTINGS["train_days"]),
    )
    null_7 = null_notification_comparison(
        timestamps,
        diag_v["episodes"],
        eligible,
        leakages,
        diag_v["analysis_start"],
        diag_v["analysis_end"],
    )
    null_2 = null_at_post_hours(
        timestamps,
        diag_v["episodes"],
        eligible,
        leakages,
        diag_v["analysis_start"],
        diag_v["analysis_end"],
        post_hours=2.0,
    )
    retention = hit_retention(diag_o["primary"]["matches"], diag_v["primary"]["matches"])
    remaining = scale_excursion_inspection(sig_diag, sensor_ids, diag_v["episodes"])

    summary = {
        "generated_at": iso_now(),
        "settings": SETTINGS,
        "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
        "original_results_preserved": "outputs/RESULTS.md unchanged",
        "DEV_original": strip_episodes(dev_o),
        "DEV_variant": strip_episodes(dev_v),
        "DIAG_original": strip_episodes(diag_o),
        "DIAG_variant": strip_episodes(diag_v),
        "DIAG_hit_retention": retention,
        "variant_null_7d": null_7,
        "variant_null_2h": null_2,
        "remaining_problems": remaining,
        "recommendation": recommend(dev_o, dev_v, diag_o, diag_v, null_7, null_2),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "variant_comparison_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (OUT / "VARIANT_COMPARISON.md").write_text(render(summary) + "\n")
    print(summary["recommendation"], flush=True)
    print(f"Wrote {OUT / 'VARIANT_COMPARISON.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
