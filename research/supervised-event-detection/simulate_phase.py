"""Phase-corrected synthetic scenarios — new dir only; does not touch original NPZs.

Randomizes pattern time origin; independently samples leak onset after warm-up.
Matched leak/control pairs share phase and stay in the same split.
"""

from __future__ import annotations

import json
import traceback
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
from simulate import (
    DURATION_HOURS,
    LEAK_AREA_M2,
    N_CONTROL_SCENARIOS,
    N_LEAK_SCENARIOS,
    WARMUP_HOURS,
    file_sha256,
    pipe_group,
    sample_pipes,
    _apply_demand_scale,
)

PHASE_MASTER_SEED = 20261025
PHASE_PERIOD_HOURS = 24.0  # sample origin uniformly on one day within the week pattern


@dataclass
class PhaseScenarioSpec:
    scenario_id: str
    kind: str
    seed: int
    pipe: str | None
    pipe_group: int | None
    demand_scale: float
    leak_area_m2: float | None
    leak_start_hour: float | None
    leak_end_hour: float | None
    operating_realization: int
    pattern_phase_offset_hours: float
    pair_id: str | None = None
    notes: str = ""


@dataclass
class PhaseScenarioResult:
    spec: PhaseScenarioSpec
    ok: bool
    error: str | None = None
    traceback: str | None = None
    timestamps_s: np.ndarray | None = None
    pressures: np.ndarray | None = None
    flows: np.ndarray | None = None
    levels: np.ndarray | None = None
    labels_abrupt_positive: np.ndarray | None = None
    provenance: dict = field(default_factory=dict)


def build_phase_scenario_plan(inp_path: Path = DEFAULT_INP) -> list[PhaseScenarioSpec]:
    """Sample phases i.i.d. for leaks/controls; match first N_CONTROL leaks to controls."""
    rng = np.random.default_rng(PHASE_MASTER_SEED)
    wn = wntr.network.WaterNetworkModel(str(inp_path))
    pipes = sample_pipes(rng, wn, N_LEAK_SCENARIOS)
    specs: list[PhaseScenarioSpec] = []
    op_pool = [0, 1, 2, 3]

    leak_phases: list[float] = []
    for i, pipe in enumerate(pipes):
        op = int(rng.choice(op_pool))
        demand = float(rng.choice([0.92, 0.97, 1.0, 1.03, 1.08]))
        area = float(rng.choice(LEAK_AREA_M2))
        phase = float(rng.uniform(0.0, PHASE_PERIOD_HOURS))
        leak_phases.append(phase)
        # Independent of phase: onset after warm-up on scenario wall clock
        start_h = float(rng.uniform(WARMUP_HOURS + 2, DURATION_HOURS - 10))
        end_h = float(min(DURATION_HOURS - 0.5, start_h + rng.uniform(6.0, 18.0)))
        pair_id = f"pair_{i:03d}" if i < N_CONTROL_SCENARIOS else None
        specs.append(
            PhaseScenarioSpec(
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
                pattern_phase_offset_hours=phase,
                pair_id=pair_id,
                notes=(
                    "phase-corrected abrupt leak; pattern_start randomized; "
                    "onset independent of phase"
                ),
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
        # Matched counterpart: identical phase to leak i; control demand from control pool
        op = int(rng.choice(op_pool))
        demand = float(rng.choice([0.85, 0.90, 1.10, 1.15, 1.20]))
        phase = float(leak_phases[i])  # same phase distribution point as matched leak
        specs.append(
            PhaseScenarioSpec(
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
                pattern_phase_offset_hours=phase,
                pair_id=f"pair_{i:03d}",
                notes=(
                    "phase-matched no-leak control; shares pattern_phase_offset_hours "
                    "with paired leak"
                ),
            )
        )
    return specs


def _apply_pattern_phase(wn: wntr.network.WaterNetworkModel, phase_hours: float) -> None:
    """Shift demand pattern origin; level-based pump controls follow hydraulics."""
    offset_s = float(phase_hours) * 3600.0
    wn.options.time.pattern_start = offset_s
    wn.options.time.start_clocktime = offset_s


def _run_one(spec: PhaseScenarioSpec, inp_path: Path) -> PhaseScenarioResult:
    try:
        wn = wntr.network.WaterNetworkModel(str(inp_path))
        wn.options.time.duration = int(DURATION_HOURS * 3600)
        wn.options.time.hydraulic_timestep = STEP_SECONDS
        wn.options.time.report_timestep = STEP_SECONDS
        wn.options.time.pattern_timestep = min(
            wn.options.time.pattern_timestep, STEP_SECONDS
        )
        _apply_pattern_phase(wn, spec.pattern_phase_offset_hours)

        scale = spec.demand_scale * (1.0 + 0.01 * (spec.operating_realization - 1.5))
        _apply_demand_scale(wn, scale)

        leak_start_s = leak_end_s = None
        if spec.kind == "leak_abrupt":
            assert spec.pipe and spec.leak_area_m2 and spec.leak_start_hour is not None
            link = wn.get_link(spec.pipe)
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
            # Scenario-wall intervention (not pattern-shifted), after warm-up
            pump = wn.get_link("PUMP_1")
            act = wntr.network.controls.ControlAction(pump, "status", 0)
            t0 = int((WARMUP_HOURS + 4) * 3600)
            cond = wntr.network.controls.SimTimeCondition(wn, "=", t0)
            wn.add_control(
                f"pump_off_{spec.scenario_id}", wntr.network.controls.Control(cond, act)
            )
            act2 = wntr.network.controls.ControlAction(pump, "status", 1)
            t1 = t0 + int(3 * 3600)
            cond2 = wntr.network.controls.SimTimeCondition(wn, "=", t1)
            wn.add_control(
                f"pump_on_{spec.scenario_id}", wntr.network.controls.Control(cond2, act2)
            )

        if spec.kind == "control_tank":
            rng = np.random.default_rng(spec.seed)
            jnames = list(wn.junction_name_list)
            pick = rng.choice(jnames, size=min(40, len(jnames)), replace=False)
            for jn in pick:
                j = wn.get_node(jn)
                for ts in j.demand_timeseries_list:
                    ts.base_value = float(ts.base_value) * 1.25

        sim = wntr.sim.EpanetSimulator(wn)
        res = sim.run_sim()

        P = res.node["pressure"]
        for sid in PRESSURE_SENSORS:
            if sid not in P.columns:
                raise RuntimeError(f"missing pressure node {sid}")
        pressures = P[PRESSURE_SENSORS].to_numpy(dtype=np.float64)
        fr = res.link["flowrate"]
        flows = np.column_stack(
            [fr[s].to_numpy(dtype=np.float64) * 3600.0 for s in FLOW_SENSORS]
        )
        tank = wn.get_node("T1")
        levels = (res.node["head"]["T1"] - tank.elevation).to_numpy(dtype=np.float64).reshape(
            -1, 1
        )
        T = pressures.shape[0]
        timestamps_s = np.arange(T) * STEP_SECONDS

        if spec.kind == "control_sensor":
            rng = np.random.default_rng(spec.seed)
            t0 = int((WARMUP_HOURS + 3) * STEPS_PER_HOUR)
            t1 = t0 + int(2 * STEPS_PER_HOUR)
            sens = rng.choice(len(PRESSURE_SENSORS), size=8, replace=False)
            noise = rng.normal(0.0, 1.5, size=(t1 - t0, sens.size))
            pressures = pressures.copy()
            pressures[t0:t1, sens] += noise

        labels = np.zeros(T, dtype=bool)
        if spec.kind == "leak_abrupt" and leak_start_s is not None:
            i0 = int(leak_start_s // STEP_SECONDS)
            i1 = int(min(T, i0 + 6 * STEPS_PER_HOUR))
            labels[i0:i1] = True

        return PhaseScenarioResult(
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
                "pattern_phase_offset_hours": spec.pattern_phase_offset_hours,
                "pattern_start_s": float(spec.pattern_phase_offset_hours) * 3600.0,
                "start_clocktime_s": float(spec.pattern_phase_offset_hours) * 3600.0,
                "tank_pump_controls": "level-based (unchanged; follow shifted demand)",
                "flow_unit_conversion": "wntr_m3s_times_3600_to_m3h",
                "tank_level": "head_minus_elevation_m",
                "pressure_unit": "m",
                "n_steps": T,
                "phase_master_seed": PHASE_MASTER_SEED,
            },
        )
    except Exception as e:
        return PhaseScenarioResult(
            spec=spec,
            ok=False,
            error=f"{type(e).__name__}: {e}",
            traceback=traceback.format_exc(),
            provenance={"inp": str(inp_path), "inp_sha256": file_sha256(inp_path)},
        )


def run_all_phase_scenarios(
    out_dir: Path,
    inp_path: Path = DEFAULT_INP,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Refuse to write into the original scenario directory
    if out_dir.resolve() == (Path(__file__).resolve().parent / "outputs" / "synthetic_scenarios").resolve():
        raise RuntimeError("refusing to overwrite original synthetic_scenarios/")

    specs = build_phase_scenario_plan(inp_path)
    results = []
    failures = []
    for spec in specs:
        print(
            f"Sim {spec.scenario_id} ({spec.kind}) phase={spec.pattern_phase_offset_hours:.3f}h…",
            flush=True,
        )
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
                pattern_phase_offset_hours=np.array(
                    [spec.pattern_phase_offset_hours], dtype=np.float64
                ),
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
        "experiment": "scenario_phase_correction",
        "master_seed": PHASE_MASTER_SEED,
        "phase_period_hours": PHASE_PERIOD_HOURS,
        "inp_path": str(inp_path),
        "inp_sha256": file_sha256(inp_path),
        "n_planned": len(specs),
        "n_ok": sum(1 for r in results if r["ok"]),
        "n_failed": sum(1 for r in results if not r["ok"]),
        "changes": {
            "pattern_phase": "Unif[0,24) hours → pattern_start and start_clocktime",
            "leak_onset": "independent Unif[14,38] scenario-wall hours",
            "matched_pairs": f"first {N_CONTROL_SCENARIOS} leaks paired to controls with same phase",
            "tank_pump_controls": "level-based unchanged",
        },
        "preserves_original_scenarios": True,
        "original_scenarios_path": "outputs/synthetic_scenarios/",
        "leak_sampling_note": (
            "Pipes sampled with PHASE_MASTER_SEED from L-TOWN.inp; "
            "2019 leak labels not used."
        ),
        "scenarios": results,
        "failures": failures,
    }
    (out_dir / "scenario_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
