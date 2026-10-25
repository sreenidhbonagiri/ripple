#!/usr/bin/env python3
"""DEV-only CUSUM-h calibration on original build_signals z; freeze; DIAG once."""

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
from detector import RECOVERY_RESIDUAL_LE_K, run_all_targets  # noqa: E402
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
H_GRID = [8.0, 16.0, 32.0, 64.0, 128.0, 256.0]
K = 0.5
RESIDUAL_RECOVER_STEPS = 12
UNMATCHED_CAP = 3.0


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    return {
        "settings": dict(settings),
        "period": period.name,
        "runtime_seconds": runtime,
        "n_episodes": len(episodes),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": primary,
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


def select_h(grid: list[dict]) -> tuple[dict | None, bool]:
    eligible = [g for g in grid if g["unmatched_per_week"] <= UNMATCHED_CAP]
    if not eligible:
        return None, False

    def delay_key(g):
        d = g["primary"]["abrupt_delay_hours"]["median"]
        return d if d is not None and np.isfinite(d) else 1e9

    eligible = sorted(
        eligible,
        key=lambda g: (
            -(g["primary"]["abrupt_recall"] if np.isfinite(g["primary"]["abrupt_recall"]) else -1),
            delay_key(g),
            g["unmatched_per_week"],
            g["settings"]["cusum_h"],
        ),
    )
    return eligible[0], True


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("episodes", "sig")}


def write_reconciliation(timestamps, pressures, sensor_ids, leakages) -> dict:
    """Reproduce variant DIAG; contrast with context baseline numbers (read-only)."""
    variant = json.loads((OUT / "variant_comparison_summary.json").read_text())
    context = json.loads((OUT / "context_comparison_summary.json").read_text())
    settings = {
        "train_days": FROZEN_BASE["train_days"],
        "n_refs": FROZEN_BASE["n_refs"],
        "cusum_k": K,
        "cusum_h": 8.0,
        "recover_hours": FROZEN_BASE["recover_hours"],
    }
    repro = evaluate_period(
        pressures, timestamps, sensor_ids, leakages, DIAG, settings
    )
    elig, _ = split_eligible_onsets(
        onsets_in_period(leakages, DIAG),
        train_end_time(timestamps, period_indices(timestamps, DIAG)[0], settings["train_days"]),
    )
    null = null_at_post_hours(
        timestamps,
        repro["episodes"],
        elig,
        leakages,
        repro["analysis_start"],
        repro["analysis_end"],
        post_hours=2.0,
    )
    v = variant["DIAG_variant"]
    c = context["DIAG_baseline"]
    doc = {
        "generated_at": iso_now(),
        "pressures_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "flows_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Flows.csv"),
        "levels_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Levels.csv"),
        "authoritative_signal": "build_signals.z (per-pair normalize then median)",
        "context_baseline_signal": "aggregate raw r then normalize (dual.z_base) — DIFFERENT",
        "reproduction_build_signals_h8": {
            "unmatched_per_week": repro["unmatched_per_week"],
            "n_episodes": repro["n_episodes"],
            "summed_sensor_alarm_pct": repro["occupancy"]["summed_sensor_alarm_pct_of_eligible"],
            "union_alarm_pct": repro["occupancy"]["union_alarm_pct_of_analysis"],
            "null_2h_frac_ge_obs": null["fraction_shifts_ge_observed"],
            "null_2h_obs": null["observed_abrupt_matches"],
            "null_2h_median": null["null_match_median"],
            "z_sha256_16": repro["z_sha256_16"],
        },
        "variant_report": {
            "unmatched_per_week": v["unmatched_per_week"],
            "n_episodes": v["n_episodes"],
            "summed_sensor_alarm_pct": v["occupancy"]["summed_sensor_alarm_pct_of_eligible"],
            "null_2h_frac_ge_obs": variant["variant_null_2h"]["fraction_shifts_ge_observed"],
        },
        "context_baseline_report": {
            "unmatched_per_week": c["unmatched_per_week"],
            "n_episodes": c["n_episodes"],
            "summed_sensor_alarm_pct": c["occupancy"]["summed_sensor_alarm_pct_of_eligible"],
            "null_2h_frac_ge_obs": context["null_2h_baseline"]["fraction_shifts_ge_observed"],
        },
        "delta_repro_minus_variant": {
            "unmatched_per_week": repro["unmatched_per_week"] - v["unmatched_per_week"],
            "summed_sensor_alarm_pct": (
                repro["occupancy"]["summed_sensor_alarm_pct_of_eligible"]
                - v["occupancy"]["summed_sensor_alarm_pct_of_eligible"]
            ),
            "null_2h_frac": (
                null["fraction_shifts_ge_observed"]
                - variant["variant_null_2h"]["fraction_shifts_ge_observed"]
            ),
        },
        "unexplained_differences_remain": False,
        "conclusion": (
            "VARIANT residual-recovery baseline reproduces exactly on build_signals.z. "
            "CONTEXT 'baseline' differed because it used aggregate-then-normalize z_base."
        ),
    }
    (OUT / "baseline_reconciliation.json").write_text(json.dumps(doc, indent=2) + "\n")
    # Markdown already written as BASELINE_RECONCILIATION.md; append repro stamp
    return doc, repro


def render_calibration(summary: dict) -> str:
    lines = [
        "# CUSUM-h calibration — original relationship signal",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Authoritative signal: `build_signals.z` (see `BASELINE_RECONCILIATION.md`). "
        "Context correction not used. Historical VARIANT/CONTEXT/RESULTS reports preserved.",
        "",
        f"Fixed: K={summary['fixed']['n_refs']}, k={summary['fixed']['cusum_k']}, "
        f"residual_recover_steps={summary['fixed']['residual_recover_steps']}, "
        f"train_days={summary['fixed']['train_days']}.",
        f"Provisional unmatched/week cap: **≤ {UNMATCHED_CAP:g}** (not operator-validated).",
        "",
        "## DEV grid (every setting)",
        "",
        "| h | Abrupt recall | Median delay (h) | Unmatched/wk | Dup 24h | "
        "Union occ% | Sensor-alarm% | Longest (h) | Censored | Episodes |",
        "|---|---------------|------------------|--------------|---------|-----------|"
        "---------------|-------------|----------|----------|",
    ]
    for g in summary["DEV_grid"]:
        d = g["primary"]["abrupt_delay_hours"]["median"]
        lines.append(
            f"| {g['settings']['cusum_h']:g} | {g['primary']['abrupt_recall']:.2f} | "
            f"{'' if d is None else f'{d:.3f}'} | {g['unmatched_per_week']:.2f} | "
            f"{g['duplicate_unmatched_within_24h']} | "
            f"{g['occupancy']['union_alarm_pct_of_analysis']:.2f} | "
            f"{g['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f} | "
            f"{g['occupancy']['episode_length_hours']['max']} | "
            f"{g['occupancy']['n_episodes_right_censored']} | {g['n_episodes']} |"
        )
    fr = summary["frozen"]
    lines += [
        "",
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
            "**Selection failure:** no DEV setting met unmatched/week ≤ "
            f"{UNMATCHED_CAP:g}. No invented winner. DIAG not run under a new h.",
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
        f"- Abrupt recall: **{d['primary']['abrupt_recall']:.2f}** "
        f"delays={d['primary']['abrupt_delay_hours']}",
        f"- Incipient recall: **{d['primary']['incipient_recall']:.2f}**",
        f"- Unmatched/wk: **{d['unmatched_per_week']:.2f}**; "
        f"dup: {d['duplicate_unmatched_within_24h']}",
        f"- Union occ%: {d['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
        f"sensor-alarm%: {d['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
        f"- Longest (h): {d['occupancy']['episode_length_hours']['max']}; "
        f"censored: {d['occupancy']['n_episodes_right_censored']}",
        "",
        "Per-event (post-training eligible):",
        "",
    ]
    for m in d["primary"]["matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) notify={m['notify_time']} "
            f"delay_h={m['delay_hours']} sensor={m.get('stream_id')}"
        )
    lines += ["", "Prefix (separate):", ""]
    for m in d["in_prefix_matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(f"- {tag} {m['pipe']} notify={m['notify_time']}")
    n2 = summary["null_2h"]
    lines += [
        "",
        "## 0–2 h notification-time shifted null",
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

    print("Reconciliation / reproduce variant baseline…", flush=True)
    recon, _ = write_reconciliation(
        pb.timestamps, pb.pressures, pb.sensor_ids, leakages
    )
    assert abs(recon["delta_repro_minus_variant"]["unmatched_per_week"]) < 1e-9
    assert abs(recon["delta_repro_minus_variant"]["summed_sensor_alarm_pct"]) < 1e-9
    assert abs(recon["delta_repro_minus_variant"]["null_2h_frac"]) < 1e-9
    print("Reproduction OK — proceeding to DEV h grid.", flush=True)

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
            f"  abrupt={row['primary']['abrupt_recall']:.2f} "
            f"unmatched/wk={row['unmatched_per_week']:.2f} "
            f"union%={row['occupancy']['union_alarm_pct_of_analysis']:.1f} "
            f"sum%={row['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}",
            flush=True,
        )

    chosen, gate = select_h(grid)
    frozen = {
        "frozen_at": iso_now(),
        "gate_met": gate,
        "selected_h": None if not gate else chosen["settings"]["cusum_h"],
        "unmatched_cap": UNMATCHED_CAP,
        "selection_rule": (
            "among unmatched/wk<=3: max abrupt recall, then min median delay, "
            "then min unmatched/wk; else selection failure"
        ),
        "signal": "build_signals.z",
        "fixed": {
            **base_settings,
            "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
            "recovery_mode": RECOVERY_RESIDUAL_LE_K,
        },
        "dev_snapshot": None
        if not gate
        else {
            "abrupt_recall": chosen["primary"]["abrupt_recall"],
            "unmatched_per_week": chosen["unmatched_per_week"],
            "median_delay": chosen["primary"]["abrupt_delay_hours"]["median"],
            "n_episodes": chosen["n_episodes"],
        },
        "note": (
            ""
            if gate
            else "No DEV setting met provisional unmatched/week ≤ 3; DIAG not run for a new h."
        ),
    }
    (OUT / "threshold_frozen.json").write_text(json.dumps(frozen, indent=2) + "\n")
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
        # Compare to authoritative h=8 variant
        v = json.loads((OUT / "variant_comparison_summary.json").read_text())["DIAG_variant"]
        interpretation = (
            f"Frozen h={frozen['selected_h']}: abrupt_recall="
            f"{diag['primary']['abrupt_recall']:.2f}, unmatched/wk="
            f"{diag['unmatched_per_week']:.2f}, union occ%="
            f"{diag['occupancy']['union_alarm_pct_of_analysis']:.1f}, "
            f"sensor-alarm%={diag['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}, "
            f"censored={diag['occupancy']['n_episodes_right_censored']}. "
            f"Relative to authoritative h=8 variant "
            f"(unmatched/wk={v['unmatched_per_week']:.2f}, "
            f"sensor-alarm%={v['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}): "
            "assess whether useful notify timing is preserved while nuisance "
            "notifications/occupancy fall for reasons other than mere latching."
        )
        if diag["occupancy"]["union_alarm_pct_of_analysis"] > 90 and diag["unmatched_per_week"] <= UNMATCHED_CAP:
            interpretation += (
                " Caution: low unmatched/week with near-saturated union occupancy "
                "can reflect latched alarms rather than true nuisance reduction."
            )

    if not gate:
        recommendation = (
            "**Selection failure / no-go on this calibration:** no h in "
            f"{H_GRID} achieved provisional unmatched/week ≤ {UNMATCHED_CAP:g} on DEV "
            "under the fixed residual-recovery policy and original relationship signal. "
            "Do not invent a winner; do not retune recovery or features here."
        )
    else:
        abr = diag["primary"]["abrupt_recall"]
        um = diag["unmatched_per_week"]
        union = diag["occupancy"]["union_alarm_pct_of_analysis"]
        frac_null = null2["fraction_shifts_ge_observed"]
        if abr >= 0.5 and um <= UNMATCHED_CAP and union < 50 and frac_null < 0.5:
            recommendation = (
                "**Conditional research continue:** calibrated h meets DEV workload "
                "gate and shows a usable DIAG sensitivity/burden profile without "
                "relying on saturated latching alone; 0–2h null not dominated by chance. "
                "Still diagnostic — not validated detection."
            )
        elif union >= 90 and um <= UNMATCHED_CAP:
            recommendation = (
                "**No-go:** apparent workload improvement is consistent with latched "
                "network occupancy rather than cleared nuisance structure."
            )
        elif abr < 0.5:
            recommendation = (
                "**No-go:** calibrated h loses abrupt notification recall on DIAG."
            )
        else:
            recommendation = (
                "**Mixed / no-go:** threshold calibration does not clearly preserve "
                "useful timing while reducing nuisance under the declared criteria."
            )

    summary = {
        "generated_at": iso_now(),
        "reconciliation_ok": True,
        "fixed": {
            **base_settings,
            "residual_recover_steps": RESIDUAL_RECOVER_STEPS,
        },
        "DEV_grid": [strip(g) for g in grid],
        "frozen": frozen,
        "DIAG": diag,
        "null_2h": null2,
        "interpretation": interpretation,
        "recommendation": recommendation,
        "holdout_honesty": (
            "DIAG results are diagnostic given prior examination; not a new blind holdout. "
            "2019 not evaluated."
        ),
    }
    (OUT / "threshold_calibration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (OUT / "THRESHOLD_CALIBRATION_RESULTS.md").write_text(
        render_calibration(summary) + "\n"
    )
    print(recommendation, flush=True)
    print(f"Wrote {OUT / 'THRESHOLD_CALIBRATION_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
