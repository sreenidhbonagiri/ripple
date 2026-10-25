"""Method M Tiger timeline: cursor bounds, run isolation, empty, notifies, seeks."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.method_m_db import DEFAULT_RUN_ID  # noqa: E402
from app.method_m_timeline import present_method_m_timeline  # noqa: E402
from app.method_m_warning import floor_to_score_step  # noqa: E402


def _tiger_ready() -> bool:
    if not get_settings().database_url:
        return False
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'method_m_runs'
                    """
                )
                if cur.fetchone() is None:
                    return False
                cur.execute("SELECT COUNT(*)::BIGINT AS n FROM method_m_runs")
                return int(cur.fetchone()["n"]) > 0
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _tiger_ready(),
    reason="Tiger Method M run not available",
)


@pytest.fixture()
def tiger_store(monkeypatch):
    monkeypatch.setenv("RIPPLE_METHOD_M_STORE", "tiger")
    monkeypatch.setenv("RIPPLE_METHOD_M_RUN_ID", DEFAULT_RUN_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_requires_tiger_store(monkeypatch):
    monkeypatch.setenv("RIPPLE_METHOD_M_STORE", "file")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="requires RIPPLE_METHOD_M_STORE=tiger"):
        present_method_m_timeline(datetime(2019, 1, 24, 18, 35, 0))
    get_settings.cache_clear()


def test_cursor_bounds_no_future_stamps(tiger_store):
    cursor = datetime(2019, 1, 24, 18, 37, 0)  # floors to 18:35
    res = present_method_m_timeline(cursor)
    assert res["store"] == "tiger"
    assert res["run_id"] == DEFAULT_RUN_ID
    assert res["window_end"] == "2019-01-24 18:35:00"
    assert res["window_start"] == "2019-01-23 18:35:00"
    assert res["points"]
    assert res["points"][-1]["ts"] == res["window_end"]
    for p in res["points"]:
        assert p["ts"] <= res["window_end"]
    for n in res["notifications"]:
        assert n["notify_ts"] <= res["window_end"]


def test_jan24_notification_visible_not_before(tiger_store):
    at_notify = present_method_m_timeline(datetime(2019, 1, 24, 18, 30, 0))
    notify_ts = [n["notify_ts"] for n in at_notify["notifications"]]
    assert "2019-01-24 18:30:00" in notify_ts
    # No episode end / peak fields
    assert all("end_ts" not in n and "peak" not in n for n in at_notify["notifications"])

    before = present_method_m_timeline(datetime(2019, 1, 24, 18, 25, 0))
    before_ts = [n["notify_ts"] for n in before["notifications"]]
    assert "2019-01-24 18:30:00" not in before_ts
    assert before["window_end"] == "2019-01-24 18:25:00"
    assert all(p["ts"] <= "2019-01-24 18:25:00" for p in before["points"])


def test_jan15_notification_and_threshold(tiger_store):
    res = present_method_m_timeline(datetime(2019, 1, 15, 23, 0, 0))
    assert res["threshold"] == pytest.approx(4.517)
    assert any(n["notify_ts"] == "2019-01-15 23:00:00" for n in res["notifications"])
    # Jan 24 notify is in the future relative to this cursor — must not appear
    assert all(n["notify_ts"] <= "2019-01-15 23:00:00" for n in res["notifications"])
    assert "2019-01-24 18:30:00" not in [n["notify_ts"] for n in res["notifications"]]


def test_empty_before_coverage(tiger_store):
    res = present_method_m_timeline(datetime(2018, 12, 31, 12, 0, 0))
    assert res["status"] == "before_coverage"
    assert res["points"] == []
    assert res["notifications"] == []


def test_method_run_isolation(tiger_store):
    res = present_method_m_timeline(datetime(2019, 1, 12, 15, 0, 0))
    assert res["run_id"] == DEFAULT_RUN_ID
    assert res["provenance"]["run_id"] == DEFAULT_RUN_ID
    assert res["provenance"]["store"] == "tiger"
    assert res["source"] == "method_m_scores"
    # All points belong to the selected run's frozen grid (spot-check values exist)
    assert res["points"]
    assert res["missingness"]["returned_stamps"] == len(res["points"])


def test_rapid_backward_seek_drops_future_evidence(tiger_store):
    later = present_method_m_timeline(datetime(2019, 1, 24, 18, 35, 0))
    earlier = present_method_m_timeline(datetime(2019, 1, 24, 18, 25, 0))
    assert later["window_end"] > earlier["window_end"]
    later_only = {p["ts"] for p in later["points"]} - {p["ts"] for p in earlier["points"]}
    assert later_only
    assert all(ts > earlier["window_end"] for ts in later_only)
    assert "2019-01-24 18:30:00" in [n["notify_ts"] for n in later["notifications"]]
    assert "2019-01-24 18:30:00" not in [n["notify_ts"] for n in earlier["notifications"]]


def test_window_length_and_floor(tiger_store):
    cursor = datetime(2019, 1, 16, 0, 7, 0)
    res = present_method_m_timeline(cursor)
    end = floor_to_score_step(cursor)
    start = end - timedelta(hours=24)
    assert res["window_end"] == end.strftime("%Y-%m-%d %H:%M:%S")
    assert res["window_start"] == start.strftime("%Y-%m-%d %H:%M:%S")
    assert res["timeline_hours"] == 24
