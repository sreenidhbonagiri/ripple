"""Investigation evidence tests (comparison boundaries, mappings, cursor safety)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.investigation import (  # noqa: E402
    Point,
    freshness_at,
    pressure_change_30m,
    pressure_comparison_from_db,
    verify_flow_mappings_against_model,
)
from app.replay import replay_snapshot  # noqa: E402


@pytest.fixture(scope="module")
def require_db():
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL not configured")
    # Do not return Settings (may contain credentials in repr)


def test_flow_mappings_against_official_model():
    settings = get_settings()
    mapping = verify_flow_mappings_against_model(str(settings.ripple_inp_path))
    assert "external inflow" in mapping["p227"]
    assert "external inflow" in mapping["p235"]
    assert "internal transfer" in mapping["PUMP_1"]
    assert mapping["T1"] == "tank level"


def test_pressure_change_available_on_grid():
    cursor = datetime(2019, 1, 12, 15, 0, 0)
    points = [
        Point(cursor - timedelta(minutes=30), 40.0),
        Point(cursor - timedelta(minutes=5), 41.0),
        Point(cursor, 42.5),
    ]
    result = pressure_change_30m(points, cursor)
    assert result.available is True
    assert result.delta_m == pytest.approx(2.5)
    assert result.current_status == "current"
    assert result.prior_status == "current"


def test_pressure_change_unavailable_when_prior_missing():
    cursor = datetime(2019, 1, 12, 14, 10, 0)
    points = [Point(cursor, 30.0)]
    result = pressure_change_30m(points, cursor)
    assert result.available is False
    assert result.prior_status == "missing"
    assert result.delta_m is None


def test_pressure_change_unavailable_when_stale():
    cursor = datetime(2019, 1, 12, 15, 0, 0)
    # Observation older than 300s relative to prior comparison time
    points = [
        Point(cursor - timedelta(minutes=40), 10.0),
        Point(cursor, 12.0),
    ]
    result = pressure_change_30m(points, cursor)
    assert result.available is False
    assert result.prior_status == "stale"


def test_freshness_rejects_future_observation():
    at = datetime(2019, 1, 12, 15, 0, 0)
    with pytest.raises(ValueError):
        freshness_at(at + timedelta(minutes=5), at)


def test_comparison_ignores_future_points():
    cursor = datetime(2019, 1, 12, 15, 0, 0)
    points = [
        Point(cursor - timedelta(minutes=30), 20.0),
        Point(cursor, 21.0),
        Point(cursor + timedelta(minutes=5), 99.0),  # must be ignored
    ]
    result = pressure_change_30m(points, cursor)
    assert result.available is True
    assert result.current_value == 21.0
    assert result.delta_m == pytest.approx(1.0)


def test_db_pressure_comparison_and_snapshot_context(require_db):
    cursor = datetime(2019, 1, 12, 15, 30, 0)
    cmp = pressure_comparison_from_db("n1", cursor)
    assert cmp.current_ts is None or cmp.current_ts <= cursor
    assert cmp.prior_ts is None or cmp.prior_ts <= cmp.prior_cursor

    snap = replay_snapshot(cursor)
    by_id = {o.sensor_id: o for o in snap.observations}
    for sid in ("p227", "p235", "PUMP_1", "T1"):
        assert sid in by_id
        obs = by_id[sid]
        assert obs.observation_ts is None or obs.observation_ts <= cursor

    before = replay_snapshot(datetime(2018, 12, 31, 23, 55, 0))
    assert all(o.status == "missing" for o in before.observations)


def test_pressure_change_at_data_start_prior_missing(require_db):
    # First imported timestamp: prior −30 min is outside coverage → unavailable
    result = pressure_comparison_from_db("n1", datetime(2019, 1, 1, 0, 0, 0))
    assert result.available is False
    assert result.prior_status == "missing"


def test_n54_comparison_prior_before_presenter_window(require_db):
    """Prior −30 min at 14:05 is 13:35 — before presenter start; DB still has it."""
    cursor = datetime(2019, 1, 12, 14, 5, 0)
    result = pressure_comparison_from_db("n54", cursor)
    assert result.prior_cursor == datetime(2019, 1, 12, 13, 35, 0)
    assert result.prior_status == "current"
    assert result.prior_ts is not None
    assert result.prior_ts <= result.prior_cursor
    assert result.current_status == "current"
    assert result.available is True
    assert result.delta_m is not None


def test_n54_illustrative_15_00_delta(require_db):
    result = pressure_comparison_from_db("n54", datetime(2019, 1, 12, 15, 0, 0))
    assert result.available is True
    assert result.current_value == pytest.approx(36.41, abs=0.02)
    assert result.delta_m == pytest.approx(-0.95, abs=0.02)
