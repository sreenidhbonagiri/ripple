"""Tiger Data sponsor evidence: live counts + saved January benchmark artifact.

Expensive raw/CAGG timing loops are never re-run on API or page load.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT, get_settings
from app.db import get_connection
from app.schemas import PRESENTER_END, PRESENTER_START
from app.storage_capacity import get_storage_snapshot, require_storage_limit_bytes

DEFAULT_ARTIFACT = REPO_ROOT / "artifacts" / "january_raw_cagg_benchmark.json"


def benchmark_artifact_path() -> Path:
    settings = get_settings()
    override = getattr(settings, "ripple_benchmark_artifact", None)
    if override:
        return Path(override)
    return DEFAULT_ARTIFACT


def _load_saved_benchmark() -> dict[str, Any] | None:
    path = benchmark_artifact_path()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    data["_artifact"] = {
        "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "run_date_utc": data.get("run_date_utc") or mtime.strftime("%Y-%m-%d"),
        "run_mtime_utc": mtime.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "repeats": data.get("repeats"),
    }
    return data


def _pretty_bytes(n: int) -> str:
    for unit, denom in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if abs(n) >= denom:
            return f"{n / denom:.2f} {unit}"
    return f"{n} B"


def present_tiger_evidence() -> dict[str, Any]:
    """Live stored counts/size + saved benchmark (no re-bench)."""
    saved = _load_saved_benchmark()
    try:
        limit_bytes = require_storage_limit_bytes()
    except RuntimeError:
        limit_bytes = None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::BIGINT AS n FROM sensors")
            n_sensors = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*)::BIGINT AS n FROM readings")
            n_readings = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*)::BIGINT AS n FROM readings
                WHERE ts >= %s AND ts <= %s
                """,
                (PRESENTER_START, PRESENTER_END),
            )
            n_presenter = int(cur.fetchone()["n"])
            cur.execute("SELECT MIN(ts) AS tmin, MAX(ts) AS tmax FROM readings")
            ts_range = cur.fetchone()
            cur.execute("SELECT COUNT(*)::BIGINT AS n FROM readings_15m")
            n_cagg = int(cur.fetchone()["n"])
            cur.execute("SELECT pg_database_size(current_database())::BIGINT AS n")
            db_bytes = int(cur.fetchone()["n"])

            method_m_live: dict[str, Any] | None = None
            try:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'method_m_runs'
                    """
                )
                if cur.fetchone():
                    cur.execute(
                        """
                        SELECT run_id, n_score_stamps, n_contributor_rows,
                               n_notifications, serving_hours_sha256
                        FROM method_m_runs
                        ORDER BY run_id
                        """
                    )
                    runs = [dict(r) for r in cur.fetchall()]
                    cur.execute(
                        """
                        SELECT
                            COALESCE(SUM(pg_total_relation_size(quote_ident(c.relname)::regclass)), 0)
                                ::BIGINT AS bytes
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public'
                          AND c.relname IN (
                            'method_m_runs',
                            'method_m_scores',
                            'method_m_sensor_evidence',
                            'method_m_notifications'
                          )
                        """
                    )
                    mm_bytes = int(cur.fetchone()["bytes"] or 0)
                    method_m_live = {
                        "tables_present": True,
                        "runs": runs,
                        "relation_bytes_approx": mm_bytes,
                        "relation_pretty": _pretty_bytes(mm_bytes),
                        "note": (
                            "Frozen Method M detector outputs only "
                            "(no evaluation labels, no raw SCADA duplication). "
                            "Serving defaults to file unless RIPPLE_METHOD_M_STORE=tiger."
                        ),
                    }
            except Exception:  # noqa: BLE001
                conn.rollback()
                method_m_live = {
                    "tables_present": False,
                    "note": "method_m_* tables not available (migration 003 not applied).",
                }

    snap = None
    try:
        snap = get_storage_snapshot()
        db_bytes = snap.database_bytes
        limit_bytes = snap.limit_bytes
        working_ceiling = snap.working_ceiling_bytes
        readings_ht = snap.readings_hypertable_bytes
        cagg_bytes = snap.readings_15m_bytes
    except Exception:  # noqa: BLE001
        working_ceiling = int(limit_bytes * 0.80) if limit_bytes else None
        readings_ht = None
        cagg_bytes = None

    workloads: list[dict[str, Any]] = []
    if saved:
        for wl in saved.get("workloads", []):
            if wl.get("skipped"):
                continue
            db = wl.get("database_execution_explain") or {}
            raw = db.get("raw") or wl.get("raw_db") or {}
            cagg = db.get("cagg") or wl.get("cagg_db") or {}
            eq = wl.get("equivalence") or {}
            workloads.append(
                {
                    "id": wl.get("id"),
                    "label": wl.get("label"),
                    "supports_investigation": wl.get("supports_investigation")
                    or wl.get("supports"),
                    "window": wl.get("window"),
                    "outputs_match": eq.get("outputs_match"),
                    "raw_rows": eq.get("raw_row_count"),
                    "cagg_rows": eq.get("cagg_row_count"),
                    "average_method": eq.get("average_method"),
                    "db_median_raw_s": raw.get("median_s"),
                    "db_median_cagg_s": cagg.get("median_s"),
                    "db_p95_raw_s": raw.get("p95_s"),
                    "db_p95_cagg_s": cagg.get("p95_s"),
                    "db_median_speedup": wl.get("db_median_speedup"),
                    "speedup_note": wl.get("speedup_note"),
                    "timing_scope": "database_execution",
                    "timing_label": "database execution",
                }
            )

    return {
        "mode": "saved_benchmark_plus_live_counts",
        "reran_expensive_benchmark": False,
        "rerun_note": (
            "Workload timings are loaded from the saved January benchmark artifact. "
            "They are not re-measured on each page load."
        ),
        "product_boundary": (
            "Historical investigation evidence only. "
            "Pressure anomalies are not confirmed leaks."
        ),
        "live_stored": {
            "sensors": n_sensors,
            "readings_total": n_readings,
            "readings_in_presenter_window": n_presenter,
            "readings_15m_rows": n_cagg,
            "coverage_start": (
                ts_range["tmin"].strftime("%Y-%m-%d %H:%M:%S")
                if ts_range and ts_range["tmin"]
                else None
            ),
            "coverage_end": (
                ts_range["tmax"].strftime("%Y-%m-%d %H:%M:%S")
                if ts_range and ts_range["tmax"]
                else None
            ),
            "presenter_window": {
                "start": PRESENTER_START.strftime("%Y-%m-%d %H:%M:%S"),
                "end": PRESENTER_END.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "method_m_evidence": method_m_live,
        },
        "storage": {
            "database_bytes": db_bytes,
            "database_pretty": _pretty_bytes(db_bytes),
            "readings_hypertable_bytes": readings_ht,
            "readings_15m_bytes": cagg_bytes,
            "limit_bytes": limit_bytes,
            "limit_pretty": _pretty_bytes(limit_bytes) if limit_bytes else None,
            "working_ceiling_bytes": working_ceiling,
            "working_ceiling_pretty": (
                _pretty_bytes(working_ceiling) if working_ceiling else None
            ),
            "headroom_note": "Working ceiling = 80% of configured Tiger Console limit (20% headroom).",
        },
        "saved_benchmark": {
            "available": saved is not None,
            "run_date_utc": (saved or {}).get("_artifact", {}).get("run_date_utc"),
            "run_mtime_utc": (saved or {}).get("_artifact", {}).get("run_mtime_utc"),
            "artifact_path": (saved or {}).get("_artifact", {}).get("path"),
            "repeats": (saved or {}).get("_artifact", {}).get("repeats")
            or (saved or {}).get("repeats"),
            "method": (saved or {}).get("method"),
            "dataset_scope": (saved or {}).get("coverage"),
            "compression_enabled_at_benchmark": (saved or {}).get(
                "compression_enabled", False
            ),
            "workloads": workloads,
            "latency_distinction": (
                "Timings are labeled database execution "
                "(EXPLAIN ANALYZE Execution Time). "
                "They are not application or browser loading time."
            ),
            "no_app_wide_speedup_claim": True,
        },
    }
