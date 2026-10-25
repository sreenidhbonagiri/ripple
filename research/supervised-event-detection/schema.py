"""Shared sensor schema, units, and sampling semantics for synthetic + measured."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INP = REPO_ROOT / "data" / "L-TOWN.inp"
DEFAULT_RAW = REPO_ROOT / "data" / "raw"

# Official BattLeDIM SCADA pressure columns (order frozen; matches FMR3C package).
PRESSURE_SENSORS: list[str] = [
    "n1", "n4", "n31", "n54", "n105", "n114", "n163", "n188", "n215", "n229",
    "n288", "n296", "n332", "n342", "n410", "n415", "n429", "n458", "n469", "n495",
    "n506", "n516", "n519", "n549", "n613", "n636", "n644", "n679", "n722", "n726",
    "n740", "n752", "n769",
]

FLOW_SENSORS: list[str] = ["p227", "p235", "PUMP_1"]
LEVEL_SENSORS: list[str] = ["T1"]

STEPS_PER_HOUR = 12  # 5-minute grid
STEP_SECONDS = 300

# Units (BattLeDIM README + WNTR conversion)
UNIT_PRESSURE = "m"  # pressure head at junctions
UNIT_FLOW_SCADA = "m3/h"
UNIT_FLOW_WNTR = "m3/s"  # convert * 3600 → SCADA
UNIT_TANK_LEVEL = "m"  # tank water level (head - elevation)

PUMP_ON_EPS = 1.0  # m³/h; matches prior context residual design


@dataclass(frozen=True)
class FeatureConfig:
    """Pre-declared causal feature recipe (frozen before fitting)."""

    delta_steps: tuple[int, ...] = (1, 6, 24)  # 5 min, 30 min, 2 h
    top_k_pressure_delta: int = 5
    include_calendar: bool = False  # pilot: pressure+context only set
    # Max causal lag is 2 h (24 steps); scenario trajectories also reserve 12 h
    # hydraulic warm-up before leak/control interventions.
    warm_up_steps: int = 12 * STEPS_PER_HOUR


FEATURE_SET_NAME = "pressure_context_v1"
FEATURE_CONFIG = FeatureConfig()
