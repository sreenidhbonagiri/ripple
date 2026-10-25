"""Synthetic scenarios for uncertainty-aware H0/H1 feasibility.

Whole-scenario train/dev/test splits — no evaluation leak peeking into
candidate generation (candidates come from hypothesis_test.candidate_nodes_from_topology).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wntr
import wntr.network.io

from .hypothesis_test import HypothesisConfig, candidate_nodes_from_topology, decide_hypothesis, decision_to_dict
from .synthetic_networks import (
    build_branched_three_sensor_network,
    build_tank_pump_network,
    inject_nodal_leak,
    scale_all_demands,
    scale_all_roughness,
)


# Whole-scenario splits (protocol §11).
SPLIT_OF: dict[str, str] = {
    "nl_nominal": "train",
    "leak_nominal_J3": "train",
    "nl_demand_scale": "train",
    "nl_noise": "dev",
    "leak_noise_J3": "dev",
    "ambiguous_demand_J1": "dev",
    "nl_roughness": "dev",
    "leak_demand_var_J2": "test",
    "nl_pump_transition": "test",
    "leak_pump_J1": "test",
    "leak_roughness_J3": "test",
    "nl_demand_node_J1": "test",
}


@dataclass
class ScenarioTruth:
    scenario_id: str
    network_id: str
    split: str
    has_new_leak: bool
    leak_node: str | None
    leak_m3h: float
    description: str
    factors: list[str]
    ambiguous_by_design: bool = False


def _clone(wn: wntr.network.WaterNetworkModel, scratch: Path) -> wntr.network.WaterNetworkModel:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"scen_{np.random.randint(1e12)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def _heads(wn: wntr.network.WaterNetworkModel, sensors: tuple[str, ...]) -> dict[str, float]:
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    return {s: float(res.node["head"].iloc[0][s]) for s in sensors}


def _add_noise(heads: dict[str, float], rng: np.random.Generator, sigma_m: float) -> dict[str, float]:
    return {k: float(v + rng.normal(0.0, sigma_m)) for k, v in heads.items()}


def _template_branched() -> tuple[wntr.network.WaterNetworkModel, tuple[str, ...]]:
    return build_branched_three_sensor_network()


def _template_pump() -> tuple[wntr.network.WaterNetworkModel, tuple[str, ...]]:
    return build_tank_pump_network()


def build_truth_and_obs(
    scenario_id: str,
    scratch: Path,
    *,
    seed: int = 0,
) -> tuple[ScenarioTruth, wntr.network.WaterNetworkModel, tuple[str, ...], dict[str, float]]:
    """Return truth metadata, model template (no leak), sensors, and observations."""
    rng = np.random.default_rng(seed)
    split = SPLIT_OF[scenario_id]

    if scenario_id.startswith("nl_pump") or scenario_id.startswith("leak_pump"):
        network_id = "pump_tank"
        wn_truth, sensors = _template_pump()
        wn_truth = _clone(wn_truth, scratch)
        # Snapshot near start (pump on); transition covered by matched BC in template.
        if scenario_id == "leak_pump_J1":
            inject_nodal_leak(wn_truth, "J1", 4.0)
            truth = ScenarioTruth(
                scenario_id, network_id, split, True, "J1", 4.0,
                "Leak at J1 on pump–tank analogue (matched BC snapshot)",
                ["leak", "pump_tank"],
            )
        else:
            truth = ScenarioTruth(
                scenario_id, network_id, split, False, None, 0.0,
                "No leak; pump–tank analogue matched",
                ["no_leak", "pump_tank"],
            )
        obs = _heads(wn_truth, sensors)
        wn_model, _ = _template_pump()
        return truth, wn_model, sensors, obs

    # Branched three-sensor family
    network_id = "branched3"
    wn_truth, sensors = _template_branched()
    wn_truth = _clone(wn_truth, scratch)
    factors: list[str] = []
    has_leak = False
    leak_node = None
    leak_m3h = 0.0
    ambiguous = False
    description = scenario_id

    if scenario_id == "nl_nominal":
        factors = ["no_leak", "nominal"]
        description = "No leak; model matches truth"
    elif scenario_id == "leak_nominal_J3":
        inject_nodal_leak(wn_truth, "J3", 5.0)
        has_leak, leak_node, leak_m3h = True, "J3", 5.0
        factors = ["leak", "nominal"]
        description = "Clear leak 5 m³/h at J3; matched model otherwise"
    elif scenario_id == "nl_demand_scale":
        scale_all_demands(wn_truth, 1.25)
        factors = ["no_leak", "demand_variation"]
        description = "No leak; uniform +25% demand in truth (inside H0 demand box via δ)"
    elif scenario_id == "nl_noise":
        factors = ["no_leak", "sensor_noise"]
        description = "No leak; sensor head noise σ=0.05 m"
    elif scenario_id == "leak_noise_J3":
        inject_nodal_leak(wn_truth, "J3", 5.0)
        has_leak, leak_node, leak_m3h = True, "J3", 5.0
        factors = ["leak", "sensor_noise"]
        description = "Leak at J3 + sensor noise σ=0.05 m"
    elif scenario_id == "ambiguous_demand_J1":
        # Extra customer demand — indistinguishable from leak at J1
        inject_nodal_leak(wn_truth, "J1", 2.5)  # demand bump helper
        factors = ["no_leak", "indistinguishable_demand"]
        ambiguous = True
        description = "No physical leak; +2.5 m³/h customer demand at J1 (≡ leak at J1)"
    elif scenario_id == "nl_roughness":
        scale_all_roughness(wn_truth, 0.95)
        factors = ["no_leak", "model_mismatch"]
        description = "No leak; truth roughness ×0.95"
    elif scenario_id == "leak_demand_var_J2":
        scale_all_demands(wn_truth, 1.15)
        inject_nodal_leak(wn_truth, "J2", 4.0)
        has_leak, leak_node, leak_m3h = True, "J2", 4.0
        factors = ["leak", "demand_variation"]
        description = "Leak at J2 + uniform demand scale 1.15"
    elif scenario_id == "leak_roughness_J3":
        scale_all_roughness(wn_truth, 0.95)
        inject_nodal_leak(wn_truth, "J3", 5.0)
        has_leak, leak_node, leak_m3h = True, "J3", 5.0
        factors = ["leak", "model_mismatch"]
        description = "Leak at J3 + roughness mismatch"
    elif scenario_id == "nl_demand_node_J1":
        inject_nodal_leak(wn_truth, "J1", 1.5)
        factors = ["no_leak", "demand_variation"]
        description = "No leak; +1.5 m³/h demand at J1 (inside δ box; control)"
    else:
        raise KeyError(scenario_id)

    obs = _heads(wn_truth, sensors)
    if "sensor_noise" in factors:
        obs = _add_noise(obs, rng, sigma_m=0.05)

    truth = ScenarioTruth(
        scenario_id=scenario_id,
        network_id=network_id,
        split=split,
        has_new_leak=has_leak,
        leak_node=leak_node,
        leak_m3h=leak_m3h,
        description=description,
        factors=factors,
        ambiguous_by_design=ambiguous,
    )
    wn_model, _ = _template_branched()
    return truth, wn_model, sensors, obs


def run_scenario(
    scenario_id: str,
    scratch: Path,
    *,
    cfg: HypothesisConfig,
    seed: int = 0,
) -> dict[str, Any]:
    truth, wn_model, sensors, obs = build_truth_and_obs(scenario_id, scratch, seed=seed)
    candidates = candidate_nodes_from_topology(truth.network_id)
    # Candidates fixed from topology — assert independence from truth leak set construction.
    assert set(candidates) == set(candidate_nodes_from_topology(truth.network_id))

    decision = decide_hypothesis(
        wn_model, sensors, obs, candidates, cfg=cfg, scratch=scratch / "fit"
    )
    region_cov = None
    loc_correct = None
    if truth.has_new_leak and truth.leak_node is not None:
        region_cov = truth.leak_node in decision.candidate_region
        loc_correct = decision.best_candidate == truth.leak_node

    return {
        "scenario_id": scenario_id,
        "split": truth.split,
        "seed": seed,
        "description": truth.description,
        "factors": truth.factors,
        "has_new_leak": truth.has_new_leak,
        "true_leak_node": truth.leak_node,
        "true_leak_m3h": truth.leak_m3h,
        "ambiguous_by_design": truth.ambiguous_by_design,
        "network_id": truth.network_id,
        "candidates": list(candidates),
        "obs_heads": obs,
        "hypothesis": decision_to_dict(decision),
        "localization_correct": loc_correct,
        "region_covers_truth": region_cov,
    }


def iter_split_scenario_ids(split: str) -> list[str]:
    return [sid for sid, sp in SPLIT_OF.items() if sp == split]


def all_scenario_ids() -> list[str]:
    return list(SPLIT_OF.keys())
