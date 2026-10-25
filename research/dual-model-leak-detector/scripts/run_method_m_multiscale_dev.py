#!/usr/bin/env python3
"""Multiscale Method M DEV selection vs exact frozen Method M baseline.

Protocol must exist first:
  outputs/detection_2018_measured_pump1/method_m_multiscale/METHOD_M_MULTISCALE_PROTOCOL.md

No 2019. No DIAG if DEV selection fails. No production changes.
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

from dual_model.detection_eval import evaluate_scores, period_bounds  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    CREDIT_HOURS,
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    REQUIRED_FROZEN_SHA256,
    WARMUP_HOURS,
)
from dual_model.dual_series import verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn, subsample_hourly  # noqa: E402
from dual_model.method_m_multiscale import (  # noqa: E402
    BASELINE_TIMESCALE,
    SCALE_END,
    SCALE_START,
    TIMESCALE_REF_HOURS,
    estimate_all_timescale_scales,
    reproduce_baseline_method_m,
    score_method_m_multiscale_combined,
)
from dual_model.notifier import episodes_from_scores  # noqa: E402
from dual_model.scada_io import load_flows_2018, load_levels_2018  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "op_helpers",
    ROOT / "scripts" / "run_measured_pump_operating_point.py",
)
_op = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_op)
OCCUPANCY_MAX = _op.OCCUPANCY_MAX
event_diagnostics = _op.event_diagnostics
passes_gates = _op.passes_gates
select_largest_passing = _op.select_largest_passing

OUT_BASE = ROOT / "outputs" / "detection_2018_measured_pump1"
OUT = OUT_BASE / "method_m_multiscale"
PROTOCOL = OUT / "METHOD_M_MULTISCALE_PROTOCOL.md"
FROZEN_RESULTS = OUT_BASE / "method_m_results.json"
ARCHIVED_SCORE_M = OUT_BASE / "score_M.csv"


@dataclass(frozen=True)
class CatalogEvent:
    pipe: str
    start: pd.Timestamp
    end: pd.Timestamp
    leak_type: str
    peak: pd.Timestamp


def parse_leak_catalog() -> list[CatalogEvent]:
    cfg_path = ROOT.parents[1] / "data" / "raw" / "dataset_configuration.yaml"
    events: list[CatalogEvent] = []
    for line in cfg_path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("- p"):
            continue
        if "incipient" not in line and "abrupt" not in line:
            continue
        parts = [p.strip() for p in line.lstrip("- ").split(",")]
        if len(parts) < 6:
            continue
        pipe, start, end, _diam, ltype, peak = parts[:6]
        events.append(
            CatalogEvent(
                pipe=pipe,
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
                leak_type=ltype,
                peak=pd.Timestamp(peak),
            )
        )
    if not events:
        raise RuntimeError(f"No leak events in {cfg_path}")
    return events


def evaluate_incipient(
    scores: pd.Series,
    period: str,
    *,
    tau: float,
    catalog: list[CatalogEvent],
) -> dict:
    """Separate incipient objective: 6 h credit from catalog startTime."""
    start, end = period_bounds(period)
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    s = scores.loc[(scores.index >= start) & (scores.index <= end)].astype(float)
    index = s.index
    episodes = episodes_from_scores(s.to_numpy(), tau=tau)
    notify_times = [index[ep.notify_idx] for ep in episodes if 0 <= ep.notify_idx < len(index)]

    eligible = [
        e
        for e in catalog
        if e.leak_type == "incipient" and warm <= e.start <= end
    ]
    rows = []
    matched: set[pd.Timestamp] = set()
    for ev in eligible:
        credit_end = ev.start + pd.Timedelta(hours=CREDIT_HOURS)
        cands = [t for t in notify_times if ev.start <= t <= credit_end]
        hit = len(cands) > 0
        mt = min(cands) if hit else None
        if mt is not None:
            matched.add(mt)
        delay = (
            float((mt - ev.start).total_seconds() / 3600.0) if mt is not None else None
        )
        # credit max score in window
        win = s.loc[(s.index >= ev.start) & (s.index <= credit_end)]
        credit_max = float(win.max()) if len(win) and win.notna().any() else None
        rows.append(
            {
                "pipe": ev.pipe,
                "onset": str(ev.start),
                "peak": str(ev.peak),
                "hit": hit,
                "delay_hours": delay,
                "matched_notify": str(mt) if mt is not None else None,
                "credit_max_score": credit_max,
            }
        )
    n_hit = sum(1 for r in rows if r["hit"])
    n_ev = len(rows)
    return {
        "n_eligible": n_ev,
        "n_hit": n_hit,
        "recall": float(n_hit / n_ev) if n_ev else float("nan"),
        "mean_delay_hours": float(np.mean([r["delay_hours"] for r in rows if r["delay_hours"] is not None]))
        if any(r["delay_hours"] is not None for r in rows)
        else None,
        "events": rows,
        "note": "Incipient reported separately; not used for DEV τ selection gates.",
    }


def event_level_compare(base_rows: list[dict], multi_rows: list[dict]) -> dict:
    by_b = {r["pipe"]: r for r in base_rows}
    by_m = {r["pipe"]: r for r in multi_rows}
    pipes = sorted(set(by_b) | set(by_m))
    gains, regressions, both_hit, both_miss = [], [], [], []
    for p in pipes:
        bh = bool(by_b.get(p, {}).get("hit"))
        mh = bool(by_m.get(p, {}).get("hit"))
        row = {
            "pipe": p,
            "baseline_hit": bh,
            "multiscale_hit": mh,
            "baseline_delay": by_b.get(p, {}).get("delay_hours"),
            "multiscale_delay": by_m.get(p, {}).get("delay_hours"),
        }
        if mh and not bh:
            gains.append(row)
        elif bh and not mh:
            regressions.append(row)
        elif bh and mh:
            both_hit.append(row)
        else:
            both_miss.append(row)
    return {
        "gains": gains,
        "regressions": regressions,
        "both_hit": both_hit,
        "both_miss": both_miss,
    }


def main() -> int:
    assert PROTOCOL.is_file(), f"Register protocol before run: {PROTOCOL}"
    digest = verify_frozen_hash(ROOT / "outputs" / "calibration" / "frozen_calibration.json")
    assert digest == REQUIRED_FROZEN_SHA256
    frozen = json.loads(FROZEN_RESULTS.read_text())
    frozen_tau = float(frozen["selection"]["tau"])
    catalog = parse_leak_catalog()

    qv = pd.read_csv(OUT_BASE / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    print(f"q_v {qv.shape}; timescales {TIMESCALE_REF_HOURS}", flush=True)

    # --- Exact baseline Method M reproduction ---
    print("Reproducing frozen Method M baseline (REF=24) …", flush=True)
    s_base, sigma_base, med_base, meta_base = reproduce_baseline_method_m(qv)
    archived = pd.read_csv(ARCHIVED_SCORE_M, index_col=0, parse_dates=True)["score"]
    common = s_base.index.intersection(archived.index)
    diff = (s_base.reindex(common) - archived.reindex(common)).abs()
    finite = diff[np.isfinite(diff) & np.isfinite(s_base.reindex(common))]
    max_abs = float(finite.max()) if len(finite) else float("nan")
    baseline_ok = bool(np.isfinite(max_abs) and max_abs < 1e-8)
    print(
        f"  baseline vs archived score_M: max|Δ|={max_abs:.3e} ok={baseline_ok}; "
        f"raw_med={med_base:.6f} frozen_tau={frozen_tau}",
        flush=True,
    )
    if not baseline_ok:
        raise SystemExit(f"Baseline Method M reproduction failed max|Δ|={max_abs}")
    if abs(med_base - float(frozen["scale"]["raw_max_median"])) > 1e-6:
        raise SystemExit("SCALE raw_max_median mismatch vs frozen method_m_results.json")

    F = subsample_hourly(load_flows_2018()).reindex(s_base.index)
    L = subsample_hourly(load_levels_2018())["T1"].reindex(s_base.index)
    tank_area = float(np.pi * (load_nominal_wn().get_node("T1").diameter / 2.0) ** 2)

    base_dev = evaluate_scores(
        s_base,
        "DEV",
        tau=frozen_tau,
        flows=F,
        levels=L,
        tank_area_m2=tank_area,
        rng=np.random.default_rng(2018),
        n_nulls=50,
    )
    base_dev["events_detail"] = event_diagnostics(s_base, frozen_tau, "DEV")
    base_dev["gate_pass"] = passes_gates(base_dev)
    base_incip_dev = evaluate_incipient(s_base, "DEV", tau=frozen_tau, catalog=catalog)
    print(
        f"  baseline DEV τ={frozen_tau}: abrupt recall={base_dev['abrupt_6h_recall']} "
        f"unm/wk={base_dev['unmatched_per_week']:.3f} occ={base_dev['occupancy']:.3f} "
        f"incip recall={base_incip_dev['recall']}",
        flush=True,
    )

    # --- Multiscale combined stream ---
    print("Estimating per-timescale SCALE σ …", flush=True)
    scale_idx = qv.index[(qv.index >= SCALE_START) & (qv.index <= SCALE_END)]
    scales = estimate_all_timescale_scales(qv, scale_idx)
    for name, sc in scales.items():
        print(
            f"  {name} REF={sc.ref_hours}h sensors={sc.meta['n_sensors_kept']} "
            f"raw_med={sc.raw_max_median:.4f}",
            flush=True,
        )
    print("Computing combined s_MS (joint max over sensors×timescales) …", flush=True)
    s_ms, med_ms, ms_meta = score_method_m_multiscale_combined(qv, scales)
    OUT.mkdir(parents=True, exist_ok=True)
    s_ms.to_csv(OUT / "score_MS_combined.csv", header=["score"])
    s_base.to_csv(OUT / "score_M_baseline_repro.csv", header=["score"])

    # Register τ grid BEFORE gate outcomes
    start, end = period_bounds("DEV")
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    d = s_ms.loc[(s_ms.index >= warm) & (s_ms.index <= end)]
    d = d[np.isfinite(d)]
    qs = {q: float(d.quantile(q)) for q in (0.75, 0.9, 0.95, 0.99)}
    tau_grid = tuple(round(qs[q], 3) for q in (0.75, 0.9, 0.95, 0.99))
    print(f"Registered combined τ grid (DEV p75/p90/p95/p99): {tau_grid}", flush=True)

    by_tau: dict[float, dict] = {}
    for tau in tau_grid:
        r = evaluate_scores(
            s_ms,
            "DEV",
            tau=tau,
            flows=F,
            levels=L,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018),
            n_nulls=50,
        )
        r["gate_pass"] = passes_gates(r)
        r["events_detail"] = event_diagnostics(s_ms, tau, "DEV")
        r["incipient"] = evaluate_incipient(s_ms, "DEV", tau=tau, catalog=catalog)
        by_tau[tau] = r
        print(
            f"  τ={tau}: abrupt={r['abrupt_6h_recall']:.3f} "
            f"unm/wk={r['unmatched_per_week']:.3f} occ={r['occupancy']:.3f} "
            f"incip={r['incipient']['recall']} pass={r['gate_pass']}",
            flush=True,
        )

    sel = select_largest_passing(by_tau)
    diag = None
    comparison = None

    if sel["selection_passed"]:
        tau = float(sel["tau"])
        print(f"DEV PASS → freeze τ={tau}; run DIAG", flush=True)
        # Freeze marker before DIAG
        freeze = {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "tau": tau,
            "combined_raw_max_median": med_ms,
            "tau_grid_registered": list(tau_grid),
            "baseline_timescale": BASELINE_TIMESCALE,
            "baseline_method_m_tau": frozen_tau,
            "acknowledgement": (
                "2018 already examined; diagnostic only. No 2019. "
                "τ frozen on DEV before DIAG."
            ),
        }
        (OUT / "FROZEN_SELECTION.json").write_text(json.dumps(freeze, indent=2) + "\n")

        r = evaluate_scores(
            s_ms,
            "DIAG",
            tau=tau,
            flows=F,
            levels=L,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + 13),
            n_nulls=200,
        )
        r["events_detail"] = event_diagnostics(s_ms, tau, "DIAG")
        r["incipient"] = evaluate_incipient(s_ms, "DIAG", tau=tau, catalog=catalog)
        base_diag = evaluate_scores(
            s_base,
            "DIAG",
            tau=frozen_tau,
            flows=F,
            levels=L,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + 13),
            n_nulls=200,
        )
        base_diag["events_detail"] = event_diagnostics(s_base, frozen_tau, "DIAG")
        base_diag["incipient"] = evaluate_incipient(
            s_base, "DIAG", tau=frozen_tau, catalog=catalog
        )
        diag = {
            "tau": tau,
            "abrupt_6h_recall": r["abrupt_6h_recall"],
            "mean_delay_hours": r["mean_delay_hours"],
            "unmatched_per_week": r["unmatched_per_week"],
            "occupancy": r["occupancy"],
            "n_hit": r["n_hit"],
            "n_eligible_abrupt": r["n_eligible_abrupt"],
            "n_notifications": r["n_notifications"],
            "timing_nulls": r["timing_nulls"],
            "events_detail": r["events_detail"],
            "incipient": r["incipient"],
            "baseline_diag": {
                "tau": frozen_tau,
                "abrupt_6h_recall": base_diag["abrupt_6h_recall"],
                "mean_delay_hours": base_diag["mean_delay_hours"],
                "unmatched_per_week": base_diag["unmatched_per_week"],
                "occupancy": base_diag["occupancy"],
                "timing_nulls": base_diag["timing_nulls"],
                "events_detail": base_diag["events_detail"],
                "incipient": base_diag["incipient"],
            },
            "event_compare_abrupt": event_level_compare(
                base_diag["events_detail"], r["events_detail"]
            ),
        }
        comparison = {
            "dev": event_level_compare(
                base_dev["events_detail"], by_tau[tau]["events_detail"]
            ),
            "dev_burden": {
                "baseline_unmatched_per_week": base_dev["unmatched_per_week"],
                "multiscale_unmatched_per_week": by_tau[tau]["unmatched_per_week"],
                "baseline_occupancy": base_dev["occupancy"],
                "multiscale_occupancy": by_tau[tau]["occupancy"],
                "baseline_mean_delay": base_dev["mean_delay_hours"],
                "multiscale_mean_delay": by_tau[tau]["mean_delay_hours"],
            },
        }
    else:
        print("DEV selection FAILED — no DIAG (protocol stop).", flush=True)
        # Still compare best abrupt-recall τ informatively? No — only report failure
        # vs baseline at frozen Method M operating point for context.
        comparison = {
            "dev_baseline_only_context": {
                "baseline_tau": frozen_tau,
                "baseline_abrupt_recall": base_dev["abrupt_6h_recall"],
                "baseline_unmatched_per_week": base_dev["unmatched_per_week"],
                "baseline_occupancy": base_dev["occupancy"],
            },
            "note": "No multiscale τ selected; no event-level multiscale comparison at a frozen τ.",
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "acknowledgement": (
            "2018 events have already been examined; measured findings are diagnostic. "
            "No 2019 evaluation or tuning."
        ),
        "frozen_calibration_sha256": digest,
        "pump_boundary": "measured_pump1",
        "baseline": {
            "timescale": BASELINE_TIMESCALE,
            "ref_hours": TIMESCALE_REF_HOURS[BASELINE_TIMESCALE],
            "reproduction_max_abs_diff_vs_archived_score_M": max_abs,
            "reproduction_ok": baseline_ok,
            "raw_max_median": med_base,
            "frozen_tau": frozen_tau,
            "scale_meta": meta_base,
            "dev": {
                "abrupt_6h_recall": base_dev["abrupt_6h_recall"],
                "unmatched_per_week": base_dev["unmatched_per_week"],
                "occupancy": base_dev["occupancy"],
                "mean_delay_hours": base_dev["mean_delay_hours"],
                "n_notifications": base_dev["n_notifications"],
                "events_detail": base_dev["events_detail"],
                "incipient": base_incip_dev,
                "timing_nulls": base_dev["timing_nulls"],
            },
        },
        "timescales_registered": TIMESCALE_REF_HOURS,
        "combined_meta": ms_meta,
        "combined_raw_max_median": med_ms,
        "tau_grid_registered": list(tau_grid),
        "gates": {
            "abrupt_6h_recall_min": GATE_RECALL,
            "unmatched_per_week_max": GATE_UNMATCHED_PER_WEEK,
            "occupancy_max": OCCUPANCY_MAX,
            "incipient_not_used_for_selection": True,
        },
        "dev_by_tau": {
            str(t): {
                "tau": t,
                "abrupt_6h_recall": by_tau[t]["abrupt_6h_recall"],
                "unmatched_per_week": by_tau[t]["unmatched_per_week"],
                "occupancy": by_tau[t]["occupancy"],
                "n_hit": by_tau[t]["n_hit"],
                "n_eligible_abrupt": by_tau[t]["n_eligible_abrupt"],
                "n_notifications": by_tau[t]["n_notifications"],
                "mean_delay_hours": by_tau[t]["mean_delay_hours"],
                "gate_pass": by_tau[t]["gate_pass"],
                "events_detail": by_tau[t]["events_detail"],
                "incipient": by_tau[t]["incipient"],
                "timing_nulls": by_tau[t]["timing_nulls"],
            }
            for t in tau_grid
        },
        "selection": sel,
        "comparison_vs_baseline": comparison,
        "diag": diag,
        "diag_skipped_reason": None
        if sel["selection_passed"]
        else "no_tau_passed_dev_gates_no_fallback",
    }
    (OUT / "method_m_multiscale_results.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    _write_md(payload, sel, by_tau, tau_grid, base_dev, frozen_tau, max_abs)
    print("Wrote", OUT / "METHOD_M_MULTISCALE_RESULTS.md", flush=True)
    return 0 if sel["selection_passed"] else 2


def _write_md(payload, sel, by_tau, tau_grid, base_dev, frozen_tau, max_abs) -> None:
    lines = [
        "# Multiscale Method M — DEV results",
        "",
        f"Protocol: [`METHOD_M_MULTISCALE_PROTOCOL.md`](METHOD_M_MULTISCALE_PROTOCOL.md)  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        f"Calibration: `{payload['frozen_calibration_sha256']}`  ",
        "",
        payload["acknowledgement"],
        "",
        "## Baseline reproduction (frozen Method M)",
        "",
        f"- Timescale **medium** REF=24 h (existing Method M definition)  ",
        f"- Repro vs archived `score_M.csv`: max\\|Δ\\|=`{max_abs:.3e}`  ",
        f"- Frozen τ=`{frozen_tau}` DEV abrupt recall=`{base_dev['abrupt_6h_recall']}` "
        f"unm/wk=`{base_dev['unmatched_per_week']:.3f}` occ=`{base_dev['occupancy']:.3f}`  ",
        "",
        "## Registered timescales",
        "",
        "| ID | Ref h | Role |",
        "|----|------:|------|",
        "| short | 12 | half-day (shortest with ≥12 hourly ref samples) |",
        "| medium | 24 | **baseline Method M** |",
        "| long | 72 | multi-day |",
        "",
        "Combined score = max\\|δ/σ\\| over sensors **and** timescales, then SCALE median "
        "calibration. **One** notifier (not independent per-scale union).",
        "",
        f"Combined SCALE raw-max median=`{payload['combined_raw_max_median']:.4f}`  ",
        f"SCALE winner counts: `{payload['combined_meta'].get('scale_period_winner_counts')}`  ",
        "",
        f"Registered τ grid: `{list(tau_grid)}`",
        "",
        f"**DEV selection passed:** `{sel['selection_passed']}` — {sel['reason']} "
        f"(τ=`{sel.get('tau')}`)",
        "",
        "## DEV tradeoff (combined stream)",
        "",
        "| τ | abrupt recall | unm/wk | occ | incip recall | n_notif | gate |",
        "|--:|-------------:|-------:|----:|-------------:|--------:|:----:|",
    ]
    for t in tau_grid:
        r = by_tau[t]
        lines.append(
            f"| {t} | {r['abrupt_6h_recall']} | {r['unmatched_per_week']:.3f} | "
            f"{r['occupancy']:.3f} | {r['incipient']['recall']} | "
            f"{r['n_notifications']} | {r['gate_pass']} |"
        )

    lines.extend(["", "### DEV abrupt events (selected / each τ)", ""])
    for t in tau_grid:
        lines.append(f"- τ={t}:")
        for ev in by_tau[t]["events_detail"]:
            lines.append(
                f"  - {ev['pipe']}: hit={ev['hit']} delay={ev['delay_hours']} "
                f"pre_onset_blocked={ev['pre_onset_blocked']} "
                f"credit_max={ev['credit_max_score']}"
            )

    lines.extend(["", "### DEV incipient (report only)", ""])
    for t in tau_grid:
        inc = by_tau[t]["incipient"]
        lines.append(f"- τ={t}: recall={inc['recall']} ({inc['n_hit']}/{inc['n_eligible']})")
        for ev in inc["events"]:
            lines.append(
                f"  - {ev['pipe']}: hit={ev['hit']} delay={ev['delay_hours']} "
                f"credit_max={ev['credit_max_score']}"
            )

    cmp_ = payload.get("comparison_vs_baseline") or {}
    if sel["selection_passed"] and "dev" in cmp_:
        lines.extend(["", "## vs baseline Method M (DEV, frozen τ vs selected τ)", ""])
        b = cmp_["dev_burden"]
        lines.append(
            f"- Burden: baseline unm/wk=`{b['baseline_unmatched_per_week']:.3f}` "
            f"occ=`{b['baseline_occupancy']:.3f}` delay=`{b['baseline_mean_delay']}` → "
            f"multiscale unm/wk=`{b['multiscale_unmatched_per_week']:.3f}` "
            f"occ=`{b['multiscale_occupancy']:.3f}` delay=`{b['multiscale_mean_delay']}`"
        )
        for label, key in (
            ("Gains (miss→hit)", "gains"),
            ("Regressions (hit→miss)", "regressions"),
            ("Both hit", "both_hit"),
            ("Both miss", "both_miss"),
        ):
            rows = cmp_["dev"][key]
            lines.append(f"- **{label}:** {len(rows)}")
            for r in rows:
                lines.append(
                    f"  - {r['pipe']}: base_delay={r['baseline_delay']} "
                    f"ms_delay={r['multiscale_delay']}"
                )

    if payload.get("diag") is not None:
        d = payload["diag"]
        tn = d["timing_nulls"]
        lines.extend(
            [
                "",
                "## DIAG (frozen after DEV)",
                "",
                f"| | τ | abrupt recall | delay h | unm/wk | occ | null mean | pct |",
                f"|--|--:|-------------:|--------:|-------:|----:|----------:|----:|",
                f"| Multiscale | {d['tau']} | {d['abrupt_6h_recall']} | "
                f"{d['mean_delay_hours']} | {d['unmatched_per_week']:.3f} | "
                f"{d['occupancy']:.3f} | {tn.get('null_recall_mean')} | "
                f"{tn.get('true_percentile_vs_null')} |",
            ]
        )
        bd = d["baseline_diag"]
        btn = bd["timing_nulls"]
        lines.append(
            f"| Baseline M | {bd['tau']} | {bd['abrupt_6h_recall']} | "
            f"{bd['mean_delay_hours']} | {bd['unmatched_per_week']:.3f} | "
            f"{bd['occupancy']:.3f} | {btn.get('null_recall_mean')} | "
            f"{btn.get('true_percentile_vs_null')} |"
        )
        lines.extend(["", "### DIAG abrupt event compare", ""])
        ec = d["event_compare_abrupt"]
        for label, key in (("Gains", "gains"), ("Regressions", "regressions")):
            lines.append(f"- {label}: {[r['pipe'] for r in ec[key]]}")
        lines.extend(
            [
                "",
                f"DIAG incipient multiscale recall=`{d['incipient']['recall']}` "
                f"baseline=`{bd['incipient']['recall']}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## DIAG",
                "",
                "**Not run.** DEV selection failed; no fallback DIAG by protocol.",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Stop / isolation",
            "",
            "- No 2019 / production / Tiger / main merge / deploy / recalibration.",
            "- Deployed Method M and frozen calibration preserved.",
            "",
        ]
    )
    (OUT / "METHOD_M_MULTISCALE_RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
