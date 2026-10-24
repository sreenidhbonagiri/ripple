"""Sensor and historical replay query helpers."""

from __future__ import annotations

from datetime import datetime

from app.db import get_connection
from app.schemas import (
    PRESENTER_END,
    PRESENTER_START,
    ReadingPoint,
    ReplaySnapshotResponse,
    ReplayWindowResponse,
    Sensor,
    SensorReadingsResponse,
    SensorsResponse,
    SnapshotObservation,
)

# BattLeDIM SCADA interval
STEP_SECONDS = 300
FRESH_SECONDS = 300
MAX_READINGS = 5000


def list_sensors() -> SensorsResponse:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, measurement_type, unit, network_element_id, network_element_kind
                FROM sensors
                ORDER BY measurement_type, id
                """
            )
            rows = cur.fetchall()
    sensors = [Sensor(**row) for row in rows]
    return SensorsResponse(count=len(sensors), sensors=sensors)


def sensor_readings(
    sensor_id: str,
    start: datetime,
    end: datetime,
    *,
    limit: int = MAX_READINGS,
) -> SensorReadingsResponse:
    if end < start:
        raise ValueError("end must be >= start")
    if limit < 1 or limit > MAX_READINGS:
        raise ValueError(f"limit must be between 1 and {MAX_READINGS}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, measurement_type, unit FROM sensors WHERE id = %s",
                (sensor_id,),
            )
            sensor = cur.fetchone()
            if not sensor:
                raise LookupError(f"Unknown sensor: {sensor_id}")

            cur.execute(
                """
                SELECT ts, value
                FROM readings
                WHERE sensor_id = %s AND ts >= %s AND ts <= %s
                ORDER BY ts
                LIMIT %s
                """,
                (sensor_id, start, end, limit),
            )
            points = cur.fetchall()

    return SensorReadingsResponse(
        sensor_id=sensor_id,
        unit=sensor["unit"],
        measurement_type=sensor["measurement_type"],
        start=start,
        end=end,
        count=len(points),
        readings=[ReadingPoint(ts=p["ts"], value=float(p["value"])) for p in points],
    )


def replay_window() -> ReplayWindowResponse:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    MIN(ts) AS data_start,
                    MAX(ts) AS data_end,
                    COUNT(*)::INT AS reading_count,
                    COUNT(DISTINCT sensor_id)::INT AS sensor_count
                FROM readings
                """
            )
            row = cur.fetchone()
    # Playback stays on the presenter preset; data_* reports full DB coverage.
    return ReplayWindowResponse(
        data_start=row["data_start"],
        data_end=row["data_end"],
        sensor_count=row["sensor_count"] or 0,
        reading_count=row["reading_count"] or 0,
        presenter_start=PRESENTER_START,
        presenter_end=PRESENTER_END,
        start=PRESENTER_START,
        end=PRESENTER_END,
        step_seconds=STEP_SECONDS,
    )


def replay_snapshot(at: datetime) -> ReplaySnapshotResponse:
    """
    Latest raw reading per sensor with ts <= cursor.
    Never returns future observations relative to `at`.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id AS sensor_id,
                    s.measurement_type,
                    s.unit,
                    s.network_element_id,
                    s.network_element_kind,
                    r.ts AS observation_ts,
                    r.value
                FROM sensors s
                LEFT JOIN LATERAL (
                    SELECT ts, value
                    FROM readings
                    WHERE sensor_id = s.id AND ts <= %s
                    ORDER BY ts DESC
                    LIMIT 1
                ) r ON TRUE
                ORDER BY s.measurement_type, s.id
                """,
                (at,),
            )
            rows = cur.fetchall()

    observations: list[SnapshotObservation] = []
    for row in rows:
        obs_ts = row["observation_ts"]
        if obs_ts is None:
            observations.append(
                SnapshotObservation(
                    sensor_id=row["sensor_id"],
                    measurement_type=row["measurement_type"],
                    unit=row["unit"],
                    network_element_id=row["network_element_id"],
                    network_element_kind=row["network_element_kind"],
                    value=None,
                    observation_ts=None,
                    age_seconds=None,
                    status="missing",
                )
            )
            continue

        # Guard: never expose future readings
        if obs_ts > at:
            raise RuntimeError("Invariant violated: snapshot returned ts > cursor")

        age = (at - obs_ts).total_seconds()
        status = "current" if age <= FRESH_SECONDS else "stale"
        observations.append(
            SnapshotObservation(
                sensor_id=row["sensor_id"],
                measurement_type=row["measurement_type"],
                unit=row["unit"],
                network_element_id=row["network_element_id"],
                network_element_kind=row["network_element_kind"],
                value=float(row["value"]),
                observation_ts=obs_ts,
                age_seconds=age,
                status=status,
            )
        )

    return ReplaySnapshotResponse(cursor=at, observations=observations)
