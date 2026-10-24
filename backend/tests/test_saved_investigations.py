"""Saved investigation validation, rate limits, and memory-store round-trips."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.investigations import (  # noqa: E402
    CREATE_RATE_LIMITER,
    InvestigationCreate,
    InvestigationRateLimitError,
    InvestigationValidationError,
    MemoryInvestigationStore,
    RateLimiter,
    set_investigation_store,
    validate_create,
)
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def memory_store():
    store = MemoryInvestigationStore()
    set_investigation_store(store)
    # Isolate rate-limit state per test
    CREATE_RATE_LIMITER._events.clear()
    yield store
    set_investigation_store(None)
    CREATE_RATE_LIMITER._events.clear()


def _valid(**overrides):
    base = dict(
        title="Jan 12 n54 walkthrough",
        note="Public observation note",
        sensor_id="n54",
        cursor_ts=datetime(2019, 1, 12, 15, 0, 0),
        window_start=datetime(2019, 1, 12, 14, 0, 0),
        window_end=datetime(2019, 1, 12, 17, 0, 0),
        source_id="battledim-ltown-zenodo-4017659",
    )
    base.update(overrides)
    return InvestigationCreate(**base)


def test_validate_accepts_presenter_shaped_payload():
    out = validate_create(_valid())
    assert out.title == "Jan 12 n54 walkthrough"
    assert out.note == "Public observation note"


def test_validate_rejects_private_control_chars_and_overlong_fields():
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(title=""))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(title="x" * 121))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(note="n" * 1001))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(sensor_id="n54;drop"))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(source_id="Not Valid"))


def test_validate_window_and_cursor_rules():
    with pytest.raises(InvestigationValidationError):
        validate_create(
            _valid(
                window_start=datetime(2019, 1, 12, 14, 0, 0),
                window_end=datetime(2019, 1, 12, 14, 2, 0),
            )
        )
    with pytest.raises(InvestigationValidationError):
        validate_create(
            _valid(
                window_start=datetime(2019, 1, 1, 0, 0, 0),
                window_end=datetime(2019, 1, 3, 0, 0, 0),
            )
        )
    with pytest.raises(InvestigationValidationError):
        validate_create(
            _valid(cursor_ts=datetime(2019, 1, 12, 13, 0, 0))
        )
    with pytest.raises(InvestigationValidationError):
        validate_create(
            _valid(cursor_ts=datetime(2019, 1, 12, 15, 1, 0))
        )


def test_memory_round_trip():
    store = MemoryInvestigationStore()
    created = store.create(_valid())
    loaded = store.get(created.id)
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.sensor_id == "n54"
    assert loaded.cursor_ts == datetime(2019, 1, 12, 15, 0, 0)
    assert store.get("missing") is None


def test_rate_limiter_blocks_after_max():
    limiter = RateLimiter(max_events=3, period_seconds=60.0)
    limiter.check("a")
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(InvestigationRateLimitError):
        limiter.check("a")
    limiter.check("b")  # other key still ok


def test_api_create_and_get_round_trip(memory_store):
    client = TestClient(app)
    payload = {
        "title": "Shared n54 view",
        "note": "Plain text only",
        "sensor_id": "n54",
        "cursor": "2019-01-12T15:00:00",
        "window_start": "2019-01-12T14:00:00",
        "window_end": "2019-01-12T17:00:00",
        "source_id": "battledim-ltown-zenodo-4017659",
    }
    created = client.post("/api/investigations", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["id"]
    assert body["share_path"] == f"/?i={body['id']}"
    assert "not authentication" in body["public_note_notice"].lower()
    assert "not a frozen evidence" in body["evidence_notice"].lower()
    assert body["note"] == "Plain text only"

    fetched = client.get(f"/api/investigations/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["sensor_id"] == "n54"
    assert fetched.json()["cursor"].startswith("2019-01-12T15:00:00")


def test_api_not_found_and_validation_errors(memory_store):
    client = TestClient(app)
    assert client.get("/api/investigations/does-not-exist").status_code == 404
    bad = client.post(
        "/api/investigations",
        json={
            "title": "x",
            "sensor_id": "n54",
            "cursor": "2019-01-12T15:00:00",
            "window_start": "2019-01-12T17:00:00",
            "window_end": "2019-01-12T14:00:00",
        },
    )
    assert bad.status_code == 400


def test_api_no_public_edit_or_delete(memory_store):
    client = TestClient(app)
    created = client.post(
        "/api/investigations",
        json={
            "title": "tmp",
            "sensor_id": "n54",
            "cursor": "2019-01-12T15:00:00",
            "window_start": "2019-01-12T14:00:00",
            "window_end": "2019-01-12T17:00:00",
        },
    )
    assert created.status_code == 201
    iid = created.json()["id"]
    assert client.put(f"/api/investigations/{iid}", json={"title": "nope"}).status_code == 405
    assert client.patch(f"/api/investigations/{iid}", json={"title": "nope"}).status_code == 405
    assert client.delete(f"/api/investigations/{iid}").status_code == 405


def test_api_rate_limit(memory_store):
    client = TestClient(app)
    # Shrink limiter for this test
    CREATE_RATE_LIMITER.max_events = 2
    CREATE_RATE_LIMITER.period_seconds = 3600.0
    CREATE_RATE_LIMITER._events.clear()
    payload = {
        "title": "rate",
        "sensor_id": "n54",
        "cursor": "2019-01-12T15:00:00",
        "window_start": "2019-01-12T14:00:00",
        "window_end": "2019-01-12T17:00:00",
    }
    assert client.post("/api/investigations", json=payload).status_code == 201
    assert client.post("/api/investigations", json=payload).status_code == 201
    limited = client.post("/api/investigations", json=payload)
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    # restore demo defaults
    CREATE_RATE_LIMITER.max_events = 10
