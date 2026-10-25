"""Tiger-backed Experimental Method M warning (same API contract as file store).

Serves one frozen method run only — never mixes runs. Evaluation labels are
not stored. Peak/end withholding matches the file-backed presenter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from app.config import get_settings
from app.db import get_connection
from app.method_m_warning import (
    EXPERIMENTAL_DISCLAIMER,
    RESOLUTION,
    RESOLUTION_NOTE,
    _fmt,
    _parse_naive,
    floor_to_score_step,
)

DEFAULT_RUN_ID = "method_m_5min_jan2019"


def resolve_run_id(conn=None) -> str:
    """Return the configured run, or the sole imported run.

    Raises if zero or multiple runs exist without an explicit config override.
    """
    settings = get_settings()
    configured = (settings.ripple_method_m_run_id or "").strip()
    if configured:
        return configured

    def _pick(cur) -> str:
        cur.execute(
            "SELECT run_id FROM method_m_runs ORDER BY run_id"
        )
        rows = cur.fetchall()
        if not rows:
            raise RuntimeError(
                "No Method M runs in Tiger. Import January artifacts or set "
                "RIPPLE_METHOD_M_STORE=file."
            )
        if len(rows) > 1:
            ids = ", ".join(r["run_id"] for r in rows)
            raise RuntimeError(
                "Multiple Method M runs present; set RIPPLE_METHOD_M_RUN_ID "
                f"explicitly to avoid mixing runs. Found: {ids}"
            )
        return str(rows[0]["run_id"])

    if conn is not None:
        with conn.cursor(row_factory=dict_row) as cur:
            return _pick(cur)
    with get_connection() as c:
        with c.cursor() as cur:
            return _pick(cur)


def _load_run(cur, run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT run_id, method, label, experimental, disclaimer, resolution,
               resolution_note, coverage_start, coverage_end, coverage_note,
               tau, tau_recover, timestep_sec, recover_steps, version_hashes,
               serving_hours_sha256, serving_notifications_sha256,
               n_score_stamps, n_contributor_rows, n_notifications
        FROM method_m_runs
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Method M run not found: {run_id}")
    return dict(row)


def _latest_score_at_or_before(cur, run_id: str, cursor: datetime) -> dict[str, Any] | None:
    target = floor_to_score_step(cursor)
    cur.execute(
        """
        SELECT ts, score, argmax_sensor_id
        FROM method_m_scores
        WHERE run_id = %s AND ts <= %s
        ORDER BY ts DESC
        LIMIT 1
        """,
        (run_id, target),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _fetch_contributors(cur, run_id: str, ts: datetime) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT sensor_id, abs_z_calibrated, delta_m3h, sigma_scale_m3h,
               qv_m3h, ref_mean_m3h
        FROM method_m_sensor_evidence
        WHERE run_id = %s AND ts = %s
        ORDER BY abs_z_calibrated DESC, sensor_id ASC
        """,
        (run_id, ts),
    )
    return [
        {
            "sensor_id": r["sensor_id"],
            "abs_z_calibrated": float(r["abs_z_calibrated"]),
            "delta_m3h": float(r["delta_m3h"]),
            "sigma_scale_m3h": float(r["sigma_scale_m3h"]),
            "qv_m3h": float(r["qv_m3h"]),
            "ref_mean_m3h": float(r["ref_mean_m3h"]),
        }
        for r in cur.fetchall()
    ]


def fetch_contributors_with_sensor_meta(
    run_id: str, ts: datetime | str
) -> list[dict[str, Any]]:
    """SQL workflow: cursor-bounded contributors joined to sensor metadata.

    Existing raw ``readings`` queries supply pressure context separately.
    """
    stamp = _parse_naive(ts) if not isinstance(ts, datetime) else ts.replace(tzinfo=None)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.sensor_id,
                       e.abs_z_calibrated,
                       e.delta_m3h,
                       e.sigma_scale_m3h,
                       e.qv_m3h,
                       e.ref_mean_m3h,
                       s.measurement_type,
                       s.unit,
                       s.network_element_id,
                       s.network_element_kind
                FROM method_m_sensor_evidence e
                LEFT JOIN sensors s ON s.id = e.sensor_id
                WHERE e.run_id = %s AND e.ts = %s
                ORDER BY e.abs_z_calibrated DESC, e.sensor_id ASC
                """,
                (run_id, stamp),
            )
            return [dict(r) for r in cur.fetchall()]


def _active_episode(
    cur, run_id: str, cursor: datetime
) -> dict[str, Any] | None:
    c = cursor.replace(tzinfo=None)
    score_floor = floor_to_score_step(c)
    cur.execute(
        """
        SELECT notify_ts, end_ts, peak_score
        FROM method_m_notifications
        WHERE run_id = %s
          AND notify_ts <= %s
          AND end_ts > %s
        ORDER BY notify_ts DESC
        LIMIT 1
        """,
        (run_id, c, score_floor),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _peak_to_cursor(
    cur, run_id: str, notify_ts: datetime, score_hour: datetime
) -> float | None:
    cur.execute(
        """
        SELECT MAX(score) AS peak
        FROM method_m_scores
        WHERE run_id = %s
          AND ts >= %s
          AND ts <= %s
          AND score IS NOT NULL
        """,
        (run_id, notify_ts, score_hour),
    )
    row = cur.fetchone()
    if row is None or row["peak"] is None:
        return None
    return float(row["peak"])


def _recovered_at_stamp(
    cur, run_id: str, cursor: datetime, score_hour: datetime
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT notify_ts, end_ts, peak_score
        FROM method_m_notifications
        WHERE run_id = %s
          AND notify_ts <= %s
          AND end_ts = %s
        ORDER BY notify_ts DESC
        LIMIT 1
        """,
        (run_id, cursor.replace(tzinfo=None), score_hour),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def present_method_m_warning_db(cursor: datetime) -> dict[str, Any]:
    """Serve Method M state from Tiger for stamps at or before ``cursor`` only."""
    c = cursor.replace(tzinfo=None)

    with get_connection() as conn:
        with conn.cursor() as cur:
            run_id = resolve_run_id(conn)
            run = _load_run(cur, run_id)
            coverage_start = run["coverage_start"].replace(tzinfo=None)
            coverage_end = run["coverage_end"].replace(tzinfo=None)
            tau = float(run["tau"])
            resolution = str(run.get("resolution") or RESOLUTION)
            resolution_note = str(run.get("resolution_note") or RESOLUTION_NOTE)
            version_hashes = run.get("version_hashes") or {}
            if hasattr(version_hashes, "keys"):
                version_hashes = dict(version_hashes)

            base: dict[str, Any] = {
                "method": "M",
                "experimental": True,
                "disclaimer": EXPERIMENTAL_DISCLAIMER,
                "resolution": resolution,
                "resolution_note": resolution_note,
                "cursor": _fmt(c),
                "score_hour": None,
                "threshold": tau,
                "recover_threshold": float(run["tau_recover"]),
                "version_hashes": version_hashes,
                "coverage": {
                    "start": _fmt(coverage_start),
                    "end": _fmt(coverage_end),
                    "note": run.get("coverage_note"),
                },
                "status": "missing",
                "warning_active": False,
                "score": None,
                "contributors": [],
                "argmax_sensor_id": None,
                "data_age_hours": None,
                "notification": None,
                "investigation_usable_without_warning": True,
                "predicted_leak_pipes": None,
                "episode_peak_score": None,
                "episode_end_ts": None,
                "notes": [],
                "store": "tiger",
                "run_id": run_id,
            }

            if c < coverage_start:
                base["status"] = "before_coverage"
                base["notes"].append(
                    "Replay cursor is before Method M January serving coverage."
                )
                return base

            score_row = _latest_score_at_or_before(cur, run_id, c)
            if score_row is None:
                base["status"] = "missing"
                base["notes"].append("No Method M score stamp at or before cursor.")
                return base

            score_hour = score_row["ts"].replace(tzinfo=None)
            hour_key = _fmt(score_hour)
            score = score_row["score"]
            age_hours = (c - score_hour).total_seconds() / 3600.0

            base["score_hour"] = hour_key
            base["score"] = None if score is None else float(score)
            base["argmax_sensor_id"] = score_row.get("argmax_sensor_id")
            base["contributors"] = _fetch_contributors(cur, run_id, score_hour)
            base["data_age_hours"] = round(age_hours, 3)
            base["notes"].append(resolution_note)

            if score is None:
                base["status"] = "score_missing"
                base["notes"].append(
                    "Score is missing for this stamp (NaN / insufficient causal reference)."
                )
                return base

            if floor_to_score_step(c) > coverage_end:
                base["notes"].append(
                    "Cursor is past January Method M serving coverage; "
                    "showing last available stamp at or before cursor."
                )

            active = _active_episode(cur, run_id, c)
            if active is not None:
                notify_ts = active["notify_ts"].replace(tzinfo=None)
                end_ts = active["end_ts"].replace(tzinfo=None)
                notify_key = _fmt(notify_ts)
                end_key = _fmt(end_ts)

                cur.execute(
                    """
                    SELECT score FROM method_m_scores
                    WHERE run_id = %s AND ts = %s
                    """,
                    (run_id, notify_ts),
                )
                notify_score_row = cur.fetchone()
                score_at_notify = (
                    None
                    if notify_score_row is None or notify_score_row["score"] is None
                    else float(notify_score_row["score"])
                )

                base["warning_active"] = True
                base["status"] = "warning"
                base["notification"] = {
                    "notify_ts": notify_key,
                    "score_at_notify": score_at_notify,
                }
                if end_ts <= score_hour:
                    base["episode_end_ts"] = end_key
                    base["episode_peak_score"] = float(active["peak_score"])
                else:
                    base["episode_end_ts"] = None
                    base["episode_peak_score"] = None
                    base["peak_score_observed_to_cursor"] = _peak_to_cursor(
                        cur, run_id, notify_ts, score_hour
                    )
                    base["notes"].append(
                        "Episode end and final peak are withheld until the replay cursor "
                        "reaches them."
                    )
            else:
                if float(score) >= tau:
                    base["status"] = "elevated_no_notify"
                    base["notes"].append(
                        "Score at or above threshold without an active notification "
                        "state at this cursor."
                    )
                else:
                    base["status"] = "below_threshold"
                    base["notes"].append(
                        "No experimental anomaly warning at this cursor. "
                        "Investigation remains usable."
                    )

                recovered = _recovered_at_stamp(cur, run_id, c, score_hour)
                if recovered is not None:
                    base["episode_end_ts"] = _fmt(recovered["end_ts"])
                    base["episode_peak_score"] = float(recovered["peak_score"])
                    base["notification"] = {
                        "notify_ts": _fmt(recovered["notify_ts"]),
                        "recovered_at_cursor_hour": True,
                    }

            return base
