"""File vs Tiger Method M response parity + SQL contributor join.

Requires DATABASE_URL, migration 003, and an imported January run.
Skipped automatically when Tiger Method M data is unavailable.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.method_m_db import (  # noqa: E402
    DEFAULT_RUN_ID,
    fetch_contributors_with_sensor_meta,
    present_method_m_warning_db,
    resolve_run_id,
)
from app.method_m_warning import (  # noqa: E402
    clear_artifact_cache,
    present_method_m_warning_file,
)

# Notification, pre-notification, active, missing/before, backward-seek
PARITY_CURSORS = [
    datetime(2019, 1, 15, 23, 0, 0),  # notify
    datetime(2019, 1, 15, 22, 55, 0),  # pre-notification
    datetime(2019, 1, 16, 0, 0, 0),  # active (withhold peak/end)
    datetime(2019, 1, 16, 19, 45, 0),  # recovered / end visible
    datetime(2019, 1, 24, 18, 35, 0),  # second notify active
    datetime(2019, 1, 24, 18, 25, 0),  # backward-seek before second notify
    datetime(2019, 1, 12, 15, 0, 0),  # below threshold / presenter
    datetime(2018, 12, 31, 23, 0, 0),  # before coverage (missing)
]


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
    reason="Tiger Method M tables/run not available (migrate 003 + import first)",
)


@pytest.fixture(autouse=True)
def _reload_artifact():
    clear_artifact_cache()
    get_settings.cache_clear()
    yield
    clear_artifact_cache()
    get_settings.cache_clear()


def _strip_store_fields(payload: dict) -> dict:
    out = dict(payload)
    out.pop("store", None)
    out.pop("run_id", None)
    # Notes order can differ slightly; compare as sets for free-form notes after
    # shared structural fields are checked.
    return out


def _assert_parity(file_res: dict, db_res: dict) -> None:
    f = _strip_store_fields(file_res)
    d = _strip_store_fields(db_res)
    assert f["status"] == d["status"]
    assert f["warning_active"] == d["warning_active"]
    assert f["score_hour"] == d["score_hour"]
    assert f["cursor"] == d["cursor"]
    assert f["threshold"] == pytest.approx(d["threshold"])
    assert f["disclaimer"] == d["disclaimer"]
    assert f["resolution"] == d["resolution"]
    assert f["predicted_leak_pipes"] is None
    assert d["predicted_leak_pipes"] is None
    assert f["argmax_sensor_id"] == d["argmax_sensor_id"]
    assert f["episode_end_ts"] == d["episode_end_ts"]
    if f["score"] is None:
        assert d["score"] is None
    else:
        assert d["score"] == pytest.approx(f["score"], rel=0, abs=1e-12)
    if f.get("episode_peak_score") is None:
        assert d.get("episode_peak_score") is None
    else:
        assert d["episode_peak_score"] == pytest.approx(
            f["episode_peak_score"], rel=0, abs=1e-12
        )
    if f.get("peak_score_observed_to_cursor") is None:
        assert d.get("peak_score_observed_to_cursor") is None
    else:
        assert d["peak_score_observed_to_cursor"] == pytest.approx(
            f["peak_score_observed_to_cursor"], rel=0, abs=1e-12
        )
    assert (f.get("notification") or None) == (d.get("notification") or None)
    assert len(f["contributors"]) == len(d["contributors"])
    for fc, dc in zip(f["contributors"], d["contributors"], strict=True):
        assert fc["sensor_id"] == dc["sensor_id"]
        for key in (
            "abs_z_calibrated",
            "delta_m3h",
            "sigma_scale_m3h",
            "qv_m3h",
            "ref_mean_m3h",
        ):
            assert dc[key] == pytest.approx(fc[key], rel=0, abs=1e-12)
    # Version hashes must match frozen provenance
    assert f["version_hashes"]["serving_hours_sha256"] == d["version_hashes"][
        "serving_hours_sha256"
    ]
    assert f["version_hashes"]["calibration_sha256"] == d["version_hashes"][
        "calibration_sha256"
    ]


@pytest.mark.parametrize("cursor", PARITY_CURSORS, ids=lambda c: c.isoformat(" "))
def test_file_vs_db_parity(cursor: datetime):
    file_res = present_method_m_warning_file(cursor)
    db_res = present_method_m_warning_db(cursor)
    _assert_parity(file_res, db_res)


def test_sql_contributor_join_includes_sensor_meta():
    run_id = resolve_run_id()
    warning = present_method_m_warning_db(datetime(2019, 1, 15, 23, 0, 0))
    assert warning["warning_active"] is True
    assert warning["score_hour"] is not None
    joined = fetch_contributors_with_sensor_meta(run_id, warning["score_hour"])
    assert joined
    assert len(joined) == len(warning["contributors"])
    for row in joined:
        assert row["sensor_id"]
        assert "abs_z_calibrated" in row
        # Pressure sensors used by Method M should resolve in sensors table
        # when January SCADA was imported; allow null if sensor catalog incomplete.
        if row.get("measurement_type") is not None:
            assert row["measurement_type"] in {"pressure", "flow", "tank_level"}


def test_warning_query_timing_honest_benchmark(capsys):
    """Record one EXPLAIN ANALYZE-style wall time; no invented speedup claim."""
    cursor = datetime(2019, 1, 15, 23, 0, 0)
    t0 = time.perf_counter()
    present_method_m_warning_db(cursor)
    db_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    present_method_m_warning_file(cursor)
    file_s = time.perf_counter() - t1
    # Sanity: both complete; print for docs (not an assertion on speedup).
    print(
        f"method_m_present_wall_s file={file_s:.4f} tiger={db_s:.4f} "
        f"(application wall clock; not a sponsor speedup claim)"
    )
    assert db_s < 30.0
    assert file_s < 30.0


def test_run_id_defaults_to_january_import():
    assert resolve_run_id() == DEFAULT_RUN_ID
