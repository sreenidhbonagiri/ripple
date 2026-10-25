"""Ripple FastAPI application — network viewer + historical replay."""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_connection, sanitize_db_error
from app.network_loader import get_cached_network
from app.history import pressure_hourly_history
from app.investigation import pressure_comparison_from_db
from app.investigations import (
    CREATE_RATE_LIMITER,
    InvestigationCreate,
    InvestigationRateLimitError,
    InvestigationValidationError,
    client_rate_limit_key,
    get_investigation_store,
)
from app.replay import (
    MAX_READINGS,
    list_sensors,
    replay_snapshot,
    replay_window,
    sensor_readings,
)
from app.schemas import (
    HealthResponse,
    HourlyHistoryResponse,
    InvestigationCreateRequest,
    InvestigationCreateResponse,
    NetworkResponse,
    PresenterPresetResponse,
    PressureComparisonResponse,
    ReadyResponse,
    ReplaySnapshotResponse,
    ReplayWindowResponse,
    SavedInvestigationResponse,
    SensorReadingsResponse,
    SensorsResponse,
)
from app.method_m_warning import present_method_m_warning
from app.tiger_evidence import present_tiger_evidence

app = FastAPI(
    title="Ripple",
    description=(
        "Historical water-network investigation workspace for the BattLeDIM "
        "L-Town benchmark. Not live utility monitoring."
    ),
    version="0.6.0",
)

_settings = get_settings()
_cors_origins = [
    o.strip() for o in _settings.ripple_cors_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_naive(value: str, field: str) -> datetime:
    try:
        text = value.strip().replace("T", " ")
        if text.endswith("Z"):
            raise ValueError("timezone-aware timestamps are not accepted")
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}: use naive TIMESTAMP (YYYY-MM-DD HH:MM:SS)",
        ) from exc
    if dt.tzinfo is not None:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be TIMESTAMP WITHOUT TIME ZONE (no geographic TZ)",
        )
    return dt


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness — no database dependency (safe for load balancers)."""
    return HealthResponse()


@app.get("/api/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    """Readiness — verifies DATABASE_URL connectivity without printing secrets."""
    settings = get_settings()
    if not settings.database_url:
        return ReadyResponse(
            status="not_ready",
            database="unconfigured",
            detail="DATABASE_URL is not configured",
        )
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        return ReadyResponse(status="ready", database="ok")
    except Exception as exc:  # noqa: BLE001
        return ReadyResponse(
            status="not_ready",
            database="error",
            detail=sanitize_db_error(str(exc)),
        )


@app.get("/api/network", response_model=NetworkResponse)
def network() -> NetworkResponse:
    settings = get_settings()
    try:
        return get_cached_network(str(settings.ripple_inp_path.resolve()))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse EPANET model: {exc}",
        ) from exc


@app.get("/api/sensors", response_model=SensorsResponse)
def sensors() -> SensorsResponse:
    try:
        return list_sensors()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get("/api/sensors/{sensor_id}/readings", response_model=SensorReadingsResponse)
def readings(
    sensor_id: str,
    start: str = Query(..., description="Naive start timestamp"),
    end: str = Query(..., description="Naive end timestamp"),
    limit: int = Query(MAX_READINGS, ge=1, le=MAX_READINGS),
) -> SensorReadingsResponse:
    start_dt = _parse_naive(start, "start")
    end_dt = _parse_naive(end, "end")
    try:
        return sensor_readings(sensor_id, start_dt, end_dt, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get("/api/replay/window", response_model=ReplayWindowResponse)
def get_replay_window() -> ReplayWindowResponse:
    try:
        return replay_window()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get("/api/presenter/preset", response_model=PresenterPresetResponse)
def get_presenter_preset() -> PresenterPresetResponse:
    """Jan 12 illustrative investigation bookmarks — not alerts or leak claims."""
    return PresenterPresetResponse()


@app.get("/api/replay/snapshot", response_model=ReplaySnapshotResponse)
def get_replay_snapshot(
    at: str = Query(..., description="Replay cursor (naive timestamp)"),
) -> ReplaySnapshotResponse:
    cursor = _parse_naive(at, "at")
    try:
        return replay_snapshot(cursor)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get(
    "/api/investigation/pressure-change",
    response_model=PressureComparisonResponse,
)
def get_pressure_change(
    at: str = Query(..., description="Replay cursor (naive timestamp)"),
    sensor_id: str = Query(..., description="Pressure sensor ID"),
) -> PressureComparisonResponse:
    """30-minute pressure observation delta — not a leak diagnosis."""
    cursor = _parse_naive(at, "at")
    try:
        result = pressure_comparison_from_db(sensor_id, cursor)
        return PressureComparisonResponse(sensor_id=sensor_id, **result.__dict__)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get(
    "/api/sensors/{sensor_id}/hourly-history",
    response_model=HourlyHistoryResponse,
)
def get_hourly_history(
    sensor_id: str,
    at: str = Query(..., description="Replay cursor (naive timestamp)"),
    days: int = Query(30, ge=1, le=30, description="Lookback days before cursor (max 30)"),
) -> HourlyHistoryResponse:
    """Hourly pressure context from readings_15m (bucket_end <= cursor only)."""
    cursor = _parse_naive(at, "at")
    try:
        return pressure_hourly_history(sensor_id, cursor, days=days)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get("/api/tiger/evidence")
def get_tiger_evidence() -> dict:
    """Sponsor evidence: live counts + saved January benchmark (no re-bench).

    Intentionally off the critical investigation-loading path — call lazily.
    """
    try:
        return present_tiger_evidence()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None


@app.get("/api/experimental/method-m-warning")
def get_method_m_warning(
    at: str = Query(..., description="Replay cursor (naive timestamp)"),
) -> dict:
    """Cursor-safe Experimental Method M historical anomaly warning (January).

    File-backed serving artifact — not a confirmed leak; no predicted pipes;
    evidence and episode peaks/ends only at or before the cursor.
    """
    cursor = _parse_naive(at, "at")
    try:
        return present_method_m_warning(cursor)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from None


def _client_rate_key(request: Request) -> str:
    """Rate-limit identity for Caddy → nginx → FastAPI (see client_rate_limit_key)."""
    peer = request.client.host if request.client else None
    return client_rate_limit_key(
        x_forwarded_for=request.headers.get("x-forwarded-for"),
        x_real_ip=request.headers.get("x-real-ip"),
        peer_host=peer,
    )


def _investigation_response(row) -> SavedInvestigationResponse:
    return SavedInvestigationResponse(
        id=row.id,
        title=row.title,
        note=row.note,
        sensor_id=row.sensor_id,
        cursor=row.cursor_ts,
        window_start=row.window_start,
        window_end=row.window_end,
        source_id=row.source_id,
        created_at=row.created_at,
        share_path=f"/?i={row.id}",
    )


@app.post(
    "/api/investigations",
    response_model=InvestigationCreateResponse,
    status_code=201,
)
def create_investigation(
    body: InvestigationCreateRequest,
    request: Request,
) -> InvestigationCreateResponse:
    """Save investigation metadata. Notes are public; ids are not authentication."""
    try:
        CREATE_RATE_LIMITER.check(_client_rate_key(request))
    except InvestigationRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from None

    payload = InvestigationCreate(
        title=body.title,
        note=body.note,
        sensor_id=body.sensor_id,
        cursor_ts=body.cursor,
        window_start=body.window_start,
        window_end=body.window_end,
        source_id=body.source_id,
    )
    try:
        row = get_investigation_store().create(payload)
    except InvestigationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None
    return InvestigationCreateResponse(**_investigation_response(row).model_dump())


@app.get(
    "/api/investigations/{investigation_id}",
    response_model=SavedInvestigationResponse,
)
def get_investigation(investigation_id: str) -> SavedInvestigationResponse:
    """Reopen saved metadata. Measurements come from existing time-series APIs."""
    if len(investigation_id) > 64 or "/" in investigation_id:
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        row = get_investigation_store().get(investigation_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=sanitize_db_error(str(exc))) from None
    if row is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return _investigation_response(row)
