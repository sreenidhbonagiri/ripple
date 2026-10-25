#!/usr/bin/env python3
"""2018 dual-model detection feasibility (DEV select → DIAG eval).

Uses corrected frozen calibration only. No recalibration. No 2019.
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

from dual_model.detection_eval import evaluate_scores, select_tau_on_dev  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    DEV_END,
    DEV_START,
    DIAG_END,
    DIAG_START,
    FIT_END,
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    REQUIRED_FROZEN_SHA256,
    TAU_GRID,
)
from dual_model.detection_scores import build_all_scores  # noqa: E402
from dual_model.dual_series import build_dual_qv_hourly, verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn  # noqa: E402


def main() -> int:
    out_dir = ROOT / "outputs" / "detection_2018"
    scratch = out_dir / "_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    frozen_path = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
    digest = verify_frozen_hash(frozen_path)
    print(f"Frozen calibration OK: {digest}", flush=True)

    # Need history before DEV for reference windows (24h+gap). Start slightly before DEV.
    series_start = "2018-01-07 00:00:00"  # after FIT start; excludes using FIT for eval labels
    # Actually protocol: FIT excluded from evaluation; reference may use hours after FIT_END only.
    series_start = str(pd.Timestamp(FIT_END) + pd.Timedelta(minutes=5))
    print(f"Building dual q_v {series_start} → {DIAG_END} …", flush=True)
    qv, flows, levels, _meta = build_dual_qv_hourly(
        series_start,
        DIAG_END,
        frozen_path=frozen_path,
        scratch=scratch,
        chunk_days=7,
        pump_boundary="inp_controls",
    )
    qv_path = out_dir / "dual_qv_hourly.parquet"
    try:
        qv.to_parquet(qv_path)
    except Exception:
        qv.to_csv(out_dir / "dual_qv_hourly.csv")
    print(f"q_v shape {qv.shape}", flush=True)

    print("Building scores A/B/C …", flush=True)
    scores = build_all_scores(qv, flows)
    for name, s in scores.items():
        s.to_csv(out_dir / f"score_{name}.csv", header=["score"])

    wn = load_nominal_wn()
    tank_area = float(np.pi * (wn.get_node("T1").diameter / 2.0) ** 2)

    rng = np.random.default_rng(2018)
    selection = {}
    diag_results = {}
    for method, s in scores.items():
        print(f"DEV selection method {method} …", flush=True)
        by_tau = {}
        for tau in TAU_GRID:
            by_tau[tau] = evaluate_scores(
                s,
                "DEV",
                tau=tau,
                flows=flows,
                levels=levels,
                tank_area_m2=tank_area,
                rng=rng,
                n_nulls=50,  # lighter on DEV grid; full nulls on frozen DIAG
            )
        sel = select_tau_on_dev(by_tau)
        selection[method] = {
            **sel,
            "dev_by_tau": {
                str(t): {
                    "abrupt_6h_recall": by_tau[t]["abrupt_6h_recall"],
                    "unmatched_per_week": by_tau[t]["unmatched_per_week"],
                    "occupancy": by_tau[t]["occupancy"],
                    "gate_pass": by_tau[t]["gate_pass"],
                    "n_eligible_abrupt": by_tau[t]["n_eligible_abrupt"],
                    "n_hit": by_tau[t]["n_hit"],
                }
                for t in TAU_GRID
            },
        }
        tau_star = sel["tau"]
        print(
            f"  → tau={tau_star} selection_passed={sel['selection_passed']} "
            f"fallback={sel['fallback']}",
            flush=True,
        )
        print(f"DIAG eval method {method} tau={tau_star} …", flush=True)
        diag_results[method] = evaluate_scores(
            s,
            "DIAG",
            tau=tau_star,
            flows=flows,
            levels=levels,
            tank_area_m2=tank_area,
            rng=np.random.default_rng(2018 + hash(method) % 1000),
            n_nulls=200,
        )
        diag_results[method]["selection"] = sel

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_calibration_sha256": digest,
        "protocol": "DETECTION_PROTOCOL.md",
        "periods": {
            "FIT_excluded_through": FIT_END,
            "DEV": [DEV_START, DEV_END],
            "DIAG": [DIAG_START, DIAG_END],
        },
        "gates": {
            "abrupt_6h_recall_min": GATE_RECALL,
            "unmatched_per_week_max": GATE_UNMATCHED_PER_WEEK,
            "tau_grid": list(TAU_GRID),
        },
        "acknowledgement": (
            "2018 events have already been examined; DIAG is protocol-bound "
            "diagnostic evaluation, not a first look."
        ),
        "selection": selection,
        "diag": diag_results,
        "any_selection_passed": any(selection[m]["selection_passed"] for m in selection),
    }
    (out_dir / "detection_results.json").write_text(json.dumps(payload, indent=2) + "\n")

    # Markdown
    lines = [
        "# 2018 dual-model detection feasibility results",
        "",
        f"Frozen calibration: `{digest}`  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "Protocol: `DETECTION_PROTOCOL.md` (registered before run).",
        "",
        payload["acknowledgement"],
        "",
        f"**Any method passed DEV gates:** `{payload['any_selection_passed']}`",
        "",
        "## DEV selection",
        "",
        "| Method | selection_passed | τ | fallback | DEV recall | DEV unmatched/wk |",
        "|--------|------------------|---:|----------|------------:|-----------------:|",
    ]
    for m in ("A", "B", "C"):
        sel = selection[m]
        t = sel["tau"]
        d = sel["dev_by_tau"][str(t)]
        lines.append(
            f"| {m} | {sel['selection_passed']} | {t} | {sel['fallback']} | "
            f"{d['abrupt_6h_recall']} | {d['unmatched_per_week']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## DIAG (frozen τ; diagnostic if selection failed)",
            "",
            "| Method | τ | sel_ok | abrupt 6h recall | mean delay h | unmatched/wk | occupancy | "
            "trans. frac unmatched | null recall mean | true pct vs null |",
            "|--------|---:|--------|-----------------:|-------------:|-------------:|----------:|"
            "---------------------:|-----------------:|-----------------:|",
        ]
    )
    for m in ("A", "B", "C"):
        r = diag_results[m]
        tn = r["timing_nulls"]
        lines.append(
            f"| {m} | {r['tau']} | {r['selection']['selection_passed']} | "
            f"{r['abrupt_6h_recall']} | {r['mean_delay_hours']} | "
            f"{r['unmatched_per_week']:.3f} | {r['occupancy']:.3f} | "
            f"{r['unmatched_on_transition_frac']} | {tn.get('null_recall_mean')} | "
            f"{tn.get('true_percentile_vs_null')} |"
        )

    lines.extend(["", "## Per-event DIAG", ""])
    for m in ("A", "B", "C"):
        lines.append(f"### Method {m}")
        lines.append("")
        lines.append("| Pipe | Onset | Hit | Delay h |")
        lines.append("|------|-------|-----|--------:|")
        for ev in diag_results[m]["events"]:
            lines.append(
                f"| {ev['pipe']} | {ev['onset']} | {ev['hit']} | {ev['delay_hours']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- A = signed total q_v change; B = per-sensor vector L2 change; C = |external inflow| change.",
            "- Virtual flow is not measured leak discharge.",
            "- No event-specific sensor selection or post-hoc τ retuning.",
            "- Stop: no 2019 / UI / Tiger / production / main.",
            "",
        ]
    )
    (out_dir / "DETECTION_RESULTS.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"any_selection_passed": payload["any_selection_passed"], "out": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())