"""Saved historical investigations — metadata only (research/demo feature).

Stores title/note/sensor/cursor/window/source in Tiger. Measurements are always
read from existing time-series tables at reopen time; saved views are not
immutable evidence. Opaque IDs are not authentication.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.db import get_connection

TITLE_MAX = 120
NOTE_MAX = 1000
SOURCE_MAX = 64
DEFAULT_SOURCE_ID = "battledim-ltown-zenodo-4017659"
MIN_WINDOW = timedelta(minutes=5)
MAX_WINDOW = timedelta(hours=24)
STEP_SECONDS = 300
ID_BYTES = 18  # token_urlsafe → opaque, unguessable-ish; still not auth

_TITLE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SENSOR_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class InvestigationValidationError(ValueError):
    pass


class InvestigationRateLimitError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many investigations created; try again later")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class SavedInvestigation:
    id: str
    title: str
    note: str | None
    sensor_id: str
    cursor_ts: datetime
    window_start: datetime
    window_end: datetime
    source_id: str
    created_at: datetime


@dataclass(frozen=True)
class InvestigationCreate:
    title: str
    note: str | None
    sensor_id: str
    cursor_ts: datetime
    window_start: datetime
    window_end: datetime
    source_id: str = DEFAULT_SOURCE_ID


def _strip_controls(text: str) -> str:
    return _TITLE_RE.sub("", text)


def validate_create(payload: InvestigationCreate) -> InvestigationCreate:
    title = _strip_controls(payload.title).strip()
    if not title:
        raise InvestigationValidationError("title is required")
    if len(title) > TITLE_MAX:
        raise InvestigationValidationError(f"title must be ≤ {TITLE_MAX} characters")

    note: str | None
    if payload.note is None:
        note = None
    else:
        note = _strip_controls(payload.note).strip()
        if not note:
            note = None
        elif len(note) > NOTE_MAX:
            raise InvestigationValidationError(f"note must be ≤ {NOTE_MAX} characters")

    sensor_id = payload.sensor_id.strip()
    if not _SENSOR_RE.fullmatch(sensor_id):
        raise InvestigationValidationError("sensor_id is invalid")

    source_id = payload.source_id.strip().lower()
    if not _SOURCE_RE.fullmatch(source_id):
        raise InvestigationValidationError(
            "source_id must be a short lowercase benchmark identifier"
        )

    for label, ts in (
        ("cursor_ts", payload.cursor_ts),
        ("window_start", payload.window_start),
        ("window_end", payload.window_end),
    ):
        if ts.tzinfo is not None:
            raise InvestigationValidationError(
                f"{label} must be TIMESTAMP WITHOUT TIME ZONE"
            )
        if ts.second != 0 or ts.microsecond != 0:
            raise InvestigationValidationError(
                f"{label} must align to whole minutes"
            )
        if (ts.minute * 60) % STEP_SECONDS != 0:
            raise InvestigationValidationError(
                f"{label} must align to the {STEP_SECONDS}-second SCADA grid"
            )

    if payload.window_end <= payload.window_start:
        raise InvestigationValidationError("window_end must be after window_start")
    span = payload.window_end - payload.window_start
    if span < MIN_WINDOW:
        raise InvestigationValidationError("investigation window is too short")
    if span > MAX_WINDOW:
        raise InvestigationValidationError(
            f"investigation window must be ≤ {int(MAX_WINDOW.total_seconds() // 3600)} hours"
        )
    if not (payload.window_start <= payload.cursor_ts <= payload.window_end):
        raise InvestigationValidationError("cursor must lie within the investigation window")

    return InvestigationCreate(
        title=title,
        note=note,
        sensor_id=sensor_id,
        cursor_ts=payload.cursor_ts,
        window_start=payload.window_start,
        window_end=payload.window_end,
        source_id=source_id,
    )


def new_opaque_id() -> str:
    return secrets.token_urlsafe(ID_BYTES)


class RateLimiter:
    """Simple per-key sliding window (process-local; enough for the public demo)."""

    def __init__(self, *, max_events: int, period_seconds: float) -> None:
        self.max_events = max_events
        self.period_seconds = period_seconds
        self._lock = threading.Lock()
        self._events: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self.period_seconds
            alive = [t for t in self._events.get(key, []) if t >= cutoff]
            if len(alive) >= self.max_events:
                oldest = min(alive)
                retry = int(max(1.0, self.period_seconds - (now - oldest)))
                raise InvestigationRateLimitError(retry)
            alive.append(now)
            self._events[key] = alive


# Demo default: 10 creates / hour / client key
CREATE_RATE_LIMITER = RateLimiter(max_events=10, period_seconds=3600.0)


class InvestigationStore(Protocol):
    def create(self, payload: InvestigationCreate, *, investigation_id: str | None = None) -> SavedInvestigation:
        ...

    def get(self, investigation_id: str) -> SavedInvestigation | None:
        ...


class MemoryInvestigationStore:
    def __init__(self) -> None:
        self._rows: dict[str, SavedInvestigation] = {}

    def create(
        self, payload: InvestigationCreate, *, investigation_id: str | None = None
    ) -> SavedInvestigation:
        validated = validate_create(payload)
        iid = investigation_id or new_opaque_id()
        row = SavedInvestigation(
            id=iid,
            title=validated.title,
            note=validated.note,
            sensor_id=validated.sensor_id,
            cursor_ts=validated.cursor_ts,
            window_start=validated.window_start,
            window_end=validated.window_end,
            source_id=validated.source_id,
            created_at=datetime.now().replace(microsecond=0),
        )
        self._rows[iid] = row
        return row

    def get(self, investigation_id: str) -> SavedInvestigation | None:
        return self._rows.get(investigation_id)


class TigerInvestigationStore:
    def create(
        self, payload: InvestigationCreate, *, investigation_id: str | None = None
    ) -> SavedInvestigation:
        validated = validate_create(payload)
        iid = investigation_id or new_opaque_id()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM sensors WHERE id = %s",
                    (validated.sensor_id,),
                )
                if cur.fetchone() is None:
                    raise InvestigationValidationError(
                        f"Unknown sensor: {validated.sensor_id}"
                    )
                cur.execute(
                    """
                    INSERT INTO saved_investigations (
                        id, title, note, sensor_id, cursor_ts,
                        window_start, window_end, source_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, title, note, sensor_id, cursor_ts,
                              window_start, window_end, source_id, created_at
                    """,
                    (
                        iid,
                        validated.title,
                        validated.note,
                        validated.sensor_id,
                        validated.cursor_ts,
                        validated.window_start,
                        validated.window_end,
                        validated.source_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return SavedInvestigation(**row)

    def get(self, investigation_id: str) -> SavedInvestigation | None:
        if not investigation_id or len(investigation_id) > 64:
            return None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, note, sensor_id, cursor_ts,
                           window_start, window_end, source_id, created_at
                    FROM saved_investigations
                    WHERE id = %s
                    """,
                    (investigation_id,),
                )
                row = cur.fetchone()
        return SavedInvestigation(**row) if row else None


_store: InvestigationStore | None = None


def get_investigation_store() -> InvestigationStore:
    global _store
    if _store is None:
        from app.config import get_settings

        mode = (get_settings().ripple_investigation_store or "tiger").strip().lower()
        _store = (
            MemoryInvestigationStore()
            if mode == "memory"
            else TigerInvestigationStore()
        )
    return _store


def set_investigation_store(store: InvestigationStore | None) -> None:
    """Test helper to inject a memory store."""
    global _store
    _store = store
