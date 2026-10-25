#!/usr/bin/env python3
"""Idempotent import of frozen January Method M serving artifacts into Tiger.

Persists detector outputs exactly (scores, top contributors, notifications).
Does not import evaluation labels or duplicate raw SCADA.

Capacity: refuses if projected size would exceed the 80% working ceiling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db import get_connection, sanitize_db_error  # noqa: E402
from app.method_m_db import DEFAULT_RUN_ID  # noqa: E402
from app.storage_capacity import (  # noqa: E402
    assert_capacity_for_bytes,
    get_storage_snapshot,
)

DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "method_m_experimental_january"
# Manifest estimated ~60.7 MiB derived tables; cushion for indexes/TOAST.
METHOD_M_JANUARY_EST_BYTES = 65_000_000
BATCH = 2000


def _parse_naive(ts: str) -> datetime:
    s = str(ts).replace("T", " ")
    if "." in s:
        s = s.split(".", 1)[0]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _compact_json_sha256(path: Path) -> str:
    obj = json.loads(path.read_text(encoding="utf-8"))
    compact = json.dumps(obj, separators=(",", ":")).encode()
    return hashlib.sha256(compact).hexdigest()


def load_artifacts(artifact_dir: Path) -> tuple[dict[str, Any], list[dict], dict[str, Any]]:
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    hours = json.loads((artifact_dir / "serving_hours.json").read_text(encoding="utf-8"))
    notif = json.loads(
        (artifact_dir / "serving_notifications.json").read_text(encoding="utf-8")
    )
    if manifest.get("evaluation_labels_in_serving") is not False:
        raise RuntimeError("Refusing import: evaluation_labels_in_serving must be false")
    return manifest, hours, notif


def verify_provenance(
    artifact_dir: Path,
    manifest: dict[str, Any],
    notif: dict[str, Any],
) -> tuple[str, str]:
    """Match export hashes: hours = compact serving_hours.json; notif = notify list."""
    vh = manifest.get("version_hashes") or {}
    hours_hash = _compact_json_sha256(artifact_dir / "serving_hours.json")
    # Export hashed the January notify timestamp list, not the full episodes blob.
    notify_list = list(notif.get("notifications") or [])
    notif_hash = hashlib.sha256(
        json.dumps(notify_list, separators=(",", ":")).encode()
    ).hexdigest()
    expected_h = vh.get("serving_hours_sha256")
    expected_n = vh.get("serving_notifications_sha256")
    if expected_h and hours_hash != expected_h:
        raise RuntimeError(
            f"serving_hours sha256 mismatch: file={hours_hash} manifest={expected_h}"
        )
    if expected_n and notif_hash != expected_n:
        raise RuntimeError(
            f"serving_notifications sha256 mismatch: list={notif_hash} "
            f"manifest={expected_n}"
        )
    episodes = list(notif.get("episodes") or [])
    ep_notifies = [ep["notify_ts"] for ep in episodes]
    if ep_notifies != notify_list:
        raise RuntimeError(
            "serving_notifications episodes notify_ts list disagrees with "
            "notifications array"
        )
    return hours_hash, notif_hash


def _existing_run(cur, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, serving_hours_sha256, serving_notifications_sha256,
               n_score_stamps, n_contributor_rows, n_notifications
        FROM method_m_runs WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _count(cur, table: str, run_id: str) -> int:
    cur.execute(
        f"SELECT COUNT(*)::BIGINT AS n FROM {table} WHERE run_id = %s",  # noqa: S608
        (run_id,),
    )
    return int(cur.fetchone()["n"])


def verify_stored(
    cur,
    run_id: str,
    *,
    hours_hash: str,
    notif_hash: str,
    n_scores: int,
    n_contrib: int,
    n_notif: int,
    sample_hours: list[dict[str, Any]],
) -> None:
    cur.execute(
        """
        SELECT serving_hours_sha256, serving_notifications_sha256,
               n_score_stamps, n_contributor_rows, n_notifications
        FROM method_m_runs WHERE run_id = %s
        """,
        (run_id,),
    )
    run = cur.fetchone()
    assert run is not None
    if run["serving_hours_sha256"] != hours_hash:
        raise RuntimeError("stored serving_hours_sha256 mismatch")
    if run["serving_notifications_sha256"] != notif_hash:
        raise RuntimeError("stored serving_notifications_sha256 mismatch")
    if int(run["n_score_stamps"]) != n_scores:
        raise RuntimeError("stored n_score_stamps mismatch")
    if int(run["n_contributor_rows"]) != n_contrib:
        raise RuntimeError("stored n_contributor_rows mismatch")
    if int(run["n_notifications"]) != n_notif:
        raise RuntimeError("stored n_notifications mismatch")

    sc = _count(cur, "method_m_scores", run_id)
    ev = _count(cur, "method_m_sensor_evidence", run_id)
    nt = _count(cur, "method_m_notifications", run_id)
    if sc != n_scores or ev != n_contrib or nt != n_notif:
        raise RuntimeError(
            f"row counts mismatch: scores={sc}/{n_scores} "
            f"evidence={ev}/{n_contrib} notif={nt}/{n_notif}"
        )

    for h in sample_hours:
        ts = _parse_naive(h["ts"])
        cur.execute(
            """
            SELECT score, argmax_sensor_id FROM method_m_scores
            WHERE run_id = %s AND ts = %s
            """,
            (run_id, ts),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"missing score row for {h['ts']}")
        file_score = h.get("score")
        db_score = row["score"]
        if file_score is None:
            if db_score is not None:
                raise RuntimeError(f"score null mismatch at {h['ts']}")
        else:
            if db_score is None or abs(float(db_score) - float(file_score)) > 1e-12:
                raise RuntimeError(f"score value mismatch at {h['ts']}")
        if (row["argmax_sensor_id"] or None) != (h.get("argmax_sensor_id") or None):
            raise RuntimeError(f"argmax mismatch at {h['ts']}")

        contribs = h.get("contributors") or []
        if not contribs:
            continue
        top = contribs[0]
        cur.execute(
            """
            SELECT abs_z_calibrated, delta_m3h FROM method_m_sensor_evidence
            WHERE run_id = %s AND ts = %s AND sensor_id = %s
            """,
            (run_id, ts, top["sensor_id"]),
        )
        er = cur.fetchone()
        if er is None:
            raise RuntimeError(f"missing evidence for {h['ts']} {top['sensor_id']}")
        if abs(float(er["abs_z_calibrated"]) - float(top["abs_z_calibrated"])) > 1e-12:
            raise RuntimeError(f"abs_z mismatch at {h['ts']}")


def import_run(
    artifact_dir: Path,
    run_id: str,
    *,
    dry_run: bool = False,
    force_reimport: bool = False,
) -> dict[str, Any]:
    manifest, hours, notif = load_artifacts(artifact_dir)
    hours_hash, notif_hash = verify_provenance(artifact_dir, manifest, notif)
    episodes = list(notif.get("episodes") or [])
    n_scores = len(hours)
    n_contrib = sum(len(h.get("contributors") or []) for h in hours)
    n_notif = len(episodes)

    sample_idx = [0, n_scores // 2, n_scores - 1] if n_scores else []
    # Prefer known notify stamps when present
    notify_ts_set = {ep["notify_ts"] for ep in episodes}
    for i, h in enumerate(hours):
        if h["ts"] in notify_ts_set and i not in sample_idx:
            sample_idx.append(i)
    sample_hours = [hours[i] for i in sorted(set(sample_idx)) if 0 <= i < n_scores]

    snap = get_storage_snapshot()
    report = {
        "run_id": run_id,
        "artifact_dir": str(artifact_dir),
        "n_score_stamps": n_scores,
        "n_contributor_rows": n_contrib,
        "n_notifications": n_notif,
        "serving_hours_sha256": hours_hash,
        "serving_notifications_sha256": notif_hash,
        "estimated_bytes": METHOD_M_JANUARY_EST_BYTES,
        "database_bytes_before": snap.database_bytes,
        "working_ceiling_bytes": snap.working_ceiling_bytes,
        "usable_bytes": snap.usable_bytes,
        "action": None,
    }

    if dry_run:
        report["action"] = "dry_run"
        projected = snap.database_bytes + METHOD_M_JANUARY_EST_BYTES
        report["would_fit"] = projected <= snap.working_ceiling_bytes
        return report

    with get_connection() as conn:
        with conn.cursor() as cur:
            existing = _existing_run(cur, run_id)
            if existing is not None:
                same = (
                    existing["serving_hours_sha256"] == hours_hash
                    and existing["serving_notifications_sha256"] == notif_hash
                    and int(existing["n_score_stamps"]) == n_scores
                    and int(existing["n_contributor_rows"]) == n_contrib
                    and int(existing["n_notifications"]) == n_notif
                )
                if same and not force_reimport:
                    verify_stored(
                        cur,
                        run_id,
                        hours_hash=hours_hash,
                        notif_hash=notif_hash,
                        n_scores=n_scores,
                        n_contrib=n_contrib,
                        n_notif=n_notif,
                        sample_hours=sample_hours,
                    )
                    report["action"] = "idempotent_skip"
                    report["database_bytes_after"] = get_storage_snapshot().database_bytes
                    return report
                if not force_reimport:
                    raise RuntimeError(
                        f"Run {run_id} exists with different provenance/counts. "
                        "Use --force-reimport to replace (deletes this run first)."
                    )
                cur.execute("DELETE FROM method_m_runs WHERE run_id = %s", (run_id,))
                conn.commit()

        assert_capacity_for_bytes(METHOD_M_JANUARY_EST_BYTES)

        coverage = manifest["coverage"]
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO method_m_runs (
                    run_id, method, label, experimental, disclaimer,
                    resolution, resolution_note,
                    coverage_start, coverage_end, coverage_note,
                    tau, tau_recover, timestep_sec, recover_steps,
                    version_hashes, serving_hours_sha256, serving_notifications_sha256,
                    n_score_stamps, n_contributor_rows, n_notifications, artifact_dir
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    run_id,
                    manifest.get("method", "M"),
                    manifest.get("label", "experimental_historical_anomaly_warning"),
                    True,
                    manifest.get(
                        "experimental_disclaimer",
                        "Experimental anomaly warning — not a confirmed leak.",
                    ),
                    manifest.get("resolution", "five_minute"),
                    manifest.get("resolution_note", ""),
                    _parse_naive(coverage["start"]),
                    _parse_naive(coverage["end"]),
                    coverage.get("note"),
                    float(manifest["tau"]),
                    float(manifest.get("tau_recover", float(manifest["tau"]) / 2.0)),
                    int(manifest.get("timestep_sec", 300)),
                    int(manifest.get("recover_steps", 12)),
                    Jsonb(manifest.get("version_hashes") or {}),
                    hours_hash,
                    notif_hash,
                    n_scores,
                    n_contrib,
                    n_notif,
                    str(artifact_dir.relative_to(REPO_ROOT))
                    if artifact_dir.is_relative_to(REPO_ROOT)
                    else str(artifact_dir),
                ),
            )

            score_rows: list[tuple] = []
            evidence_rows: list[tuple] = []
            for h in hours:
                ts = _parse_naive(h["ts"])
                score = h.get("score")
                score_rows.append(
                    (ts, run_id, None if score is None else float(score), h.get("argmax_sensor_id"))
                )
                for c in h.get("contributors") or []:
                    evidence_rows.append(
                        (
                            ts,
                            run_id,
                            c["sensor_id"],
                            float(c["abs_z_calibrated"]),
                            float(c["delta_m3h"]),
                            float(c["sigma_scale_m3h"]),
                            float(c["qv_m3h"]),
                            float(c["ref_mean_m3h"]),
                        )
                    )

            for i in range(0, len(score_rows), BATCH):
                cur.executemany(
                    """
                    INSERT INTO method_m_scores (ts, run_id, score, argmax_sensor_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    score_rows[i : i + BATCH],
                )
            for i in range(0, len(evidence_rows), BATCH):
                cur.executemany(
                    """
                    INSERT INTO method_m_sensor_evidence (
                        ts, run_id, sensor_id, abs_z_calibrated, delta_m3h,
                        sigma_scale_m3h, qv_m3h, ref_mean_m3h
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    evidence_rows[i : i + BATCH],
                )
            for ep in episodes:
                cur.execute(
                    """
                    INSERT INTO method_m_notifications (
                        run_id, notify_ts, end_ts, peak_score
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        _parse_naive(ep["notify_ts"]),
                        _parse_naive(ep["end_ts"]),
                        float(ep["peak_score"]),
                    ),
                )

            verify_stored(
                cur,
                run_id,
                hours_hash=hours_hash,
                notif_hash=notif_hash,
                n_scores=n_scores,
                n_contrib=n_contrib,
                n_notif=n_notif,
                sample_hours=sample_hours,
            )
        conn.commit()

    after = get_storage_snapshot()
    report["action"] = "imported"
    report["database_bytes_after"] = after.database_bytes
    report["bytes_delta"] = after.database_bytes - snap.database_bytes
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Directory with manifest + serving_*.json",
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force-reimport",
        action="store_true",
        help="Delete existing run_id then re-import (idempotent skip otherwise)",
    )
    args = parser.parse_args()
    try:
        report = import_run(
            args.artifact_dir,
            args.run_id,
            dry_run=args.dry_run,
            force_reimport=args.force_reimport,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {sanitize_db_error(str(exc))}")
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
