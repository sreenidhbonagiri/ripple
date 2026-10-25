"""Tiger-backed Method M score timeline (preceding 24 hours at the cursor).

Uses frozen ``method_m_scores`` / ``method_m_notifications`` for the selected
run only. Never recomputes the detector and never falls back to files.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings
from app.db import get_connection
from app.method_m_db import _load_run, resolve_run_id
from app.method_m_warning import (
    EXPERIMENTAL_DISCLAIMER,
    RESOLUTION,
    RESOLUTION_NOTE,
    _fmt,
    floor_to_score_step,
)

TIMELINE_HOURS = 24
SCORE_STEP = timedelta(minutes=5)
SCORE_INTERPRETATION = (
    "Higher score means stronger dual-model deviation from the causal reference "
    "— not a leak probability or confirmed leak."
)


def _require_tiger_store() -> None:
    mode = (get_settings().ripple_method_m_store or "file").strip().lower()
    if mode != "tiger":
        raise RuntimeError(
            "Method M timeline requires RIPPLE_METHOD_M_STORE=tiger "
            "(no file-artifact substitution)."
        )


def present_method_m_timeline(cursor: datetime) -> dict[str, Any]:
    """Return Method M scores and notify markers for [cursor−24h, floor(cursor)]."""
    _require_tiger_store()
    c = cursor.replace(tzinfo=None)
    window_end = floor_to_score_step(c)
    window_start = window_end - timedelta(hours=TIMELINE_HOURS)

    with get_connection() as conn:
        with conn.cursor() as cur:
            run_id = resolve_run_id(conn)
            run = _load_run(cur, run_id)
            tau = float(run["tau"])
            tau_recover = float(run["tau_recover"])
            version_hashes = run.get("version_hashes") or {}
            if hasattr(version_hashes, "keys"):
                version_hashes = dict(version_hashes)
            coverage_start = run["coverage_start"].replace(tzinfo=None)
            coverage_end = run["coverage_end"].replace(tzinfo=None)

            cur.execute(
                """
                SELECT ts, score, argmax_sensor_id
                FROM method_m_scores
                WHERE run_id = %s
                  AND ts >= %s
                  AND ts <= %s
                ORDER BY ts ASC
                """,
                (run_id, window_start, window_end),
            )
            score_rows = cur.fetchall()

            # Notification markers: notify stamp in the visible window only.
            # Window end is already <= cursor floor, so no future notifies leak.
            cur.execute(
                """
                SELECT notify_ts
                FROM method_m_notifications
                WHERE run_id = %s
                  AND notify_ts >= %s
                  AND notify_ts <= %s
                ORDER BY notify_ts ASC
                """,
                (run_id, window_start, window_end),
            )
            notify_rows = cur.fetchall()

    points: list[dict[str, Any]] = []
    null_scores = 0
    for row in score_rows:
        ts = row["ts"].replace(tzinfo=None)
        score = row["score"]
        if score is None:
            null_scores += 1
            points.append(
                {
                    "ts": _fmt(ts),
                    "score": None,
                    "argmax_sensor_id": row.get("argmax_sensor_id"),
                }
            )
        else:
            points.append(
                {
                    "ts": _fmt(ts),
                    "score": float(score),
                    "argmax_sensor_id": row.get("argmax_sensor_id"),
                }
            )

    notifications = [
        {"notify_ts": _fmt(r["notify_ts"].replace(tzinfo=None))} for r in notify_rows
    ]

    # Expected stamps on the native 5-minute grid (inclusive).
    expected = 0
    if window_end >= window_start:
        expected = int((window_end - window_start) / SCORE_STEP) + 1

    returned = len(points)
    # Clip expected to method coverage intersection when outside January.
    overlap_start = max(window_start, coverage_start)
    overlap_end = min(window_end, coverage_end)
    expected_in_coverage = 0
    if overlap_end >= overlap_start:
        expected_in_coverage = int((overlap_end - overlap_start) / SCORE_STEP) + 1

    status = "ok"
    notes: list[str] = [RESOLUTION_NOTE, SCORE_INTERPRETATION]
    if c < coverage_start:
        status = "before_coverage"
        notes.append("Replay cursor is before Method M January serving coverage.")
    elif not points:
        status = "empty"
        notes.append("No Method M score stamps in the preceding 24-hour window.")
    elif returned < expected_in_coverage:
        status = "partial"
        notes.append(
            "Some expected five-minute stamps in coverage are missing from storage."
        )

    return {
        "method": "M",
        "experimental": True,
        "store": "tiger",
        "run_id": run_id,
        "source": "method_m_scores",
        "notification_source": "method_m_notifications",
        "label": "Experimental anomaly score",
        "replay_label": "Historical benchmark replay",
        "disclaimer": EXPERIMENTAL_DISCLAIMER,
        "score_interpretation": SCORE_INTERPRETATION,
        "resolution": str(run.get("resolution") or RESOLUTION),
        "resolution_note": str(run.get("resolution_note") or RESOLUTION_NOTE),
        "cursor": _fmt(c),
        "window_start": _fmt(window_start),
        "window_end": _fmt(window_end),
        "timeline_hours": TIMELINE_HOURS,
        "threshold": tau,
        "recover_threshold": tau_recover,
        "version_hashes": version_hashes,
        "coverage": {
            "start": _fmt(coverage_start),
            "end": _fmt(coverage_end),
            "note": run.get("coverage_note"),
        },
        "status": status,
        "points": points,
        "notifications": notifications,
        "missingness": {
            "expected_stamps_in_window": expected,
            "expected_stamps_in_method_coverage": expected_in_coverage,
            "returned_stamps": returned,
            "null_scores": null_scores,
            "coverage_complete": (
                expected_in_coverage > 0 and returned >= expected_in_coverage
            ),
        },
        "provenance": {
            "serving_hours_sha256": run.get("serving_hours_sha256"),
            "serving_notifications_sha256": run.get("serving_notifications_sha256"),
            "run_id": run_id,
            "store": "tiger",
        },
        "notes": notes,
        "predicted_leak_pipes": None,
    }
