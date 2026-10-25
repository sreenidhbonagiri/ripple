"""Measured internal pump transfer for the isolated dual-model variant.

See ``PUMP1_MEASURED_BOUNDARY.md`` for the hydraulic formulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
import wntr
from wntr.network.base import LinkStatus

from .units import m3h_to_m3s

PUMP1_NAME = "PUMP_1"
EXTRACT_NODE = "n54"
TANK_NODE = "T1"
INJ_NODE = "_PUMP1_TANK_INJ"
INJ_PIPE = "_PUMP1_INJ_PIPE"
PATTERN_NAME = "MEAS_PUMP1_Q"
EXTRACT_DEMAND_CAT = "meas_pump1_extract"
INJECT_DEMAND_CAT = "meas_pump1_inject"


@dataclass(frozen=True)
class PumpSeriesPrep:
    """Causal pump series ready for EPANET patterns (m³/h)."""

    values_m3h: list[float]
    n_finite: int
    n_ffill: int
    n_zero_impute: int
    missing_mask: list[bool]  # True where original was non-finite


def prepare_pump_series_causal(pump_m3h: Sequence[float] | pd.Series) -> PumpSeriesPrep:
    """Fill non-finite pump samples causally (no look-ahead)."""
    raw = [float(x) if x is not None and np.isfinite(float(x)) else float("nan") for x in pump_m3h]
    out: list[float] = []
    missing: list[bool] = []
    last: float | None = None
    n_ffill = 0
    n_zero = 0
    n_finite = 0
    for v in raw:
        if np.isfinite(v):
            out.append(float(v))
            missing.append(False)
            last = float(v)
            n_finite += 1
        elif last is not None:
            out.append(last)
            missing.append(True)
            n_ffill += 1
        else:
            out.append(0.0)
            missing.append(True)
            n_zero += 1
    return PumpSeriesPrep(
        values_m3h=out,
        n_finite=n_finite,
        n_ffill=n_ffill,
        n_zero_impute=n_zero,
        missing_mask=missing,
    )


def _remove_controls_referencing(wn: wntr.network.WaterNetworkModel, link_name: str) -> list[str]:
    removed: list[str] = []
    for name in list(wn.control_name_list):
        ctrl = wn.get_control(name)
        text = str(ctrl).upper()
        if link_name.upper() in text:
            wn.remove_control(name)
            removed.append(name)
    return removed


def _ensure_tank_injection_junction(
    wn: wntr.network.WaterNetworkModel,
    *,
    tank_name: str,
    inj_name: str,
    inj_pipe: str,
) -> str:
    """Junction + short pipe into tank (FCV cannot sit on a tank)."""
    tank = wn.get_node(tank_name)
    if inj_name not in wn.node_name_list:
        x, y = tank.coordinates if tank.coordinates is not None else (0.0, 0.0)
        wn.add_junction(
            inj_name,
            elevation=float(tank.elevation),
            base_demand=0.0,
            coordinates=(float(x) - 1.0, float(y)),
        )
    if inj_pipe not in wn.link_name_list:
        wn.add_pipe(
            inj_pipe,
            inj_name,
            tank_name,
            length=1.0,
            diameter=0.50,
            roughness=150.0,
            minor_loss=0.0,
        )
    return inj_name


def _strip_named_demands(node, category: str) -> None:
    """Remove existing demand timeseries with this category name if present."""
    keep = []
    for ts in list(node.demand_timeseries_list):
        cat = getattr(ts, "category", None)
        if cat == category:
            continue
        keep.append(ts)
    # WNTR stores demands on the junction; clear and re-add keepers + we add new.
    node.demand_timeseries_list.clear()
    for ts in keep:
        node.demand_timeseries_list.append(ts)


def impose_measured_internal_pump_transfer(
    wn: wntr.network.WaterNetworkModel,
    pump_m3h: Sequence[float],
    *,
    pump_link: str = PUMP1_NAME,
    extract_node: str | None = None,
    tank_or_end_node: str | None = None,
    pattern_name: str = PATTERN_NAME,
) -> dict[str, Any]:
    """Close ``pump_link``, drop its controls, impose measured transfer via demand pair.

    If the pump end node is a tank, inject through ``_PUMP1_TANK_INJ`` → tank.
    If the end node is a junction, inject directly at that junction.
    """
    if pump_link not in wn.link_name_list:
        raise KeyError(f"Pump link not in network: {pump_link}")

    pump = wn.get_link(pump_link)
    start = extract_node or pump.start_node_name
    end = tank_or_end_node or pump.end_node_name

    removed = _remove_controls_referencing(wn, pump_link)
    pump.initial_status = LinkStatus.Closed

    end_node = wn.get_node(end)
    if end_node.node_type == "Tank":
        inj = _ensure_tank_injection_junction(
            wn, tank_name=end, inj_name=INJ_NODE, inj_pipe=INJ_PIPE
        )
    else:
        inj = end

    prep = prepare_pump_series_causal(pump_m3h)
    multipliers = [m3h_to_m3s(q) for q in prep.values_m3h]
    if pattern_name in wn.pattern_name_list:
        wn.get_pattern(pattern_name).multipliers = multipliers
    else:
        wn.add_pattern(pattern_name, multipliers)

    n_ex = wn.get_node(start)
    n_in = wn.get_node(inj)
    _strip_named_demands(n_ex, EXTRACT_DEMAND_CAT)
    _strip_named_demands(n_in, INJECT_DEMAND_CAT)
    # base ±1 m³/s × pattern(m³/s) → volumetric transfer Q(t)
    n_ex.add_demand(1.0, pattern_name, EXTRACT_DEMAND_CAT)
    n_in.add_demand(-1.0, pattern_name, INJECT_DEMAND_CAT)

    return {
        "pump_link": pump_link,
        "extract_node": start,
        "inject_node": inj,
        "end_node": end,
        "controls_removed": removed,
        "pump_closed": True,
        "pattern": pattern_name,
        "n_steps": len(prep.values_m3h),
        "n_pump_finite": prep.n_finite,
        "n_pump_ffill": prep.n_ffill,
        "n_pump_zero_impute": prep.n_zero_impute,
        "counts_as_external_supply": False,
    }
