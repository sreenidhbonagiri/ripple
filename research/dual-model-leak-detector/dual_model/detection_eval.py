"""Matching, gates, timing nulls, transition confounding."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .detection_protocol import (
    ABRUPT_EVENTS,
    CREDIT_HOURS,
    GATE_RECALL,
    GATE_UNMATCHED_PER_WEEK,
    N_TIMING_NULLS,
    PUMP_TRANSITION_M3H,
    STORAGE_TRANSITION_M3H,
    WARMUP_HOURS,
    AbruptEvent,
)
from .notifier import Episode, episodes_from_scores


def storage_rate_m3h(levels: pd.Series, tank_area_m2: float) -> pd.Series:
    """Tank storage rate A·dh/dt in m³/h.

    Scales by the index step so hourly series are not treated as 5 min
    (the previous helper used ``diff()*12`` unconditionally, which inflated
    hourly |dV| ~12× — see DETECTION_FAILURE_AUDIT.md).
    """
    lv = levels.astype(float)
    if len(lv) < 2:
        return pd.Series(np.nan, index=lv.index)
    dt_hours = lv.index.to_series().diff().dt.total_seconds() / 3600.0
    med = float(np.nanmedian(dt_hours.to_numpy(dtype=float)))
    if not np.isfinite(med) or med <= 0:
        med = 1.0
    step_h = dt_hours.where(dt_hours > 0, med)
    return tank_area_m2 * (lv.diff() / step_h)


def period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    from .detection_protocol import DEV_END, DEV_START, DIAG_END, DIAG_START

    if period == "DEV":
        return pd.Timestamp(DEV_START), pd.Timestamp(DEV_END)
    if period == "DIAG":
        return pd.Timestamp(DIAG_START), pd.Timestamp(DIAG_END)
    raise ValueError(period)


def eligible_events(period: str, index: pd.DatetimeIndex) -> list[AbruptEvent]:
    start, end = period_bounds(period)
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    out = []
    for ev in ABRUPT_EVENTS:
        if ev.period != period:
            continue
        onset = pd.Timestamp(ev.onset)
        if onset < warm or onset > end:
            continue
        credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
        if credit_end < start:
            continue
        # Need at least one index hour in credit window
        if not ((index >= onset) & (index <= credit_end)).any():
            continue
        out.append(ev)
    return out


def evaluate_scores(
    scores: pd.Series,
    period: str,
    *,
    tau: float,
    flows: pd.DataFrame | None = None,
    levels: pd.Series | None = None,
    tank_area_m2: float | None = None,
    rng: np.random.Generator | None = None,
    n_nulls: int = N_TIMING_NULLS,
) -> dict[str, Any]:
    start, end = period_bounds(period)
    s = scores.loc[(scores.index >= start) & (scores.index <= end)].astype(float)
    index = s.index
    events = eligible_events(period, index)
    episodes = episodes_from_scores(s.to_numpy(), tau=tau)

    # Map episode notify times
    notify_times = [index[ep.notify_idx] for ep in episodes if 0 <= ep.notify_idx < len(index)]
    matched_notifies: set[pd.Timestamp] = set()
    event_rows = []
    for ev in events:
        onset = pd.Timestamp(ev.onset)
        credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
        candidates = [t for t in notify_times if onset <= t <= credit_end]
        hit = len(candidates) > 0
        delay_h = None
        matched_t = None
        if hit:
            matched_t = min(candidates)
            matched_notifies.add(matched_t)
            delay_h = float((matched_t - onset).total_seconds() / 3600.0)
        event_rows.append(
            {
                "pipe": ev.pipe,
                "onset": str(onset),
                "hit": hit,
                "delay_hours": delay_h,
                "matched_notify": str(matched_t) if matched_t is not None else None,
            }
        )

    n_hit = sum(1 for r in event_rows if r["hit"])
    n_ev = len(event_rows)
    recall = float(n_hit / n_ev) if n_ev else float("nan")
    delays = [r["delay_hours"] for r in event_rows if r["delay_hours"] is not None]

    unmatched = [t for t in notify_times if t not in matched_notifies]
    weeks = max((end - start).total_seconds() / (7 * 24 * 3600), 1e-9)
    unmatched_per_week = float(len(unmatched) / weeks)

    # Occupancy: fraction of steps inside any episode
    active = np.zeros(len(index), dtype=bool)
    for ep in episodes:
        a, b = ep.notify_idx, ep.end_idx
        if a < 0:
            continue
        active[a : b + 1] = True
    occupancy = float(active.mean()) if len(active) else float("nan")

    # Operating-transition confounding among unmatched
    transition_frac = None
    if flows is not None and levels is not None and tank_area_m2 is not None and unmatched:
        fl = flows.reindex(index)
        lv = levels.reindex(index)
        d_pump = fl["PUMP_1"].astype(float).diff().abs()
        dV = storage_rate_m3h(lv, tank_area_m2).abs()
        trans = (d_pump > PUMP_TRANSITION_M3H) | (dV > STORAGE_TRANSITION_M3H)
        n_trans = sum(1 for t in unmatched if bool(trans.get(t, False)))
        transition_frac = float(n_trans / len(unmatched))

    gate_pass = (
        n_ev > 0
        and np.isfinite(recall)
        and recall >= GATE_RECALL
        and unmatched_per_week <= GATE_UNMATCHED_PER_WEEK
    )

    null_stats = timing_nulls(
        scores=s,
        events=events,
        tau=tau,
        period=period,
        rng=rng or np.random.default_rng(0),
        n_nulls=n_nulls,
    )

    return {
        "period": period,
        "tau": tau,
        "n_eligible_abrupt": n_ev,
        "n_hit": n_hit,
        "abrupt_6h_recall": recall,
        "mean_delay_hours": float(np.mean(delays)) if delays else None,
        "delays_hours": delays,
        "n_notifications": len(notify_times),
        "n_unmatched": len(unmatched),
        "unmatched_per_week": unmatched_per_week,
        "occupancy": occupancy,
        "unmatched_on_transition_frac": transition_frac,
        "gate_pass": gate_pass,
        "events": event_rows,
        "timing_nulls": null_stats,
    }


def timing_nulls(
    *,
    scores: pd.Series,
    events: list[AbruptEvent],
    tau: float,
    period: str,
    rng: np.random.Generator,
    n_nulls: int,
) -> dict[str, Any]:
    """Density-matched (hour-of-day) timing nulls for abrupt 6h recall."""
    if not events:
        return {"n_nulls": 0, "null_recall_mean": None, "true_percentile": None}
    start, end = period_bounds(period)
    index = scores.index
    warm = start + pd.Timedelta(hours=WARMUP_HOURS)
    eligible_hours = index[(index >= warm) & (index <= end)]
    if len(eligible_hours) == 0:
        return {"n_nulls": 0, "null_recall_mean": None, "true_percentile": None}

    true_onsets = [pd.Timestamp(ev.onset) for ev in events]
    hod = np.array([t.hour for t in true_onsets], dtype=int)
    # Candidate pools by hour-of-day
    pools = {h: eligible_hours[eligible_hours.hour == h] for h in range(24)}

    def recall_for_onsets(onsets: list[pd.Timestamp]) -> float:
        episodes = episodes_from_scores(scores.to_numpy(), tau=tau)
        notify_times = [
            index[ep.notify_idx] for ep in episodes if 0 <= ep.notify_idx < len(index)
        ]
        hits = 0
        for onset in onsets:
            credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
            if any(onset <= t <= credit_end for t in notify_times):
                hits += 1
        return hits / len(onsets)

    true_recall = recall_for_onsets(true_onsets)
    null_recalls = []
    for _ in range(n_nulls):
        sampled = []
        for h in hod:
            pool = pools.get(int(h), eligible_hours)
            if len(pool) == 0:
                pool = eligible_hours
            sampled.append(pd.Timestamp(rng.choice(pool)))
        null_recalls.append(recall_for_onsets(sampled))
    arr = np.asarray(null_recalls, dtype=float)
    # percentile of true among nulls (higher = more extreme vs null)
    pct = float((arr <= true_recall).mean())
    return {
        "n_nulls": n_nulls,
        "true_recall": true_recall,
        "null_recall_mean": float(arr.mean()),
        "null_recall_std": float(arr.std(ddof=0)),
        "true_percentile_vs_null": pct,
    }


def select_tau_on_dev(dev_results_by_tau: dict[float, dict]) -> dict[str, Any]:
    """Largest tau that passes gates; else selection_failed + fallback."""
    from .detection_protocol import FALLBACK_TAU, TAU_GRID

    passing = [t for t in TAU_GRID if dev_results_by_tau[t]["gate_pass"]]
    if passing:
        tau = max(passing)
        return {
            "selection_passed": True,
            "tau": tau,
            "fallback": False,
            "reason": "largest_tau_passing_gates",
        }
    # Fallback: among budget, maximize recall then minimize unmatched/week
    best = None
    for t in TAU_GRID:
        r = dev_results_by_tau[t]
        key = (r["abrupt_6h_recall"] if np.isfinite(r["abrupt_6h_recall"]) else -1.0, -r["unmatched_per_week"])
        if best is None or key > best[0]:
            best = (key, t)
    tau = best[1] if best is not None else FALLBACK_TAU
    return {
        "selection_passed": False,
        "tau": tau,
        "fallback": True,
        "reason": "no_tau_passed_gates_diagnostic_fallback",
    }