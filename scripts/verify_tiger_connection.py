#!/usr/bin/env python3
"""Verify Tiger Cloud / TimescaleDB connectivity. Never prints credentials."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Allow `python scripts/verify_tiger_connection.py` from repo root or elsewhere.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402


def _sanitize(message: str, database_url: str | None) -> str:
    """Strip connection strings, passwords, and userinfo from error text."""
    text = message
    if database_url:
        text = text.replace(database_url, "[DATABASE_URL]")
        try:
            parsed = urlparse(database_url)
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


def main() -> int:
    settings = get_settings()
    database_url = settings.database_url
    if not database_url:
        print("FAIL: DATABASE_URL is not set in project-root .env")
        return 1

    try:
        import psycopg
    except ImportError:
        print("FAIL: psycopg is not installed in the virtual environment")
        return 1

    conn = None
    try:
        conn = psycopg.connect(database_url, connect_timeout=8)
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            one = cur.fetchone()
            if one is None or one[0] != 1:
                print("FAIL: SELECT 1 did not return 1")
                return 1

            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';"
            )
            row = cur.fetchone()
            if row is None:
                print("OK: connection succeeded")
                print("TimescaleDB: not installed (extension missing)")
                return 0

            version = str(row[0])
            print("OK: connection succeeded")
            print(f"TimescaleDB: {version}")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {_sanitize(str(exc), database_url)}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
