"""Pydantic response models for the network and replay APIs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Presenter playback preset (Milestone 4): keep Jan 12 afternoon window
PRESENTER_START = datetime(2019, 1, 12, 14, 0, 0)
PRESENTER_END = datetime(2019, 1, 12, 17, 0, 0)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "ripple"
    product: str = "Historical benchmark replay workspace"
    note: str = (
        "BattLeDIM L-Town historical investigation — not live utility monitoring. "
        "Pressure anomalies are not confirmed leaks."
    )


class NodeCoordinates(BaseModel):
    x: float
    y: float


class NetworkNode(BaseModel):
    id: str
    type: Literal["Junction", "Reservoir", "Tank"]
    coordinates: NodeCoordinates | None = None
    elevation: float | None = None
    base_demand: float | None = None
    demand_pattern: str | None = None
    initial_quality: float | None = None
    base_head: float | None = None
    diameter: float | None = None
    min_level: float | None = None
    max_level: float | None = None
    initial_level: float | None = None
    min_vol: float | None = None
    overflow: bool | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class NetworkLink(BaseModel):
    id: str
    type: Literal["Pipe", "Pump", "Valve"]
    start_node: str
    end_node: str
    length: float | None = None
    diameter: float | None = None
    roughness: float | None = None
    minor_loss: float | None = None
    status: str | None = None
    check_valve: bool | None = None
    pump_type: str | None = None
    valve_type: str | None = None
    setting: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class NetworkCounts(BaseModel):
    nodes: int
    links: int
    junctions: int
    reservoirs: int
    tanks: int
    pipes: int
    pumps: int
    valves: int


class NetworkResponse(BaseModel):
    name: str
    source: str
    coordinate_system: str = (
        "Network model coordinates (EPANET), not geographic latitude/longitude"
    )
    product_boundary: str = (
        "Historical BattLeDIM L-Town benchmark — anomalies are not confirmed leaks; "
        "no predicted leak-pipe rankings"
    )
    counts: NetworkCounts
    nodes: list[NetworkNode]
    links: list[NetworkLink]


# --- Milestone 2: sensors / replay ---

FreshnessStatus = Literal["current", "stale", "missing"]


class Sensor(BaseModel):
    id: str
    measurement_type: Literal["pressure", "flow", "tank_level"]
    unit: str
    network_element_id: str
    network_element_kind: Literal["node", "link"]


class SensorsResponse(BaseModel):
    count: int
    sensors: list[Sensor]
    freshness_rule: str = (
        "BattLeDIM SCADA samples every 5 minutes (naive benchmark clock). "
        "At cursor T, each sensor uses the latest raw reading with ts <= T. "
        "current: age_seconds <= 300; stale: age_seconds > 300; "
        "missing: no reading at or before T. Snapshots never expose ts > T."
    )


class ReadingPoint(BaseModel):
    ts: datetime
    value: float


class SensorReadingsResponse(BaseModel):
    sensor_id: str
    unit: str
    measurement_type: str
    start: datetime
    end: datetime
    count: int
    readings: list[ReadingPoint]


class ReplayWindowResponse(BaseModel):
    """Actual database coverage plus the fixed presenter playback preset."""

    # Actual imported data coverage in the database
    data_start: datetime | None = None
    data_end: datetime | None = None
    sensor_count: int
    # Timescale approximate_row_count — coverage subtitle only (not Tiger evidence).
    reading_count: int
    reading_count_estimated: bool = True
    # Presenter playback preset (not expanded to full imported month)
    presenter_start: datetime
    presenter_end: datetime
    step_seconds: int = 300
    # Backward-compatible aliases for presenter window
    start: datetime | None = None
    end: datetime | None = None
    label: str = "Historical benchmark replay"
    freshness_rule: str = (
        "5-minute sampling. current if age_seconds <= 300; "
        "stale if older observation exists; missing if none at or before cursor."
    )


class HourlyHistoryBucket(BaseModel):
    hour_start: datetime
    mean_m: float
    min_m: float
    max_m: float
    count: int
    bucket_count: int
    complete: bool
    missing_buckets: int
    status: Literal["complete", "incomplete"]


class HourlyHistoryResponse(BaseModel):
    sensor_id: str
    unit: str = "m"
    cursor: datetime
    requested_days: int
    history_start: datetime
    coverage_start: datetime | None
    coverage_end: datetime | None
    coverage_days: float | None
    hour_count: int
    hours: list[HourlyHistoryBucket]
    aggregation: dict[str, Any]
    title: str = "Available history — up to 30 days"
    limit_note: str = (
        "Observed hourly min/max are not expected or safe operating limits."
    )


class SnapshotObservation(BaseModel):
    sensor_id: str
    measurement_type: str
    unit: str
    network_element_id: str
    network_element_kind: str
    value: float | None
    observation_ts: datetime | None
    age_seconds: float | None
    status: FreshnessStatus


class ReplaySnapshotResponse(BaseModel):
    cursor: datetime
    label: str = "Historical benchmark replay"
    freshness_rule: str = (
        "Raw readings only (not CAGG). Observation must have ts <= cursor. "
        "current: age_seconds <= 300; stale: age_seconds > 300; missing: none."
    )
    observations: list[SnapshotObservation]


# --- Milestone 3: investigation evidence (observations only, no leak claims) ---


class PressureComparisonResponse(BaseModel):
    sensor_id: str
    unit: str = "m"
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
    unavailable_reason: str | None = None
    note: str = (
        "Pressure change is an observation only. It does not confirm a leak."
    )


class ContextChannel(BaseModel):
    role: str
    sensor_id: str
    unit: str
    label: str
    value: float | None
    observation_ts: datetime | None
    age_seconds: float | None
    status: FreshnessStatus


class InvestigationContextResponse(BaseModel):
    cursor: datetime
    label: str = "Historical benchmark replay"
    disclaimer: str = (
        "Inspect pressure changes alongside supply, pump transfer, and tank "
        "behavior. These measurements do not confirm a leak."
    )
    selected_pressure: ContextChannel | None
    external_inflows: list[ContextChannel]
    internal_transfer: ContextChannel | None
    tank_level: ContextChannel | None
    pressure_comparison: PressureComparisonResponse | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"] = "ready"
    database: Literal["ok", "error", "unconfigured"] = "ok"
    detail: str | None = None


class PresenterPresetResponse(BaseModel):
    """Fixed Jan 12 illustrative investigation preset (not a leak claim)."""

    label: str = "Illustrative investigation — Jan 12 afternoon"
    disclaimer: str = (
        "Selected historical pressure pattern for walkthrough only. "
        "Not a detected leak, alert, or localization result."
    )
    window_start: datetime = PRESENTER_START
    window_end: datetime = PRESENTER_END
    bookmarks: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {
                "id": "window_start",
                "label": "Window start",
                "cursor": "2019-01-12 14:00:00",
                "note": "Begin the illustrative Jan 12 window.",
            },
            {
                "id": "illustrative_pressure_change",
                "label": "Illustrative pressure change",
                "cursor": "2019-01-12 15:00:00",
                "sensor_id": "n54",
                "note": (
                    "Largest fresh 30-minute pressure drop in this window "
                    "(observation only — not a leak)."
                ),
            },
            {
                "id": "midpoint",
                "label": "Midpoint",
                "cursor": "2019-01-12 15:30:00",
                "note": "Mid-window context for supply / pump / tank panels.",
            },
        ]
    )


# --- Saved investigations (metadata only; measurements from time-series tables) ---


class InvestigationCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional public plain-text note. Do not enter private data.",
    )
    sensor_id: str = Field(..., min_length=1, max_length=64)
    cursor: datetime
    window_start: datetime
    window_end: datetime
    source_id: str = Field(
        default="battledim-ltown-zenodo-4017659",
        min_length=1,
        max_length=64,
        description="Benchmark / dataset source identifier",
    )


class SavedInvestigationResponse(BaseModel):
    id: str
    title: str
    note: str | None
    sensor_id: str
    cursor: datetime
    window_start: datetime
    window_end: datetime
    source_id: str
    created_at: datetime
    share_path: str
    public_note_notice: str = (
        "Shared investigation notes are public. Do not enter private or sensitive data. "
        "The opaque link id is not authentication."
    )
    evidence_notice: str = (
        "This record stores investigation metadata only. Chart values are loaded from "
        "live historical time-series tables and are not a frozen evidence snapshot."
    )


class InvestigationCreateResponse(SavedInvestigationResponse):
    pass
