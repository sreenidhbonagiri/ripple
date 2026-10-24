"""Database helpers — sanitized errors, root .env DATABASE_URL."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


class PassThroughError(Exception):
    """Domain errors raised inside ``get_connection`` that must not be wrapped.

    ``get_connection`` sanitizes unexpected DB failures as ``RuntimeError``.
    Subclass this for validation / application errors that should propagate
    unchanged (avoids circular imports with feature modules).
    """


def sanitize_db_error(message: str, database_url: str | None = None) -> str:
    text = message
    url = database_url or get_settings().database_url
    if url:
        text = text.replace(url, "[DATABASE_URL]")
        try:
            parsed = urlparse(url)
            if parsed.password:
                text = text.replace(parsed.password, "[REDACTED]")
            if parsed.username:
                text = text.replace(parsed.username, "[REDACTED]")
            if parsed.hostname:
                text = text.replace(parsed.hostname, "[HOST]")
        except Exception:  # noqa: BLE001
            pass
    text = re.sub(r"postgres(?:ql)?://\S+", "[DATABASE_URL]", text, flags=re.I)
    text = re.sub(r"password[=:]\s*\S+", "password=[REDACTED]", text, flags=re.I)
    return text


@contextmanager
def get_connection(*, connect_timeout: int = 10) -> Iterator[psycopg.Connection]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = None
    try:
        conn = psycopg.connect(
            settings.database_url,
            connect_timeout=connect_timeout,
            row_factory=dict_row,
        )
        yield conn
    except PassThroughError:
        # Preserve intentional validation / domain errors (e.g. unknown sensor).
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(sanitize_db_error(str(exc), settings.database_url)) from None
    finally:
        if conn is not None:
            conn.close()
