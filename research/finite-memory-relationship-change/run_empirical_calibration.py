#!/usr/bin/env python3
"""Empirical percentile threshold calibration on frozen LQ=2h, LR=48h.

Does not overwrite outputs/RESULTS.md (original heuristic-τ grid).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from audit_occupancy_recovery import (  # noqa: E402
    null_at_post_hours,
    occupancy_report,
    split_eligible_onsets,
    train_end_time,
)
from evaluate import DEV, DIAG, iso_now, match_episodes, onsets_in_period, period_indices  # noqa: E402
from io_data import DEFAULT_RAW, load_leakages, load_pressures  # noqa: E402
from run_residual_recovery_variant import duplicate_unmatched, recall_block  # noqa: E402

import importlib.util  # noqa: E402


def _load_local(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"fmr3c_emp_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_windows = _load_local("windows")
_scale = _load_local("scale")
sys.modules["windows"] = _windows
sys.modules["scale"] = _scale
_detector = _load_local("detector")
_signals = _load_local("signals")

RECOVER_STEPS = _detector.RECOVER_STEPS
build_score_bundle = _detector.build_score_bundle
run_all_targets_from_scores = _detector.run_all_targets_from_scores
build_period_signals = _signals.build_period_signals

OUT = ROOT / "outputs"
TRAIN_DAYS = 14
N_REFS = 3
L_Q = 2.0
L_R = 48.0
PERCENTILES = [99.0, 99.5, 99.9, 99.95, 99.99]
UNMATCHED_CAP = 3.0
ABRUPT_6H_MIN = 2.0 / 3.0
DOMINANCE_WARN = 0.25


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def abrupt_6h(matches: list[dict]) -> dict:
    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    n = len(abrupt)
    hits = [
        m
        for m in abrupt
        if m["matched"]
        and m["delay_hours"] is not None
        and m["delay_hours"] <= 6.0 + 1e-12
    ]
    delays = [m["delay_hours"] for m in hits]
    return {
        "n_abrupt": n,
        "n_hit": len(hits),
        "recall": (len(hits) / n) if n else float("nan"),
        "delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
            "values": delays,
        },
    }


def latch_note(row: dict) -> dict:
    occ = row["occupancy"]
    union = occ["union_alarm_pct_of_analysis"]
    um = row["unmatched_per_week"]
    n_ep = row["n_episodes"]
    cens = occ["n_episodes_right_censored"]
    longest = occ["episode_length_hours"]["max"] or 0
    latched = bool(
        um <= UNMATCHED_CAP
        and (union >= 90.0 or (n_ep > 0 and cens / n_ep >= 0.25 and longest >= 500))
    )
    return {
        "latched_suspect": latched,
        "union_pct": union,
        "sensor_pct": occ["summed_sensor_alarm_pct_of_eligible"],
        "note": (
            "Low unmatched with high union / long censored episodes can reflect "
            "latched alarms rather than cleared nuisance."
            if latched
            else "No strong latched-only signature under declared heuristics."
        ),
    }


def pool_dev_scores(score_bundle: dict) -> dict:
    contrib = []
    chunks = []
    for sid, info in score_bundle["per_target"].items():
        s = info["s"]
        finite = s[np.isfinite(s)]
        contrib.append(
            {
                "sensor": sid,
                "n_finite": int(finite.size),
                "median": float(np.median(finite)) if finite.size else None,
                "p99": float(np.quantile(finite, 0.99)) if finite.size else None,
                "max": float(np.max(finite)) if finite.size else None,
            }
        )
        chunks.append(finite)
    pooled = np.concatenate(chunks) if chunks else np.array([], dtype=np.float64)
    n_tot = int(pooled.size)
    for c in contrib:
        c["fraction"] = (c["n_finite"] / n_tot) if n_tot else 0.0
    contrib = sorted(contrib, key=lambda x: -x["n_finite"])
    dominant = [c for c in contrib if c["fraction"] > DOMINANCE_WARN]
    thresholds = {}
    for p in PERCENTILES:
        thresholds[str(p)] = float(np.quantile(pooled, p / 100.0)) if n_tot else float("nan")
    return {
        "n_pooled_finite": n_tot,
        "n_eligible_sensors": len(score_bundle["per_target"]),
        "sensor_contributions": contrib,
        "dominance_warning_fraction": DOMINANCE_WARN,
        "dominant_sensors": dominant,
        "dominance_warning": bool(dominant),
        "dominance_note": (
            f"Sensor(s) exceed {DOMINANCE_WARN:.0%} of pooled finite scores; "
            "not removed — difficult sensors retained."
            if dominant
            else "No sensor exceeds dominance warning fraction of pooled mass."
        ),
        "caveat": (
            "DEV pooled scores include leaks and operating changes; percentiles "
            "are not leak-free FP calibration. Sample exceedance ≠ notification "
            "burden under temporal correlation / episode semantics."
        ),
        "percentile_thresholds": thresholds,
        "pooled_summary": {
            "median": float(np.median(pooled)) if n_tot else None,
            "p90": float(np.quantile(pooled, 0.90)) if n_tot else None,
            "max": float(np.max(pooled)) if n_tot else None,
        },
    }


def evaluate_episodes(
    timestamps,
    sensor_ids,
    leakages,
    period,
    episodes,
    *,
    analysis_offset: int,
    analysis_end: int,
    settings: dict,
    z_sha: str,
    n_eligible: int,
):
    start_i, end_i = period_indices(timestamps, period)
    train_end = train_end_time(timestamps, start_i, TRAIN_DAYS)
    eligible, in_prefix = split_eligible_onsets(
        onsets_in_period(leakages, period), train_end
    )
    prim, used = match_episodes(timestamps, episodes, eligible, leakages)
    prefix, _ = match_episodes(timestamps, episodes, in_prefix, leakages)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(episodes) - len(used)
    occ = occupancy_report(
        timestamps, episodes, analysis_offset, analysis_end, n_sensors=len(sensor_ids)
    )
    row = {
        "settings": settings,
        "period": period.name,
        "n_episodes": len(episodes),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": recall_block(prim),
        "abrupt_6h": abrupt_6h(prim),
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
        "n_eligible_sensors": n_eligible,
        "z_sha256_16": z_sha,
        "episodes": episodes,
        "analysis_start": analysis_offset,
        "analysis_end": analysis_end,
    }
    row["latch"] = latch_note(row)
    return row


def select_setting(grid: list[dict]) -> tuple[dict | None, bool]:
    eligible = [
        g
        for g in grid
        if g["unmatched_per_week"] <= UNMATCHED_CAP
        and (g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1)
        >= ABRUPT_6H_MIN - 1e-12
        and not g["latch"]["latched_suspect"]
    ]
    if not eligible:
        return None, False

    def delay_key(g):
        d = g["abrupt_6h"]["delay_hours"]["median"]
        return d if d is not None and np.isfinite(d) else 1e9

    eligible = sorted(
        eligible,
        key=lambda g: (
            -(g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1),
            g["unmatched_per_week"],
            delay_key(g),
            g["settings"]["tau"],
        ),
    )
    return eligible[0], True


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("episodes",)}


def render(summary: dict) -> str:
    lines = [
        "# FMR3C empirical threshold calibration — DEV percentiles",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Preserves `RESULTS.md` (heuristic τ grid) and all other experiments. "
        "Production untouched. 2019 not evaluated.",
        "",
        "## Cumulative development history",
        "",
        "1. Registered FMR3C design (finite-memory recent–reference on `build_signals.z`).",
        "2. Original 16-cell heuristic τ∈{3,4,5,6} × LQ/LR grid → **selection failure** "
        "(abrupt 6h=1.00 but unmatched/wk ≥ 56.8); see `RESULTS.md`.",
        "3. **This calibration:** freeze LQ=2h, LR=48h (additional DEV decision from "
        "lowest unmatched among that grid); derive common τ from DEV pooled score "
        "percentiles; full episode pipeline per threshold.",
        "",
        f"Frozen windows: LQ={L_Q:g}h, LR={L_R:g}h. "
        "AR(1)-standardized scores are **not** confidence levels.",
        f"Provisional gates: abrupt 6h ≥ {ABRUPT_6H_MIN:.4f}, unmatched/wk ≤ {UNMATCHED_CAP:g}.",
        "",
        "## Input hashes",
        "",
    ]
    for k, v in summary["input_hashes"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        f"- DEV z sha256[:16]: `{summary['dev_z_sha256_16']}`",
        "",
        "## Pooled DEV score distribution",
        "",
        f"- n_pooled_finite: **{summary['pool']['n_pooled_finite']}** across "
        f"{summary['pool']['n_eligible_sensors']} eligible sensors",
        f"- pooled median / p90 / max: {summary['pool']['pooled_summary']}",
        f"- Dominance: {summary['pool']['dominance_note']}",
        "",
        summary["pool"]["caveat"],
        "",
        "### Per-sensor contribution (top by count)",
        "",
        "| Sensor | n_finite | fraction | median | p99 | max |",
        "|--------|----------|----------|--------|-----|-----|",
    ]
    for c in summary["pool"]["sensor_contributions"][:15]:
        lines.append(
            f"| {c['sensor']} | {c['n_finite']} | {c['fraction']:.3f} | "
            f"{c['median']} | {c['p99']} | {c['max']} |"
        )
    if len(summary["pool"]["sensor_contributions"]) > 15:
        lines.append(
            f"| … | ({len(summary['pool']['sensor_contributions']) - 15} more) | | | | |"
        )
    lines += [
        "",
        "### Empirical thresholds",
        "",
        "| Percentile | τ |",
        "|------------|---|",
    ]
    for p in PERCENTILES:
        lines.append(f"| {p:g} | {summary['pool']['percentile_thresholds'][str(p)]} |")

    lines += [
        "",
        "## DEV tradeoff (full episode pipeline)",
        "",
        "| pct | τ | Emp. exceed | Abrupt6h | Unmatched/wk | Dup | Union% | "
        "Sensor% | Med/Longest (h) | Censored | Episodes | Latch? |",
        "|-----|---|-------------|----------|--------------|-----|--------|"
        "---------|-----------------|----------|----------|--------|",
    ]
    for g in summary["DEV_grid"]:
        s = g["settings"]
        med = g["occupancy"]["episode_length_hours"]["median"]
        longest = g["occupancy"]["episode_length_hours"]["max"]
        lines.append(
            f"| {s['percentile']:g} | {s['tau']:.6g} | {g['empirical_exceedance_rate']:.6f} | "
            f"{g['abrupt_6h']['recall']:.2f} | {g['unmatched_per_week']:.2f} | "
            f"{g['duplicate_unmatched_within_24h']} | "
            f"{g['occupancy']['union_alarm_pct_of_analysis']:.2f} | "
            f"{g['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f} | "
            f"{'' if med is None else f'{med:.1f}'}/{longest} | "
            f"{g['occupancy']['n_episodes_right_censored']} | {g['n_episodes']} | "
            f"{'yes' if g['latch']['latched_suspect'] else 'no'} |"
        )

    fr = summary["frozen"]
    lines += [
        "",
        "## Selection",
        "",
        f"- gate_met: **{fr['gate_met']}**",
        f"- selected: **{fr.get('selected')}**",
        f"- rule: {fr['selection_rule']}",
        f"- note: {fr.get('note', '')}",
        "",
    ]
    if not fr["gate_met"]:
        lines += [
            "**Selection failure:** no empirical percentile threshold met both "
            "provisional gates without a latched-only signature. No further "
            "threshold extension; DIAG not run.",
            "",
            "## Recommendation",
            "",
            summary["recommendation"],
            "",
        ]
        return "\n".join(lines)

    d = summary["DIAG"]
    lines += [
        "## DIAG (frozen numeric τ — diagnostic; prior examination)",
        "",
        f"- Threshold frozen from DEV: τ={d['settings']['tau']} "
        f"(percentile {d['settings']['percentile']}); **not** recomputed on DIAG.",
        f"- Abrupt 6h recall: **{d['abrupt_6h']['recall']:.2f}** "
        f"({d['abrupt_6h']['n_hit']}/{d['abrupt_6h']['n_abrupt']})",
        f"- Abrupt recall (7d window): **{d['primary']['abrupt_recall']:.2f}** "
        f"delays={d['primary']['abrupt_delay_hours']}",
        f"- Incipient: **{d['primary']['incipient_recall']:.2f}**",
        f"- Unmatched/wk: **{d['unmatched_per_week']:.2f}**; "
        f"dup: {d['duplicate_unmatched_within_24h']}",
        f"- Union%: {d['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
        f"sensor%: {d['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
        f"- Median/longest ep (h): "
        f"{d['occupancy']['episode_length_hours']['median']}/"
        f"{d['occupancy']['episode_length_hours']['max']}; "
        f"censored: {d['occupancy']['n_episodes_right_censored']}",
        f"- Latch: {d['latch']['note']}",
        "",
        "Per-event (post-training):",
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
    for label, key in (("0–2 h", "null_2h"), ("0–6 h", "null_6h")):
        n = summary[key]
        lines += [
            "",
            f"## Notification-time shifted null — {label} (diagnostic)",
            "",
            f"- Observed abrupt matches: **{n['observed_abrupt_matches']}** / "
            f"{n['n_abrupt_onsets']}",
            f"- Null median (min–max): {n['null_match_median']} "
            f"({n['null_match_min']}–{n['null_match_max']})",
            f"- Frac shifts ≥ obs: **{n['fraction_shifts_ge_observed']:.2f}** "
            f"(n_shifts={n['null_n_valid_shifts']})",
            "",
            n["caveat"],
        ]
    lines += [
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

    print(f"DEV build_signals + scores once (LQ={L_Q}, LR={L_R})…", flush=True)
    d0, d1 = period_indices(pb.timestamps, DEV)
    sig_dev, train_z_dev, _, _ = build_period_signals(
        pb.pressures, interval_start=d0, interval_end=d1, train_days=TRAIN_DAYS, n_refs=N_REFS
    )
    z_sha = hashlib.sha256(np.ascontiguousarray(sig_dev.z).tobytes()).hexdigest()[:16]
    scores_dev = build_score_bundle(
        sig_dev.z,
        pb.sensor_ids,
        sig_dev.target_models,
        analysis_offset=sig_dev.analysis_offset,
        train_z=train_z_dev,
        l_q_hours=L_Q,
        l_r_hours=L_R,
    )
    pool = pool_dev_scores(scores_dev)
    print(
        f"Pooled n={pool['n_pooled_finite']}; dominance={pool['dominance_warning']}; "
        f"thresholds={pool['percentile_thresholds']}",
        flush=True,
    )
    (OUT / "empirical_pool_dev.json").write_text(json.dumps(pool, indent=2) + "\n")

    # Flatten all finite for exceedance rate
    all_finite = np.concatenate(
        [info["s"][np.isfinite(info["s"])] for info in scores_dev["per_target"].values()]
    )

    grid = []
    for p in PERCENTILES:
        tau = pool["percentile_thresholds"][str(p)]
        print(f"DEV episode pipeline percentile={p} tau={tau:.6g}…", flush=True)
        t0 = time.perf_counter()
        episodes = run_all_targets_from_scores(scores_dev, tau=tau)
        runtime = time.perf_counter() - t0
        exceed = float(np.mean(all_finite >= tau)) if all_finite.size else float("nan")
        row = evaluate_episodes(
            pb.timestamps,
            pb.sensor_ids,
            leakages,
            DEV,
            episodes,
            analysis_offset=sig_dev.analysis_offset,
            analysis_end=d1,
            settings={
                "l_q_hours": L_Q,
                "l_r_hours": L_R,
                "tau": tau,
                "percentile": p,
                "recover_steps": RECOVER_STEPS,
                "train_days": TRAIN_DAYS,
                "n_refs": N_REFS,
                "threshold_source": "DEV_pooled_empirical_percentile",
            },
            z_sha=z_sha,
            n_eligible=len(scores_dev["per_target"]),
        )
        row["runtime_seconds"] = runtime
        row["empirical_exceedance_rate"] = exceed
        grid.append(row)
        print(
            f"  abrupt6h={row['abrupt_6h']['recall']:.2f} "
            f"unmatched/wk={row['unmatched_per_week']:.2f} "
            f"union%={row['occupancy']['union_alarm_pct_of_analysis']:.1f} "
            f"exceed={exceed:.6f}",
            flush=True,
        )

    chosen, gate = select_setting(grid)
    # Also note numeric-only gate without latch filter for transparency
    numeric_ok = [
        g
        for g in grid
        if g["unmatched_per_week"] <= UNMATCHED_CAP
        and (g["abrupt_6h"]["recall"] if np.isfinite(g["abrupt_6h"]["recall"]) else -1)
        >= ABRUPT_6H_MIN - 1e-12
    ]
    frozen = {
        "frozen_at": iso_now(),
        "gate_met": gate,
        "signal": {"l_q_hours": L_Q, "l_r_hours": L_R, "decision": "additional_dev_from_prior_grid"},
        "selected": None
        if not gate
        else {
            "percentile": chosen["settings"]["percentile"],
            "tau": chosen["settings"]["tau"],
        },
        "unmatched_cap": UNMATCHED_CAP,
        "abrupt_6h_min": ABRUPT_6H_MIN,
        "selection_rule": (
            "among abrupt6h>=2/3 and unmatched/wk<=3 and not latched_suspect: "
            "max abrupt6h recall, then min unmatched/wk, then min median 6h delay"
        ),
        "numeric_gate_met_count": len(numeric_ok),
        "dev_snapshot": None
        if not gate
        else {
            "abrupt_6h_recall": chosen["abrupt_6h"]["recall"],
            "unmatched_per_week": chosen["unmatched_per_week"],
            "median_delay_6h": chosen["abrupt_6h"]["delay_hours"]["median"],
            "union_pct": chosen["occupancy"]["union_alarm_pct_of_analysis"],
        },
        "note": (
            ""
            if gate
            else (
                "No DEV empirical percentile met both provisional gates without "
                "latched-only signature; no further threshold extension; DIAG not run."
            )
        ),
    }
    (OUT / "empirical_frozen.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(f"Froze gate_met={gate} selected={frozen['selected']}", flush=True)

    diag = null2 = null6 = None
    interpretation = ""
    if gate:
        print("DIAG once at frozen numeric tau (not recomputed)…", flush=True)
        s = frozen["selected"]
        g0, g1 = period_indices(pb.timestamps, DIAG)
        sig_diag, train_z_diag, _, _ = build_period_signals(
            pb.pressures, interval_start=g0, interval_end=g1, train_days=TRAIN_DAYS, n_refs=N_REFS
        )
        scores_diag = build_score_bundle(
            sig_diag.z,
            pb.sensor_ids,
            sig_diag.target_models,
            analysis_offset=sig_diag.analysis_offset,
            train_z=train_z_diag,
            l_q_hours=L_Q,
            l_r_hours=L_R,
        )
        episodes = run_all_targets_from_scores(scores_diag, tau=s["tau"])
        diag_full = evaluate_episodes(
            pb.timestamps,
            pb.sensor_ids,
            leakages,
            DIAG,
            episodes,
            analysis_offset=sig_diag.analysis_offset,
            analysis_end=g1,
            settings={
                "l_q_hours": L_Q,
                "l_r_hours": L_R,
                "tau": s["tau"],
                "percentile": s["percentile"],
                "recover_steps": RECOVER_STEPS,
                "train_days": TRAIN_DAYS,
                "n_refs": N_REFS,
                "threshold_source": "frozen_from_DEV_percentile",
            },
            z_sha=hashlib.sha256(np.ascontiguousarray(sig_diag.z).tobytes()).hexdigest()[:16],
            n_eligible=len(scores_diag["per_target"]),
        )
        elig, _ = split_eligible_onsets(
            onsets_in_period(leakages, DIAG),
            train_end_time(pb.timestamps, g0, TRAIN_DAYS),
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
        null6 = null_at_post_hours(
            pb.timestamps,
            diag_full["episodes"],
            elig,
            leakages,
            diag_full["analysis_start"],
            diag_full["analysis_end"],
            post_hours=6.0,
        )
        diag = strip(diag_full)
        interpretation = (
            f"Frozen τ={s['tau']} from DEV p{s['percentile']} (diagnostic): "
            f"abrupt6h={diag['abrupt_6h']['recall']:.2f}, "
            f"unmatched/wk={diag['unmatched_per_week']:.2f}, "
            f"union%={diag['occupancy']['union_alarm_pct_of_analysis']:.1f}. "
            f"{diag['latch']['note']}"
        )

    if not gate:
        recommendation = (
            "**Selection failure / no-go:** no DEV pooled-score percentile in "
            f"{PERCENTILES} yielded both abrupt 6h recall ≥ {ABRUPT_6H_MIN:.4f} and "
            f"unmatched/week ≤ {UNMATCHED_CAP:g} without latched-only signature under "
            f"frozen LQ={L_Q:g}h, LR={L_R:g}h. Historical excursions are not extreme "
            "enough relative to leak-associated scores for useful notifications at "
            "these provisional targets. Do not invent a winner; do not extend "
            "percentiles further here."
        )
    else:
        abr = diag["abrupt_6h"]["recall"]
        um = diag["unmatched_per_week"]
        latched = diag["latch"]["latched_suspect"]
        union = diag["occupancy"]["union_alarm_pct_of_analysis"]
        if abr >= ABRUPT_6H_MIN and um <= UNMATCHED_CAP and not latched and union < 50:
            recommendation = (
                "**Conditional research continue:** empirical τ meets DEV dual gates "
                "and a usable DIAG profile without clear latching-only success. "
                "Still diagnostic — not validated detection."
            )
        elif latched or (union >= 90 and um <= UNMATCHED_CAP):
            recommendation = (
                "**No-go:** apparent workload improvement is consistent with latched "
                "episodes rather than new-event discrimination."
            )
        elif abr < ABRUPT_6H_MIN:
            recommendation = (
                "**No-go:** frozen empirical τ loses useful six-hour abrupt sensitivity on DIAG."
            )
        else:
            recommendation = (
                "**Mixed / no-go:** empirical calibration does not show leak-associated "
                "excursions are sufficiently extreme vs historical scores for useful "
                "notifications under declared criteria."
            )

    summary = {
        "generated_at": iso_now(),
        "preserves": "outputs/RESULTS.md (original heuristic grid)",
        "input_hashes": input_hashes,
        "dev_z_sha256_16": z_sha,
        "frozen_signal": {"l_q_hours": L_Q, "l_r_hours": L_R},
        "pool": pool,
        "DEV_grid": [strip(g) for g in grid],
        "frozen": frozen,
        "DIAG": diag,
        "null_2h": null2,
        "null_6h": null6,
        "interpretation": interpretation,
        "recommendation": recommendation,
        "holdout_honesty": (
            "DIAG is diagnostic given prior examination; not an untouched holdout. "
            "Threshold not recomputed from DIAG percentiles. 2019 not evaluated."
        ),
    }
    (OUT / "empirical_calibration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (OUT / "EMPIRICAL_CALIBRATION_RESULTS.md").write_text(render(summary) + "\n")
    print(recommendation, flush=True)
    print(f"Wrote {OUT / 'EMPIRICAL_CALIBRATION_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
