#!/usr/bin/env python3
"""Apply SQL migrations against Tiger Cloud / TimescaleDB."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db import get_connection, sanitize_db_error  # noqa: E402


def main() -> int:
    migrations_dir = REPO_ROOT / "backend" / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print("No migration files found")
        return 1

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            conn.commit()

            for path in files:
                version = path.name
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s",
                        (version,),
                    )
                    if cur.fetchone():
                        print(f"skip {version}")
                        continue

                sql = path.read_text(encoding="utf-8")
                # Continuous aggregate refresh must not run inside these DDL migrations.
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
                conn.commit()
                print(f"applied {version}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {sanitize_db_error(str(exc))}")
        return 1

    print("OK: migrations complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
