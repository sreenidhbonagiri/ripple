"""Pairwise OLS residuals + offline CUSUM (LILA-inspired; independent code)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PairwiseModel:
    intercept: np.ndarray  # (S, S); intercept[i,j] for P_i ~ a + b P_j
    slope: np.ndarray
    train_mean_S: float
    train_std_S: float
    n_sensors: int


@dataclass
class Candidate:
    change_idx: int
    alarm_idx: int
    score_at_change: float
    evidence_through_idx: int


def fit_pairwise_ols(
    pressures: np.ndarray,
    train_slice: slice,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit P_i = a_ij + b_ij P_j on training rows. Diagonal left as NaN."""
    train = pressures[train_slice]
    _, n_s = train.shape
    intercept = np.full((n_s, n_s), np.nan, dtype=np.float64)
    slope = np.full((n_s, n_s), np.nan, dtype=np.float64)
    for j in range(n_s):
        x = train[:, j]
        for i in range(n_s):
            if i == j:
                continue
            y = train[:, i]
            mask = np.isfinite(x) & np.isfinite(y)
            if mask.sum() < 24:
                continue
            xv = x[mask].astype(np.float64)
            yv = y[mask].astype(np.float64)
            var = np.var(xv)
            if var < 1e-12:
                continue
            b = np.cov(xv, yv, ddof=0)[0, 1] / var
            a = float(yv.mean() - b * xv.mean())
            intercept[i, j] = a
            slope[i, j] = b
    return intercept, slope


def aggregate_score(
    pressures: np.ndarray,
    intercept: np.ndarray,
    slope: np.ndarray,
    start: int,
    end: int,
) -> np.ndarray:
    """Frobenius-like residual magnitude on [start, end). NaN where no valid pairs."""
    n = end - start
    s2 = np.zeros(n, dtype=np.float64)
    counts = np.zeros(n, dtype=np.int32)
    block = pressures[start:end]
    n_s = block.shape[1]
    for j in range(n_s):
        pj = block[:, j]
        for i in range(n_s):
            if i == j:
                continue
            a = intercept[i, j]
            b = slope[i, j]
            if not (np.isfinite(a) and np.isfinite(b)):
                continue
            r = block[:, i] - (a + b * pj)
            ok = np.isfinite(r) & np.isfinite(pj) & np.isfinite(block[:, i])
            s2 = np.where(ok, s2 + r * r, s2)
            counts = np.where(ok, counts + 1, counts)
    out = np.full(n, np.nan, dtype=np.float64)
    valid = counts > 0
    out[valid] = np.sqrt(s2[valid])
    return out


def build_model(pressures: np.ndarray, train_start: int, train_end: int) -> PairwiseModel:
    intercept, slope = fit_pairwise_ols(pressures, slice(train_start, train_end))
    train_scores = aggregate_score(pressures, intercept, slope, train_start, train_end)
    finite = train_scores[np.isfinite(train_scores)]
    n_s = pressures.shape[1]
    if finite.size < 10:
        # Degenerate (e.g. constant sensors): no usable pairs → no candidates downstream.
        return PairwiseModel(intercept, slope, float("nan"), float("nan"), n_s)
    mu = float(finite.mean())
    sd = float(finite.std())
    if sd < 1e-9:
        sd = 1.0
    return PairwiseModel(intercept, slope, mu, sd, n_s)


def offline_cusum_candidates(
    scores: np.ndarray,
    *,
    mu: float,
    sd: float,
    analysis_offset: int,
    k: float,
    h: float,
    min_segment_steps: int,
) -> list[Candidate]:
    """CUSUM on z=(S-mu)/sd for scores aligned to absolute indices via analysis_offset.

    ``scores`` covers absolute indices [analysis_offset, analysis_offset+len).
    Never reads beyond that array (interval end bound).
    """
    candidates: list[Candidate] = []
    c = 0.0
    last_zero_local = 0
    last_alarm_local = -10**9
    if not (np.isfinite(mu) and np.isfinite(sd) and sd > 0):
        return []
    for local, s in enumerate(scores):
        if not np.isfinite(s):
            c = 0.0
            last_zero_local = local
            continue
        z = (s - mu) / sd
        c = max(0.0, c + z - k)
        if c == 0.0:
            last_zero_local = local
        if c >= h and (local - last_alarm_local) >= min_segment_steps:
            change_local = last_zero_local
            alarm_local = local
            candidates.append(
                Candidate(
                    change_idx=analysis_offset + change_local,
                    alarm_idx=analysis_offset + alarm_local,
                    score_at_change=float(scores[change_local]),
                    evidence_through_idx=-1,  # filled by caller
                )
            )
            last_alarm_local = local
            c = 0.0
            last_zero_local = local
    # evidence_through = next change or end of scores
    end_abs = analysis_offset + len(scores) - 1
    for i, cand in enumerate(candidates):
        if i + 1 < len(candidates):
            cand.evidence_through_idx = candidates[i + 1].change_idx
        else:
            cand.evidence_through_idx = end_abs
    return candidates


def run_interval(
    pressures: np.ndarray,
    *,
    interval_start: int,
    interval_end: int,
    train_days: int,
    steps_per_day: int = 288,
    cusum_k: float = 0.5,
    cusum_h: float = 6.0,
    min_segment_hours: float = 12.0,
) -> tuple[PairwiseModel, list[Candidate], np.ndarray]:
    """Fit on prefix; score+CUSUM on post-training portion through interval_end (exclusive end idx)."""
    train_steps = train_days * steps_per_day
    train_start = interval_start
    train_end = min(interval_start + train_steps, interval_end)
    if train_end - train_start < steps_per_day:
        raise ValueError("training window too short for interval")
    model = build_model(pressures, train_start, train_end)
    # Analysis uses only [train_end, interval_end) — never beyond interval_end
    scores = aggregate_score(pressures, model.intercept, model.slope, train_end, interval_end)
    min_seg = int(min_segment_hours * 12)  # 5-min steps
    cands = offline_cusum_candidates(
        scores,
        mu=model.train_mean_S,
        sd=model.train_std_S,
        analysis_offset=train_end,
        k=cusum_k,
        h=cusum_h,
        min_segment_steps=min_seg,
    )
    return model, cands, scores
