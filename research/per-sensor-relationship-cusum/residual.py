"""Directed pairwise OLS + signed per-target residual signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAD_SCALE = 1.4826


@dataclass(frozen=True)
class PairModel:
    intercept: float
    slope: float
    rmse: float
    mad: float
    n_train: int
    loc: float  # residual median on train
    scale: float  # robust scale for normalization


@dataclass
class TargetModel:
    target: int
    refs: list[int]
    pairs: dict[int, PairModel]  # ref -> model


@dataclass
class SignalBundle:
    """Per-target z(t) and optional global S(t) on an analysis span."""

    z: np.ndarray  # (T_span, S) float64 with NaN missing
    expected_by_ref: dict[tuple[int, int], np.ndarray]  # optional debug
    target_models: list[TargetModel]
    global_s: np.ndarray  # (T_span,) standardized global magnitude
    analysis_offset: int  # absolute index of first analysis row


def _mad(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = float(np.median(x))
    return float(np.median(np.abs(x - med)))


def fit_pair(
    pressures: np.ndarray,
    i: int,
    j: int,
    train_slice: slice,
) -> PairModel | None:
    train = pressures[train_slice]
    yi = train[:, i].astype(np.float64)
    xj = train[:, j].astype(np.float64)
    mask = np.isfinite(yi) & np.isfinite(xj)
    n = int(mask.sum())
    if n < 24:
        return None
    xv = xj[mask]
    yv = yi[mask]
    var = float(np.var(xv))
    if var < 1e-12:
        return None
    b = float(np.cov(xv, yv, ddof=0)[0, 1] / var)
    a = float(yv.mean() - b * xv.mean())
    resid = yv - (a + b * xv)
    # signed under-pressure residual on train: expected - measured = -resid_ols
    e = (a + b * xv) - yv
    rmse = float(np.sqrt(np.mean(resid * resid)))
    mad = _mad(e)
    loc = float(np.median(e))
    scale = mad * MAD_SCALE
    if not np.isfinite(scale) or scale < 1e-6:
        std = float(np.std(e))
        scale = std if std > 1e-6 else float("nan")
    if not np.isfinite(scale):
        return None
    return PairModel(a, b, rmse, mad, n, loc, scale)


def select_references(
    pressures: np.ndarray,
    train_slice: slice,
    *,
    n_refs: int,
    n_min_frac: float = 0.8,
) -> list[TargetModel]:
    """Training-only reference selection. No leak locations."""
    n_train = train_slice.stop - train_slice.start
    n_min = max(24, int(n_min_frac * n_train))
    n_s = pressures.shape[1]
    models: list[TargetModel] = []
    for i in range(n_s):
        cands: list[tuple[float, float, int, PairModel]] = []
        for j in range(n_s):
            if i == j:
                continue
            pm = fit_pair(pressures, i, j, train_slice)
            if pm is None or pm.n_train < n_min:
                continue
            cands.append((pm.rmse, pm.mad, j, pm))
        if not cands:
            models.append(TargetModel(i, [], {}))
            continue
        # ranks
        order_rmse = sorted(range(len(cands)), key=lambda k: cands[k][0])
        order_mad = sorted(range(len(cands)), key=lambda k: cands[k][1])
        rank_rmse = {k: r for r, k in enumerate(order_rmse)}
        rank_mad = {k: r for r, k in enumerate(order_mad)}
        scored = sorted(
            range(len(cands)),
            key=lambda k: (rank_rmse[k] + rank_mad[k], cands[k][0], cands[k][2]),
        )
        keep = scored[:n_refs]
        refs = [cands[k][2] for k in keep]
        pairs = {cands[k][2]: cands[k][3] for k in keep}
        models.append(TargetModel(i, refs, pairs))
    return models


def build_signals(
    pressures: np.ndarray,
    *,
    interval_start: int,
    interval_end: int,
    train_days: int,
    n_refs: int,
    steps_per_day: int = 288,
) -> SignalBundle:
    train_steps = train_days * steps_per_day
    train_start = interval_start
    train_end = min(interval_start + train_steps, interval_end)
    if train_end - train_start < steps_per_day:
        raise ValueError("training window too short")
    train_slice = slice(train_start, train_end)
    target_models = select_references(pressures, train_slice, n_refs=n_refs)

    analysis_offset = train_end
    span = interval_end - analysis_offset
    n_s = pressures.shape[1]
    z = np.full((span, n_s), np.nan, dtype=np.float64)
    n_ref_min = max(1, (n_refs + 1) // 2)

    # Precompute all directed pair residuals for global S on analysis (+ train for scale)
    # Global uses all valid pairs — equivalent-effort baseline
    global_raw = np.full(span, np.nan, dtype=np.float64)

    block = pressures[analysis_offset:interval_end]
    # Also need train residuals for global scale
    train_block = pressures[train_start:train_end]

    # Fit all directed pairs for global (reuse select's fits where possible, else fit)
    all_pairs: dict[tuple[int, int], PairModel] = {}
    for i in range(n_s):
        for j in range(n_s):
            if i == j:
                continue
            if i in range(len(target_models)) and j in target_models[i].pairs:
                all_pairs[(i, j)] = target_models[i].pairs[j]
            else:
                pm = fit_pair(pressures, i, j, train_slice)
                if pm is not None:
                    all_pairs[(i, j)] = pm

    # Per-target z
    for tm in target_models:
        i = tm.target
        if not tm.refs:
            continue
        cols = []
        for j, pm in tm.pairs.items():
            pj = block[:, j]
            pi = block[:, i]
            e = (pm.intercept + pm.slope * pj) - pi
            tilde = (e - pm.loc) / pm.scale
            ok = np.isfinite(pj) & np.isfinite(pi) & np.isfinite(tilde)
            col = np.where(ok, tilde, np.nan)
            cols.append(col)
        if not cols:
            continue
        stack = np.vstack(cols)  # (R, T)
        valid_count = np.sum(np.isfinite(stack), axis=0)
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack, axis=0)
        med = np.where(valid_count >= n_ref_min, med, np.nan)
        z[:, i] = med

    # Global S(t): Frobenius-like of signed e (same polarity magnitude)
    s2 = np.zeros(span, dtype=np.float64)
    cnt = np.zeros(span, dtype=np.int32)
    for (i, j), pm in all_pairs.items():
        pj = block[:, j]
        pi = block[:, i]
        e = (pm.intercept + pm.slope * pj) - pi
        ok = np.isfinite(pj) & np.isfinite(pi) & np.isfinite(e)
        s2 = np.where(ok, s2 + e * e, s2)
        cnt = np.where(ok, cnt + 1, cnt)
    raw_s = np.where(cnt > 0, np.sqrt(s2), np.nan)

    # train scale for S
    s2_tr = np.zeros(train_end - train_start, dtype=np.float64)
    cnt_tr = np.zeros(train_end - train_start, dtype=np.int32)
    for (i, j), pm in all_pairs.items():
        pj = train_block[:, j]
        pi = train_block[:, i]
        e = (pm.intercept + pm.slope * pj) - pi
        ok = np.isfinite(pj) & np.isfinite(pi) & np.isfinite(e)
        s2_tr = np.where(ok, s2_tr + e * e, s2_tr)
        cnt_tr = np.where(ok, cnt_tr + 1, cnt_tr)
    raw_s_tr = np.where(cnt_tr > 0, np.sqrt(s2_tr), np.nan)
    finite_tr = raw_s_tr[np.isfinite(raw_s_tr)]
    if finite_tr.size < 10:
        global_s = np.full(span, np.nan)
    else:
        loc = float(np.median(finite_tr))
        scale = _mad(finite_tr) * MAD_SCALE
        if not np.isfinite(scale) or scale < 1e-9:
            scale = float(np.std(finite_tr)) or 1.0
        global_s = (raw_s - loc) / scale

    return SignalBundle(
        z=z,
        expected_by_ref={},
        target_models=target_models,
        global_s=global_s,
        analysis_offset=analysis_offset,
    )


def expected_pressure_series(
    pressures: np.ndarray,
    tm: TargetModel,
    ref: int,
    start: int,
    end: int,
) -> np.ndarray:
    """Expected pressure hat{P}_i^(j) on [start, end) for verification."""
    pm = tm.pairs[ref]
    pj = pressures[start:end, ref]
    return pm.intercept + pm.slope * pj
