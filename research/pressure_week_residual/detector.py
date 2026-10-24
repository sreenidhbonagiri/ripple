"""Causal pressure scores and episode policy (research only; no production wiring)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from io_scada import MIN30, WEEK, ScadaBundle  # noqa: E402

CONFIRM_K = 3
CLEAR_M = 6
STEPS_PER_WEEK = int(WEEK / np.timedelta64(5, "m"))  # 2016
STEPS_30M = int(MIN30 / np.timedelta64(5, "m"))  # 6


@dataclass(frozen=True)
class ScoreSeries:
    """Per-timestep network scores. NaN score means missing_history (not zero)."""

    score: np.ndarray  # float64 (T,), NaN if missing_history
    strongest_sensor_idx: np.ndarray  # int32 (T,), -1 if missing
    missing_history: np.ndarray  # bool (T,)
    method: str


def _max_drop_scores(pressures: np.ndarray, lag_steps: int, method: str) -> ScoreSeries:
    """Causal max_s (P(t-lag)-P(t)) over sensors; NaN/missing_history when no valid sensor."""
    t_count, _ = pressures.shape
    score = np.full(t_count, np.nan, dtype=np.float64)
    strongest = np.full(t_count, -1, dtype=np.int32)
    missing = np.ones(t_count, dtype=bool)
    if t_count <= lag_steps:
        return ScoreSeries(score, strongest, missing, method=method)

    cur = pressures[lag_steps:]
    ref = pressures[:-lag_steps]
    valid = np.isfinite(cur) & np.isfinite(ref)
    drop = np.where(valid, ref - cur, -np.inf)
    any_valid = valid.any(axis=1)
    idxs = np.where(any_valid)[0]
    if idxs.size:
        j = np.argmax(drop[idxs], axis=1)
        target = lag_steps + idxs
        score[target] = drop[idxs, j]
        strongest[target] = j.astype(np.int32)
        missing[target] = False
    return ScoreSeries(score, strongest, missing, method=method)


def week_residual_scores(pressures: np.ndarray) -> ScoreSeries:
    """r_s(t)=P(t-7d)-P(t); S(t)=max valid residual. Uses only rows ≤ t."""
    return _max_drop_scores(pressures, STEPS_PER_WEEK, "week_residual")


def raw_drop_scores(pressures: np.ndarray, lag_steps: int = STEPS_30M) -> ScoreSeries:
    """b_s(t)=P(t-lag)-P(t); B(t)=max valid. Causal short-horizon raw drop baseline."""
    return _max_drop_scores(pressures, lag_steps, "raw_30m_drop")


@dataclass
class Episode:
    start_idx: int
    end_idx: int  # inclusive last alarmed index
    notify_idx: int
    peak_score: float
    strongest_sensor_idx: int


def build_episodes(
    series: ScoreSeries,
    tau: float,
    confirm_k: int = CONFIRM_K,
    clear_m: int = CLEAR_M,
    start_idx: int = 0,
    end_idx_exclusive: int | None = None,
) -> list[Episode]:
    """Streaming confirm/clear over [start_idx, end_idx_exclusive)."""
    n = len(series.score)
    end = n if end_idx_exclusive is None else end_idx_exclusive
    episodes: list[Episode] = []
    in_alarm = False
    exceed_run = 0
    clear_run = 0
    pending_start = -1
    cur_peak = -np.inf
    cur_strong = -1
    ep_notify = -1

    for i in range(start_idx, end):
        if series.missing_history[i]:
            # Missing history does not count as normal low score; freeze streak counters.
            continue
        s = series.score[i]
        if not in_alarm:
            if s >= tau:
                if exceed_run == 0:
                    pending_start = i
                exceed_run += 1
                if s > cur_peak:
                    cur_peak = s
                    cur_strong = int(series.strongest_sensor_idx[i])
                if exceed_run >= confirm_k:
                    in_alarm = True
                    ep_notify = i
                    clear_run = 0
            else:
                exceed_run = 0
                pending_start = -1
                cur_peak = -np.inf
                cur_strong = -1
        else:
            if s > cur_peak:
                cur_peak = s
                cur_strong = int(series.strongest_sensor_idx[i])
            if s < tau:
                clear_run += 1
                if clear_run >= clear_m:
                    # Episode ends at the step before the clear run completed.
                    end_i = i - clear_m
                    episodes.append(
                        Episode(
                            start_idx=pending_start,
                            end_idx=max(end_i, ep_notify),
                            notify_idx=ep_notify,
                            peak_score=float(cur_peak),
                            strongest_sensor_idx=cur_strong,
                        )
                    )
                    in_alarm = False
                    exceed_run = 0
                    clear_run = 0
                    pending_start = -1
                    cur_peak = -np.inf
                    cur_strong = -1
                    ep_notify = -1
            else:
                clear_run = 0

    if in_alarm:
        episodes.append(
            Episode(
                start_idx=pending_start,
                end_idx=end - 1,
                notify_idx=ep_notify,
                peak_score=float(cur_peak),
                strongest_sensor_idx=cur_strong,
            )
        )
    return episodes


def context_deltas_at(bundle: ScadaBundle, idx: int) -> dict[str, float | None]:
    """Prior-week deltas for flow/pump/tank at idx — context only, never a veto."""
    out: dict[str, float | None] = {}
    if idx < STEPS_PER_WEEK:
        for name in bundle.flow_ids + bundle.level_ids:
            out[name] = None
        return out
    for j, name in enumerate(bundle.flow_ids):
        cur = float(bundle.flows[idx, j])
        ref = float(bundle.flows[idx - STEPS_PER_WEEK, j])
        out[name] = None if not (np.isfinite(cur) and np.isfinite(ref)) else cur - ref
    for j, name in enumerate(bundle.level_ids):
        cur = float(bundle.levels[idx, j])
        ref = float(bundle.levels[idx - STEPS_PER_WEEK, j])
        out[name] = None if not (np.isfinite(cur) and np.isfinite(ref)) else cur - ref
    return out
