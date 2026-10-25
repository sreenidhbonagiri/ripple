"""Construct the dual hydraulic network (virtual reservoirs at sensors).

Published construction (Steffelbauer et al. 2022; Campbell et al. 2024):

- At each pressure-sensor junction, attach a Throttle Control Valve (TCV) to a
  virtual reservoir (VR).
- Fix the VR total head to the *measured hydraulic head*
  ``H_meas = P_meas + z_sensor`` (pressure head + elevation).
- Use a sufficiently small but nonzero TCV loss coefficient so the primal and
  dual networks are numerically (not mathematically) equivalent when the model
  matches the measurements.
- Virtual leak flow ``q_v`` is the flow through the TCV from the sensor node
  toward the VR (positive = outflow leaving the physical network into the VR).

Paper notation: ``[q_v]_i = -[q_in]_{i+n_f}`` (outflow to the virtual reservoir).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd
import wntr


DEFAULT_TCV_SETTING = 1.0e-3  # dimensionless TCV loss coefficient K
DEFAULT_TCV_DIAMETER_M = 0.10


@dataclass(frozen=True)
class DualModelSpec:
    """Engineering choices for dual construction (declared before evaluation)."""

    sensor_nodes: tuple[str, ...]
    tcv_setting: float = DEFAULT_TCV_SETTING
    tcv_diameter_m: float = DEFAULT_TCV_DIAMETER_M
    vr_prefix: str = "VR_"
    tcv_prefix: str = "TCV_"
    # EPANET multiplies pattern × base_head; use base_head=1 and pattern=H.
    reservoir_base_head: float = 1.0

    def vr_name(self, sensor: str) -> str:
        return f"{self.vr_prefix}{sensor}"

    def tcv_name(self, sensor: str) -> str:
        return f"{self.tcv_prefix}{sensor}"


def pressure_to_head(
    pressure_m: float | np.ndarray | pd.Series,
    elevation_m: float | np.ndarray | pd.Series,
) -> float | np.ndarray | pd.Series:
    """Convert pressure head (m) + elevation (m) → absolute hydraulic head (m)."""
    return pressure_m + elevation_m


def _clone_network(wn: wntr.network.WaterNetworkModel, scratch: Path | None = None) -> wntr.network.WaterNetworkModel:
    """Deep-copy via INP round-trip (WNTR in-memory deepcopy is unreliable)."""
    scratch = Path(scratch) if scratch is not None else Path("/tmp")
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"_primal_clone_{id(wn)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def attach_virtual_reservoirs(
    wn_primal: wntr.network.WaterNetworkModel,
    spec: DualModelSpec,
    *,
    heads: Mapping[str, float] | None = None,
    head_timeseries: Mapping[str, Sequence[float]] | None = None,
    pattern_timestep_sec: int | None = None,
    scratch_dir: Path | None = None,
) -> wntr.network.WaterNetworkModel:
    """Return a dual network cloned from ``wn_primal`` with VR+TCV at sensors.

    Provide either:
      - ``heads``: constant absolute hydraulic head per sensor (steady / snapshot), or
      - ``head_timeseries``: sequence of absolute heads per sensor (EPS).

    When ``head_timeseries`` is used, each VR gets ``base_head=1`` and a head
    pattern whose values are the absolute heads (EPANET multiplies pattern × base).
    """
    if (heads is None) == (head_timeseries is None):
        raise ValueError("Provide exactly one of heads or head_timeseries")

    missing = [s for s in spec.sensor_nodes if s not in wn_primal.node_name_list]
    if missing:
        raise KeyError(f"Sensor nodes not in network: {missing}")

    wd = _clone_network(wn_primal, scratch_dir)

    if head_timeseries is not None:
        n = len(next(iter(head_timeseries.values())))
        for s, series in head_timeseries.items():
            if len(series) != n:
                raise ValueError(f"Head series length mismatch for {s}")
        if pattern_timestep_sec is None:
            pattern_timestep_sec = int(wd.options.time.pattern_timestep)
        # Ensure pattern timestep matches series cadence expectation of caller.
        wd.options.time.pattern_timestep = int(pattern_timestep_sec)

    for sensor in spec.sensor_nodes:
        node = wd.get_node(sensor)
        x, y = node.coordinates if node.coordinates is not None else (0.0, 0.0)
        vr = spec.vr_name(sensor)
        tcv = spec.tcv_name(sensor)
        if vr in wd.node_name_list or tcv in wd.link_name_list:
            raise ValueError(f"Virtual names collide with existing network: {vr}/{tcv}")

        if heads is not None:
            H = float(heads[sensor])
            wd.add_reservoir(vr, base_head=H, coordinates=(x, y + 5.0))
        else:
            assert head_timeseries is not None
            pat_name = f"HPAT_{sensor}"
            series = [float(v) for v in head_timeseries[sensor]]
            # EPANET patterns need duration coverage; pad last value if needed.
            wd.add_pattern(pat_name, series)
            wd.add_reservoir(
                vr,
                base_head=spec.reservoir_base_head,
                head_pattern=pat_name,
                coordinates=(x, y + 5.0),
            )

        # TCV: start=sensor (network), end=VR. Setting = loss coefficient K.
        # minor_loss left at 0; Campbell et al. (2024) use TCV settings for K.
        wd.add_valve(
            tcv,
            sensor,
            vr,
            diameter=spec.tcv_diameter_m,
            valve_type="TCV",
            minor_loss=0.0,
            initial_setting=spec.tcv_setting,
        )

    return wd


def sensor_elevations(wn: wntr.network.WaterNetworkModel, sensors: Iterable[str]) -> dict[str, float]:
    return {s: float(wn.get_node(s).elevation) for s in sensors}


def heads_from_pressure_frame(
    pressure_m: pd.DataFrame,
    elevations: Mapping[str, float],
    sensors: Sequence[str],
) -> dict[str, list[float]]:
    """Build absolute-head timeseries dict from a pressure DataFrame (columns=sensors)."""
    out: dict[str, list[float]] = {}
    for s in sensors:
        z = float(elevations[s])
        out[s] = (pressure_m[s].astype(float) + z).tolist()
    return out


@dataclass
class DualTopology:
    """Book-keeping for virtual assets attached to a dual network."""

    spec: DualModelSpec
    tcv_names: tuple[str, ...] = field(init=False)
    vr_names: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.tcv_names = tuple(self.spec.tcv_name(s) for s in self.spec.sensor_nodes)
        self.vr_names = tuple(self.spec.vr_name(s) for s in self.spec.sensor_nodes)