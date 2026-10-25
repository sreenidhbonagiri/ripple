"""Run dual hydraulics and extract virtual leak flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import wntr

from .dual_builder import DualModelSpec, DualTopology, attach_virtual_reservoirs
from .units import m3s_to_m3h


@dataclass
class DualSimulationResult:
    """Virtual flows and bookkeeping for one dual run.

    ``q_v`` columns are sensor names; values are m³/s with sign convention:
    positive = flow from sensor node into the virtual reservoir (outflow residual /
    virtual leak flow), matching Steffelbauer et al. ``q_v = -q_in`` at VRs.
    """

    q_v_m3s: pd.DataFrame
    q_v_sum_m3s: pd.Series
    spec: DualModelSpec
    notes: dict

    @property
    def q_v_m3h(self) -> pd.DataFrame:
        return self.q_v_m3s * 3600.0

    @property
    def q_v_sum_m3h(self) -> pd.Series:
        return self.q_v_sum_m3s * 3600.0


def _extract_qv(
    link_flow: pd.DataFrame,
    spec: DualModelSpec,
) -> pd.DataFrame:
    cols = {}
    for s in spec.sensor_nodes:
        tcv = spec.tcv_name(s)
        # EPANET flowrate > 0 along link direction start→end = sensor→VR.
        cols[s] = link_flow[tcv].astype(float)
    return pd.DataFrame(cols, index=link_flow.index)


def run_dual_steady(
    wn_primal: wntr.network.WaterNetworkModel,
    spec: DualModelSpec,
    heads: Mapping[str, float],
    *,
    scratch_dir: Path | None = None,
) -> DualSimulationResult:
    """Single hydraulic snapshot: constant VR heads."""
    wd = attach_virtual_reservoirs(wn_primal, spec, heads=heads, scratch_dir=scratch_dir)
    # Steady: duration 0 still reports one step in EPANET via WNTR.
    wd.options.time.duration = 0
    wd.options.time.hydraulic_timestep = 3600
    wd.options.time.report_timestep = 3600
    res = wntr.sim.EpanetSimulator(wd).run_sim()
    qv = _extract_qv(res.link["flowrate"], spec)
    return DualSimulationResult(
        q_v_m3s=qv,
        q_v_sum_m3s=qv.sum(axis=1),
        spec=spec,
        notes={"mode": "steady", "topology": DualTopology(spec).__dict__},
    )


def run_dual_timeseries(
    wn_primal: wntr.network.WaterNetworkModel,
    spec: DualModelSpec,
    head_timeseries: Mapping[str, Sequence[float]],
    *,
    duration_sec: int,
    hydraulic_timestep_sec: int,
    pattern_timestep_sec: int | None = None,
    scratch_dir: Path | None = None,
) -> DualSimulationResult:
    """Extended-period dual simulation with time-varying measured heads."""
    if pattern_timestep_sec is None:
        pattern_timestep_sec = hydraulic_timestep_sec
    wd = attach_virtual_reservoirs(
        wn_primal,
        spec,
        head_timeseries=head_timeseries,
        pattern_timestep_sec=pattern_timestep_sec,
        scratch_dir=scratch_dir,
    )
    wd.options.time.duration = int(duration_sec)
    wd.options.time.hydraulic_timestep = int(hydraulic_timestep_sec)
    wd.options.time.report_timestep = int(hydraulic_timestep_sec)
    wd.options.time.pattern_timestep = int(pattern_timestep_sec)
    res = wntr.sim.EpanetSimulator(wd).run_sim()
    qv = _extract_qv(res.link["flowrate"], spec)
    return DualSimulationResult(
        q_v_m3s=qv,
        q_v_sum_m3s=qv.sum(axis=1),
        spec=spec,
        notes={
            "mode": "timeseries",
            "duration_sec": duration_sec,
            "hydraulic_timestep_sec": hydraulic_timestep_sec,
        },
    )


def summarize_qv(result: DualSimulationResult) -> dict:
    q = result.q_v_m3s.iloc[0]
    return {
        "q_v_m3s": {k: float(v) for k, v in q.items()},
        "q_v_m3h": {k: m3s_to_m3h(float(v)) for k, v in q.items()},
        "sum_m3s": float(result.q_v_sum_m3s.iloc[0]),
        "sum_m3h": m3s_to_m3h(float(result.q_v_sum_m3s.iloc[0])),
        "abs_max_m3h": m3s_to_m3h(float(np.max(np.abs(q.values)))),
    }