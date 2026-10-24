"""Presenter preset + cursor-safety / stale-response guards."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.history import pressure_hourly_history  # noqa: E402
from app.replay import replay_snapshot  # noqa: E402
from app.schemas import PRESENTER_END, PRESENTER_START, PresenterPresetResponse  # noqa: E402


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def require_db():
    get_settings.cache_clear()
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")


def test_presenter_preset_jan12_bounds_and_language():
    preset = PresenterPresetResponse()
    assert preset.window_start == PRESENTER_START
    assert preset.window_end == PRESENTER_END
    assert PRESENTER_START == datetime(2019, 1, 12, 14, 0, 0)
    assert PRESENTER_END == datetime(2019, 1, 12, 17, 0, 0)
    text = (preset.label + " " + preset.disclaimer).lower()
    assert "leak" in text  # disclaimer mentions not a leak
    assert "detected leak" in text or "not a detected leak" in text
    assert "alert" not in preset.label.lower()
    bookmarks = {b["id"]: b for b in preset.bookmarks}
    assert bookmarks["illustrative_pressure_change"]["sensor_id"] == "n54"
    assert bookmarks["illustrative_pressure_change"]["cursor"] == "2019-01-12 15:00:00"


def test_rapid_snapshot_cursors_never_expose_future(require_db):
    """Simulate rapid cursor navigation: each response must respect its own cursor."""
    cursors = [
        datetime(2019, 1, 12, 14, 0, 0),
        datetime(2019, 1, 12, 14, 30, 0),
        datetime(2019, 1, 12, 15, 0, 0),
        datetime(2019, 1, 12, 15, 30, 0),
        datetime(2019, 1, 12, 16, 0, 0),
        datetime(2019, 1, 12, 17, 0, 0),
    ]
    # Out-of-order completion simulation: fetch later cursor first, then earlier.
    later = replay_snapshot(cursors[-1])
    earlier = replay_snapshot(cursors[0])
    for obs in later.observations:
        if obs.observation_ts is not None:
            assert obs.observation_ts <= cursors[-1]
    for obs in earlier.observations:
        if obs.observation_ts is not None:
            assert obs.observation_ts <= cursors[0]
    # Frontend ignores stale responses via request-id; backend itself is cursor-scoped.
    for cursor in cursors:
        snap = replay_snapshot(cursor)
        assert snap.cursor == cursor
        for obs in snap.observations:
            if obs.observation_ts is not None:
                assert obs.observation_ts <= cursor


def test_hourly_history_excludes_post_cursor_buckets(require_db):
    cursor = datetime(2019, 1, 12, 15, 0, 0)
    hist = pressure_hourly_history("n54", cursor, days=14)
    for hour in hist.hours:
        # Hour start itself must be <= cursor; contributing buckets end <= cursor
        assert hour.hour_start <= cursor
    assert hist.aggregation["bucket_inclusion"].startswith("bucket_end")
