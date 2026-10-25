"""Bounded WNTR/EPANET synthetic scenarios on official L-TOWN.inp.

Pipe locations are sampled with a fixed seed and **without** consulting 2019
leak labels. Failures are recorded, not silently dropped.
"""

from __future__ import annotations

import hashlib
import json
import traceback
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import wntr

from schema import (
    DEFAULT_INP,
    FLOW_SENSORS,
    LEVEL_SENSORS,
    PRESSURE_SENSORS,
    STEP_SECONDS,
    STEPS_PER_HOUR,
)

# Pilot bounds (registered small budget — do not expand quietly)
MASTER_SEED = 20261024
N_LEAK_SCENARIOS = 24
N_CONTROL_SCENARIOS = 16
DURATION_HOURS = 48
WARMUP_HOURS = 12  # continuous trajectory warm-up inside the 48 h
LEAK_AREA_M2 = (  # diameters ~8–22 mm → area
    0.00005,
    0.00010,
    0.00020,
    0.00035,
)


@dataclass
class ScenarioSpec:
    scenario_id: str
    kind: str  # leak_abrupt | control_demand | control_pump | control_sensor | control_tank
    seed: int
    pipe: str | None
    pipe_group: int | None
    demand_scale: float
    leak_area_m2: float | None
    leak_start_hour: float | None
    leak_end_hour: float | None
    operating_realization: int
    notes: str = ""


@dataclass
class ScenarioResult:
    spec: ScenarioSpec
    ok: bool
    error: str | None = None
    traceback: str | None = None
    timestamps_s: np.ndarray | None = None
    pressures: np.ndarray | None = None  # (T, 33) m
    flows: np.ndarray | None = None  # (T, 3) m3/h
    levels: np.ndarray | None = None  # (T, 1) m
    labels_abrupt_positive: np.ndarray | None = None  # (T,) bool credit window
    provenance: dict = field(default_factory=dict)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pipe_group(pipe: str, n_groups: int = 5) -> int:
    """Stable group id from pipe name — not from measured leak labels."""
    h = hashlib.sha256(pipe.encode()).hexdigest()
    return int(h[:8], 16) % n_groups


def sample_pipes(rng: np.random.Generator, wn: wntr.network.WaterNetworkModel, n: int) -> list[str]:
    """Sample distinct pipes without consulting 2019 (or any) leak labels."""
    pipes = list(wn.pipe_name_list)
    # Exclude tiny connectors if diameter missing — keep all official pipes
    choice = rng.choice(len(pipes), size=min(n, len(pipes)), replace=False)
    return [pipes[i] for i in choice]


def build_scenario_plan(inp_path: Path = DEFAULT_INP) -> list[ScenarioSpec]:
    rng = np.random.default_rng(MASTER_SEED)
    wn = wntr.network.WaterNetworkModel(str(inp_path))
    pipes = sample_pipes(rng, wn, N_LEAK_SCENARIOS)
    specs: list[ScenarioSpec] = []
    op_pool = [0, 1, 2, 3]  # distinct demand/operating realizations

    for i, pipe in enumerate(pipes):
        op = int(rng.choice(op_pool))
        demand = float(rng.choice([0.92, 0.97, 1.0, 1.03, 1.08]))
        area = float(rng.choice(LEAK_AREA_M2))
        # Leak mid-trajectory after warm-up — not at t=0 / restart
        start_h = float(rng.uniform(WARMUP_HOURS + 2, DURATION_HOURS - 10))
        end_h = float(min(DURATION_HOURS - 0.5, start_h + rng.uniform(6.0, 18.0)))
        specs.append(
            ScenarioSpec(
                scenario_id=f"leak_{i:03d}_{pipe}",
                kind="leak_abrupt",
                seed=int(rng.integers(0, 2**31 - 1)),
                pipe=pipe,
                pipe_group=pipe_group(pipe),
                demand_scale=demand,
                leak_area_m2=area,
                leak_start_hour=start_h,
                leak_end_hour=end_h,
                operating_realization=op,
                notes="abrupt leak on continuous trajectory after warm-up",
            )
        )

    control_kinds = (
        ["control_demand"] * 5
        + ["control_pump"] * 4
        + ["control_tank"] * 3
        + ["control_sensor"] * 4
    )
    rng.shuffle(control_kinds)
    for i, kind in enumerate(control_kinds[:N_CONTROL_SCENARIOS]):
        op = int(rng.choice(op_pool))
        demand = float(rng.choice([0.85, 0.90, 1.10, 1.15, 1.20]))
        specs.append(
            ScenarioSpec(
                scenario_id=f"ctrl_{i:03d}_{kind}",
                kind=kind,
                seed=int(rng.integers(0, 2**31 - 1)),
                pipe=None,
                pipe_group=None,
                demand_scale=demand,
                leak_area_m2=None,
                leak_start_hour=None,
                leak_end_hour=None,
                operating_realization=op,
                notes="difficult no-new-leak control",
            )
        )
    return specs


def _apply_demand_scale(wn, scale: float) -> None:
    for _, j in wn.junctions():
        for ts in j.demand_timeseries_list:
            ts.base_value = float(ts.base_value) * scale


def _run_one(spec: ScenarioSpec, inp_path: Path) -> ScenarioResult:
    try:
        wn = wntr.network.WaterNetworkModel(str(inp_path))
        wn.options.time.duration = int(DURATION_HOURS * 3600)
        wn.options.time.hydraulic_timestep = STEP_SECONDS
        wn.options.time.report_timestep = STEP_SECONDS
        wn.options.time.pattern_timestep = min(
            wn.options.time.pattern_timestep, STEP_SECONDS
        )

        # Operating realization: mild pattern time shift via demand scale + noise seed
        scale = spec.demand_scale * (1.0 + 0.01 * (spec.operating_realization - 1.5))
        _apply_demand_scale(wn, scale)

        leak_start_s = leak_end_s = None
        if spec.kind == "leak_abrupt":
            assert spec.pipe and spec.leak_area_m2 and spec.leak_start_hour is not None
            link = wn.get_link(spec.pipe)
            # Prefer start node if junction
            node_id = link.start_node_name
            node = wn.get_node(node_id)
            if node.node_type != "Junction":
                node_id = link.end_node_name
                node = wn.get_node(node_id)
            if node.node_type != "Junction":
                raise RuntimeError(f"no junction endpoint for pipe {spec.pipe}")
            leak_start_s = int(spec.leak_start_hour * 3600)
            leak_end_s = int(spec.leak_end_hour * 3600)
            node.add_leak(
                wn, area=float(spec.leak_area_m2), start_time=leak_start_s, end_time=leak_end_s
            )

        if spec.kind == "control_pump":
            # Force pump off for a mid-window block via control
            pump = wn.get_link("PUMP_1")
            act = wntr.network.controls.ControlAction(pump, "status", 0)
            t0 = int((WARMUP_HOURS + 4) * 3600)
            cond = wntr.network.controls.SimTimeCondition(wn, "=", t0)
            wn.add_control(f"pump_off_{spec.scenario_id}", wntr.network.controls.Control(cond, act))
            act2 = wntr.network.controls.ControlAction(pump, "status", 1)
            t1 = t0 + int(3 * 3600)
            cond2 = wntr.network.controls.SimTimeCondition(wn, "=", t1)
            wn.add_control(
                f"pump_on_{spec.scenario_id}", wntr.network.controls.Control(cond2, act2)
            )

        if spec.kind == "control_tank":
            # Demand spike that stresses tank (already scaled); add second mid-run scale via emitters — skip if unsupported
            # Use an additional demand multiplier on a subset of junctions
            rng = np.random.default_rng(spec.seed)
            jnames = list(wn.junction_name_list)
            pick = rng.choice(jnames, size=min(40, len(jnames)), replace=False)
            for jn in pick:
                j = wn.get_node(jn)
                for ts in j.demand_timeseries_list:
                    ts.base_value = float(ts.base_value) * 1.25

        sim = wntr.sim.EpanetSimulator(wn)
        res = sim.run_sim()

        # Extract SCADA-aligned channels
        P = res.node["pressure"]
        for sid in PRESSURE_SENSORS:
            if sid not in P.columns:
                raise RuntimeError(f"missing pressure node {sid}")
        pressures = P[PRESSURE_SENSORS].to_numpy(dtype=np.float64)

        fr = res.link["flowrate"]
        flows = np.column_stack(
            [fr[s].to_numpy(dtype=np.float64) * 3600.0 for s in FLOW_SENSORS]
        )  # m3/s → m3/h

        tank = wn.get_node("T1")
        level = (res.node["head"]["T1"] - tank.elevation).to_numpy(dtype=np.float64)
        levels = level.reshape(-1, 1)

        T = pressures.shape[0]
        timestamps_s = np.arange(T) * STEP_SECONDS

        # Sensor disturbance control: additive noise on pressures only (post-sim)
        if spec.kind == "control_sensor":
            rng = np.random.default_rng(spec.seed)
            # Mid-window burst disturbance on a random subset of sensors
            t0 = int((WARMUP_HOURS + 3) * STEPS_PER_HOUR)
            t1 = t0 + int(2 * STEPS_PER_HOUR)
            sens = rng.choice(len(PRESSURE_SENSORS), size=8, replace=False)
            noise = rng.normal(0.0, 1.5, size=(t1 - t0, sens.size))
            pressures = pressures.copy()
            pressures[t0:t1, sens] += noise

        # Abrupt positive credit: [leak_start, leak_start+6h]
        labels = np.zeros(T, dtype=bool)
        if spec.kind == "leak_abrupt" and leak_start_s is not None:
            i0 = int(leak_start_s // STEP_SECONDS)
            i1 = int(min(T, i0 + 6 * STEPS_PER_HOUR))
            labels[i0:i1] = True

        return ScenarioResult(
            spec=spec,
            ok=True,
            timestamps_s=timestamps_s,
            pressures=pressures,
            flows=flows,
            levels=levels,
            labels_abrupt_positive=labels,
            provenance={
                "inp": str(inp_path),
                "inp_sha256": file_sha256(inp_path),
                "simulator": "wntr.sim.EpanetSimulator",
                "duration_hours": DURATION_HOURS,
                "step_seconds": STEP_SECONDS,
                "flow_unit_conversion": "wntr_m3s_times_3600_to_m3h",
                "tank_level": "head_minus_elevation_m",
                "pressure_unit": "m",
                "n_steps": T,
            },
        )
    except Exception as e:
        return ScenarioResult(
            spec=spec,
            ok=False,
            error=f"{type(e).__name__}: {e}",
            traceback=traceback.format_exc(),
            provenance={"inp": str(inp_path), "inp_sha256": file_sha256(inp_path)},
        )


def run_all_scenarios(
    out_dir: Path,
    inp_path: Path = DEFAULT_INP,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = build_scenario_plan(inp_path)
    results = []
    failures = []
    for spec in specs:
        print(f"Sim {spec.scenario_id} ({spec.kind})…", flush=True)
        r = _run_one(spec, inp_path)
        meta = {
            "spec": asdict(spec),
            "ok": r.ok,
            "error": r.error,
            "provenance": r.provenance,
        }
        if r.ok:
            npz_path = out_dir / f"{spec.scenario_id}.npz"
            np.savez_compressed(
                npz_path,
                timestamps_s=r.timestamps_s,
                pressures=r.pressures,
                flows=r.flows,
                levels=r.levels,
                labels_abrupt_positive=r.labels_abrupt_positive,
            )
            meta["npz"] = npz_path.name
            meta["shape"] = {
                "pressures": list(r.pressures.shape),
                "flows": list(r.flows.shape),
                "levels": list(r.levels.shape),
            }
            results.append(meta)
        else:
            meta["traceback"] = r.traceback
            failures.append(meta)
            results.append(meta)
            print(f"  FAIL {r.error}", flush=True)

    summary = {
        "master_seed": MASTER_SEED,
        "inp_path": str(inp_path),
        "inp_sha256": file_sha256(inp_path),
        "n_planned": len(specs),
        "n_ok": sum(1 for r in results if r["ok"]),
        "n_failed": sum(1 for r in results if not r["ok"]),
        "leak_sampling_note": (
            "Pipes sampled with MASTER_SEED from L-TOWN.inp pipe list; "
            "2019 leak labels were not read or used for inclusion/exclusion."
        ),
        "similarity_note": (
            "All scenarios share the same nominal L-TOWN.inp topology and patterns; "
            "they differ by pipe, leak area, demand scale, operating_realization, "
            "and control interventions. Residual hydraulic similarity remains."
        ),
        "scenarios": results,
        "failures": failures,
    }
    (out_dir / "scenario_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
