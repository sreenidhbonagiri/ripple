"""Controlled synthetic networks for mechanism verification (not L-Town)."""

from __future__ import annotations

import wntr

from .units import m3h_to_m3s


def build_branched_three_sensor_network(
    *,
    duration_sec: int = 6 * 3600,
    timestep_sec: int = 3600,
    reservoir_head_m: float = 100.0,
    elevation_m: float = 50.0,
    demand_j1_m3h: float = 10.0,
    demand_j2_m3h: float = 10.0,
    demand_j3_m3h: float = 5.0,
    roughness: float = 130.0,
) -> tuple[wntr.network.WaterNetworkModel, tuple[str, ...]]:
    """R → J1 → J2 → J3 with pressure sensors at all three junctions."""
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.inpfile_units = "CMH"
    wn.options.hydraulic.headloss = "H-W"
    wn.options.time.duration = duration_sec
    wn.options.time.hydraulic_timestep = timestep_sec
    wn.options.time.report_timestep = timestep_sec
    wn.options.time.pattern_timestep = timestep_sec

    n_steps = duration_sec // timestep_sec + 1
    wn.add_pattern("pat", [1.0] * max(n_steps, 2))
    wn.add_reservoir("R", base_head=reservoir_head_m, coordinates=(0.0, 0.0))
    wn.add_junction(
        "J1",
        elevation=elevation_m,
        base_demand=m3h_to_m3s(demand_j1_m3h),
        demand_pattern="pat",
        coordinates=(100.0, 0.0),
    )
    wn.add_junction(
        "J2",
        elevation=elevation_m,
        base_demand=m3h_to_m3s(demand_j2_m3h),
        demand_pattern="pat",
        coordinates=(200.0, 0.0),
    )
    wn.add_junction(
        "J3",
        elevation=elevation_m,
        base_demand=m3h_to_m3s(demand_j3_m3h),
        demand_pattern="pat",
        coordinates=(300.0, 0.0),
    )
    wn.add_pipe("P1", "R", "J1", length=500.0, diameter=0.20, roughness=roughness)
    wn.add_pipe("P2", "J1", "J2", length=500.0, diameter=0.15, roughness=roughness)
    wn.add_pipe("P3", "J2", "J3", length=500.0, diameter=0.10, roughness=roughness)
    return wn, ("J1", "J2", "J3")


def build_tank_pump_network(
    *,
    duration_sec: int = 12 * 3600,
    timestep_sec: int = 3600,
    pump_power_kw: float = 5.0,
) -> tuple[wntr.network.WaterNetworkModel, tuple[str, ...]]:
    """Reservoir → pump → J1 → J2 → tank; sensors at J1, J2.

    A timed control turns the pump off at t = 6 h so dual flows can be checked
    across a pump / tank boundary transition with a correctly specified model.
    """
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.inpfile_units = "CMH"
    wn.options.hydraulic.headloss = "H-W"
    wn.options.time.duration = duration_sec
    wn.options.time.hydraulic_timestep = timestep_sec
    wn.options.time.report_timestep = timestep_sec
    wn.options.time.pattern_timestep = timestep_sec

    n_steps = duration_sec // timestep_sec + 1
    wn.add_pattern("pat", [1.0] * max(n_steps, 2))

    wn.add_reservoir("R", base_head=80.0, coordinates=(0.0, 0.0))
    wn.add_junction("J0", elevation=50.0, base_demand=0.0, coordinates=(50.0, 0.0))
    wn.add_junction(
        "J1",
        elevation=55.0,
        base_demand=m3h_to_m3s(8.0),
        demand_pattern="pat",
        coordinates=(150.0, 0.0),
    )
    wn.add_junction(
        "J2",
        elevation=55.0,
        base_demand=m3h_to_m3s(4.0),
        demand_pattern="pat",
        coordinates=(250.0, 0.0),
    )
    wn.add_tank(
        "T1",
        elevation=60.0,
        init_level=3.0,
        min_level=0.5,
        max_level=6.0,
        diameter=10.0,
        coordinates=(350.0, 0.0),
    )

    wn.add_pipe("P_R_J0", "R", "J0", length=50.0, diameter=0.25, roughness=130.0)
    wn.add_pump(
        "PUMP",
        "J0",
        "J1",
        pump_type="POWER",
        pump_parameter=pump_power_kw,
    )
    wn.add_pipe("P_J1_J2", "J1", "J2", length=400.0, diameter=0.15, roughness=130.0)
    wn.add_pipe("P_J2_T", "J2", "T1", length=200.0, diameter=0.15, roughness=130.0)

    pump = wn.get_link("PUMP")
    act_off = wntr.network.controls.ControlAction(pump, "status", 0)
    cond = wntr.network.controls.SimTimeCondition(wn, ">=", 6 * 3600)
    wn.add_control("pump_off", wntr.network.controls.Control(cond, act_off))

    return wn, ("J1", "J2")


def inject_nodal_leak(
    wn: wntr.network.WaterNetworkModel,
    node_name: str,
    leak_m3h: float,
) -> float:
    """Add a constant demand-driven leak (m³/h) at a junction. Returns leak m³/s.

    This is a demand-driven leak (not pressure-dependent emitter). The papers
    likewise treat diagnosed leaks as fixed outflows for dual analysis, while
    noting BattLeDIM generation used pressure-dependent leaks — a documented
    departure for synthetic truth here is that we *know* the exact discharge.
    """
    q = m3h_to_m3s(leak_m3h)
    node = wn.get_node(node_name)
    if not node.demand_timeseries_list:
        raise ValueError(f"Node {node_name} has no demand timeseries to augment")
    node.demand_timeseries_list[0].base_value = float(node.demand_timeseries_list[0].base_value) + q
    return q


def scale_all_demands(wn: wntr.network.WaterNetworkModel, factor: float) -> None:
    for name in wn.junction_name_list:
        node = wn.get_node(name)
        for ts in node.demand_timeseries_list:
            ts.base_value = float(ts.base_value) * factor


def scale_all_roughness(wn: wntr.network.WaterNetworkModel, factor: float) -> None:
    for name in wn.pipe_name_list:
        pipe = wn.get_link(name)
        pipe.roughness = float(pipe.roughness) * factor


def shift_sensor_datum(
    heads: dict[str, float],
    sensor: str,
    delta_m: float,
) -> dict[str, float]:
    """Bias one sensor's absolute head (elevation / datum error)."""
    out = dict(heads)
    out[sensor] = float(out[sensor]) + float(delta_m)
    return out