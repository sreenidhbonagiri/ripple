"""Retrospective benchmark-outcome artifact (evaluation only).

Isolated from Method M warning/timeline serving, detector inputs, saved
investigations, and printed briefs. Does not load official leakage CSVs.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = (
    REPO_ROOT / "artifacts" / "method_m_benchmark_outcome_v1" / "outcome.json"
)


def artifact_path() -> Path:
    return DEFAULT_ARTIFACT


@lru_cache(maxsize=1)
def _load_raw() -> tuple[str, dict[str, Any]]:
    path = artifact_path()
    if not path.is_file():
        raise FileNotFoundError(f"benchmark outcome artifact missing: {path}")
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("benchmark outcome artifact must be a JSON object")
    return hashlib.sha256(raw).hexdigest(), data


def present_benchmark_outcome() -> dict[str, Any]:
    """Return the frozen evaluation view payload (no cursor, no detector state)."""
    sha, data = _load_raw()
    example = data.get("verified_example") or {}
    summary = data.get("diagnostic_summary") or {}
    provenance = data.get("provenance") or {}
    return {
        "artifact_id": data.get("artifact_id"),
        "version": data.get("version"),
        "kind": data.get("kind"),
        "title": data.get("title"),
        "evaluation_type": data.get("evaluation_type"),
        "year_examined_note": data.get("year_examined_note"),
        "localization_note": data.get("localization_note"),
        "isolation": data.get("isolation"),
        "matching_protocol": data.get("matching_protocol"),
        "diagnostic_summary": {
            "abrupt_recall_excluding_development_example_p523": summary.get(
                "abrupt_recall_excluding_development_example_p523"
            ),
            "abrupt_recall_inclusive": summary.get("abrupt_recall_inclusive"),
            "incipient_recall": summary.get("incipient_recall"),
            "unmatched_notifications_2019": summary.get(
                "unmatched_notifications_2019"
            ),
            "validated_localization": summary.get("validated_localization"),
        },
        "verified_example": {
            "id": example.get("id"),
            "label": example.get("label"),
            "pipe_id": example.get("pipe_id"),
            "leak_type": example.get("leak_type"),
            "development_example": example.get("development_example"),
            "official_labeled_onset": example.get("official_labeled_onset"),
            "frozen_notification_time": example.get("frozen_notification_time"),
            "delay_hours": example.get("delay_hours"),
            "delay_five_minute_steps": example.get("delay_five_minute_steps"),
            "delay_note": example.get("delay_note"),
            "matched": example.get("matched"),
            "truth_map_label": example.get("truth_map_label"),
            "contributing_sensor_note": example.get("contributing_sensor_note"),
        },
        "provenance": provenance,
        "artifact_sha256": sha,
        "notes": [
            "Retrospective evaluation — not available to the detector at investigation time.",
            "Opening this view is explicit; ground-truth overlays are removed when returning to replay.",
        ],
    }
