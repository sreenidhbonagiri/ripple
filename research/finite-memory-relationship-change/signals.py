"""Reuse sibling build_signals fits; compute train-prefix z for past-only scales."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

CUSUM = Path(__file__).resolve().parents[1] / "per-sensor-relationship-cusum"
if str(CUSUM) not in sys.path:
    sys.path.insert(0, str(CUSUM))

from residual import SignalBundle, TargetModel, build_signals  # noqa: E402


def z_from_models(
    pressures_block: np.ndarray,
    target_models: list[TargetModel],
    n_refs: int,
) -> np.ndarray:
    """Apply frozen pair loc/scale medians on a pressure block (train or analysis)."""
    n_t, n_s = pressures_block.shape
    z = np.full((n_t, n_s), np.nan, dtype=np.float64)
    n_ref_min = max(1, (n_refs + 1) // 2)
    for tm in target_models:
        i = tm.target
        if not tm.refs:
            continue
        cols = []
        for j, pm in tm.pairs.items():
            pj = pressures_block[:, j]
            pi = pressures_block[:, i]
            e = (pm.intercept + pm.slope * pj) - pi
            tilde = (e - pm.loc) / pm.scale
            ok = np.isfinite(pj) & np.isfinite(pi) & np.isfinite(tilde)
            cols.append(np.where(ok, tilde, np.nan))
        if not cols:
            continue
        stack = np.vstack(cols)
        valid_count = np.sum(np.isfinite(stack), axis=0)
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack, axis=0)
        z[:, i] = np.where(valid_count >= n_ref_min, med, np.nan)
    return z


def build_period_signals(
    pressures: np.ndarray,
    *,
    interval_start: int,
    interval_end: int,
    train_days: int = 14,
    n_refs: int = 3,
) -> tuple[SignalBundle, np.ndarray, int, int]:
    """Returns (analysis SignalBundle, train_z, train_start, train_end)."""
    steps_per_day = 288
    train_steps = train_days * steps_per_day
    train_start = interval_start
    train_end = min(interval_start + train_steps, interval_end)
    sig = build_signals(
        pressures,
        interval_start=interval_start,
        interval_end=interval_end,
        train_days=train_days,
        n_refs=n_refs,
    )
    train_z = z_from_models(
        pressures[train_start:train_end],
        sig.target_models,
        n_refs,
    )
    return sig, train_z, train_start, train_end
