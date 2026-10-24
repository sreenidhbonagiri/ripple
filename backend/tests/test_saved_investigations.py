"""Saved investigation validation, rate limits, and store round-trips."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import PassThroughError, get_connection, sanitize_db_error  # noqa: E402
from app.investigations import (  # noqa: E402
    CREATE_RATE_LIMITER,
    InvestigationCreate,
    InvestigationRateLimitError,
    InvestigationValidationError,
    MemoryInvestigationStore,
    RateLimiter,
    TigerInvestigationStore,
    client_rate_limit_key,
    set_investigation_store,
    validate_create,
)
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def memory_store():
    store = MemoryInvestigationStore(
        known_sensors={"n54"},
        coverage_start=datetime(2019, 1, 1, 0, 0, 0),
        coverage_end=datetime(2019, 1, 31, 23, 55, 0),
    )
    set_investigation_store(store)
    CREATE_RATE_LIMITER._events.clear()
    yield store
    set_investigation_store(None)
    CREATE_RATE_LIMITER._events.clear()
    CREATE_RATE_LIMITER.max_events = 10


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


def test_validate_rejects_unsupported_source_and_coverage():
    with pytest.raises(InvestigationValidationError, match="supported benchmark"):
        validate_create(_valid(source_id="other-benchmark-v1"))
    with pytest.raises(InvestigationValidationError, match="outside available"):
        validate_create(
            _valid(
                window_start=datetime(2018, 6, 1, 0, 0, 0),
                window_end=datetime(2018, 6, 1, 3, 0, 0),
                cursor_ts=datetime(2018, 6, 1, 1, 0, 0),
            ),
            coverage_start=datetime(2019, 1, 1, 0, 0, 0),
            coverage_end=datetime(2019, 1, 31, 23, 55, 0),
        )


def test_validate_rejects_private_control_chars_and_overlong_fields():
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(title=""))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(title="x" * 121))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(note="n" * 1001))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(sensor_id="n54;drop"))


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
        validate_create(_valid(cursor_ts=datetime(2019, 1, 12, 13, 0, 0)))
    with pytest.raises(InvestigationValidationError):
        validate_create(_valid(cursor_ts=datetime(2019, 1, 12, 15, 1, 0)))


def test_memory_round_trip():
    store = MemoryInvestigationStore(known_sensors={"n54"})
    created = store.create(_valid())
    loaded = store.get(created.id)
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.sensor_id == "n54"
    assert store.get("missing") is None


def test_rate_limiter_blocks_and_bounds_keys():
    limiter = RateLimiter(max_events=3, period_seconds=60.0, max_keys=5)
    limiter.check("a")
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(InvestigationRateLimitError):
        limiter.check("a")
    limiter.check("b")
    for i in range(20):
        limiter.check(f"flood-{i}")
    assert len(limiter._events) <= 5


def test_client_rate_limit_key_ignores_spoofed_leftmost_xff():
    # Spoofed left, real client, then loopback nginx/caddy hop on the right.
    key = client_rate_limit_key(
        x_forwarded_for="203.0.113.9, 198.51.100.44, 127.0.0.1",
        x_real_ip="127.0.0.1",
        peer_host="172.18.0.3",
    )
    assert key == "198.51.100.44"
    # Leftmost alone must not win when only spoof + loopback remain after skip… 
    # If all hops trusted, fall back to peer.
    key2 = client_rate_limit_key(
        x_forwarded_for="127.0.0.1",
        x_real_ip="127.0.0.1",
        peer_host="172.18.0.3",
    )
    assert key2 == "172.18.0.3"


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
    assert body["share_path"] == f"/?i={body['id']}"
    assert "not authentication" in body["public_note_notice"].lower()
    assert body["note"] == "Plain text only"

    fetched = client.get(f"/api/investigations/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["sensor_id"] == "n54"


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
    unsupported = client.post(
        "/api/investigations",
        json={
            "title": "x",
            "sensor_id": "n54",
            "cursor": "2019-01-12T15:00:00",
            "window_start": "2019-01-12T14:00:00",
            "window_end": "2019-01-12T17:00:00",
            "source_id": "not-the-battledim-source",
        },
    )
    assert unsupported.status_code == 400
    unknown = client.post(
        "/api/investigations",
        json={
            "title": "x",
            "sensor_id": "n_unknown_zz",
            "cursor": "2019-01-12T15:00:00",
            "window_start": "2019-01-12T14:00:00",
            "window_end": "2019-01-12T17:00:00",
        },
    )
    assert unknown.status_code == 400
    assert "Unknown sensor" in unknown.json()["detail"]


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
    CREATE_RATE_LIMITER.max_events = 10


@pytest.fixture
def require_db():
    get_settings.cache_clear()
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")
    yield
    get_settings.cache_clear()


def test_get_connection_preserves_passthrough_errors(require_db):
    class Boom(PassThroughError):
        pass

    with pytest.raises(Boom, match="keep-me"):
        with get_connection() as _conn:
            raise Boom("keep-me")


def test_sanitize_still_redacts_url_credentials():
    # Does not print secrets; only checks redaction helper behavior.
    sample = "failed connect to postgresql://user:supersecret@db.example:5432/app"
    out = sanitize_db_error(sample, "postgresql://user:supersecret@db.example:5432/app")
    assert "supersecret" not in out
    assert "[REDACTED]" in out or "[DATABASE_URL]" in out


def test_tiger_store_unknown_sensor_is_validation_not_runtime(require_db):
    """Exercises real get_connection + TigerInvestigationStore boundary."""
    set_investigation_store(None)
    store = TigerInvestigationStore()
    with pytest.raises(InvestigationValidationError, match="Unknown sensor") as ei:
        store.create(_valid(sensor_id="n_does_not_exist_zz99"))
    assert not isinstance(ei.value, RuntimeError)

    # HTTP mapping must stay 400 (not sanitized 500).
    set_investigation_store(store)
    CREATE_RATE_LIMITER._events.clear()
    client = TestClient(app)
    res = client.post(
        "/api/investigations",
        json={
            "title": "bad sensor",
            "sensor_id": "n_does_not_exist_zz99",
            "cursor": "2019-01-12T15:00:00",
            "window_start": "2019-01-12T14:00:00",
            "window_end": "2019-01-12T17:00:00",
            "source_id": "battledim-ltown-zenodo-4017659",
        },
    )
    assert res.status_code == 400, res.text
    assert "Unknown sensor" in res.json()["detail"]
