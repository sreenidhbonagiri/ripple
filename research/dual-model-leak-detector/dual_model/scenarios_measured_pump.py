"""Synthetic verification for the measured-PUMP_1 dual boundary variant."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import wntr
import wntr.network.io

from .dual_builder import DualModelSpec, attach_virtual_reservoirs
from .pump_boundary import impose_measured_internal_pump_transfer, prepare_pump_series_causal
from .simulate import _extract_qv
from .synthetic_networks import build_ltown_like_pump_tank_network, inject_nodal_leak
from .units import m3s_to_m3h


def _clone(wn: wntr.network.WaterNetworkModel, scratch: Path) -> wntr.network.WaterNetworkModel:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"mp_clone_{id(wn)}_{np.random.randint(1e9)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def _run_primal(wn: wntr.network.WaterNetworkModel, sensors: tuple[str, ...]):
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    heads = {s: [float(x) for x in res.node["head"][s].tolist()] for s in sensors}
    pump_m3h = (res.link["flowrate"]["PUMP_1"] * 3600.0).astype(float).tolist()
    return res, heads, pump_m3h


def _run_dual_measured(
    wn_primal: wntr.network.WaterNetworkModel,
    sensors: tuple[str, ...],
    heads_ts: dict[str, list[float]],
    pump_m3h: list[float],
    scratch: Path,
) -> tuple[Any, dict[str, Any]]:
    duration = int(wn_primal.options.time.duration)
    dt = int(wn_primal.options.time.hydraulic_timestep)
    spec = DualModelSpec(sensor_nodes=sensors)
    wd = attach_virtual_reservoirs(
        wn_primal,
        spec,
        head_timeseries=heads_ts,
        pattern_timestep_sec=dt,
        scratch_dir=scratch,
    )
    wd.options.time.duration = duration
    wd.options.time.hydraulic_timestep = dt
    wd.options.time.report_timestep = dt
    wd.options.time.pattern_timestep = dt
    # Match primal tank init
    wd.get_node("T1").init_level = float(wn_primal.get_node("T1").init_level)
    info = impose_measured_internal_pump_transfer(wd, pump_m3h, pump_link="PUMP_1")
    res = wntr.sim.EpanetSimulator(wd).run_sim()
    qv = _extract_qv(res.link["flowrate"], spec) * 3600.0  # m³/h
    return qv, {"converged": True, **info}


def scenario_matched_transition_measured(scratch: Path) -> dict[str, Any]:
    """No leak; dual uses measured pump flow from matched primal."""
    wn, sensors = build_ltown_like_pump_tank_network()
    _res, heads, pump_m3h = _run_primal(wn, sensors)
    qv, info = _run_dual_measured(_clone(wn, scratch), sensors, heads, pump_m3h, scratch)
    s = qv.sum(axis=1)
    # Around pump-off (6 h): indices at dt=1h → index 6
    max_abs = float(np.nanmax(np.abs(s.values)))
    at_switch = float(s.iloc[min(6, len(s) - 1)])
    n54_jump = float(qv["n54"].diff().abs().iloc[min(6, len(qv) - 1)])
    return {
        "id": "measured_pump_matched_transition",
        "description": "Matched no-leak pump/tank transition with measured PUMP_1 BC",
        "actual_leak_m3h": 0.0,
        "result": {
            "max_abs_sum_m3h": max_abs,
            "sum_at_switch_m3h": at_switch,
            "n54_abs_delta_at_switch_m3h": n54_jump,
            "pump_m3h_at_switch": pump_m3h[min(6, len(pump_m3h) - 1)],
            "pump_boundary": info,
        },
        "pass_criterion": "max_abs_sum_m3h < 0.5",
        "passed": max_abs < 0.5,
        "interpretation": (
            "With measured internal transfer matching the primal pump, Σq_v stays "
            "near zero across the pump-off transition."
        ),
    }


def scenario_leak_stable_measured(scratch: Path) -> dict[str, Any]:
    """Constant leak under stable pump (no switch); measured pump BC."""
    leak_m3h = 5.0
    wn, sensors = build_ltown_like_pump_tank_network()
    # Remove timed pump-off so pump stays on
    wn.remove_control("pump_off")
    inject_nodal_leak(wn, "J_branch", leak_m3h)
    _res, heads, pump_m3h = _run_primal(wn, sensors)
    # Dual model: same topology WITHOUT the leak demand, measured heads+pump from leak primal
    wn_model, _ = build_ltown_like_pump_tank_network()
    wn_model.remove_control("pump_off")
    qv, info = _run_dual_measured(wn_model, sensors, heads, pump_m3h, scratch)
    s = qv.sum(axis=1)
    mean_sum = float(np.nanmean(s.values))
    return {
        "id": "measured_pump_leak_stable",
        "description": "Leak during stable pump operation; dual omits leak, uses measured Qp+heads",
        "actual_leak_m3h": leak_m3h,
        "result": {
            "mean_sum_m3h": mean_sum,
            "max_abs_sum_m3h": float(np.nanmax(np.abs(s.values))),
            "pump_boundary": info,
        },
        "pass_criterion": "mean_sum_m3h within [2, 8] (tracks ~5 m³/h leak)",
        "passed": 2.0 <= mean_sum <= 8.0,
        "interpretation": (
            "Virtual-flow sum should reflect the omitted leak under a matched pump BC."
        ),
    }


def scenario_leak_coincident_transition_measured(scratch: Path) -> dict[str, Any]:
    """Leak present through a pump-off transition; measured Qp from leak primal."""
    leak_m3h = 5.0
    wn, sensors = build_ltown_like_pump_tank_network()
    inject_nodal_leak(wn, "J_branch", leak_m3h)
    _res, heads, pump_m3h = _run_primal(wn, sensors)
    wn_model, _ = build_ltown_like_pump_tank_network()
    qv, info = _run_dual_measured(wn_model, sensors, heads, pump_m3h, scratch)
    s = qv.sum(axis=1)
    before = float(np.nanmean(s.iloc[1:6].values))
    after = float(np.nanmean(s.iloc[7:12].values)) if len(s) > 8 else float(s.iloc[-1])
    switch_delta = float(s.iloc[min(6, len(s) - 1)] - s.iloc[min(5, len(s) - 1)])
    return {
        "id": "measured_pump_leak_coincident_transition",
        "description": "Leak coincident with pump transition; measured PUMP_1 BC",
        "actual_leak_m3h": leak_m3h,
        "result": {
            "mean_sum_before_m3h": before,
            "mean_sum_after_m3h": after,
            "sum_delta_at_switch_m3h": switch_delta,
            "pump_boundary": info,
        },
        "pass_criterion": (
            "before/after means in [2, 8] and |switch ΔΣ| < 3 (transition not a large artifact)"
        ),
        "passed": (
            2.0 <= before <= 8.0
            and 2.0 <= after <= 8.0
            and abs(switch_delta) < 3.0
        ),
        "interpretation": (
            "Leak imprint in Σq_v should persist across the switch; measured Qp "
            "should prevent a large transition-only residual jump."
        ),
    }


def scenario_noisy_missing_pump_measured(scratch: Path) -> dict[str, Any]:
    """Noisy and missing pump measurements; check convergence and causal fill."""
    wn, sensors = build_ltown_like_pump_tank_network()
    _res, heads, pump_true = _run_primal(wn, sensors)
    rng = np.random.default_rng(0)
    noisy = []
    for i, q in enumerate(pump_true):
        if i in (3, 4):
            noisy.append(float("nan"))  # missing block
        else:
            noisy.append(float(q) + float(rng.normal(0, 1.5)))
    prep = prepare_pump_series_causal(noisy)
    try:
        qv, info = _run_dual_measured(_clone(wn, scratch), sensors, heads, prep.values_m3h, scratch)
        converged = True
        max_abs = float(np.nanmax(np.abs(qv.sum(axis=1).values)))
        err = str(info.get("error", ""))
    except Exception as exc:  # noqa: BLE001
        converged = False
        max_abs = float("nan")
        err = str(exc)
        info = {}
    return {
        "id": "measured_pump_noisy_missing",
        "description": "Noisy + missing pump samples with causal fill; matched heads, no leak",
        "actual_leak_m3h": 0.0,
        "result": {
            "converged": converged,
            "max_abs_sum_m3h": max_abs,
            "n_ffill": prep.n_ffill,
            "n_zero_impute": prep.n_zero_impute,
            "error": err,
            "pump_boundary": info,
        },
        "pass_criterion": "converged and max_abs_sum_m3h < 5 (bounded artifact under noise/ffill)",
        "passed": converged and np.isfinite(max_abs) and max_abs < 5.0,
        "interpretation": (
            "Causal fill must not look ahead; solver should still converge; Σq_v "
            "artifacts stay bounded versus a matched zero-leak case."
        ),
    }


def run_all_measured_pump_scenarios(scratch: Path) -> list[dict[str, Any]]:
    return [
        scenario_matched_transition_measured(scratch),
        scenario_leak_stable_measured(scratch),
        scenario_leak_coincident_transition_measured(scratch),
        scenario_noisy_missing_pump_measured(scratch),
    ]
