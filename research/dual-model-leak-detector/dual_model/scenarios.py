"""Synthetic mechanism scenarios for dual-model verification.

Each scenario returns a structured dict suitable for JSON serialization.
Actual leak discharge is recorded whenever a leak is injected. Virtual flow
is never claimed to be automatically equal to true leak discharge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import wntr
import wntr.network.io

from .dual_builder import DualModelSpec
from .simulate import run_dual_steady, run_dual_timeseries, summarize_qv
from .synthetic_networks import (
    build_branched_three_sensor_network,
    build_tank_pump_network,
    inject_nodal_leak,
    scale_all_demands,
    scale_all_roughness,
    shift_sensor_datum,
)


def _clone(wn: wntr.network.WaterNetworkModel, scratch: Path) -> wntr.network.WaterNetworkModel:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"clone_{id(wn)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def _primal_heads_snapshot(
    wn: wntr.network.WaterNetworkModel,
    sensors: tuple[str, ...],
) -> tuple[dict[str, float], Any]:
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    heads = {s: float(res.node["head"].iloc[0][s]) for s in sensors}
    return heads, res


def _near_zero(sum_m3h: float, tol_m3h: float = 0.05) -> bool:
    return abs(sum_m3h) <= tol_m3h


def scenario_no_leak_correct(
    scratch: Path,
    *,
    tcv_setting: float = 1e-3,
) -> dict[str, Any]:
    """No leak; dual model matches the primal that generated the heads."""
    wn, sensors = build_branched_three_sensor_network()
    heads, _ = _primal_heads_snapshot(wn, sensors)
    spec = DualModelSpec(sensor_nodes=sensors, tcv_setting=tcv_setting)
    dual = run_dual_steady(wn, spec, heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    return {
        "id": "no_leak_correct",
        "description": "No-leak, correctly specified dual model",
        "actual_leak_m3h": 0.0,
        "result": summary,
        "distinguishes_leak": None,
        "interpretation": (
            "sum(q_v) ≈ 0 when the hydraulic model matches the measured heads; "
            "residual is numerical (nonzero TCV loss), not a physical leak."
        ),
        "pass_criterion": "abs(sum_m3h) < 0.05",
        "passed": _near_zero(summary["sum_m3h"]),
    }


def scenario_known_leak(
    scratch: Path,
    *,
    leak_node: str = "J3",
    leak_m3h: float = 5.0,
    tcv_setting: float = 1e-3,
) -> dict[str, Any]:
    """Leak in 'reality'; dual model is leak-free but driven by leaky heads."""
    wn_truth, sensors = build_branched_three_sensor_network()
    wn_truth = _clone(wn_truth, scratch)
    actual_leak_m3s = inject_nodal_leak(wn_truth, leak_node, leak_m3h)
    heads, _ = _primal_heads_snapshot(wn_truth, sensors)

    wn_model, _ = build_branched_three_sensor_network()  # no leak in model
    spec = DualModelSpec(sensor_nodes=sensors, tcv_setting=tcv_setting)
    dual = run_dual_steady(wn_model, spec, heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    err = abs(summary["sum_m3h"] - leak_m3h)
    # Localization: argmax |q_v| should be at/near leak node for this topology
    qv = summary["q_v_m3h"]
    dominant = max(qv, key=lambda k: abs(qv[k]))
    return {
        "id": "known_injected_leak",
        "description": f"Known demand-driven leak of {leak_m3h} m³/h at {leak_node}",
        "actual_leak_m3h": leak_m3h,
        "actual_leak_m3s": actual_leak_m3s,
        "result": summary,
        "sum_minus_actual_m3h": summary["sum_m3h"] - leak_m3h,
        "dominant_sensor": dominant,
        "distinguishes_leak": True,
        "interpretation": (
            "With a correct demand/roughness model, sum(q_v) approximates the "
            "injected leak discharge and the largest |q_v| localizes near the leak. "
            "q_v is still a model imbalance, not a physical orifice flow."
        ),
        "pass_criterion": "abs(sum_m3h - leak_m3h) < 0.1 and dominant_sensor == leak_node",
        "passed": err < 0.1 and dominant == leak_node,
    }


def scenario_demand_change_matched(scratch: Path) -> dict[str, Any]:
    """Demand changes in truth and in the dual model (no leak)."""
    wn_truth, sensors = build_branched_three_sensor_network()
    wn_truth = _clone(wn_truth, scratch)
    scale_all_demands(wn_truth, 1.5)
    heads, _ = _primal_heads_snapshot(wn_truth, sensors)

    wn_model, _ = build_branched_three_sensor_network()
    wn_model = _clone(wn_model, scratch)
    scale_all_demands(wn_model, 1.5)
    spec = DualModelSpec(sensor_nodes=sensors)
    dual = run_dual_steady(wn_model, spec, heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    return {
        "id": "demand_change_matched",
        "description": "Uniform +50% demand in truth and in dual model; no leak",
        "actual_leak_m3h": 0.0,
        "result": summary,
        "distinguishes_leak": True,
        "interpretation": (
            "Ordinary demand operations that are represented in the dual model "
            "do not produce a virtual-leak signature (sum q_v ≈ 0)."
        ),
        "pass_criterion": "abs(sum_m3h) < 0.05",
        "passed": _near_zero(summary["sum_m3h"]),
    }


def scenario_demand_mismatch(scratch: Path) -> dict[str, Any]:
    """Demand increases in truth; dual model keeps baseline demand (no leak)."""
    wn_truth, sensors = build_branched_three_sensor_network()
    wn_truth = _clone(wn_truth, scratch)
    # Increase only J1 by +5 m³/h
    inject_nodal_leak(wn_truth, "J1", 5.0)  # reuse helper as extra demand
    heads, _ = _primal_heads_snapshot(wn_truth, sensors)

    wn_model, _ = build_branched_three_sensor_network()
    spec = DualModelSpec(sensor_nodes=sensors)
    dual = run_dual_steady(wn_model, spec, heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    return {
        "id": "demand_mismatch_no_leak",
        "description": "Truth demand +5 m³/h at J1; model unaware; no physical leak",
        "actual_leak_m3h": 0.0,
        "unmodeled_demand_m3h": 5.0,
        "result": summary,
        "distinguishes_leak": False,
        "interpretation": (
            "Unmodeled demand produces sum(q_v) ≈ the demand error. Virtual flow "
            "cannot distinguish this from a real leak of the same magnitude. "
            "This is why demand calibration is required before measured-data use."
        ),
        "pass_criterion": "abs(sum_m3h - 5.0) < 0.2 (documents confounding, not a leak TP)",
        "passed": abs(summary["sum_m3h"] - 5.0) < 0.2,
        "confounder": True,
    }


def scenario_roughness_mismatch(scratch: Path, factor: float = 0.9) -> dict[str, Any]:
    """Roughness error without leak."""
    wn_truth, sensors = build_branched_three_sensor_network()
    heads, _ = _primal_heads_snapshot(wn_truth, sensors)

    wn_model, _ = build_branched_three_sensor_network()
    wn_model = _clone(wn_model, scratch)
    scale_all_roughness(wn_model, factor)
    spec = DualModelSpec(sensor_nodes=sensors)
    dual = run_dual_steady(wn_model, spec, heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    return {
        "id": "roughness_mismatch_no_leak",
        "description": f"No leak; dual model roughness scaled by {factor}",
        "actual_leak_m3h": 0.0,
        "roughness_scale": factor,
        "result": summary,
        "distinguishes_leak": False,
        "interpretation": (
            "Roughness error induces nonzero q_v even without leaks (Campbell et al. "
            "2024). Magnitude depends on operating point; not automatically a leak."
        ),
        "pass_criterion": "abs(sum_m3h) > 0.05 (nonzero confounder documented)",
        "passed": abs(summary["sum_m3h"]) > 0.05,
        "confounder": True,
    }


def scenario_sensor_datum_mismatch(scratch: Path, delta_m: float = 0.5) -> dict[str, Any]:
    """Bias one sensor head (elevation/datum error) without leak."""
    wn, sensors = build_branched_three_sensor_network()
    heads, _ = _primal_heads_snapshot(wn, sensors)
    heads_bad = shift_sensor_datum(heads, "J2", delta_m)
    spec = DualModelSpec(sensor_nodes=sensors)
    dual = run_dual_steady(wn, spec, heads_bad, scratch_dir=scratch)
    summary = summarize_qv(dual)
    return {
        "id": "sensor_datum_mismatch",
        "description": f"No leak; +{delta_m} m datum bias on J2 head",
        "actual_leak_m3h": 0.0,
        "datum_bias_m": delta_m,
        "biased_sensor": "J2",
        "result": summary,
        "distinguishes_leak": False,
        "interpretation": (
            "A sensor elevation/datum error drives local q_v and can look like a "
            "nearby leak. Sensor-specific elevation calibration (Campbell et al. "
            "2024) is needed before detection claims."
        ),
        "pass_criterion": "abs(sum_m3h) > 0.05 or abs(q_v[J2]) dominant",
        "passed": abs(summary["sum_m3h"]) > 0.05 or abs(summary["q_v_m3h"]["J2"]) == max(
            abs(v) for v in summary["q_v_m3h"].values()
        ),
        "confounder": True,
    }


def _index_to_sec(t) -> int:
    if hasattr(t, "total_seconds"):
        return int(t.total_seconds())
    return int(t)


def scenario_pump_tank_transition(scratch: Path) -> dict[str, Any]:
    """Correctly specified model across pump-off and tank level change; no leak."""
    wn, sensors = build_tank_pump_network()
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    heads_ts = {s: [float(x) for x in res.node["head"][s].tolist()] for s in sensors}

    duration = int(wn.options.time.duration)
    dt = int(wn.options.time.hydraulic_timestep)
    spec = DualModelSpec(sensor_nodes=sensors)
    dual = run_dual_timeseries(
        wn,
        spec,
        heads_ts,
        duration_sec=duration,
        hydraulic_timestep_sec=dt,
        pattern_timestep_sec=dt,
        scratch_dir=scratch,
    )

    idx = list(dual.q_v_sum_m3h.index)

    def _at_m3h(t_sec: int) -> float:
        best = min(idx, key=lambda t: abs(_index_to_sec(t) - t_sec))
        return float(dual.q_v_sum_m3h.loc[best])

    before_m3h = _at_m3h(5 * 3600)
    after_m3h = _at_m3h(7 * 3600)
    max_abs = float(np.max(np.abs(dual.q_v_sum_m3h.values)))
    return {
        "id": "pump_tank_transition",
        "description": "Pump off at 6 h; tank level evolves; model matches truth; no leak",
        "actual_leak_m3h": 0.0,
        "result": {
            "sum_m3h_before_pump_off": before_m3h,
            "sum_m3h_after_pump_off": after_m3h,
            "max_abs_sum_m3h": max_abs,
            "n_timesteps": len(dual.q_v_sum_m3h),
        },
        "distinguishes_leak": True,
        "interpretation": (
            "When pump status and tank boundaries are represented in the dual model "
            "and VR heads track the matching primal, sum(q_v) stays near zero across "
            "the transition. q_v does not flag ordinary pump/tank operations."
        ),
        "pass_criterion": "max_abs_sum_m3h < 0.2",
        "passed": max_abs < 0.2,
    }


def run_all_scenarios(scratch: Path) -> list[dict[str, Any]]:
    return [
        scenario_no_leak_correct(scratch),
        scenario_known_leak(scratch),
        scenario_demand_change_matched(scratch),
        scenario_demand_mismatch(scratch),
        scenario_roughness_mismatch(scratch),
        scenario_sensor_datum_mismatch(scratch),
        scenario_pump_tank_transition(scratch),
    ]