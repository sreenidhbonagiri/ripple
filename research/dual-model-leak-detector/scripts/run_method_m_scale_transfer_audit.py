#!/usr/bin/env python3
"""Method M scale-transfer audit (no fitting, no τ change, no Method M rerun).

Protocol notes embedded in output. Preserves Method M artifacts.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_eval import period_bounds, timing_nulls  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    ABRUPT_EVENTS,
    CREDIT_HOURS,
    EPS_SIGMA,
    REF_GAP_HOURS,
    REF_HOURS,
    REF_MIN_SAMPLES,
    REQUIRED_FROZEN_SHA256,
    WARMUP_HOURS,
)
from dual_model.detection_scores import _ref_slice  # noqa: E402
from dual_model.dual_series import verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import subsample_hourly  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402
from dual_model.scada_io import load_flows_2018  # noqa: E402

OUT = ROOT / "outputs" / "detection_2018_measured_pump1"
AUDIT = OUT / "method_m_scale_transfer"
SCALE_START = pd.Timestamp("2018-01-09 01:00:00")
SCALE_END = pd.Timestamp("2018-01-21 23:00:00")
EXCLUDE_H = 72
N_CTRL = 25
TAU_M = 4.347
FOCUS = ("p183", "p369")


def compute_deltas(qv: pd.DataFrame) -> pd.DataFrame:
    cols = list(qv.columns)
    deltas = pd.DataFrame(np.nan, index=qv.index, columns=cols, dtype=float)
    for t in qv.index:
        ref_idx = _ref_slice(qv.index, t)
        if len(ref_idx) < REF_MIN_SAMPLES:
            continue
        row = qv.loc[t, cols].astype(float)
        ref = qv.loc[ref_idx, cols].astype(float)
        n_ref = ref.notna().sum(axis=0)
        ok = row.notna() & (n_ref >= REF_MIN_SAMPLES)
        if not bool(ok.any()):
            continue
        use = ok.index[ok]
        mu = ref.loc[:, use].mean(axis=0)
        deltas.loc[t, use] = row.loc[use] - mu
    return deltas


def onset_mask(index: pd.DatetimeIndex, onsets: list[pd.Timestamp], hours: int) -> pd.Series:
    m = pd.Series(False, index=index)
    for o in onsets:
        m |= (index >= o - pd.Timedelta(hours=hours)) & (index <= o + pd.Timedelta(hours=hours))
    return m


def select_controls(
    t0: pd.Timestamp,
    *,
    index: pd.DatetimeIndex,
    q_ext: pd.Series,
    pump: pd.Series,
    abrupt_onsets: list[pd.Timestamp],
) -> list[pd.Timestamp]:
    pre0 = index[(index >= t0 - pd.Timedelta(hours=6)) & (index < t0)]
    if len(pre0) < 3:
        return []
    q0 = float(q_ext.reindex(pre0).mean())
    p0 = float(pump.reindex(pre0).mean())
    hod = t0.hour
    cands = []
    for t in index:
        if t.hour != hod:
            continue
        if abs((t - t0).total_seconds()) < 7 * 24 * 3600:
            continue
        if any(abs((t - o).total_seconds()) <= EXCLUDE_H * 3600 for o in abrupt_onsets):
            continue
        pre = index[(index >= t - pd.Timedelta(hours=6)) & (index < t)]
        post = index[(index >= t) & (index <= t + pd.Timedelta(hours=6))]
        if len(pre) < 3 or len(post) < 3:
            continue
        dq = abs(float(q_ext.reindex(pre).mean()) - q0)
        dp = abs(float(pump.reindex(pre).mean()) - p0)
        cands.append((dq + dp, t))
    if not cands:
        return []
    dists = np.asarray([c[0] for c in cands], dtype=float)
    thr = float(np.quantile(dists, 0.80))
    filtered = [c for c in cands if c[0] <= thr] or cands
    filtered.sort(key=lambda x: x[0])
    return [c[1] for c in filtered[:N_CTRL]]


def window_stats(
    t0: pd.Timestamp,
    *,
    deltas: pd.DataFrame,
    sigma_scale: pd.Series,
    sigma_local: pd.Series,
    cal: float,
) -> dict:
    post = deltas.index[
        (deltas.index >= t0) & (deltas.index <= t0 + pd.Timedelta(hours=CREDIT_HOURS))
    ]
    D = deltas.loc[post]
    # max over credit hours of |δ_i|, then network max
    abs_d = D.abs()
    # per sensor: max |δ| in credit
    sens_max_abs = abs_d.max(axis=0)
    sens_mean_abs = abs_d.mean(axis=0)
    # z under SCALE and local
    z_sc = sens_max_abs / sigma_scale.reindex(sens_max_abs.index).clip(lower=EPS_SIGMA)
    z_loc = sens_max_abs / sigma_local.reindex(sens_max_abs.index).clip(lower=EPS_SIGMA)
    # network maxima
    def _argmax(s: pd.Series):
        s = s[np.isfinite(s)]
        if len(s) == 0:
            return None, float("nan")
        i = s.abs().idxmax() if (s < 0).any() else s.idxmax()
        # for nonnegative use idxmax
        i = s.idxmax()
        return str(i), float(s.loc[i])

    top_abs_s, top_abs = _argmax(sens_max_abs)
    top_zsc_s, top_zsc = _argmax(z_sc)
    top_zloc_s, top_zloc = _argmax(z_loc)
    # Method M raw-style network max |z_scale| / cal over credit hours (hour-wise then max)
    hour_raw = []
    for t in post:
        row = D.loc[t]
        ok = [c for c in sigma_scale.index if c in row.index and np.isfinite(float(row[c]))]
        if not ok:
            continue
        z = (row[ok].astype(float).abs() / sigma_scale.loc[ok].clip(lower=EPS_SIGMA))
        z = z[np.isfinite(z)]
        if len(z):
            hour_raw.append(float(z.max()) / cal)
    return {
        "n_post": int(len(post)),
        "network_max_abs_delta": top_abs,
        "argmax_abs_delta_sensor": top_abs_s,
        "network_max_z_scale": top_zsc,
        "argmax_z_scale_sensor": top_zsc_s,
        "network_max_z_local": top_zloc,
        "argmax_z_local_sensor": top_zloc_s,
        "credit_max_s_M_from_deltas": float(np.nanmax(hour_raw)) if hour_raw else float("nan"),
        "per_sensor_max_abs_delta": {k: float(v) for k, v in sens_max_abs.items() if np.isfinite(v)},
        "per_sensor_max_z_scale": {k: float(v) for k, v in z_sc.items() if np.isfinite(v)},
        "per_sensor_max_z_local": {k: float(v) for k, v in z_loc.items() if np.isfinite(v)},
    }


def snr(event: float, ctrls: list[float]) -> float:
    arr = np.asarray([c for c in ctrls if np.isfinite(c)], dtype=float)
    if not np.isfinite(event) or len(arr) < 3:
        return float("nan")
    return float((event - arr.mean()) / max(float(arr.std(ddof=0)), 1e-6))


def classify_focus(snr_abs: float, snr_zsc: float, snr_zloc: float) -> str:
    """Separate weak numerator vs January-scale obscuring."""
    def ge(x, t=1.5):
        return np.isfinite(x) and abs(x) >= t

    def lt(x, t=1.5):
        return np.isfinite(x) and abs(x) < t

    if lt(snr_abs) and lt(snr_zloc):
        return "weak_vs_contemporaneous_ordinary"
    if ge(snr_abs) and lt(snr_zsc) and ge(snr_zloc):
        return "january_scale_obscures_local_unusual"
    if ge(snr_abs) and ge(snr_zsc):
        return "numerator_and_scale_norm_both_elevated_but_below_tau"
    if lt(snr_abs) and ge(snr_zsc):
        return "scale_deflation_amplifies_ordinary_delta"
    return "mixed_or_unclear"


def main() -> int:
    AUDIT.mkdir(parents=True, exist_ok=True)
    digest = verify_frozen_hash(ROOT / "outputs" / "calibration" / "frozen_calibration.json")
    assert digest == REQUIRED_FROZEN_SHA256

    meta = json.loads((OUT / "method_m_results.json").read_text())
    sigma_scale = pd.Series(meta["scale"]["sigma_m3h"], dtype=float)
    cal = float(meta["scale"]["raw_max_median"])
    assert abs(cal - meta["scale"]["raw_max_median"]) < 1e-9

    print("Loading q_v and building causal δ_i …", flush=True)
    qv = pd.read_csv(OUT / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    score_m = pd.read_csv(OUT / "score_M.csv", index_col=0, parse_dates=True).iloc[:, 0]
    deltas = compute_deltas(qv)
    # cache deltas for inspection size — optional csv gitignored
    deltas.to_csv(AUDIT / "deltas_hourly.csv")

    F = subsample_hourly(load_flows_2018()).reindex(qv.index)
    q_ext = F["p227"].astype(float) + F["p235"].astype(float)
    pump = F["PUMP_1"].astype(float)

    onsets = [pd.Timestamp(ev.onset) for ev in ABRUPT_EVENTS]
    near_onset = onset_mask(deltas.index, onsets, EXCLUDE_H)

    # Monthly σ of δ (non-onset-neighborhood hours only — not labeled leak-free)
    months = sorted({(t.year, t.month) for t in deltas.index})
    monthly_sigma = {}
    transfer_rows = []
    for y, m in months:
        mask = (deltas.index.year == y) & (deltas.index.month == m) & (~near_onset.to_numpy())
        sub = deltas.loc[mask]
        row = {"year": y, "month": m, "n_hours": int(mask.sum())}
        for s in sigma_scale.index:
            x = sub[s].astype(float)
            x = x[np.isfinite(x)]
            if len(x) < 24:
                sig_m = float("nan")
            else:
                sig_m = float(max(float(x.std(ddof=0)), EPS_SIGMA))
            monthly_sigma[(y, m, s)] = sig_m
            ratio = sig_m / float(sigma_scale[s]) if np.isfinite(sig_m) else float("nan")
            transfer_rows.append(
                {
                    "sensor": s,
                    "year": y,
                    "month": m,
                    "sigma_scale": float(sigma_scale[s]),
                    "sigma_month_non_onset_nbhd": sig_m,
                    "ratio_month_over_scale": ratio,
                    "n_hours": int(len(x)),
                }
            )
        row["median_ratio"] = float(
            np.nanmedian([r["ratio_month_over_scale"] for r in transfer_rows if r["month"] == m and r["year"] == y])
        )
    pd.DataFrame(transfer_rows).to_csv(AUDIT / "per_sensor_month_scale_ratios.csv", index=False)

    # Summary table by month
    month_summary = []
    for y, m in months:
        ratios = [
            r["ratio_month_over_scale"]
            for r in transfer_rows
            if r["year"] == y and r["month"] == m and np.isfinite(r["ratio_month_over_scale"])
        ]
        if not ratios:
            continue
        month_summary.append(
            {
                "year_month": f"{y:04d}-{m:02d}",
                "n_sensors": len(ratios),
                "ratio_median": float(np.median(ratios)),
                "ratio_p10": float(np.quantile(ratios, 0.1)),
                "ratio_p90": float(np.quantile(ratios, 0.9)),
                "frac_ratio_gt_1_5": float(np.mean(np.asarray(ratios) > 1.5)),
                "frac_ratio_lt_0_67": float(np.mean(np.asarray(ratios) < 2 / 3)),
            }
        )

    # Focus events p183, p369
    focus_reports = []
    for ev in ABRUPT_EVENTS:
        if ev.pipe not in FOCUS:
            continue
        t0 = pd.Timestamp(ev.onset)
        y, m = t0.year, t0.month
        sig_local = pd.Series(
            {s: monthly_sigma.get((y, m, s), float("nan")) for s in sigma_scale.index},
            dtype=float,
        )
        # fill missing local with scale (documented)
        sig_local = sig_local.fillna(sigma_scale)

        ev_stats = window_stats(
            t0, deltas=deltas, sigma_scale=sigma_scale, sigma_local=sig_local, cal=cal
        )
        ctrls = select_controls(
            t0, index=qv.index, q_ext=q_ext, pump=pump, abrupt_onsets=onsets
        )
        ctrl_stats = [
            window_stats(
                tc, deltas=deltas, sigma_scale=sigma_scale, sigma_local=sig_local, cal=cal
            )
            for tc in ctrls
        ]
        snr_abs = snr(
            ev_stats["network_max_abs_delta"],
            [c["network_max_abs_delta"] for c in ctrl_stats],
        )
        snr_zsc = snr(
            ev_stats["network_max_z_scale"],
            [c["network_max_z_scale"] for c in ctrl_stats],
        )
        snr_zloc = snr(
            ev_stats["network_max_z_local"],
            [c["network_max_z_local"] for c in ctrl_stats],
        )
        snr_sm = snr(
            ev_stats["credit_max_s_M_from_deltas"],
            [c["credit_max_s_M_from_deltas"] for c in ctrl_stats],
        )
        # stored score credit max
        post = score_m.index[
            (score_m.index >= t0) & (score_m.index <= t0 + pd.Timedelta(hours=CREDIT_HOURS))
        ]
        credit_score = score_m.reindex(post)
        credit_score = credit_score[np.isfinite(credit_score)]
        credit_max = float(credit_score.max()) if len(credit_score) else float("nan")

        verdict = classify_focus(snr_abs, snr_zsc, snr_zloc)
        # Top sensors by |δ| and by z_local / z_scale
        top_abs = sorted(
            ev_stats["per_sensor_max_abs_delta"].items(), key=lambda x: -x[1]
        )[:5]
        top_zloc = sorted(
            ev_stats["per_sensor_max_z_local"].items(), key=lambda x: -x[1]
        )[:5]
        top_zsc = sorted(
            ev_stats["per_sensor_max_z_scale"].items(), key=lambda x: -x[1]
        )[:5]

        focus_reports.append(
            {
                "pipe": ev.pipe,
                "onset": str(t0),
                "month_local_sigma": f"{y:04d}-{m:02d}",
                "n_controls": len(ctrls),
                "credit_max_score_M": credit_max,
                "tau_M": TAU_M,
                "below_tau": bool(np.isfinite(credit_max) and credit_max < TAU_M),
                "event_window": {
                    k: ev_stats[k]
                    for k in (
                        "network_max_abs_delta",
                        "argmax_abs_delta_sensor",
                        "network_max_z_scale",
                        "argmax_z_scale_sensor",
                        "network_max_z_local",
                        "argmax_z_local_sensor",
                        "credit_max_s_M_from_deltas",
                    )
                },
                "snr_vs_operating_matched_controls": {
                    "max_abs_delta": snr_abs,
                    "max_z_scale": snr_zsc,
                    "max_z_local_month": snr_zloc,
                    "credit_s_M": snr_sm,
                },
                "ctrl_means": {
                    "max_abs_delta": float(np.nanmean([c["network_max_abs_delta"] for c in ctrl_stats])),
                    "max_z_scale": float(np.nanmean([c["network_max_z_scale"] for c in ctrl_stats])),
                    "max_z_local": float(np.nanmean([c["network_max_z_local"] for c in ctrl_stats])),
                },
                "top_sensors_max_abs_delta": top_abs,
                "top_sensors_z_scale": top_zsc,
                "top_sensors_z_local": top_zloc,
                "verdict": verdict,
                "note_controls": (
                    "Controls are operating-condition matched non-onset-neighborhood "
                    "hours; they are not treated as confirmed leak-free."
                ),
            }
        )

    # Timing nulls — full recount with histogram (DIAG Method M frozen)
    print("Recomputing DIAG timing-null distribution for reporting …", flush=True)
    diag_events = [ev for ev in ABRUPT_EVENTS if ev.period == "DIAG"]
    # eligible_events filter via evaluate path — use all DIAG abrupt with warm-up
    start, end = period_bounds("DIAG")
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    s_diag = score_m.loc[(score_m.index >= start) & (score_m.index <= end)]
    from dual_model.detection_eval import eligible_events

    elig = eligible_events("DIAG", s_diag.index)
    rng = np.random.default_rng(2018 + 13)  # same seed family as Method M DIAG run
    null_stats = timing_nulls(
        scores=s_diag,
        events=elig,
        tau=TAU_M,
        period="DIAG",
        rng=rng,
        n_nulls=200,
    )
    # Expand: recount with same seed to get histogram
    rng2 = np.random.default_rng(2018 + 13)
    index = s_diag.index
    eligible_hours = index[(index >= warm) & (index <= end)]
    true_onsets = [pd.Timestamp(ev.onset) for ev in elig]
    hod = [t.hour for t in true_onsets]
    pools = {h: eligible_hours[eligible_hours.hour == h] for h in range(24)}
    eps = episodes_from_scores(s_diag.to_numpy(), tau=TAU_M)
    notify_times = [index[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(index)]

    def recall_for(onsets):
        hits = 0
        for onset in onsets:
            ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
            if any(onset <= t <= ce for t in notify_times):
                hits += 1
        return hits / len(onsets)

    null_recalls = []
    n_onset_draws = 0
    for _ in range(200):
        sampled = []
        for h in hod:
            pool = pools.get(int(h), eligible_hours)
            if len(pool) == 0:
                pool = eligible_hours
            sampled.append(pd.Timestamp(rng2.choice(pool)))
            n_onset_draws += 1
        null_recalls.append(recall_for(sampled))
    arr = np.asarray(null_recalls, dtype=float)
    true_recall = recall_for(true_onsets)
    # counts of null recall values
    # possible recalls: 0, 1/3, 2/3, 1
    cnt = Counter(np.round(arr, 6))
    n_null_ge_true = int((arr >= true_recall).sum())
    n_null_le_true = int((arr <= true_recall).sum())
    timing_report = {
        "assignment_rules": {
            "description": (
                "Density-matched timing nulls: for each of N null replicates, sample "
                "|E| candidate onsets uniformly from DIAG eligible hours that match "
                "the empirical hour-of-day of the true abrupt onsets (one draw per "
                "true event HOD). Episodes/notifies are fixed from the score series "
                "at frozen τ; a null onset is a hit if any notify falls in "
                "[onset, onset+6h]. True percentile = fraction of null recalls ≤ true recall."
            ),
            "eligible_hours": "DIAG index hours with t >= DIAG_START + WARMUP_HOURS (25h)",
            "matching": "hour-of-day of each true abrupt onset",
            "hit_rule": "any Method M notify in credit window [t0, t0+6h]",
            "percentile_definition": "mean(I(null_recall <= true_recall))",
            "rng_seed": 2018 + 13,
        },
        "n_null_replicates": 200,
        "n_true_events_E": len(true_onsets),
        "n_onset_timestamp_draws_total": n_onset_draws,
        "n_fixed_notifies_in_DIAG": len(notify_times),
        "true_recall": true_recall,
        "null_recall_mean": float(arr.mean()),
        "null_recall_std": float(arr.std(ddof=0)),
        "true_percentile_vs_null": float((arr <= true_recall).mean()),
        "null_recall_value_counts": {str(k): int(v) for k, v in sorted(cnt.items())},
        "n_nulls_with_recall_ge_true": n_null_ge_true,
        "n_nulls_with_recall_le_true": n_null_le_true,
        "from_stored_method_m_json": meta["diag"]["timing_nulls"],
        "recomputed_matches_stored": abs(true_recall - meta["diag"]["timing_nulls"]["true_recall"]) < 1e-9
        and abs(float(arr.mean()) - meta["diag"]["timing_nulls"]["null_recall_mean"]) < 1e-9,
    }

    # Recommendation: causal scale adaptation?
    # Evidence: systematic inflation of later-month σ vs SCALE, AND focus misses
    # classified as january_scale_obscures
    late = [r for r in month_summary if r["year_month"] >= "2018-07"]
    med_late = float(np.mean([r["ratio_median"] for r in late])) if late else float("nan")
    focus_verdicts = [f["verdict"] for f in focus_reports]
    obscures = sum(v == "january_scale_obscures_local_unusual" for v in focus_verdicts)
    weak = sum(v == "weak_vs_contemporaneous_ordinary" for v in focus_verdicts)

    recommend_adaptation = False
    recommendation = None
    recommendation_note = ""
    if obscures >= 1 and med_late > 1.25:
        recommend_adaptation = True
        recommendation = (
            "Consider causal recent-window scale adaptation for Method M σ_i "
            "(not enacted here)."
        )
        recommendation_note = (
            f"{obscures}/2 focus misses classified as January-scale obscuring; "
            f"median late-year σ_month/σ_SCALE≈{med_late:.2f}."
        )
    else:
        recommend_adaptation = False
        recommendation = None
        recommendation_note = (
            "Evidence does not cleanly support causal scale adaptation: "
            f"focus verdicts={focus_verdicts}; median Jul–Dec σ ratio≈{med_late:.2f}."
        )

    absorption_assessment = {
        "risk": (
            "Causal rolling/adapting σ_i estimated on a recent window that includes "
            "a slowly growing leak will inflate σ_i as |δ_i| grows, so |δ_i|/σ_i can "
            "remain ordinary even while the physical leak enlarges — adaptation can "
            "absorb growing leaks."
        ),
        "implication": (
            "Even if SCALE transfer is imperfect, recommending adaptation requires "
            "that obscuring from stale January scales dominate, and that absorption "
            "risk is accepted or mitigated (e.g. floor σ, exclude high-|δ| hours from "
            "scale updates, or dual timescales). This audit does not implement adaptation."
        ),
        "supported_here": recommend_adaptation,
    }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "acknowledgement": (
            "Diagnostic audit only; no Method M refit, τ change, or dual rebuild. "
            "Non-onset neighborhoods are not treated as leak-free."
        ),
        "frozen_calibration_sha256": digest,
        "method_m_tau": TAU_M,
        "scale_period": [str(SCALE_START), str(SCALE_END)],
        "month_scale_transfer_summary": month_summary,
        "focus_events": focus_reports,
        "timing_nulls_diag_detail": timing_report,
        "recommendation_causal_scale_adaptation": recommendation,
        "recommend_adaptation": recommend_adaptation,
        "recommendation_note": recommendation_note,
        "growing_leak_absorption_assessment": absorption_assessment,
    }
    (AUDIT / "scale_transfer_audit.json").write_text(json.dumps(payload, indent=2) + "\n")

    # Markdown
    lines = [
        "# Method M scale-transfer audit",
        "",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "No fitting, threshold changes, or Method M reruns. Preserves prior results.",
        "",
        payload["acknowledgement"],
        "",
        f"January SCALE: `{SCALE_START}` → `{SCALE_END}`. "
        "Monthly σ = std of causal δ_i on hours **outside** ±72 h of registered abrupt "
        "onsets (operating sample — **not** labeled leak-free).",
        "",
        "## Per-month scale transfer (median over sensors of σ_month/σ_SCALE)",
        "",
        "| Month | n sens | ratio median | p10 | p90 | frac>1.5 | frac<2/3 |",
        "|-------|-------:|-------------:|----:|----:|---------:|---------:|",
    ]
    for r in month_summary:
        lines.append(
            f"| {r['year_month']} | {r['n_sensors']} | {r['ratio_median']:.3f} | "
            f"{r['ratio_p10']:.3f} | {r['ratio_p90']:.3f} | "
            f"{r['frac_ratio_gt_1_5']:.2f} | {r['frac_ratio_lt_0_67']:.2f} |"
        )

    lines.extend(
        [
            "",
            "Numerator vs normalization: ratios >1 mean later ordinary |δ| dispersion "
            "exceeds January SCALE σ (January scales are **tight** relative to later months). "
            "Ratios <1 mean January scales are **loose** later.",
            "",
            "## Focus misses p183 & p369",
            "",
            "Contrasts: credit-window network max |δ|, max |δ|/σ_SCALE, max |δ|/σ_month "
            "vs operating-matched controls (HOD + PRE Q_ext/PUMP_1).",
            "",
        ]
    )
    for f in focus_reports:
        s = f["snr_vs_operating_matched_controls"]
        e = f["event_window"]
        lines.append(f"### {f['pipe']} ({f['onset']})")
        lines.append("")
        lines.append(f"- **Verdict:** `{f['verdict']}`")
        lines.append(
            f"- Credit max s_M={f['credit_max_score_M']:.3f} (τ={TAU_M}); "
            f"n_ctrl={f['n_controls']}."
        )
        lines.append(
            f"- Event max|δ|={e['network_max_abs_delta']:.3f} ({e['argmax_abs_delta_sensor']}); "
            f"max z_SCALE={e['network_max_z_scale']:.3f} ({e['argmax_z_scale_sensor']}); "
            f"max z_month={e['network_max_z_local']:.3f} ({e['argmax_z_local_sensor']})."
        )
        lines.append(
            f"- SNR vs controls — |δ|: {s['max_abs_delta']:.2f}; "
            f"z_SCALE: {s['max_z_scale']:.2f}; z_month: {s['max_z_local_month']:.2f}; "
            f"s_M: {s['credit_s_M']:.2f}."
        )
        lines.append(
            f"- Ctrl means — |δ|={f['ctrl_means']['max_abs_delta']:.3f}, "
            f"z_SCALE={f['ctrl_means']['max_z_scale']:.3f}, "
            f"z_month={f['ctrl_means']['max_z_local']:.3f}."
        )
        lines.append(f"- Top |δ| sensors: {f['top_sensors_max_abs_delta']}")
        lines.append(f"- Top z_SCALE sensors: {f['top_sensors_z_scale']}")
        lines.append(f"- Top z_month sensors: {f['top_sensors_z_local']}")
        lines.append("")

    tr = timing_report
    lines.extend(
        [
            "## DIAG timing nulls (actual counts — not only percentile)",
            "",
            f"- **N null replicates:** {tr['n_null_replicates']}",
            f"- **|E| true DIAG abrupt events:** {tr['n_true_events_E']}",
            f"- **Total onset timestamp draws:** {tr['n_onset_timestamp_draws_total']} "
            f"(= N × |E| = {tr['n_null_replicates']} × {tr['n_true_events_E']})",
            f"- **Fixed DIAG notifies at τ={TAU_M}:** {tr['n_fixed_notifies_in_DIAG']}",
            f"- **True recall:** {tr['true_recall']}",
            f"- **Null recall mean ± std:** {tr['null_recall_mean']:.4f} ± {tr['null_recall_std']:.4f}",
            f"- **Percentile definition:** fraction of nulls with recall ≤ true "
            f"= {tr['true_percentile_vs_null']} "
            f"({tr['n_nulls_with_recall_le_true']}/{tr['n_null_replicates']} nulls)",
            f"- **Nulls with recall ≥ true:** {tr['n_nulls_with_recall_ge_true']}/{tr['n_null_replicates']}",
            f"- **Null recall value counts:** `{tr['null_recall_value_counts']}`",
            "",
            "### Assignment rules",
            "",
            tr["assignment_rules"]["description"],
            "",
            f"- Eligible hours: {tr['assignment_rules']['eligible_hours']}",
            f"- Matching: {tr['assignment_rules']['matching']}",
            f"- Hit rule: {tr['assignment_rules']['hit_rule']}",
            f"- RNG seed: {tr['assignment_rules']['rng_seed']}",
            "",
            "## Recommendation",
            "",
        ]
    )
    if recommend_adaptation:
        lines.append(f"**Causal scale adaptation:** {recommendation}")
        lines.append("")
        lines.append(recommendation_note)
    else:
        lines.append("**Do not recommend causal scale adaptation** on this evidence.")
        lines.append("")
        lines.append(recommendation_note)

    lines.extend(
        [
            "",
            "### Growing-leak absorption",
            "",
            absorption_assessment["risk"],
            "",
            absorption_assessment["implication"],
            "",
            "## Notes",
            "",
            "- Full sensor set; no leak-based sensor selection.",
            "- Per-sensor month ratios: `per_sensor_month_scale_ratios.csv`.",
            "- No 2019 / UI / Tiger / deployment / Method M parameter changes.",
            "",
        ]
    )
    (AUDIT / "SCALE_TRANSFER_AUDIT.md").write_text("\n".join(lines) + "\n")
    (OUT / "METHOD_M_SCALE_TRANSFER_AUDIT.md").write_text(
        "See [`method_m_scale_transfer/SCALE_TRANSFER_AUDIT.md`]"
        "(method_m_scale_transfer/SCALE_TRANSFER_AUDIT.md).\n"
    )
    print("Wrote", AUDIT / "SCALE_TRANSFER_AUDIT.md", flush=True)
    print("recommend_adaptation=", recommend_adaptation, "focus=", focus_verdicts, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
