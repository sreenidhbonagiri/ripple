#!/usr/bin/env python3
"""Paired change-only feature ablation under episode-notification selection.

Preserves production, pilot artifacts, target-alignment, and episode_objective/.
No new simulations, labels, features, 2019, Tiger, UI, or main merge.
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

from ablation_arms import (
    PUMP_CHANGE_FEATURES,
    arm_a_names,
    arm_b_names,
    arm_registry,
    subset_X,
)
from dataset_build import build_split_tables
from episode_metrics import evaluate_split_episodes
from evaluate_measured import eval_period, run_supervised_on_measured
from features import feature_names as full_feature_names
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
ABL = OUT / "change_only_ablation"


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
    keep = {k: summary[k] for k in summary if k not in ("per_leak", "per_control")}
    keep["per_leak_brief"] = [
        {
            "scenario_id": r["scenario_id"],
            "pipe": r.get("pipe"),
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


def split_train_for_arm(tables: dict, keep: list[str]) -> dict:
    all_names = tables["feature_names"]
    tr = tables["splits"]["train"]
    return {
        "X": subset_X(tr["X"], all_names, keep),
        "y": tr["y"],
        "scenario_ids": tr["scenario_ids"],
        "n_rows": tr["n_rows"],
        "n_pos": tr["n_pos"],
    }


def coef_analysis(frozen: dict) -> dict:
    names = frozen.get("feature_names") or []
    coef = np.asarray(frozen["coef"], dtype=np.float64)
    if len(names) != len(coef):
        return {"error": "coef/name length mismatch"}
    abs_c = np.abs(coef)
    total = float(abs_c.sum()) or 1.0
    ranked = sorted(
        [
            {"name": n, "coef": float(c), "abs_coef": float(a), "share": float(a / total)}
            for n, c, a in zip(names, coef, abs_c)
        ],
        key=lambda r: -r["abs_coef"],
    )
    pump = [r for r in ranked if r["name"] in PUMP_CHANGE_FEATURES]
    pump_share = float(sum(r["abs_coef"] for r in pump) / total)
    return {
        "top10": ranked[:10],
        "pump_change_features": pump,
        "pump_change_abs_coef_share": pump_share,
        "still_exploits_pump_change": pump_share >= 0.10
        or any(r["name"] in PUMP_CHANGE_FEATURES for r in ranked[:5]),
    }


def verify_arm_a_vs_baseline(frozen_a: dict, baseline: dict) -> dict:
    sel_a = frozen_a["selected"]
    sel_b = baseline["selected"]
    dm_a = frozen_a["dev_metrics"]
    dm_b = baseline["dev_metrics"]
    checks = {
        "C_match": float(sel_a["C"]) == float(sel_b["C"]),
        "tau_match": float(sel_a["tau"]) == float(sel_b["tau"]),
        "gate_met_match": bool(frozen_a["gate_met"]) == bool(baseline["gate_met"]),
        "selection_failure_match": bool(frozen_a["selection_failure"])
        == bool(baseline["selection_failure"]),
        "dev_episode_6h_recall_match": abs(
            float(dm_a["episode_6h_recall"]) - float(dm_b["episode_6h_recall"])
        )
        < 1e-12,
        "dev_control_ep_per_week_match": abs(
            float(dm_a["control_episodes_per_week"])
            - float(dm_b["control_episodes_per_week"])
        )
        < 1e-9,
        "n_grid_match": len(frozen_a["grid_records"]) == len(baseline["grid_records"]),
    }
    # Coefficient closeness (same C refit)
    coef_a = np.asarray(frozen_a["coef"], dtype=np.float64)
    coef_b = np.asarray(baseline["coef"], dtype=np.float64)
    checks["coef_allclose"] = bool(
        coef_a.shape == coef_b.shape and np.allclose(coef_a, coef_b, rtol=1e-6, atol=1e-8)
    )
    checks["all_passed"] = all(checks.values())
    return checks


def paired_synth_leaks(a_brief, b_brief) -> list[dict]:
    by_b = {r["scenario_id"]: r for r in b_brief}
    rows = []
    for ra in a_brief:
        rb = by_b.get(ra["scenario_id"])
        if rb is None:
            continue
        hit_a = bool(ra["episode_6h_hit"])
        hit_b = bool(rb["episode_6h_hit"])
        if hit_a and hit_b:
            pair = "both_hit"
        elif (not hit_a) and (not hit_b):
            pair = "both_miss"
        elif hit_a and (not hit_b):
            pair = "A_hit_B_miss"  # regression for B
        else:
            pair = "A_miss_B_hit"  # gain for B
        rows.append(
            {
                "scenario_id": ra["scenario_id"],
                "pipe": ra.get("pipe"),
                "pair": pair,
                "A_hit": hit_a,
                "B_hit": hit_b,
                "A_delay_h": ra.get("delay_hours"),
                "B_delay_h": rb.get("delay_hours"),
                "A_blocked": ra.get("blocked_by_preonset_active"),
                "B_blocked": rb.get("blocked_by_preonset_active"),
                "A_row_credit": ra.get("row_credit_hit"),
                "B_row_credit": rb.get("row_credit_hit"),
            }
        )
    return rows


def paired_measured_abrupt(a_per, b_per) -> list[dict]:
    by_b = {(r["pipe"], r["onset"]): r for r in b_per}
    rows = []
    for ra in a_per:
        key = (ra["pipe"], ra["onset"])
        rb = by_b.get(key)
        if rb is None:
            continue
        ha = bool(ra.get("within_6h"))
        hb = bool(rb.get("within_6h"))
        if ha and hb:
            pair = "both_hit6"
        elif (not ha) and (not hb):
            pair = "both_miss6"
        elif ha and (not hb):
            pair = "A_hit6_B_miss6"
        else:
            pair = "A_miss6_B_hit6"
        rows.append(
            {
                "pipe": ra["pipe"],
                "onset": ra["onset"],
                "pair": pair,
                "A_within_6h": ha,
                "B_within_6h": hb,
                "A_delay_h": ra.get("delay_hours"),
                "B_delay_h": rb.get("delay_hours"),
                "A_matched": ra.get("matched"),
                "B_matched": rb.get("matched"),
            }
        )
    return rows


def interpret(doc: dict) -> dict:
    a = doc["arms"]["arm_A"]
    b = doc["arms"]["arm_B"]
    syn_a = a["synthetic_episode"]["synthetic_test"]
    syn_b = b["synthetic_episode"]["synthetic_test"]
    # Synthetic operating point: prefer higher episode recall then lower burden
    syn_improved = False
    syn_reason = []
    if syn_b["episode_6h_recall"] > syn_a["episode_6h_recall"] + 1e-12:
        syn_improved = True
        syn_reason.append("higher synth-test episode_6h_recall")
    elif syn_b["episode_6h_recall"] + 1e-12 < syn_a["episode_6h_recall"]:
        syn_reason.append("lower synth-test episode_6h_recall")
    else:
        syn_reason.append("equal synth-test episode_6h_recall")
    if syn_b["control_episodes_per_week"] + 1e-12 < syn_a["control_episodes_per_week"]:
        syn_reason.append("lower synth-test control ep/wk")
        if abs(syn_b["episode_6h_recall"] - syn_a["episode_6h_recall"]) <= 1e-12:
            syn_improved = True
    elif syn_b["control_episodes_per_week"] > syn_a["control_episodes_per_week"] + 1e-12:
        syn_reason.append("higher synth-test control ep/wk")
        syn_improved = False if syn_b["episode_6h_recall"] <= syn_a["episode_6h_recall"] + 1e-12 else syn_improved

    m_dev_a = a["measured"]["supervised"]["DEV"]["abrupt_6h"]["recall"]
    m_dev_b = b["measured"]["supervised"]["DEV"]["abrupt_6h"]["recall"]
    m_diag_a = a["measured"]["supervised"]["DIAG"]["abrupt_6h"]["recall"]
    m_diag_b = b["measured"]["supervised"]["DIAG"]["abrupt_6h"]["recall"]
    um_dev_a = a["measured"]["supervised"]["DEV"]["unmatched_per_week"]
    um_dev_b = b["measured"]["supervised"]["DEV"]["unmatched_per_week"]
    um_diag_a = a["measured"]["supervised"]["DIAG"]["unmatched_per_week"]
    um_diag_b = b["measured"]["supervised"]["DIAG"]["unmatched_per_week"]

    # Transfer: both periods matter; one DIAG bump alone is insufficient
    transfer_improved = (
        (m_dev_b > m_dev_a + 1e-12 or m_diag_b > m_diag_a + 1e-12)
        and not (m_dev_b + 1e-12 < m_dev_a and m_diag_b + 1e-12 < m_diag_a)
    )
    # Stricter: require non-worsening on both and improvement on at least one,
    # plus burden not exploding
    transfer_strict = (
        m_dev_b + 1e-12 >= m_dev_a
        and m_diag_b + 1e-12 >= m_diag_a
        and (m_dev_b > m_dev_a + 1e-12 or m_diag_b > m_diag_a + 1e-12)
        and um_dev_b <= um_dev_a * 1.25 + 1e-9
        and um_diag_b <= um_diag_a * 1.25 + 1e-9
    )
    return {
        "a_synthetic_operating_point_improved": syn_improved,
        "a_synthetic_notes": "; ".join(syn_reason),
        "b_measured_transfer_improved_strict": transfer_strict,
        "b_measured_notes": (
            f"DEV abrupt6h A={m_dev_a} B={m_dev_b}; DIAG A={m_diag_a} B={m_diag_b}; "
            f"unmatched/wk DEV A={um_dev_a:.4g} B={um_dev_b:.4g}; "
            f"DIAG A={um_diag_a:.4g} B={um_diag_b:.4g}. "
            "One favorable DIAG recall alone does not establish transfer improvement."
        ),
        "loose_any_period_recall_up": transfer_improved,
    }


def render(doc: dict) -> str:
    reg = doc["arm_registry"]
    lines = [
        "# Change-only feature ablation (episode-notification objective)",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "**Question:** Does removing absolute operating-state features improve "
        "synthetic-to-measured transfer under the same episode-notification objective?",
        "",
        "Preserves production, prior reports, and `outputs/episode_objective/`. "
        "No new simulations, labels, features, 2019, Tiger, UI, or main merge.",
        "",
        "## Registered arms (before fit)",
        "",
        f"- Arm A: {reg['arm_A']['n_features']} features — `{reg['arm_A']['label']}`",
        f"- Arm B: {reg['arm_B']['n_features']} features — `{reg['arm_B']['label']}`",
        f"- Removed in B: {reg['arm_B']['removed']}",
        "",
        "Selection rule (both arms):",
        "",
        doc["selection_rule"],
        "",
        f"Arm A vs episode-objective baseline: "
        f"**{'PASS' if doc['arm_A_baseline_check']['all_passed'] else 'FAIL'}** "
        f"`{doc['arm_A_baseline_check']}`",
        "",
        "## Side-by-side headline (episode metrics)",
        "",
        "| Metric | Arm A | Arm B |",
        "|--------|-------|-------|",
    ]

    def row(label, va, vb):
        lines.append(f"| {label} | {va} | {vb} |")

    a, b = doc["arms"]["arm_A"], doc["arms"]["arm_B"]
    row(
        "Selected (C, τ)",
        f"{a['frozen']['selected']['C']}, {a['frozen']['selected']['tau']}",
        f"{b['frozen']['selected']['C']}, {b['frozen']['selected']['tau']}",
    )
    row("gate_met", a["frozen"]["gate_met"], b["frozen"]["gate_met"])
    row(
        "selection_failure",
        a["frozen"]["selection_failure"],
        b["frozen"]["selection_failure"],
    )
    for split in ("synthetic_dev", "synthetic_test"):
        sa = a["synthetic_episode"][split]
        sb = b["synthetic_episode"][split]
        row(
            f"{split} episode_6h",
            f"{sa['episode_6h_recall']:.4g} ({sa['n_episode_6h_hit']}/{sa['n_leak_scenarios']})",
            f"{sb['episode_6h_recall']:.4g} ({sb['n_episode_6h_hit']}/{sb['n_leak_scenarios']})",
        )
        row(
            f"{split} median_delay_h",
            sa["median_delay_h"],
            sb["median_delay_h"],
        )
        row(
            f"{split} ctrl ep/wk",
            f"{sa['control_episodes_per_week']:.4g}",
            f"{sb['control_episodes_per_week']:.4g}",
        )
        row(
            f"{split} blocked_preonset",
            sa["n_blocked_by_preonset_active"],
            sb["n_blocked_by_preonset_active"],
        )
        row(
            f"{split} row_credit scen (side)",
            f"{sa['row_credit_scenario_recall']:.4g}",
            f"{sb['row_credit_scenario_recall']:.4g}",
        )

    for period in ("DEV", "DIAG"):
        ma = a["measured"]["supervised"][period]
        mb = b["measured"]["supervised"][period]
        row(
            f"measured {period} abrupt6h",
            f"{ma['abrupt_6h']['recall']} ({ma['abrupt_6h']['n_hit']}/{ma['abrupt_6h']['n_abrupt']})",
            f"{mb['abrupt_6h']['recall']} ({mb['abrupt_6h']['n_hit']}/{mb['abrupt_6h']['n_abrupt']})",
        )
        row(
            f"measured {period} delays_h",
            ma["abrupt_6h"]["delays"],
            mb["abrupt_6h"]["delays"],
        )
        row(
            f"measured {period} unmatched/wk",
            f"{ma['unmatched_per_week']:.4g}",
            f"{mb['unmatched_per_week']:.4g}",
        )
        row(
            f"measured {period} dup24h",
            ma["duplicate_unmatched_within_24h"],
            mb["duplicate_unmatched_within_24h"],
        )
        row(
            f"measured {period} union alarm %",
            f"{ma['occupancy']['union_alarm_pct_of_analysis']:.4g}",
            f"{mb['occupancy']['union_alarm_pct_of_analysis']:.4g}",
        )

    lines += [
        "",
        "## Coefficient / pump-change shortcut check",
        "",
    ]
    for arm_id in ("arm_A", "arm_B"):
        ca = doc["arms"][arm_id]["coef_analysis"]
        lines.append(
            f"### {arm_id}: pump_change_abs_share={ca['pump_change_abs_coef_share']:.4g}; "
            f"still_exploits_pump_change={ca['still_exploits_pump_change']}"
        )
        lines.append("")
        lines.append("| rank | feature | coef | share |")
        lines.append("|------|---------|------|-------|")
        for i, r in enumerate(ca["top10"], 1):
            lines.append(
                f"| {i} | `{r['name']}` | {r['coef']:.4g} | {r['share']:.4g} |"
            )
        lines.append("")

    lines += [
        "## Paired synthetic-test leak outcomes",
        "",
    ]
    counts = {}
    for r in doc["paired_synthetic_test"]:
        counts[r["pair"]] = counts.get(r["pair"], 0) + 1
        lines.append(
            f"- {r['pair']} `{r['scenario_id']}` "
            f"A_delay={r['A_delay_h']} B_delay={r['B_delay_h']} "
            f"blocked A/B={r['A_blocked']}/{r['B_blocked']}"
        )
    lines += ["", f"Pair counts: `{counts}`", ""]

    lines += ["## Paired measured abrupt 6h outcomes", ""]
    for period in ("DEV", "DIAG"):
        lines.append(f"### {period}")
        lines.append("")
        pc = {}
        for r in doc["paired_measured"][period]:
            pc[r["pair"]] = pc.get(r["pair"], 0) + 1
            lines.append(
                f"- {r['pair']} {r['pipe']} onset={r['onset']} "
                f"A_delay={r['A_delay_h']} B_delay={r['B_delay_h']}"
            )
        lines += ["", f"Counts: `{pc}`", ""]

    itp = doc["interpretation"]
    lines += [
        "## Interpretation (separate claims)",
        "",
        f"**(a) Synthetic operating point improved?** "
        f"**{itp['a_synthetic_operating_point_improved']}** — {itp['a_synthetic_notes']}",
        "",
        f"**(b) Measured transfer improved (strict)?** "
        f"**{itp['b_measured_transfer_improved_strict']}** — {itp['b_measured_notes']}",
        "",
        f"Loose any-period recall up (not sufficient alone): "
        f"{itp['loose_any_period_recall_up']}",
        "",
        "## Non-goals",
        "",
        "- No main merge, Tiger, UI, deployment",
        "- No new simulations or model families",
        "- Episode-objective artifacts preserved",
        "",
    ]
    return "\n".join(lines)


def run_arm(
    arm_id: str,
    keep: list[str],
    label: str,
    tables: dict,
    manifest: dict,
    assignments: dict,
    measured: dict,
    leakages,
) -> dict:
    print(f"=== {arm_id}: fit + select ({len(keep)} feats) ===", flush=True)
    train = split_train_for_arm(tables, keep)
    t0 = time.perf_counter()
    frozen = fit_select_episode(
        train,
        SIM_DIR,
        manifest,
        assignments,
        feature_names=keep,
        feature_set_label=label,
    )
    frozen["frozen_at"] = iso_now()
    frozen["arm_id"] = arm_id
    print(
        f"{arm_id}: C={frozen['selected']['C']} tau={frozen['selected']['tau']} "
        f"gate_met={frozen['gate_met']} failure={frozen['selection_failure']} "
        f"({time.perf_counter()-t0:.1f}s)",
        flush=True,
    )

    syn_ep = {}
    for split in ("synthetic_dev", "synthetic_test"):
        raw = evaluate_split_episodes(
            SIM_DIR, manifest, assignments, split, frozen
        )
        syn_ep[split] = slim_episode_eval(raw)
        print(
            f"{arm_id} {split}: ep6h={syn_ep[split]['episode_6h_recall']} "
            f"ctrl/wk={syn_ep[split]['control_episodes_per_week']}",
            flush=True,
        )

    # Row-table side metrics on subsetted split matrices
    syn_row = {}
    all_names = tables["feature_names"]
    for split_name in ("synthetic_dev", "synthetic_test"):
        sp = tables["splits"][split_name]
        syn_row[split_name] = evaluate_synthetic_split(
            frozen,
            {
                "X": subset_X(sp["X"], all_names, keep),
                "y": sp["y"],
                "scenario_ids": sp["scenario_ids"],
                "n_rows": sp["n_rows"],
            },
        )

    print(f"=== {arm_id}: measured 2018 diagnostic ===", flush=True)
    episodes, q = run_supervised_on_measured(frozen, measured)
    np.savez_compressed(ABL / f"{arm_id}_measured_2018_scores.npz", q=q)
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
            label=f"change_only_{arm_id}",
        )
        print(
            f"{arm_id} measured {name} abrupt6h="
            f"{measured_out['supervised'][name]['abrupt_6h']['recall']}",
            flush=True,
        )

    return {
        "frozen": frozen,
        "coef_analysis": coef_analysis(frozen),
        "synthetic_episode": syn_ep,
        "synthetic_row_table": syn_row,
        "measured": measured_out,
    }


def main() -> int:
    ABL.mkdir(parents=True, exist_ok=True)
    # Persist registry before any fit
    registry = arm_registry()
    (ABL / "arm_registry.json").write_text(
        json.dumps(_jsonable(registry), indent=2) + "\n"
    )

    print("=== Tests ===", flush=True)
    import pytest

    tr = pytest.main([str(ROOT / "tests"), "-q"])
    if tr != 0:
        print("TESTS FAILED — abort", flush=True)
        return 1

    if not (SIM_DIR / "scenario_manifest.json").exists():
        print("Missing synthetic scenarios", flush=True)
        return 1
    if not (EO / "frozen_model.json").exists():
        print("Missing episode-objective baseline freeze", flush=True)
        return 1

    baseline = json.loads((EO / "frozen_model.json").read_text())
    tables = build_split_tables(SIM_DIR)
    manifest = json.loads((SIM_DIR / "scenario_manifest.json").read_text())
    assignments = tables["split_info"]["assignments"]
    assert tables["feature_names"] == full_feature_names()

    print("=== Load measured 2018 (shared) ===", flush=True)
    measured = load_measured_2018(DEFAULT_RAW)
    leakages = load_leakages()

    print(f"RULE: {SELECTION_RULE}", flush=True)
    arm_A = run_arm(
        "arm_A",
        arm_a_names(),
        "pressure_context_v1",
        tables,
        manifest,
        assignments,
        measured,
        leakages,
    )
    check = verify_arm_a_vs_baseline(arm_A["frozen"], baseline)
    print(f"Arm A baseline check: {check}", flush=True)
    if not check["all_passed"]:
        print("Arm A failed to reproduce episode-objective baseline — abort", flush=True)
        (ABL / "arm_A_baseline_check_FAILED.json").write_text(
            json.dumps(_jsonable({"check": check, "frozen": arm_A["frozen"]}), indent=2)
            + "\n"
        )
        return 1

    arm_B = run_arm(
        "arm_B",
        arm_b_names(),
        "change_residual_only_v1",
        tables,
        manifest,
        assignments,
        measured,
        leakages,
    )

    # Persist per-arm freezes
    for arm_id, arm in (("arm_A", arm_A), ("arm_B", arm_B)):
        (ABL / f"{arm_id}_frozen_model.json").write_text(
            json.dumps(_jsonable(arm["frozen"]), indent=2) + "\n"
        )
        (ABL / f"{arm_id}_dev_grid.json").write_text(
            json.dumps(_jsonable(arm["frozen"]["grid_records"]), indent=2) + "\n"
        )
        (ABL / f"{arm_id}_synthetic_episode_eval.json").write_text(
            json.dumps(_jsonable(arm["synthetic_episode"]), indent=2) + "\n"
        )
        (ABL / f"{arm_id}_measured_2018_eval.json").write_text(
            json.dumps(_jsonable(arm["measured"]), indent=2) + "\n"
        )

    paired_syn = paired_synth_leaks(
        arm_A["synthetic_episode"]["synthetic_test"]["per_leak_brief"],
        arm_B["synthetic_episode"]["synthetic_test"]["per_leak_brief"],
    )
    paired_meas = {
        period: paired_measured_abrupt(
            arm_A["measured"]["supervised"][period]["abrupt_6h"]["per_event"],
            arm_B["measured"]["supervised"][period]["abrupt_6h"]["per_event"],
        )
        for period in ("DEV", "DIAG")
    }

    doc = {
        "generated_at": iso_now(),
        "experiment": "change_only_ablation_episode_objective",
        "tests": "passed",
        "selection_rule": SELECTION_RULE,
        "arm_registry": registry,
        "arm_A_baseline_check": check,
        "raw_pressure_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "scenarios_reused": True,
        "preserves": [
            "outputs/pilot_*",
            "outputs/PILOT_RESULTS.md",
            "outputs/TARGET_ALIGNMENT_BEFORE_ABLATION.md",
            "outputs/TRANSFER_FAILURE_DIAGNOSIS.md",
            "outputs/episode_objective/",
        ],
        "arms": {"arm_A": arm_A, "arm_B": arm_B},
        "paired_synthetic_test": paired_syn,
        "paired_measured": paired_meas,
    }
    # Strip bulky coef arrays from summary arms — already in frozen files
    for arm in doc["arms"].values():
        fr = dict(arm["frozen"])
        fr.pop("coef", None)
        fr.pop("scaler_mean", None)
        fr.pop("scaler_scale", None)
        # keep grid in separate files; slim summary
        fr["grid_records"] = [
            {
                k: r[k]
                for k in (
                    "C",
                    "tau",
                    "episode_6h_recall",
                    "control_episodes_per_week",
                    "median_delay_h",
                    "row_credit_scenario_recall",
                    "n_blocked_by_preonset_active",
                    "gate_met",
                )
            }
            for r in fr.get("grid_records", [])
        ]
        arm["frozen"] = fr

    doc["interpretation"] = interpret(doc)
    (ABL / "summary.json").write_text(json.dumps(_jsonable(doc), indent=2) + "\n")
    (ABL / "CHANGE_ONLY_ABLATION_RESULTS.md").write_text(render(doc) + "\n")
    print(json.dumps(doc["interpretation"], indent=2), flush=True)
    print(f"Wrote {ABL / 'CHANGE_ONLY_ABLATION_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
