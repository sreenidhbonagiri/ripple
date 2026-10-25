#!/usr/bin/env python3
"""FMR3C registered 16-cell DEV grid → freeze → optional DIAG."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
# Sibling CUSUM package first for shared eval/IO; FMR3C modules imported by file path.
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
    spec = importlib.util.spec_from_file_location(f"fmr3c_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_windows = _load_local("windows")
_scale = _load_local("scale")
# detector depends on scale/windows already registered under fmr3c_* names —
# re-bind expected import names inside detector by preloading aliases.
sys.modules["windows"] = _windows
sys.modules["scale"] = _scale
_detector = _load_local("detector")
_signals = _load_local("signals")

hours_to_steps = _windows.hours_to_steps
sigma_from_train = _scale.sigma_from_train
score_series = _detector.score_series
RECOVER_STEPS = _detector.RECOVER_STEPS
run_all_targets = _detector.run_all_targets
build_period_signals = _signals.build_period_signals

OUT = ROOT / "outputs"
TRAIN_DAYS = 14
N_REFS = 3
L_Q = [2.0, 6.0]
L_R = [24.0, 48.0]
TAU = [3.0, 4.0, 5.0, 6.0]
UNMATCHED_CAP = 3.0
ABRUPT_6H_MIN = 2.0 / 3.0


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


def evaluate_setting(
    pressures,
    timestamps,
    sensor_ids,
    leakages,
    period,
    *,
    l_q: float,
    l_r: float,
    tau: float,
    sig=None,
    train_z=None,
):
    start_i, end_i = period_indices(timestamps, period)
    if sig is None or train_z is None:
        sig, train_z, _, _ = build_period_signals(
            pressures,
            interval_start=start_i,
            interval_end=end_i,
            train_days=TRAIN_DAYS,
            n_refs=N_REFS,
        )
    t0 = time.perf_counter()
    episodes, meta = run_all_targets(
        sig.z,
        sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        train_z=train_z,
        l_q_hours=l_q,
        l_r_hours=l_r,
        tau=tau,
    )
    runtime = time.perf_counter() - t0
    train_end = train_end_time(timestamps, start_i, TRAIN_DAYS)
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
    a6 = abrupt_6h(prim)
    row = {
        "settings": {
            "l_q_hours": l_q,
            "l_r_hours": l_r,
            "tau": tau,
            "recover_steps": RECOVER_STEPS,
            "train_days": TRAIN_DAYS,
            "n_refs": N_REFS,
        },
        "period": period.name,
        "runtime_seconds": runtime,
        "n_episodes": len(episodes),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(timestamps, episodes, used),
        "primary": primary,
        "abrupt_6h": a6,
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
        "n_eligible_sensors": sum(
            1 for m in meta["scale_meta"].values() if m.get("eligible")
        ),
        "z_sha256_16": hashlib.sha256(np.ascontiguousarray(sig.z).tobytes()).hexdigest()[:16],
        "episodes": episodes,
        "sig": sig,
        "train_z": train_z,
        "analysis_start": sig.analysis_offset,
        "analysis_end": end_i,
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
            g["settings"]["l_q_hours"],
            g["settings"]["l_r_hours"],
            g["settings"]["tau"],
        ),
    )
    return eligible[0], True


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("episodes", "sig", "train_z")}


def synthetic_calibration_report() -> dict:
    """Correlated no-change exceedance — report only; do not tune after DIAG."""
    rng = np.random.default_rng(42)
    rows = []
    for rho in (0.0, 0.5, 0.8):
        n = 8000
        e = rng.normal(size=n)
        z = np.empty(n)
        z[0] = e[0]
        for i in range(1, n):
            z[i] = rho * z[i - 1] + (np.sqrt(1 - rho**2) if rho < 1 else 0) * e[i]
        for l_q, l_r in ((2.0, 24.0), (6.0, 48.0)):
            n_q, n_r = hours_to_steps(l_q), hours_to_steps(l_r)
            sigma, meta = sigma_from_train(z[:3000], n_q, n_r)
            if not meta["eligible"]:
                continue
            s = score_series(z[3000:], n_q=n_q, n_r=n_r, sigma=sigma)
            finite = s[np.isfinite(s)]
            rates = {f"tau_{int(t)}": float(np.mean(finite >= t)) for t in TAU}
            rows.append(
                {
                    "rho": rho,
                    "l_q_hours": l_q,
                    "l_r_hours": l_r,
                    "sigma": sigma,
                    "n_finite_scores": int(finite.size),
                    "exceedance_rates": rates,
                    "limitations": (
                        "AR(1) n_eff approximates mean SE, not median-difference variance; "
                        "tau are heuristic score thresholds, not calibrated confidence."
                    ),
                }
            )
    return {
        "generated_at": iso_now(),
        "purpose": "Honesty check on temporally correlated synthetic no-change inputs",
        "do_not_tune_after_diag": True,
        "rows": rows,
    }


def render(summary: dict) -> str:
    lines = [
        "# FMR3C results — finite-memory recent–reference residual change",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Preserves production and all prior detector reports. "
        "CUSUM-family results untouched. 2019 not evaluated.",
        "",
        f"Grid: LQ={L_Q}, LR={L_R}, tau={TAU} (16 settings). "
        f"recover_steps={RECOVER_STEPS}.",
        f"Provisional gates: abrupt 6h recall ≥ {ABRUPT_6H_MIN:.4f}, "
        f"unmatched/week ≤ {UNMATCHED_CAP:g} (not operator-validated).",
        "",
        "## Input hashes",
        "",
    ]
    for k, v in summary["input_hashes"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        f"- DEV z sha256[:16]: `{summary['dev_z_sha256_16']}`",
        "",
        "## Synthetic correlated no-change (not for tuning)",
        "",
        summary["synthetic_calibration"]["purpose"] + ". "
        + "Do not retune tau after DIAG.",
        "",
    ]
    for row in summary["synthetic_calibration"]["rows"]:
        lines.append(
            f"- rho={row['rho']}, LQ={row['l_q_hours']}, LR={row['l_r_hours']}: "
            f"exceedance={row['exceedance_rates']}"
        )
    lines += [
        "",
        "## DEV grid (every setting)",
        "",
        "| LQ | LR | tau | Abrupt6h | Unmatched/wk | Dup | Union% | Sensor% | "
        "Med/Longest ep (h) | Censored | Episodes | Latch? |",
        "|----|----|-----|----------|--------------|-----|--------|---------|"
        "--------------------|----------|----------|--------|",
    ]
    for g in summary["DEV_grid"]:
        s = g["settings"]
        med = g["occupancy"]["episode_length_hours"]["median"]
        longest = g["occupancy"]["episode_length_hours"]["max"]
        lines.append(
            f"| {s['l_q_hours']:g} | {s['l_r_hours']:g} | {s['tau']:g} | "
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
            "**Selection failure:** no DEV setting met both provisional gates. "
            "DIAG not run under a new setting.",
            "",
            "## Recommendation",
            "",
            summary["recommendation"],
            "",
        ]
        return "\n".join(lines)

    d = summary["DIAG"]
    lines += [
        "## DIAG (frozen — diagnostic only; prior examination)",
        "",
        f"- Abrupt 6h recall: **{d['abrupt_6h']['recall']:.2f}** "
        f"({d['abrupt_6h']['n_hit']}/{d['abrupt_6h']['n_abrupt']})",
        f"- Abrupt recall (7d registered window): **{d['primary']['abrupt_recall']:.2f}** "
        f"delays={d['primary']['abrupt_delay_hours']}",
        f"- Incipient recall: **{d['primary']['incipient_recall']:.2f}**",
        f"- Unmatched/wk: **{d['unmatched_per_week']:.2f}**; "
        f"dup: {d['duplicate_unmatched_within_24h']}",
        f"- Union%: {d['occupancy']['union_alarm_pct_of_analysis']:.2f}; "
        f"sensor%: {d['occupancy']['summed_sensor_alarm_pct_of_eligible']:.2f}",
        f"- Active sensors mean/med/p90/max: "
        f"{d['occupancy']['active_sensors']['mean']:.2f}/"
        f"{d['occupancy']['active_sensors']['median']:.2f}/"
        f"{d['occupancy']['active_sensors']['p90']:.2f}/"
        f"{d['occupancy']['active_sensors']['max']:.0f}",
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
    for label, key in (("0–2 h", "null_2h"), ("0–6 h (primary useful window)", "null_6h")):
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
    print("Synthetic calibration probe…", flush=True)
    synth = synthetic_calibration_report()
    (OUT / "synthetic_calibration.json").write_text(json.dumps(synth, indent=2) + "\n")

    print("Loading SCADA…", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()
    input_hashes = {
        "2018_SCADA_Pressures.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "2018_SCADA_Flows.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Flows.csv"),
        "2018_SCADA_Levels.csv": file_sha256(DEFAULT_RAW / "2018_SCADA_Levels.csv"),
    }

    print("DEV build_signals once…", flush=True)
    d0, d1 = period_indices(pb.timestamps, DEV)
    sig_dev, train_z_dev, _, _ = build_period_signals(
        pb.pressures, interval_start=d0, interval_end=d1, train_days=TRAIN_DAYS, n_refs=N_REFS
    )
    dev_z16 = hashlib.sha256(np.ascontiguousarray(sig_dev.z).tobytes()).hexdigest()[:16]

    grid = []
    for l_q in L_Q:
        for l_r in L_R:
            for tau in TAU:
                print(f"DEV LQ={l_q} LR={l_r} tau={tau}…", flush=True)
                row = evaluate_setting(
                    pb.pressures,
                    pb.timestamps,
                    pb.sensor_ids,
                    leakages,
                    DEV,
                    l_q=l_q,
                    l_r=l_r,
                    tau=tau,
                    sig=sig_dev,
                    train_z=train_z_dev,
                )
                grid.append(row)
                print(
                    f"  abrupt6h={row['abrupt_6h']['recall']:.2f} "
                    f"unmatched/wk={row['unmatched_per_week']:.2f} "
                    f"union%={row['occupancy']['union_alarm_pct_of_analysis']:.1f}",
                    flush=True,
                )

    chosen, gate = select_setting(grid)
    frozen = {
        "frozen_at": iso_now(),
        "gate_met": gate,
        "selected": None
        if not gate
        else {
            "l_q_hours": chosen["settings"]["l_q_hours"],
            "l_r_hours": chosen["settings"]["l_r_hours"],
            "tau": chosen["settings"]["tau"],
        },
        "unmatched_cap": UNMATCHED_CAP,
        "abrupt_6h_min": ABRUPT_6H_MIN,
        "selection_rule": (
            "among abrupt6h>=2/3 and unmatched/wk<=3: max abrupt6h recall, "
            "then min unmatched/wk, then min median 6h delay"
        ),
        "dev_snapshot": None
        if not gate
        else {
            "abrupt_6h_recall": chosen["abrupt_6h"]["recall"],
            "unmatched_per_week": chosen["unmatched_per_week"],
            "median_delay_6h": chosen["abrupt_6h"]["delay_hours"]["median"],
            "union_pct": chosen["occupancy"]["union_alarm_pct_of_analysis"],
            "n_episodes": chosen["n_episodes"],
        },
        "note": (
            ""
            if gate
            else "No DEV setting met both provisional gates; DIAG not run."
        ),
    }
    (OUT / "frozen_settings.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(f"Froze gate_met={gate} selected={frozen['selected']}", flush=True)

    diag = None
    null2 = null6 = None
    interpretation = ""
    if gate:
        print("DIAG once at frozen setting…", flush=True)
        s = frozen["selected"]
        diag_full = evaluate_setting(
            pb.pressures,
            pb.timestamps,
            pb.sensor_ids,
            leakages,
            DIAG,
            l_q=s["l_q_hours"],
            l_r=s["l_r_hours"],
            tau=s["tau"],
        )
        elig, _ = split_eligible_onsets(
            onsets_in_period(leakages, DIAG),
            train_end_time(
                pb.timestamps, period_indices(pb.timestamps, DIAG)[0], TRAIN_DAYS
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
            f"Frozen LQ={s['l_q_hours']} LR={s['l_r_hours']} tau={s['tau']} "
            f"(diagnostic): abrupt6h={diag['abrupt_6h']['recall']:.2f}, "
            f"unmatched/wk={diag['unmatched_per_week']:.2f}, "
            f"union%={diag['occupancy']['union_alarm_pct_of_analysis']:.1f}, "
            f"sensor%={diag['occupancy']['summed_sensor_alarm_pct_of_eligible']:.1f}, "
            f"longest_h={diag['occupancy']['episode_length_hours']['max']}, "
            f"censored={diag['occupancy']['n_episodes_right_censored']}. "
            f"{diag['latch']['note']}"
        )

    if not gate:
        recommendation = (
            "**Selection failure / no-go:** no setting in the registered 16-cell "
            "FMR3C grid met both provisional DEV gates (abrupt 6h recall ≥ 2/3 and "
            "unmatched/week ≤ 3). Do not invent a winner; do not enlarge the grid; "
            "do not retune from synthetic or DIAG."
        )
    else:
        abr = diag["abrupt_6h"]["recall"]
        um = diag["unmatched_per_week"]
        union = diag["occupancy"]["union_alarm_pct_of_analysis"]
        latched = diag["latch"]["latched_suspect"]
        frac2 = null2["fraction_shifts_ge_observed"]
        if (
            abr >= ABRUPT_6H_MIN
            and um <= UNMATCHED_CAP
            and not latched
            and union < 50
            and frac2 < 0.5
        ):
            recommendation = (
                "**Conditional research continue:** frozen FMR3C meets useful timing "
                "and burden heuristics on DIAG without a clear latched-only signature. "
                "Still diagnostic — not validated detection; not for productization."
            )
        elif latched or (union >= 90 and um <= UNMATCHED_CAP):
            recommendation = (
                "**No-go:** low unmatched burden is consistent with long active / "
                "latched episodes rather than cleared nuisance structure."
            )
        elif abr < ABRUPT_6H_MIN:
            recommendation = (
                "**No-go:** frozen setting loses useful six-hour abrupt sensitivity on DIAG."
            )
        else:
            recommendation = (
                "**Mixed / no-go:** FMR3C does not clearly distinguish new events "
                "better than accumulated-departure detectors under declared criteria."
            )

    summary = {
        "generated_at": iso_now(),
        "method": "FMR3C",
        "input_hashes": input_hashes,
        "dev_z_sha256_16": dev_z16,
        "synthetic_calibration": synth,
        "DEV_grid": [strip(g) for g in grid],
        "frozen": frozen,
        "DIAG": diag,
        "null_2h": null2,
        "null_6h": null6,
        "interpretation": interpretation,
        "recommendation": recommendation,
        "holdout_honesty": (
            "DIAG is diagnostic given prior examination of labels and prior detectors. "
            "2019 not evaluated. Synthetic rates not used for post-DIAG retuning."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "RESULTS.md").write_text(render(summary) + "\n")
    print(recommendation, flush=True)
    print(f"Wrote {OUT / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
