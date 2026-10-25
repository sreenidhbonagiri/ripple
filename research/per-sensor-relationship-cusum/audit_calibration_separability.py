#!/usr/bin/env python3
"""Residual calibration & separability audit (frozen fits; no detector retune).

Preserves original and residual-recovery detectors and all frozen results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate import DIAG, STEPS_PER_DAY, iso_now, onsets_in_period, period_indices  # noqa: E402
from io_data import DEFAULT_RAW, load_context, load_leakages, load_pressures  # noqa: E402
from residual import MAD_SCALE, _mad, build_signals, fit_pair  # noqa: E402

OUT = ROOT / "outputs"
FROZEN = json.loads((OUT / "frozen_settings.json").read_text())["settings"]
K_ALLOW = float(FROZEN["cusum_k"])

# Separability window (equal length for events and controls)
PRE_H = 6.0
POST_H = 24.0
WINDOW_STEPS = int((PRE_H + POST_H) * 12)
CONTROL_EXCLUDE_DAYS = 7.0


def signed_residual(pressures, i, j, pm, start, end):
    block_i = pressures[start:end, i].astype(np.float64)
    block_j = pressures[start:end, j].astype(np.float64)
    e = (pm.intercept + pm.slope * block_j) - block_i
    ok = np.isfinite(block_i) & np.isfinite(block_j)
    return np.where(ok, e, np.nan)


def pair_calibration_row(
    pressures,
    sensor_ids,
    i,
    j,
    pm,
    train_start,
    train_end,
    analysis_start,
    analysis_end,
):
    """Train residual stats + chronological out-of-fit error on post-train span."""
    e_tr = signed_residual(pressures, i, j, pm, train_start, train_end)
    finite_tr = e_tr[np.isfinite(e_tr)]
    raw_med = float(np.median(finite_tr)) if finite_tr.size else float("nan")
    raw_mad = _mad(finite_tr)
    raw_std = float(np.std(finite_tr)) if finite_tr.size else float("nan")

    # Exact scale path (mirrors residual.fit_pair)
    scale_via = "mad * 1.4826"
    scale = raw_mad * MAD_SCALE
    fallback = False
    if not np.isfinite(scale) or scale < 1e-6:
        fallback = True
        scale_via = "std fallback (MAD*1.4826 invalid or <1e-6)"
        scale = raw_std if (np.isfinite(raw_std) and raw_std > 1e-6) else float("nan")

    # Chronological OOS: first 14 days after train (or all analysis if shorter)
    oos_end = min(analysis_start + 14 * STEPS_PER_DAY, analysis_end)
    e_oos = signed_residual(pressures, i, j, pm, analysis_start, oos_end)
    finite_oos = e_oos[np.isfinite(e_oos)]
    oos_rmse = (
        float(np.sqrt(np.mean(finite_oos**2))) if finite_oos.size else float("nan")
    )
    oos_mad = _mad(finite_oos)
    oos_med = float(np.median(finite_oos)) if finite_oos.size else float("nan")

    # Full analysis residual spread
    e_an = signed_residual(pressures, i, j, pm, analysis_start, analysis_end)
    finite_an = e_an[np.isfinite(e_an)]
    an_mad = _mad(finite_an)

    ratio_oos = (
        float(oos_mad / raw_mad) if (raw_mad and raw_mad > 1e-12 and np.isfinite(oos_mad)) else float("nan")
    )
    # Genuine predictability vs under-estimated uncertainty
    if np.isfinite(ratio_oos) and ratio_oos > 2.0:
        scale_reading = "underestimated_oos_uncertainty"
    elif np.isfinite(raw_mad) and raw_mad < 0.05 and np.isfinite(ratio_oos) and ratio_oos <= 1.5:
        scale_reading = "genuinely_tight_in_sample_and_near_oos"
    elif np.isfinite(raw_mad) and raw_mad < 0.05:
        scale_reading = "tiny_in_sample_scale_with_oos_inflation"
    else:
        scale_reading = "moderate_or_mixed"

    return {
        "target": sensor_ids[i],
        "reference": sensor_ids[j],
        "intercept_m": pm.intercept,
        "slope": pm.slope,
        "n_train": pm.n_train,
        "train_residual_median_m": raw_med,
        "train_residual_MAD_m": raw_mad,
        "train_residual_std_m": raw_std,
        "train_fit_rmse_m": pm.rmse,
        "norm_loc_m": pm.loc,
        "norm_scale_m": pm.scale,
        "scale_formula": scale_via,
        "scale_used_fallback": fallback,
        "oos_14d_residual_median_m": oos_med,
        "oos_14d_residual_MAD_m": oos_mad,
        "oos_14d_rmse_m": oos_rmse,
        "oos_MAD_over_train_MAD": ratio_oos,
        "analysis_residual_MAD_m": an_mad,
        "units": "meters (BattLeDIM SCADA pressure head)",
        "scale_interpretation": scale_reading,
    }


def consecutive_exceedances(mask: np.ndarray) -> list[int]:
    lengths = []
    run = 0
    for v in mask:
        if v:
            run += 1
        elif run:
            lengths.append(run)
            run = 0
    if run:
        lengths.append(run)
    return lengths


def acf_lag1(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size < 3:
        return float("nan")
    x0 = x[:-1]
    x1 = x[1:]
    if np.std(x0) < 1e-12 or np.std(x1) < 1e-12:
        return float("nan")
    return float(np.corrcoef(x0, x1)[0, 1])


def target_excursion_report(
    pressures,
    timestamps,
    context,
    sensor_ids,
    tm,
    train_start,
    train_end,
    analysis_start,
    analysis_end,
    z_col,
):
    i = tm.target
    # Aggregate raw residual median across refs (meters) on train vs analysis
    def agg_raw(start, end):
        cols = []
        for j, pm in tm.pairs.items():
            cols.append(signed_residual(pressures, i, j, pm, start, end))
        if not cols:
            return np.array([])
        stack = np.vstack(cols)
        with np.errstate(all="ignore"):
            return np.nanmedian(stack, axis=0)

    raw_tr = agg_raw(train_start, train_end)
    raw_an = agg_raw(analysis_start, analysis_end)
    z = z_col

    def quantiles(x):
        x = x[np.isfinite(x)]
        if x.size == 0:
            return None
        qs = [0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
        return {f"p{int(q*100)}": float(np.quantile(x, q)) for q in qs}

    elev = np.isfinite(z) & (z > K_ALLOW)
    runs = consecutive_exceedances(elev)
    # Monthly drift of median z
    months = {}
    for t_idx in range(analysis_start, analysis_end):
        local = t_idx - analysis_start
        if local >= len(z) or not np.isfinite(z[local]):
            continue
        ts = timestamps[t_idx]
        # numpy datetime64 → month key
        month = str(ts.astype("datetime64[M]"))
        months.setdefault(month, []).append(float(z[local]))
    monthly_median = {m: float(np.median(vs)) for m, vs in sorted(months.items())}

    # Pump/tank operating state (analysis)
    pump_j = context.flow_ids.index("PUMP_1")
    t1_j = context.level_ids.index("T1")
    pump = context.flows[analysis_start:analysis_end, pump_j]
    t1 = context.levels[analysis_start:analysis_end, t1_j]
    # correlate z with pump/tank where finite
    def safe_corr(a, b):
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 50:
            return float("nan")
        if np.std(a[m]) < 1e-12 or np.std(b[m]) < 1e-12:
            return float("nan")
        return float(np.corrcoef(a[m], b[m])[0, 1])

    # Bias: train vs analysis median raw residual
    med_tr = float(np.nanmedian(raw_tr)) if np.isfinite(raw_tr).any() else float("nan")
    med_an = float(np.nanmedian(raw_an)) if np.isfinite(raw_an).any() else float("nan")
    mad_tr = _mad(raw_tr)
    mad_an = _mad(raw_an)

    # Classification heuristics (evidence tags, not labels)
    tags = []
    if np.isfinite(med_tr) and np.isfinite(med_an) and abs(med_an - med_tr) > max(0.05, 2 * mad_tr):
        tags.append("baseline_bias")
    if np.isfinite(mad_tr) and np.isfinite(mad_an) and mad_an > 2.0 * max(mad_tr, 1e-6):
        tags.append("scale_mismatch")
    if runs and np.median(runs) <= 3 and (np.mean(elev) if elev.size else 0) > 0.05:
        tags.append("isolated_spikes_common")
    if runs and max(runs) >= 12 * 6:  # >=6h consecutive
        tags.append("persistent_relationship_changes")
    # month-to-month spread
    if len(monthly_median) >= 3:
        vals = list(monthly_median.values())
        if max(vals) - min(vals) > 1.0:
            tags.append("monthly_drift")

    return {
        "target": sensor_ids[i],
        "refs": [sensor_ids[j] for j in tm.refs],
        "train_raw_residual_quantiles_m": quantiles(raw_tr),
        "analysis_raw_residual_quantiles_m": quantiles(raw_an),
        "train_raw_median_m": med_tr,
        "analysis_z_quantiles": quantiles(z),
        "frac_z_gt_k": float(np.mean(elev)) if elev.size else float("nan"),
        "exceedance_run_lengths_steps": {
            "n_runs": len(runs),
            "median": float(np.median(runs)) if runs else None,
            "p90": float(np.quantile(runs, 0.9)) if runs else None,
            "max": int(max(runs)) if runs else None,
        },
        "z_lag1_acf": acf_lag1(z),
        "monthly_median_z": monthly_median,
        "corr_z_vs_PUMP_1": safe_corr(z, pump),
        "corr_z_vs_T1": safe_corr(z, t1),
        "train_vs_analysis_raw_median_m": {"train": med_tr, "analysis": med_an},
        "train_vs_analysis_raw_MAD_m": {"train": mad_tr, "analysis": mad_an},
        "evidence_tags": tags,
    }


def onset_exclusion_mask(timestamps, leakages, start_i, end_i) -> np.ndarray:
    """True within ±CONTROL_EXCLUDE_DAYS of any labeled *onset* (not full leak life).

    Ongoing background leaks may still be open in control windows; we only keep
    controls away from labeled onset neighborhoods so diagnostic event times are
    not reused as ordinary references.
    """
    n = end_i - start_i
    mask = np.zeros(n, dtype=bool)
    pad = np.timedelta64(int(CONTROL_EXCLUDE_DAYS * 24 * 60), "m")
    onsets = [L.start for L in leakages]
    for local, abs_i in enumerate(range(start_i, end_i)):
        t = timestamps[abs_i]
        for t0 in onsets:
            if (t0 - pad) <= t <= (t0 + pad):
                mask[local] = True
                break
    return mask


def select_control_windows(
    timestamps,
    analysis_start,
    analysis_end,
    leakages,
    window_steps: int,
    n_controls: int = 3,
) -> list[dict]:
    """Documented rule (not visual convenience).

    Place candidate starts at analysis offsets floor(span_free * q) for
    q in {1/4, 2/4, 3/4}. A window is eligible if it lies in the analysis span
    and does not overlap ±7 d around any labeled onset. If ineligible, advance
    one day (288 steps) until eligible or span exhausted.

    Controls are not assumed leak-free (background leaks may remain open).
    """
    span = analysis_end - analysis_start
    excl = onset_exclusion_mask(timestamps, leakages, analysis_start, analysis_end)
    free = span - window_steps
    if free <= 0:
        return []
    qs = [0.25, 0.5, 0.75][:n_controls]
    chosen = []
    used = set()
    for q in qs:
        start_local = int(free * q)
        while start_local + window_steps <= span:
            if start_local in used:
                start_local += STEPS_PER_DAY
                continue
            seg = excl[start_local : start_local + window_steps]
            if not np.any(seg):
                abs0 = analysis_start + start_local
                chosen.append(
                    {
                        "start_idx": abs0,
                        "end_idx": abs0 + window_steps,
                        "start_time": str(timestamps[abs0]).replace("T", " "),
                        "end_time": str(timestamps[abs0 + window_steps - 1]).replace("T", " "),
                        "rule": f"quartile_q={q}_onset_exclusion_advanced",
                    }
                )
                used.add(start_local)
                break
            start_local += STEPS_PER_DAY
    return chosen


def event_window(onset, timestamps, analysis_start, analysis_end):
    center = int(np.searchsorted(timestamps, onset, side="left"))
    pre = int(PRE_H * 12)
    post = int(POST_H * 12)
    a0 = center - pre
    a1 = center + post
    a0 = max(a0, analysis_start)
    a1 = min(a1, analysis_end)
    # Force equal length if clipped: prefer post-onset length WINDOW_STEPS if possible
    if a1 - a0 < WINDOW_STEPS:
        # expand if possible
        need = WINDOW_STEPS - (a1 - a0)
        a0 = max(analysis_start, a0 - need)
        a1 = min(analysis_end, a0 + WINDOW_STEPS)
    elif a1 - a0 > WINDOW_STEPS:
        a1 = a0 + WINDOW_STEPS
    return a0, a1


def separability_for_event(
    pressures,
    timestamps,
    sensor_ids,
    sig,
    leak,
    controls,
    analysis_start,
):
    """Raw pair residuals + target aggregate around onset vs controls.

    Sensors: all targets that use training-selected refs only (no leak-location picking).
    Report network-wide median |Δ| and the target with largest post-onset rise in z
    *among all sensors* without using pipe identity for selection — for plots we show
    top-3 by |event_median_z - control_median_z| computed only after defining windows
    from labels for timing. Actually user said: do not select sensors using known leak
    locations. So plot a fixed set: all sensors' aggregate summary + plot sensors
    with largest training-scale sensitivity? Better: plot the three targets with
    largest *control* MAD of z (most variable ordinary) AND report event stats for
    all targets; for figure show median z across all targets plus the three highest
    event-minus-control contrast sensors selected by contrast magnitude (uses event
    window timing from labels but not leak topology). Contrast uses the labeled
    time window only — allowed ("labels may identify diagnostic event windows only").
    """
    analysis_end = sig.analysis_offset + sig.z.shape[0]
    a0, a1 = event_window(leak.start, timestamps, analysis_start, analysis_end)
    off = sig.analysis_offset
    e0 = max(0, a0 - off)
    e1 = min(sig.z.shape[0], a1 - off)
    onset_local = int(np.searchsorted(timestamps, leak.start) - off)

    # Per-target event vs control contrast on aggregate z
    contrasts = []
    for ti, tm in enumerate(sig.target_models):
        z = sig.z[:, ti]
        ev = z[e0:e1]
        # post-onset slice within window
        post0 = max(e0, onset_local)
        post = z[post0:e1]
        ctrl_vals = []
        for c in controls:
            c0 = c["start_idx"] - off
            c1 = c["end_idx"] - off
            if c0 < 0 or c1 > len(z):
                continue
            ctrl_vals.append(z[c0:c1])
        if not ctrl_vals or not np.isfinite(ev).any():
            continue
        ctrl_stack = np.concatenate([v[np.isfinite(v)] for v in ctrl_vals if np.isfinite(v).any()])
        if ctrl_stack.size == 0:
            continue
        ev_med = float(np.nanmedian(post)) if np.isfinite(post).any() else float("nan")
        ctrl_med = float(np.median(ctrl_stack))
        ev_max = float(np.nanmax(post)) if np.isfinite(post).any() else float("nan")
        ctrl_meds = [float(np.nanmedian(v)) for v in ctrl_vals if np.isfinite(v).any()]
        # Percentile of event post median among pooled control *samples* (equal-length windows)
        pct = (
            float(100.0 * np.mean(ctrl_stack <= ev_med))
            if ctrl_stack.size and np.isfinite(ev_med)
            else float("nan")
        )
        beats_all_ctrl_medians = bool(
            ctrl_meds and np.isfinite(ev_med) and ev_med > max(ctrl_meds)
        )
        # raw meters: median of per-ref residuals post-onset
        raw_post = []
        raw_ctrl = []
        for j, pm in tm.pairs.items():
            e_post = signed_residual(pressures, ti, j, pm, off + post0, off + e1)
            raw_post.append(e_post)
            for c in controls:
                raw_ctrl.append(
                    signed_residual(pressures, ti, j, pm, c["start_idx"], c["end_idx"])
                )
        raw_post_m = float(np.nanmedian(np.concatenate(raw_post))) if raw_post else float("nan")
        raw_ctrl_m = float(np.nanmedian(np.concatenate(raw_ctrl))) if raw_ctrl else float("nan")
        contrasts.append(
            {
                "target": sensor_ids[ti],
                "refs": [sensor_ids[j] for j in tm.refs],
                "event_post_median_z": ev_med,
                "event_post_max_z": ev_max,
                "control_median_z": ctrl_med,
                "delta_z": ev_med - ctrl_med if np.isfinite(ev_med) else float("nan"),
                "event_median_percentile_vs_control_samples": pct,
                "beats_all_control_window_medians": beats_all_ctrl_medians,
                "event_post_median_raw_residual_m": raw_post_m,
                "control_median_raw_residual_m": raw_ctrl_m,
                "delta_raw_m": raw_post_m - raw_ctrl_m
                if np.isfinite(raw_post_m) and np.isfinite(raw_ctrl_m)
                else float("nan"),
            }
        )
    contrasts.sort(key=lambda r: abs(r["delta_z"]) if np.isfinite(r["delta_z"]) else -1, reverse=True)

    # Stand-out before CUSUM: compare delta_z and delta_raw to control dispersion
    ctrl_delta_scale = float(np.nanstd([c["control_median_z"] for c in contrasts[:10]])) if contrasts else float("nan")
    top = contrasts[:5]
    standout = False
    if top:
        t0 = top[0]
        # Stand out in z and meters relative to equal-length ordinary controls
        standout = bool(
            np.isfinite(t0["delta_z"])
            and t0["delta_z"] > 2.0
            and t0["event_median_percentile_vs_control_samples"] >= 95
            and t0["beats_all_control_window_medians"]
            and np.isfinite(t0["delta_raw_m"])
            and abs(t0["delta_raw_m"]) > 0.05
        )

    return {
        "pipe": leak.pipe,
        "onset": str(leak.start).replace("T", " "),
        "event_window": {
            "start": str(timestamps[a0]).replace("T", " "),
            "end": str(timestamps[a1 - 1]).replace("T", " "),
            "pre_hours": PRE_H,
            "post_hours": POST_H,
        },
        "controls": controls,
        "top_contrasts_by_abs_delta_z": top,
        "n_targets_scored": len(contrasts),
        "stands_out_before_cusum_accumulation": standout,
        "note": (
            "Contrast ranking uses labeled onset time only for window placement; "
            "no leak-location sensor picking. Examined diagnostic examples, not validation."
        ),
    }, contrasts, (a0, a1, e0, e1, onset_local)


def make_separability_plot(
    pressures,
    timestamps,
    sensor_ids,
    sig,
    leak,
    controls,
    contrasts,
    window_meta,
    out_path: Path,
):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        return f"plot_error:{exc}"

    a0, a1, e0, e1, onset_local = window_meta
    off = sig.analysis_offset
    # Plot top-3 contrast targets: all refs' raw residuals + aggregate z
    top = contrasts[:3]
    fig, axes = plt.subplots(len(top) + 1, 1, figsize=(12, 3.2 * (len(top) + 1)), sharex=False)
    if len(top) == 0:
        plt.close(fig)
        return "no_targets"
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])

    for ax, row in zip(axes[:-1], top):
        ti = sensor_ids.index(row["target"])
        tm = sig.target_models[ti]
        # event window raw residuals per ref
        t_rel = np.arange(e0, e1)
        for j, pm in tm.pairs.items():
            e = signed_residual(pressures, ti, j, pm, off + e0, off + e1)
            ax.plot(t_rel, e, lw=0.7, alpha=0.85, label=f"e via {sensor_ids[j]}")
        ax.plot(t_rel, sig.z[e0:e1, ti], color="#000", lw=1.0, label="z aggregate")
        ax.axvline(onset_local, color="#c45c26", ls="--", lw=1)
        ax.axhline(0, color="#999", lw=0.5)
        ax.set_ylabel("m / z")
        ax.set_title(
            f"{leak.pipe}: {row['target']} refs={row['refs']} "
            f"Δz={row['delta_z']:.2f} Δraw={row['delta_raw_m']:.3f} m "
            f"pct={row['event_median_percentile_vs_control_samples']:.0f}"
        )
        ax.legend(fontsize=6, ncol=3)

    # Control comparison panel: event post median z vs each control window median for top target
    ax = axes[-1]
    if top:
        ti = sensor_ids.index(top[0]["target"])
        # bar-like: control medians + event
        vals = []
        labels = []
        for c in controls:
            c0 = c["start_idx"] - off
            c1 = c["end_idx"] - off
            vals.append(float(np.nanmedian(sig.z[c0:c1, ti])))
            labels.append("ctrl " + c["start_time"][5:16])
        post0 = max(e0, onset_local)
        vals.append(float(np.nanmedian(sig.z[post0:e1, ti])))
        labels.append("event post")
        ax.bar(range(len(vals)), vals, color=["#8ecae6"] * (len(vals) - 1) + ["#c45c26"])
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
        ax.set_ylabel(f"median z ({top[0]['target']})")
        ax.set_title("Equal-length controls vs event (documented quartile rule)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return str(out_path.relative_to(ROOT))


def recommend(pair_rows, excursion_rows, sep_rows) -> dict:
    ratios = [r["oos_MAD_over_train_MAD"] for r in pair_rows if np.isfinite(r["oos_MAD_over_train_MAD"])]
    frac_under = float(np.mean(np.array(ratios) > 2.0)) if ratios else 0.0
    tiny = [r for r in pair_rows if r["train_residual_MAD_m"] < 0.05]
    frac_tiny = len(tiny) / max(1, len(pair_rows))

    tag_counts = {}
    for ex in excursion_rows:
        for t in ex["evidence_tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    standout_n = sum(1 for s in sep_rows if s["stands_out_before_cusum_accumulation"])
    # Overlap: top delta_z small or percentile low
    weak = 0
    for s in sep_rows:
        if not s["top_contrasts_by_abs_delta_z"]:
            weak += 1
            continue
        t = s["top_contrasts_by_abs_delta_z"][0]
        if not (
            t["delta_z"] > 2
            and t["event_median_percentile_vs_control_samples"] >= 95
            and t.get("beats_all_control_window_medians")
        ):
            weak += 1

    # Decision priority per user instructions
    # Priority: (1) OOS underestimation (2) ordinary/leak overlap (3) operating drift
    if frac_under >= 0.5 or (frac_tiny >= 0.5 and frac_under >= 0.3):
        return {
            "direction": "chronological_out_of_sample_calibration",
            "proposal": (
                "Next experiment: calibrate residual location/scale on a chronological "
                "out-of-fit window after the fitting period (hold out post-train days for "
                "MAD/loc), keeping training-only reference selection. Do not apply an "
                "arbitrary scale floor; let OOS dispersion set normalization."
            ),
            "supported_by": (
                f"{frac_under:.0%} of selected pairs have OOS MAD > 2× train MAD; "
                f"{frac_tiny:.0%} have train MAD < 0.05 m."
            ),
        }
    if standout_n == 0 or weak >= 2:
        # Near-term OOS MAD matches train (tiny scales look "real"), yet events do not
        # separate from ordinary controls → calibration alone will not fix detection.
        return {
            "direction": "calibration_unlikely_alone",
            "proposal": (
                "Ordinary and leak-timed residual changes overlap substantially under "
                "the documented controls; calibration alone is unlikely to solve "
                "detection. Revisit the sensing hypothesis, aggregation, or "
                "state-conditional features—without an arbitrary scale floor."
            ),
            "supported_by": (
                f"abrupt events standing out before CUSUM: {standout_n}/3; "
                f"weak-separability count={weak}; "
                f"median OOS/train MAD={float(np.median(ratios)) if ratios else None:.3f}; "
                f"tags={tag_counts}"
            ),
        }
    if tag_counts.get("monthly_drift", 0) >= 10 or tag_counts.get("baseline_bias", 0) >= 10:
        return {
            "direction": "conditional_baseline_or_causal_adaptation",
            "proposal": (
                "Next experiment: a justified conditional baseline or causal adaptation "
                "keyed to operating state (e.g. pump/tank strata or slow chronological "
                "adaptation), not a recovery sweep."
            ),
            "supported_by": f"evidence_tag_counts={tag_counts}; standout={standout_n}/3",
        }
    return {
        "direction": "conditional_baseline_or_causal_adaptation",
        "proposal": (
            "Next experiment: conditional baseline / causal adaptation "
            "(measurement-supported among remaining options)."
        ),
        "supported_by": f"oos_inflation_frac={frac_under:.2f}; tags={tag_counts}; standout={standout_n}/3",
    }


def render(summary: dict) -> str:
    lines = [
        "# Residual calibration & separability audit",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Frozen detectors, RESULTS, variant comparison, and production are **preserved**. "
        "No recovery sweep, normalization floor, or new detector.",
        "",
        f"DIAG fits: train_days={summary['settings']['train_days']}, K={summary['settings']['n_refs']}, "
        f"k={summary['settings']['cusum_k']}.",
        "",
        "## 1. Normalization verification",
        "",
        r"Signed residual \(e = \hat P_i - P_i\) in **meters**. "
        f"Scale = MAD(e)·{MAD_SCALE} with std fallback if MAD scale < 1e-6.",
        "",
        f"- Selected pairs: **{summary['normalization']['n_pairs']}**",
        f"- Train MAD < 0.05 m: **{summary['normalization']['n_tiny_train_mad']}** "
        f"({summary['normalization']['frac_tiny_train_mad']:.1%})",
        f"- OOS MAD / train MAD > 2: **{summary['normalization']['n_oos_inflate_gt2']}** "
        f"({summary['normalization']['frac_oos_inflate_gt2']:.1%})",
        f"- Scale fallback used: **{summary['normalization']['n_scale_fallback']}**",
        "",
        "Interpretation counts:",
        "",
    ]
    for k, v in summary["normalization"]["interpretation_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines += [
        "",
        "Full per-pair table: `outputs/calibration_pairs.json`.",
        "",
        "### Sample pairs (smallest train MAD)",
        "",
        "| Target | Ref | a (m) | b | train MAD (m) | scale (m) | OOS MAD (m) | OOS/train | reading |",
        "|--------|-----|-------|---|---------------|-----------|-------------|-----------|---------|",
    ]
    for r in summary["normalization"]["smallest_mad_examples"]:
        lines.append(
            f"| {r['target']} | {r['reference']} | {r['intercept_m']:.3f} | {r['slope']:.3f} | "
            f"{r['train_residual_MAD_m']:.4f} | {r['norm_scale_m']:.4f} | "
            f"{r['oos_14d_residual_MAD_m']:.4f} | {r['oos_MAD_over_train_MAD']:.2f} | "
            f"{r['scale_interpretation']} |"
        )
    lines += [
        "",
        "## 2. Ordinary excursions (train vs analysis)",
        "",
        f"Evidence-tag totals across {len(summary['excursions'])} targets: "
        f"{summary['excursion_tag_totals']}",
        "",
        f"- Median frac(z>k): **{summary['excursion_summary']['median_frac_z_gt_k']:.3f}**",
        f"- Median lag-1 ACF(z): **{summary['excursion_summary']['median_lag1_acf']:.3f}**",
        f"- Targets with max exceedance run ≥ 6 h: "
        f"**{summary['excursion_summary']['n_max_run_ge_6h']}**",
        "",
        "Unmatched / non-onset periods are **not** assumed leak-free (background leaks, ops).",
        "",
        "Per-target details: `outputs/calibration_excursions.json`.",
        "",
        "## 3. Signal separability (abrupt DIAG examples)",
        "",
        "**Control rule:** equal-length windows "
        f"({PRE_H:g} h pre + {POST_H:g} h post = {WINDOW_STEPS} steps). "
        "Candidate starts at analysis free-span quartiles {1/4, 2/4, 3/4}; "
        f"reject if overlapping ±{CONTROL_EXCLUDE_DAYS:g} d around any labeled "
        "**onset** (not full leak lifetime); else advance +1 day until eligible. "
        "Controls are not assumed leak-free. Not chosen by visual convenience.",
        "",
        "Labels identify event window timing only. No leak-location sensor picking. "
        "**Not validation.**",
        "",
    ]
    for s in summary["separability"]:
        lines += [
            f"### {s['pipe']} onset {s['onset']}",
            f"- Stands out before CUSUM (rule): **{s['stands_out_before_cusum_accumulation']}**",
            f"- Plot: {s.get('plot')}",
            f"- Controls: {[c['start_time'] for c in s['controls']]}",
            "",
        ]
        if s["top_contrasts_by_abs_delta_z"]:
            lines.append(
                "| Target | Δz | Δraw (m) | event post z | ctrl z | pct vs ctrl samples | beats all ctrl medians | refs |"
            )
            lines.append(
                "|--------|----|----------|--------------|--------|---------------------|------------------------|------|"
            )
            for t in s["top_contrasts_by_abs_delta_z"][:5]:
                lines.append(
                    f"| {t['target']} | {t['delta_z']:.2f} | {t['delta_raw_m']:.3f} | "
                    f"{t['event_post_median_z']:.2f} | {t['control_median_z']:.2f} | "
                    f"{t['event_median_percentile_vs_control_samples']:.0f} | "
                    f"{t['beats_all_control_window_medians']} | {t['refs']} |"
                )
        lines.append("")
    lines += [
        "## 4. Recommended next experiment",
        "",
        f"**Direction:** `{summary['recommendation']['direction']}`",
        "",
        summary["recommendation"]["proposal"],
        "",
        f"**Supported by:** {summary['recommendation']['supported_by']}",
        "",
        "Not implemented. No 2019 evaluation.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    print("Loading…", flush=True)
    pressures_b = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    context = load_context(DEFAULT_RAW)
    leakages = load_leakages()
    assert np.array_equal(pressures_b.timestamps, context.timestamps)
    timestamps = pressures_b.timestamps
    sensor_ids = pressures_b.sensor_ids
    pressures = pressures_b.pressures

    start_i, end_i = period_indices(timestamps, DIAG)
    train_start = start_i
    train_end = start_i + FROZEN["train_days"] * STEPS_PER_DAY
    print("Building frozen DIAG signals…", flush=True)
    sig = build_signals(
        pressures,
        interval_start=start_i,
        interval_end=end_i,
        train_days=FROZEN["train_days"],
        n_refs=FROZEN["n_refs"],
    )
    analysis_start = sig.analysis_offset
    analysis_end = end_i

    # --- 1. pairs ---
    pair_rows = []
    for tm in sig.target_models:
        for j, pm in tm.pairs.items():
            # Recompute scale path metadata with explicit fallbacks
            row = pair_calibration_row(
                pressures,
                sensor_ids,
                tm.target,
                j,
                pm,
                train_start,
                train_end,
                analysis_start,
                analysis_end,
            )
            pair_rows.append(row)

    interp_counts: dict[str, int] = {}
    for r in pair_rows:
        interp_counts[r["scale_interpretation"]] = interp_counts.get(r["scale_interpretation"], 0) + 1
    ratios = [r["oos_MAD_over_train_MAD"] for r in pair_rows if np.isfinite(r["oos_MAD_over_train_MAD"])]
    tiny = [r for r in pair_rows if np.isfinite(r["train_residual_MAD_m"]) and r["train_residual_MAD_m"] < 0.05]
    inflate = [r for r in pair_rows if np.isfinite(r["oos_MAD_over_train_MAD"]) and r["oos_MAD_over_train_MAD"] > 2.0]

    # --- 2. excursions ---
    print("Excursion diagnostics…", flush=True)
    excursions = []
    for tm in sig.target_models:
        excursions.append(
            target_excursion_report(
                pressures,
                timestamps,
                context,
                sensor_ids,
                tm,
                train_start,
                train_end,
                analysis_start,
                analysis_end,
                sig.z[:, tm.target],
            )
        )
    tag_totals: dict[str, int] = {}
    for ex in excursions:
        for t in ex["evidence_tags"]:
            tag_totals[t] = tag_totals.get(t, 0) + 1
    fracs = [ex["frac_z_gt_k"] for ex in excursions if np.isfinite(ex["frac_z_gt_k"])]
    acfs = [ex["z_lag1_acf"] for ex in excursions if np.isfinite(ex["z_lag1_acf"])]
    n_long = sum(
        1
        for ex in excursions
        if ex["exceedance_run_lengths_steps"]["max"]
        and ex["exceedance_run_lengths_steps"]["max"] >= 12 * 6
    )

    # --- 3. separability ---
    print("Separability…", flush=True)
    controls = select_control_windows(
        timestamps, analysis_start, analysis_end, leakages, WINDOW_STEPS, n_controls=3
    )
    abrupt = [L for L in onsets_in_period(leakages, DIAG) if L.leak_type == "abrupt"]
    # Prefer post-training abrupt (eligible) — still the three DIAG abrupt events
    sep_rows = []
    plot_dir = OUT / "calibration_plots"
    for L in abrupt:
        sep, contrasts, meta = separability_for_event(
            pressures, timestamps, sensor_ids, sig, L, controls, analysis_start
        )
        plot_path = plot_dir / f"separability_{L.pipe}.png"
        sep["plot"] = make_separability_plot(
            pressures, timestamps, sensor_ids, sig, L, controls, contrasts, meta, plot_path
        )
        sep_rows.append(sep)

    rec = recommend(pair_rows, excursions, sep_rows)

    smallest = sorted(pair_rows, key=lambda r: r["train_residual_MAD_m"] or 1e9)[:8]
    summary = {
        "generated_at": iso_now(),
        "settings": FROZEN,
        "preserved": "original+variant detectors and frozen outputs unchanged",
        "normalization": {
            "n_pairs": len(pair_rows),
            "n_tiny_train_mad": len(tiny),
            "frac_tiny_train_mad": len(tiny) / max(1, len(pair_rows)),
            "n_oos_inflate_gt2": len(inflate),
            "frac_oos_inflate_gt2": len(inflate) / max(1, len(pair_rows)),
            "median_oos_over_train_MAD": float(np.median(ratios)) if ratios else None,
            "n_scale_fallback": sum(1 for r in pair_rows if r["scale_used_fallback"]),
            "interpretation_counts": interp_counts,
            "smallest_mad_examples": smallest,
            "scale_formula_doc": (
                "scale = MAD(signed residual e)*1.4826 on training samples; "
                "if not finite or <1e-6, fall back to sample std; units meters"
            ),
        },
        "excursions": excursions,
        "excursion_tag_totals": tag_totals,
        "excursion_summary": {
            "median_frac_z_gt_k": float(np.median(fracs)) if fracs else None,
            "median_lag1_acf": float(np.median(acfs)) if acfs else None,
            "n_max_run_ge_6h": n_long,
        },
        "control_rule": {
            "window_steps": WINDOW_STEPS,
            "pre_hours": PRE_H,
            "post_hours": POST_H,
            "exclude_days_around_leaks": CONTROL_EXCLUDE_DAYS,
            "placement": "analysis free-span quartiles with +1 day advance if excluded",
            "selected_controls": controls,
        },
        "separability": sep_rows,
        "recommendation": rec,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calibration_pairs.json").write_text(json.dumps(pair_rows, indent=2) + "\n")
    (OUT / "calibration_excursions.json").write_text(json.dumps(excursions, indent=2) + "\n")
    # Slim summary without full excursions duplicated? keep pointers
    slim = dict(summary)
    slim["excursions"] = f"{len(excursions)} targets → calibration_excursions.json"
    (OUT / "calibration_audit_summary.json").write_text(json.dumps(slim, indent=2) + "\n")
    (OUT / "CALIBRATION_AUDIT.md").write_text(render(summary) + "\n")
    print(rec["direction"], "-", rec["proposal"][:200])
    print(f"Wrote {OUT / 'CALIBRATION_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
