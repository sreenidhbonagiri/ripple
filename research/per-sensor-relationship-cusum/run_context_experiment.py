#!/usr/bin/env python3
"""Paired baseline vs context-corrected residuals under residual-recovery CUSUM."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_calibration_separability import (  # noqa: E402
    CONTROL_EXCLUDE_DAYS,
    POST_H,
    PRE_H,
    WINDOW_STEPS,
    select_control_windows,
)
from audit_occupancy_recovery import (  # noqa: E402
    null_at_post_hours,
    occupancy_report,
    split_eligible_onsets,
    train_end_time,
)
from context_residual import FEATURE_NAMES, build_dual_signals  # noqa: E402
from detector import RECOVERY_RESIDUAL_LE_K, run_all_targets  # noqa: E402
from evaluate import (  # noqa: E402
    DEV,
    DIAG,
    iso_now,
    match_episodes,
    onsets_in_period,
    period_indices,
)
from io_data import DEFAULT_RAW, load_context, load_leakages, load_pressures  # noqa: E402
from residual import build_signals  # noqa: E402
from run_residual_recovery_variant import (  # noqa: E402
    duplicate_unmatched,
    recall_block,
)

OUT = ROOT / "outputs"
FROZEN = json.loads((OUT / "frozen_settings.json").read_text())["settings"]
SETTINGS = {
    "train_days": FROZEN["train_days"],
    "n_refs": FROZEN["n_refs"],
    "cusum_k": FROZEN["cusum_k"],
    "cusum_h": FROZEN["cusum_h"],
    "recover_hours": FROZEN["recover_hours"],
    "residual_recover_steps": 12,
    "context_fit_days": 14,
    "context_val_days": 14,
}


def evaluate_z(
    name: str,
    z_mat: np.ndarray,
    analysis_offset: int,
    target_models,
    timestamps,
    sensor_ids,
    leakages,
    period,
    settings: dict,
):
    start_i, end_i = period_indices(timestamps, period)
    train_end = train_end_time(timestamps, start_i, settings["train_days"])
    t0 = time.perf_counter()
    episodes = run_all_targets(
        z_mat,
        sensor_ids,
        target_models,
        analysis_offset=analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=settings["residual_recover_steps"],
    )
    runtime = time.perf_counter() - t0
    all_onsets = onsets_in_period(leakages, period)
    eligible, in_prefix = split_eligible_onsets(all_onsets, train_end)
    prim, used = match_episodes(timestamps, episodes, eligible, leakages)
    prefix, _ = match_episodes(timestamps, episodes, in_prefix, leakages)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(episodes) - len(used)
    occ = occupancy_report(
        timestamps, episodes, analysis_offset, end_i, n_sensors=len(sensor_ids)
    )
    return {
        "name": name,
        "period": period.name,
        "runtime_seconds": runtime,
        "n_episodes": len(episodes),
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": recall_block(prim),
        "in_prefix_matches": prefix,
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
        "analysis_start": analysis_offset,
        "analysis_end": end_i,
        "train_end": str(train_end).replace("T", " "),
    }


def frac_z_gt_k(z_mat: np.ndarray, k: float) -> float:
    m = np.isfinite(z_mat)
    if not m.any():
        return float("nan")
    return float(np.mean(z_mat[m] > k))


def signal_preservation(
    pressures,
    timestamps,
    sensor_ids,
    dual,
    leakages,
    analysis_start,
    analysis_end,
):
    controls = select_control_windows(
        timestamps, analysis_start, analysis_end, leakages, WINDOW_STEPS, n_controls=3
    )
    abrupt = [L for L in onsets_in_period(leakages, DIAG) if L.leak_type == "abrupt"]
    off = dual.analysis_offset
    rows = []
    for L in abrupt:
        center = int(np.searchsorted(timestamps, L.start, side="left"))
        pre = int(PRE_H * 12)
        post = int(POST_H * 12)
        a0 = max(analysis_start, center - pre)
        a1 = min(analysis_end, a0 + WINDOW_STEPS)
        e0, e1 = a0 - off, a1 - off
        onset_local = center - off
        post0 = max(e0, onset_local)
        # Score targets by baseline |delta z| vs controls (no leak-location picking)
        scored = []
        for ti, tm in enumerate(dual.target_models):
            zb = dual.z_base[:, ti]
            zc = dual.z_ctx[:, ti]
            rb = dual.r_raw[:, ti]
            rc = dual.r_corr[:, ti]
            if not np.isfinite(zb[post0:e1]).any():
                continue
            ctrl_zb, ctrl_zc, ctrl_rb, ctrl_rc = [], [], [], []
            for c in controls:
                c0, c1 = c["start_idx"] - off, c["end_idx"] - off
                ctrl_zb.append(zb[c0:c1])
                ctrl_zc.append(zc[c0:c1])
                ctrl_rb.append(rb[c0:c1])
                ctrl_rc.append(rc[c0:c1])
            def med(xs):
                v = np.concatenate([x[np.isfinite(x)] for x in xs if np.isfinite(x).any()])
                return float(np.median(v)) if v.size else float("nan")

            ev_zb = float(np.nanmedian(zb[post0:e1]))
            ev_zc = float(np.nanmedian(zc[post0:e1]))
            ev_rb = float(np.nanmedian(rb[post0:e1]))
            ev_rc = float(np.nanmedian(rc[post0:e1]))
            cb, cc = med(ctrl_zb), med(ctrl_zc)
            crb, crc = med(ctrl_rb), med(ctrl_rc)
            scored.append(
                {
                    "target": sensor_ids[ti],
                    "refs": [sensor_ids[j] for j in tm.refs],
                    "base_delta_z": ev_zb - cb,
                    "ctx_delta_z": ev_zc - cc,
                    "base_delta_raw_m": ev_rb - crb,
                    "ctx_delta_raw_m": ev_rc - crc,
                    "event_base_z": ev_zb,
                    "event_ctx_z": ev_zc,
                    "event_base_raw_m": ev_rb,
                    "event_ctx_raw_m": ev_rc,
                    "control_base_z": cb,
                    "control_ctx_z": cc,
                }
            )
        scored.sort(key=lambda r: abs(r["base_delta_z"]) if np.isfinite(r["base_delta_z"]) else -1, reverse=True)
        top = scored[:5]
        # Explained-away: context shrinks positive leak-oriented delta_z by >50% for top target
        explained = False
        if top:
            t0 = top[0]
            if (
                np.isfinite(t0["base_delta_z"])
                and t0["base_delta_z"] > 1.0
                and np.isfinite(t0["ctx_delta_z"])
                and t0["ctx_delta_z"] < 0.5 * t0["base_delta_z"]
            ):
                explained = True
        rows.append(
            {
                "pipe": L.pipe,
                "onset": str(L.start).replace("T", " "),
                "controls": [c["start_time"] for c in controls],
                "top": top,
                "context_explains_away_top_signal": explained,
            }
        )

    # Ordinary pump transitions vs stable: sample large |ΔPUMP| vs small
    # (diagnostic only)
    return {
        "control_rule": {
            "window_steps": WINDOW_STEPS,
            "pre_hours": PRE_H,
            "post_hours": POST_H,
            "onset_exclude_days": CONTROL_EXCLUDE_DAYS,
            "controls": controls,
        },
        "abrupt_events": rows,
        "note": "Diagnostic examples only; not independent validation.",
    }


def pump_transition_check(timestamps, pump1, dual, analysis_start, analysis_end):
    """Compare |z| near large pump steps vs stable periods (ordinary ops)."""
    off = dual.analysis_offset
    p = pump1[analysis_start:analysis_end]
    dp = np.abs(np.diff(p, prepend=p[0]))
    large = dp > np.nanpercentile(dp[np.isfinite(dp)], 95)
    stable = dp < np.nanpercentile(dp[np.isfinite(dp)], 50)
    # mean abs z across sensors
    def mean_abs(z, mask):
        # mask on analysis-relative
        vals = []
        for ti in range(z.shape[1]):
            col = z[mask, ti]
            col = col[np.isfinite(col)]
            if col.size:
                vals.append(float(np.mean(np.abs(col))))
        return float(np.mean(vals)) if vals else float("nan")

    # align mask length with z rows
    n = dual.z_base.shape[0]
    large = large[:n]
    stable = stable[:n]
    return {
        "mean_abs_z_base_large_pump_delta": mean_abs(dual.z_base, large),
        "mean_abs_z_ctx_large_pump_delta": mean_abs(dual.z_ctx, large),
        "mean_abs_z_base_stable_pump": mean_abs(dual.z_base, stable),
        "mean_abs_z_ctx_stable_pump": mean_abs(dual.z_ctx, stable),
    }


def recommend(dev_b, dev_c, diag_b, diag_c, null_b, null_c, preserv, frac_b, frac_c) -> str:
    lines = [
        f"DIAG abrupt recall base={diag_b['primary']['abrupt_recall']:.2f} "
        f"ctx={diag_c['primary']['abrupt_recall']:.2f}; "
        f"unmatched/wk {diag_b['unmatched_per_week']:.1f}→{diag_c['unmatched_per_week']:.1f}; "
        f"union occ% {diag_b['occupancy']['union_alarm_pct_of_analysis']:.1f}→"
        f"{diag_c['occupancy']['union_alarm_pct_of_analysis']:.1f}; "
        f"summed sensor-alarm% {diag_b['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}→"
        f"{diag_c['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}; "
        f"frac(z>k) {frac_b:.3f}→{frac_c:.3f}."
    ]
    lines.append(
        f"0–2h null frac≥obs: base={null_b['fraction_shifts_ge_observed']:.2f} "
        f"(obs={null_b['observed_abrupt_matches']}, "
        f"null med={null_b['null_match_median']}, "
        f"n_shifts={null_b['null_n_valid_shifts']}); "
        f"ctx={null_c['fraction_shifts_ge_observed']:.2f} "
        f"(obs={null_c['observed_abrupt_matches']}, "
        f"null med={null_c['null_match_median']})."
    )
    explained = sum(
        1 for e in preserv["abrupt_events"] if e["context_explains_away_top_signal"]
    )
    if explained >= 2:
        return (
            "**No-go:** context correction explains away leak-timed residual contrast "
            f"on {explained}/3 abrupt DIAG examples. " + " ".join(lines)
        )
    better_burden = (
        diag_c["unmatched_per_week"] < 0.7 * diag_b["unmatched_per_week"]
        and diag_c["occupancy"]["union_alarm_pct_of_analysis"]
        < 0.9 * diag_b["occupancy"]["union_alarm_pct_of_analysis"]
    )
    hold_sens = diag_c["primary"]["abrupt_recall"] >= diag_b["primary"]["abrupt_recall"] - 1e-9
    beat_null = null_c["fraction_shifts_ge_observed"] < 0.5
    if hold_sens and better_burden and beat_null and explained == 0:
        return (
            "**Conditional continue:** context correction improves burden without "
            "losing abrupt notify recall or explaining away events, and beats the "
            "0–2h descriptive null. Still diagnostic — not validated leak detection. "
            + " ".join(lines)
        )
    if frac_c >= frac_b * 0.9 and not better_burden:
        return (
            "**No-go:** context correction fails to meaningfully reduce ordinary "
            "excursions / alert burden under the fixed residual-recovery policy. "
            + " ".join(lines)
        )
    return (
        "**No-go / mixed:** context correction does not clearly improve the "
        "sensitivity–burden tradeoff without broad matching or latched-alarm reliance. "
        f"Events explained away: {explained}/3. " + " ".join(lines)
    )


def strip(r):
    return {k: v for k, v in r.items() if k != "episodes"}


def render(summary: dict) -> str:
    lines = [
        "# Context-conditioned residual experiment — paired results",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Prior detectors and negative results preserved. Design: `CONTEXT_DESIGN.md`.",
        "Notification policy: residual-recovery (`z≤k` ×12); **not swept**.",
        "",
        f"Frozen alpha (DEV chronological val): **{summary['frozen_alpha']}**",
        f"Alpha DEV scores (mean RMSE m): {summary['dev_alpha_scores']}",
        "",
        "## DEV (recorded before DIAG)",
        "",
    ]
    for key in ("DEV_baseline", "DEV_context"):
        r = summary[key]
        lines += [
            f"### {r['name']}",
            f"- Abrupt recall: **{r['primary']['abrupt_recall']:.2f}** "
            f"delays={r['primary']['abrupt_delay_hours']}",
            f"- Incipient: **{r['primary']['incipient_recall']:.2f}**",
            f"- Unmatched/wk: **{r['unmatched_per_week']:.2f}**; "
            f"dup: {r['duplicate_unmatched_within_24h']}",
            f"- Union occ%: {r['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
            f"summed sensor-alarm%: {r['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
            f"- Longest (h): {r['occupancy']['episode_length_hours']['max']}; "
            f"censored: {r['occupancy']['n_episodes_right_censored']}",
            "",
        ]
    lines += ["## DIAG (diagnostic — not independent validation)", ""]
    for key in ("DIAG_baseline", "DIAG_context"):
        r = summary[key]
        lines += [
            f"### {r['name']}",
            f"- Abrupt recall: **{r['primary']['abrupt_recall']:.2f}** "
            f"delays={r['primary']['abrupt_delay_hours']}",
            f"- Incipient: **{r['primary']['incipient_recall']:.2f}**",
            f"- Unmatched/wk: **{r['unmatched_per_week']:.2f}**; "
            f"dup: {r['duplicate_unmatched_within_24h']}",
            f"- Union occ%: {r['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
            f"summed%: {r['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
            f"- Longest (h): {r['occupancy']['episode_length_hours']['max']}; "
            f"censored: {r['occupancy']['n_episodes_right_censored']}",
            "",
        ]
        for m in r["primary"]["matches"]:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(
                f"- {tag} {m['pipe']} ({m['leak_type']}) notify={m['notify_time']} "
                f"delay_h={m['delay_hours']} sensor={m.get('stream_id')}"
            )
        lines += ["", "Prefix (separate):", ""]
        for m in r["in_prefix_matches"]:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(f"- {tag} {m['pipe']} notify={m['notify_time']}")
        lines.append("")

    lines += [
        f"Ordinary frac(z>k): baseline={summary['diag_frac_z_gt_k_baseline']:.3f}, "
        f"context={summary['diag_frac_z_gt_k_context']:.3f}",
        "",
        "## Signal preservation (abrupt DIAG)",
        "",
    ]
    for e in summary["signal_preservation"]["abrupt_events"]:
        lines.append(
            f"### {e['pipe']} — explains_away={e['context_explains_away_top_signal']}"
        )
        if e["top"]:
            lines.append(
                "| Target | Δz base | Δz ctx | Δraw base (m) | Δraw ctx (m) |"
            )
            lines.append("|--------|---------|--------|---------------|--------------|")
            for t in e["top"][:3]:
                lines.append(
                    f"| {t['target']} | {t['base_delta_z']:.2f} | {t['ctx_delta_z']:.2f} | "
                    f"{t['base_delta_raw_m']:.3f} | {t['ctx_delta_raw_m']:.3f} |"
                )
        lines.append("")
    lines += [
        "## Pump transition vs stable (ordinary)",
        str(summary["pump_transition"]),
        "",
        "## 0–2 h notification shifted null",
        f"- Baseline: {summary['null_2h_baseline']}",
        f"- Context: {summary['null_2h_context']}",
        "",
        "## Recommendation",
        "",
        summary["recommendation"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    print("Loading…", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    ctx = load_context(DEFAULT_RAW)
    leakages = load_leakages()
    assert np.array_equal(pb.timestamps, ctx.timestamps)
    pump_j = ctx.flow_ids.index("PUMP_1")
    t1_j = ctx.level_ids.index("T1")
    pump1 = ctx.flows[:, pump_j]
    tank = ctx.levels[:, t1_j]
    timestamps = pb.timestamps
    sensor_ids = pb.sensor_ids

    # --- DEV: select alpha, record ---
    print("DEV pairwise + dual signals (select alpha)…", flush=True)
    d0, d1 = period_indices(timestamps, DEV)
    sig_dev = build_signals(
        pb.pressures,
        interval_start=d0,
        interval_end=d1,
        train_days=SETTINGS["train_days"],
        n_refs=SETTINGS["n_refs"],
    )
    dual_dev, meta_dev = build_dual_signals(
        pb.pressures,
        timestamps,
        pump1,
        tank,
        sig_dev.target_models,
        interval_start=d0,
        interval_end=d1,
        pair_train_days=SETTINGS["train_days"],
        context_fit_days=SETTINGS["context_fit_days"],
        context_val_days=SETTINGS["context_val_days"],
        select_alpha=True,
    )
    alpha = dual_dev.alpha
    print(f"Froze alpha={alpha} scores={meta_dev['alpha_scores_mean_rmse']}", flush=True)
    (OUT / "context_frozen.json").write_text(
        json.dumps(
            {
                "frozen_at": iso_now(),
                "alpha": alpha,
                "settings": SETTINGS,
                "dev_alpha_scores_mean_rmse": meta_dev["alpha_scores_mean_rmse"],
                "features": FEATURE_NAMES,
            },
            indent=2,
        )
        + "\n"
    )

    print("DEV evaluate…", flush=True)
    dev_b = evaluate_z(
        "baseline_raw_residual",
        dual_dev.z_base,
        dual_dev.analysis_offset,
        sig_dev.target_models,
        timestamps,
        sensor_ids,
        leakages,
        DEV,
        SETTINGS,
    )
    dev_c = evaluate_z(
        "context_corrected",
        dual_dev.z_ctx,
        dual_dev.analysis_offset,
        sig_dev.target_models,
        timestamps,
        sensor_ids,
        leakages,
        DEV,
        SETTINGS,
    )
    (OUT / "context_dev_snapshot.json").write_text(
        json.dumps(
            {
                "recorded_at": iso_now(),
                "alpha": alpha,
                "DEV_baseline": strip(dev_b),
                "DEV_context": strip(dev_c),
            },
            indent=2,
        )
        + "\n"
    )

    # --- DIAG frozen alpha ---
    print("DIAG pairwise + dual signals…", flush=True)
    g0, g1 = period_indices(timestamps, DIAG)
    sig_diag = build_signals(
        pb.pressures,
        interval_start=g0,
        interval_end=g1,
        train_days=SETTINGS["train_days"],
        n_refs=SETTINGS["n_refs"],
    )
    dual_diag, meta_diag = build_dual_signals(
        pb.pressures,
        timestamps,
        pump1,
        tank,
        sig_diag.target_models,
        interval_start=g0,
        interval_end=g1,
        pair_train_days=SETTINGS["train_days"],
        context_fit_days=SETTINGS["context_fit_days"],
        context_val_days=SETTINGS["context_val_days"],
        alpha=alpha,
        select_alpha=False,
    )
    print("DIAG evaluate…", flush=True)
    diag_b = evaluate_z(
        "baseline_raw_residual",
        dual_diag.z_base,
        dual_diag.analysis_offset,
        sig_diag.target_models,
        timestamps,
        sensor_ids,
        leakages,
        DIAG,
        SETTINGS,
    )
    diag_c = evaluate_z(
        "context_corrected",
        dual_diag.z_ctx,
        dual_diag.analysis_offset,
        sig_diag.target_models,
        timestamps,
        sensor_ids,
        leakages,
        DIAG,
        SETTINGS,
    )

    eligible, _ = split_eligible_onsets(
        onsets_in_period(leakages, DIAG),
        train_end_time(timestamps, g0, SETTINGS["train_days"]),
    )
    null_b = null_at_post_hours(
        timestamps,
        diag_b["episodes"],
        eligible,
        leakages,
        diag_b["analysis_start"],
        diag_b["analysis_end"],
        post_hours=2.0,
    )
    null_c = null_at_post_hours(
        timestamps,
        diag_c["episodes"],
        eligible,
        leakages,
        diag_c["analysis_start"],
        diag_c["analysis_end"],
        post_hours=2.0,
    )

    preserv = signal_preservation(
        pb.pressures,
        timestamps,
        sensor_ids,
        dual_diag,
        leakages,
        dual_diag.analysis_offset,
        g1,
    )
    pump_tr = pump_transition_check(
        timestamps, pump1, dual_diag, dual_diag.analysis_offset, g1
    )
    frac_b = frac_z_gt_k(dual_diag.z_base, SETTINGS["cusum_k"])
    frac_c = frac_z_gt_k(dual_diag.z_ctx, SETTINGS["cusum_k"])

    summary = {
        "generated_at": iso_now(),
        "holdout_honesty": "DIAG is diagnostic, not independent validation; 2019 not evaluated.",
        "frozen_alpha": alpha,
        "dev_alpha_scores": meta_dev["alpha_scores_mean_rmse"],
        "settings": SETTINGS,
        "DEV_baseline": strip(dev_b),
        "DEV_context": strip(dev_c),
        "DIAG_baseline": strip(diag_b),
        "DIAG_context": strip(diag_c),
        "diag_frac_z_gt_k_baseline": frac_b,
        "diag_frac_z_gt_k_context": frac_c,
        "signal_preservation": preserv,
        "pump_transition": pump_tr,
        "null_2h_baseline": null_b,
        "null_2h_context": null_c,
        "recommendation": recommend(
            dev_b, dev_c, diag_b, diag_c, null_b, null_c, preserv, frac_b, frac_c
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "context_comparison_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (OUT / "CONTEXT_COMPARISON.md").write_text(render(summary) + "\n")
    print(summary["recommendation"], flush=True)
    print(f"Wrote {OUT / 'CONTEXT_COMPARISON.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
