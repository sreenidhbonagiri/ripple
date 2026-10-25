"""Benchmark-outcome evaluation artifact — isolation from Method M serving."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.benchmark_outcome import present_benchmark_outcome  # noqa: E402
from app.method_m_warning import present_method_m_warning  # noqa: E402

ARTIFACT = REPO_ROOT / "artifacts" / "method_m_benchmark_outcome_v1" / "outcome.json"


def test_artifact_exists_and_matches_frozen_jan24_row():
    assert ARTIFACT.is_file()
    out = present_benchmark_outcome()
    assert out["artifact_id"] == "method_m_benchmark_outcome_v1"
    assert out["version"] == 1
    ex = out["verified_example"]
    assert ex["pipe_id"] == "p827"
    assert ex["official_labeled_onset"] == "2019-01-24 18:30:00"
    assert ex["frozen_notification_time"] == "2019-01-24 18:30:00"
    assert ex["delay_hours"] == 0.0
    assert ex["delay_five_minute_steps"] == 0
    assert ex["matched"] is True
    assert "not predicted" in ex["truth_map_label"].lower()
    summary = out["diagnostic_summary"]
    assert summary["abrupt_recall_excluding_development_example_p523"] == "2/8"
    assert summary["abrupt_recall_inclusive"] == "3/9"
    assert summary["incipient_recall"] == "0/10"
    assert summary["unmatched_notifications_2019"] == 6
    assert summary["validated_localization"] is False
    assert out["evaluation_type"] == "frozen_diagnostic_not_blind_holdout"
    assert out["provenance"]["frozen_notifications"]["sha256"].startswith("7283a096")


def test_warning_api_excludes_evaluation_labels():
    res = present_method_m_warning(datetime(2019, 1, 24, 18, 30, 0))
    blob = str(res).lower()
    assert "p827" not in blob
    assert "abrupt" not in blob
    assert "incipient" not in blob
    assert "official_labeled_onset" not in blob
    assert res["predicted_leak_pipes"] is None


def test_serving_artifact_still_excludes_per_event_labels():
    from app.method_m_warning import load_artifact

    art = load_artifact()
    assert art.manifest.get("evaluation_labels_in_serving") is False
    hours_blob = str(art.hours_by_ts)
    assert "p827" not in hours_blob
    assert "official_labeled_onset" not in hours_blob
    notify_blob = str(art.episodes)
    assert "p827" not in notify_blob
    assert "onset" not in notify_blob.lower()


def test_benchmark_outcome_route_shape_has_isolation_flags():
    out = present_benchmark_outcome()
    iso = out["isolation"]
    assert iso["not_in_warning_api"] is True
    assert iso["not_in_timeline_api"] is True
    assert iso["not_in_printed_briefs"] is True
    assert iso["opens_only_on_explicit_user_action"] is True
