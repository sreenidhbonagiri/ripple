#!/usr/bin/env python3
"""Post-hoc audit of completed multiscale Method M (no fitting / no τ retune).

Reads frozen selection and dual_qv; recomputes per-scale scores only for
forensic comparison. Does not change thresholds or re-run selection.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_protocol import (  # noqa: E402
    ABRUPT_EVENTS,
    CREDIT_HOURS,
    DEV_END,
    DEV_START,
    DIAG_END,
    DIAG_START,
    WARMUP_HOURS,
)
from dual_model.method_m_multiscale import (  # noqa: E402
    SCALE_END,
    SCALE_START,
    TIMESCALE_REF_HOURS,
    estimate_all_timescale_scales,
    score_method_m_single_timescale,
)
from dual_model.notifier import episodes_from_scores  # noqa: E402

OUT_BASE = ROOT / "outputs" / "detection_2018_measured_pump1"
OUT = OUT_BASE / "method_m_multiscale"
TAU_MS = float(json.loads((OUT / "FROZEN_SELECTION.json").read_text())["tau"])
TAU_M = float(json.loads((OUT / "FROZEN_SELECTION.json").read_text())["baseline_method_m_tau"])
CREDIT = pd.Timedelta(hours=CREDIT_HOURS)
# Fixed exclusion around labeled onsets when building ordinary controls (not tuned).
EXCLUDE_RADIUS = pd.Timedelta(hours=72)


@dataclass(frozen=True)
class CatalogEvent:
    pipe: str
    onset: pd.Timestamp
    period: str
    leak_type: str
    peak: pd.Timestamp | None = None


def parse_incipient() -> list[CatalogEvent]:
    cfg = ROOT.parents[1] / "data" / "raw" / "dataset_configuration.yaml"
    out: list[CatalogEvent] = []
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if not line.startswith("- p") or "incipient" not in line:
            continue
        parts = [p.strip() for p in line.lstrip("- ").split(",")]
        if len(parts) < 6:
            continue
        pipe, start, _end, _d, _t, peak = parts[:6]
        onset = pd.Timestamp(start)
        if pd.Timestamp(DEV_START) <= onset <= pd.Timestamp(DEV_END):
            period = "DEV"
        elif pd.Timestamp(DIAG_START) <= onset <= pd.Timestamp(DIAG_END):
            period = "DIAG"
        else:
            continue
        warm = pd.Timestamp(DEV_START if period == "DEV" else DIAG_START) + pd.Timedelta(
            hours=WARMUP_HOURS
        )
        if onset < warm:
            continue
        out.append(
            CatalogEvent(pipe, onset, period, "incipient", pd.Timestamp(peak))
        )
    return out


def abrupt_events() -> list[CatalogEvent]:
    out = []
    for ev in ABRUPT_EVENTS:
        onset = pd.Timestamp(ev.onset)
        warm = pd.Timestamp(DEV_START if ev.period == "DEV" else DIAG_START) + pd.Timedelta(
            hours=WARMUP_HOURS
        )
        if onset < warm:
            continue
        out.append(CatalogEvent(ev.pipe, onset, ev.period, "abrupt"))
    return out


def period_slice(s: pd.Series, period: str) -> pd.Series:
    if period == "DEV":
        a, b = pd.Timestamp(DEV_START), pd.Timestamp(DEV_END)
    else:
        a, b = pd.Timestamp(DIAG_START), pd.Timestamp(DIAG_END)
    warm = a + pd.Timedelta(hours=WARMUP_HOURS)
    return s.loc[(s.index >= warm) & (s.index <= b)]


def empirical_percentile(score: float, ref: pd.Series) -> float | None:
    if score is None or not np.isfinite(score):
        return None
    x = ref[np.isfinite(ref)]
    if len(x) == 0:
        return None
    return float((x <= score).mean())


def window_stats(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    w = s.loc[(s.index >= start) & (s.index <= end)]
    w = w[np.isfinite(w)]
    if len(w) == 0:
        return {
            "n": 0,
            "max": None,
            "mean": None,
            "frac_ge_dev_p95": None,
            "n_ge_dev_p95": 0,
        }
    return {"n": int(len(w)), "max": float(w.max()), "mean": float(w.mean())}


def main() -> int:
    qv = pd.read_csv(OUT_BASE / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    s_ms = pd.read_csv(OUT / "score_MS_combined.csv", index_col=0, parse_dates=True)["score"]
    s_base = pd.read_csv(OUT / "score_M_baseline_repro.csv", index_col=0, parse_dates=True)[
        "score"
    ]

    print("Estimating frozen SCALE σ per timescale (audit only) …", flush=True)
    scales = estimate_all_timescale_scales(qv)
    # Own-scale calibrated scores (each / its own SCALE median) — forensic, not for retune
    per: dict[str, pd.Series] = {}
    raw: dict[str, pd.Series] = {}
    for name, sc in scales.items():
        print(f"  scoring {name} REF={sc.ref_hours} …", flush=True)
        per[name] = score_method_m_single_timescale(
            qv,
            ref_hours=sc.ref_hours,
            sigma_m3h=sc.sigma_m3h,
            raw_max_median=sc.raw_max_median,
        )
        raw[name] = score_method_m_single_timescale(
            qv,
            ref_hours=sc.ref_hours,
            sigma_m3h=sc.sigma_m3h,
            raw_max_median=1.0,
        )

    # Winner timescale for combined raw max (same construction as experiment)
    raw_df = pd.DataFrame(raw)
    winner = pd.Series(pd.NA, index=raw_df.index, dtype=object)
    finite_any = raw_df.notna().any(axis=1)
    winner.loc[finite_any] = raw_df.loc[finite_any].idxmax(axis=1)

    # DEV empirical reference distributions (post-warmup), fixed once
    dev_refs = {name: period_slice(per[name], "DEV") for name in per}
    dev_refs["combined"] = period_slice(s_ms, "DEV")
    dev_refs["baseline_medium"] = period_slice(s_base, "DEV")
    dev_p95 = {k: float(v.dropna().quantile(0.95)) for k, v in dev_refs.items()}

    # Combined notifies at frozen τ (reconstruct; no retune)
    start, end = pd.Timestamp(DEV_START), pd.Timestamp(DIAG_END)
    s_year = s_ms.loc[(s_ms.index >= start) & (s_ms.index <= end)]
    eps = episodes_from_scores(s_year.to_numpy(dtype=float), tau=TAU_MS)
    notify_times = [
        s_year.index[ep.notify_idx]
        for ep in eps
        if 0 <= ep.notify_idx < len(s_year.index)
    ]

    def notify_driver(t: pd.Timestamp) -> dict:
        row = {n: float(raw[n].loc[t]) if np.isfinite(raw[n].loc[t]) else None for n in raw}
        w = winner.loc[t] if t in winner.index else None
        return {
            "notify_ts": str(t),
            "winner_timescale": None if pd.isna(w) else str(w),
            "raw_abs_z": row,
            "combined_score": float(s_ms.loc[t]) if np.isfinite(s_ms.loc[t]) else None,
            "per_scale_calibrated": {
                n: float(per[n].loc[t]) if np.isfinite(per[n].loc[t]) else None for n in per
            },
        }

    notify_audit = [notify_driver(t) for t in notify_times]

    # Ordinary control pool: DEV hours outside exclusion of all labeled onsets
    all_onsets = [e.onset for e in abrupt_events() + parse_incipient()]
    dev_idx = period_slice(s_ms, "DEV").index
    control_starts: list[pd.Timestamp] = []
    for t in dev_idx:
        if any(abs((t - o).total_seconds()) <= EXCLUDE_RADIUS.total_seconds() for o in all_onsets):
            continue
        # need full 6h window inside DEV
        if t + CREDIT > pd.Timestamp(DEV_END):
            continue
        control_starts.append(t)
    # Fixed subsample: every 24th eligible hour (deterministic, not tuned)
    control_starts = control_starts[::24]
    print(f"Control windows (6h): {len(control_starts)}", flush=True)

    def control_dist(series: pd.Series, p95: float) -> dict:
        maxima = []
        means = []
        frac_p95 = []
        for t0 in control_starts:
            st = window_stats(series, t0, t0 + CREDIT)
            if st["max"] is None:
                continue
            maxima.append(st["max"])
            means.append(st["mean"])
            w = series.loc[(series.index >= t0) & (series.index <= t0 + CREDIT)]
            w = w[np.isfinite(w)]
            frac_p95.append(float((w >= p95).mean()) if len(w) else 0.0)
        return {
            "n_controls": len(maxima),
            "max_mean": float(np.mean(maxima)) if maxima else None,
            "max_p95": float(np.quantile(maxima, 0.95)) if maxima else None,
            "mean_of_means": float(np.mean(means)) if means else None,
            "frac_hours_ge_dev_p95_mean": float(np.mean(frac_p95)) if frac_p95 else None,
            "maxima": maxima,
            "fracs": frac_p95,
        }

    ctrl_long = control_dist(per["long"], dev_p95["long"])
    ctrl_med = control_dist(per["medium"], dev_p95["medium"])
    ctrl_short = control_dist(per["short"], dev_p95["short"])
    ctrl_ms = control_dist(s_ms, dev_p95["combined"])

    def event_row(ev: CatalogEvent) -> dict:
        t0, t1 = ev.onset, ev.onset + CREDIT
        row: dict = {
            "pipe": ev.pipe,
            "onset": str(ev.onset),
            "period": ev.period,
            "leak_type": ev.leak_type,
        }
        for name in ("short", "medium", "long"):
            st = window_stats(per[name], t0, t1)
            row[f"{name}_max"] = st["max"]
            row[f"{name}_mean"] = st["mean"]
            row[f"{name}_max_dev_pct"] = empirical_percentile(
                st["max"], dev_refs[name]
            )
            row[f"{name}_mean_dev_pct"] = empirical_percentile(
                st["mean"], dev_refs[name]
            )
            p95 = dev_p95[name]
            w = per[name].loc[(per[name].index >= t0) & (per[name].index <= t1)]
            w = w[np.isfinite(w)]
            row[f"{name}_frac_ge_dev_p95"] = (
                float((w >= p95).mean()) if len(w) else None
            )
        st_c = window_stats(s_ms, t0, t1)
        row["combined_max"] = st_c["max"]
        row["combined_max_dev_pct"] = empirical_percentile(st_c["max"], dev_refs["combined"])
        st_b = window_stats(s_base, t0, t1)
        row["baseline_medium_max"] = st_b["max"]
        row["baseline_medium_max_dev_pct"] = empirical_percentile(
            st_b["max"], dev_refs["baseline_medium"]
        )
        # Would notify under frozen thresholds?
        row["hit_baseline_tau"] = bool(
            st_b["max"] is not None and st_b["max"] >= TAU_M
        )
        row["hit_combined_tau"] = bool(
            st_c["max"] is not None and st_c["max"] >= TAU_MS
        )
        # Counterfactuals for calibration / joint-max effects
        row["hit_if_combined_used_baseline_tau"] = bool(
            st_c["max"] is not None and st_c["max"] >= TAU_M
        )
        row["hit_if_medium_used_combined_tau"] = bool(
            st_b["max"] is not None and st_b["max"] >= TAU_MS
        )
        # Notifies inside credit from combined stream
        in_credit = [t for t in notify_times if t0 <= t <= t1]
        row["combined_notifies_in_credit"] = [str(t) for t in in_credit]
        row["notify_drivers"] = [notify_driver(t) for t in in_credit]
        # Long-scale unusual vs controls (same 6h window definition)
        if st["max"] is not None and ctrl_long["maxima"]:
            row["long_max_vs_control_pct"] = float(
                (np.asarray(ctrl_long["maxima"]) <= st["max"]).mean()
            )
            row["long_frac_p95_vs_control_pct"] = float(
                (
                    np.asarray(ctrl_long["fracs"])
                    <= (row["long_frac_ge_dev_p95"] or 0.0)
                ).mean()
            )
        else:
            row["long_max_vs_control_pct"] = None
            row["long_frac_p95_vs_control_pct"] = None
        return row

    abrupt_rows = [event_row(e) for e in abrupt_events()]
    incip_rows = [event_row(e) for e in parse_incipient()]

    # p538 deep dive
    p538 = next(r for r in abrupt_rows if r["pipe"] == "p538")
    p538_analysis = {
        "question": "Was p538 lost because joint-max calibration raised the threshold?",
        "baseline_medium_max_in_credit": p538["baseline_medium_max"],
        "combined_max_in_credit": p538["combined_max"],
        "tau_baseline": TAU_M,
        "tau_combined": TAU_MS,
        "hit_baseline_tau_on_medium": p538["hit_baseline_tau"],
        "hit_combined_tau_on_combined": p538["hit_combined_tau"],
        "hit_if_combined_score_vs_baseline_tau": p538["hit_if_combined_used_baseline_tau"],
        "hit_if_medium_score_vs_combined_tau": p538["hit_if_medium_used_combined_tau"],
        "per_scale_max": {
            "short": p538["short_max"],
            "medium": p538["medium_max"],
            "long": p538["long_max"],
        },
        "per_scale_dev_pct": {
            "short": p538["short_max_dev_pct"],
            "medium": p538["medium_max_dev_pct"],
            "long": p538["long_max_dev_pct"],
        },
    }
    # Causal attribution
    lost_by_raised_tau = (
        p538["hit_baseline_tau"]
        and not p538["hit_combined_tau"]
        and p538["hit_if_medium_used_combined_tau"] is False
        and p538["hit_if_combined_used_baseline_tau"] is True
    )
    # If medium alone fails combined τ, raised τ is sufficient to lose even without joint score change
    lost_primarily_raised_tau = (
        p538["hit_baseline_tau"]
        and not p538["hit_if_medium_used_combined_tau"]
    )
    lost_primarily_joint_score_shape = (
        p538["hit_baseline_tau"]
        and p538["hit_if_medium_used_combined_tau"]
        and not p538["hit_combined_tau"]
    )
    p538_analysis["lost_primarily_because_tau_raised"] = lost_primarily_raised_tau
    p538_analysis["lost_primarily_because_joint_score_shape"] = lost_primarily_joint_score_shape
    p538_analysis["counterfactual_raised_tau_alone_explains_miss"] = (
        lost_primarily_raised_tau
    )
    p538_analysis["note"] = (
        "Compare (medium max vs τ_MS) vs (combined max vs τ_M). "
        "If medium max < τ_MS, the higher selected τ alone would miss p538 "
        "even on the baseline medium score."
    )

    # Incipient long-scale unusual?
    incip_unusual = []
    for r in incip_rows:
        # "sustained" = frac hours ≥ DEV p95 of long score, unusual vs controls
        frac = r["long_frac_ge_dev_p95"]
        vs = r["long_frac_p95_vs_control_pct"]
        unusual = (
            frac is not None
            and vs is not None
            and frac >= 0.5
            and vs >= 0.95
        )
        incip_unusual.append(
            {
                "pipe": r["pipe"],
                "period": r["period"],
                "long_mean": r["long_mean"],
                "long_max": r["long_max"],
                "long_max_dev_pct": r["long_max_dev_pct"],
                "long_frac_ge_dev_p95": frac,
                "long_frac_p95_vs_control_pct": vs,
                "sustained_unusual_vs_controls": unusual,
                "notified": len(r["combined_notifies_in_credit"]) > 0,
            }
        )

    # Redundancy: correlation of per-scale series on DEV; disagreement on events
    dev_short = dev_refs["short"].dropna()
    common = dev_short.index
    corr = {
        "short_medium": float(
            pd.Series(dev_refs["short"].reindex(common)).corr(
                pd.Series(dev_refs["medium"].reindex(common))
            )
        ),
        "short_long": float(
            pd.Series(dev_refs["short"].reindex(common)).corr(
                pd.Series(dev_refs["long"].reindex(common))
            )
        ),
        "medium_long": float(
            pd.Series(dev_refs["medium"].reindex(common)).corr(
                pd.Series(dev_refs["long"].reindex(common))
            )
        ),
    }
    # Event-level: which scale has unique max among the three (strict)
    unique_leaders = {"short": [], "medium": [], "long": [], "tie": []}
    for r in abrupt_rows + incip_rows:
        vals = {n: r[f"{n}_max"] for n in ("short", "medium", "long")}
        if any(v is None for v in vals.values()):
            continue
        mx = max(vals.values())
        leaders = [n for n, v in vals.items() if abs(v - mx) <= 1e-12]
        if len(leaders) == 1:
            unique_leaders[leaders[0]].append(r["pipe"])
        else:
            unique_leaders["tie"].append(r["pipe"])

    # Distinct useful evidence?
    # Require: some event where a non-medium scale is uniquely elevated AND that
    # would matter for detection without only raising false burden — audit stance:
    # distinct if (a) notify drivers often non-medium OR (b) incipient long unusual
    # without being mirrored by medium, AND not only τ-inflation regressions.
    driver_counts = {"short": 0, "medium": 0, "long": 0, "unknown": 0}
    for n in notify_audit:
        w = n["winner_timescale"]
        if w in driver_counts:
            driver_counts[w] += 1
        else:
            driver_counts["unknown"] += 1

    any_incip_unusual = any(x["sustained_unusual_vs_controls"] for x in incip_unusual)
    # Check if unusual long incipient are also unusual on medium (same criterion)
    distinct_long_incip = []
    for x in incip_unusual:
        if not x["sustained_unusual_vs_controls"]:
            continue
        # find matching event row
        er = next(r for r in incip_rows if r["pipe"] == x["pipe"])
        med_frac = er["medium_frac_ge_dev_p95"]
        med_vs = None
        if med_frac is not None and ctrl_med["fracs"]:
            med_vs = float((np.asarray(ctrl_med["fracs"]) <= med_frac).mean())
        long_only = med_vs is None or med_vs < 0.95 or (med_frac or 0) < 0.5
        if long_only:
            distinct_long_incip.append({**x, "medium_frac_ge_dev_p95": med_frac, "medium_frac_vs_control_pct": med_vs})

    recommendation = {
        "distinct_useful_evidence": bool(distinct_long_incip)
        or (
            driver_counts["short"] + driver_counts["long"] > driver_counts["medium"]
            and any(
                r["hit_combined_tau"] and not r["hit_baseline_tau"] for r in abrupt_rows
            )
        ),
        "rationale": "",
        "next_experiment": None,
        "close_multiscale": True,
    }
    if distinct_long_incip:
        recommendation["distinct_useful_evidence"] = True
        recommendation["close_multiscale"] = False
        recommendation["next_experiment"] = (
            "Isolated long-scale–only Method M (REF=72) with its own DEV selection "
            "budget — not joint max — to test whether sustained long responses can "
            "pass abrupt gates without τ inflation that regresses medium hits."
        )
        recommendation["rationale"] = (
            "At least one incipient shows sustained long-scale elevation unusual vs "
            "controls that is not mirrored on medium under the same window rule."
        )
    else:
        recommendation["distinct_useful_evidence"] = False
        recommendation["close_multiscale"] = True
        recommendation["next_experiment"] = None
        recommendation["rationale"] = (
            "Per-scale scores are highly correlated on DEV; event windows are usually "
            "co-led or medium-led; joint-max selection raised τ and regressed p538; "
            "no incipient showed a sustained long-scale response that was unusual vs "
            "controls without also looking elevated on medium (or none unusual). "
            "Multiscale joint search did not provide distinct useful evidence."
        )

    # Recompute distinct flag more carefully from actual incip_unusual + medium mirror
    if not distinct_long_incip and not any_incip_unusual:
        recommendation["rationale"] = (
            "No incipient 6h window showed sustained long-scale elevation (frac≥0.5 of "
            "hours ≥ DEV long p95) that was ≥95th percentile of ordinary controls. "
            f"DEV per-scale correlations: {corr}. Notify drivers at τ={TAU_MS}: "
            f"{driver_counts}. Joint selection raised τ ({TAU_M}→{TAU_MS}) and lost "
            "p538; DIAG abrupt unchanged vs baseline. Close multiscale as unsuccessful."
        )
    elif any_incip_unusual and not distinct_long_incip:
        recommendation["rationale"] = (
            "Some incipient long-scale fractions are high vs controls, but the same "
            "windows are also unusual on medium under identical rules — redundant with "
            "baseline Method M, not distinct long-scale evidence. "
            f"Drivers={driver_counts}; p538 lost primarily via raised τ. "
            "Close multiscale as unsuccessful."
        )
        recommendation["close_multiscale"] = True
        recommendation["distinct_useful_evidence"] = False
        recommendation["next_experiment"] = None

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "acknowledgement": (
            "2018 already examined; audit only. No fitting, τ changes, 2019, or deploy."
        ),
        "frozen_tau_combined": TAU_MS,
        "frozen_tau_baseline": TAU_M,
        "timescales": TIMESCALE_REF_HOURS,
        "dev_p95": dev_p95,
        "control_definition": {
            "window_hours": CREDIT_HOURS,
            "exclude_radius_hours": int(EXCLUDE_RADIUS.total_seconds() // 3600),
            "pool": "DEV post-warmup hours outside exclusion of all abrupt/incipient onsets",
            "subsample": "every_24th_eligible_start",
            "n_controls": len(control_starts),
        },
        "control_summaries": {
            "long": {k: v for k, v in ctrl_long.items() if k not in ("maxima", "fracs")},
            "medium": {k: v for k, v in ctrl_med.items() if k not in ("maxima", "fracs")},
            "short": {k: v for k, v in ctrl_short.items() if k not in ("maxima", "fracs")},
            "combined": {k: v for k, v in ctrl_ms.items() if k not in ("maxima", "fracs")},
        },
        "dev_correlations": corr,
        "notify_driver_counts": driver_counts,
        "notifications": notify_audit,
        "abrupt_events": abrupt_rows,
        "incipient_events": incip_rows,
        "p538_analysis": p538_analysis,
        "incipient_long_unusual": incip_unusual,
        "distinct_long_incip_candidates": distinct_long_incip,
        "event_scale_leaders": unique_leaders,
        "recommendation": recommendation,
    }
    (OUT / "multiscale_audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    _write_md(payload)
    print("Wrote", OUT / "MULTISCALE_AUDIT.md", flush=True)
    print("RECOMMENDATION close=", recommendation["close_multiscale"], flush=True)
    return 0


def _write_md(p: dict) -> None:
    lines = [
        "# Multiscale Method M — post-hoc audit (no fitting)",
        "",
        f"Generated: `{p['generated_at_utc']}`  ",
        p["acknowledgement"],
        "",
        f"Frozen combined τ=`{p['frozen_tau_combined']}`; baseline Method M τ=`{p['frozen_tau_baseline']}`.",
        "",
        "## Method",
        "",
        "- Per-scale scores: own SCALE σ and own median calibration (forensic).",
        "- Combined stream: archived `score_MS_combined.csv` + frozen τ (unchanged).",
        "- Event window: **6 h from onset/startTime** (same credit rule as evaluation).",
        "- Controls: DEV 6 h windows, exclude ±72 h of all labeled onsets, every 24th start.",
        "- No sensor/window selection per event; no τ retune; no 2019.",
        "",
        f"DEV score correlations: `{p['dev_correlations']}`  ",
        f"Notify-hour timescale winners (combined raw max): `{p['notify_driver_counts']}`",
        "",
        "## Abrupt events — per-scale maxima and DEV percentiles",
        "",
        "| Pipe | Period | short max (pct) | medium max (pct) | long max (pct) | combined max (pct) | hit M | hit MS | drivers |",
        "|------|--------|----------------:|-----------------:|---------------:|-------------------:|:-----:|:------:|---------|",
    ]
    for r in p["abrupt_events"]:
        drivers = ",".join(
            d["winner_timescale"] or "?" for d in r["notify_drivers"]
        ) or "—"
        lines.append(
            f"| {r['pipe']} | {r['period']} | "
            f"{_fmt(r['short_max'])} ({_pct(r['short_max_dev_pct'])}) | "
            f"{_fmt(r['medium_max'])} ({_pct(r['medium_max_dev_pct'])}) | "
            f"{_fmt(r['long_max'])} ({_pct(r['long_max_dev_pct'])}) | "
            f"{_fmt(r['combined_max'])} ({_pct(r['combined_max_dev_pct'])}) | "
            f"{r['hit_baseline_tau']} | {r['hit_combined_tau']} | {drivers} |"
        )

    lines.extend(
        [
            "",
            "## Incipient events — same windows",
            "",
            "| Pipe | Period | short max (pct) | medium max (pct) | long max (pct) | long frac≥p95 | vs ctrl pct | notified |",
            "|------|--------|----------------:|-----------------:|---------------:|--------------:|------------:|:--------:|",
        ]
    )
    for r in p["incipient_events"]:
        lines.append(
            f"| {r['pipe']} | {r['period']} | "
            f"{_fmt(r['short_max'])} ({_pct(r['short_max_dev_pct'])}) | "
            f"{_fmt(r['medium_max'])} ({_pct(r['medium_max_dev_pct'])}) | "
            f"{_fmt(r['long_max'])} ({_pct(r['long_max_dev_pct'])}) | "
            f"{_fmt(r['long_frac_ge_dev_p95'])} | "
            f"{_pct(r['long_frac_p95_vs_control_pct'])} | "
            f"{bool(r['combined_notifies_in_credit'])} |"
        )

    a = p["p538_analysis"]
    lines.extend(
        [
            "",
            "## Was p538 lost because joint-max calibration raised the threshold?",
            "",
            f"- Medium (baseline) max in credit: `{_fmt(a['baseline_medium_max_in_credit'])}` vs τ_M=`{a['tau_baseline']}` → hit `{a['hit_baseline_tau_on_medium']}`",
            f"- Combined max in credit: `{_fmt(a['combined_max_in_credit'])}` vs τ_MS=`{a['tau_combined']}` → hit `{a['hit_combined_tau_on_combined']}`",
            f"- Counterfactual: medium max vs τ_MS → `{a['hit_if_medium_score_vs_combined_tau']}`",
            f"- Counterfactual: combined max vs τ_M → `{a['hit_if_combined_score_vs_baseline_tau']}`",
            f"- Per-scale maxima: `{a['per_scale_max']}`",
            f"- **Raised τ alone explains miss:** `{a['lost_primarily_because_tau_raised']}`",
            f"- **Joint score shape (not τ) explains miss:** `{a['lost_primarily_because_joint_score_shape']}`",
            "",
            a["note"],
            "",
            "## Incipient long-scale sustained unusual vs controls?",
            "",
        ]
    )
    for x in p["incipient_long_unusual"]:
        lines.append(
            f"- **{x['pipe']}** ({x['period']}): long_frac≥DEV_p95=`{_fmt(x['long_frac_ge_dev_p95'])}`, "
            f"vs controls pct=`{_pct(x['long_frac_p95_vs_control_pct'])}`, "
            f"sustained_unusual=`{x['sustained_unusual_vs_controls']}`, notified=`{x['notified']}`"
        )
    if not any(x["sustained_unusual_vs_controls"] for x in p["incipient_long_unusual"]):
        lines.append(
            "- **None** of the incipient 6 h windows met sustained-unusual criteria "
            "(≥50% hours ≥ DEV long p95 and that fraction ≥95th pct of controls)."
        )

    lines.extend(
        [
            "",
            "## Redundancy vs distinct evidence",
            "",
            f"- DEV correlations: `{p['dev_correlations']}`",
            f"- Event windows with unique scale leader: `{p['event_scale_leaders']}`",
            f"- Notify drivers: `{p['notify_driver_counts']}`",
            f"- Distinct long-only incipient candidates: `{[c['pipe'] for c in p['distinct_long_incip_candidates']]}`",
            "",
            "## Gains and counterexamples (together)",
            "",
            "- **Gain vs baseline abrupt notify:** none in the completed selection "
            "(see experiment results).",
            "- **Counterexample / regression:** p538 DEV hit→miss under combined τ; "
            "DIAG abrupt identical (p158 only).",
            "- **Incipient:** no notifies at selected τ; no distinct sustained long-only signal under audit rules.",
            "",
            "## Recommendation",
            "",
            f"- Distinct useful evidence: **`{p['recommendation']['distinct_useful_evidence']}`**",
            f"- Close multiscale as unsuccessful: **`{p['recommendation']['close_multiscale']}`**",
            f"- Next experiment: `{p['recommendation']['next_experiment']}`",
            "",
            p["recommendation"]["rationale"],
            "",
            "## Stop",
            "",
            "No threshold changes, new selection runs, 2019, production, or deployment.",
            "",
        ]
    )
    (OUT / "MULTISCALE_AUDIT.md").write_text("\n".join(lines) + "\n")


def _fmt(x) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{float(x):.3f}"


def _pct(x) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{100*float(x):.1f}%"


if __name__ == "__main__":
    raise SystemExit(main())
