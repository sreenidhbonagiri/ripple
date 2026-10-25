"""Cursor-safe Experimental Method M historical anomaly warning (file-backed).

Serving data is January 2019 only, matching existing Tiger raw coverage.
Evaluation labels are never loaded into the serving payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT

DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "method_m_experimental_january"

EXPERIMENTAL_DISCLAIMER = "Experimental anomaly warning — not a confirmed leak."
RESOLUTION = "hourly"
RESOLUTION_NOTE = (
    "Scores and notifications are on an hourly grid. "
    "Sub-hour precision must not be implied."
)


@dataclass(frozen=True)
class MethodMArtifact:
    manifest: dict[str, Any]
    hours_by_ts: dict[str, dict[str, Any]]
    hour_index: list[str]  # sorted ascending naive "YYYY-MM-DD HH:MM:SS"
    episodes: list[dict[str, Any]]


def artifact_dir() -> Path:
    return DEFAULT_ARTIFACT_DIR


def _parse_naive(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    s = str(ts).replace("T", " ")
    if "." in s:
        s = s.split(".", 1)[0]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def floor_to_hour(cursor: datetime) -> datetime:
    c = cursor.replace(tzinfo=None)
    return c.replace(minute=0, second=0, microsecond=0)


@lru_cache(maxsize=1)
def load_artifact() -> MethodMArtifact:
    root = artifact_dir()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    hours = json.loads((root / "serving_hours.json").read_text(encoding="utf-8"))
    notif = json.loads((root / "serving_notifications.json").read_text(encoding="utf-8"))
    hours_by_ts = {h["ts"]: h for h in hours}
    hour_index = sorted(hours_by_ts.keys())
    return MethodMArtifact(
        manifest=manifest,
        hours_by_ts=hours_by_ts,
        hour_index=hour_index,
        episodes=list(notif.get("episodes") or []),
    )


def clear_artifact_cache() -> None:
    load_artifact.cache_clear()


def _latest_hour_at_or_before(cursor: datetime, hour_index: list[str]) -> str | None:
    target = _fmt(floor_to_hour(cursor))
    # binary search last <= target
    lo, hi = 0, len(hour_index)
    while lo < hi:
        mid = (lo + hi) // 2
        if hour_index[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    return hour_index[lo - 1]


def _active_episode_at(
    cursor: datetime, episodes: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Episode whose notify is ≤ cursor and that has not recovered before cursor.

    Recovery end is only known once the cursor reaches end_ts. Until then the
    episode remains active if notify ≤ cursor (we never invent a future end).
    """
    c = cursor.replace(tzinfo=None)
    active: dict[str, Any] | None = None
    for ep in episodes:
        notify = _parse_naive(ep["notify_ts"])
        end = _parse_naive(ep["end_ts"])
        if notify > c:
            continue
        # Still open at cursor if recovery hour is strictly after cursor hour
        if end > floor_to_hour(c):
            # Prefer the latest notify still open
            if active is None or notify > _parse_naive(active["notify_ts"]):
                active = ep
        # else recovered at/before cursor — not active
    return active


def present_method_m_warning(cursor: datetime) -> dict[str, Any]:
    """Serve Method M state available at or before ``cursor`` only."""
    art = load_artifact()
    man = art.manifest
    c = cursor.replace(tzinfo=None)
    coverage_start = _parse_naive(man["coverage"]["start"])
    coverage_end = _parse_naive(man["coverage"]["end"])
    tau = float(man["tau"])

    base: dict[str, Any] = {
        "method": "M",
        "experimental": True,
        "disclaimer": EXPERIMENTAL_DISCLAIMER,
        "resolution": RESOLUTION,
        "resolution_note": RESOLUTION_NOTE,
        "cursor": _fmt(c),
        "score_hour": None,
        "threshold": tau,
        "recover_threshold": float(man.get("tau_recover", tau / 2.0)),
        "version_hashes": man.get("version_hashes") or {},
        "coverage": man.get("coverage"),
        "status": "missing",
        "warning_active": False,
        "score": None,
        "contributors": [],
        "argmax_sensor_id": None,
        "data_age_hours": None,
        "notification": None,
        "investigation_usable_without_warning": True,
        "predicted_leak_pipes": None,  # never populated
        "episode_peak_score": None,
        "episode_end_ts": None,
        "notes": [],
    }

    if c < coverage_start:
        base["status"] = "before_coverage"
        base["notes"].append(
            "Replay cursor is before Method M January serving coverage."
        )
        return base

    hour_key = _latest_hour_at_or_before(c, art.hour_index)
    if hour_key is None:
        base["status"] = "missing"
        base["notes"].append("No Method M score hour at or before cursor.")
        return base

    hour = art.hours_by_ts[hour_key]
    score_hour = _parse_naive(hour_key)
    score = hour.get("score")
    age_hours = (c - score_hour).total_seconds() / 3600.0

    base["score_hour"] = hour_key
    base["score"] = score
    base["argmax_sensor_id"] = hour.get("argmax_sensor_id")
    base["contributors"] = list(hour.get("contributors") or [])
    base["data_age_hours"] = round(age_hours, 3)
    base["notes"].append(RESOLUTION_NOTE)

    if score is None:
        base["status"] = "score_missing"
        base["notes"].append(
            "Score is missing for this hour (NaN / insufficient causal reference)."
        )
        return base

    if c > coverage_end + timedelta(hours=1) - timedelta(seconds=1):
        # Cursor past January serving package — still show last available hour
        # but mark out_of_serving_coverage (Tiger may still have raw Jan data only).
        if floor_to_hour(c) > coverage_end:
            base["notes"].append(
                "Cursor is past January Method M serving coverage; "
                "showing last available hour at or before cursor."
            )

    active = _active_episode_at(c, art.episodes)
    if active is not None:
        notify_ts = active["notify_ts"]
        end_ts = active["end_ts"]
        end_dt = _parse_naive(end_ts)
        notify_dt = _parse_naive(notify_ts)

        # Causal peak: max score from notify hour through current score hour
        peak_to_cursor = None
        for ts in art.hour_index:
            tdt = _parse_naive(ts)
            if tdt < notify_dt:
                continue
            if tdt > score_hour:
                break
            sc = art.hours_by_ts[ts].get("score")
            if sc is None:
                continue
            peak_to_cursor = sc if peak_to_cursor is None else max(peak_to_cursor, sc)

        base["warning_active"] = True
        base["status"] = "warning"
        base["notification"] = {
            "notify_ts": notify_ts,
            "score_at_notify": (art.hours_by_ts.get(notify_ts) or {}).get("score"),
        }
        # Never expose future episode end or full-episode peak before cursor reaches them
        if end_dt <= score_hour:
            base["episode_end_ts"] = end_ts
            base["episode_peak_score"] = float(active["peak_score"])
        else:
            base["episode_end_ts"] = None
            base["episode_peak_score"] = None
            base["peak_score_observed_to_cursor"] = peak_to_cursor
            base["notes"].append(
                "Episode end and final peak are withheld until the replay cursor "
                "reaches them."
            )
    else:
        if float(score) >= tau:
            # Score above τ but notifier not active (edge / recovery boundary)
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

        # If the cursor sits exactly on a completed episode end hour, expose
        # end/peak (both ≤ cursor). Do not describe future peaks/ends.
        for ep in art.episodes:
            end = _parse_naive(ep["end_ts"])
            notify = _parse_naive(ep["notify_ts"])
            if notify <= c and end == score_hour:
                base["episode_end_ts"] = ep["end_ts"]
                base["episode_peak_score"] = float(ep["peak_score"])
                base["notification"] = {
                    "notify_ts": ep["notify_ts"],
                    "recovered_at_cursor_hour": True,
                }
                break

    return base
