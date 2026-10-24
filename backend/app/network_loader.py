"""Load and serialize the BattLeDIM L-Town EPANET model via WNTR."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import wntr

from app.schemas import (
    NetworkCounts,
    NetworkLink,
    NetworkNode,
    NetworkResponse,
    NodeCoordinates,
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _node_type(node: Any) -> str:
    # Prefer WNTR's node_type (Junction/Reservoir/Tank) over concrete class names.
    ntype = str(getattr(node, "node_type", None) or type(node).__name__)
    if ntype in {"Junction", "Reservoir", "Tank"}:
        return ntype
    raise ValueError(f"Unsupported node type: {ntype}")


def _link_type(link: Any) -> str:
    # Prefer WNTR's link_type (Pipe/Pump/Valve); subclasses include HeadPump, PRValve, etc.
    ltype = str(getattr(link, "link_type", None) or type(link).__name__)
    if ltype in {"Pipe", "Pump", "Valve"}:
        return ltype
    raise ValueError(f"Unsupported link type: {ltype} ({type(link).__name__})")


def _status_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_node(node_id: str, wn: wntr.network.WaterNetworkModel) -> NetworkNode:
    node = wn.get_node(node_id)
    ntype = _node_type(node)
    coords = getattr(node, "coordinates", None)
    coordinates = None
    if coords is not None and len(coords) >= 2:
        coordinates = NodeCoordinates(x=float(coords[0]), y=float(coords[1]))

    data: dict[str, Any] = {
        "id": node_id,
        "type": ntype,
        "coordinates": coordinates,
        "elevation": _safe_float(getattr(node, "elevation", None)),
        "initial_quality": _safe_float(getattr(node, "initial_quality", None)),
        "attributes": {},
    }

    if ntype == "Junction":
        base_demand = None
        demand_pattern = None
        demand_timeseries = getattr(node, "demand_timeseries_list", None)
        if demand_timeseries:
            first = demand_timeseries[0]
            base_demand = _safe_float(getattr(first, "base_value", None))
            pattern = getattr(first, "pattern_name", None)
            demand_pattern = str(pattern) if pattern else None
        data["base_demand"] = base_demand
        data["demand_pattern"] = demand_pattern
        data["attributes"] = {
            "emitter_coefficient": _safe_float(getattr(node, "emitter_coefficient", None)),
        }
    elif ntype == "Reservoir":
        data["base_head"] = _safe_float(getattr(node, "base_head", None))
        data["attributes"] = {
            "head_pattern_name": getattr(node, "head_pattern_name", None),
        }
    elif ntype == "Tank":
        data["diameter"] = _safe_float(getattr(node, "diameter", None))
        data["min_level"] = _safe_float(getattr(node, "min_level", None))
        data["max_level"] = _safe_float(getattr(node, "max_level", None))
        data["initial_level"] = _safe_float(getattr(node, "init_level", None))
        data["min_vol"] = _safe_float(getattr(node, "min_vol", None))
        data["overflow"] = bool(getattr(node, "overflow", False))
        data["attributes"] = {
            "vol_curve_name": getattr(node, "vol_curve_name", None),
        }

    return NetworkNode(**data)


def _serialize_link(link_id: str, wn: wntr.network.WaterNetworkModel) -> NetworkLink:
    link = wn.get_link(link_id)
    ltype = _link_type(link)
    start_node = str(link.start_node_name)
    end_node = str(link.end_node_name)

    data: dict[str, Any] = {
        "id": link_id,
        "type": ltype,
        "start_node": start_node,
        "end_node": end_node,
        "status": _status_str(getattr(link, "initial_status", None)),
        "attributes": {
            "wntr_class": type(link).__name__,
        },
    }

    if ltype == "Pipe":
        data["length"] = _safe_float(getattr(link, "length", None))
        data["diameter"] = _safe_float(getattr(link, "diameter", None))
        data["roughness"] = _safe_float(getattr(link, "roughness", None))
        data["minor_loss"] = _safe_float(getattr(link, "minor_loss", None))
        data["check_valve"] = bool(getattr(link, "check_valve", False))
        data["attributes"] = {
            "bulk_coeff": _safe_float(getattr(link, "bulk_coeff", None)),
            "wall_coeff": _safe_float(getattr(link, "wall_coeff", None)),
        }
    elif ltype == "Pump":
        pump_type = getattr(link, "pump_type", None)
        data["pump_type"] = str(pump_type) if pump_type is not None else None
        data["setting"] = _safe_float(getattr(link, "base_speed", None))
        data["attributes"] = {
            "speed_pattern_name": getattr(link, "speed_pattern_name", None),
            "pump_curve_name": getattr(link, "pump_curve_name", None),
            "power": _safe_float(getattr(link, "power", None)),
        }
    elif ltype == "Valve":
        valve_type = getattr(link, "valve_type", None)
        data["valve_type"] = str(valve_type) if valve_type is not None else None
        data["diameter"] = _safe_float(getattr(link, "diameter", None))
        data["setting"] = _safe_float(getattr(link, "initial_setting", None))
        data["minor_loss"] = _safe_float(getattr(link, "minor_loss", None))
        data["attributes"] = {}

    return NetworkLink(**data)


def build_network_response(inp_path: Path) -> NetworkResponse:
    if not inp_path.is_file():
        raise FileNotFoundError(
            f"EPANET model not found at {inp_path}. "
            "Run scripts/download_ltown.sh first."
        )

    wn = wntr.network.WaterNetworkModel(str(inp_path))

    nodes = [_serialize_node(nid, wn) for nid in wn.node_name_list]
    links = [_serialize_link(lid, wn) for lid in wn.link_name_list]

    counts = NetworkCounts(
        nodes=len(nodes),
        links=len(links),
        junctions=sum(1 for n in nodes if n.type == "Junction"),
        reservoirs=sum(1 for n in nodes if n.type == "Reservoir"),
        tanks=sum(1 for n in nodes if n.type == "Tank"),
        pipes=sum(1 for l in links if l.type == "Pipe"),
        pumps=sum(1 for l in links if l.type == "Pump"),
        valves=sum(1 for l in links if l.type == "Valve"),
    )

    # WNTR often stores the absolute INP path in `name`; prefer a short model label.
    raw_name = str(wn.name) if wn.name else ""
    if not raw_name or "/" in raw_name or "\\" in raw_name or raw_name.endswith(".inp"):
        name = inp_path.stem
    else:
        name = raw_name
    return NetworkResponse(
        name=name,
        source=str(inp_path.name),
        counts=counts,
        nodes=nodes,
        links=links,
    )


@lru_cache
def get_cached_network(inp_path_str: str) -> NetworkResponse:
    return build_network_response(Path(inp_path_str))
