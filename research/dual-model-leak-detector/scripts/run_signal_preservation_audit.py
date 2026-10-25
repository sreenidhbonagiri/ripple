#!/usr/bin/env python3
"""Event-level signal-preservation audit (no fitting/tuning).

Protocol: outputs/detection_2018_measured_pump1/SIGNAL_PRESERVATION_PROTOCOL.md
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.area_topology import build_roughness_clusters, load_pressure_sensors  # noqa: E402
from dual_model.detection_protocol import ABRUPT_EVENTS, REQUIRED_FROZEN_SHA256  # noqa: E402
from dual_model.dual_series import load_frozen, verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import (  # noqa: E402
    load_nominal_wn,
    run_primal_window,
    subsample_hourly,
)
from dual_model.scada_io import (  # noqa: E402
    load_amr_demands_2018,
    load_flows_2018,
    load_levels_2018,
    load_pressures_2018,
)

OUT = ROOT / "outputs" / "detection_2018_measured_pump1" / "signal_preservation"
SCORE_DIR = ROOT / "outputs" / "detection_2018_measured_pump1"
FROZEN_TAU_A = 1.791
PRE_H = 6
POST_H = 6
EPS = 1e-6
N_CTRL = 25
EXCLUDE_H = 72


def _window_slices(idx: pd.DatetimeIndex, t0: pd.Timestamp):
    pre = idx[(idx >= t0 - pd.Timedelta(hours=PRE_H)) & (idx < t0)]
    post = idx[(idx >= t0) & (idx <= t0 + pd.Timedelta(hours=POST_H))]
    return pre, post


def _delta_mean(series: pd.Series, pre: pd.DatetimeIndex, post: pd.DatetimeIndex) -> float:
    a = series.reindex(pre).astype(float)
    b = series.reindex(post).astype(float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    return float(b.mean() - a.mean())


def _delta_vector(df: pd.DataFrame, pre: pd.DatetimeIndex, post: pd.DatetimeIndex) -> pd.Series:
    cols = list(df.columns)
    out = {}
    for c in cols:
        out[c] = _delta_mean(df[c], pre, post)
    return pd.Series(out, dtype=float)


def _net_summaries(delta: pd.Series) -> dict:
    v = delta.astype(float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"mean_signed": None, "mean_abs": None, "l2": None, "n": 0}
    return {
        "mean_signed": float(v.mean()),
        "mean_abs": float(v.abs().mean()),
        "l2": float(np.linalg.norm(v.values)),
        "n": int(len(v)),
    }


def _snr(event_val: float, ctrl_vals: list[float]) -> float:
    arr = np.asarray([c for c in ctrl_vals if np.isfinite(c)], dtype=float)
    if not np.isfinite(event_val) or len(arr) < 3:
        return float("nan")
    return float((event_val - arr.mean()) / max(arr.std(ddof=0), EPS))


def build_primal_pressures(
    *,
    use_frozen: bool,
    scratch: Path,
    index: pd.DatetimeIndex,
    levels: pd.Series,
    amr: pd.DataFrame,
) -> pd.DataFrame:
    """Chunked hourly primal pressures for the audit index."""
    wn = load_nominal_wn()
    dm, roughness, _tcv = (None, None, None)
    clusters = None
    if use_frozen:
        frozen_path = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
        dm, roughness, _tcv = load_frozen(frozen_path)
        clusters = build_roughness_clusters(wn)

    chunks = []
    # Cover index span in 7-day chunks
    start, end = index.min(), index.max()
    cur = start
    while cur <= end:
        chunk_end = min(cur + pd.Timedelta(days=7) - pd.Timedelta(hours=1), end)
        ts = index[(index >= cur) & (index <= chunk_end)]
        if len(ts) < 2:
            cur = chunk_end + pd.Timedelta(hours=1)
            continue
        Lv = levels.reindex(ts)
        Ah = amr.reindex(ts) if use_frozen else None
        # drop NaN level rows
        ok = Lv.notna()
        if use_frozen:
            ok = ok & Ah.notna().all(axis=1)
        ts = ts[ok.values]
        if len(ts) < 2:
            cur = chunk_end + pd.Timedelta(hours=1)
            continue
        res = run_primal_window(
            wn,
            ts,
            demand_model=dm,
            amr_lh=Ah if use_frozen else None,
            levels_m=levels.reindex(ts),
            scratch=scratch,
            roughness=roughness if use_frozen else None,
            clusters=clusters,
            timestep_sec=3600,
        )
        if res.converged:
            chunks.append(res.pressure_m)
        else:
            print(f"  primal fail {cur}: {res.notes}", flush=True)
        cur = chunk_end + pd.Timedelta(hours=1)

    if not chunks:
        return pd.DataFrame(index=index)
    P = pd.concat(chunks).sort_index()
    return P[~P.index.duplicated(keep="first")]


def select_controls(
    t0: pd.Timestamp,
    *,
    index: pd.DatetimeIndex,
    q_ext: pd.Series,
    pump: pd.Series,
    abrupt_onsets: list[pd.Timestamp],
) -> list[pd.Timestamp]:
    pre0, _ = _window_slices(index, t0)
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
            continue  # skip same week as event
        if any(abs((t - o).total_seconds()) <= EXCLUDE_H * 3600 for o in abrupt_onsets):
            continue
        pre, post = _window_slices(index, t)
        if len(pre) < 3 or len(post) < 3:
            continue
        dq = abs(float(q_ext.reindex(pre).mean()) - q0)
        dp = abs(float(pump.reindex(pre).mean()) - p0)
        cands.append((dq + dp, dq, dp, t))

    if not cands:
        return []
    dists = np.asarray([c[0] for c in cands], dtype=float)
    thr = float(np.quantile(dists, 0.80))
    filtered = [c for c in cands if c[0] <= thr] or cands
    filtered.sort(key=lambda x: x[0])
    return [c[3] for c in filtered[:N_CTRL]]


def contrasts_at(
    t0: pd.Timestamp,
    *,
    index: pd.DatetimeIndex,
    P_meas: pd.DataFrame,
    q_ext: pd.Series,
    err_cal: pd.DataFrame,
    err_nom: pd.DataFrame,
    qv: pd.DataFrame,
    score_a: pd.Series,
) -> dict:
    pre, post = _window_slices(index, t0)
    dP = _delta_vector(P_meas, pre, post)
    dEcal = _delta_vector(err_cal, pre, post)
    dEnom = _delta_vector(err_nom, pre, post)
    dQv = _delta_vector(qv, pre, post)
    dQext = _delta_mean(q_ext, pre, post)
    dSa = _delta_mean(score_a, pre, post)
    credit = score_a.reindex(post)
    credit = credit[np.isfinite(credit)]
    return {
        "n_pre": int(len(pre)),
        "n_post": int(len(post)),
        "delta_P": dP.to_dict(),
        "delta_P_net": _net_summaries(dP),
        "delta_Qext": dQext,
        "delta_err_cal": dEcal.to_dict(),
        "delta_err_cal_net": _net_summaries(dEcal),
        "delta_err_nom": dEnom.to_dict(),
        "delta_err_nom_net": _net_summaries(dEnom),
        "delta_qv": dQv.to_dict(),
        "delta_qv_net": _net_summaries(dQv),
        "delta_sum_qv": float(dQv.sum()) if dQv.notna().any() else float("nan"),
        "delta_score_A": dSa,
        "credit_max_score_A": float(credit.max()) if len(credit) else float("nan"),
    }


def classify_miss(snr: dict) -> str:
    """Earliest dual-path loss stage (measurements → hydraulics → Σq_v → score)."""
    snr_p = abs(snr.get("P_l2", float("nan")))
    snr_q = abs(snr.get("Qext", float("nan")))
    snr_ecal = abs(snr.get("err_cal_l2", float("nan")))
    snr_sum = abs(snr.get("sum_qv", float("nan")))
    snr_qv_l2 = abs(snr.get("qv_l2", float("nan")))
    snr_sa = abs(snr.get("score_A", float("nan")))
    snr_cred = abs(snr.get("credit_max_A", float("nan")))
    max_sensor_qv = max(
        (abs(v) for k, v in snr.items() if k.startswith("qv_") and k != "qv_l2"),
        default=float("nan"),
    )

    def ge(x: float, t: float) -> bool:
        return np.isfinite(x) and x >= t

    def lt(x: float, t: float) -> bool:
        return np.isfinite(x) and x < t

    meas_strong = ge(snr_p, 1.5) or ge(snr_q, 1.5)
    meas_weak = (not ge(snr_p, 1.5)) and (not ge(snr_q, 1.5))
    qv_strong = ge(snr_sum, 1.5) or ge(snr_qv_l2, 1.5)
    score_strong = ge(snr_sa, 1.5) or ge(snr_cred, 1.5)
    sensor_strong = ge(max_sensor_qv, 2.0) or ge(snr_qv_l2, 2.0)

    # 1) Already weak in measurements (and dual does not independently light up)
    if meas_weak and not qv_strong:
        return "weak_in_measurements"
    # 2) Measurement contrast absorbed: pred-error and dual q_v both ordinary
    if meas_strong and lt(snr_ecal, 1.0) and not qv_strong:
        return "explained_by_hydraulics"
    # 3) Per-sensor / vector q_v contrast canceled in the signed sum
    if sensor_strong and lt(snr_sum, 1.0):
        return "canceled_by_signed_sum"
    # 4) Σq_v contrast present but Method A temporal score does not elevate
    if qv_strong and not score_strong:
        return "suppressed_by_temporal_score"
    # 5) Score elevated vs ordinary controls but still below frozen τ
    if score_strong:
        return "survives_to_score_below_tau"
    if meas_weak:
        return "weak_in_measurements"
    return "unclear"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    digest = verify_frozen_hash(ROOT / "outputs" / "calibration" / "frozen_calibration.json")
    assert digest == REQUIRED_FROZEN_SHA256

    sensors = list(load_pressure_sensors())
    print("Loading SCADA + dual scores …", flush=True)
    P_meas = subsample_hourly(load_pressures_2018())[sensors]
    F = subsample_hourly(load_flows_2018())
    L = subsample_hourly(load_levels_2018())["T1"]
    A = subsample_hourly(load_amr_demands_2018())
    q_ext = F["p227"].astype(float) + F["p235"].astype(float)
    pump = F["PUMP_1"].astype(float)

    qv = pd.read_csv(SCORE_DIR / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    qv = qv[[c for c in sensors if c in qv.columns]]
    score_a = pd.read_csv(SCORE_DIR / "score_A.csv", index_col=0, parse_dates=True).iloc[:, 0]

    # Common hourly index covering events
    idx = P_meas.index.intersection(F.index).intersection(L.index).intersection(qv.index).intersection(score_a.index)
    P_meas, q_ext, pump, L, A = P_meas.loc[idx], q_ext.loc[idx], pump.loc[idx], L.loc[idx], A.loc[idx]
    qv, score_a = qv.loc[idx], score_a.loc[idx]

    scratch_cal = OUT / "_scratch_primal_cal"
    scratch_nom = OUT / "_scratch_primal_nom"
    cache_cal = OUT / "primal_P_calibrated.csv"
    cache_nom = OUT / "primal_P_nominal.csv"
    if cache_cal.exists() and cache_nom.exists():
        print("Loading cached primal pressures …", flush=True)
        P_cal = pd.read_csv(cache_cal, index_col=0, parse_dates=True)
        P_nom = pd.read_csv(cache_nom, index_col=0, parse_dates=True)
    else:
        print("Building frozen-calibrated primal pressures …", flush=True)
        P_cal = build_primal_pressures(
            use_frozen=True, scratch=scratch_cal, index=idx, levels=L, amr=A
        )
        print("Building INP-nominal primal pressures …", flush=True)
        P_nom = build_primal_pressures(
            use_frozen=False, scratch=scratch_nom, index=idx, levels=L, amr=A
        )
        P_cal.to_csv(cache_cal)
        P_nom.to_csv(cache_nom)
    # Align
    common = idx.intersection(P_cal.index).intersection(P_nom.index)
    P_meas = P_meas.loc[common]
    P_cal = P_cal.loc[common, sensors]
    P_nom = P_nom.loc[common, sensors]
    q_ext, pump = q_ext.loc[common], pump.loc[common]
    qv, score_a = qv.loc[common], score_a.loc[common]
    err_cal = P_meas - P_cal
    err_nom = P_meas - P_nom
    index = common

    onsets = [pd.Timestamp(ev.onset) for ev in ABRUPT_EVENTS]
    event_rows = []
    per_sensor_rows = []

    for ev in ABRUPT_EVENTS:
        t0 = pd.Timestamp(ev.onset)
        print(f"Event {ev.pipe} {t0} …", flush=True)
        ctrls = select_controls(
            t0, index=index, q_ext=q_ext, pump=pump, abrupt_onsets=onsets
        )
        ev_c = contrasts_at(
            t0,
            index=index,
            P_meas=P_meas,
            q_ext=q_ext,
            err_cal=err_cal,
            err_nom=err_nom,
            qv=qv,
            score_a=score_a,
        )
        ctrl_cs = [
            contrasts_at(
                tc,
                index=index,
                P_meas=P_meas,
                q_ext=q_ext,
                err_cal=err_cal,
                err_nom=err_nom,
                qv=qv,
                score_a=score_a,
            )
            for tc in ctrls
        ]

        def gather(key_net: str, field: str) -> list[float]:
            out = []
            for c in ctrl_cs:
                v = c[key_net].get(field) if isinstance(c[key_net], dict) else None
                if v is not None and np.isfinite(v):
                    out.append(float(v))
            return out

        snr = {
            "P_l2": _snr(ev_c["delta_P_net"]["l2"], gather("delta_P_net", "l2")),
            "P_mean_abs": _snr(ev_c["delta_P_net"]["mean_abs"], gather("delta_P_net", "mean_abs")),
            "Qext": _snr(ev_c["delta_Qext"], [c["delta_Qext"] for c in ctrl_cs]),
            "err_cal_l2": _snr(ev_c["delta_err_cal_net"]["l2"], gather("delta_err_cal_net", "l2")),
            "err_nom_l2": _snr(ev_c["delta_err_nom_net"]["l2"], gather("delta_err_nom_net", "l2")),
            "qv_l2": _snr(ev_c["delta_qv_net"]["l2"], gather("delta_qv_net", "l2")),
            "sum_qv": _snr(ev_c["delta_sum_qv"], [c["delta_sum_qv"] for c in ctrl_cs]),
            "score_A": _snr(ev_c["delta_score_A"], [c["delta_score_A"] for c in ctrl_cs]),
            "credit_max_A": _snr(
                ev_c["credit_max_score_A"], [c["credit_max_score_A"] for c in ctrl_cs]
            ),
        }
        # per-sensor SNR for P and q_v
        for s in sensors:
            snr[f"P_{s}"] = _snr(
                float(ev_c["delta_P"].get(s, float("nan"))),
                [float(c["delta_P"].get(s, float("nan"))) for c in ctrl_cs],
            )
            snr[f"qv_{s}"] = _snr(
                float(ev_c["delta_qv"].get(s, float("nan"))),
                [float(c["delta_qv"].get(s, float("nan"))) for c in ctrl_cs],
            )
            per_sensor_rows.append(
                {
                    "pipe": ev.pipe,
                    "onset": str(t0),
                    "sensor": s,
                    "delta_P": ev_c["delta_P"].get(s),
                    "snr_P": snr[f"P_{s}"],
                    "delta_err_cal": ev_c["delta_err_cal"].get(s),
                    "delta_qv": ev_c["delta_qv"].get(s),
                    "snr_qv": snr[f"qv_{s}"],
                }
            )

        missed = bool(
            np.isfinite(ev_c["credit_max_score_A"]) and ev_c["credit_max_score_A"] < FROZEN_TAU_A
        )
        loss_stage = classify_miss(snr) if missed else "detected_above_tau"
        # For detected events still report stage as N/A for miss taxonomy
        if not missed:
            loss_stage = "not_missed_credit_max_ge_tau"

        row = {
            "pipe": ev.pipe,
            "onset": str(t0),
            "period": ev.period,
            "n_controls": len(ctrls),
            "missed_vs_tau_A": missed,
            "loss_stage": loss_stage,
            "credit_max_score_A": ev_c["credit_max_score_A"],
            "frozen_tau_A": FROZEN_TAU_A,
            "delta_P_l2": ev_c["delta_P_net"]["l2"],
            "delta_P_mean_abs": ev_c["delta_P_net"]["mean_abs"],
            "delta_Qext": ev_c["delta_Qext"],
            "delta_err_cal_l2": ev_c["delta_err_cal_net"]["l2"],
            "delta_err_nom_l2": ev_c["delta_err_nom_net"]["l2"],
            "delta_qv_l2": ev_c["delta_qv_net"]["l2"],
            "delta_sum_qv": ev_c["delta_sum_qv"],
            "delta_score_A": ev_c["delta_score_A"],
            "snr": snr,
            "ctrl_mean_P_l2": float(np.nanmean(gather("delta_P_net", "l2"))) if gather("delta_P_net", "l2") else None,
            "ctrl_std_P_l2": float(np.nanstd(gather("delta_P_net", "l2"))) if gather("delta_P_net", "l2") else None,
            "ctrl_mean_sum_qv": float(np.nanmean([c["delta_sum_qv"] for c in ctrl_cs])) if ctrl_cs else None,
            "ctrl_std_sum_qv": float(np.nanstd([c["delta_sum_qv"] for c in ctrl_cs])) if ctrl_cs else None,
        }
        event_rows.append(row)
        print(
            f"  missed={missed} stage={loss_stage} "
            f"SNR P_l2={snr['P_l2']:.2f} Qext={snr['Qext']:.2f} "
            f"err_cal={snr['err_cal_l2']:.2f} sum_qv={snr['sum_qv']:.2f} "
            f"sA={snr['score_A']:.2f} cred={snr['credit_max_A']:.2f}",
            flush=True,
        )

    # Recommendation
    miss_stages = [r["loss_stage"] for r in event_rows if r["missed_vs_tau_A"]]
    from collections import Counter

    counts = Counter(miss_stages)
    recommendation = None
    recommendation_note = (
        "No supported correction emerged: misses do not share a single demonstrated "
        "signal-loss stage that a bounded intervention would fix."
    )
    # Only recommend if a specific actionable stage dominates (≥ half of misses) with clear mechanism
    if miss_stages:
        top, ntop = counts.most_common(1)[0]
        if ntop >= max(2, (len(miss_stages) + 1) // 2) and top == "canceled_by_signed_sum":
            recommendation = (
                "Replace Method A signed Σq_v with a non-canceling aggregation "
                "(e.g. vector L2 change already studied as B) only after addressing B occupancy — "
                "not enacted here."
            )
            recommendation_note = (
                f"{ntop}/{len(miss_stages)} misses show signed-sum cancellation; "
                "aggregation—not measurement absence—removes distinguishability."
            )
        elif ntop >= max(2, (len(miss_stages) + 1) // 2) and top == "suppressed_by_temporal_score":
            recommendation = (
                "Revise causal reference / normalization for Method A so ordinary "
                "ref-window σ does not suppress event ΔΣq_v — not enacted here."
            )
            recommendation_note = (
                f"{ntop}/{len(miss_stages)} misses retain Σq_v contrast but lose it in s_A."
            )
        elif ntop >= max(2, (len(miss_stages) + 1) // 2) and top == "explained_by_hydraulics":
            recommendation = (
                "Revisit hydraulic boundary/demand specification: measurement contrasts "
                "are absorbed into the calibrated primal so dual residuals stay ordinary."
            )
            recommendation_note = f"{ntop}/{len(miss_stages)} misses explained by hydraulics."
        elif ntop >= max(2, (len(miss_stages) + 1) // 2) and top == "weak_in_measurements":
            recommendation = None
            recommendation_note = (
                f"{ntop}/{len(miss_stages)} misses are already weak in measured pressure/inflow "
                "vs operating-matched controls — no dual/score correction is supported."
            )
        elif top == "survives_to_score_below_tau":
            recommendation = None
            recommendation_note = (
                "Score contrasts exceed ordinary variability but remain below the frozen τ; "
                "that is a threshold/separability limit, and this audit does not change thresholds."
            )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": "SIGNAL_PRESERVATION_PROTOCOL.md",
        "acknowledgement": (
            "2018 events have already been examined; all contrasts are diagnostic."
        ),
        "frozen_calibration_sha256": digest,
        "frozen_tau_A_diagnostic_miss_flag": FROZEN_TAU_A,
        "windows": {"pre_h": PRE_H, "post_h": POST_H},
        "n_sensors": len(sensors),
        "sensors": sensors,
        "events": event_rows,
        "miss_stage_counts": dict(counts),
        "recommendation": recommendation,
        "recommendation_note": recommendation_note,
    }
    (OUT / "signal_preservation_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    pd.DataFrame(per_sensor_rows).to_csv(OUT / "per_sensor_contrasts.csv", index=False)

    # Markdown
    lines = [
        "# Signal-preservation audit (diagnostic)",
        "",
        f"Protocol: [`SIGNAL_PRESERVATION_PROTOCOL.md`](../SIGNAL_PRESERVATION_PROTOCOL.md)  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        f"Frozen calibration: `{digest}`  ",
        "",
        payload["acknowledgement"],
        "",
        f"Windows: PRE=[{PRE_H}h before onset), POST=[onset, +{POST_H}h]. "
        f"Controls: hour-of-day + PRE Q_ext / PUMP_1 matched (n≤{N_CTRL}).",
        "",
        f"Miss flag (diagnostic only): Method A credit max < τ={FROZEN_TAU_A}.",
        "",
        "## Network-level contrasts vs ordinary controls (SNR)",
        "",
        "| Pipe | Period | Miss? | Loss stage | SNR ΔP L2 | SNR ΔQext | SNR Δerr_cal L2 | SNR Δerr_nom L2 | SNR ΔΣq_v | SNR Δs_A | SNR credit max | credit max |",
        "|------|--------|:-----:|------------|----------:|----------:|----------------:|----------------:|----------:|---------:|---------------:|-----------:|",
    ]
    for r in event_rows:
        s = r["snr"]
        lines.append(
            f"| {r['pipe']} | {r['period']} | {r['missed_vs_tau_A']} | `{r['loss_stage']}` | "
            f"{s['P_l2']:.2f} | {s['Qext']:.2f} | {s['err_cal_l2']:.2f} | {s['err_nom_l2']:.2f} | "
            f"{s['sum_qv']:.2f} | {s['score_A']:.2f} | {s['credit_max_A']:.2f} | "
            f"{r['credit_max_score_A']:.3f} |"
        )

    lines.extend(
        [
            "",
            "### Raw event Δ (not SNR)",
            "",
            "| Pipe | ΔP L2 (m) | ΔQext (m³/h) | Δerr_cal L2 (m) | ΔΣq_v (m³/h) | Δs_A |",
            "|------|----------:|-------------:|----------------:|-------------:|-----:|",
        ]
    )
    for r in event_rows:
        lines.append(
            f"| {r['pipe']} | {r['delta_P_l2']:.3f} | {r['delta_Qext']:.2f} | "
            f"{r['delta_err_cal_l2']:.3f} | {r['delta_sum_qv']:.2f} | {r['delta_score_A']:.3f} |"
        )

    lines.extend(["", "## Per-event loss notes", ""])
    for r in event_rows:
        s = r["snr"]
        # top sensors by |snr_qv|
        qv_snrs = [(k[3:], s[k]) for k in s if k.startswith("qv_") and k != "qv_l2" and np.isfinite(s[k])]
        qv_snrs.sort(key=lambda x: abs(x[1]), reverse=True)
        top = ", ".join(f"{nm}={val:.1f}" for nm, val in qv_snrs[:5])
        p_snrs = [(k[2:], s[k]) for k in s if k.startswith("P_") and k not in ("P_l2", "P_mean_abs") and np.isfinite(s[k])]
        p_snrs.sort(key=lambda x: abs(x[1]), reverse=True)
        top_p = ", ".join(f"{nm}={val:.1f}" for nm, val in p_snrs[:5])
        lines.append(f"### {r['pipe']} ({r['period']})")
        lines.append("")
        lines.append(f"- **Stage:** `{r['loss_stage']}` (miss={r['missed_vs_tau_A']}, n_ctrl={r['n_controls']})")
        lines.append(f"- Top |SNR ΔP| sensors: {top_p}")
        lines.append(f"- Top |SNR Δq_v| sensors: {top}")
        lines.append(
            f"- Measurement: SNR ΔP_L2={s['P_l2']:.2f}, ΔQext={s['Qext']:.2f}; "
            f"calibrated error SNR={s['err_cal_l2']:.2f}; "
            f"Σq_v SNR={s['sum_qv']:.2f}; s_A SNR={s['score_A']:.2f}."
        )
        lines.append("")

    lines.extend(
        [
            "## Miss-stage counts",
            "",
            "```",
            json.dumps(dict(counts), indent=2),
            "```",
            "",
            "## Recommendation",
            "",
        ]
    )
    if recommendation:
        lines.append(f"**One intervention (evidence-backed, not enacted):** {recommendation}")
        lines.append("")
        lines.append(recommendation_note)
    else:
        lines.append(f"**No supported correction emerged.** {recommendation_note}")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Sensors are the full pressure set; none chosen by leak pipe.",
            "- `err_cal` = meas − frozen-calibrated primal; `err_nom` = meas − INP-nominal primal.",
            "- No threshold changes, 2019, UI, Tiger, or deploy.",
            "",
        ]
    )
    (OUT / "SIGNAL_PRESERVATION_RESULTS.md").write_text("\n".join(lines) + "\n")
    # also copy short pointer next to other reports
    (SCORE_DIR / "SIGNAL_PRESERVATION_RESULTS.md").write_text(
        "See [`signal_preservation/SIGNAL_PRESERVATION_RESULTS.md`](signal_preservation/SIGNAL_PRESERVATION_RESULTS.md).\n"
    )
    print("Wrote", OUT / "SIGNAL_PRESERVATION_RESULTS.md", flush=True)
    print("recommendation:", recommendation, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
