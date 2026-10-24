"""Hourly history aggregation and cursor-boundary tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.history import pressure_hourly_history  # noqa: E402


@pytest.fixture(scope="module")
def require_db():
    get_settings.cache_clear()
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")


def test_no_future_buckets_in_hourly_history(require_db):
    cursor = datetime(2019, 1, 12, 15, 30, 0)
    hist = pressure_hourly_history("n1", cursor, days=30)
    for hour in hist.hours:
        # Each contributing 15m bucket ends at bucket+15m <= cursor
        assert hour.hour_start <= cursor
    assert hist.cursor == cursor
    assert all(h.count > 0 for h in hist.hours)


def test_bucket_boundary_exactly_on_cursor(require_db):
    # Bucket 15:15–15:30 ends exactly at cursor → included
    cursor = datetime(2019, 1, 12, 15, 30, 0)
    hist = pressure_hourly_history("n1", cursor, days=2)
    hour_15 = next((h for h in hist.hours if h.hour_start == datetime(2019, 1, 12, 15, 0, 0)), None)
    assert hour_15 is not None
    # Only two completed buckets in that hour before/at 15:30: 15:00 and 15:15
    assert hour_15.bucket_count == 2
    assert hour_15.complete is False
    assert hour_15.status == "incomplete"


def test_partial_hour_inside_bucket_boundary(require_db):
    # Cursor inside a bucket (15:20) → bucket 15:15 ends 15:30 > cursor → excluded
    cursor = datetime(2019, 1, 12, 15, 20, 0)
    hist = pressure_hourly_history("n1", cursor, days=2)
    hour_15 = next((h for h in hist.hours if h.hour_start == datetime(2019, 1, 12, 15, 0, 0)), None)
    assert hour_15 is not None
    assert hour_15.bucket_count == 1  # only 15:00–15:15
    assert hour_15.complete is False


def test_cagg_hourly_matches_raw_sql(require_db):
    cursor = datetime(2019, 1, 12, 16, 0, 0)
    hist = pressure_hourly_history("n1", cursor, days=2)
    # Compare a complete hour if present: 14:00 hour at cursor 16:00 has 4 buckets
    hour = next(h for h in hist.hours if h.hour_start == datetime(2019, 1, 12, 14, 0, 0))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    SUM(value) AS sum_v,
                    COUNT(*)::BIGINT AS cnt,
                    MIN(value) AS min_v,
                    MAX(value) AS max_v
                FROM readings
                WHERE sensor_id = 'n1'
                  AND ts >= %s AND ts < %s
                  AND ts <= %s
                """,
                (
                    datetime(2019, 1, 12, 14, 0, 0),
                    datetime(2019, 1, 12, 15, 0, 0),
                    cursor,
                ),
            )
            raw = cur.fetchone()
    assert hour.count == int(raw["cnt"])
    assert hour.min_m == pytest.approx(float(raw["min_v"]))
    assert hour.max_m == pytest.approx(float(raw["max_v"]))
    assert hour.mean_m == pytest.approx(float(raw["sum_v"]) / float(raw["cnt"]))


def test_empty_hours_omitted_before_data(require_db):
    cursor = datetime(2019, 1, 12, 14, 30, 0)
    hist = pressure_hourly_history("n1", cursor, days=30)
    # No hours before imported data should appear as empty placeholders
    assert all(h.count > 0 for h in hist.hours)
    if hist.hours:
        assert hist.hours[0].hour_start >= datetime(2019, 1, 1, 0, 0, 0)
