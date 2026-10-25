#!/usr/bin/env python3
"""Phase-correction experiment: randomized pattern origin + independent onset.

Preserves original synthetic_scenarios/ and all prior reports.
Synthetic DEV select → freeze → synthetic test only. No measured evaluation.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from features import build_feature_matrix as _bfm, feature_manifest
from schema import DEFAULT_INP, FEATURE_CONFIG, STEPS_PER_HOUR
from simulate import DURATION_HOURS
from simulate_phase import PHASE_MASTER_SEED, run_all_phase_scenarios
from splits_phase import assign_splits_phase
from train_episode_objective import SELECTION_RULE, fit_select_episode
from train_pilot import evaluate_synthetic_split
from episode_metrics import (
    SCENARIO_WEEKS,
    analyze_control_scenario,
    analyze_leak_scenario,
    score_full_trajectory,
)
from notifications import RECOVER_STEPS, episodes_from_scores
from verify_phase_distributions import verify_phase_onset_distributions

OUT = ROOT / "outputs"
ORIG_SIM = OUT / "synthetic_scenarios"
SIM_DIR = OUT / "synthetic_scenarios_phase"
PC = OUT / "phase_correction"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def build_split_tables_phase(sim_dir: Path) -> dict:
    """Like dataset_build.build_split_tables but uses assign_splits_phase."""
    from features import feature_manifest as fm

    manifest = json.loads((sim_dir / "scenario_manifest.json").read_text())
    split_info = assign_splits_phase(manifest)
    warm = FEATURE_CONFIG.warm_up_steps
    scenario_warm = 12 * STEPS_PER_HOUR
    start_i = max(warm, scenario_warm)

    tables = {
        k: {"X": [], "y": [], "scenario_ids": [], "meta": []}
        for k in ("train", "synthetic_dev", "synthetic_test")
    }
    feat_names = None
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        sid = sc["spec"]["scenario_id"]
        split = split_info["assignments"][sid]
        if split not in tables:
            continue
        arr = np.load(sim_dir / sc["npz"])
        X, names = _bfm(arr["pressures"], arr["flows"], arr["levels"])
        feat_names = names
        y = arr["labels_abrupt_positive"].astype(np.int32)
        sl = slice(start_i, None)
        Xs, ys = X[sl], y[sl]
        ok = np.all(np.isfinite(Xs), axis=1)
        Xs, ys = Xs[ok], ys[ok]
        for i in range(Xs.shape[0]):
            tables[split]["X"].append(Xs[i])
            tables[split]["y"].append(int(ys[i]))
            tables[split]["scenario_ids"].append(sid)
            tables[split]["meta"].append(
                {
                    "kind": sc["spec"]["kind"],
                    "pipe": sc["spec"]["pipe"],
                    "pipe_group": sc["spec"]["pipe_group"],
                    "operating_realization": sc["spec"]["operating_realization"],
                    "pair_id": sc["spec"].get("pair_id"),
                    "pattern_phase_offset_hours": sc["spec"].get(
                        "pattern_phase_offset_hours"
                    ),
                }
            )

    out = {
        "feature_manifest": fm(),
        "split_info": split_info,
        "row_start_index": start_i,
        "feature_names": feat_names,
        "splits": {},
    }
    for k, tab in tables.items():
        X = (
            np.ascontiguousarray(np.asarray(tab["X"], dtype=np.float64))
            if tab["X"]
            else np.zeros((0, len(feat_names or [])))
        )
        y = np.asarray(tab["y"], dtype=np.int32)
        out["splits"][k] = {
            "X": X,
            "y": y,
            "scenario_ids": tab["scenario_ids"],
            "meta": tab["meta"],
            "n_rows": int(X.shape[0]),
            "n_pos": int(y.sum()) if y.size else 0,
            "n_scenarios": len(set(tab["scenario_ids"])),
        }
    return out


def occupancy_and_preonset(sim_dir: Path, manifest, assignments, split: str, frozen: dict) -> dict:
    """Episode metrics plus alarm occupancy and pre-onset notify counts."""
    tau = float(frozen["selected"]["tau"])
    leak_rows = []
    ctrl_rows = []
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        sid = sc["spec"]["scenario_id"]
        if assignments.get(sid) != split:
            continue
        arr = np.load(sim_dir / sc["npz"])
        q = score_full_trajectory(arr["pressures"], arr["flows"], arr["levels"], frozen)
        eps = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
        # Occupancy: fraction of post-warmup steps with active episode covering t
        warm = FEATURE_CONFIG.warm_up_steps
        active = np.zeros(q.shape[0], dtype=bool)
        for e in eps:
            active[e.notify_idx : e.end_idx + 1] = True
        post = active[warm:]
        occ = float(post.mean()) if post.size else float("nan")

        if sc["spec"]["kind"] == "leak_abrupt":
            info = analyze_leak_scenario(q, arr["labels_abrupt_positive"], tau=tau)
            leak_rows.append(
                {
                    "scenario_id": sid,
                    "pipe": sc["spec"]["pipe"],
                    "pair_id": sc["spec"].get("pair_id"),
                    "pattern_phase_offset_hours": sc["spec"].get(
                        "pattern_phase_offset_hours"
                    ),
                    "leak_start_hour": sc["spec"].get("leak_start_hour"),
                    "occupancy_frac": occ,
                    "n_preonset_notifies": len(info.get("preonset_notifies") or []),
                    **info,
                }
            )
        elif sc["spec"]["kind"].startswith("control"):
            cinfo = analyze_control_scenario(q, tau=tau)
            ctrl_rows.append(
                {
                    "scenario_id": sid,
                    "kind": sc["spec"]["kind"],
                    "pair_id": sc["spec"].get("pair_id"),
                    "pattern_phase_offset_hours": sc["spec"].get(
                        "pattern_phase_offset_hours"
                    ),
                    "occupancy_frac": occ,
                    **cinfo,
                }
            )

    n_leak = len(leak_rows)
    n_hit = sum(1 for r in leak_rows if r.get("episode_6h_hit"))
    delays = [r["delay_hours"] for r in leak_rows if r.get("delay_hours") is not None]
    n_ctrl = len(ctrl_rows)
    n_ctrl_eps = sum(r["n_episodes"] for r in ctrl_rows)
    ctrl_weeks = n_ctrl * SCENARIO_WEEKS if n_ctrl else float("nan")
    return {
        "split": split,
        "tau": tau,
        "n_leak_scenarios": n_leak,
        "episode_6h_recall": (n_hit / n_leak) if n_leak else float("nan"),
        "n_episode_6h_hit": n_hit,
        "median_delay_h": float(np.median(delays)) if delays else None,
        "delays_h": delays,
        "row_credit_scenario_recall": (
            sum(1 for r in leak_rows if r.get("row_credit_hit")) / n_leak
            if n_leak
            else float("nan")
        ),
        "n_blocked_by_preonset_active": sum(
            1 for r in leak_rows if r.get("blocked_by_preonset_active")
        ),
        "n_preonset_notifies_total": sum(
            r.get("n_preonset_notifies", 0) for r in leak_rows
        ),
        "mean_leak_occupancy_frac": (
            float(np.mean([r["occupancy_frac"] for r in leak_rows])) if leak_rows else None
        ),
        "n_control_scenarios": n_ctrl,
        "n_control_episodes": n_ctrl_eps,
        "control_exposure_weeks": ctrl_weeks,
        "control_episodes_per_week": (
            (n_ctrl_eps / ctrl_weeks) if ctrl_weeks and ctrl_weeks > 0 else float("nan")
        ),
        "mean_control_occupancy_frac": (
            float(np.mean([r["occupancy_frac"] for r in ctrl_rows])) if ctrl_rows else None
        ),
        "control_exposure_note": (
            f"Each control scenario contributes {DURATION_HOURS} h "
            f"({SCENARIO_WEEKS:.4g} weeks). ep/wk = n_episodes / "
            f"(n_controls × {SCENARIO_WEEKS:.4g})."
        ),
        "per_leak": leak_rows,
        "per_control": ctrl_rows,
    }


def assert_no_time_features(feature_names: list[str]) -> None:
    forbidden = ("sin_tod", "cos_tod", "is_weekend", "hour", "onset", "scenario_time", "phase")
    bad = [n for n in feature_names if any(f in n.lower() for f in forbidden)]
    # pattern_phase is not a feature name from builder; check explicit
    if bad:
        raise RuntimeError(f"forbidden time-like features present: {bad}")


def render(doc: dict) -> str:
    lines = [
        "# Scenario-phase correction — synthetic results",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Randomized pattern time origin; independent leak onset after warm-up. "
        "Original `synthetic_scenarios/` preserved. **No measured evaluation** this round.",
        "",
        "## Changes",
        "",
    ]
    for k, v in doc["changes"].items():
        lines.append(f"- **{k}**: {v}")
    lines += [
        "",
        f"Master seed: `{doc['master_seed']}`",
        f"Selection rule: {doc['selection_rule']}",
        "",
        "## Pre-fit distribution checks",
        "",
        f"Passed: **{doc['distribution_checks']['all_passed']}**",
        "",
        f"```json\n{json.dumps(doc['distribution_checks'], indent=2)}\n```",
        "",
        f"Splits: `{doc['splits']['counts']}`; pairs colocated="
        f"{doc['splits']['pairs_colocated']}",
        "",
        "## Freeze",
        "",
        f"- Selected C={doc['frozen']['selected']['C']}, τ={doc['frozen']['selected']['tau']}",
        f"- gate_met={doc['frozen']['gate_met']}, "
        f"selection_failure={doc['frozen']['selection_failure']}",
        f"- DEV metrics: `{doc['frozen']['dev_metrics']}`",
        "",
        "## Synthetic evaluation (headline = episode)",
        "",
        "| Split | episode_6h | med delay h | ctrl ep/wk | ctrl exposure wk | "
        "preonset notifies | blocked | leak occ | ctrl occ | row_credit |",
        "|-------|------------|-------------|------------|------------------|"
        "------------------|---------|----------|----------|------------|",
    ]
    for name in ("synthetic_dev", "synthetic_test"):
        m = doc["synthetic"][name]
        lines.append(
            f"| {name} | {m['episode_6h_recall']:.4g} "
            f"({m['n_episode_6h_hit']}/{m['n_leak_scenarios']}) | "
            f"{m['median_delay_h']} | {m['control_episodes_per_week']:.4g} | "
            f"{m['control_exposure_weeks']:.4g} | {m['n_preonset_notifies_total']} | "
            f"{m['n_blocked_by_preonset_active']} | "
            f"{m['mean_leak_occupancy_frac']:.4g} | "
            f"{m['mean_control_occupancy_frac']:.4g} | "
            f"{m['row_credit_scenario_recall']:.4g} |"
        )
    lines += [
        "",
        doc["synthetic"]["synthetic_test"]["control_exposure_note"],
        "",
        "### Synthetic test per-leak",
        "",
    ]
    for r in doc["synthetic"]["synthetic_test"]["per_leak"]:
        tag = "HIT6" if r["episode_6h_hit"] else "MISS"
        lines.append(
            f"- {tag} `{r['scenario_id']}` phase={r.get('pattern_phase_offset_hours'):.3f}h "
            f"onset={r.get('leak_start_hour'):.3f}h delay={r.get('delay_hours')} "
            f"blocked={r.get('blocked_by_preonset_active')} "
            f"preonset_n={r.get('n_preonset_notifies')} occ={r.get('occupancy_frac'):.3f}"
        )
    lines += [
        "",
        "## Stop",
        "",
        "Synthetic results only — awaiting review before any measured evaluation.",
        "",
        "## Non-goals this round",
        "",
        "- No measured 2018/2019, production, UI, Tiger, deployment",
        "- Original scenarios/results untouched",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    PC.mkdir(parents=True, exist_ok=True)
    if not ORIG_SIM.exists():
        print("Original scenarios missing — abort (nothing to preserve against)", flush=True)
        return 1

    print("=== Tests ===", flush=True)
    import pytest

    tr = pytest.main([str(ROOT / "tests"), "-q"])
    if tr != 0:
        print("TESTS FAILED", flush=True)
        return 1

    print("=== Simulate phase-corrected scenarios (new dir) ===", flush=True)
    t0 = time.perf_counter()
    syn = run_all_phase_scenarios(SIM_DIR, DEFAULT_INP)
    print(
        f"Sim done in {time.perf_counter()-t0:.1f}s ok={syn['n_ok']} fail={syn['n_failed']}",
        flush=True,
    )
    (PC / "sim_summary.json").write_text(json.dumps(_jsonable(syn), indent=2) + "\n")

    manifest = json.loads((SIM_DIR / "scenario_manifest.json").read_text())
    print("=== Verify phase/onset distributions (before fit) ===", flush=True)
    checks = verify_phase_onset_distributions(manifest)
    (PC / "distribution_checks.json").write_text(
        json.dumps(_jsonable(checks), indent=2) + "\n"
    )
    print(json.dumps(checks, indent=2), flush=True)
    if not checks["all_passed"]:
        print("DISTRIBUTION CHECKS FAILED — abort before fit", flush=True)
        return 1

    print("=== Build tables + splits ===", flush=True)
    tables = build_split_tables_phase(SIM_DIR)
    if not tables["split_info"]["pairs_colocated"]:
        print("Paired scenarios not colocated in splits — abort", flush=True)
        return 1
    assert_no_time_features(tables["feature_names"])
    assignments = tables["split_info"]["assignments"]

    print("=== Fit + episode DEV selection ===", flush=True)
    print(f"RULE: {SELECTION_RULE}", flush=True)
    frozen = fit_select_episode(
        tables["splits"]["train"],
        SIM_DIR,
        manifest,
        assignments,
        feature_names=tables["feature_names"],
        feature_set_label="pressure_context_v1",
    )
    frozen["frozen_at"] = iso_now()
    frozen["experiment"] = "scenario_phase_correction"
    print(
        f"Selected C={frozen['selected']['C']} tau={frozen['selected']['tau']} "
        f"gate_met={frozen['gate_met']} failure={frozen['selection_failure']}",
        flush=True,
    )
    (PC / "frozen_model.json").write_text(json.dumps(_jsonable(frozen), indent=2) + "\n")
    (PC / "dev_grid.json").write_text(
        json.dumps(_jsonable(frozen["grid_records"]), indent=2) + "\n"
    )

    print("=== Synthetic DEV/TEST (episode + occupancy) ===", flush=True)
    syn_eval = {}
    for split in ("synthetic_dev", "synthetic_test"):
        syn_eval[split] = occupancy_and_preonset(
            SIM_DIR, manifest, assignments, split, frozen
        )
        m = syn_eval[split]
        print(
            f"{split}: ep6h={m['episode_6h_recall']} ctrl/wk={m['control_episodes_per_week']} "
            f"blocked={m['n_blocked_by_preonset_active']} "
            f"preonset_n={m['n_preonset_notifies_total']} "
            f"ctrl_occ={m['mean_control_occupancy_frac']}",
            flush=True,
        )
    (PC / "synthetic_episode_eval.json").write_text(
        json.dumps(_jsonable(syn_eval), indent=2) + "\n"
    )

    # Side row-table metrics (not headline)
    syn_row = {
        "synthetic_dev": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_dev"]
        ),
        "synthetic_test": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_test"]
        ),
    }
    (PC / "synthetic_row_table_eval.json").write_text(
        json.dumps(_jsonable(syn_row), indent=2) + "\n"
    )

    doc = {
        "generated_at": iso_now(),
        "experiment": "scenario_phase_correction",
        "master_seed": PHASE_MASTER_SEED,
        "selection_rule": SELECTION_RULE,
        "changes": syn["changes"],
        "distribution_checks": checks,
        "splits": tables["split_info"],
        "feature_manifest": feature_manifest(),
        "forbidden_inputs_check": "passed (no scenario time / onset / phase features)",
        "frozen": {
            "selected": frozen["selected"],
            "gate_met": frozen["gate_met"],
            "selection_failure": frozen["selection_failure"],
            "dev_metrics": frozen["dev_metrics"],
            "budget": frozen["budget"],
            "n_train": frozen["n_train"],
            "n_train_pos": frozen["n_train_pos"],
        },
        "synthetic": syn_eval,
        "synthetic_row_table": syn_row,
        "preserves": [
            "outputs/synthetic_scenarios/",
            "outputs/pilot_*",
            "outputs/episode_objective/",
            "outputs/change_only_ablation/",
            "outputs/arm_a_synth_miss_audit/",
            "outputs/t199_trigger_audit/",
        ],
        "stop": "synthetic_only_awaiting_review",
        "measured_evaluation": False,
    }
    (PC / "summary.json").write_text(json.dumps(_jsonable(doc), indent=2) + "\n")
    (PC / "PHASE_CORRECTION_RESULTS.md").write_text(render(doc) + "\n")
    print(f"Wrote {PC / 'PHASE_CORRECTION_RESULTS.md'}", flush=True)
    print("STOP: synthetic results only — no measured evaluation.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
