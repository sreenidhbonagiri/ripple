#!/usr/bin/env python3
"""DEV operating-point selection for measured-PUMP_1 dual (quantile τ grid).

Protocol: outputs/detection_2018_measured_pump1/OPERATING_POINT_PROTOCOL.md
No grid expansion after results. DIAG only if ≥1 method passes. No fallback DIAG.
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

from dual_model.detection_eval import eligible_events, evaluate_scores, period_bounds  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    ABRUPT_EVENTS,
    CREDIT_HOURS,
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    REQUIRED_FROZEN_SHA256,
    WARMUP_HOURS,
)
from dual_model.dual_series import verify_frozen_hash  # noqa: E402
from dual_model.ltown_hydraulics import load_nominal_wn, subsample_hourly  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402
from dual_model.scada_io import load_flows_2018, load_levels_2018  # noqa: E402

OUT = ROOT / "outputs" / "detection_2018_measured_pump1"
PROTOCOL = OUT / "OPERATING_POINT_PROTOCOL.md"

# Registered a priori from DEV p75/p90/p95/p99 (OPERATING_POINT_PROTOCOL.md)
TAU_GRID: dict[str, tuple[float, ...]] = {
    "A": (0.669, 1.097, 1.343, 1.791),
    "B": (7.843, 10.999, 13.031, 19.747),
    "C": (1.103, 1.530, 1.929, 2.349),
}
OCCUPANCY_MAX = 0.20


def load_scores() -> dict[str, pd.Series]:
    out = {}
    for m in ("A", "B", "C"):
        s = pd.read_csv(OUT / f"score_{m}.csv", index_col=0, parse_dates=True).iloc[:, 0]
        out[m] = s.astype(float)
    return out


def score_distribution(s: pd.Series, period: str) -> dict:
    start, end = period_bounds(period)
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    d = s.loc[(s.index >= warm) & (s.index <= end)]
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return {"n": 0}
    qs = [0.5, 0.75, 0.9, 0.95, 0.99]
    return {
        "n": int(len(d)),
        "mean": float(d.mean()),
        "std": float(d.std(ddof=0)),
        "min": float(d.min()),
        "max": float(d.max()),
        "quantiles": {str(q): float(d.quantile(q)) for q in qs},
        "frac_ge_0": float((d >= 0).mean()) if period else None,
    }


def event_diagnostics(
    scores: pd.Series,
    tau: float,
    period: str,
    *,
    recover_steps: int | None = None,
) -> list[dict]:
    from dual_model.detection_protocol import RECOVER_STEPS

    start, end = period_bounds(period)
    s = scores.loc[(scores.index >= start) & (scores.index <= end)].astype(float)
    index = s.index
    events = eligible_events(period, index)
    rec = RECOVER_STEPS if recover_steps is None else int(recover_steps)
    eps = episodes_from_scores(s.to_numpy(), tau=tau, recover_steps=rec)
    notify_times = [index[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(index)]

    # Active mask for pre-onset blocking
    active = np.zeros(len(index), dtype=bool)
    for ep in eps:
        if ep.notify_idx < 0:
            continue
        active[ep.notify_idx : ep.end_idx + 1] = True

    rows = []
    for ev in events:
        onset = pd.Timestamp(ev.onset)
        credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
        # index position at/after onset
        pos = index.searchsorted(onset)
        if pos >= len(index):
            pos = len(index) - 1
        # If onset falls between hours, blocking refers to the hour at/after onset
        # and whether any episode was already active entering the credit window.
        pre_onset_blocked = False
        if pos > 0 and active[pos - 1]:
            pre_onset_blocked = True
        elif pos < len(index) and index[pos] <= onset and active[pos]:
            # exact hour onset while already active from prior notify
            # (notify_idx < pos would mean started earlier)
            pass
        # More precise: episode active at the last index strictly before onset
        before = index[index < onset]
        if len(before):
            i_before = index.get_loc(before[-1])
            if isinstance(i_before, slice):
                i_before = i_before.start
            pre_onset_blocked = bool(active[int(i_before)])

        cands = [t for t in notify_times if onset <= t <= credit_end]
        hit = len(cands) > 0
        delay = float((min(cands) - onset).total_seconds() / 3600.0) if hit else None
        credit = s.loc[(s.index >= onset) & (s.index <= credit_end)]
        credit = credit[np.isfinite(credit)]
        rows.append(
            {
                "pipe": ev.pipe,
                "onset": str(onset),
                "period": period,
                "hit": hit,
                "delay_hours": delay,
                "matched_notify": str(min(cands)) if hit else None,
                "pre_onset_blocked": pre_onset_blocked,
                "credit_max_score": float(credit.max()) if len(credit) else None,
                "credit_n_finite": int(len(credit)),
                "n_credit_notifies": len(cands),
            }
        )
    return rows


def passes_gates(row: dict) -> bool:
    return (
        row["n_eligible_abrupt"] > 0
        and np.isfinite(row["abrupt_6h_recall"])
        and row["abrupt_6h_recall"] >= GATE_RECALL
        and row["unmatched_per_week"] <= GATE_UNMATCHED_PER_WEEK
        and row["occupancy"] <= OCCUPANCY_MAX
    )


def select_largest_passing(by_tau: dict[float, dict]) -> dict:
    passing = [t for t, r in by_tau.items() if r["gate_pass"]]
    if not passing:
        return {
            "selection_passed": False,
            "tau": None,
            "reason": "no_tau_passed_dev_gates",
        }
    tau = max(passing)
    return {
        "selection_passed": True,
        "tau": tau,
        "reason": "largest_tau_passing_recall_burden_occupancy",
    }


def main() -> int:
    digest = verify_frozen_hash(ROOT / "outputs" / "calibration" / "frozen_calibration.json")
    assert digest == REQUIRED_FROZEN_SHA256
    assert PROTOCOL.exists(), "protocol must exist before evaluation"

    scores = load_scores()
    F = subsample_hourly(load_flows_2018())
    L = subsample_hourly(load_levels_2018())["T1"]
    # align
    idx = scores["A"].index
    flows = F.reindex(idx)
    levels = L.reindex(idx)
    wn = load_nominal_wn()
    tank_area = float(np.pi * (wn.get_node("T1").diameter / 2.0) ** 2)

    dist = {m: {"DEV": score_distribution(scores[m], "DEV"), "DIAG": score_distribution(scores[m], "DIAG")} for m in scores}

    dev_tables: dict[str, dict] = {}
    selections: dict[str, dict] = {}

    for method, grid in TAU_GRID.items():
        print(f"DEV tradeoff method {method} grid={grid}", flush=True)
        by_tau = {}
        for tau in grid:
            r = evaluate_scores(
                scores[method],
                "DEV",
                tau=tau,
                flows=flows,
                levels=levels,
                tank_area_m2=tank_area,
                rng=np.random.default_rng(2018),
                n_nulls=50,
            )
            r["gate_pass"] = passes_gates(r)
            r["events_detail"] = event_diagnostics(scores[method], tau, "DEV")
            by_tau[tau] = r
            print(
                f"  τ={tau}: recall={r['abrupt_6h_recall']:.3f} "
                f"unm/wk={r['unmatched_per_week']:.3f} occ={r['occupancy']:.3f} "
                f"pass={r['gate_pass']}",
                flush=True,
            )
        sel = select_largest_passing(by_tau)
        selections[method] = sel
        dev_tables[method] = {
            "grid": list(grid),
            "selection": sel,
            "by_tau": {
                str(t): {
                    "tau": t,
                    "abrupt_6h_recall": by_tau[t]["abrupt_6h_recall"],
                    "unmatched_per_week": by_tau[t]["unmatched_per_week"],
                    "occupancy": by_tau[t]["occupancy"],
                    "n_hit": by_tau[t]["n_hit"],
                    "n_eligible_abrupt": by_tau[t]["n_eligible_abrupt"],
                    "n_notifications": by_tau[t]["n_notifications"],
                    "n_unmatched": by_tau[t]["n_unmatched"],
                    "gate_pass": by_tau[t]["gate_pass"],
                    "mean_delay_hours": by_tau[t]["mean_delay_hours"],
                    "events_detail": by_tau[t]["events_detail"],
                    "timing_nulls": by_tau[t]["timing_nulls"],
                    "unmatched_on_transition_frac": by_tau[t]["unmatched_on_transition_frac"],
                }
                for t in grid
            },
        }

    any_pass = any(selections[m]["selection_passed"] for m in selections)
    diag_results: dict[str, dict] = {}

    if any_pass:
        for method, sel in selections.items():
            if not sel["selection_passed"]:
                continue
            tau = float(sel["tau"])
            print(f"DIAG frozen {method} τ={tau}", flush=True)
            r = evaluate_scores(
                scores[method],
                "DIAG",
                tau=tau,
                flows=flows,
                levels=levels,
                tank_area_m2=tank_area,
                rng=np.random.default_rng(2018 + hash(method) % 1000),
                n_nulls=200,
            )
            r["events_detail"] = event_diagnostics(scores[method], tau, "DIAG")
            r["gate_pass_info_only"] = passes_gates({**r, "n_eligible_abrupt": r["n_eligible_abrupt"]})
            diag_results[method] = {
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
        print("SELECTION FAILED for all methods — no DIAG run.", flush=True)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "acknowledgement": (
            "2018 events have already been examined; all measured findings are diagnostic."
        ),
        "frozen_calibration_sha256": digest,
        "pump_boundary": "measured_pump1",
        "score_source": "outputs/detection_2018_measured_pump1/score_*.csv",
        "gates": {
            "abrupt_6h_recall_min": GATE_RECALL,
            "unmatched_per_week_max": GATE_UNMATCHED_PER_WEEK,
            "occupancy_max": OCCUPANCY_MAX,
        },
        "tau_grid_registered": {m: list(g) for m, g in TAU_GRID.items()},
        "score_distributions": dist,
        "dev": dev_tables,
        "selection": selections,
        "any_selection_passed": any_pass,
        "diag": diag_results if any_pass else None,
        "diag_skipped_reason": None if any_pass else "no_method_passed_dev_gates_no_fallback",
    }
    (OUT / "operating_point_results.json").write_text(json.dumps(payload, indent=2) + "\n")

    # Markdown
    lines = [
        "# Measured-PUMP_1 operating-point evaluation (DEV selection)",
        "",
        f"Protocol: [`OPERATING_POINT_PROTOCOL.md`](OPERATING_POINT_PROTOCOL.md) (registered before run).  ",
        f"Frozen calibration: `{digest}`  ",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "",
        payload["acknowledgement"],
        "",
        f"**Any method passed DEV gates:** `{any_pass}`",
        "",
        "Gates: recall ≥ 2/3, unmatched/week ≤ 3, **occupancy ≤ 0.20** "
        "(rejects permanently active detectors).",
        "",
        "## Score distributions (DEV, post-warmup)",
        "",
        "| Method | n | mean | p50 | p90 | p99 | max |",
        "|--------|--:|-----:|----:|----:|----:|----:|",
    ]
    for m in ("A", "B", "C"):
        d = dist[m]["DEV"]
        q = d["quantiles"]
        lines.append(
            f"| {m} | {d['n']} | {d['mean']:.3f} | {q['0.5']:.3f} | {q['0.9']:.3f} | "
            f"{q['0.99']:.3f} | {d['max']:.3f} |"
        )

    lines.extend(["", "## DEV tradeoff (registered quantile grid)", ""])
    for m in ("A", "B", "C"):
        label = {"A": "Σq_v change", "B": "vector ‖Δq_v‖₂", "C": "inflow baseline |ΔQ_ext|"}[m]
        lines.append(f"### Method {m} ({label})")
        lines.append("")
        lines.append(
            "| τ | recall | unmatched/wk | occupancy | n_hit/n_ev | n_notif | gate_pass |"
        )
        lines.append(
            "|--:|-------:|-------------:|----------:|-----------:|--------:|:---------:|"
        )
        for t in TAU_GRID[m]:
            r = dev_tables[m]["by_tau"][str(t)]
            lines.append(
                f"| {t} | {r['abrupt_6h_recall']} | {r['unmatched_per_week']:.3f} | "
                f"{r['occupancy']:.3f} | {r['n_hit']}/{r['n_eligible_abrupt']} | "
                f"{r['n_notifications']} | {r['gate_pass']} |"
            )
        sel = selections[m]
        lines.append("")
        lines.append(
            f"**Selection:** passed=`{sel['selection_passed']}` τ=`{sel.get('tau')}` "
            f"— {sel['reason']}"
        )
        lines.append("")
        # Event detail at selected or at each τ if failed — show at all τ for transparency
        lines.append("Event-level (each τ):")
        lines.append("")
        for t in TAU_GRID[m]:
            lines.append(f"- τ={t}:")
            for ev in dev_tables[m]["by_tau"][str(t)]["events_detail"]:
                lines.append(
                    f"  - {ev['pipe']}: hit={ev['hit']} delay={ev['delay_hours']} "
                    f"pre_onset_blocked={ev['pre_onset_blocked']} "
                    f"credit_max={ev['credit_max_score']}"
                )
        lines.append("")

    if any_pass:
        lines.extend(["## DIAG (frozen DEV settings only)", ""])
        lines.append(
            "| Method | τ | recall | mean delay h | unmatched/wk | occupancy | "
            "trans.frac | null recall mean |"
        )
        lines.append(
            "|--------|---:|-------:|-------------:|-------------:|----------:|"
            "----------:|-----------------:|"
        )
        for m, r in diag_results.items():
            tn = r["timing_nulls"]
            lines.append(
                f"| {m} | {r['tau']} | {r['abrupt_6h_recall']} | {r['mean_delay_hours']} | "
                f"{r['unmatched_per_week']:.3f} | {r['occupancy']:.3f} | "
                f"{r['unmatched_on_transition_frac']} | {tn.get('null_recall_mean')} |"
            )
        lines.append("")
        for m, r in diag_results.items():
            lines.append(f"### DIAG events — Method {m}")
            lines.append("")
            lines.append(
                "| Pipe | Hit | Delay h | Pre-onset blocked | Credit max |"
            )
            lines.append("|------|:---:|--------:|:-----------------:|-----------:|")
            for ev in r["events_detail"]:
                lines.append(
                    f"| {ev['pipe']} | {ev['hit']} | {ev['delay_hours']} | "
                    f"{ev['pre_onset_blocked']} | {ev['credit_max_score']} |"
                )
            lines.append("")
    else:
        lines.extend(
            [
                "## DIAG",
                "",
                "**Not run.** Selection failed for A, B, and C under the registered "
                "gates (including occupancy ≤ 0.20). No fallback DIAG by protocol.",
                "",
            ]
        )

    lines.extend(
        [
            "## Notes",
            "",
            "- Hourly dual limits notification timing to clock-hour granularity.",
            "- Method C is the external-inflow baseline (p227+p235 only).",
            "- No 2019 / new features / recalibration / recovery changes / UI / Tiger / main.",
            "",
        ]
    )
    (OUT / "OPERATING_POINT_RESULTS.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "OPERATING_POINT_RESULTS.md", flush=True)
    print(json.dumps({"any_selection_passed": any_pass, "selection": selections}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
