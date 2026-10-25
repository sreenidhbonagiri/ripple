"""Train-only dependence-aware scale for median-difference scores.

See DESIGN.md §2.3: AR(1) n_eff is an approximation; sigma is not a calibrated
SE for median differences; tau is heuristic.
"""

from __future__ import annotations

import numpy as np

MAD_SCALE = 1.4826
SIGMA_MIN = 1e-6
RHO_MAX = 0.95


def mad(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = float(np.median(x))
    return float(np.median(np.abs(x - med)))


def lag1_autocorr(z: np.ndarray) -> float:
    """Lag-1 sample correlation on consecutive finite pairs (past series only)."""
    z = np.asarray(z, dtype=np.float64)
    if z.size < 3:
        return 0.0
    a = z[:-1]
    b = z[1:]
    m = np.isfinite(a) & np.isfinite(b)
    if int(m.sum()) < 8:
        return 0.0
    a = a[m]
    b = b[m]
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
    if denom < 1e-18:
        return 0.0
    rho = float(np.sum(a * b) / denom)
    return float(np.clip(rho, 0.0, RHO_MAX))


def n_eff(n: int, rho: float) -> float:
    """AR(1) mean-variance effective size approximation (not median-specific)."""
    rho = float(np.clip(rho, 0.0, RHO_MAX))
    return max(2.0, float(n) * (1.0 - rho) / (1.0 + rho))


def sigma_from_train(z_train: np.ndarray, n_q: int, n_r: int) -> tuple[float, dict]:
    """Frozen per-target scale from training z only.

    Returns (sigma, meta). sigma is NaN if ineligible.
    """
    z_train = np.asarray(z_train, dtype=np.float64)
    mad_i = mad(z_train)
    rho = lag1_autocorr(z_train)
    meta = {
        "mad": mad_i,
        "rho_lag1": rho,
        "n_eff_q": n_eff(n_q, rho),
        "n_eff_r": n_eff(n_r, rho),
        "n_train_finite": int(np.isfinite(z_train).sum()),
    }
    if not np.isfinite(mad_i) or mad_i <= 0:
        meta["eligible"] = False
        meta["reason"] = "nonpositive_mad"
        return float("nan"), meta
    ne_q = meta["n_eff_q"]
    ne_r = meta["n_eff_r"]
    sigma = MAD_SCALE * mad_i * float(np.sqrt(1.0 / ne_q + 1.0 / ne_r))
    meta["sigma"] = sigma
    if not np.isfinite(sigma) or sigma < SIGMA_MIN:
        meta["eligible"] = False
        meta["reason"] = "sigma_too_small"
        return float("nan"), meta
    meta["eligible"] = True
    meta["reason"] = "ok"
    return float(sigma), meta
