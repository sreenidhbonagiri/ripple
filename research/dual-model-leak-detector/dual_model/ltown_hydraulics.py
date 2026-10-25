"""Primal / dual hydraulics on L-Town with measured boundary assists."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import wntr
import wntr.network.io

from .area_topology import load_pressure_sensors
from .demand_calibration import DemandModel, apply_demand_model
from .dual_builder import DualModelSpec, attach_virtual_reservoirs, sensor_elevations
from .scada_io import INP_PATH, m3h_to_m3s
from .simulate import DualSimulationResult, _extract_qv


def load_nominal_wn() -> wntr.network.WaterNetworkModel:
    return wntr.network.WaterNetworkModel(str(INP_PATH))


def clone_wn(wn: wntr.network.WaterNetworkModel, scratch: Path) -> wntr.network.WaterNetworkModel:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"wn_{id(wn)}_{np.random.randint(1e9)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def configure_time(wn: wntr.network.WaterNetworkModel, timestamps: pd.DatetimeIndex, timestep_sec: int) -> None:
    duration = int((timestamps[-1] - timestamps[0]).total_seconds())
    wn.options.time.duration = duration
    wn.options.time.hydraulic_timestep = timestep_sec
    wn.options.time.report_timestep = timestep_sec
    wn.options.time.pattern_timestep = timestep_sec
    wn.options.time.start_clocktime = (
        timestamps[0].hour * 3600 + timestamps[0].minute * 60 + timestamps[0].second
    )


def set_tank_init_from_measurement(wn: wntr.network.WaterNetworkModel, level_m: float) -> None:
    tank = wn.get_node("T1")
    level_m = float(np.clip(level_m, tank.min_level + 1e-3, tank.max_level - 1e-3))
    tank.init_level = level_m


def subsample_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Keep timestamps on the hour (and :00 of 5-min grid)."""
    return df[df.index.minute == 0]


@dataclass
class PrimalRunResult:
    pressure_m: pd.DataFrame  # columns sensors
    flow_m3h: pd.DataFrame  # p227, p235, PUMP_1
    level_m: pd.Series
    timestamps: pd.DatetimeIndex
    converged: bool
    notes: dict[str, Any]


def run_primal_window(
    wn_template: wntr.network.WaterNetworkModel,
    timestamps: pd.DatetimeIndex,
    *,
    demand_model: DemandModel | None,
    amr_lh: pd.DataFrame | None,
    levels_m: pd.Series,
    scratch: Path,
    roughness: dict[str, float] | None = None,
    clusters=None,
    timestep_sec: int = 3600,
) -> PrimalRunResult:
    """Run demand-driven EPS; tank init from first measured level; pump via INP controls."""
    from .area_topology import apply_cluster_roughness

    wn = clone_wn(wn_template, scratch)
    configure_time(wn, timestamps, timestep_sec)
    set_tank_init_from_measurement(wn, float(levels_m.iloc[0]))

    if demand_model is not None:
        apply_demand_model(wn, demand_model, timestamps, amr_lh)
    if roughness is not None and clusters is not None:
        apply_cluster_roughness(wn, clusters, roughness)

    try:
        res = wntr.sim.EpanetSimulator(wn).run_sim()
        converged = True
    except Exception as exc:  # noqa: BLE001
        return PrimalRunResult(
            pressure_m=pd.DataFrame(),
            flow_m3h=pd.DataFrame(),
            level_m=pd.Series(dtype=float),
            timestamps=timestamps,
            converged=False,
            notes={"error": str(exc)},
        )

    sensors = load_pressure_sensors()
    # Map simulation index → timestamps (WNTR uses Timedelta index from 0)
    n = min(len(res.node["pressure"]), len(timestamps))
    idx = timestamps[:n]
    P = res.node["pressure"][list(sensors)].iloc[:n].copy()
    P.index = idx
    flows = pd.DataFrame(
        {
            "p227": res.link["flowrate"]["p227"].iloc[:n].values * 3600.0,
            "p235": res.link["flowrate"]["p235"].iloc[:n].values * 3600.0,
            "PUMP_1": res.link["flowrate"]["PUMP_1"].iloc[:n].values * 3600.0,
        },
        index=idx,
    )
    # Tank water level ≈ pressure at tank node in EPANET
    level = res.node["pressure"]["T1"].iloc[:n].copy()
    level.index = idx
    return PrimalRunResult(
        pressure_m=P,
        flow_m3h=flows,
        level_m=level,
        timestamps=idx,
        converged=True,
        notes={"timestep_sec": timestep_sec, "n": n},
    )


def run_dual_window(
    wn_template: wntr.network.WaterNetworkModel,
    timestamps: pd.DatetimeIndex,
    pressures_m: pd.DataFrame,
    *,
    demand_model: DemandModel | None,
    amr_lh: pd.DataFrame | None,
    levels_m: pd.Series,
    scratch: Path,
    roughness: dict[str, float] | None = None,
    clusters=None,
    tcv_setting: float = 1e-3,
    timestep_sec: int = 3600,
    pump_boundary: str = "inp_controls",
    pump_flow_m3h: pd.Series | None = None,
) -> DualSimulationResult:
    """Dual EPS: VR heads = measured P + elevation; demands/roughness as specified.

    ``pump_boundary``:
      - ``inp_controls`` (default): INP tank-level pump open/close (baseline).
      - ``measured_pump1``: close PUMP_1, drop its controls, impose measured
        internal transfer n54→T1 (see PUMP1_MEASURED_BOUNDARY.md). Requires
        ``pump_flow_m3h`` aligned to ``timestamps``.
    """
    from .area_topology import apply_cluster_roughness
    from .pump_boundary import impose_measured_internal_pump_transfer

    if pump_boundary not in ("inp_controls", "measured_pump1"):
        raise ValueError(f"Unknown pump_boundary={pump_boundary!r}")

    sensors = load_pressure_sensors()
    wn = clone_wn(wn_template, scratch)
    configure_time(wn, timestamps, timestep_sec)
    set_tank_init_from_measurement(wn, float(levels_m.iloc[0]))
    if demand_model is not None:
        apply_demand_model(wn, demand_model, timestamps, amr_lh)
    if roughness is not None and clusters is not None:
        apply_cluster_roughness(wn, clusters, roughness)

    pump_notes: dict[str, Any] = {"pump_boundary": pump_boundary}
    if pump_boundary == "measured_pump1" and pump_flow_m3h is None:
        raise ValueError("pump_flow_m3h required when pump_boundary='measured_pump1'")

    elev = sensor_elevations(wn, sensors)
    P = pressures_m[list(sensors)].reindex(timestamps).interpolate(limit=2)
    head_ts = {s: (P[s].astype(float) + elev[s]).tolist() for s in sensors}
    spec = DualModelSpec(sensor_nodes=sensors, tcv_setting=tcv_setting)
    try:
        wd = attach_virtual_reservoirs(
            wn,
            spec,
            head_timeseries=head_ts,
            pattern_timestep_sec=timestep_sec,
            scratch_dir=scratch,
        )
        configure_time(wd, timestamps, timestep_sec)
        set_tank_init_from_measurement(wd, float(levels_m.iloc[0]))
        # Impose after VR attach so the dual clone carries the measured transfer
        # without a second INP round-trip that could drop demand categories.
        if pump_boundary == "measured_pump1":
            assert pump_flow_m3h is not None
            q_pump = pump_flow_m3h.reindex(timestamps).astype(float)
            pump_notes.update(
                impose_measured_internal_pump_transfer(wd, q_pump.tolist())
            )

        res = wntr.sim.EpanetSimulator(wd).run_sim()
        qv = _extract_qv(res.link["flowrate"], spec)
        n = min(len(qv), len(timestamps))
        qv = qv.iloc[:n].copy()
        qv.index = timestamps[:n]
        return DualSimulationResult(
            q_v_m3s=qv,
            q_v_sum_m3s=qv.sum(axis=1),
            spec=spec,
            notes={"timestep_sec": timestep_sec, "n": n, "converged": True, **pump_notes},
        )
    except Exception as exc:  # noqa: BLE001
        empty = pd.DataFrame(
            np.nan, index=timestamps, columns=list(sensors), dtype=float
        )
        return DualSimulationResult(
            q_v_m3s=empty,
            q_v_sum_m3s=empty.sum(axis=1),
            spec=spec,
            notes={
                "timestep_sec": timestep_sec,
                "n": 0,
                "converged": False,
                "error": str(exc),
                **pump_notes,
            },
        )


def pressure_metrics(sim: pd.DataFrame, meas: pd.DataFrame) -> dict[str, Any]:
    common = sim.index.intersection(meas.index)
    if len(common) == 0:
        return {"rmse_m": None, "bias_m": None, "n": 0}
    cols = [c for c in sim.columns if c in meas.columns]
    err = sim.loc[common, cols] - meas.loc[common, cols]
    return {
        "rmse_m": float(np.sqrt(np.nanmean(err.values**2))),
        "bias_m": float(np.nanmean(err.values)),
        "mae_m": float(np.nanmean(np.abs(err.values))),
        "per_sensor_rmse_m": {c: float(np.sqrt(np.nanmean(err[c].values**2))) for c in cols},
        "n": int(len(common)),
    }


def flow_metrics(sim: pd.DataFrame, meas: pd.DataFrame) -> dict[str, Any]:
    common = sim.index.intersection(meas.index)
    out: dict[str, Any] = {"n": int(len(common))}
    if len(common) == 0:
        return out
    for col in ("p227", "p235", "PUMP_1"):
        e = sim.loc[common, col] - meas.loc[common, col]
        out[col] = {
            "rmse_m3h": float(np.sqrt(np.nanmean(e.values**2))),
            "bias_m3h": float(np.nanmean(e.values)),
        }
    ext_s = sim.loc[common, "p227"] + sim.loc[common, "p235"]
    ext_m = meas.loc[common, "p227"] + meas.loc[common, "p235"]
    e = ext_s - ext_m
    out["external_sum"] = {
        "rmse_m3h": float(np.sqrt(np.nanmean(e.values**2))),
        "bias_m3h": float(np.nanmean(e.values)),
    }
    return out


def level_metrics(sim: pd.Series, meas: pd.Series) -> dict[str, Any]:
    common = sim.index.intersection(meas.index)
    if len(common) == 0:
        return {"rmse_m": None, "n": 0}
    e = sim.loc[common] - meas.loc[common]
    return {
        "rmse_m": float(np.sqrt(np.nanmean(e.values**2))),
        "bias_m": float(np.nanmean(e.values)),
        "n": int(len(common)),
    }


def virtual_flow_metrics(dual: DualSimulationResult) -> dict[str, Any]:
    qvh = dual.q_v_m3h
    s = dual.q_v_sum_m3h
    day = qvh[(qvh.index.hour >= 10) & (qvh.index.hour < 15)]
    night = qvh[(qvh.index.hour >= 0) & (qvh.index.hour < 5)]
    per = {
        c: {
            "mean_m3h": float(qvh[c].mean()),
            "std_m3h": float(qvh[c].std()),
            "abs_mean_m3h": float(qvh[c].abs().mean()),
        }
        for c in qvh.columns
    }
    return {
        "sum_mean_m3h": float(s.mean()),
        "sum_std_m3h": float(s.std()),
        "sum_abs_mean_m3h": float(s.abs().mean()),
        "mean_abs_individual_m3h": float(qvh.abs().mean().mean()),
        "cancellation_ratio": float(
            s.abs().mean() / max(qvh.abs().mean().mean() * len(qvh.columns), 1e-12)
        ),
        "day_sum_mean_m3h": float(day.sum(axis=1).mean()) if len(day) else None,
        "night_sum_mean_m3h": float(night.sum(axis=1).mean()) if len(night) else None,
        "per_sensor": per,
    }