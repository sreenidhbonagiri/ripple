#!/usr/bin/env python3
"""Native five-minute Method M DEV (measured-PUMP_1, frozen calibration).

Protocol: outputs/.../method_m_5min/METHOD_M_5MIN_PROTOCOL.md
Reproduces hourly DEV from existing frozen score_M.csv (no hourly re-solve).
DIAG only if all registered DEV gates pass.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_eval import evaluate_scores, period_bounds, storage_rate_m3h  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
    DEV_END,
    DEV_START,
    DIAG_END,
    DIAG_START,
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    MIN_SCALE_SAMPLES_5MIN,
    RECOVER_STEPS_5MIN,
    REF_MIN_SAMPLES_5MIN,
    REQUIRED_FROZEN_SHA256,
    TIMESTEP_SEC_5MIN,
    WARMUP_HOURS,
)
from dual_model.detection_scores import (  # noqa: E402
    estimate_method_m_scales,
    score_M_maxabs_local_change,
)
from dual_model.dual_series import build_dual_qv_5min, verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn  # noqa: E402
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

OUT = ROOT / "outputs" / "detection_2018_measured_pump1" / "method_m_5min"
HOURLY_OUT = ROOT / "outputs" / "detection_2018_measured_pump1"
PROTOCOL = OUT / "METHOD_M_5MIN_PROTOCOL.md"
FROZEN = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
SCRATCH = OUT / "scratch"
HOURLY_TAU = 4.347
SCALE_START = pd.Timestamp("2018-01-09 01:00:00")
SCALE_END = pd.Timestamp("2018-01-21 23:00:00")
# Dual must cover SCALE refs (25h before SCALE) through DEV; DIAG appended if gates pass.
DUAL_DEV_START = "2018-01-08 00:00:00"
DUAL_DEV_END = str(pd.Timestamp(DEV_END))


def _reproduce_hourly_dev(tank_area: float) -> dict:
    """Evaluate frozen hourly score_M at τ=4.347 — does not re-run hydraulics."""
    score_path = HOURLY_OUT / "score_M.csv"
    s = pd.read_csv(score_path, index_col=0, parse_dates=True).iloc[:, 0].astype(float)
    F = pd.read_csv(HOURLY_OUT / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    # Flows/levels for transition frac: load SCADA hourly-aligned to score index
    from dual_model.ltown_hydraulics import subsample_hourly

    flows = subsample_hourly(load_flows_2018()).reindex(s.index)
    levels = subsample_hourly(load_levels_2018())["T1"].reindex(s.index)
    r = evaluate_scores(
        s,
        "DEV",
        tau=HOURLY_TAU,
        flows=flows,
        levels=levels,
        tank_area_m2=tank_area,
        rng=np.random.default_rng(2018),
        n_nulls=50,
        recover_steps=1,
    )
    r["gate_pass"] = passes_gates(r)
    r["events_detail"] = event_diagnostics(s, HOURLY_TAU, "DEV", recover_steps=1)
    r["source"] = {
        "score_file": str(score_path.relative_to(ROOT)),
        "note": "Reproduced from existing frozen hourly score_M; hydraulics not re-run.",
        "tau": HOURLY_TAU,
    }
    # dual_qv unused except confirming path exists
    _ = F
    return r


def _summarize_fill_meta(meta: dict) -> dict:
    n_cleared = int(meta.get("n_qv_cleared_stale_total", 0) or 0)
    n_ts = int(meta.get("n_timestamps", 0) or 0)
    p_stats = []
    pump_stats = []
    for ch in meta.get("chunks", []):
        if "pressure_fill_stats" in ch:
            p_stats.append(ch["pressure_fill_stats"])
        if "pump_fill_stats" in ch:
            pump_stats.append(ch["pump_fill_stats"])

    def _agg(stats: list[dict]) -> dict:
        if not stats:
            return {}
        n_obs = sum(s.get("n_observed", 0) for s in stats)
        n_fill = sum(s.get("n_filled", 0) for s in stats)
        n_un = sum(s.get("n_unavailable", 0) for s in stats)
        n_cells = sum(s.get("n_cells", 0) for s in stats)
        return {
            "n_cells": n_cells,
            "n_observed": n_obs,
            "n_filled": n_fill,
            "n_unavailable": n_un,
            "frac_observed": n_obs / max(n_cells, 1),
            "frac_filled": n_fill / max(n_cells, 1),
            "frac_unavailable": n_un / max(n_cells, 1),
        }

    return {
        "n_timestamps": n_ts,
        "n_solver_failures": int(meta.get("n_solver_failures", 0)),
        "n_chunks": int(meta.get("n_chunks", 0)),
        "n_qv_cleared_stale_total": n_cleared,
        "frac_qv_cleared_stale": n_cleared / max(n_ts, 1),
        "median_index_step": meta.get("median_index_step"),
        "pressure": _agg(p_stats),
        "pump": _agg(pump_stats),
    }


def _build_or_load_dual(start: str, end: str, path: Path, chunk_days: int = 3) -> tuple:
    if path.exists():
        print(f"Loading cached dual {path} …", flush=True)
        qv = pd.read_csv(path, index_col=0, parse_dates=True)
        flows = pd.read_csv(path.with_name("flows_5min.csv"), index_col=0, parse_dates=True)
        levels = pd.read_csv(path.with_name("levels_5min.csv"), index_col=0, parse_dates=True).iloc[:, 0]
        meta = json.loads(path.with_name("dual_meta.json").read_text())
        return qv, flows, levels, meta

    print(f"Building 5-min dual {start} → {end} (chunk_days={chunk_days}) …", flush=True)
    t0 = time.perf_counter()
    qv, flows, levels, meta = build_dual_qv_5min(
        start,
        end,
        frozen_path=FROZEN,
        scratch=SCRATCH,
        chunk_days=chunk_days,
        pump_boundary="measured_pump1",
        scada_year=2018,
        causal_fill_max_age_steps=CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
    )
    meta["runtime_sec_build"] = float(time.perf_counter() - t0)
    path.parent.mkdir(parents=True, exist_ok=True)
    qv.to_csv(path)
    flows.to_csv(path.with_name("flows_5min.csv"))
    levels.to_csv(path.with_name("levels_5min.csv"), header=["T1"])
    # Chunk notes can be large; keep summary + truncated chunk list
    meta_store = {k: v for k, v in meta.items() if k != "chunks"}
    meta_store["chunks"] = [
        {kk: vv for kk, vv in ch.items() if kk not in ("pressure_fill_stats", "pump_fill_stats", "level_fill_stats")}
        | {
            "pressure_fill_stats": ch.get("pressure_fill_stats"),
            "pump_fill_stats": ch.get("pump_fill_stats"),
            "level_fill_stats": ch.get("level_fill_stats"),
        }
        for ch in meta.get("chunks", [])
    ]
    path.with_name("dual_meta.json").write_text(json.dumps(meta_store, indent=2, default=str) + "\n")
    print(
        f"  dual done: n={len(qv)} failures={meta['n_solver_failures']} "
        f"runtime={meta['runtime_sec_build']:.1f}s",
        flush=True,
    )
    return qv, flows, levels, meta


def main() -> int:
    t_all = time.perf_counter()
    assert PROTOCOL.exists(), "Register METHOD_M_5MIN_PROTOCOL.md before running"
    digest = verify_frozen_hash(FROZEN)
    assert digest == REQUIRED_FROZEN_SHA256
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    tank_area = float(np.pi * (load_nominal_wn().get_node("T1").diameter / 2.0) ** 2)

    print("=== Reproduce hourly Method M DEV from frozen score_M ===", flush=True)
    hourly_dev = _reproduce_hourly_dev(tank_area)
    print(
        f"  hourly τ={HOURLY_TAU}: recall={hourly_dev['abrupt_6h_recall']} "
        f"unm/wk={hourly_dev['unmatched_per_week']:.3f} occ={hourly_dev['occupancy']:.3f} "
        f"pass={hourly_dev['gate_pass']}",
        flush=True,
    )

    dual_path = OUT / "dual_qv_5min_dev.csv"
    qv, flows, levels, dual_meta = _build_or_load_dual(DUAL_DEV_START, DUAL_DEV_END, dual_path)
    fill_summary = _summarize_fill_meta(dual_meta)
    print(f"  fill/missing summary: {json.dumps(fill_summary, default=str)}", flush=True)

    # Alignment checks
    step = qv.index.to_series().diff().median()
    assert step == pd.Timedelta(minutes=5), f"expected 5-min step, got {step}"
    assert flows.index.equals(qv.index)
    assert levels.index.equals(qv.index)

    scale_idx = qv.index[(qv.index >= SCALE_START) & (qv.index <= SCALE_END)]
    print(
        f"Estimating SCALE σ_i on {scale_idx[0]} → {scale_idx[-1]} (n={len(scale_idx)}) …",
        flush=True,
    )
    t_score = time.perf_counter()
    sigma, raw_med, scale_meta = estimate_method_m_scales(
        qv,
        scale_idx,
        min_scale_samples=MIN_SCALE_SAMPLES_5MIN,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    print(
        f"  kept {scale_meta['n_sensors_kept']} sensors; raw_max median={raw_med}",
        flush=True,
    )
    print("Computing s_M (5-min) …", flush=True)
    s_m = score_M_maxabs_local_change(
        qv,
        sigma_m3h=sigma,
        raw_max_median=raw_med,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    score_runtime = float(time.perf_counter() - t_score)
    s_m.to_csv(OUT / "score_M_5min.csv", header=["score"])
    sigma.to_csv(OUT / "method_m_5min_sigma.csv", header=["sigma_m3h"])

    start, end = period_bounds("DEV")
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    d = s_m.loc[(s_m.index >= warm) & (s_m.index <= end)]
    d = d[np.isfinite(d)]
    qs = {q: float(d.quantile(q)) for q in (0.75, 0.9, 0.95, 0.99)}
    tau_grid = tuple(round(qs[q], 3) for q in (0.75, 0.9, 0.95, 0.99))
    print(f"Registered τ grid (DEV p75/p90/p95/p99): {tau_grid}", flush=True)

    by_tau = {}
    for tau in tau_grid:
        r = evaluate_scores(
            s_m,
            "DEV",
            tau=tau,
            flows=flows,
            levels=levels,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018),
            n_nulls=50,
            recover_steps=RECOVER_STEPS_5MIN,
        )
        r["gate_pass"] = passes_gates(r)
        r["events_detail"] = event_diagnostics(
            s_m, tau, "DEV", recover_steps=RECOVER_STEPS_5MIN
        )
        by_tau[tau] = r
        print(
            f"  τ={tau}: recall={r['abrupt_6h_recall']:.3f} "
            f"unm/wk={r['unmatched_per_week']:.3f} occ={r['occupancy']:.3f} "
            f"pass={r['gate_pass']}",
            flush=True,
        )

    sel = select_largest_passing(by_tau)
    diag = None
    diag_meta = None
    if sel["selection_passed"]:
        tau = float(sel["tau"])
        print(f"DEV PASS → building DIAG dual and evaluating at τ={tau}", flush=True)
        diag_path = OUT / "dual_qv_5min_diag.csv"
        qv_d, flows_d, levels_d, diag_meta = _build_or_load_dual(
            str(pd.Timestamp(DIAG_START)),
            str(pd.Timestamp(DIAG_END)),
            diag_path,
        )
        # Concatenate DEV+DIAG for continuous refs into DIAG
        qv_full = pd.concat([qv, qv_d]).sort_index()
        qv_full = qv_full[~qv_full.index.duplicated(keep="first")]
        flows_full = pd.concat([flows, flows_d]).sort_index()
        flows_full = flows_full[~flows_full.index.duplicated(keep="first")].reindex(qv_full.index)
        levels_full = pd.concat([levels, levels_d]).sort_index()
        levels_full = levels_full[~levels_full.index.duplicated(keep="first")].reindex(qv_full.index)
        s_full = score_M_maxabs_local_change(
            qv_full,
            sigma_m3h=sigma,
            raw_max_median=raw_med,
            ref_min_samples=REF_MIN_SAMPLES_5MIN,
        )
        s_full.to_csv(OUT / "score_M_5min_full.csv", header=["score"])
        r = evaluate_scores(
            s_full,
            "DIAG",
            tau=tau,
            flows=flows_full,
            levels=levels_full,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + 13),
            n_nulls=200,
            recover_steps=RECOVER_STEPS_5MIN,
        )
        r["events_detail"] = event_diagnostics(
            s_full, tau, "DIAG", recover_steps=RECOVER_STEPS_5MIN
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
            "n_unmatched": r["n_unmatched"],
            "unmatched_on_transition_frac": r["unmatched_on_transition_frac"],
            "timing_nulls": r["timing_nulls"],
            "events_detail": r["events_detail"],
            "dual_fill_summary": _summarize_fill_meta(diag_meta),
            "dual_runtime_sec": diag_meta.get("runtime_sec_build"),
        }
    else:
        print("DEV selection FAILED — no DIAG (protocol stop).", flush=True)

    # Paired comparison vs hourly at selected / best 5-min τ vs frozen hourly
    compare_tau = sel.get("tau")
    five_at = by_tau.get(compare_tau) if compare_tau is not None else None
    if five_at is None and by_tau:
        # Still report p99 row for comparison when selection fails
        five_at = by_tau[tau_grid[-1]]
        compare_tau = tau_grid[-1]

    event_cmp = []
    if five_at is not None:
        h_ev = {e["pipe"]: e for e in hourly_dev["events_detail"]}
        for e in five_at["events_detail"]:
            h = h_ev.get(e["pipe"], {})
            event_cmp.append(
                {
                    "pipe": e["pipe"],
                    "hourly_hit": h.get("hit"),
                    "hourly_delay_hours": h.get("delay_hours"),
                    "hourly_pre_onset_blocked": h.get("pre_onset_blocked"),
                    "five_min_hit": e.get("hit"),
                    "five_min_delay_hours": e.get("delay_hours"),
                    "five_min_pre_onset_blocked": e.get("pre_onset_blocked"),
                    "hit_gain": bool(e.get("hit")) and not bool(h.get("hit")),
                    "hit_regression": bool(h.get("hit")) and not bool(e.get("hit")),
                    "delay_delta_hours": (
                        None
                        if e.get("delay_hours") is None or h.get("delay_hours") is None
                        else float(e["delay_hours"]) - float(h["delay_hours"])
                    ),
                }
            )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "acknowledgement": (
            "2018 events have already been examined; measured findings are diagnostic. "
            "Higher resolution is not assumed to improve sensitivity."
        ),
        "frozen_calibration_sha256": digest,
        "pump_boundary": "measured_pump1",
        "timestep_sec": TIMESTEP_SEC_5MIN,
        "ref_min_samples": REF_MIN_SAMPLES_5MIN,
        "min_scale_samples": MIN_SCALE_SAMPLES_5MIN,
        "recover_steps": RECOVER_STEPS_5MIN,
        "causal_fill_max_age_steps": CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
        "runtime_sec_total": float(time.perf_counter() - t_all),
        "runtime_sec_score": score_runtime,
        "runtime_sec_dual_dev": dual_meta.get("runtime_sec_build"),
        "dual_fill_summary": fill_summary,
        "hourly_baseline_reproduced": {
            "tau": HOURLY_TAU,
            "abrupt_6h_recall": hourly_dev["abrupt_6h_recall"],
            "mean_delay_hours": hourly_dev["mean_delay_hours"],
            "unmatched_per_week": hourly_dev["unmatched_per_week"],
            "occupancy": hourly_dev["occupancy"],
            "n_hit": hourly_dev["n_hit"],
            "n_eligible_abrupt": hourly_dev["n_eligible_abrupt"],
            "n_notifications": hourly_dev["n_notifications"],
            "gate_pass": hourly_dev["gate_pass"],
            "events_detail": hourly_dev["events_detail"],
            "source": hourly_dev["source"],
        },
        "scale": {
            "period": [str(SCALE_START), str(SCALE_END)],
            **scale_meta,
            "sigma_m3h": {k: float(v) for k, v in sigma.items()},
        },
        "score_dev_distribution": {
            "n": int(len(d)),
            "mean": float(d.mean()) if len(d) else None,
            "quantiles": {str(k): float(v) for k, v in qs.items()},
            "max": float(d.max()) if len(d) else None,
        },
        "tau_grid_registered": list(tau_grid),
        "gates": {
            "abrupt_6h_recall_min": GATE_RECALL,
            "unmatched_per_week_max": GATE_UNMATCHED_PER_WEEK,
            "occupancy_max": OCCUPANCY_MAX,
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
                "gate_pass": by_tau[t]["gate_pass"],
                "mean_delay_hours": by_tau[t]["mean_delay_hours"],
                "events_detail": by_tau[t]["events_detail"],
                "timing_nulls": by_tau[t]["timing_nulls"],
            }
            for t in tau_grid
        },
        "selection": sel,
        "paired_comparison": {
            "hourly_tau": HOURLY_TAU,
            "five_min_tau_reported": compare_tau,
            "five_min_selection_passed": sel["selection_passed"],
            "recall_hourly": hourly_dev["abrupt_6h_recall"],
            "recall_five_min": five_at["abrupt_6h_recall"] if five_at else None,
            "unmatched_per_week_hourly": hourly_dev["unmatched_per_week"],
            "unmatched_per_week_five_min": five_at["unmatched_per_week"] if five_at else None,
            "occupancy_hourly": hourly_dev["occupancy"],
            "occupancy_five_min": five_at["occupancy"] if five_at else None,
            "mean_delay_hourly": hourly_dev["mean_delay_hours"],
            "mean_delay_five_min": five_at["mean_delay_hours"] if five_at else None,
            "events": event_cmp,
        },
        "diag": diag,
        "diag_skipped_reason": None
        if sel["selection_passed"]
        else "no_tau_passed_dev_gates_no_fallback",
    }
    (OUT / "method_m_5min_results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    _write_md(payload, sel, by_tau, tau_grid, hourly_dev)
    print("Wrote", OUT / "METHOD_M_5MIN_RESULTS.md", flush=True)
    print(f"Total runtime {payload['runtime_sec_total']:.1f}s", flush=True)
    return 0


def _write_md(payload, sel, by_tau, tau_grid, hourly_dev) -> None:
    lines = [
        "# Method M five-minute DEV results (measured-PUMP_1)",
        "",
        f"Protocol: [`METHOD_M_5MIN_PROTOCOL.md`](METHOD_M_5MIN_PROTOCOL.md)  ",
        f"Frozen calibration: `{payload['frozen_calibration_sha256']}`  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "",
        payload["acknowledgement"],
        "",
        "## Settings",
        "",
        f"- timestep_sec=`{payload['timestep_sec']}`  ",
        f"- REF_MIN_SAMPLES=`{payload['ref_min_samples']}`, "
        f"MIN_SCALE_SAMPLES=`{payload['min_scale_samples']}`, "
        f"RECOVER_STEPS=`{payload['recover_steps']}` (1 h)  ",
        f"- causal_fill_max_age_steps=`{payload['causal_fill_max_age_steps']}`  ",
        f"- dual DEV runtime_s=`{payload.get('runtime_sec_dual_dev')}`, "
        f"score runtime_s=`{payload.get('runtime_sec_score')}`, "
        f"total_s=`{payload.get('runtime_sec_total')}`  ",
        "",
        "### Measurement / fill / solver",
        "",
        "```json",
        json.dumps(payload["dual_fill_summary"], indent=2, default=str),
        "```",
        "",
        "## Hourly baseline (reproduced from frozen score_M; hydraulics not re-run)",
        "",
        f"τ=`{HOURLY_TAU}`: recall=`{hourly_dev['abrupt_6h_recall']}` "
        f"unm/wk=`{hourly_dev['unmatched_per_week']:.3f}` "
        f"occ=`{hourly_dev['occupancy']:.3f}` "
        f"mean_delay_h=`{hourly_dev['mean_delay_hours']}`  ",
        "",
        "## Five-minute DEV",
        "",
        f"**DEV selection passed:** `{sel['selection_passed']}`  ",
        f"Selection: τ=`{sel.get('tau')}` — {sel['reason']}",
        "",
        f"Registered τ grid (DEV p75/p90/p95/p99): `{list(tau_grid)}`",
        "",
        "Gates: recall≥2/3, unmatched/wk≤3, occupancy≤0.20.",
        "",
        "| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |",
        "|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|",
    ]
    for t in tau_grid:
        r = by_tau[t]
        lines.append(
            f"| {t} | {r['abrupt_6h_recall']} | {r['unmatched_per_week']:.3f} | "
            f"{r['occupancy']:.3f} | {r['n_hit']}/{r['n_eligible_abrupt']} | "
            f"{r['n_notifications']} | {r['gate_pass']} |"
        )
    lines.extend(["", "### DEV events (each τ)", ""])
    for t in tau_grid:
        lines.append(f"- τ={t}:")
        for ev in by_tau[t]["events_detail"]:
            lines.append(
                f"  - {ev['pipe']}: hit={ev['hit']} delay={ev['delay_hours']} "
                f"pre_onset_blocked={ev['pre_onset_blocked']} "
                f"credit_max={ev['credit_max_score']}"
            )

    pc = payload["paired_comparison"]
    lines.extend(
        [
            "",
            "## Paired hourly vs five-minute",
            "",
            f"Five-minute τ reported: `{pc['five_min_tau_reported']}` "
            f"(selection_passed=`{pc['five_min_selection_passed']}`)",
            "",
            "| Metric | Hourly | Five-minute |",
            "|--------|-------:|------------:|",
            f"| Recall | {pc['recall_hourly']} | {pc['recall_five_min']} |",
            f"| Mean delay h | {pc['mean_delay_hourly']} | {pc['mean_delay_five_min']} |",
            (
                f"| Unmatched/wk | {pc['unmatched_per_week_hourly']:.3f} | "
                f"{pc['unmatched_per_week_five_min']:.3f} |"
                if pc["unmatched_per_week_five_min"] is not None
                else f"| Unmatched/wk | {pc['unmatched_per_week_hourly']:.3f} | None |"
            ),
            (
                f"| Occupancy | {pc['occupancy_hourly']:.3f} | {pc['occupancy_five_min']:.3f} |"
                if pc["occupancy_five_min"] is not None
                else f"| Occupancy | {pc['occupancy_hourly']:.3f} | None |"
            ),
            "",
            "| Pipe | Hourly hit/delay | 5-min hit/delay | Gain | Regression | Delay Δh |",
            "|------|-----------------:|----------------:|:----:|:----------:|---------:|",
        ]
    )
    for e in pc["events"]:
        lines.append(
            f"| {e['pipe']} | {e['hourly_hit']}/{e['hourly_delay_hours']} | "
            f"{e['five_min_hit']}/{e['five_min_delay_hours']} | "
            f"{e['hit_gain']} | {e['hit_regression']} | {e['delay_delta_hours']} |"
        )

    if payload["diag"] is not None:
        diag = payload["diag"]
        tn = diag["timing_nulls"]
        lines.extend(
            [
                "",
                "## DIAG (frozen τ)",
                "",
                "| τ | recall | delay h | unmatched/wk | occupancy | null recall mean | true pct vs null |",
                "|--:|-------:|--------:|-------------:|----------:|-----------------:|-----------------:|",
                f"| {diag['tau']} | {diag['abrupt_6h_recall']} | {diag['mean_delay_hours']} | "
                f"{diag['unmatched_per_week']:.3f} | {diag['occupancy']:.3f} | "
                f"{tn.get('null_recall_mean')} | {tn.get('true_percentile_vs_null')} |",
                "",
                "| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |",
                "|------|:---:|--------:|:-----------------:|-----------:|",
            ]
        )
        for ev in diag["events_detail"]:
            lines.append(
                f"| {ev['pipe']} | {ev['hit']} | {ev['delay_hours']} | "
                f"{ev['pre_onset_blocked']} | {ev['credit_max_score']} |"
            )
    else:
        lines.extend(
            [
                "",
                "## DIAG",
                "",
                f"**Not run.** {payload['diag_skipped_reason']}",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Hourly baseline is score-only reproduction, not a hydraulic re-solve.",
            "- No 2019 / production / UI / Tiger / deploy / recalibration.",
            "",
        ]
    )
    (OUT / "METHOD_M_5MIN_RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
