#!/usr/bin/env python3
"""Objective-alignment pilot: select on episode-notification DEV metrics.

Preserves original pilot_* artifacts and TARGET_ALIGNMENT_BEFORE_ABLATION.
No new simulations, feature ablation, 2019, Tiger, UI, or main merge.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dataset_build import build_split_tables
from episode_metrics import evaluate_split_episodes
from evaluate_measured import eval_period, run_supervised_on_measured
from features import feature_manifest
from io_measured import load_measured_2018
from schema import DEFAULT_RAW
from train_episode_objective import SELECTION_RULE, fit_select_episode
from train_pilot import evaluate_synthetic_split

CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))
from evaluate import DEV, DIAG, period_indices  # noqa: E402
from io_data import load_leakages  # noqa: E402

OUT = ROOT / "outputs"
SIM_DIR = OUT / "synthetic_scenarios"
EO = OUT / "episode_objective"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if o is None or isinstance(o, (str, bool, int, float)):
        return o
    return str(o)


def slim_episode_eval(summary: dict) -> dict:
    """Keep headline + diagnostics; drop bulky episode lists for markdown."""
    keep = {
        k: summary[k]
        for k in summary
        if k not in ("per_leak", "per_control")
    }
    keep["per_leak_brief"] = [
        {
            "scenario_id": r["scenario_id"],
            "episode_6h_hit": r.get("episode_6h_hit"),
            "row_credit_hit": r.get("row_credit_hit"),
            "delay_hours": r.get("delay_hours"),
            "blocked_by_preonset_active": r.get("blocked_by_preonset_active"),
            "n_episodes": r.get("n_episodes"),
            "preonset_notifies": r.get("preonset_notifies"),
        }
        for r in summary.get("per_leak", [])
    ]
    keep["per_control_brief"] = [
        {
            "scenario_id": r["scenario_id"],
            "kind": r.get("kind"),
            "n_episodes": r.get("n_episodes"),
        }
        for r in summary.get("per_control", [])
    ]
    return keep


def render(doc: dict) -> str:
    fr = doc["frozen"]
    lines = [
        "# Episode-objective alignment pilot",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Corrects the **model/threshold selection objective** to match measured "
        "six-hour **episode-notification** semantics. Same scenarios, splits, "
        "features, labels, preprocessing, and L2 logistic family as the original "
        "synthetic pilot.",
        "",
        "**Preserves** original `pilot_*` artifacts and "
        "`TARGET_ALIGNMENT_BEFORE_ABLATION.md`. **Not** a feature ablation; "
        "**no** new simulations; **no** 2019.",
        "",
        "## Labels (unchanged)",
        "",
        doc["label_note"],
        "",
        "## Selection rule (declared before run)",
        "",
        fr["selection_rule"],
        "",
        f"- Gates: episode_6h_recall ≥ {fr['gates']['episode_6h_recall_min']:g}; "
        f"control_episodes_per_week ≤ {fr['gates']['control_episodes_per_week_max']:g}",
        f"- Budget: C∈{fr['budget']['C_grid']}, τ∈{fr['budget']['tau_grid']}",
        f"- Tests: {doc['tests']}",
        "",
        "## DEV grid (all attempted settings)",
        "",
        "| C | τ | ep6h recall | ctrl ep/wk | med delay h | row scen | "
        "blocked | disagree | gates |",
        "|---|---|-------------|------------|-------------|----------|"
        "---------|----------|-------|",
    ]
    for r in fr["grid_records"]:
        gate = "PASS" if r["gate_met"] else "fail"
        lines.append(
            f"| {r['C']} | {r['tau']} | {r['episode_6h_recall']:.4g} | "
            f"{r['control_episodes_per_week']:.4g} | {r['median_delay_h']} | "
            f"{r['row_credit_scenario_recall']:.4g} | "
            f"{r['n_blocked_by_preonset_active']} | "
            f"{r['n_row_vs_episode_disagree']} | {gate} |"
        )
    lines += [
        "",
        "## Freeze",
        "",
        f"- Selected: **C={fr['selected']['C']}, τ={fr['selected']['tau']}**",
        f"- gate_met: **{fr['gate_met']}**",
        f"- selection_failure: **{fr['selection_failure']}**",
        f"- DEV episode_6h_recall: {fr['dev_metrics']['episode_6h_recall']}",
        f"- DEV control_episodes_per_week: "
        f"{fr['dev_metrics']['control_episodes_per_week']}",
        f"- DEV median_delay_h: {fr['dev_metrics']['median_delay_h']}",
        "",
    ]
    if fr["selection_failure"]:
        lines += [
            "**Selection failure:** no candidate met both provisional gates. "
            "Rank-best under the declared ordering was frozen with `gate_met=false` "
            "for diagnostic follow-through only — not a claim of success.",
            "",
        ]

    lines += [
        "## Synthetic evaluation (episode headline; row-credit for discrepancy)",
        "",
        "Synthetic metrics are **not** combined with measured accuracy.",
        "",
        "| Split | episode_6h | row_credit scen | med delay h | "
        "ctrl ep/wk | blocked | disagree |",
        "|-------|------------|-----------------|-------------|"
        "------------|---------|----------|",
    ]
    for name in ("synthetic_dev", "synthetic_test"):
        m = doc["synthetic_episode"][name]
        lines.append(
            f"| {name} | {m['episode_6h_recall']:.4g} "
            f"({m['n_episode_6h_hit']}/{m['n_leak_scenarios']}) | "
            f"{m['row_credit_scenario_recall']:.4g} | {m['median_delay_h']} | "
            f"{m['control_episodes_per_week']:.4g} | "
            f"{m['n_blocked_by_preonset_active']} | "
            f"{m['n_row_vs_episode_disagree']} |"
        )
    # Original row-table metrics for transparency
    lines += [
        "",
        "Original row-table metrics at frozen (C,τ) (not selection objective):",
        "",
    ]
    for name in ("synthetic_dev", "synthetic_test"):
        m = doc["synthetic_row_table"][name]
        if m.get("empty"):
            lines.append(f"- {name}: empty")
        else:
            lines.append(
                f"- {name}: scenario_recall(row)={m.get('scenario_recall')}, "
                f"row_recall={m.get('row_recall')}, fp_row_rate={m.get('fp_row_rate')}"
            )

    lines += [
        "",
        "### Synthetic test per-leak",
        "",
    ]
    for r in doc["synthetic_episode"]["synthetic_test"]["per_leak_brief"]:
        tag = "HIT6" if r["episode_6h_hit"] else "MISS"
        lines.append(
            f"- {tag} {r['scenario_id']} delay_h={r['delay_hours']} "
            f"row_credit={r['row_credit_hit']} blocked={r['blocked_by_preonset_active']} "
            f"n_ep={r['n_episodes']} preonset={r['preonset_notifies']}"
        )

    lines += [
        "",
        "## Measured 2018 (diagnostic — no retune; prior examination)",
        "",
        "Same notifier as synthetic. Headline = abrupt 6h episode notification. "
        "Not combined with synthetic figures into one accuracy.",
        "",
    ]
    for period in ("DEV", "DIAG"):
        s = doc["measured"]["supervised"][period]
        a6 = s["abrupt_6h"]
        lines += [
            f"### {period}",
            "",
            f"- Eligible onsets: {s['n_eligible_onsets']}",
            f"- Abrupt 6h recall: **{a6['recall']}** "
            f"({a6['n_hit']}/{a6['n_abrupt']})",
            f"- Delays (h): {a6['delays']}",
            f"- Episodes: {s['n_episodes']}; unmatched/wk: "
            f"{s['unmatched_per_week']:.4g}; "
            f"dup24h unmatched: {s['duplicate_unmatched_within_24h']}",
            f"- Occupancy union%: "
            f"{s['occupancy']['union_alarm_pct_of_analysis']:.4g}",
            "",
            "Per abrupt event:",
            "",
        ]
        for row in a6["per_event"]:
            tag = (
                "HIT6"
                if row["within_6h"]
                else ("HIT>6" if row["matched"] else "MISS")
            )
            lines.append(
                f"- {tag} {row['pipe']} delay_h={row['delay_hours']} "
                f"notify={row['notify_time']}"
            )
        lines += ["", "Misses (all types):", ""]
        for m in s["misses"]:
            lines.append(
                f"- MISS {m['pipe']} ({m['leak_type']}) onset={m['onset']}"
            )
        lines.append("")

    lines += [
        "## Diagnosis",
        "",
        doc["diagnosis"],
        "",
        "## Non-goals",
        "",
        "- No feature ablation, new simulations, or 2019",
        "- No main merge, Tiger, UI, deployment",
        "- Original row-hit pilot remains archived baseline",
        "",
    ]
    return "\n".join(lines)


def diagnose(doc: dict) -> str:
    fr = doc["frozen"]
    st = doc["synthetic_episode"]["synthetic_test"]
    m_dev = doc["measured"]["supervised"]["DEV"]["abrupt_6h"]
    m_diag = doc["measured"]["supervised"]["DIAG"]["abrupt_6h"]
    parts = [
        f"Selection gate_met={fr['gate_met']} selection_failure={fr['selection_failure']} "
        f"frozen C={fr['selected']['C']} τ={fr['selected']['tau']}.",
        f"Synthetic test episode_6h_recall={st['episode_6h_recall']} "
        f"vs row_credit_scenario_recall={st['row_credit_scenario_recall']} "
        f"(disagree scenarios={st['n_row_vs_episode_disagree']}; "
        f"blocked_preonset={st['n_blocked_by_preonset_active']}).",
        f"Measured abrupt6h DEV={m_dev['recall']} DIAG={m_diag['recall']} "
        f"(diagnostic only; not retuned).",
    ]
    if st["n_row_vs_episode_disagree"] > 0 or (
        abs(st["episode_6h_recall"] - st["row_credit_scenario_recall"]) > 1e-9
    ):
        parts.append(
            "Row-credit vs episode-notification discrepancy is present under the "
            "shared notifier — selection now targets the episode objective."
        )
    if fr["selection_failure"]:
        parts.append(
            "No grid point met provisional gates; frozen candidate is rank-best "
            "without gates and must not be read as a successful gate pass."
        )
    return " ".join(parts)


def main() -> int:
    EO.mkdir(parents=True, exist_ok=True)
    print("=== Tests ===", flush=True)
    import pytest

    tr = pytest.main([str(ROOT / "tests"), "-q"])
    if tr != 0:
        print("TESTS FAILED — abort", flush=True)
        return 1

    if not (SIM_DIR / "scenario_manifest.json").exists():
        print("Missing synthetic scenarios — refuse to resimulate", flush=True)
        return 1

    print("=== Build tables (reuse scenarios) ===", flush=True)
    tables = build_split_tables(SIM_DIR)
    manifest = json.loads((SIM_DIR / "scenario_manifest.json").read_text())
    assignments = tables["split_info"]["assignments"]

    print("=== Fit + episode DEV selection ===", flush=True)
    print(f"RULE: {SELECTION_RULE}", flush=True)
    t0 = time.perf_counter()
    frozen = fit_select_episode(
        tables["splits"]["train"], SIM_DIR, manifest, assignments
    )
    frozen["frozen_at"] = iso_now()
    frozen["feature_names"] = tables["feature_names"]
    print(
        f"Selected C={frozen['selected']['C']} tau={frozen['selected']['tau']} "
        f"gate_met={frozen['gate_met']} failure={frozen['selection_failure']} "
        f"in {time.perf_counter()-t0:.1f}s",
        flush=True,
    )
    (EO / "frozen_model.json").write_text(json.dumps(_jsonable(frozen), indent=2) + "\n")
    (EO / "dev_grid.json").write_text(
        json.dumps(_jsonable(frozen["grid_records"]), indent=2) + "\n"
    )

    print("=== Synthetic test (episode) ===", flush=True)
    syn_ep = {}
    for split in ("synthetic_dev", "synthetic_test"):
        raw = evaluate_split_episodes(
            SIM_DIR, manifest, assignments, split, frozen
        )
        syn_ep[split] = slim_episode_eval(raw)
        print(
            f"{split}: ep6h={syn_ep[split]['episode_6h_recall']} "
            f"row={syn_ep[split]['row_credit_scenario_recall']} "
            f"ctrl/wk={syn_ep[split]['control_episodes_per_week']}",
            flush=True,
        )
    (EO / "synthetic_episode_eval.json").write_text(
        json.dumps(_jsonable(syn_ep), indent=2) + "\n"
    )

    syn_row = {
        "synthetic_dev": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_dev"]
        ),
        "synthetic_test": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_test"]
        ),
    }
    (EO / "synthetic_row_table_eval.json").write_text(
        json.dumps(_jsonable(syn_row), indent=2) + "\n"
    )

    print("=== Measured 2018 diagnostic ===", flush=True)
    measured = load_measured_2018(DEFAULT_RAW)
    episodes, q = run_supervised_on_measured(frozen, measured)
    np.savez_compressed(EO / "measured_2018_scores.npz", q=q)
    leakages = load_leakages()
    measured_out = {"supervised": {}}
    for period, name in ((DEV, "DEV"), (DIAG, "DIAG")):
        g0, g1 = period_indices(measured["timestamps"], period)
        measured_out["supervised"][name] = eval_period(
            measured["timestamps"],
            episodes,
            leakages,
            period,
            analysis_start=g0,
            analysis_end=g1,
            n_sensors=1,
            label="episode_objective_supervised",
        )
        print(
            f"Measured {name} abrupt6h="
            f"{measured_out['supervised'][name]['abrupt_6h']['recall']}",
            flush=True,
        )
    (EO / "measured_2018_eval.json").write_text(
        json.dumps(_jsonable(measured_out), indent=2) + "\n"
    )

    doc = {
        "generated_at": iso_now(),
        "experiment": "episode_objective_alignment",
        "tests": "passed",
        "feature_manifest": feature_manifest(),
        "raw_pressure_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "scenarios_reused": True,
        "splits": tables["split_info"],
        "label_note": frozen["label_note"],
        "frozen": {
            "selected": frozen["selected"],
            "gate_met": frozen["gate_met"],
            "selection_failure": frozen["selection_failure"],
            "selection_rule": frozen["selection_rule"],
            "gates": frozen["gates"],
            "budget": frozen["budget"],
            "dev_metrics": frozen["dev_metrics"],
            "grid_records": frozen["grid_records"],
            "n_train": frozen["n_train"],
            "n_train_pos": frozen["n_train_pos"],
        },
        "synthetic_episode": syn_ep,
        "synthetic_row_table": syn_row,
        "measured": measured_out,
        "preserves": [
            "outputs/pilot_frozen_model.json",
            "outputs/pilot_summary.json",
            "outputs/PILOT_RESULTS.md",
            "outputs/TARGET_ALIGNMENT_BEFORE_ABLATION.md",
            "outputs/synthetic_scenarios/",
        ],
        "holdout_honesty": (
            "2018 measured evaluation is diagnostic (events previously examined). "
            "Synthetic and measured metrics are not combined into one accuracy."
        ),
    }
    doc["diagnosis"] = diagnose(doc)
    (EO / "summary.json").write_text(json.dumps(_jsonable(doc), indent=2) + "\n")
    (EO / "EPISODE_OBJECTIVE_RESULTS.md").write_text(render(doc) + "\n")
    print(doc["diagnosis"], flush=True)
    print(f"Wrote {EO / 'EPISODE_OBJECTIVE_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
