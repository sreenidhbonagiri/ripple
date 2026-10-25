#!/usr/bin/env python3
"""Method M DEV operating-point evaluation (measured-PUMP_1 dual).

Protocol registered first: METHOD_M_PROTOCOL.md
No DIAG if DEV selection fails. No p866/DIAG-based choices.
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

from dual_model.detection_eval import evaluate_scores, period_bounds  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    REQUIRED_FROZEN_SHA256,
    WARMUP_HOURS,
)
from dual_model.detection_scores import (  # noqa: E402
    estimate_method_m_scales,
    score_M_maxabs_local_change,
)
from dual_model.dual_series import verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn, subsample_hourly  # noqa: E402
from dual_model.scada_io import load_flows_2018, load_levels_2018  # noqa: E402

# Reuse operating-point helpers without package-importing scripts/
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

OUT = ROOT / "outputs" / "detection_2018_measured_pump1"
PROTOCOL = OUT / "METHOD_M_PROTOCOL.md"
SCALE_START = pd.Timestamp("2018-01-09 01:00:00")
SCALE_END = pd.Timestamp("2018-01-21 23:00:00")


def main() -> int:
    assert PROTOCOL.exists(), "Register METHOD_M_PROTOCOL.md before running"
    digest = verify_frozen_hash(ROOT / "outputs" / "calibration" / "frozen_calibration.json")
    assert digest == REQUIRED_FROZEN_SHA256

    qv = pd.read_csv(OUT / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    print(f"q_v shape {qv.shape}; all columns used (n={qv.shape[1]})", flush=True)

    scale_idx = qv.index[(qv.index >= SCALE_START) & (qv.index <= SCALE_END)]
    print(f"Estimating SCALE σ_i on {scale_idx[0]} → {scale_idx[-1]} (n={len(scale_idx)}) …", flush=True)
    sigma, raw_med, scale_meta = estimate_method_m_scales(qv, scale_idx)
    print(
        f"  kept {scale_meta['n_sensors_kept']} sensors; "
        f"dropped {scale_meta['sensors_dropped']}; "
        f"raw_max median={raw_med:.4f}",
        flush=True,
    )
    print("Computing s_M …", flush=True)
    s_m = score_M_maxabs_local_change(qv, sigma_m3h=sigma, raw_max_median=raw_med)
    s_m.to_csv(OUT / "score_M.csv", header=["score"])

    # Register τ grid from DEV quantiles BEFORE gate evaluation outcomes drive expansion
    start, end = period_bounds("DEV")
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    d = s_m.loc[(s_m.index >= warm) & (s_m.index <= end)]
    d = d[np.isfinite(d)]
    qs = {q: float(d.quantile(q)) for q in (0.75, 0.9, 0.95, 0.99)}
    tau_grid = tuple(round(qs[q], 3) for q in (0.75, 0.9, 0.95, 0.99))
    print(f"Registered τ grid from DEV quantiles: {tau_grid}", flush=True)

    F = subsample_hourly(load_flows_2018()).reindex(s_m.index)
    L = subsample_hourly(load_levels_2018())["T1"].reindex(s_m.index)
    tank_area = float(np.pi * (load_nominal_wn().get_node("T1").diameter / 2.0) ** 2)

    by_tau = {}
    for tau in tau_grid:
        r = evaluate_scores(
            s_m,
            "DEV",
            tau=tau,
            flows=F,
            levels=L,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018),
            n_nulls=50,
        )
        r["gate_pass"] = passes_gates(r)
        r["events_detail"] = event_diagnostics(s_m, tau, "DEV")
        by_tau[tau] = r
        print(
            f"  τ={tau}: recall={r['abrupt_6h_recall']:.3f} "
            f"unm/wk={r['unmatched_per_week']:.3f} occ={r['occupancy']:.3f} "
            f"pass={r['gate_pass']}",
            flush=True,
        )

    sel = select_largest_passing(by_tau)
    diag = None
    if sel["selection_passed"]:
        tau = float(sel["tau"])
        print(f"DEV PASS → DIAG at τ={tau}", flush=True)
        r = evaluate_scores(
            s_m,
            "DIAG",
            tau=tau,
            flows=F,
            levels=L,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + 13),
            n_nulls=200,
        )
        r["events_detail"] = event_diagnostics(s_m, tau, "DIAG")
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
        }
    else:
        print("DEV selection FAILED — no DIAG (protocol stop).", flush=True)

    # Method B inequivalence note (short)
    comparison = {
        "method_B": "L2(||δ||)/mean_i(σ_ref,i(t)) with rolling causal σ",
        "method_M": "max_i|δ_i/σ_i^{SCALE}| / median_SCALE(raw max)",
        "equivalent": False,
    }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "acknowledgement": (
            "2018 events have already been examined; measured findings are diagnostic."
        ),
        "frozen_calibration_sha256": digest,
        "pump_boundary": "measured_pump1",
        "vs_method_B": comparison,
        "scale": {
            "period": [str(SCALE_START), str(SCALE_END)],
            **scale_meta,
            "sigma_m3h": {k: float(v) for k, v in sigma.items()},
        },
        "score_dev_distribution": {
            "n": int(len(d)),
            "mean": float(d.mean()),
            "quantiles": {str(k): float(v) for k, v in qs.items()},
            "max": float(d.max()),
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
        "diag": diag,
        "diag_skipped_reason": None
        if sel["selection_passed"]
        else "no_tau_passed_dev_gates_no_fallback",
    }
    (OUT / "method_m_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    sigma.to_csv(OUT / "method_m_sigma.csv", header=["sigma_m3h"])

    lines = [
        "# Method M operating-point results (measured-PUMP_1)",
        "",
        f"Protocol: [`METHOD_M_PROTOCOL.md`](METHOD_M_PROTOCOL.md) (registered before run).  ",
        f"Frozen calibration: `{digest}`  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "",
        payload["acknowledgement"],
        "",
        "## vs Method B",
        "",
        "Method B is **not** equivalent: B uses L2(delta)/mean rolling ref sigma; "
        "M uses training-only per-sensor sigma and max |z_i| with SCALE median "
        "max-calibration. Not a rename of B.",
        "",
        f"**DEV selection passed:** `{sel['selection_passed']}`  ",
        f"Selection: τ=`{sel.get('tau')}` — {sel['reason']}",
        "",
        f"SCALE: `{SCALE_START}` → `{SCALE_END}`; sensors kept "
        f"{scale_meta['n_sensors_kept']}/{qv.shape[1]}; "
        f"raw-max median={raw_med:.4f}.",
        "",
        f"Registered τ grid (DEV p75/p90/p95/p99): `{list(tau_grid)}`",
        "",
        "Gates: recall≥2/3, unmatched/wk≤3, occupancy≤0.20.",
        "",
        "## DEV tradeoff",
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

    if diag is not None:
        lines.extend(
            [
                "",
                "## DIAG (frozen τ)",
                "",
                f"| τ | recall | delay h | unmatched/wk | occupancy | null recall mean | true pct vs null |",
                f"|--:|-------:|--------:|-------------:|----------:|-----------------:|-----------------:|",
            ]
        )
        tn = diag["timing_nulls"]
        lines.append(
            f"| {diag['tau']} | {diag['abrupt_6h_recall']} | {diag['mean_delay_hours']} | "
            f"{diag['unmatched_per_week']:.3f} | {diag['occupancy']:.3f} | "
            f"{tn.get('null_recall_mean')} | {tn.get('true_percentile_vs_null')} |"
        )
        lines.extend(["", "| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |",
                      "|------|:---:|--------:|:-----------------:|-----------:|"])
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
                "**Not run.** DEV selection failed; no fallback DIAG by protocol.",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Standardized scores are not probabilities; hours and sensors are dependent.",
            "- No 2019 / production / UI / Tiger / deploy / recalibration.",
            "",
        ]
    )
    (OUT / "METHOD_M_RESULTS.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "METHOD_M_RESULTS.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
