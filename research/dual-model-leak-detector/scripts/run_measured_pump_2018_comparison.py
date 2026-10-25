#!/usr/bin/env python3
"""Paired 2018 comparison: measured-PUMP_1 dual vs baseline (frozen settings).

No threshold selection. No recalibration. Diagnostic comparison only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_eval import evaluate_scores, storage_rate_m3h  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    ABRUPT_EVENTS,
    CREDIT_HOURS,
    DIAG_END,
    FIT_END,
    PUMP_TRANSITION_M3H,
    REQUIRED_FROZEN_SHA256,
    STORAGE_TRANSITION_M3H,
)
from dual_model.detection_scores import build_all_scores  # noqa: E402
from dual_model.dual_series import build_dual_qv_hourly, verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402


BASELINE_DIR = ROOT / "outputs" / "detection_2018"
OUT_DIR = ROOT / "outputs" / "detection_2018_measured_pump1"


def _load_baseline_tau() -> dict[str, float]:
    doc = json.loads((BASELINE_DIR / "detection_results.json").read_text())
    return {m: float(doc["selection"][m]["tau"]) for m in ("A", "B", "C")}


def _load_baseline_qv() -> pd.DataFrame | None:
    csv_path = BASELINE_DIR / "dual_qv_hourly.csv"
    pq = BASELINE_DIR / "dual_qv_hourly.parquet"
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    if csv_path.exists():
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        return df
    return None


def _credit_max(score: pd.Series, onset: pd.Timestamp) -> float:
    end = onset + pd.Timedelta(hours=CREDIT_HOURS)
    w = score.loc[(score.index >= onset) & (score.index <= end)]
    w = w[np.isfinite(w)]
    return float(w.max()) if len(w) else float("nan")


def _switch_excursion_table(
    qv: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    label: str,
) -> dict:
    d_pump = flows["PUMP_1"].astype(float).diff().abs()
    switches = d_pump[d_pump > PUMP_TRANSITION_M3H].index
    if "n54" not in qv.columns or len(switches) == 0:
        return {"label": label, "n_switches": 0}
    dq = qv.diff()
    n54 = dq["n54"].reindex(switches).abs()
    total = dq.sum(axis=1).reindex(switches).abs()
    # Ordinary hours
    ordinary = d_pump[d_pump <= PUMP_TRANSITION_M3H].index
    n54_ord = dq["n54"].reindex(ordinary).abs()
    tot_ord = dq.sum(axis=1).reindex(ordinary).abs()
    return {
        "label": label,
        "n_switches": int(len(switches)),
        "n54_abs_delta_at_switch_mean": float(n54.mean()),
        "n54_abs_delta_ordinary_mean": float(n54_ord.mean()),
        "sum_abs_delta_at_switch_mean": float(total.mean()),
        "sum_abs_delta_ordinary_mean": float(tot_ord.mean()),
        "frac_switch_n54_dominates": float(
            (n54 >= dq.reindex(switches).abs().max(axis=1)).mean()
        ),
    }


def _transition_frac(scores: pd.Series, tau: float, flows: pd.DataFrame, levels: pd.Series, area: float, period: str) -> float | None:
    r = evaluate_scores(
        scores,
        period,
        tau=tau,
        flows=flows,
        levels=levels,
        tank_area_m2=area,
        rng=np.random.default_rng(0),
        n_nulls=0,
    )
    return r.get("unmatched_on_transition_frac")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scratch = OUT_DIR / "_scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    frozen_path = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
    digest = verify_frozen_hash(frozen_path)
    assert digest == REQUIRED_FROZEN_SHA256
    tau_by_method = _load_baseline_tau()
    print(f"Frozen OK {digest}; diagnostic tau={tau_by_method}", flush=True)

    series_start = str(pd.Timestamp(FIT_END) + pd.Timedelta(minutes=5))
    print(f"Building measured-pump dual q_v {series_start} → {DIAG_END} …", flush=True)
    qv, flows, levels, meta = build_dual_qv_hourly(
        series_start,
        DIAG_END,
        frozen_path=frozen_path,
        scratch=scratch,
        chunk_days=7,
        pump_boundary="measured_pump1",
    )
    try:
        qv.to_parquet(OUT_DIR / "dual_qv_hourly.parquet")
    except Exception:
        qv.to_csv(OUT_DIR / "dual_qv_hourly.csv")
    qv.to_csv(OUT_DIR / "dual_qv_hourly.csv")
    print(f"q_v shape {qv.shape}; solver failures={meta['n_solver_failures']}", flush=True)

    scores = build_all_scores(qv, flows)
    for name, s in scores.items():
        s.to_csv(OUT_DIR / f"score_{name}.csv", header=["score"])

    wn = load_nominal_wn()
    tank_area = float(np.pi * (wn.get_node("T1").diameter / 2.0) ** 2)

    # Evaluate at baseline diagnostic τ (no re-selection)
    diag = {}
    dev = {}
    for method, s in scores.items():
        tau = tau_by_method[method]
        print(f"Eval {method} tau={tau} (diagnostic, no selection) …", flush=True)
        dev[method] = evaluate_scores(
            s, "DEV", tau=tau, flows=flows, levels=levels, tank_area_m2=tank_area,
            rng=np.random.default_rng(2018), n_nulls=50,
        )
        diag[method] = evaluate_scores(
            s, "DIAG", tau=tau, flows=flows, levels=levels, tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + hash(method) % 1000), n_nulls=200,
        )

    baseline_qv = _load_baseline_qv()
    baseline_scores = {}
    if baseline_qv is not None:
        # Align columns
        common_cols = [c for c in qv.columns if c in baseline_qv.columns]
        baseline_qv = baseline_qv[common_cols].reindex(qv.index)
        # Rebuild baseline scores from stored CSVs if present
        for m in ("A", "B", "C"):
            p = BASELINE_DIR / f"score_{m}.csv"
            if p.exists():
                baseline_scores[m] = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]

    # Missed-event credit-window scores
    event_rows = []
    for ev in ABRUPT_EVENTS:
        onset = pd.Timestamp(ev.onset)
        row = {"pipe": ev.pipe, "onset": str(onset), "period": ev.period}
        for m, s in scores.items():
            row[f"{m}_credit_max_measured"] = _credit_max(s, onset)
            row[f"{m}_tau"] = tau_by_method[m]
            if m in baseline_scores:
                row[f"{m}_credit_max_baseline"] = _credit_max(baseline_scores[m], onset)
            # blocked?
            eps = episodes_from_scores(s.to_numpy(), tau=tau_by_method[m])
            notify_times = [s.index[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(s.index)]
            credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
            in_credit = [t for t in notify_times if onset <= t <= credit_end]
            row[f"{m}_hit"] = len(in_credit) > 0
            prior = [t for t in notify_times if t < onset]
            active_prior = False
            if prior and not in_credit:
                # approximate: last notify before onset with no recovery before credit
                # use evaluate event table instead
                pass
            row[f"{m}_n_credit_notifies"] = len(in_credit)
        event_rows.append(row)
    # Enrich hit/block from evaluate_scores event tables
    for period_name, block in (("DEV", dev), ("DIAG", diag)):
        for m, r in block.items():
            by_pipe = {e["pipe"]: e for e in r["events"]}
            for row in event_rows:
                if row["period"] != period_name:
                    continue
                ev = by_pipe.get(row["pipe"])
                if ev:
                    row[f"{m}_hit"] = ev["hit"]
                    row[f"{m}_delay_h"] = ev["delay_hours"]

    # Excursions
    exc_meas = _switch_excursion_table(qv, flows, label="measured_pump1")
    exc_base = None
    if baseline_qv is not None:
        exc_base = _switch_excursion_table(baseline_qv, flows, label="baseline_inp_controls")

    # Corrected transition diagnostic: pump-only vs storage (hourly-correct dV)
    d_pump = flows["PUMP_1"].astype(float).diff().abs()
    dV = storage_rate_m3h(levels, tank_area).abs()
    trans_pump = d_pump > PUMP_TRANSITION_M3H
    trans_storage = dV > STORAGE_TRANSITION_M3H
    trans_either = trans_pump | trans_storage

    def unmatched_trans_breakdown(method: str, period: str) -> dict:
        s = scores[method]
        tau = tau_by_method[method]
        r = evaluate_scores(
            s, period, tau=tau, flows=flows, levels=levels, tank_area_m2=tank_area,
            rng=np.random.default_rng(0), n_nulls=0,
        )
        # Recompute unmatched set
        idx = s.loc[
            (s.index >= pd.Timestamp({"DEV": "2018-01-08", "DIAG": "2018-07-01"}[period]))
            & (s.index <= pd.Timestamp({"DEV": "2018-06-30 23:55:00", "DIAG": "2018-12-31 23:55:00"}[period]))
        ].index
        eps = episodes_from_scores(s.loc[idx].to_numpy(), tau=tau)
        notify_times = [idx[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(idx)]
        matched = set()
        from dual_model.detection_eval import eligible_events

        for ev in eligible_events(period, idx):
            onset = pd.Timestamp(ev.onset)
            ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
            cands = [t for t in notify_times if onset <= t <= ce]
            if cands:
                matched.add(min(cands))
        unmatched = [t for t in notify_times if t not in matched]
        if not unmatched:
            return {
                "n_unmatched": 0,
                "frac_pump": None,
                "frac_storage": None,
                "frac_either": None,
                "helper_frac": r.get("unmatched_on_transition_frac"),
            }
        def frac(mask: pd.Series) -> float:
            return float(sum(1 for t in unmatched if bool(mask.get(t, False))) / len(unmatched))

        return {
            "n_unmatched": len(unmatched),
            "frac_pump_only_gt10": frac(trans_pump),
            "frac_storage_gt15_corrected": frac(trans_storage),
            "frac_either": frac(trans_either),
            "helper_frac_corrected": r.get("unmatched_on_transition_frac"),
        }

    trans_stats = {
        m: {"DEV": unmatched_trans_breakdown(m, "DEV"), "DIAG": unmatched_trans_breakdown(m, "DIAG")}
        for m in ("A", "B", "C")
    }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "diagnostic_paired_boundary_change",
        "note": (
            "Thresholds taken from baseline selection fallback; not re-selected. "
            "Boundary change may alter score distributions — metrics are diagnostic."
        ),
        "frozen_calibration_sha256": digest,
        "pump_boundary": "measured_pump1",
        "baseline_dir": str(BASELINE_DIR.relative_to(ROOT)),
        "tau_from_baseline": tau_by_method,
        "solver": {
            "n_chunks": meta["n_chunks"],
            "n_solver_failures": meta["n_solver_failures"],
            "pump_impute_totals": {
                "n_ffill": sum(c.get("n_pump_ffill", 0) for c in meta["chunks"]),
                "n_zero_impute": sum(c.get("n_pump_zero_impute", 0) for c in meta["chunks"]),
            },
        },
        "excursions": {"measured": exc_meas, "baseline": exc_base},
        "events": event_rows,
        "dev": {
            m: {
                "tau": tau_by_method[m],
                "abrupt_6h_recall": dev[m]["abrupt_6h_recall"],
                "unmatched_per_week": dev[m]["unmatched_per_week"],
                "occupancy": dev[m]["occupancy"],
                "n_hit": dev[m]["n_hit"],
                "n_eligible": dev[m]["n_eligible_abrupt"],
                "gate_pass_under_baseline_tau": dev[m]["gate_pass"],
            }
            for m in ("A", "B", "C")
        },
        "diag": {
            m: {
                "tau": tau_by_method[m],
                "abrupt_6h_recall": diag[m]["abrupt_6h_recall"],
                "mean_delay_hours": diag[m]["mean_delay_hours"],
                "unmatched_per_week": diag[m]["unmatched_per_week"],
                "occupancy": diag[m]["occupancy"],
                "unmatched_on_transition_frac": diag[m]["unmatched_on_transition_frac"],
                "timing_nulls": diag[m]["timing_nulls"],
                "events": diag[m]["events"],
            }
            for m in ("A", "B", "C")
        },
        "transition_stats_corrected": trans_stats,
    }
    # Drop bulky chunk notes from saved meta
    (OUT_DIR / "comparison_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    (OUT_DIR / "run_meta_light.json").write_text(
        json.dumps(
            {
                "n_chunks": meta["n_chunks"],
                "n_solver_failures": meta["n_solver_failures"],
                "failed_chunks": [c for c in meta["chunks"] if not c.get("converged", True)],
            },
            indent=2,
        )
        + "\n"
    )
    pd.DataFrame(event_rows).to_csv(OUT_DIR / "event_score_comparison.csv", index=False)

    # Markdown report
    lines = [
        "# 2018 measured-PUMP_1 dual vs baseline (diagnostic)",
        "",
        f"Frozen calibration: `{digest}`  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "Formulation: `PUMP1_MEASURED_BOUNDARY.md`",
        "",
        "**Diagnostic comparison only.** Same frozen calibration and baseline "
        "fallback τ (A=1.5, B=1.0, C=1.0). **No** threshold re-selection, "
        "**no** recalibration. Score distributions may shift under the new boundary.",
        "",
        f"Solver failures: **{meta['n_solver_failures']}** / {meta['n_chunks']} chunks.",
        "",
        "## Virtual-flow excursions at pump switches",
        "",
        "| Variant | n switches | mean\\|Δn54\\| switch | mean\\|Δn54\\| ordinary | mean\\|ΔΣ\\| switch | mean\\|ΔΣ\\| ordinary | frac n54 dominates |",
        "|---------|----------:|---------------------:|-----------------------:|------------------:|--------------------:|-------------------:|",
    ]
    for exc in (exc_base, exc_meas):
        if exc is None:
            continue
        lines.append(
            f"| {exc['label']} | {exc['n_switches']} | "
            f"{exc.get('n54_abs_delta_at_switch_mean')} | "
            f"{exc.get('n54_abs_delta_ordinary_mean')} | "
            f"{exc.get('sum_abs_delta_at_switch_mean')} | "
            f"{exc.get('sum_abs_delta_ordinary_mean')} | "
            f"{exc.get('frac_switch_n54_dominates')} |"
        )

    lines.extend(
        [
            "",
            "## DEV / DIAG at baseline τ (diagnostic)",
            "",
            "### DEV",
            "",
            "| Method | τ | recall | unmatched/wk | occupancy | gate_pass (info only) |",
            "|--------|---:|-------:|-------------:|----------:|:---------------------:|",
        ]
    )
    for m in ("A", "B", "C"):
        d = payload["dev"][m]
        lines.append(
            f"| {m} | {d['tau']} | {d['abrupt_6h_recall']} | {d['unmatched_per_week']:.3f} | "
            f"{d['occupancy']:.3f} | {d['gate_pass_under_baseline_tau']} |"
        )

    lines.extend(
        [
            "",
            "### DIAG",
            "",
            "| Method | τ | recall | delay h | unmatched/wk | occupancy | trans.frac (corrected helper) |",
            "|--------|---:|-------:|--------:|-------------:|----------:|------------------------------:|",
        ]
    )
    for m in ("A", "B", "C"):
        d = payload["diag"][m]
        lines.append(
            f"| {m} | {d['tau']} | {d['abrupt_6h_recall']} | {d['mean_delay_hours']} | "
            f"{d['unmatched_per_week']:.3f} | {d['occupancy']:.3f} | "
            f"{d['unmatched_on_transition_frac']} |"
        )

    lines.extend(["", "## Per-event credit-window scores", ""])
    lines.append(
        "| Pipe | Period | A max (base→meas) | B max (base→meas) | C max (base→meas) | A hit | B hit | C hit |"
    )
    lines.append(
        "|------|--------|------------------:|------------------:|------------------:|:-----:|:-----:|:-----:|"
    )
    for row in event_rows:
        def pair(m):
            b = row.get(f"{m}_credit_max_baseline")
            a = row.get(f"{m}_credit_max_measured")
            if b is None:
                return f"{a:.3f}" if a is not None and np.isfinite(a) else a
            return f"{b:.3f}→{a:.3f}"

        lines.append(
            f"| {row['pipe']} | {row['period']} | {pair('A')} | {pair('B')} | {pair('C')} | "
            f"{row.get('A_hit')} | {row.get('B_hit')} | {row.get('C_hit')} |"
        )

    lines.extend(
        [
            "",
            "## Corrected transition statistics (actual hourly intervals)",
            "",
            "Storage rate uses `A·Δh/Δt` with Δt from the index (no spurious ×12).",
            "",
        ]
    )
    for m in ("A", "B", "C"):
        lines.append(f"### Method {m}")
        lines.append("")
        lines.append("| Period | n unmatched | frac pump\\|Δ\\|>10 | frac storage\\|dV\\|>15 | frac either | helper |")
        lines.append("|--------|------------:|------------------:|----------------------:|------------:|-------:|")
        for period in ("DEV", "DIAG"):
            t = trans_stats[m][period]
            lines.append(
                f"| {period} | {t['n_unmatched']} | {t.get('frac_pump_only_gt10')} | "
                f"{t.get('frac_storage_gt15_corrected')} | {t.get('frac_either')} | "
                f"{t.get('helper_frac_corrected')} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- Baseline artifacts under `outputs/detection_2018/` are preserved.",
            "- PUMP_1 is an internal transfer only; Method C still uses p227+p235.",
            "- Stop: no 2019 / UI / Tiger / production / main.",
            "",
        ]
    )
    (OUT_DIR / "COMPARISON_RESULTS.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT_DIR / "COMPARISON_RESULTS.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
