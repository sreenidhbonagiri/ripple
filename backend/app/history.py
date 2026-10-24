"""Historical pressure context from readings_15m continuous aggregate."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db import get_connection
from app.schemas import (
    HourlyHistoryBucket,
    HourlyHistoryResponse,
)

HISTORY_DAYS_DEFAULT = 30
BUCKET_MINUTES = 15
EXPECTED_BUCKETS_PER_HOUR = 4
# 5-minute SCADA → up to 3 readings per 15-minute bucket
EXPECTED_READINGS_PER_HOUR = 12


def pressure_hourly_history(
    sensor_id: str,
    cursor: datetime,
    *,
    days: int = HISTORY_DAYS_DEFAULT,
) -> HourlyHistoryResponse:
    if days < 1 or days > 30:
        raise ValueError("days must be between 1 and 30")

    history_start = cursor - timedelta(days=days)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, measurement_type, unit FROM sensors WHERE id = %s",
                (sensor_id,),
            )
            sensor = cur.fetchone()
            if not sensor:
                raise LookupError(f"Unknown sensor: {sensor_id}")
            if sensor["measurement_type"] != "pressure":
                raise ValueError("Hourly history is only available for pressure sensors")

            # Include only 15-minute buckets whose end <= cursor (no partial/future bucket).
            # bucket is the start; end = bucket + 15 minutes.
            cur.execute(
                """
                SELECT
                    date_trunc('hour', bucket) AS hour_start,
                    SUM(sum) AS sum_sum,
                    SUM(count) AS sum_count,
                    MIN(min) AS min_v,
                    MAX(max) AS max_v,
                    COUNT(*)::INT AS bucket_count
                FROM readings_15m
                WHERE sensor_id = %s
                  AND bucket >= %s
                  AND (bucket + INTERVAL '15 minutes') <= %s
                GROUP BY 1
                HAVING SUM(count) > 0
                ORDER BY 1
                """,
                (sensor_id, history_start, cursor),
            )
            rows = cur.fetchall()

    hours: list[HourlyHistoryBucket] = []
    for row in rows:
        total_count = int(row["sum_count"] or 0)
        if total_count <= 0:
            continue
        bucket_count = int(row["bucket_count"] or 0)
        weighted_mean = float(row["sum_sum"]) / float(total_count)
        complete = (
            bucket_count >= EXPECTED_BUCKETS_PER_HOUR
            and total_count >= EXPECTED_READINGS_PER_HOUR
        )
        missing_buckets = max(EXPECTED_BUCKETS_PER_HOUR - bucket_count, 0)
        hours.append(
            HourlyHistoryBucket(
                hour_start=row["hour_start"],
                mean_m=weighted_mean,
                min_m=float(row["min_v"]),
                max_m=float(row["max_v"]),
                count=total_count,
                bucket_count=bucket_count,
                complete=complete,
                missing_buckets=missing_buckets,
                status="complete" if complete else "incomplete",
            )
        )

    coverage_start = hours[0].hour_start if hours else None
    coverage_end = hours[-1].hour_start if hours else None
    # Coverage span in days among returned hours (actual available, not requested)
    coverage_days = None
    if coverage_start and coverage_end:
        coverage_days = (coverage_end - coverage_start).total_seconds() / 86400.0

    return HourlyHistoryResponse(
        sensor_id=sensor_id,
        unit=sensor["unit"],
        cursor=cursor,
        requested_days=days,
        history_start=history_start,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        coverage_days=coverage_days,
        hour_count=len(hours),
        hours=hours,
        aggregation={
            "source": "readings_15m",
            "bucket_minutes": BUCKET_MINUTES,
            "weighted_mean": "sum(bucket.sum) / sum(bucket.count)",
            "bucket_inclusion": "bucket_end = bucket + 15 minutes; require bucket_end <= cursor",
            "empty_hours": "omitted",
            "incomplete_hour": (
                f"bucket_count < {EXPECTED_BUCKETS_PER_HOUR} or "
                f"count < {EXPECTED_READINGS_PER_HOUR}"
            ),
            "note": (
                "Historical min/max are observed extremes from aggregated SCADA, "
                "not expected or safe operating limits."
            ),
        },
    )
