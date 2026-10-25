"""Cursor safety, missingness, version provenance for Experimental Method M."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.method_m_warning import (  # noqa: E402
    EXPERIMENTAL_DISCLAIMER,
    clear_artifact_cache,
    load_artifact,
    present_method_m_warning,
)


@pytest.fixture(autouse=True)
def _reload_artifact():
    clear_artifact_cache()
    yield
    clear_artifact_cache()


def test_artifact_loads_january_only():
    art = load_artifact()
    assert art.manifest["coverage"]["start"].startswith("2019-01-01")
    assert art.manifest["coverage"]["end"].startswith("2019-01-31")
    assert art.manifest["evaluation_labels_in_serving"] is False
    assert art.manifest["resolution"] == "five_minute"
    assert art.manifest["tau"] == pytest.approx(4.517)
    assert len(art.hour_index) == 8928
    assert len(art.episodes) == 2
    blob = str(art.hours_by_ts)
    for label in ("p523", "p827", "abrupt", "incipient", "carryover"):
        assert label not in blob
    mv = art.manifest["matching_verification"]
    assert mv["abrupt_recall_excluding_p523_dev_example"] == "2/8"
    assert mv["abrupt_recall"] == "3/9"
    assert mv["incipient_recall"] == "0/10"
    assert mv["unmatched_notifications_2019"] == 6
    assert mv["evaluation_type"] == "frozen_diagnostic_not_blind_holdout"


def test_version_provenance_present():
    art = load_artifact()
    hashes = art.manifest["version_hashes"]
    assert hashes["calibration_sha256"].startswith("5fab3acb")
    assert "tau_sha256" in hashes
    assert "serving_hours_sha256" in hashes
    res = present_method_m_warning(datetime(2019, 1, 12, 15, 0, 0))
    assert res["version_hashes"]["calibration_sha256"] == hashes["calibration_sha256"]
    assert res["disclaimer"] == EXPERIMENTAL_DISCLAIMER
    assert res["resolution"] == "five_minute"
    assert "five-minute" in res["resolution_note"].lower()


def test_before_coverage_missing():
    res = present_method_m_warning(datetime(2018, 12, 31, 23, 0, 0))
    assert res["status"] == "before_coverage"
    assert res["warning_active"] is False
    assert res["score"] is None
    assert res["investigation_usable_without_warning"] is True
    assert res["predicted_leak_pipes"] is None


def test_presenter_cursor_no_warning_still_usable():
    """Jan 12 afternoon — investigation usable; no Method M notify yet."""
    res = present_method_m_warning(datetime(2019, 1, 12, 15, 0, 0))
    assert res["warning_active"] is False
    assert res["status"] == "below_threshold"
    assert res["score"] is not None
    assert res["score"] < res["threshold"]
    assert res["score_hour"] == "2019-01-12 15:00:00"
    assert res["investigation_usable_without_warning"] is True
    assert res["predicted_leak_pipes"] is None
    assert res["episode_end_ts"] is None
    assert res["episode_peak_score"] is None


def test_cursor_floors_to_five_minute_stamp():
    res = present_method_m_warning(datetime(2019, 1, 12, 15, 37, 0))
    assert res["score_hour"] == "2019-01-12 15:35:00"
    assert res["data_age_hours"] == pytest.approx(2 / 60.0, abs=0.01)


def test_never_serves_future_stamp_evidence():
    cursor = datetime(2019, 1, 15, 22, 55, 0)
    res = present_method_m_warning(cursor)
    assert res["score_hour"] == "2019-01-15 22:55:00"
    assert res["warning_active"] is False
    assert res["notification"] is None


def test_warning_active_withholds_future_peak_and_end():
    # Notify at 2019-01-15 23:00; end at 2019-01-16 19:45
    res = present_method_m_warning(datetime(2019, 1, 16, 0, 0, 0))
    assert res["warning_active"] is True
    assert res["status"] == "warning"
    assert res["disclaimer"] == EXPERIMENTAL_DISCLAIMER
    assert res["notification"]["notify_ts"] == "2019-01-15 23:00:00"
    assert res["episode_end_ts"] is None
    assert res["episode_peak_score"] is None
    assert res.get("peak_score_observed_to_cursor") is not None
    assert any("withhold" in n.lower() or "withheld" in n.lower() for n in res["notes"])
    assert res["contributors"]
    assert res["threshold"] == pytest.approx(4.517)
    assert res["predicted_leak_pipes"] is None


def test_after_episode_end_exposes_peak():
    res = present_method_m_warning(datetime(2019, 1, 16, 19, 45, 0))
    assert res["episode_end_ts"] == "2019-01-16 19:45:00"
    assert res["episode_peak_score"] == pytest.approx(9.861590406632889)
    assert res["warning_active"] is False


def test_second_january_notify_earlier_than_hourly():
    """Five-minute notify for p827 is 18:30 (hourly was 19:00)."""
    res = present_method_m_warning(datetime(2019, 1, 24, 18, 35, 0))
    assert res["warning_active"] is True
    assert res["notification"]["notify_ts"] == "2019-01-24 18:30:00"
    assert res["score_hour"] == "2019-01-24 18:35:00"
    assert res["episode_end_ts"] is None
    assert res["episode_peak_score"] is None
    # Before 18:30 must not see the notify
    earlier = present_method_m_warning(datetime(2019, 1, 24, 18, 25, 0))
    assert earlier["warning_active"] is False
    assert earlier["notification"] is None


def test_tiger_capacity_decision_documented():
    art = load_artifact()
    cap = art.manifest["tiger_capacity"]
    assert cap["checked"] is True
    assert cap["would_fit"] is True
    assert cap["decision"] == "file_backed_artifact_no_tiger_derived_table"


def test_warning_demo_frozen_january_notify_cursor_safe():
    """Actual frozen January notification used as warning-demo bookmark."""
    notify = datetime(2019, 1, 15, 23, 0, 0)
    res = present_method_m_warning(notify)
    assert res["warning_active"] is True
    assert res["notification"]["notify_ts"] == "2019-01-15 23:00:00"
    assert res["score_hour"] == "2019-01-15 23:00:00"
    assert res["episode_end_ts"] is None
    assert res["episode_peak_score"] is None
    assert res["predicted_leak_pipes"] is None
    assert "not a confirmed leak" in res["disclaimer"].lower()
    for c in res["contributors"]:
        assert "pipe" not in c["sensor_id"]
    earlier = present_method_m_warning(datetime(2019, 1, 15, 22, 55, 0))
    assert earlier["warning_active"] is False
    assert earlier["notification"] is None
    assert earlier["score_hour"] == "2019-01-15 22:55:00"


def test_hashes_match_frozen_research_bundle():
    art = load_artifact()
    root = Path(__file__).resolve().parents[2]
    pre = json.loads(
        (
            root
            / "research/dual-model-leak-detector/outputs/detection_2019_method_m_5min/pre_inference_hashes.json"
        ).read_text(encoding="utf-8")
    )
    pre_label = json.loads(
        (
            root
            / "research/dual-model-leak-detector/outputs/detection_2019_method_m_5min/pre_label_hashes.json"
        ).read_text(encoding="utf-8")
    )
    vh = art.manifest["version_hashes"]
    assert vh["calibration_sha256"] == pre["calibration_sha256"]
    assert vh["sensor_scales_sha256"] == pre["sensor_scales_sha256"]
    assert vh["tau_sha256"] == pre["tau_sha256"]
    assert vh["score_M_2019_sha256"] == pre_label["score_M_5min_2019_sha256"]
    assert vh["notifications_2019_sha256"] == pre_label["notifications_2019_sha256"]


def test_serving_hours_hash_matches_manifest():
    import hashlib

    art_dir = REPO_ROOT / "artifacts" / "method_m_experimental_january"
    hours = (art_dir / "serving_hours.json").read_bytes()
    # Recompute compact hash as export did
    hours_obj = json.loads(hours)
    compact = json.dumps(hours_obj, separators=(",", ":")).encode()
    art = load_artifact()
    assert (
        hashlib.sha256(compact).hexdigest()
        == art.manifest["version_hashes"]["serving_hours_sha256"]
    )


def test_notices_do_not_claim_leak_or_localization():
    res = present_method_m_warning(datetime(2019, 1, 15, 23, 0, 0))
    blob = " ".join(
        [
            res["disclaimer"],
            " ".join(res["notes"]),
            str(res.get("predicted_leak_pipes")),
        ]
    ).lower()
    assert "not a confirmed leak" in res["disclaimer"].lower()
    assert res["predicted_leak_pipes"] is None
    assert "p523" not in str(res)
    assert "abrupt" not in str(res).lower()
