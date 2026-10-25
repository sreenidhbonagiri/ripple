"""Apply frozen pilot to continuous measured 2018; compare with FMR3C."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
FMR = ROOT.parent / "finite-memory-relationship-change"
# CUSUM first — do not shadow its detector with FMR3C's detector.py
sys.path.insert(0, str(CUSUM))

from evaluate import (  # noqa: E402
    DIAG,
    DEV,
    match_episodes,
    onsets_in_period,
    period_indices,
)
from audit_occupancy_recovery import (  # noqa: E402
    occupancy_report,
    split_eligible_onsets,
    train_end_time,
)
from io_data import load_leakages  # noqa: E402

import importlib.util  # noqa: E402

from features import build_feature_matrix
from io_measured import load_measured_2018
from notifications import Episode, episodes_from_scores
from schema import FEATURE_CONFIG
from train_pilot import predict_proba


def duplicate_unmatched(timestamps, episodes, matched_idx: set[int]) -> int:
    notify_times = [timestamps[ep.notify_idx] for ep in episodes]
    dup = 0
    for j, ep in enumerate(episodes):
        if j in matched_idx:
            continue
        t = notify_times[j]
        for k, t2 in enumerate(notify_times):
            if k == j:
                continue
            if abs(float((t - t2) / np.timedelta64(1, "h"))) <= 24.0:
                dup += 1
                break
    return dup


def _load_fmr(name: str):
    path = FMR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"sed_fmr_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Isolate FMR modules under unique names; wire windows/scale for detector
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def abrupt_6h(matches: list[dict]) -> dict:
    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    hits = [
        m
        for m in abrupt
        if m["matched"]
        and m["delay_hours"] is not None
        and m["delay_hours"] <= 6.0 + 1e-12
    ]
    return {
        "n_abrupt": len(abrupt),
        "n_hit": len(hits),
        "recall": (len(hits) / len(abrupt)) if abrupt else float("nan"),
        "delays": [m["delay_hours"] for m in hits],
        "per_event": [
            {
                "pipe": m["pipe"],
                "onset": m["onset"],
                "matched": m["matched"],
                "notify_time": m.get("notify_time"),
                "delay_hours": m.get("delay_hours"),
                "within_6h": bool(
                    m["matched"]
                    and m.get("delay_hours") is not None
                    and m["delay_hours"] <= 6.0 + 1e-12
                ),
                "stream_id": m.get("stream_id"),
            }
            for m in abrupt
        ],
    }


def eval_period(
    timestamps,
    episodes: list,
    leakages,
    period,
    *,
    analysis_start: int,
    analysis_end: int,
    n_sensors: int,
    label: str,
) -> dict:
    g0, g1 = period_indices(timestamps, period)
    train_end = train_end_time(timestamps, g0, 14)
    eligible, prefix = split_eligible_onsets(onsets_in_period(leakages, period), train_end)
    # Adapt Episode objects to FMR3C-compatible duck type for match_episodes
    class _E:
        pass

    adapted = []
    for ep in episodes:
        e = _E()
        e.notify_idx = ep.notify_idx
        e.end_idx = ep.end_idx
        e.change_estimate_idx = ep.notify_idx
        e.stream_id = ep.stream_id
        e.refs_used = list(ep.refs_used)
        e.target_idx = 0
        e.peak_cusum = ep.peak_score
        adapted.append(e)

    # Filter episodes to period analysis span
    adapted_p = [
        e
        for e in adapted
        if analysis_start <= e.notify_idx < analysis_end
    ]
    matches, used = match_episodes(timestamps, adapted_p, eligible, leakages)
    weeks = float((g1 - g0) * 5 / (60 * 24 * 7))
    unmatched = len(adapted_p) - len(used)
    occ = occupancy_report(
        timestamps, adapted_p, analysis_start, analysis_end, n_sensors=n_sensors
    )
    a6 = abrupt_6h(matches)
    return {
        "label": label,
        "period": period.name,
        "train_end": str(train_end).replace("T", " "),
        "n_eligible_onsets": len(eligible),
        "eligible_onsets": [
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
            }
            for L in eligible
        ],
        "n_episodes": len(adapted_p),
        "n_unmatched": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": duplicate_unmatched(
            timestamps, adapted_p, used
        ),
        "abrupt_6h": a6,
        "matches": matches,
        "prefix_n": len(prefix),
        "occupancy": {
            "union_alarm_pct_of_analysis": occ["union_alarm_pct_of_analysis"],
            "summed_sensor_alarm_pct_of_eligible": occ[
                "summed_sensor_alarm_pct_of_eligible"
            ],
            "episode_length_hours": occ["episode_length_hours"],
            "n_episodes_right_censored": occ["n_episodes_right_censored"],
        },
        "misses": [m for m in matches if not m["matched"]],
    }


def run_supervised_on_measured(frozen: dict, measured: dict) -> tuple[list[Episode], np.ndarray]:
    X, _ = build_feature_matrix(
        measured["pressures"], measured["flows"], measured["levels"]
    )
    # warm-up: scores NaN until warm_up_steps
    warm = FEATURE_CONFIG.warm_up_steps
    q = np.full(X.shape[0], np.nan, dtype=np.float64)
    ok = np.all(np.isfinite(X), axis=1)
    ok[:warm] = False
    if ok.any():
        q[ok] = predict_proba(frozen, X[ok])
    tau = float(frozen["selected"]["tau"])
    episodes = episodes_from_scores(q, tau=tau, analysis_offset=0)
    return episodes, q


def run_fmr3c_baseline(measured_pressures_path: Path, period_name: str) -> dict:
    """Replay frozen FMR3C on 2018 period (DEV or DIAG)."""
    from io_data import load_pressures

    # Load FMR package modules without permanently shadowing CUSUM detector
    _windows = _load_fmr("windows")
    _scale = _load_fmr("scale")
    sys.modules["windows"] = _windows
    sys.modules["scale"] = _scale
    _detector = _load_fmr("detector")
    _signals = _load_fmr("signals")

    emp = json.loads((FMR / "outputs" / "empirical_frozen.json").read_text())
    tau = float(emp["selected"]["tau"])
    l_q = float(emp["signal"]["l_q_hours"])
    l_r = float(emp["signal"]["l_r_hours"])

    pb = load_pressures(measured_pressures_path)
    leakages = load_leakages()
    period = DEV if period_name == "DEV" else DIAG
    g0, g1 = period_indices(pb.timestamps, period)
    sig, train_z, _, _ = _signals.build_period_signals(
        pb.pressures, interval_start=g0, interval_end=g1, train_days=14, n_refs=3
    )
    scores = _detector.build_score_bundle(
        sig.z,
        pb.sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        train_z=train_z,
        l_q_hours=l_q,
        l_r_hours=l_r,
    )
    episodes = _detector.run_all_targets_from_scores(scores, tau=tau)
    return eval_period(
        pb.timestamps,
        [
            Episode(
                notify_idx=e.notify_idx,
                end_idx=e.end_idx,
                peak_score=e.peak_score,
                stream_id=e.stream_id,
                refs_used=list(e.refs_used),
            )
            for e in episodes
        ],
        leakages,
        period,
        analysis_start=sig.analysis_offset,
        analysis_end=g1,
        n_sensors=len(pb.sensor_ids),
        label="frozen_FMR3C",
    )
