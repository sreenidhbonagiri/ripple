"""Fresh whole-scenario L-Town synthetic suite (post toy audit).

Candidates = all pressure sensors (registered before truths).
Eval leaks are drawn from that set so omission is not confounded with region rules.
Train/DEV/TEST assign entire scenario IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wntr

from .dual_builder import DualModelSpec
from .ltown_hypothesis import (
    LTownHypConfig,
    _apply_area_scales,
    _apply_rho,
    _clone,
    _snapshot_bases,
    build_calibrated_template,
    decide_ltown,
    decision_to_dict,
    registered_candidates,
)
from .simulate import run_dual_steady, summarize_qv
from .synthetic_networks import inject_nodal_leak


# Fresh IDs — disjoint from toy hypothesis_synthetic names.
SPLIT_OF: dict[str, str] = {
    # train
    "lt_nl_nominal": "train",
    "lt_leak_only_n506": "train",
    "lt_demand_only_areaC": "train",
    # dev
    "lt_nl_noise": "dev",
    "lt_leak_noise_n726": "dev",
    "lt_demand_only_areaA": "dev",
    "lt_mismatch_roughness": "dev",
    "lt_combined_demand_leak_n644": "dev",
    # test (frozen after DEV calibration — never used to pick ε / τ)
    "lt_leak_only_n342": "test",
    "lt_demand_only_areaB": "test",
    "lt_combined_n519": "test",
    "lt_pump_transition_nl": "test",
    "lt_pump_transition_leak_n54": "test",
    "lt_mismatch_leak_n415": "test",
}


@dataclass
class Truth:
    scenario_id: str
    split: str
    has_new_leak: bool
    leak_node: str | None
    leak_m3h: float
    factors: list[str]
    description: str
    ambiguous_by_design: bool
    perturbation_inside_bounds: bool
    bound_notes: str


def _set_pump_status(wn, open: bool) -> None:
    if "PUMP_1" not in wn.link_name_list:
        return
    pump = wn.get_link("PUMP_1")
    try:
        pump.status = 1 if open else 0
    except Exception:
        pump.initial_status = 1 if open else 0


def _scale_area_demands(wn, area_nodes: set[str], factor: float) -> None:
    for name in area_nodes:
        node = wn.get_node(name)
        for ts in node.demand_timeseries_list:
            ts.base_value = float(ts.base_value) * float(factor)


def build_scenario(
    scenario_id: str,
    scratch: Path,
    *,
    seed: int = 0,
) -> tuple[Truth, Any, tuple[str, ...], dict[str, set[str]], dict[str, float], list[str]]:
    """Return truth, model template, sensors, areas, obs heads, candidates."""
    rng = np.random.default_rng(seed)
    wn_model, sensors, areas = build_calibrated_template(scratch / "base")
    candidates = list(registered_candidates())
    assert set(candidates) <= set(wn_model.junction_name_list)

    wn_truth = _clone(wn_model, scratch / "truth")
    bases = _snapshot_bases(wn_truth)
    pipe_rough0 = {p: float(wn_truth.get_link(p).roughness) for p in wn_truth.pipe_name_list}

    has_leak = False
    leak_node = None
    leak_m3h = 0.0
    factors: list[str] = []
    ambiguous = False
    inside = True
    bound_notes = "nominal"
    desc = scenario_id
    scales = {"A": 1.0, "B": 1.0, "C": 1.0}
    rho = 1.0
    pump_open = True

    if scenario_id == "lt_nl_nominal":
        factors = ["no_leak", "nominal"]
        desc = "No leak; calibrated model matches truth"
    elif scenario_id == "lt_leak_only_n506":
        has_leak, leak_node, leak_m3h = True, "n506", 5.0
        factors = ["leak_only"]
        desc = "Leak-only 5 m³/h at n506 (candidate)"
        bound_notes = "q=5 within [0,15]"
    elif scenario_id == "lt_demand_only_areaC":
        scales["C"] = 1.08
        factors = ["demand_only"]
        desc = "Demand-only Area-C ×1.08; no leak"
        bound_notes = "scale 1.08 within [0.88,1.12]"
    elif scenario_id == "lt_nl_noise":
        factors = ["no_leak", "sensor_noise"]
        desc = "No leak; sensor head noise σ=0.03 m"
    elif scenario_id == "lt_leak_noise_n726":
        has_leak, leak_node, leak_m3h = True, "n726", 4.5
        factors = ["leak_only", "sensor_noise"]
        desc = "Leak 4.5 at n726 + noise"
    elif scenario_id == "lt_demand_only_areaA":
        scales["A"] = 1.08
        factors = ["demand_only"]
        desc = "Demand-only Area-A ×1.08"
        bound_notes = "scale 1.08 within bounds"
    elif scenario_id == "lt_mismatch_roughness":
        rho = 0.97
        factors = ["model_mismatch", "no_leak"]
        desc = "No leak; global HW ×0.97 in truth"
        bound_notes = "rho 0.97 within [0.95,1.05]"
    elif scenario_id == "lt_combined_demand_leak_n644":
        scales["A"] = 1.06
        has_leak, leak_node, leak_m3h = True, "n644", 4.0
        factors = ["combined_demand_leak"]
        desc = "Combined Area-A ×1.06 + leak 4 at n644"
    elif scenario_id == "lt_leak_only_n342":
        has_leak, leak_node, leak_m3h = True, "n342", 5.0
        factors = ["leak_only"]
        desc = "TEST leak-only at n342"
    elif scenario_id == "lt_demand_only_areaB":
        scales["B"] = 1.10
        factors = ["demand_only"]
        desc = "TEST demand-only Area-B ×1.10"
        bound_notes = "scale 1.10 within [0.88,1.12]"
    elif scenario_id == "lt_combined_n519":
        scales["C"] = 1.07
        has_leak, leak_node, leak_m3h = True, "n519", 3.5
        factors = ["combined_demand_leak"]
        desc = "TEST combined Area-C ×1.07 + leak n519"
    elif scenario_id == "lt_pump_transition_nl":
        pump_open = False
        factors = ["pump_transition", "no_leak"]
        desc = "TEST no leak; PUMP_1 forced closed (transition analogue)"
    elif scenario_id == "lt_pump_transition_leak_n54":
        pump_open = False
        has_leak, leak_node, leak_m3h = True, "n54", 4.0
        factors = ["pump_transition", "leak_only"]
        desc = "TEST leak at n54 with PUMP_1 closed"
    elif scenario_id == "lt_mismatch_leak_n415":
        rho = 0.96
        has_leak, leak_node, leak_m3h = True, "n415", 5.0
        factors = ["model_mismatch", "leak_only"]
        desc = "TEST roughness ×0.96 + leak n415"
    else:
        raise KeyError(scenario_id)

    # Ensure leak nodes are candidates (protocol: represented)
    if has_leak:
        assert leak_node in candidates, f"{leak_node} not in registered candidates"

    _apply_area_scales(wn_truth, bases, areas, scales)
    _apply_rho(wn_truth, rho, pipe_rough0)
    _set_pump_status(wn_truth, pump_open)
    if has_leak:
        inject_nodal_leak(wn_truth, leak_node, leak_m3h)

    wn_truth.options.time.duration = 0
    wn_truth.options.time.hydraulic_timestep = 3600
    wn_truth.options.time.report_timestep = 3600
    res = wntr.sim.EpanetSimulator(wn_truth).run_sim()
    obs = {s: float(res.node["head"].iloc[0][s]) for s in sensors}
    if "sensor_noise" in factors:
        obs = {k: float(v + rng.normal(0.0, 0.03)) for k, v in obs.items()}

    # Model template: calibrated, pump status matched to truth BC (not a free nuisance)
    wn_model2 = _clone(wn_model, scratch / "model")
    _set_pump_status(wn_model2, pump_open)

    truth = Truth(
        scenario_id=scenario_id,
        split=SPLIT_OF[scenario_id],
        has_new_leak=has_leak,
        leak_node=leak_node,
        leak_m3h=leak_m3h,
        factors=factors,
        description=desc,
        ambiguous_by_design=ambiguous,
        perturbation_inside_bounds=inside,
        bound_notes=bound_notes,
    )
    return truth, wn_model2, sensors, areas, obs, candidates


def run_ltown_scenario(
    scenario_id: str,
    scratch: Path,
    *,
    cfg: LTownHypConfig,
    seed: int = 0,
) -> dict[str, Any]:
    truth, wn_model, sensors, areas, obs, candidates = build_scenario(
        scenario_id, scratch, seed=seed
    )
    decision = decide_ltown(
        wn_model, sensors, areas, obs, candidates, cfg=cfg, scratch=scratch / "fit"
    )
    # Signature baseline (dual) on same obs / model template without leak
    spec = DualModelSpec(sensor_nodes=tuple(sensors), tcv_setting=1e-3)
    dual = run_dual_steady(wn_model, spec, obs, scratch_dir=scratch / "dual")
    summary = summarize_qv(dual)
    qv = summary["q_v_m3h"]
    dominant = max(qv, key=lambda k: abs(qv[k]))

    return {
        "scenario_id": scenario_id,
        "split": truth.split,
        "seed": seed,
        "description": truth.description,
        "factors": truth.factors,
        "has_new_leak": truth.has_new_leak,
        "true_leak_node": truth.leak_node,
        "true_leak_m3h": truth.leak_m3h,
        "true_leak_in_candidates": (truth.leak_node in candidates) if truth.has_new_leak else None,
        "ambiguous_by_design": truth.ambiguous_by_design,
        "perturbation_inside_bounds": truth.perturbation_inside_bounds,
        "bound_notes": truth.bound_notes,
        "n_candidates": len(candidates),
        "candidates": candidates,
        "n_sensors": len(sensors),
        "network": "L-TOWN.inp+frozen_HW_clusters",
        "calibration_sha256": "5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921",
        "hypothesis": decision_to_dict(decision),
        "baseline_signature_raw": {
            "sum_m3h": float(summary["sum_m3h"]),
            "abs_sum_m3h": abs(float(summary["sum_m3h"])),
            "dominant": dominant,
            "q_v_m3h": qv,
        },
    }


def all_scenario_ids() -> list[str]:
    return list(SPLIT_OF.keys())
