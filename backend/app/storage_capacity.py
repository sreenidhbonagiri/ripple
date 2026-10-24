"""Database storage capacity checks (no credentials in output)."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.db import get_connection

# 20% headroom against the configured service limit.
HEADROOM_FRACTION = 0.20
WORKING_FRACTION = 1.0 - HEADROOM_FRACTION  # 0.80 → 600 MiB when limit is 750 MiB
BYTES_PER_READING_FALLBACK = 320  # includes index/CAGG overhead cushion


@dataclass(frozen=True)
class StorageSnapshot:
    database_bytes: int  # pg_database_size: tables, indexes, toast, CAGGs, etc.
    readings_hypertable_bytes: int
    readings_15m_bytes: int
    limit_bytes: int
    working_ceiling_bytes: int
    available_to_limit_bytes: int
    usable_bytes: int  # room under working ceiling
    readings_count: int
    bytes_per_reading_est: int


def require_storage_limit_bytes() -> int:
    settings = get_settings()
    limit = settings.ripple_storage_limit_bytes
    if limit is None or limit <= 0:
        raise RuntimeError(
            "RIPPLE_STORAGE_LIMIT_BYTES must be set explicitly in project-root .env "
            "(Tiger Console service storage). No default fallback is applied."
        )
    return int(limit)


def working_ceiling_bytes(limit_bytes: int) -> int:
    return int(limit_bytes * WORKING_FRACTION)


def _relation_bytes(cur, qualified_name: str) -> int:
    cur.execute("SELECT pg_total_relation_size(%s::regclass) AS bytes", (qualified_name,))
    row = cur.fetchone()
    return int(row["bytes"] or 0)


def get_storage_snapshot() -> StorageSnapshot:
    limit = require_storage_limit_bytes()
    ceiling = working_ceiling_bytes(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Total database size includes indexes, TOAST, and continuous aggregates.
            cur.execute("SELECT pg_database_size(current_database()) AS bytes")
            database_bytes = int(cur.fetchone()["bytes"])

            cur.execute("SELECT COUNT(*)::BIGINT AS n FROM readings")
            readings_count = int(cur.fetchone()["n"])

            # Prefer Timescale hypertable_size (chunks + indexes). Avoid
            # format('%I...') here: with no psycopg params, '%%' is sent literally.
            readings_ht = 0
            try:
                cur.execute(
                    """
                    SELECT hypertable_size(
                        (quote_ident(hypertable_schema) || '.' ||
                         quote_ident(hypertable_name))::regclass
                    ) AS bytes
                    FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'readings'
                    """
                )
                row = cur.fetchone()
                readings_ht = int(row["bytes"]) if row and row["bytes"] is not None else 0
            except Exception:  # noqa: BLE001
                conn.rollback()
                readings_ht = _relation_bytes(cur, "readings")

            cagg_bytes = 0
            try:
                cur.execute(
                    """
                    SELECT
                        quote_ident(materialization_hypertable_schema)
                          || '.' ||
                        quote_ident(materialization_hypertable_name) AS mat
                    FROM timescaledb_information.continuous_aggregates
                    WHERE view_name = 'readings_15m'
                    """
                )
                row = cur.fetchone()
                if row and row["mat"]:
                    cur.execute(
                        "SELECT hypertable_size(%s::regclass) AS bytes",
                        (row["mat"],),
                    )
                    cagg_bytes = int(cur.fetchone()["bytes"] or 0)
            except Exception:  # noqa: BLE001
                conn.rollback()
                try:
                    cagg_bytes = _relation_bytes(cur, "readings_15m")
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    cagg_bytes = 0

    bpr = (
        max(int(readings_ht / readings_count), BYTES_PER_READING_FALLBACK)
        if readings_count > 0 and readings_ht > 0
        else BYTES_PER_READING_FALLBACK
    )
    available_to_limit = max(limit - database_bytes, 0)
    usable = max(ceiling - database_bytes, 0)
    return StorageSnapshot(
        database_bytes=database_bytes,
        readings_hypertable_bytes=readings_ht,
        readings_15m_bytes=cagg_bytes,
        limit_bytes=limit,
        working_ceiling_bytes=ceiling,
        available_to_limit_bytes=available_to_limit,
        usable_bytes=usable,
        readings_count=readings_count,
        bytes_per_reading_est=bpr,
    )


def estimate_import_bytes(new_reading_count: int, snapshot: StorageSnapshot) -> int:
    return int(new_reading_count * snapshot.bytes_per_reading_est)


def assert_capacity_for_import(new_reading_count: int) -> StorageSnapshot:
    snap = get_storage_snapshot()
    needed = estimate_import_bytes(new_reading_count, snap)
    projected = snap.database_bytes + needed
    if projected > snap.working_ceiling_bytes:
        raise RuntimeError(
            "Capacity check failed: projected database size "
            f"{projected} bytes exceeds working ceiling "
            f"{snap.working_ceiling_bytes} bytes "
            f"(20% headroom under limit {snap.limit_bytes}; "
            f"current_db={snap.database_bytes}, est_import={needed}). "
            "Import stopped; service was not upgraded."
        )
    return snap
