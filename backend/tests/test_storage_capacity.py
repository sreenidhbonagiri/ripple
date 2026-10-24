"""Storage capacity policy: explicit limit, 20% headroom, no 2 GiB fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app import storage_capacity as sc  # noqa: E402


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_working_ceiling_750_mib_headroom():
    limit = 786_432_000  # 750 MiB
    assert sc.working_ceiling_bytes(limit) == 629_145_600  # 600 MiB
    assert sc.WORKING_FRACTION == 0.80
    assert sc.HEADROOM_FRACTION == 0.20


def test_require_storage_limit_missing_raises(monkeypatch):
    monkeypatch.delenv("RIPPLE_STORAGE_LIMIT_BYTES", raising=False)
    # Ensure Settings does not pick a value from a real .env during this unit test
    with patch.object(sc, "get_settings") as gs:
        gs.return_value = MagicMock(ripple_storage_limit_bytes=None)
        with pytest.raises(RuntimeError, match="RIPPLE_STORAGE_LIMIT_BYTES must be set"):
            sc.require_storage_limit_bytes()


def test_require_storage_limit_non_positive_raises():
    with patch.object(sc, "get_settings") as gs:
        gs.return_value = MagicMock(ripple_storage_limit_bytes=0)
        with pytest.raises(RuntimeError, match="RIPPLE_STORAGE_LIMIT_BYTES must be set"):
            sc.require_storage_limit_bytes()


def test_no_two_gib_fallback_constant():
    assert not hasattr(sc, "DEFAULT_LIMIT_BYTES")
    assert getattr(sc, "DEFAULT_LIMIT_BYTES", None) is None
    # Guard against reintroducing an unverified 2 GiB default
    src = Path(sc.__file__).read_text(encoding="utf-8")
    assert "2147483648" not in src
    assert "2 * 1024" not in src
    assert "2 GiB" not in src


def test_assert_capacity_uses_working_ceiling_not_remaining_fraction():
    """Projected db+import must stay under limit*0.8 (not 80% of remaining free)."""
    snap = sc.StorageSnapshot(
        database_bytes=500_000_000,
        readings_hypertable_bytes=400_000_000,
        readings_15m_bytes=50_000_000,
        limit_bytes=786_432_000,
        working_ceiling_bytes=629_145_600,
        available_to_limit_bytes=286_432_000,
        usable_bytes=129_145_600,
        readings_count=330_336,
        bytes_per_reading_est=320,
    )
    with (
        patch.object(sc, "get_storage_snapshot", return_value=snap),
    ):
        # 129_145_600 / 320 = 403_580 readings still fit under ceiling
        ok = sc.assert_capacity_for_import(100_000)
        assert ok.working_ceiling_bytes == 629_145_600

        # Push projected over ceiling
        with pytest.raises(RuntimeError, match="working ceiling"):
            sc.assert_capacity_for_import(500_000)
