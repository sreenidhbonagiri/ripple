"""
Coordinated investigation evidence helpers (Milestone 3).

Mappings verified against official L-TOWN.inp:
  - p227: Pipe R1 (reservoir) → n303 — external inflow
  - p235: Pipe R2 (reservoir) → n336 — external inflow
  - PUMP_1: Pump n54 → T1 — internal tank transfer (not external supply)
  - T1: Tank level sensor

Describes observations only — no leak diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.replay import FRESH_SECONDS, replay_snapshot
from app.schemas import SnapshotObservation

# Verified against L-TOWN.inp (see module docstring)
EXTERNAL_INFLOW_IDS = ("p227", "p235")
INTERNAL_TRANSFER_ID = "PUMP_1"
TANK_LEVEL_ID = "T1"

COMPARE_OFFSET = timedelta(minutes=30)
FreshnessStatus = Literal["current", "stale", "missing"]


@dataclass(frozen=True)
class Point:
    ts: datetime
    value: float


@dataclass(frozen=True)
class PressureComparison:
    available: bool
    cursor: datetime
    prior_cursor: datetime
    current_value: float | None
    current_ts: datetime | None
    current_status: FreshnessStatus
    prior_value: float | None
    prior_ts: datetime | None
    prior_status: FreshnessStatus
    delta_m: float | None
    unavailable_reason: str | None


def freshness_at(observation_ts: datetime | None, at: datetime) -> FreshnessStatus:
    if observation_ts is None:
        return "missing"
    if observation_ts > at:
        raise ValueError("observation_ts must be <= comparison time")
    age = (at - observation_ts).total_seconds()
    return "current" if age <= FRESH_SECONDS else "stale"


def latest_at_or_before(points: list[Point], at: datetime) -> Point | None:
    """Latest raw point with ts <= at (no interpolation)."""
    chosen: Point | None = None
    for p in points:
        if p.ts > at:
            break
        chosen = p
    return chosen


def pressure_change_30m(points: list[Point], cursor: datetime) -> PressureComparison:
    """
    Compare selected pressure at cursor vs 30 minutes earlier.

    Both ends must be fresh (current) relative to their comparison times;
    otherwise the comparison is unavailable. Never labels a leak.
    """
    # Ensure chronological order without assuming caller sorted
    ordered = sorted(points, key=lambda p: p.ts)
    # Cursor-safety: ignore any future points if present
    ordered = [p for p in ordered if p.ts <= cursor]

    prior_cursor = cursor - COMPARE_OFFSET
    current = latest_at_or_before(ordered, cursor)
    prior = latest_at_or_before(ordered, prior_cursor)

    current_status = freshness_at(current.ts if current else None, cursor)
    prior_status = freshness_at(prior.ts if prior else None, prior_cursor)

    if current_status != "current" or prior_status != "current":
        reasons = []
        if current_status == "missing":
            reasons.append("current observation missing")
        elif current_status == "stale":
            reasons.append("current observation stale")
        if prior_status == "missing":
            reasons.append("prior (−30 min) observation missing")
        elif prior_status == "stale":
            reasons.append("prior (−30 min) observation stale")
        return PressureComparison(
            available=False,
            cursor=cursor,
            prior_cursor=prior_cursor,
            current_value=current.value if current else None,
            current_ts=current.ts if current else None,
            current_status=current_status,
            prior_value=prior.value if prior else None,
            prior_ts=prior.ts if prior else None,
            prior_status=prior_status,
            delta_m=None,
            unavailable_reason="; ".join(reasons),
        )

    assert current is not None and prior is not None
    return PressureComparison(
        available=True,
        cursor=cursor,
        prior_cursor=prior_cursor,
        current_value=current.value,
        current_ts=current.ts,
        current_status=current_status,
        prior_value=prior.value,
        prior_ts=prior.ts,
        prior_status=prior_status,
        delta_m=current.value - prior.value,
        unavailable_reason=None,
    )


def context_from_snapshot(
    observations: list[SnapshotObservation],
) -> dict[str, SnapshotObservation | None]:
    by_id = {o.sensor_id: o for o in observations}
    return {
        "external_inflow_p227": by_id.get("p227"),
        "external_inflow_p235": by_id.get("p235"),
        "internal_transfer_pump_1": by_id.get("PUMP_1"),
        "tank_level_t1": by_id.get("T1"),
    }


def verify_flow_mappings_against_model(inp_path: str) -> dict[str, str]:
    """Raise if official model mappings drift from documented roles."""
    import wntr

    wn = wntr.network.WaterNetworkModel(inp_path)
    p227 = wn.get_link("p227")
    p235 = wn.get_link("p235")
    pump = wn.get_link("PUMP_1")
    tank = wn.get_node("T1")

    if wn.get_node(p227.start_node_name).node_type != "Reservoir":
        raise AssertionError("p227 must start at a reservoir (external inflow)")
    if wn.get_node(p235.start_node_name).node_type != "Reservoir":
        raise AssertionError("p235 must start at a reservoir (external inflow)")
    if getattr(pump, "link_type", None) != "Pump":
        raise AssertionError("PUMP_1 must be a Pump (internal transfer)")
    if pump.end_node_name != "T1":
        raise AssertionError("PUMP_1 must discharge to tank T1")
    if tank.node_type != "Tank":
        raise AssertionError("T1 must be a Tank")

    return {
        "p227": f"{p227.start_node_name}→{p227.end_node_name} (external inflow)",
        "p235": f"{p235.start_node_name}→{p235.end_node_name} (external inflow)",
        "PUMP_1": f"{pump.start_node_name}→{pump.end_node_name} (internal transfer)",
        "T1": "tank level",
    }


def pressure_comparison_from_db(sensor_id: str, cursor: datetime) -> PressureComparison:
    """Load raw points at or before cursor and compute the 30-minute comparison."""
    from app.db import get_connection

    prior = cursor - COMPARE_OFFSET
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT measurement_type FROM sensors WHERE id = %s",
                (sensor_id,),
            )
            row = cur.fetchone()
            if not row:
                raise LookupError(f"Unknown sensor: {sensor_id}")
            if row["measurement_type"] != "pressure":
                raise ValueError("Pressure comparison requires a pressure sensor")

            cur.execute(
                """
                SELECT ts, value
                FROM readings
                WHERE sensor_id = %s AND ts <= %s
                ORDER BY ts
                """,
                (sensor_id, cursor),
            )
            points = [Point(ts=r["ts"], value=float(r["value"])) for r in cur.fetchall()]

    # Ensure prior comparison time also never pulls future data relative to cursor
    _ = prior
    return pressure_change_30m(points, cursor)
