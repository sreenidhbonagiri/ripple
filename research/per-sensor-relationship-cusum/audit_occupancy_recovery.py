#!/usr/bin/env python3
"""Audit frozen per-sensor DIAG run: eligibility, occupancy, recovery, 0–2h timing.

Does not change frozen settings, original RESULTS headline, or the detector.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detector import Episode, run_all_targets  # noqa: E402
from evaluate import (  # noqa: E402
    ABRUPT_POST_DAYS,
    DIAG,
    NULL_SHIFT_DAYS,
    STEPS_PER_DAY,
    abrupt_window,
    incipient_window,
    iso_now,
    match_episodes,
    null_notification_comparison,
    onsets_in_period,
    period_indices,
    shift_episodes,
)
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402
from residual import build_signals  # noqa: E402

OUT = ROOT / "outputs"
FROZEN = OUT / "frozen_settings.json"
ORIGINAL_SUMMARY = OUT / "summary.json"


def load_frozen() -> dict:
    return json.loads(FROZEN.read_text())["settings"]


def train_end_time(timestamps: np.ndarray, period_start_i: int, train_days: int) -> np.datetime64:
    return timestamps[period_start_i + train_days * STEPS_PER_DAY]


def split_eligible_onsets(
    onsets: list[Leakage],
    train_end: np.datetime64,
) -> tuple[list[Leakage], list[Leakage]]:
    """Primary eligible: onset at/after post-training analysis start."""
    eligible = [L for L in onsets if L.start >= train_end]
    in_prefix = [L for L in onsets if L.start < train_end]
    return eligible, in_prefix


def match_with_post_hours(
    timestamps: np.ndarray,
    episodes: list[Episode],
    onsets: list[Leakage],
    leakages: list[Leakage],
    post_hours: float,
) -> tuple[list[dict], set[int]]:
    """Abrupt/incipient: notify in [onset, onset+post_hours] ∩ [onset, end]; no pre-onset credit."""
    used: set[int] = set()
    results: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo = L.start
        hi = min(L.start + np.timedelta64(int(post_hours * 60), "m"), L.end)
        if L.leak_type != "abrupt":
            hi = min(hi, L.peak)
        best_j = None
        best_t = None
        for j, ep in enumerate(episodes):
            if j in used:
                continue
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                if best_j is None or t < best_t:
                    best_j = j
                    best_t = t
        if best_j is None:
            # already-active at onset?
            active_at = [
                ep
                for ep in episodes
                if timestamps[ep.notify_idx] < L.start <= timestamps[ep.end_idx]
            ]
            results.append(
                {
                    "pipe": L.pipe,
                    "leak_type": L.leak_type,
                    "onset": str(L.start).replace("T", " "),
                    "matched": False,
                    "notify_time": None,
                    "delay_hours": None,
                    "already_active_at_onset": [
                        {"stream": ep.stream_id, "notify": str(timestamps[ep.notify_idx]).replace("T", " ")}
                        for ep in active_at
                    ],
                }
            )
            continue
        used.add(best_j)
        ep = episodes[best_j]
        results.append(
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "matched": True,
                "notify_time": str(best_t).replace("T", " "),
                "delay_hours": float((best_t - L.start) / np.timedelta64(1, "h")),
                "stream_id": ep.stream_id,
                "already_active_at_onset": [],
            }
        )
    return results, used


def null_at_post_hours(
    timestamps: np.ndarray,
    episodes: list[Episode],
    onsets: list[Leakage],
    leakages: list[Leakage],
    analysis_start: int,
    analysis_end: int,
    post_hours: float,
) -> dict:
    abrupt = [L for L in onsets if L.leak_type == "abrupt"]
    obs, _ = match_with_post_hours(timestamps, episodes, onsets, leakages, post_hours)
    obs_n = sum(1 for m in obs if m["leak_type"] == "abrupt" and m["matched"])
    counts = []
    for day in NULL_SHIFT_DAYS:
        sh = shift_episodes(episodes, day * STEPS_PER_DAY, analysis_start, analysis_end)
        rows, _ = match_with_post_hours(timestamps, sh, onsets, leakages, post_hours)
        counts.append(sum(1 for m in rows if m["leak_type"] == "abrupt" and m["matched"]))
    arr = np.asarray(counts, dtype=float)
    return {
        "window": f"0–{post_hours:g} h post-onset (no pre-onset credit)",
        "n_abrupt_onsets": len(abrupt),
        "observed_abrupt_matches": obs_n,
        "null_n_valid_shifts": len(NULL_SHIFT_DAYS),
        "null_match_median": float(np.median(arr)),
        "null_match_min": int(arr.min()),
        "null_match_max": int(arr.max()),
        "null_match_mean": float(arr.mean()),
        "fraction_shifts_ge_observed": float(np.mean(arr >= obs_n)),
        "caveat": (
            "Newly added diagnostic — not the registered 7-day headline. "
            "Overlapping shifts are dependent; n is small."
        ),
        "per_onset": obs,
    }


def occupancy_report(
    timestamps: np.ndarray,
    episodes: list[Episode],
    analysis_start: int,
    analysis_end: int,
    n_sensors: int,
) -> dict:
    span = analysis_end - analysis_start
    eligible_sensor_steps = span * n_sensors
    # per-sensor alarm mask on analysis-relative indices
    alarm = np.zeros((span, n_sensors), dtype=bool)
    lengths = []
    censored = 0
    for ep in episodes:
        if ep.target_idx < 0:
            continue
        a0 = max(0, ep.notify_idx - analysis_start)
        a1 = min(span - 1, ep.end_idx - analysis_start)
        if a1 < a0:
            continue
        alarm[a0 : a1 + 1, ep.target_idx] = True
        dur_h = float((ep.end_idx - ep.notify_idx) * 5 / 60.0)
        right_cens = ep.end_idx >= analysis_end - 1
        if right_cens:
            censored += 1
        lengths.append(
            {
                "stream": ep.stream_id,
                "notify": str(timestamps[ep.notify_idx]).replace("T", " "),
                "end": str(timestamps[ep.end_idx]).replace("T", " "),
                "duration_hours": dur_h,
                "right_censored": right_cens,
                "peak_cusum": ep.peak_cusum,
            }
        )

    sensor_alarm_steps = int(alarm.sum())
    union_steps = int(np.any(alarm, axis=1).sum())
    active_count = alarm.sum(axis=1).astype(np.float64)
    hours_per_step = 5 / 60.0
    return {
        "analysis_hours": span * hours_per_step,
        "n_sensors": n_sensors,
        "eligible_sensor_hours": eligible_sensor_steps * hours_per_step,
        "summed_sensor_alarm_hours": sensor_alarm_steps * hours_per_step,
        "summed_sensor_alarm_pct_of_eligible": 100.0
        * sensor_alarm_steps
        / eligible_sensor_steps,
        "union_alarm_hours": union_steps * hours_per_step,
        "union_alarm_pct_of_analysis": 100.0 * union_steps / span,
        "active_sensors": {
            "mean": float(active_count.mean()),
            "median": float(np.median(active_count)),
            "p90": float(np.quantile(active_count, 0.9)),
            "max": float(active_count.max()),
        },
        "n_notifications": len(episodes),
        "n_episodes_right_censored": censored,
        "episode_length_hours": {
            "n": len(lengths),
            "median": float(np.median([x["duration_hours"] for x in lengths]))
            if lengths
            else None,
            "p90": float(np.quantile([x["duration_hours"] for x in lengths], 0.9))
            if lengths
            else None,
            "max": float(max(x["duration_hours"] for x in lengths)) if lengths else None,
            "mean": float(np.mean([x["duration_hours"] for x in lengths]))
            if lengths
            else None,
        },
        "episodes_detail": sorted(lengths, key=lambda x: -x["duration_hours"]),
        "note": (
            "Notifications count episode starts only. Occupancy counts ongoing alarm "
            "intervals; already-active alarms are not new detections."
        ),
    }


def simulate_cusum_state(
    z: np.ndarray,
    *,
    k: float,
    h: float,
    recover_steps: int,
) -> dict:
    """Replay detector state for diagnosis (does not alter frozen episode list)."""
    n = len(z)
    c = np.full(n, np.nan)
    active = np.zeros(n, dtype=bool)
    recover_run = np.zeros(n, dtype=np.int32)
    notify_mask = np.zeros(n, dtype=bool)
    c_val = 0.0
    is_active = False
    rec = 0
    for i, val in enumerate(z):
        if not np.isfinite(val):
            continue
        c_val = max(0.0, c_val + val - k)
        c[i] = c_val
        if not is_active:
            if c_val >= h:
                is_active = True
                notify_mask[i] = True
                rec = 0
        else:
            if c_val == 0.0:
                rec += 1
                if rec >= recover_steps:
                    is_active = False
                    rec = 0
                    c_val = 0.0
                    c[i] = 0.0
            else:
                rec = 0
        active[i] = is_active
        recover_run[i] = rec
    return {
        "c": c,
        "active": active,
        "recover_run": recover_run,
        "notify_mask": notify_mask,
    }


def diagnose_episode(
    pressures: np.ndarray,
    timestamps: np.ndarray,
    sensor_ids: list[str],
    bundle,
    ep: Episode,
    settings: dict,
    label: str,
    out_dir: Path,
) -> dict:
    """Evidence-oriented recovery diagnosis for one episode."""
    i = ep.target_idx
    tm = bundle.target_models[i]
    off = bundle.analysis_offset
    # local span with padding
    pad = 288  # 1 day
    a0 = max(0, ep.notify_idx - off - pad)
    a1 = min(bundle.z.shape[0], ep.end_idx - off + pad + 1)
    abs0 = off + a0
    abs1 = off + a1
    z = bundle.z[a0:a1, i]
    state = simulate_cusum_state(
        bundle.z[:, i],
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_steps=max(1, int(settings["recover_hours"] * 12)),
    )
    # Pair scales and residuals on analysis
    pair_info = []
    for j, pm in tm.pairs.items():
        pair_info.append(
            {
                "ref": sensor_ids[j],
                "intercept": pm.intercept,
                "slope": pm.slope,
                "train_rmse": pm.rmse,
                "train_mad": pm.mad,
                "norm_scale": pm.scale,
                "norm_loc": pm.loc,
                "n_train": pm.n_train,
            }
        )

    # After notify: does z normalize while C stays high?
    n_loc = ep.notify_idx - off
    e_loc = min(ep.end_idx - off, bundle.z.shape[0] - 1)
    post_z = bundle.z[n_loc : e_loc + 1, i]
    post_c = state["c"][n_loc : e_loc + 1]
    finite_z = post_z[np.isfinite(post_z)]
    finite_c = post_c[np.isfinite(post_c)]
    # fractions
    z_near0 = float(np.mean(np.abs(finite_z) < 0.5)) if finite_z.size else None
    z_neg = float(np.mean(finite_z < 0)) if finite_z.size else None
    c_pos = float(np.mean(finite_c > 0)) if finite_c.size else None
    # windows where |z|<0.5 for long runs but C>0
    debt_evidence = False
    if finite_z.size and finite_c.size:
        # count steps with |z|<k and C>1
        both = np.isfinite(post_z) & np.isfinite(post_c)
        debt_steps = int(np.sum(both & (np.abs(post_z) < settings["cusum_k"]) & (post_c > 1.0)))
        debt_evidence = debt_steps > 12 * 6  # >6 hours

    # sustained z elevation?
    sustained_z = bool(finite_z.size and np.nanmedian(finite_z) > 0.5)

    small_scale = any(p["norm_scale"] < 0.05 for p in pair_info)

    hyp = {
        "sustained_observable_relationship_change": {
            "supported": sustained_z,
            "evidence": f"median post-notify z={float(np.nanmedian(finite_z)) if finite_z.size else None}",
        },
        "cusum_debt_despite_normalized_residual": {
            "supported": debt_evidence and not sustained_z,
            "evidence": (
                f"steps with |z|<k and C>1: "
                f"{int(np.sum((np.abs(post_z) < settings['cusum_k']) & (post_c > 1.0) & np.isfinite(post_z) & np.isfinite(post_c))) if post_z.size else 0}; "
                f"frac |z|<0.5={z_near0}; frac C>0={c_pos}"
            ),
        },
        "restrictive_24h_recovery": {
            "supported": None,  # filled after checking max recover_run vs need for C==0
            "evidence": (
                f"recovery requires {int(settings['recover_hours']*12)} consecutive steps with C==0; "
                f"max recover_run in episode={int(np.nanmax(state['recover_run'][n_loc:e_loc+1])) if e_loc>=n_loc else 0}"
            ),
        },
        "small_normalization_scales": {
            "supported": small_scale,
            "evidence": f"pair scales={[round(p['norm_scale'],4) for p in pair_info]}",
        },
        "seasonal_model_mismatch": {
            "supported": None,
            "evidence": (
                "DIAG train is first 14 days of Jul; long late-year episodes may reflect "
                "drift of pairwise maps — hypothesis unless z stays elevated vs refs."
            ),
        },
    }
    # Restrictive recovery: if C hits 0 often but never for 24h consecutively
    rr = state["recover_run"][n_loc : e_loc + 1]
    max_rr = int(np.nanmax(rr)) if rr.size else 0
    need = int(settings["recover_hours"] * 12)
    c_hits_zero = bool(np.any((post_c == 0) & np.isfinite(post_c))) if post_c.size else False
    hyp["restrictive_24h_recovery"]["supported"] = bool(
        c_hits_zero and max_rr < need and ep.end_idx >= (off + bundle.z.shape[0] - 1)
    )

    # Implementation sanity: C update matches formula on a sample
    impl_ok = True
    z_full = bundle.z[:, i]
    c_chk = 0.0
    for li in range(min(500, len(z_full))):
        v = z_full[li]
        if not np.isfinite(v):
            continue
        c_chk = max(0.0, c_chk + v - settings["cusum_k"])
        if np.isfinite(state["c"][li]) and abs(state["c"][li] - c_chk) > 1e-6:
            impl_ok = False
            break

    # Plot
    paths = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        out_dir.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(4, 1, figsize=(12, 9), sharex=True)
        t_rel = np.arange(a0, a1)
        # pressures
        ax = axes[0]
        ax.plot(t_rel, pressures[abs0:abs1, i], color="#1a1a1a", lw=0.8, label=f"P {sensor_ids[i]}")
        for j, pm in tm.pairs.items():
            hat = pm.intercept + pm.slope * pressures[abs0:abs1, j]
            ax.plot(t_rel, hat, lw=0.7, alpha=0.85, label=f"hat via {sensor_ids[j]}")
        ax.axvline(ep.notify_idx - off, color="#c45c26", ls="--", lw=1)
        ax.set_ylabel("pressure")
        ax.legend(fontsize=6, ncol=2)
        ax.set_title(f"{label}: {ep.stream_id} notify={timestamps[ep.notify_idx]}")

        ax = axes[1]
        ax.plot(t_rel, z, color="#1a6b7a", lw=0.8)
        ax.axhline(0, color="#999", lw=0.5)
        ax.axhline(settings["cusum_k"], color="#999", ls=":", lw=0.5)
        ax.set_ylabel("z_i")

        ax = axes[2]
        ax.plot(t_rel, state["c"][a0:a1], color="#6b2d5c", lw=0.8)
        ax.axhline(settings["cusum_h"], color="#c45c26", ls="--", lw=0.7)
        ax.set_ylabel("CUSUM C")

        ax = axes[3]
        ax.plot(t_rel, state["recover_run"][a0:a1], color="#2d6b3a", lw=0.8)
        ax.axhline(need, color="#c45c26", ls="--", lw=0.7)
        ax.set_ylabel("recover_run")
        ax.set_xlabel("analysis step")
        fig.tight_layout()
        fname = out_dir / f"recovery_{label}_{ep.stream_id}.png"
        fig.savefig(fname, dpi=110)
        plt.close(fig)
        paths.append(str(fname.relative_to(ROOT)))
    except Exception as exc:  # noqa: BLE001
        paths.append(f"plot_error:{exc}")

    return {
        "label": label,
        "stream": ep.stream_id,
        "notify": str(timestamps[ep.notify_idx]).replace("T", " "),
        "end": str(timestamps[ep.end_idx]).replace("T", " "),
        "duration_hours": float((ep.end_idx - ep.notify_idx) * 5 / 60.0),
        "right_censored": bool(ep.end_idx >= off + bundle.z.shape[0] - 1),
        "peak_cusum": ep.peak_cusum,
        "refs": list(ep.refs_used),
        "pair_calibration": pair_info,
        "post_notify_z_median": float(np.nanmedian(finite_z)) if finite_z.size else None,
        "post_notify_frac_abs_z_lt_0.5": z_near0,
        "post_notify_frac_z_negative": z_neg,
        "post_notify_frac_c_positive": c_pos,
        "hypotheses": hyp,
        "implementation_replay_ok": impl_ok,
        "plots": paths,
    }


def recommend_next(diagnoses: list[dict], occupancy: dict) -> dict:
    """One targeted next change supported by state evidence."""
    debt = [d for d in diagnoses if d["hypotheses"]["cusum_debt_despite_normalized_residual"]["supported"]]
    sustained = [
        d for d in diagnoses if d["hypotheses"]["sustained_observable_relationship_change"]["supported"]
    ]
    restrictive = [d for d in diagnoses if d["hypotheses"]["restrictive_24h_recovery"]["supported"]]
    small = [d for d in diagnoses if d["hypotheses"]["small_normalization_scales"]["supported"]]

    if debt and not all(d["hypotheses"]["sustained_observable_relationship_change"]["supported"] for d in diagnoses):
        return {
            "proposal": (
                "Change recovery to require sustained **observable residual normalization** "
                "(e.g. N consecutive finite steps with z_i ≤ k or z_i ≤ 0), while keeping "
                "the episode active if z_i remains elevated — do **not** clear on wall-clock "
                "alone and do **not** periodically reset CUSUM to spawn repeated incidents."
            ),
            "supported_by": "CUSUM-debt evidence on diagnosed episodes where |z| is small but C stays >0",
            "episodes_with_debt_evidence": [d["stream"] for d in debt],
            "status": "proposed only — not implemented",
        }
    if sustained and occupancy["union_alarm_pct_of_analysis"] > 50:
        return {
            "proposal": (
                "Prioritize diagnosing / mitigating **sustained pairwise model mismatch** "
                "(recalibration schedule or reference quality gates) before changing CUSUM "
                "recovery — residuals themselves remain elevated."
            ),
            "supported_by": "median post-notify z remains clearly positive on longest/hit streams",
            "status": "proposed only — not implemented",
        }
    if restrictive:
        return {
            "proposal": (
                "If C reaches 0 repeatedly but rarely for a full 24 h streak, shorten the "
                "consecutive C==0 recovery streak **only after** confirming residuals are "
                "normalized; still forbid periodic resets."
            ),
            "supported_by": "recover_run max < required streak while C hits zero",
            "status": "proposed only — not implemented",
        }
    if small:
        return {
            "proposal": "Floor or reject pairs with very small normalization scales before CUSUM.",
            "supported_by": "small MAD/scale on contributing pairs",
            "status": "proposed only — not implemented",
        }
    return {
        "proposal": (
            "Gather more residual-vs-CUSUM evidence before changing recovery; current "
            "diagnoses do not uniquely support one fix."
        ),
        "supported_by": "mixed signals",
        "status": "proposed only — not implemented",
    }


def render(summary: dict) -> str:
    o = summary["original_headline_preserved"]
    corr = summary["eligibility_correction"]
    occ = summary["occupancy"]
    lines = [
        "# Audit — per-sensor relationship CUSUM (frozen DIAG)",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Frozen settings, original `RESULTS.md` / `summary.json` headline, production, and "
        "other branches are **preserved**. No detector retuning.",
        "",
        "## 0. Original registered result (preserved)",
        "",
        f"- Abrupt recall (original, all DIAG onsets): **{o['abrupt_recall']:.2f}**",
        f"- Incipient recall: **{o['incipient_recall']:.2f}**",
        f"- Unmatched/wk: **{o['unmatched_per_week']:.2f}**",
        f"- Recommendation (original): {o['recommendation'][:180]}…",
        "",
        "## 1. Eligibility correction",
        "",
        f"Training/calibration prefix: first **{summary['train_days']}** days of DIAG "
        f"(through **{corr['train_end']}**). Onsets with `startTime` **before** this "
        "instant are **excluded** from primary post-training onset recall.",
        "",
        f"- In-prefix onsets (excluded from primary): {[x['pipe'] for x in corr['in_prefix_onsets']]}",
        f"- Primary-eligible onsets: {[x['pipe'] for x in corr['eligible_onsets']]}",
        "",
        "### Primary post-training recall (corrected)",
        "",
        f"- Abrupt recall: **{corr['primary']['abrupt_recall']:.2f}** "
        f"({corr['primary']['n_abrupt']} onsets)",
        f"- Incipient recall: **{corr['primary']['incipient_recall']:.2f}** "
        f"({corr['primary']['n_incipient']} onsets)",
        f"- Abrupt delays (h): {corr['primary']['abrupt_delay_hours']}",
        "",
        "#### Eligible per-event",
        "",
    ]
    for m in corr["primary"]["matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"notify={m['notify_time']} delay_h={m['delay_hours']} sensor={m.get('stream_id')}"
        )
    lines += ["", "#### In-prefix onsets (reported separately; not in primary recall)", ""]
    for m in corr["in_prefix_matches"]:
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} ({m['leak_type']}) onset {m['onset']} "
            f"notify={m['notify_time']} delay_h={m['delay_hours']} "
            f"— excluded because onset is inside fitting prefix"
        )
    lines += [
        "",
        "## 2. Alarm occupancy",
        "",
        f"- Notifications (episode starts): **{occ['n_notifications']}**",
        f"- Summed sensor-alarm hours: **{occ['summed_sensor_alarm_hours']:.1f}** "
        f"({occ['summed_sensor_alarm_pct_of_eligible']:.2f}% of eligible sensor-hours)",
        f"- Union alarm hours (any sensor): **{occ['union_alarm_hours']:.1f}** "
        f"({occ['union_alarm_pct_of_analysis']:.2f}% of analysis hours)",
        f"- Active-sensor count: mean={occ['active_sensors']['mean']:.2f}, "
        f"median={occ['active_sensors']['median']:.2f}, "
        f"p90={occ['active_sensors']['p90']:.2f}, max={occ['active_sensors']['max']:.0f}",
        f"- Episode length (h): median={occ['episode_length_hours']['median']}, "
        f"p90={occ['episode_length_hours']['p90']}, max={occ['episode_length_hours']['max']}",
        f"- Right-censored episodes: **{occ['n_episodes_right_censored']}** / {occ['episode_length_hours']['n']}",
        "",
        occ["note"],
        "",
        "Longest episodes:",
        "",
    ]
    for ep in occ["episodes_detail"][:8]:
        lines.append(
            f"- {ep['stream']}: {ep['duration_hours']:.1f} h "
            f"{'(right-censored) ' if ep['right_censored'] else ''}"
            f"notify={ep['notify']} end={ep['end']}"
        )
    lines += [
        "",
        "## 3. Recovery diagnosis",
        "",
        "Evidence vs hypotheses for longest episodes and abrupt hit streams. "
        "Implementation replay of CUSUM arithmetic checked on a prefix sample.",
        "",
    ]
    for d in summary["recovery_diagnoses"]:
        lines += [
            f"### {d['label']} — {d['stream']}",
            "",
            f"- Duration {d['duration_hours']:.1f} h; right_censored={d['right_censored']}; "
            f"peak_C={d['peak_cusum']:.1f}",
            f"- Refs: {d['refs']}",
            f"- Pair scales: {[round(p['norm_scale'], 4) for p in d['pair_calibration']]}",
            f"- Post-notify median z={d['post_notify_z_median']}; "
            f"frac|z|<0.5={d['post_notify_frac_abs_z_lt_0.5']}; "
            f"frac C>0={d['post_notify_frac_c_positive']}",
            f"- Implementation replay ok: {d['implementation_replay_ok']}",
            f"- Plots: {d['plots']}",
            "",
        ]
        for name, h in d["hypotheses"].items():
            lines.append(
                f"  - **{name}**: supported={h['supported']} — {h['evidence']}"
            )
        lines.append("")
    lines += [
        "## 4. Tight-timing diagnostic (0–2 h) — not the registered headline",
        "",
        f"Registered abrupt window remains **0–{ABRUPT_POST_DAYS:g} days** "
        f"(corrected primary abrupt recall={corr['primary']['abrupt_recall']:.2f}).",
        "",
        f"### 0–2 h results",
        "",
        f"- Eligible abrupt matches: **{summary['tight_2h']['observed_abrupt_matches']}** / "
        f"{summary['tight_2h']['n_abrupt_onsets']}",
        f"- Null median (min–max): {summary['tight_2h']['null_match_median']:.0f} "
        f"({summary['tight_2h']['null_match_min']}–{summary['tight_2h']['null_match_max']})",
        f"- Fraction of shifts ≥ observed: **{summary['tight_2h']['fraction_shifts_ge_observed']:.2f}**",
        f"- Valid shifts: {summary['tight_2h']['null_n_valid_shifts']} (overlapping — not independent)",
        "",
        str(summary["tight_2h"]["caveat"]),
        "",
        "Per-onset (0–2 h):",
        "",
    ]
    for m in summary["tight_2h"]["per_onset"]:
        if m["leak_type"] != "abrupt":
            continue
        tag = "HIT" if m["matched"] else "MISS"
        lines.append(
            f"- {tag} {m['pipe']} delay_h={m['delay_hours']} "
            f"already_active={m.get('already_active_at_onset')}"
        )
    lines += [
        "",
        "## 5. Recommended next change (not implemented)",
        "",
        f"**Proposal:** {summary['next_change']['proposal']}",
        "",
        f"**Supported by:** {summary['next_change']['supported_by']}",
        "",
        f"Status: {summary['next_change']['status']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = load_frozen()
    original = json.loads(ORIGINAL_SUMMARY.read_text())
    bundle_p = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()
    start_i, end_i = period_indices(bundle_p.timestamps, DIAG)
    train_end = train_end_time(bundle_p.timestamps, start_i, settings["train_days"])
    analysis_start = start_i + settings["train_days"] * STEPS_PER_DAY

    print("Rebuilding frozen DIAG signals…", flush=True)
    sig = build_signals(
        bundle_p.pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=settings["train_days"],
        n_refs=settings["n_refs"],
    )
    episodes = run_all_targets(
        sig.z,
        bundle_p.sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        k=settings["cusum_k"],
        h=settings["cusum_h"],
        recover_hours=settings["recover_hours"],
    )

    all_onsets = onsets_in_period(leakages, DIAG)
    eligible, in_prefix = split_eligible_onsets(all_onsets, train_end)

    # Original-style match on all onsets (for cross-check)
    orig_matches, _ = match_episodes(
        bundle_p.timestamps, episodes, all_onsets, leakages
    )
    prim_matches, _ = match_episodes(
        bundle_p.timestamps, episodes, eligible, leakages
    )
    prefix_matches, _ = match_episodes(
        bundle_p.timestamps, episodes, in_prefix, leakages
    )

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
            },
            "matches": matches,
        }

    occ = occupancy_report(
        bundle_p.timestamps,
        episodes,
        analysis_start,
        end_i,
        n_sensors=len(bundle_p.sensor_ids),
    )

    # Diagnoses: 3 longest + abrupt hit streams
    abrupt_eligible = [L for L in eligible if L.leak_type == "abrupt"]
    prim = recall_block(prim_matches)
    hit_streams = []
    for m in prim["matches"]:
        if m["matched"] and m["leak_type"] == "abrupt":
            hit_streams.append(m["stream_id"])

    by_stream = {}
    for ep in episodes:
        by_stream.setdefault(ep.stream_id, []).append(ep)

    to_diag: list[tuple[str, Episode]] = []
    for detail in occ["episodes_detail"][:3]:
        ep = next(
            e
            for e in episodes
            if e.stream_id == detail["stream"]
            and str(bundle_p.timestamps[e.notify_idx]).replace("T", " ") == detail["notify"]
        )
        to_diag.append((f"longest_{detail['stream']}", ep))
    for m in prim["matches"]:
        if m["matched"] and m["leak_type"] == "abrupt":
            # episode that matched
            nt = np.datetime64(m["notify_time"].replace(" ", "T"))
            ep = next(
                e
                for e in episodes
                if e.stream_id == m["stream_id"] and bundle_p.timestamps[e.notify_idx] == nt
            )
            to_diag.append((f"abrupt_hit_{m['pipe']}", ep))

    # dedupe by (stream, notify)
    seen = set()
    uniq = []
    for lab, ep in to_diag:
        key = (ep.stream_id, ep.notify_idx)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((lab, ep))

    plot_dir = OUT / "audit_plots"
    diagnoses = []
    for lab, ep in uniq:
        print(f"Diagnosing {lab}…", flush=True)
        diagnoses.append(
            diagnose_episode(
                bundle_p.pressures,
                bundle_p.timestamps,
                bundle_p.sensor_ids,
                sig,
                ep,
                settings,
                lab,
                plot_dir,
            )
        )

    tight = null_at_post_hours(
        bundle_p.timestamps,
        episodes,
        eligible,
        leakages,
        analysis_start,
        end_i,
        post_hours=2.0,
    )
    # also registered 7-day null on eligible only for context
    null_7d = null_notification_comparison(
        bundle_p.timestamps,
        episodes,
        eligible,
        leakages,
        analysis_start,
        end_i,
    )

    next_change = recommend_next(diagnoses, occ)

    summary = {
        "generated_at": iso_now(),
        "train_days": settings["train_days"],
        "frozen_settings": settings,
        "original_headline_preserved": {
            "abrupt_recall": original["DIAG_per_sensor"]["abrupt_recall"],
            "incipient_recall": original["DIAG_per_sensor"]["incipient_recall"],
            "unmatched_per_week": original["DIAG_per_sensor"]["unmatched_per_week"],
            "recommendation": original["recommendation"],
        },
        "eligibility_correction": {
            "train_end": str(train_end).replace("T", " "),
            "in_prefix_onsets": [
                {"pipe": L.pipe, "type": L.leak_type, "onset": str(L.start).replace("T", " ")}
                for L in in_prefix
            ],
            "eligible_onsets": [
                {"pipe": L.pipe, "type": L.leak_type, "onset": str(L.start).replace("T", " ")}
                for L in eligible
            ],
            "primary": recall_block(prim_matches),
            "in_prefix_matches": prefix_matches,
            "note": (
                "p654 (2018-07-05) falls inside DIAG 14-day training prefix ending "
                f"{train_end}; excluded from primary post-training recall."
            ),
        },
        "occupancy": occ,
        "recovery_diagnoses": diagnoses,
        "tight_2h": tight,
        "null_7d_eligible_only": null_7d,
        "next_change": next_change,
        "crosscheck_original_style_matches": orig_matches,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    # Drop bulky per-step arrays if any — none stored
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "AUDIT.md").write_text(render(summary) + "\n")
    print(next_change["proposal"])
    print(f"Wrote {OUT / 'AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
