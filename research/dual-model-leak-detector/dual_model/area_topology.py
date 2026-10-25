"""L-Town area partitions and roughness cluster membership."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import wntr
import yaml
from pathlib import Path

from .scada_io import RAW


def load_pressure_sensors() -> tuple[str, ...]:
    meta = yaml.safe_load((RAW / "sensors_metadata.yaml").read_text())
    return tuple(meta["pressure_sensors"])


def load_amr_nodes() -> tuple[str, ...]:
    cfg = yaml.safe_load((RAW / "dataset_configuration.yaml").read_text())
    return tuple(cfg["amrs"])


def _adjacency(wn: wntr.network.WaterNetworkModel) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for lname in wn.link_name_list:
        link = wn.get_link(lname)
        a, b = link.start_node_name, link.end_node_name
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def area_c_junctions(wn: wntr.network.WaterNetworkModel) -> set[str]:
    """Junctions on the tank side of PUMP_1 (Area C)."""
    adj = _adjacency(wn)
    seen: set[str] = set()
    q: deque[str] = deque(["T1"])
    while q:
        u = q.popleft()
        if u in seen:
            continue
        seen.add(u)
        for v in adj.get(u, []):
            if {u, v} == {"n54", "T1"}:
                continue  # do not cross pump into Area A
            if v not in seen:
                q.append(v)
    return {n for n in seen if n in wn.junction_name_list}


def area_b_junctions(wn: wntr.network.WaterNetworkModel) -> set[str]:
    """Junctions downstream of PRV-3 (n229→n226) — Area B."""
    adj = _adjacency(wn)
    if "PRV-3" not in wn.link_name_list:
        return set()
    start = wn.get_link("PRV-3").end_node_name
    seen: set[str] = set()
    q: deque[str] = deque([start])
    while q:
        u = q.popleft()
        if u in seen:
            continue
        seen.add(u)
        for v in adj.get(u, []):
            if v == "n229":
                continue
            if v not in seen:
                q.append(v)
    return {n for n in seen if n in wn.junction_name_list}


@dataclass(frozen=True)
class RoughnessCluster:
    name: str
    pipe_names: tuple[str, ...]
    x0: float  # initial HW


def build_roughness_clusters(wn: wntr.network.WaterNetworkModel) -> list[RoughnessCluster]:
    """Six clusters adapted to the local L-TOWN.inp (see DEPARTURES).

    Paper used diameter corrections + material/zone grouping with initial C in
    {90,120,140,146}. Local INP already lists discrete diameters with C∈{120,140}.
    We partition by Area C / Area B / Zone A (diameter, C0) without OD→ID edits.
    """
    ac = area_c_junctions(wn)
    ab = area_b_junctions(wn)

    buckets: dict[str, list[str]] = {
        "C_area_c": [],
        "B_area_b": [],
        "A_d100_c120": [],
        "A_d100_c140": [],
        "A_d150_200": [],
        "A_plastic_small": [],
    }
    x0: dict[str, float] = {}

    for pname in wn.pipe_name_list:
        pipe = wn.get_link(pname)
        d_mm = int(round(pipe.diameter * 1000))
        c0 = float(pipe.roughness)
        u, v = pipe.start_node_name, pipe.end_node_name
        # Area membership by endpoints (junctions); reservoir pipes → Zone A default
        ends = {u, v}
        if ends & ac and not (ends & {"R1", "R2", "n54"}):
            # pipe touches Area C junction
            if u in ac or v in ac:
                buckets["C_area_c"].append(pname)
                x0.setdefault("C_area_c", c0)
                continue
        if u in ab or v in ab:
            buckets["B_area_b"].append(pname)
            x0.setdefault("B_area_b", c0)
            continue
        if d_mm in (63, 75, 160, 225):
            buckets["A_plastic_small"].append(pname)
            x0.setdefault("A_plastic_small", c0)
        elif d_mm == 100 and abs(c0 - 120) < 1:
            buckets["A_d100_c120"].append(pname)
            x0.setdefault("A_d100_c120", c0)
        elif d_mm == 100:
            buckets["A_d100_c140"].append(pname)
            x0.setdefault("A_d100_c140", c0)
        else:
            buckets["A_d150_200"].append(pname)
            x0.setdefault("A_d150_200", c0)

    clusters = []
    for name, pipes in buckets.items():
        if not pipes:
            continue
        clusters.append(RoughnessCluster(name=name, pipe_names=tuple(pipes), x0=x0[name]))
    return clusters


def apply_cluster_roughness(
    wn: wntr.network.WaterNetworkModel,
    clusters: list[RoughnessCluster],
    values: dict[str, float],
) -> None:
    for cl in clusters:
        c = float(values[cl.name])
        for pname in cl.pipe_names:
            wn.get_link(pname).roughness = c