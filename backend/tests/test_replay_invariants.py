"""Backend tests for replay cursor invariants (requires DATABASE_URL)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.replay import list_sensors, replay_snapshot, replay_window, sensor_readings  # noqa: E402


@pytest.fixture(scope="module")
def require_db():
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL not configured")
    # Do not return Settings (may contain credentials in repr)


def test_replay_window_populated(require_db):
    window = replay_window()
    assert window.presenter_start is not None
    assert window.presenter_end is not None
    assert window.start == window.presenter_start
    assert window.end == window.presenter_end
    assert window.data_start is not None
    assert window.data_end is not None
    assert window.reading_count >= 1369
    assert window.reading_count_estimated is True
    assert window.sensor_count == 37
    assert window.step_seconds == 300
    # Presenter preset stays on Jan 12 afternoon even if more data is imported
    assert window.presenter_start.isoformat(sep=" ") == "2019-01-12 14:00:00"
    assert window.presenter_end.isoformat(sep=" ") == "2019-01-12 17:00:00"
    assert window.data_start <= window.presenter_start
    assert window.data_end >= window.presenter_end


def test_sensors_count(require_db):
    res = list_sensors()
    assert res.count == 37
    assert len(res.sensors) == 37


def test_snapshot_missing_before_data_coverage(require_db):
    snap = replay_snapshot(datetime(2018, 12, 31, 23, 55, 0))
    assert all(o.status == "missing" for o in snap.observations)
    assert all(o.observation_ts is None for o in snap.observations)


def test_snapshot_never_future(require_db):
    cursor = datetime(2019, 1, 12, 15, 0, 0)
    snap = replay_snapshot(cursor)
    for obs in snap.observations:
        if obs.observation_ts is not None:
            assert obs.observation_ts <= cursor


def test_readings_bounded(require_db):
    sensors = list_sensors().sensors
    sid = sensors[0].id
    res = sensor_readings(
        sid,
        datetime(2019, 1, 12, 14, 0, 0),
        datetime(2019, 1, 12, 17, 0, 0),
    )
    assert res.count >= 1
    assert all(datetime(2019, 1, 12, 14, 0, 0) <= r.ts <= datetime(2019, 1, 12, 17, 0, 0) for r in res.readings)
