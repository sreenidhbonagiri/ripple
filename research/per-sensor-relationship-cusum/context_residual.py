"""Operating-context correction of pairwise relationship residuals (associative)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from residual import MAD_SCALE, TargetModel, _mad

FEATURE_NAMES = [
    "sin_tod",
    "cos_tod",
    "is_weekend",
    "pump1",
    "pump1_on",
    "tank_T1",
    "d_tank_T1",
]
PUMP_ON_EPS = 1.0
ALPHA_GRID = [0.1, 1.0, 10.0, 100.0, 1000.0]


@dataclass
class ContextModel:
    target_idx: int
    beta: np.ndarray  # includes intercept as beta[0]
    alpha: float
    n_fit: int
    train_rmse: float


@dataclass
class DualSignals:
    """Baseline and context-corrected standardized series on the analysis span."""

    z_base: np.ndarray  # (T, S)
    z_ctx: np.ndarray
    r_raw: np.ndarray  # meters aggregate residual
    r_corr: np.ndarray
    r_hat_ctx: np.ndarray
    analysis_offset: int
    target_models: list[TargetModel]
    context_models: list[ContextModel | None]
    alpha: float
    feature_names: list[str]


def build_context_features(
    timestamps: np.ndarray,
    pump1: np.ndarray,
    tank_t1: np.ndarray,
    start: int,
    end: int,
) -> np.ndarray:
    """Causal features on [start, end). Shape (n, n_features). No future values."""
    n = end - start
    X = np.zeros((n, len(FEATURE_NAMES)), dtype=np.float64)
    # hour of day from datetime64[m]
    # convert to python-friendly: hours since epoch
    ts = timestamps[start:end]
    # numpy: view as minutes then derive hour-of-day
    # timestamps are datetime64[m]
    minutes = ts.astype("datetime64[m]").astype(np.int64)
    # day-of-week: 1970-01-01 was Thursday → (days+4)%7 with Mon=0
    days = ts.astype("datetime64[D]").astype(np.int64)
    dow = (days + 4) % 7  # Mon=0 … Sun=6
    hour = (minutes % (24 * 60)) / 60.0
    X[:, 0] = np.sin(2 * np.pi * hour / 24.0)
    X[:, 1] = np.cos(2 * np.pi * hour / 24.0)
    X[:, 2] = (dow >= 5).astype(np.float64)
    p = pump1[start:end].astype(np.float64)
    X[:, 3] = p
    X[:, 4] = (np.isfinite(p) & (p > PUMP_ON_EPS)).astype(np.float64)
    t1 = tank_t1[start:end].astype(np.float64)
    X[:, 5] = t1
    d = np.full(n, np.nan, dtype=np.float64)
    if start > 0:
        prev = tank_t1[start - 1 : end - 1].astype(np.float64)
        d = t1 - prev
    else:
        d[1:] = t1[1:] - t1[:-1]
        d[0] = np.nan
    X[:, 6] = d
    return X


def aggregate_raw_residuals(
    pressures: np.ndarray,
    target_models: list[TargetModel],
    start: int,
    end: int,
) -> np.ndarray:
    """r_i(t) = median_j e_ij(t) in meters on [start, end). Shape (n, S)."""
    n = end - start
    n_s = pressures.shape[1]
    out = np.full((n, n_s), np.nan, dtype=np.float64)
    block = pressures[start:end]
    n_ref_min_default = 1
    for tm in target_models:
        i = tm.target
        if not tm.refs:
            continue
        cols = []
        for j, pm in tm.pairs.items():
            e = (pm.intercept + pm.slope * block[:, j]) - block[:, i]
            ok = np.isfinite(block[:, j]) & np.isfinite(block[:, i])
            cols.append(np.where(ok, e, np.nan))
        stack = np.vstack(cols)
        n_ref_min = max(n_ref_min_default, (len(tm.refs) + 1) // 2)
        valid = np.sum(np.isfinite(stack), axis=0)
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack, axis=0)
        out[:, i] = np.where(valid >= n_ref_min, med, np.nan)
    return out


def _design_matrix(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Add intercept; return (X1, row_mask) for finite rows."""
    mask = np.all(np.isfinite(X), axis=1)
    Xf = X[mask]
    ones = np.ones((Xf.shape[0], 1), dtype=np.float64)
    return np.hstack([ones, Xf]), mask


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, int, float]:
    X1, mask = _design_matrix(X)
    yf = y[mask]
    if X1.shape[0] < X1.shape[1] + 5:
        raise ValueError("insufficient rows for ridge")
    # Do not penalize intercept
    p = X1.shape[1]
    xtx = X1.T @ X1
    pen = np.eye(p) * alpha
    pen[0, 0] = 0.0
    beta = np.linalg.solve(xtx + pen, X1.T @ yf)
    pred = X1 @ beta
    rmse = float(np.sqrt(np.mean((yf - pred) ** 2)))
    return beta, int(mask.sum()), rmse


def predict_ridge(X: np.ndarray, beta: np.ndarray) -> np.ndarray:
    out = np.full(X.shape[0], np.nan, dtype=np.float64)
    X1, mask = _design_matrix(X)
    out[mask] = X1 @ beta
    return out


def standardize_series(r: np.ndarray, train_slice_local: slice) -> tuple[np.ndarray, float, float]:
    """Identical robust normalization procedure on a 1-D series (analysis-local)."""
    train = r[train_slice_local]
    finite = train[np.isfinite(train)]
    if finite.size < 10:
        return np.full_like(r, np.nan, dtype=np.float64), float("nan"), float("nan")
    loc = float(np.median(finite))
    scale = _mad(finite) * MAD_SCALE
    if not np.isfinite(scale) or scale < 1e-6:
        std = float(np.std(finite))
        scale = std if std > 1e-6 else float("nan")
    if not np.isfinite(scale):
        return np.full_like(r, np.nan, dtype=np.float64), loc, scale
    z = (r - loc) / scale
    z = np.where(np.isfinite(r), z, np.nan)
    return z, loc, scale


def select_alpha_dev(
    X_fit: np.ndarray,
    y_fit: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    alphas: list[float] = ALPHA_GRID,
) -> tuple[float, dict]:
    """Pick alpha by chronological validation RMSE for one target."""
    scores = {}
    best_a, best_s = alphas[0], float("inf")
    for a in alphas:
        try:
            beta, _, _ = fit_ridge(X_fit, y_fit, a)
        except Exception:
            continue
        pred = predict_ridge(X_val, beta)
        m = np.isfinite(pred) & np.isfinite(y_val)
        if m.sum() < 20:
            continue
        rmse = float(np.sqrt(np.mean((y_val[m] - pred[m]) ** 2)))
        scores[a] = rmse
        if rmse < best_s:
            best_s, best_a = rmse, a
    return best_a, scores


def build_dual_signals(
    pressures: np.ndarray,
    timestamps: np.ndarray,
    pump1: np.ndarray,
    tank_t1: np.ndarray,
    target_models: list[TargetModel],
    *,
    interval_start: int,
    interval_end: int,
    pair_train_days: int = 14,
    context_fit_days: int = 14,
    context_val_days: int = 14,
    alpha: float | None = None,
    select_alpha: bool = False,
    steps_per_day: int = 288,
) -> tuple[DualSignals, dict]:
    """Build baseline and context-corrected z on post-pair analysis span.

    If select_alpha: choose alpha on DEV context-val RMSE (mean across targets).
    If alpha given: use it (DIAG / frozen).
    """
    pair_train_steps = pair_train_days * steps_per_day
    pair_train_end = min(interval_start + pair_train_steps, interval_end)
    analysis_offset = pair_train_end
    if analysis_offset >= interval_end:
        raise ValueError("no analysis span")

    r_full = aggregate_raw_residuals(
        pressures, target_models, analysis_offset, interval_end
    )
    X_full = build_context_features(
        timestamps, pump1, tank_t1, analysis_offset, interval_end
    )

    fit_steps = context_fit_days * steps_per_day
    val_steps = context_val_days * steps_per_day
    fit_end = min(fit_steps, r_full.shape[0])
    val_end = min(fit_end + val_steps, r_full.shape[0])

    meta = {
        "pair_train_end": str(timestamps[pair_train_end]).replace("T", " "),
        "context_fit_local": [0, fit_end],
        "context_val_local": [fit_end, val_end],
        "alpha_grid": ALPHA_GRID,
        "alpha_selected": None,
        "alpha_scores_mean_rmse": {},
        "feature_names": FEATURE_NAMES,
        "units": {
            "residual": "meters",
            "pump1": "SCADA flow units",
            "tank_T1": "SCADA level units",
            "d_tank_T1": "level units per 5-min step (causal)",
        },
    }

    if select_alpha:
        # Mean validation RMSE across targets with enough data
        score_sums = {a: 0.0 for a in ALPHA_GRID}
        score_counts = {a: 0 for a in ALPHA_GRID}
        for ti in range(r_full.shape[1]):
            y = r_full[:, ti]
            if np.sum(np.isfinite(y[0:fit_end])) < 50:
                continue
            for a in ALPHA_GRID:
                try:
                    beta, _, _ = fit_ridge(X_full[0:fit_end], y[0:fit_end], a)
                except Exception:
                    continue
                pred = predict_ridge(X_full[fit_end:val_end], beta)
                yv = y[fit_end:val_end]
                m = np.isfinite(pred) & np.isfinite(yv)
                if m.sum() < 20:
                    continue
                rmse = float(np.sqrt(np.mean((yv[m] - pred[m]) ** 2)))
                score_sums[a] += rmse
                score_counts[a] += 1
        means = {
            a: (score_sums[a] / score_counts[a]) if score_counts[a] else float("inf")
            for a in ALPHA_GRID
        }
        alpha = min(means, key=means.get)
        meta["alpha_scores_mean_rmse"] = means
        meta["alpha_selected"] = alpha
    elif alpha is None:
        raise ValueError("alpha required when select_alpha is False")

    meta["alpha_selected"] = alpha

    # Fit context models on context-fit window with chosen alpha
    context_models: list[ContextModel | None] = []
    r_hat = np.full_like(r_full, np.nan)
    for ti in range(r_full.shape[1]):
        y = r_full[:, ti]
        if np.sum(np.isfinite(y[0:fit_end])) < 50:
            context_models.append(None)
            continue
        try:
            beta, n_fit, tr_rmse = fit_ridge(X_full[0:fit_end], y[0:fit_end], alpha)
        except Exception:
            context_models.append(None)
            continue
        context_models.append(
            ContextModel(ti, beta, alpha, n_fit, tr_rmse)
        )
        r_hat[:, ti] = predict_ridge(X_full, beta)

    r_corr = r_full - r_hat

    # Standardize: use pairwise-training window residuals for loc/scale.
    # Pair train is before analysis_offset — recompute r on pair train for loc/scale.
    r_pair_train = aggregate_raw_residuals(
        pressures, target_models, interval_start, pair_train_end
    )
    # For corrected series, context hat on pair-train is not defined the same way;
    # use analysis-local first fit_end days of each series for loc/scale of that series
    # (identical *procedure*: robust loc/scale on a chronological early window of the
    # series being standardized). Documented in CONTEXT_DESIGN as pairwise-train for
    # baseline raw; for corrected use context-fit window (early corrected samples).
    n_s = r_full.shape[1]
    z_base = np.full_like(r_full, np.nan)
    z_ctx = np.full_like(r_full, np.nan)
    # Baseline: loc/scale from pair-train raw aggregate
    for ti in range(n_s):
        finite = r_pair_train[:, ti]
        finite = finite[np.isfinite(finite)]
        if finite.size < 10:
            continue
        loc = float(np.median(finite))
        scale = _mad(finite) * MAD_SCALE
        if not np.isfinite(scale) or scale < 1e-6:
            std = float(np.std(finite))
            scale = std if std > 1e-6 else float("nan")
        if not np.isfinite(scale):
            continue
        z_base[:, ti] = np.where(
            np.isfinite(r_full[:, ti]), (r_full[:, ti] - loc) / scale, np.nan
        )

    # Corrected: loc/scale from context-fit window of r_corr (chronological early window)
    for ti in range(n_s):
        train = r_corr[0:fit_end, ti]
        finite = train[np.isfinite(train)]
        if finite.size < 10:
            continue
        loc = float(np.median(finite))
        scale = _mad(finite) * MAD_SCALE
        if not np.isfinite(scale) or scale < 1e-6:
            std = float(np.std(finite))
            scale = std if std > 1e-6 else float("nan")
        if not np.isfinite(scale):
            continue
        z_ctx[:, ti] = np.where(
            np.isfinite(r_corr[:, ti]), (r_corr[:, ti] - loc) / scale, np.nan
        )

    dual = DualSignals(
        z_base=z_base,
        z_ctx=z_ctx,
        r_raw=r_full,
        r_corr=r_corr,
        r_hat_ctx=r_hat,
        analysis_offset=analysis_offset,
        target_models=target_models,
        context_models=context_models,
        alpha=float(alpha),
        feature_names=list(FEATURE_NAMES),
    )
    return dual, meta
