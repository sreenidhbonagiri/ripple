#!/usr/bin/env python3
"""Frozen five-minute Method M on 2019 — diagnostic (not a blind holdout).

Order: hash frozen bundle → build 2019 dual → score/notify with 2018 history →
hash scores/notifies → load labels → evaluate and compare to hourly Method M.
No retuning. τ=4.517 fixed from 2018 5-min DEV freeze.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_protocol import (  # noqa: E402
    CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
    CREDIT_HOURS,
    RECOVER_STEPS_5MIN,
    REF_MIN_SAMPLES_5MIN,
    REQUIRED_FROZEN_SHA256,
    TIMESTEP_SEC_5MIN,
    WARMUP_HOURS,
)
from dual_model.detection_scores import score_M_maxabs_local_change  # noqa: E402
from dual_model.dual_series import build_dual_qv_5min, verify_frozen_hash  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402

OUT = ROOT / "outputs" / "detection_2019_method_m_5min"
M5 = ROOT / "outputs" / "detection_2018_measured_pump1" / "method_m_5min"
M2018 = ROOT / "outputs" / "detection_2018_measured_pump1"
HOURLY_2019 = ROOT / "outputs" / "detection_2019_method_m"
FROZEN_CAL = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
TAU = 4.517
HOURLY_TAU = 4.347
EVAL_START = pd.Timestamp("2019-01-01 00:00:00")
EVAL_END = pd.Timestamp("2019-12-31 23:55:00")
N_NULLS = 200
DEV_EXAMPLE_PIPE = "p523"  # excluded from primary abrupt metrics


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


@dataclass(frozen=True)
class LeakEvent:
    pipe: str
    start: pd.Timestamp
    end: pd.Timestamp
    leak_type: str
    peak: pd.Timestamp
    diameter_m: float


def parse_leak_catalog() -> list[LeakEvent]:
    cfg_path = ROOT.parents[1] / "data" / "raw" / "dataset_configuration.yaml"
    raw = cfg_path.read_text().splitlines()
    events = []
    for line in raw:
        line = line.strip()
        if not line.startswith("- p"):
            continue
        if "incipient" not in line and "abrupt" not in line:
            continue
        body = line.lstrip("- ").strip()
        parts = [p.strip() for p in body.split(",")]
        if len(parts) < 6:
            continue
        pipe, start, end, diam, ltype, peak = parts[:6]
        events.append(
            LeakEvent(
                pipe=pipe,
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
                leak_type=ltype,
                peak=pd.Timestamp(peak),
                diameter_m=float(diam),
            )
        )
    if not events:
        raise RuntimeError(f"No leak events parsed from {cfg_path}")
    return events


def _summarize_fill_meta(meta: dict) -> dict:
    n_cleared = int(meta.get("n_qv_cleared_stale_total", 0) or 0)
    n_ts = int(meta.get("n_timestamps", 0) or 0)
    p_stats, pump_stats = [], []
    for ch in meta.get("chunks", []):
        if "pressure_fill_stats" in ch:
            p_stats.append(ch["pressure_fill_stats"])
        if "pump_fill_stats" in ch:
            pump_stats.append(ch["pump_fill_stats"])

    def _agg(stats: list[dict]) -> dict:
        if not stats:
            return {}
        n_obs = sum(s.get("n_observed", 0) for s in stats)
        n_fill = sum(s.get("n_filled", 0) for s in stats)
        n_un = sum(s.get("n_unavailable", 0) for s in stats)
        n_cells = sum(s.get("n_cells", 0) for s in stats)
        return {
            "n_cells": n_cells,
            "n_observed": n_obs,
            "n_filled": n_fill,
            "n_unavailable": n_un,
            "frac_observed": n_obs / max(n_cells, 1),
            "frac_filled": n_fill / max(n_cells, 1),
            "frac_unavailable": n_un / max(n_cells, 1),
        }

    return {
        "n_timestamps": n_ts,
        "n_solver_failures": int(meta.get("n_solver_failures", 0)),
        "n_chunks": int(meta.get("n_chunks", 0)),
        "n_qv_cleared_stale_total": n_cleared,
        "frac_qv_cleared_stale": n_cleared / max(n_ts, 1),
        "median_index_step": meta.get("median_index_step"),
        "pressure": _agg(p_stats),
        "pump": _agg(pump_stats),
    }


def record_pre_inference_hashes() -> tuple[dict, dict]:
    m5 = json.loads((M5 / "method_m_5min_results.json").read_text())
    scale = m5["scale"]
    scale_blob = json.dumps(
        {"sigma_m3h": scale["sigma_m3h"], "raw_max_median": scale["raw_max_median"]},
        sort_keys=True,
    )
    tau_blob = f"{TAU:.12g}"
    paths = {
        "frozen_calibration.json": FROZEN_CAL,
        "METHOD_M_5MIN_PROTOCOL.md": M5 / "METHOD_M_5MIN_PROTOCOL.md",
        "METHOD_M_5MIN_FREEZE.md": M5 / "METHOD_M_5MIN_FREEZE.md",
        "FROZEN_SELECTION.json": M5 / "FROZEN_SELECTION.json",
        "method_m_5min_results.json": M5 / "method_m_5min_results.json",
        "PUMP1_MEASURED_BOUNDARY.md": ROOT / "PUMP1_MEASURED_BOUNDARY.md",
        "pump_boundary.py": ROOT / "dual_model" / "pump_boundary.py",
        "causal_fill.py": ROOT / "dual_model" / "causal_fill.py",
        "notifier.py": ROOT / "dual_model" / "notifier.py",
        "detection_scores.py": ROOT / "dual_model" / "detection_scores.py",
        "ltown_hydraulics.py": ROOT / "dual_model" / "ltown_hydraulics.py",
        "dual_series.py": ROOT / "dual_model" / "dual_series.py",
        "run_method_m_5min_2019_frozen.py": ROOT / "scripts" / "run_method_m_5min_2019_frozen.py",
        "hourly_method_m_2019_results.json": HOURLY_2019 / "method_m_2019_results.json",
    }
    file_hashes = {k: sha256_file(p) for k, p in paths.items() if p.exists()}
    cal_hash = file_hashes["frozen_calibration.json"]
    if cal_hash != REQUIRED_FROZEN_SHA256:
        raise RuntimeError(f"calibration hash mismatch: {cal_hash}")
    if abs(float(m5["selection"]["tau"]) - TAU) > 1e-9:
        raise RuntimeError(f"frozen τ mismatch: results={m5['selection']['tau']} expected={TAU}")
    payload = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "acknowledgement": (
            "2019 has already been examined during previous research; "
            "this is a frozen diagnostic evaluation of five-minute Method M, "
            "not a blind holdout."
        ),
        "variant": "method_m_5min",
        "file_sha256": file_hashes,
        "calibration_sha256": cal_hash,
        "sensor_scales_sha256": sha256_text(scale_blob),
        "sensor_scales_n": len(scale["sigma_m3h"]),
        "raw_max_median": scale["raw_max_median"],
        "tau": TAU,
        "tau_sha256": sha256_text(tau_blob),
        "timestep_sec": TIMESTEP_SEC_5MIN,
        "ref_min_samples": REF_MIN_SAMPLES_5MIN,
        "recover_steps": RECOVER_STEPS_5MIN,
        "causal_fill_max_age_steps": CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
        "causality": {
            "calibration_uses_future_2019": False,
            "scales_use_future_2019": False,
            "tau_selected_on_2019": False,
            "score_ref_looks_ahead": False,
            "pump_bc_looks_ahead": False,
            "pressure_fill_looks_ahead": False,
            "notes": (
                "Scales from 2018 5-min SCALE; τ from 2018 5-min DEV; dual/score "
                "use causal fills and measurements at/before analysis time."
            ),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pre_inference_hashes.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload, scale


def event_rows_for(
    events: list[LeakEvent],
    *,
    notify_times: list[pd.Timestamp],
    score: pd.Series,
    active: np.ndarray,
    index: pd.DatetimeIndex,
    eval_start: pd.Timestamp,
    eval_end: pd.Timestamp,
    warm_end: pd.Timestamp,
    kind: str,
) -> list[dict]:
    rows = []
    for ev in events:
        onset = ev.start
        if onset < eval_start or onset > eval_end:
            continue
        credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
        in_warmup = onset < warm_end
        before = index[index < onset]
        blocked = False
        if len(before):
            i_before = index.get_loc(before[-1])
            if isinstance(i_before, (slice, np.ndarray)):
                i_before = int(np.asarray(i_before).ravel()[0])
            blocked = bool(active[int(i_before)])
        cands = [t for t in notify_times if onset <= t <= credit_end]
        hit = len(cands) > 0
        delay = float((min(cands) - onset).total_seconds() / 3600.0) if hit else None
        credit = score.loc[(score.index >= onset) & (score.index <= credit_end)]
        credit = credit[np.isfinite(credit)]
        rows.append(
            {
                "pipe": ev.pipe,
                "leak_type": kind,
                "onset": str(onset),
                "peak": str(ev.peak),
                "end": str(ev.end),
                "excluded_warmup": bool(in_warmup),
                "is_dev_example": ev.pipe == DEV_EXAMPLE_PIPE,
                "hit": hit and not in_warmup,
                "hit_including_warmup": hit,
                "delay_hours": delay if not in_warmup else None,
                "pre_onset_blocked": blocked,
                "credit_max_score": float(credit.max()) if len(credit) else None,
                "n_credit_notifies": len(cands),
                "score_finite_in_credit": int(len(credit)),
            }
        )
    return rows


def summarize(rows: list[dict], *, exclude_pipes: set[str] | None = None) -> dict:
    if exclude_pipes:
        rows = [r for r in rows if r["pipe"] not in exclude_pipes]
    elig = [r for r in rows if not r["excluded_warmup"]]
    warm = [r for r in rows if r["excluded_warmup"]]
    n_hit = sum(1 for r in elig if r["hit"])
    delays = [r["delay_hours"] for r in elig if r["delay_hours"] is not None]
    return {
        "n_listed": len(rows),
        "n_eligible": len(elig),
        "n_warmup_excluded": len(warm),
        "n_hit": n_hit,
        "recall": float(n_hit / len(elig)) if elig else float("nan"),
        "mean_delay_hours": float(np.mean(delays)) if delays else None,
        "delays_hours": delays,
        "n_pre_onset_blocked_among_eligible": sum(1 for r in elig if r["pre_onset_blocked"]),
        "n_events_with_multiple_credit_notifies": sum(
            1 for r in elig if int(r.get("n_credit_notifies", 0)) > 1
        ),
        "events": rows,
    }


def timing_null_detail(
    score: pd.Series,
    events: list[dict],
    *,
    notify_times: list[pd.Timestamp],
    eval_start: pd.Timestamp,
    eval_end: pd.Timestamp,
    warm_end: pd.Timestamp,
    rng: np.random.Generator,
    n_nulls: int = N_NULLS,
) -> dict:
    eligible = [
        e for e in events if not e["excluded_warmup"] and pd.Timestamp(e["onset"]) >= warm_end
    ]
    if not eligible:
        return {"n_nulls": 0, "n_events": 0}
    true_onsets = [pd.Timestamp(e["onset"]) for e in eligible]
    index = score.index[(score.index >= eval_start) & (score.index <= eval_end)]
    eligible_hours = index[(index >= warm_end) & (index <= eval_end)]
    hod = [t.hour for t in true_onsets]
    pools = {h: eligible_hours[eligible_hours.hour == h] for h in range(24)}

    def recall_for(onsets: list[pd.Timestamp]) -> float:
        hits = 0
        for onset in onsets:
            ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
            if any(onset <= t <= ce for t in notify_times):
                hits += 1
        return hits / len(onsets)

    true_recall = recall_for(true_onsets)
    null_recalls = []
    n_draws = 0
    for _ in range(n_nulls):
        sampled = []
        for h in hod:
            pool = pools.get(int(h), eligible_hours)
            if len(pool) == 0:
                pool = eligible_hours
            sampled.append(pd.Timestamp(rng.choice(pool)))
            n_draws += 1
        null_recalls.append(recall_for(sampled))
    arr = np.asarray(null_recalls, dtype=float)
    cnt = Counter(np.round(arr, 6))
    n_exceed = int((arr >= true_recall).sum())  # nulls as extreme as / exceeding true
    return {
        "n_null_replicates": n_nulls,
        "n_events_E": len(true_onsets),
        "n_onset_timestamp_draws_total": n_draws,
        "n_fixed_notifies_in_eval": len(
            [t for t in notify_times if eval_start <= t <= eval_end]
        ),
        "true_recall": true_recall,
        "null_recall_mean": float(arr.mean()),
        "null_recall_std": float(arr.std(ddof=0)),
        "true_percentile_vs_null": float((arr <= true_recall).mean()),
        "n_nulls_recall_le_true": int((arr <= true_recall).sum()),
        "n_nulls_recall_ge_true": n_exceed,
        "n_timing_null_exceedances": n_exceed,
        "null_recall_value_counts": {str(k): int(v) for k, v in sorted(cnt.items())},
        "assignment_rules": (
            "For each of N replicates, sample |E| onsets from eligible eval stamps "
            "matching each true event's hour-of-day; hit if any frozen notify lies in "
            "[onset, onset+6h]. Percentile = fraction of null recalls ≤ true recall. "
            "Exceedance count = nulls with recall ≥ true."
        ),
    }


def load_2018_qv() -> pd.DataFrame:
    dev = pd.read_csv(M5 / "dual_qv_5min_dev.csv", index_col=0, parse_dates=True)
    diag = pd.read_csv(M5 / "dual_qv_5min_diag.csv", index_col=0, parse_dates=True)
    qv = pd.concat([dev, diag]).sort_index()
    return qv[~qv.index.duplicated(keep="first")]


def compare_to_hourly(
    abrupt_rows: list[dict],
    abrupt_primary: dict,
    abrupt_inclusive: dict,
    incip_sum: dict,
    burden: dict,
    nulls_primary: dict,
    nulls_inclusive: dict,
) -> dict:
    hourly = json.loads((HOURLY_2019 / "method_m_2019_results.json").read_text())
    h_abrupt = {e["pipe"]: e for e in hourly["abrupt"]["events"]}
    h_incip = {e["pipe"]: e for e in hourly["incipient"]["events"]}

    event_cmp = []
    both_delays = []
    for e in abrupt_rows:
        if e["excluded_warmup"]:
            continue
        h = h_abrupt.get(e["pipe"], {})
        row = {
            "pipe": e["pipe"],
            "is_dev_example": e["is_dev_example"],
            "hourly_hit": h.get("hit"),
            "hourly_delay_hours": h.get("delay_hours"),
            "five_min_hit": e["hit"],
            "five_min_delay_hours": e["delay_hours"],
            "hit_gain": bool(e["hit"]) and not bool(h.get("hit")),
            "hit_regression": bool(h.get("hit")) and not bool(e["hit"]),
        }
        if e["delay_hours"] is not None and h.get("delay_hours") is not None:
            row["delay_delta_hours"] = float(e["delay_hours"]) - float(h["delay_hours"])
            both_delays.append(row["delay_delta_hours"])
        else:
            row["delay_delta_hours"] = None
        event_cmp.append(row)

    def _incip_cmp() -> list[dict]:
        out = []
        for e in incip_sum["events"]:
            if e["excluded_warmup"]:
                continue
            h = h_incip.get(e["pipe"], {})
            out.append(
                {
                    "pipe": e["pipe"],
                    "hourly_hit": h.get("hit"),
                    "five_min_hit": e["hit"],
                    "hit_gain": bool(e["hit"]) and not bool(h.get("hit")),
                    "hit_regression": bool(h.get("hit")) and not bool(e["hit"]),
                    "hourly_delay_hours": h.get("delay_hours"),
                    "five_min_delay_hours": e["delay_hours"],
                }
            )
        return out

    h_null = hourly["timing_nulls_abrupt"]
    return {
        "hourly_tau": HOURLY_TAU,
        "five_min_tau": TAU,
        "abrupt_inclusive": {
            "hourly_recall": hourly["abrupt"]["recall"],
            "five_min_recall": abrupt_inclusive["recall"],
            "hourly_n_hit": hourly["abrupt"]["n_hit"],
            "five_min_n_hit": abrupt_inclusive["n_hit"],
            "hourly_mean_delay": hourly["abrupt"]["mean_delay_hours"],
            "five_min_mean_delay": abrupt_inclusive["mean_delay_hours"],
        },
        "abrupt_primary_excl_p523": {
            "hourly_recall": _hourly_recall_excl(h_abrupt, DEV_EXAMPLE_PIPE),
            "five_min_recall": abrupt_primary["recall"],
            "five_min_n_hit": abrupt_primary["n_hit"],
            "five_min_n_eligible": abrupt_primary["n_eligible"],
            "five_min_mean_delay": abrupt_primary["mean_delay_hours"],
        },
        "incipient": {
            "hourly_recall": hourly["incipient"]["recall"],
            "five_min_recall": incip_sum["recall"],
            "hourly_n_hit": hourly["incipient"]["n_hit"],
            "five_min_n_hit": incip_sum["n_hit"],
            "events": _incip_cmp(),
        },
        "burden": {
            "hourly_n_notifications": hourly["burden"]["n_notifications_2019"],
            "five_min_n_notifications": burden["n_notifications_2019"],
            "hourly_unmatched_per_week": hourly["burden"]["unmatched_per_week"],
            "five_min_unmatched_per_week": burden["unmatched_per_week"],
            "hourly_occupancy": hourly["burden"]["occupancy"],
            "five_min_occupancy": burden["occupancy"],
            "five_min_n_duplicate_notify_timestamps": burden["n_duplicate_notify_timestamps"],
            "five_min_n_events_multi_credit_notifies": burden[
                "n_events_with_multiple_credit_notifies"
            ],
        },
        "delays_on_both_detected_abrupt": {
            "n_both_hit": len(both_delays),
            "mean_delay_delta_hours_five_minus_hourly": (
                float(np.mean(both_delays)) if both_delays else None
            ),
            "per_event": [r for r in event_cmp if r["delay_delta_hours"] is not None],
        },
        "abrupt_event_comparison": event_cmp,
        "timing_nulls": {
            "hourly_inclusive": {
                "true_recall": h_null["true_recall"],
                "n_nulls_recall_ge_true": h_null["n_nulls_recall_ge_true"],
                "true_percentile_vs_null": h_null["true_percentile_vs_null"],
            },
            "five_min_inclusive": {
                "true_recall": nulls_inclusive["true_recall"],
                "n_timing_null_exceedances": nulls_inclusive["n_timing_null_exceedances"],
                "true_percentile_vs_null": nulls_inclusive["true_percentile_vs_null"],
            },
            "five_min_primary_excl_p523": {
                "true_recall": nulls_primary["true_recall"],
                "n_timing_null_exceedances": nulls_primary["n_timing_null_exceedances"],
                "true_percentile_vs_null": nulls_primary["true_percentile_vs_null"],
            },
        },
    }


def _hourly_recall_excl(h_abrupt: dict, pipe: str) -> float:
    elig = [e for p, e in h_abrupt.items() if p != pipe and not e.get("excluded_warmup")]
    if not elig:
        return float("nan")
    return float(sum(1 for e in elig if e.get("hit")) / len(elig))


def main() -> int:
    t_all = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = OUT / "_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    assert (OUT / "PRE_INFERENCE_FROZEN_BUNDLE.md").exists(), (
        "Register PRE_INFERENCE_FROZEN_BUNDLE.md before running"
    )

    print("=== Phase 0: pre-inference hashes (no 2019 labels) ===", flush=True)
    digest = verify_frozen_hash(FROZEN_CAL)
    assert digest == REQUIRED_FROZEN_SHA256
    pre, scale = record_pre_inference_hashes()
    sigma = pd.Series(scale["sigma_m3h"], dtype=float)
    cal = float(scale["raw_max_median"])
    print(
        f"calibration={pre['calibration_sha256'][:16]}… τ={TAU} "
        f"scales_n={pre['sensor_scales_n']} recover={RECOVER_STEPS_5MIN}",
        flush=True,
    )

    dual_path = OUT / "dual_qv_5min_2019.csv"
    meta_path = OUT / "dual_meta_2019.json"
    if dual_path.exists() and meta_path.exists():
        print("Loading cached 2019 5-min dual …", flush=True)
        qv19 = pd.read_csv(dual_path, index_col=0, parse_dates=True)
        meta19 = json.loads(meta_path.read_text())
    else:
        print("=== Phase 1: 2019 measured-PUMP_1 dual (5-min, frozen cal) ===", flush=True)
        t0 = time.perf_counter()
        qv19, _flows, _levels, meta19 = build_dual_qv_5min(
            "2019-01-01 00:00:00",
            "2019-12-31 23:55:00",
            frozen_path=FROZEN_CAL,
            scratch=scratch,
            chunk_days=3,
            pump_boundary="measured_pump1",
            scada_year=2019,
            causal_fill_max_age_steps=CAUSAL_FILL_MAX_AGE_STEPS_5MIN,
        )
        meta19["runtime_sec_build"] = float(time.perf_counter() - t0)
        qv19.to_csv(dual_path)
        meta_store = {k: v for k, v in meta19.items()}
        meta_path.write_text(json.dumps(meta_store, indent=2, default=str) + "\n")
        print(
            f"q_v2019 shape={qv19.shape} failures={meta19['n_solver_failures']}/"
            f"{meta19['n_chunks']} runtime={meta19['runtime_sec_build']:.1f}s",
            flush=True,
        )

    fill_summary = _summarize_fill_meta(meta19)
    print(f"fill summary: {json.dumps(fill_summary, default=str)}", flush=True)

    print("=== Phase 2: concat 2018 history + score (frozen σ) ===", flush=True)
    qv18 = load_2018_qv()
    cols = [c for c in sigma.index if c in qv18.columns and c in qv19.columns]
    qv18, qv19c = qv18[cols], qv19[cols]
    qv_all = pd.concat([qv18, qv19c]).sort_index()
    qv_all = qv_all[~qv_all.index.duplicated(keep="last")]
    t_score = time.perf_counter()
    score_all = score_M_maxabs_local_change(
        qv_all,
        sigma_m3h=sigma.reindex(cols),
        raw_max_median=cal,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    score_runtime = float(time.perf_counter() - t_score)
    score_2019 = score_all.loc[(score_all.index >= EVAL_START) & (score_all.index <= EVAL_END)]
    score_2019.to_csv(OUT / "score_M_5min_2019.csv", header=["score"])

    print("=== Phase 3: notifications (continuous state, recover=12) ===", flush=True)
    eps = episodes_from_scores(
        score_all.to_numpy(), tau=TAU, recover_steps=RECOVER_STEPS_5MIN
    )
    index_all = score_all.index
    notify_all = [
        index_all[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(index_all)
    ]
    active = np.zeros(len(index_all), dtype=bool)
    for ep in eps:
        if ep.notify_idx < 0:
            continue
        active[ep.notify_idx : ep.end_idx + 1] = True

    notify_2019 = [t for t in notify_all if EVAL_START <= t <= EVAL_END]
    finite_2019 = score_2019[np.isfinite(score_2019)]
    first_avail = str(finite_2019.index[0]) if len(finite_2019) else None
    n_nan_2019 = int((~np.isfinite(score_2019)).sum())
    notify_counts = Counter(notify_2019)
    n_dup_ts = sum(1 for _t, c in notify_counts.items() if c > 1)

    score_bytes = score_2019.to_csv(header=["score"]).encode("utf-8")
    notify_blob = "\n".join(str(t) for t in notify_2019) + "\n"
    pre_label = {
        "hashed_at_utc": datetime.now(timezone.utc).isoformat(),
        "score_M_5min_2019_sha256": sha256_bytes(score_bytes),
        "n_score_stamps": int(len(score_2019)),
        "n_finite_scores": int(np.isfinite(score_2019).sum()),
        "n_nan_scores": n_nan_2019,
        "first_notification_available_score_time": first_avail,
        "notifications_2019_sha256": sha256_text(notify_blob),
        "n_notifications_2019": len(notify_2019),
        "n_duplicate_notify_timestamps": n_dup_ts,
        "n_episodes_total_concat": len(eps),
        "solver_failures_2019": meta19["n_solver_failures"],
        "n_chunks_2019": meta19["n_chunks"],
        "runtime_sec_score": score_runtime,
        "runtime_sec_dual": meta19.get("runtime_sec_build"),
        "fill_summary": fill_summary,
        "missing_data_handling": {
            "score_NaN": "no notify; reset recovery (notifier.py)",
            "stale_required_boundary": "q_v cleared → score NaN (causal_fill max_age=2)",
            "dual_nonconverged_chunk": "NaN q_v rows; propagates to score NaN",
        },
        "state_carry": {
            "notifier_reset_at_leak_onsets": False,
            "notifier_reset_at_month_boundaries": False,
            "score_history_includes_2018_for_ref_and_state": True,
            "recover_steps": RECOVER_STEPS_5MIN,
        },
    }
    (OUT / "pre_label_hashes.json").write_text(json.dumps(pre_label, indent=2) + "\n")
    (OUT / "notifications_2019.txt").write_text(notify_blob)
    print(
        f"pre-label hashes written; n_notif={len(notify_2019)} "
        f"score_sha={pre_label['score_M_5min_2019_sha256'][:16]}…",
        flush=True,
    )

    print("=== Phase 4: load labels and evaluate (diagnostic) ===", flush=True)
    catalog = parse_leak_catalog()
    abrupt_2019 = [
        e for e in catalog if e.leak_type == "abrupt" and EVAL_START <= e.start <= EVAL_END
    ]
    incipient_2019 = [
        e for e in catalog if e.leak_type == "incipient" and EVAL_START <= e.start <= EVAL_END
    ]
    carryover = [e for e in catalog if e.start < EVAL_START and e.end >= EVAL_START]
    warm_end = EVAL_START + pd.Timedelta(hours=WARMUP_HOURS)

    abrupt_rows = event_rows_for(
        abrupt_2019,
        notify_times=notify_all,
        score=score_all,
        active=active,
        index=index_all,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        kind="abrupt",
    )
    incip_rows = event_rows_for(
        incipient_2019,
        notify_times=notify_all,
        score=score_all,
        active=active,
        index=index_all,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        kind="incipient",
    )

    abrupt_inclusive = summarize(abrupt_rows)
    abrupt_primary = summarize(abrupt_rows, exclude_pipes={DEV_EXAMPLE_PIPE})
    incip_sum = summarize(incip_rows)

    matched_notifies: set[pd.Timestamp] = set()
    for r in abrupt_rows + incip_rows:
        if r["excluded_warmup"]:
            continue
        onset = pd.Timestamp(r["onset"])
        ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
        cands = [t for t in notify_2019 if onset <= t <= ce]
        if cands:
            matched_notifies.add(min(cands))
    unmatched = [t for t in notify_2019 if t not in matched_notifies]
    weeks = max((EVAL_END - EVAL_START).total_seconds() / (7 * 24 * 3600), 1e-9)
    mask_2019 = (index_all >= EVAL_START) & (index_all <= EVAL_END)
    occ = float(active[mask_2019].mean()) if mask_2019.any() else float("nan")

    burden = {
        "n_notifications_2019": len(notify_2019),
        "n_unmatched": len(unmatched),
        "unmatched_per_week": float(len(unmatched) / weeks),
        "occupancy": occ,
        "n_duplicate_notify_timestamps": n_dup_ts,
        "n_events_with_multiple_credit_notifies": (
            abrupt_inclusive["n_events_with_multiple_credit_notifies"]
            + incip_sum["n_events_with_multiple_credit_notifies"]
        ),
        "matching_note": (
            "Notify matched if it falls in any eligible abrupt OR incipient "
            "6h credit window; else unmatched."
        ),
    }

    carry_rows = []
    for e in carryover:
        open_end = min(e.end, EVAL_END)
        n_in = sum(1 for t in notify_2019 if EVAL_START <= t <= open_end)
        carry_rows.append(
            {
                "pipe": e.pipe,
                "leak_type": e.leak_type,
                "start": str(e.start),
                "end": str(e.end),
                "n_2019_notifies_while_open": n_in,
            }
        )

    nulls_inclusive = timing_null_detail(
        score_2019,
        abrupt_rows,
        notify_times=notify_2019,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        rng=np.random.default_rng(2019),
        n_nulls=N_NULLS,
    )
    nulls_primary = timing_null_detail(
        score_2019,
        [r for r in abrupt_rows if r["pipe"] != DEV_EXAMPLE_PIPE],
        notify_times=notify_2019,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        rng=np.random.default_rng(2019),
        n_nulls=N_NULLS,
    )

    comparison = compare_to_hourly(
        abrupt_rows,
        abrupt_primary,
        abrupt_inclusive,
        incip_sum,
        burden,
        nulls_primary,
        nulls_inclusive,
    )

    results = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "frozen_diagnostic_not_blind_holdout",
        "acknowledgement": pre["acknowledgement"],
        "variant": "method_m_5min",
        "pre_inference": {
            "calibration_sha256": pre["calibration_sha256"],
            "sensor_scales_sha256": pre["sensor_scales_sha256"],
            "tau": TAU,
            "tau_sha256": pre["tau_sha256"],
            "file_sha256": pre["file_sha256"],
        },
        "pre_label": pre_label,
        "dual_2019_meta": {
            "n_chunks": meta19["n_chunks"],
            "n_solver_failures": meta19["n_solver_failures"],
            "pump_boundary": meta19.get("pump_boundary"),
            "timestep_sec": TIMESTEP_SEC_5MIN,
            "runtime_sec_build": meta19.get("runtime_sec_build"),
            "fill_summary": fill_summary,
            "failed_chunks": [
                c for c in meta19.get("chunks", []) if not c.get("converged", True)
            ],
        },
        "abrupt_primary_excl_p523": abrupt_primary,
        "abrupt_inclusive": abrupt_inclusive,
        "incipient": incip_sum,
        "carryover_leaks_from_before_2019": carry_rows,
        "burden": burden,
        "timing_nulls_abrupt_primary_excl_p523": nulls_primary,
        "timing_nulls_abrupt_inclusive": nulls_inclusive,
        "comparison_vs_hourly_method_m": comparison,
        "runtime_sec_total": float(time.perf_counter() - t_all),
        "dev_example_excluded_from_primary": DEV_EXAMPLE_PIPE,
    }
    (OUT / "method_m_5min_2019_results.json").write_text(
        json.dumps(results, indent=2, default=str) + "\n"
    )
    _write_md(results, pre, pre_label, meta19, fill_summary)
    _write_manifest(results, pre, pre_label)
    print("Wrote", OUT / "METHOD_M_5MIN_2019_RESULTS.md", flush=True)
    print(
        json.dumps(
            {
                "abrupt_primary_recall": abrupt_primary["recall"],
                "abrupt_inclusive_recall": abrupt_inclusive["recall"],
                "incipient_recall": incip_sum["recall"],
                "unmatched_per_week": burden["unmatched_per_week"],
                "occupancy": occ,
                "solver_failures": meta19["n_solver_failures"],
                "runtime_sec": results["runtime_sec_total"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


def _write_manifest(results: dict, pre: dict, pre_label: dict) -> None:
    manifest = {
        "artifact": "method_m_5min_2019_diagnostic",
        "generated_at_utc": results["generated_at_utc"],
        "acknowledgement": results["acknowledgement"],
        "frozen_tau": TAU,
        "calibration_sha256": pre["calibration_sha256"],
        "pre_inference_hashes_sha256": sha256_file(OUT / "pre_inference_hashes.json"),
        "pre_label_hashes_sha256": sha256_file(OUT / "pre_label_hashes.json"),
        "results_json_sha256": sha256_file(OUT / "method_m_5min_2019_results.json"),
        "score_M_5min_2019_sha256": pre_label["score_M_5min_2019_sha256"],
        "notifications_2019_sha256": pre_label["notifications_2019_sha256"],
        "notifications_txt_sha256": sha256_file(OUT / "notifications_2019.txt"),
        "dual_qv_5min_2019_sha256": (
            sha256_file(OUT / "dual_qv_5min_2019.csv")
            if (OUT / "dual_qv_5min_2019.csv").exists()
            else None
        ),
        "dual_meta_2019_sha256": (
            sha256_file(OUT / "dual_meta_2019.json")
            if (OUT / "dual_meta_2019.json").exists()
            else None
        ),
        "reproducibility": {
            "script": "scripts/run_method_m_5min_2019_frozen.py",
            "script_sha256": pre["file_sha256"].get("run_method_m_5min_2019_frozen.py"),
            "command": (
                "PYTHONPATH=. python scripts/run_method_m_5min_2019_frozen.py"
            ),
            "notes": (
                "Dual CSV may be cached; delete dual_qv_5min_2019.csv to rebuild. "
                "Scores/notifies are hashed before labels."
            ),
        },
    }
    (OUT / "REPRODUCIBILITY_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


def _write_md(results, pre, pre_label, meta19, fill_summary) -> None:
    ap = results["abrupt_primary_excl_p523"]
    ai = results["abrupt_inclusive"]
    inc = results["incipient"]
    cmp_ = results["comparison_vs_hourly_method_m"]
    tn_p = results["timing_nulls_abrupt_primary_excl_p523"]
    tn_i = results["timing_nulls_abrupt_inclusive"]
    lines = [
        "# Frozen five-minute Method M on 2019 — diagnostic evaluation",
        "",
        f"**Not a blind holdout.** {pre['acknowledgement']}",
        "",
        f"Generated: `{results['generated_at_utc']}`  ",
        f"τ=`{TAU}` (frozen 5-min). Calibration `{pre['calibration_sha256'][:16]}…`.  ",
        f"Pre-label score hash `{pre_label['score_M_5min_2019_sha256'][:16]}…`; "
        f"notify hash `{pre_label['notifications_2019_sha256'][:16]}…`.",
        "",
        "See `PRE_INFERENCE_FROZEN_BUNDLE.md`, `pre_inference_hashes.json`, "
        "`pre_label_hashes.json`, `REPRODUCIBILITY_MANIFEST.json`.",
        "",
        "## Dual / freshness / availability",
        "",
        f"- Solver failures: **{meta19['n_solver_failures']}** / {meta19['n_chunks']} chunks",
        f"- 2019 score stamps: {pre_label['n_score_stamps']} "
        f"(finite {pre_label['n_finite_scores']}, NaN {pre_label['n_nan_scores']})",
        f"- First finite score in 2019: `{pre_label['first_notification_available_score_time']}`",
        f"- Notifier: continuous 2018→2019; recover_steps=`{RECOVER_STEPS_5MIN}`; "
        "**no** reset at onsets/months",
        "",
        "```json",
        json.dumps(fill_summary, indent=2, default=str),
        "```",
        "",
        f"## Abrupt six-hour recall — **primary** (excl. {DEV_EXAMPLE_PIPE})",
        "",
        f"| n eligible | recall | mean delay h | pre-onset blocked | multi-credit notifies |",
        f"|----------:|-------:|-------------:|------------------:|----------------------:|",
        f"| {ap['n_eligible']} | {ap['recall']} | {ap['mean_delay_hours']} | "
        f"{ap['n_pre_onset_blocked_among_eligible']} | "
        f"{ap['n_events_with_multiple_credit_notifies']} |",
        "",
        f"## Abrupt six-hour recall — **inclusive** (includes {DEV_EXAMPLE_PIPE})",
        "",
        f"| n eligible | recall | mean delay h | pre-onset blocked |",
        f"|----------:|-------:|-------------:|------------------:|",
        f"| {ai['n_eligible']} | {ai['recall']} | {ai['mean_delay_hours']} | "
        f"{ai['n_pre_onset_blocked_among_eligible']} |",
        "",
        "| Pipe | Onset | Hit | Delay h | Pre-onset blocked | Credit max | Dev-ex |",
        "|------|-------|:---:|--------:|:-----------------:|-----------:|:------:|",
    ]
    for r in ai["events"]:
        lines.append(
            f"| {r['pipe']} | {r['onset']} | {r['hit']} | {r['delay_hours']} | "
            f"{r['pre_onset_blocked']} | {r['credit_max_score']} | {r['is_dev_example']} |"
        )

    lines.extend(
        [
            "",
            "## Incipient (separate; 6 h from catalog startTime)",
            "",
            f"Eligible recall: **{inc['recall']}** ({inc['n_hit']}/{inc['n_eligible']}); "
            f"warmup excluded {inc['n_warmup_excluded']}.",
            "",
            "| Pipe | Onset | Peak | Hit | Delay h | Pre-onset blocked | Credit max |",
            "|------|-------|------|:---:|--------:|:-----------------:|-----------:|",
        ]
    )
    for r in inc["events"]:
        if r["excluded_warmup"]:
            continue
        lines.append(
            f"| {r['pipe']} | {r['onset']} | {r['peak']} | {r['hit']} | {r['delay_hours']} | "
            f"{r['pre_onset_blocked']} | {r['credit_max_score']} |"
        )

    b = results["burden"]
    lines.extend(
        [
            "",
            "## Burden",
            "",
            f"- Notifications (2019): **{b['n_notifications_2019']}**",
            f"- Duplicate notify timestamps: **{b['n_duplicate_notify_timestamps']}**",
            f"- Events with >1 credit-window notify: **{b['n_events_with_multiple_credit_notifies']}**",
            f"- Unmatched/week: **{b['unmatched_per_week']:.3f}** ({b['n_unmatched']} unmatched)",
            f"- Alarm occupancy (2019 stamps): **{b['occupancy']:.4f}**",
            "",
            "## vs frozen hourly Method M (τ=4.347)",
            "",
            "| Metric | Hourly | Five-minute |",
            "|--------|-------:|------------:|",
            f"| Abrupt recall (inclusive) | {cmp_['abrupt_inclusive']['hourly_recall']} | "
            f"{cmp_['abrupt_inclusive']['five_min_recall']} |",
            f"| Abrupt recall (excl. p523) | {cmp_['abrupt_primary_excl_p523']['hourly_recall']} | "
            f"{cmp_['abrupt_primary_excl_p523']['five_min_recall']} |",
            f"| Incipient recall | {cmp_['incipient']['hourly_recall']} | "
            f"{cmp_['incipient']['five_min_recall']} |",
            f"| Unmatched/week | {cmp_['burden']['hourly_unmatched_per_week']:.3f} | "
            f"{cmp_['burden']['five_min_unmatched_per_week']:.3f} |",
            f"| Occupancy | {cmp_['burden']['hourly_occupancy']:.4f} | "
            f"{cmp_['burden']['five_min_occupancy']:.4f} |",
            f"| n notifications | {cmp_['burden']['hourly_n_notifications']} | "
            f"{cmp_['burden']['five_min_n_notifications']} |",
            "",
            "### Abrupt event gains / regressions",
            "",
            "| Pipe | Hourly hit/delay | 5-min hit/delay | Gain | Regression | Delay Δh |",
            "|------|-----------------:|----------------:|:----:|:----------:|---------:|",
        ]
    )
    for e in cmp_["abrupt_event_comparison"]:
        lines.append(
            f"| {e['pipe']}{'*' if e['is_dev_example'] else ''} | "
            f"{e['hourly_hit']}/{e['hourly_delay_hours']} | "
            f"{e['five_min_hit']}/{e['five_min_delay_hours']} | "
            f"{e['hit_gain']} | {e['hit_regression']} | {e['delay_delta_hours']} |"
        )
    lines.append("")
    lines.append(f"\\* `{DEV_EXAMPLE_PIPE}` = development example (excluded from primary).")
    lines.extend(
        [
            "",
            "### Delays on events detected by both",
            "",
            f"n both-hit: **{cmp_['delays_on_both_detected_abrupt']['n_both_hit']}**; "
            f"mean (5-min − hourly) delay h: "
            f"**{cmp_['delays_on_both_detected_abrupt']['mean_delay_delta_hours_five_minus_hourly']}**",
            "",
            "## Timing nulls (identical matching rules)",
            "",
            "### Primary (excl. p523)",
            "",
            f"- N=**{tn_p['n_null_replicates']}**; |E|=**{tn_p['n_events_E']}**; "
            f"true recall=**{tn_p['true_recall']}**",
            f"- Exceedances (null recall ≥ true): **{tn_p['n_timing_null_exceedances']}/"
            f"{tn_p['n_null_replicates']}**",
            f"- Percentile (null≤true): **{tn_p['true_percentile_vs_null']}**",
            f"- Null mean±std: **{tn_p['null_recall_mean']:.4f} ± {tn_p['null_recall_std']:.4f}**",
            "",
            "### Inclusive",
            "",
            f"- N=**{tn_i['n_null_replicates']}**; |E|=**{tn_i['n_events_E']}**; "
            f"true recall=**{tn_i['true_recall']}**",
            f"- Exceedances (null recall ≥ true): **{tn_i['n_timing_null_exceedances']}/"
            f"{tn_i['n_null_replicates']}**",
            f"- Percentile (null≤true): **{tn_i['true_percentile_vs_null']}**",
            f"- Hourly exceedances (null≥true): "
            f"**{cmp_['timing_nulls']['hourly_inclusive']['n_nulls_recall_ge_true']}/200**",
            "",
            tn_i["assignment_rules"],
            "",
            "## Carryover leaks (started before 2019-01-01)",
            "",
            "| Pipe | Type | Start | End | n 2019 notifies while open |",
            "|------|------|-------|-----|---------------------------:|",
        ]
    )
    for r in results["carryover_leaks_from_before_2019"]:
        lines.append(
            f"| {r['pipe']} | {r['leak_type']} | {r['start']} | {r['end']} | "
            f"{r['n_2019_notifies_while_open']} |"
        )
    lines.extend(
        [
            "",
            "## Stop",
            "",
            "No parameter changes after results. No UI / Tiger / deployment / main merge. "
            "Artifacts under `outputs/detection_2019_method_m_5min/`.",
            "",
        ]
    )
    (OUT / "METHOD_M_5MIN_2019_RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
