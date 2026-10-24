"""Tiger evidence serves saved January benchmark — never re-runs timings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.tiger_evidence import (  # noqa: E402
    benchmark_artifact_path,
    present_tiger_evidence,
)


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


def test_benchmark_artifact_exists_and_shaped():
    path = benchmark_artifact_path()
    if not path.is_file():
        pytest.skip("January benchmark artifact not written yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("repeats") == 7
    assert data.get("timing_label") == "database_execution"
    assert data.get("not_application_loading_time") is True
    assert isinstance(data.get("workloads"), list)
    assert len(data["workloads"]) >= 1
    for wl in data["workloads"]:
        assert "equivalence" in wl
        assert "database_execution_explain" in wl
        assert wl["database_execution_explain"]["scope"] == "database_execution"


def test_present_tiger_evidence_loads_artifact_not_rebench(require_db):
    path = benchmark_artifact_path()
    if not path.is_file():
        pytest.skip("January benchmark artifact not written yet")
    payload = present_tiger_evidence()
    assert payload["reran_expensive_benchmark"] is False
    assert payload["saved_benchmark"]["available"] is True
    assert payload["saved_benchmark"]["run_date_utc"]
    assert payload["saved_benchmark"]["repeats"] == 7
    assert "database execution" in payload["saved_benchmark"]["latency_distinction"].lower()
    assert payload["live_stored"]["readings_total"] > 0
    assert payload["storage"]["database_bytes"] > 0
    assert payload["storage"]["limit_bytes"] == 786_432_000
    assert payload["storage"]["working_ceiling_bytes"] == 629_145_600
    workloads = payload["saved_benchmark"]["workloads"]
    assert len(workloads) >= 1
    assert all(w.get("outputs_match") for w in workloads)
    assert all(w.get("timing_label") == "database execution" for w in workloads)
