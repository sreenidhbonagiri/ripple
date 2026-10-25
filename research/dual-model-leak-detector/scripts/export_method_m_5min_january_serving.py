#!/usr/bin/env python3
"""Export January five-minute Method M serving artifact (no evaluation labels).

Reads frozen 5-min research outputs (default: sibling worktree
``rippple-method-m-multiscale``) and writes
``artifacts/method_m_experimental_january/`` for the product API.
Does not import raw data or write Tiger derived tables.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
# Prefer sibling research worktree (code + dual/score CSVs).
_RESEARCH_PKG = Path(
    os.environ.get(
        "METHOD_M_5MIN_PKG",
        str(
            ROOT.parent
            / "rippple-method-m-multiscale"
            / "research"
            / "dual-model-leak-detector"
        ),
    )
)
sys.path.insert(0, str(_RESEARCH_PKG))

from dual_model.detection_scores import EPS_SIGMA  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402

RES = _RESEARCH_PKG / "outputs"
OUT2019 = RES / "detection_2019_method_m_5min"
OUT2018_5 = RES / "detection_2018_measured_pump1" / "method_m_5min"
ART = ROOT / "artifacts" / "method_m_experimental_january"

REF_HOURS = 24
REF_GAP_HOURS = 1
REF_MIN_SAMPLES_5MIN = 144
RECOVER_STEPS_5MIN = 12
TAU = 4.517


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    if not (OUT2019 / "pre_inference_hashes.json").exists():
        raise SystemExit(f"Missing 5-min research bundle at {OUT2019}")

    pre = json.loads((OUT2019 / "pre_inference_hashes.json").read_text())
    pre_label = json.loads((OUT2019 / "pre_label_hashes.json").read_text())
    tau = float(pre["tau"])
    if abs(tau - TAU) > 1e-9:
        raise SystemExit(f"expected τ={TAU}, got {tau}")
    raw_max_median = float(pre["raw_max_median"])

    sigma = pd.read_csv(OUT2018_5 / "method_m_5min_sigma.csv", index_col=0)["sigma_m3h"]
    qv18_dev = pd.read_csv(OUT2018_5 / "dual_qv_5min_dev.csv", index_col=0, parse_dates=True)
    qv18_diag = pd.read_csv(OUT2018_5 / "dual_qv_5min_diag.csv", index_col=0, parse_dates=True)
    qv18 = pd.concat([qv18_dev, qv18_diag]).sort_index()
    qv18 = qv18[~qv18.index.duplicated(keep="first")]
    qv19 = pd.read_csv(OUT2019 / "dual_qv_5min_2019.csv", index_col=0, parse_dates=True)
    cols = [c for c in qv19.columns if c in sigma.index]
    qv = pd.concat([qv18[cols], qv19[cols]]).sort_index()
    qv = qv[~qv.index.duplicated(keep="last")]

    score_full = pd.read_csv(OUT2019 / "score_M_5min_2019.csv", index_col=0, parse_dates=True)[
        "score"
    ]
    jan_start = pd.Timestamp("2019-01-01 00:00:00")
    jan_end = pd.Timestamp("2019-01-31 23:55:00")
    jan_idx = score_full.index[(score_full.index >= jan_start) & (score_full.index <= jan_end)]

    sig = sigma.reindex(cols).astype(float).clip(lower=EPS_SIGMA)
    cal = raw_max_median

    hours: list[dict] = []
    for t in jan_idx:
        sc = float(score_full.loc[t])
        end = t - pd.Timedelta(hours=REF_GAP_HOURS)
        start = end - pd.Timedelta(hours=REF_HOURS)
        ref_idx = qv.index[(qv.index >= start) & (qv.index <= end)]
        contrib: list[dict] = []
        argmax = None
        if len(ref_idx) >= REF_MIN_SAMPLES_5MIN:
            row = qv.loc[t, cols].astype(float)
            ref = qv.loc[ref_idx, cols].astype(float)
            n_ref = ref.notna().sum(axis=0)
            ok = row.notna() & (n_ref >= REF_MIN_SAMPLES_5MIN)
            if bool(ok.any()):
                use = ok.index[ok]
                mu = ref.loc[:, use].mean(axis=0)
                delta = row.loc[use] - mu
                z_cal = (delta / sig.loc[use]).abs() / cal
                z_cal = z_cal[np.isfinite(z_cal)]
                if len(z_cal):
                    full_max = float(z_cal.max())
                    if np.isfinite(sc) and abs(full_max - sc) > 1e-5:
                        raise SystemExit(f"score mismatch at {t}: {sc} vs {full_max}")
                    ranked = z_cal.sort_values(ascending=False)
                    mx = float(ranked.iloc[0])
                    keep = ranked[(ranked >= mx * 0.5) | (ranked.index == ranked.index[0])].head(
                        5
                    )
                    argmax = str(ranked.index[0])
                    for sid, zc in keep.items():
                        contrib.append(
                            {
                                "sensor_id": sid,
                                "abs_z_calibrated": float(zc),
                                "delta_m3h": float(delta.loc[sid]),
                                "sigma_scale_m3h": float(sig.loc[sid]),
                                "qv_m3h": float(row.loc[sid]),
                                "ref_mean_m3h": float(mu.loc[sid]),
                            }
                        )
        hours.append(
            {
                "ts": t.strftime("%Y-%m-%d %H:%M:%S"),
                "score": None if not np.isfinite(sc) else sc,
                "argmax_sensor_id": argmax,
                "contributors": contrib,
            }
        )

    notifies = [
        line.strip()
        for line in (OUT2019 / "notifications_2019.txt").read_text().splitlines()
        if line.strip()
    ]
    jan_notifies = [t for t in notifies if jan_start <= pd.Timestamp(t) <= jan_end]

    eps = episodes_from_scores(
        score_full.values.astype(float), tau=tau, recover_steps=RECOVER_STEPS_5MIN
    )
    notify_meta = []
    for ep in eps:
        nts = score_full.index[ep.notify_idx]
        ets = score_full.index[ep.end_idx]
        if jan_start <= nts <= jan_end:
            notify_meta.append(
                {
                    "notify_ts": nts.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_ts": ets.strftime("%Y-%m-%d %H:%M:%S"),
                    "peak_score": float(ep.peak_score),
                }
            )

    hours_bytes = json.dumps(hours, separators=(",", ":")).encode()
    notif_bytes = json.dumps(jan_notifies, separators=(",", ":")).encode()
    # ~12× hourly January rows
    est_derived = int(5059200 * (len(hours) / 744.0))

    protocol_key = next(
        (
            k
            for k in (
                "METHOD_M_5MIN_PROTOCOL.md",
                "METHOD_M_PROTOCOL.md",
            )
            if k in pre.get("file_sha256", {})
        ),
        None,
    )
    protocol_hash = (
        pre["file_sha256"].get(protocol_key)
        if protocol_key
        else pre["file_sha256"].get("METHOD_M_5MIN_FREEZE.md")
    )

    manifest = {
        "method": "M",
        "label": "experimental_historical_anomaly_warning",
        "experimental_disclaimer": "Experimental anomaly warning — not a confirmed leak.",
        "resolution": "five_minute",
        "resolution_note": (
            "Scores and notifications are on a native five-minute grid. "
            "Do not treat notify times as sub-sample precision beyond the 5-minute stamp."
        ),
        "coverage": {
            "start": "2019-01-01 00:00:00",
            "end": "2019-01-31 23:55:00",
            "note": (
                "January 2019 only — matches existing Tiger raw coverage; "
                "no additional raw import."
            ),
        },
        "tau": tau,
        "tau_recover": tau / 2.0,
        "timestep_sec": 300,
        "recover_steps": RECOVER_STEPS_5MIN,
        "ref_min_samples": REF_MIN_SAMPLES_5MIN,
        "raw_max_median": raw_max_median,
        "version_hashes": {
            "calibration_sha256": pre["calibration_sha256"],
            "sensor_scales_sha256": pre["sensor_scales_sha256"],
            "tau_sha256": pre["tau_sha256"],
            "score_M_2019_sha256": pre_label["score_M_5min_2019_sha256"],
            "notifications_2019_sha256": pre_label["notifications_2019_sha256"],
            "detection_scores_py_sha256": pre["file_sha256"]["detection_scores.py"],
            "notifier_py_sha256": pre["file_sha256"]["notifier.py"],
            "METHOD_M_PROTOCOL_sha256": protocol_hash,
            "serving_hours_sha256": hashlib.sha256(hours_bytes).hexdigest(),
            "serving_notifications_sha256": hashlib.sha256(notif_bytes).hexdigest(),
        },
        "evaluation_labels_in_serving": False,
        "tiger_capacity": {
            "checked": True,
            "database_bytes": 100013759,
            "limit_bytes": 786432000,
            "working_ceiling_bytes": 629145600,
            "usable_bytes": 529131841,
            "estimated_derived_table_bytes": est_derived,
            "would_fit": True,
            "decision": "file_backed_artifact_no_tiger_derived_table",
            "rationale": (
                "Capacity allows a derived table at five-minute density, but serving "
                "stays file-backed to avoid hypertable growth and keep eval labels "
                "out of the database."
            ),
        },
        "n_hours": len(hours),
        "n_score_stamps": len(hours),
        "n_notifications_january": len(jan_notifies),
        "matching_verification": {
            "one_to_one_abrupt_2019": True,
            "abrupt_recall": "3/9",
            "abrupt_recall_excluding_p523_dev_example": "2/8",
            "incipient_recall": "0/10",
            "unmatched_notifications_2019": 6,
            "notification_timestamps_match_frozen_file": True,
            "five_minute_resolution_disclosed": True,
            "evaluation_type": "frozen_diagnostic_not_blind_holdout",
            "carryover_note": (
                "Carryover open-leak counts reuse the same 2019 notifications; "
                "they are not independent detections."
            ),
            "vs_hourly": (
                "Same detected abrupt events as hourly Method M; earlier "
                "notifications on shared hits where the five-minute grid allows."
            ),
        },
    }

    (ART / "serving_hours.json").write_text(json.dumps(hours), encoding="utf-8")
    (ART / "serving_notifications.json").write_text(
        json.dumps({"notifications": jan_notifies, "episodes": notify_meta}, indent=2),
        encoding="utf-8",
    )
    (ART / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"Wrote {ART} ({len(hours)} stamps, {len(jan_notifies)} January notifies: "
        f"{jan_notifies})"
    )
    if notify_meta:
        print("episodes:", json.dumps(notify_meta, indent=2))


if __name__ == "__main__":
    main()
