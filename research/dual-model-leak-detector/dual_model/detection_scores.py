"""Causal change scores A/B/C from dual q_v and external inflow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .detection_protocol import EPS_SIGMA, REF_GAP_HOURS, REF_HOURS, REF_MIN_SAMPLES


def _ref_slice(index: pd.DatetimeIndex, t: pd.Timestamp) -> pd.DatetimeIndex:
    end = t - pd.Timedelta(hours=REF_GAP_HOURS)
    start = end - pd.Timedelta(hours=REF_HOURS)
    return index[(index >= start) & (index <= end)]


def score_A_signed_sum_change(qv_m3h: pd.DataFrame) -> pd.Series:
    """Normalized one-sided change in signed total virtual flow."""
    total = qv_m3h.sum(axis=1)
    out = pd.Series(np.nan, index=qv_m3h.index, dtype=float)
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t)
        ref = total.loc[ref_idx]
        ref = ref[np.isfinite(ref)]
        if len(ref) < REF_MIN_SAMPLES or not np.isfinite(total.loc[t]):
            continue
        mu, sig = float(ref.mean()), float(ref.std(ddof=0))
        out.loc[t] = (float(total.loc[t]) - mu) / max(sig, EPS_SIGMA)
    return out


def score_B_vector_change(qv_m3h: pd.DataFrame) -> pd.Series:
    """L2 norm of per-sensor q_v change vs causal ref mean (no sign cancellation)."""
    out = pd.Series(np.nan, index=qv_m3h.index, dtype=float)
    cols = list(qv_m3h.columns)
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t)
        ref = qv_m3h.loc[ref_idx, cols]
        if ref.shape[0] < REF_MIN_SAMPLES:
            continue
        row = qv_m3h.loc[t, cols]
        if not np.isfinite(row.values).all():
            continue
        mu = ref.mean(axis=0)
        # Scale by mean per-sensor ref std so score is dimensionless-ish
        sig = float(ref.std(axis=0, ddof=0).mean())
        delta = row.astype(float) - mu.astype(float)
        out.loc[t] = float(np.linalg.norm(delta.values)) / max(sig, EPS_SIGMA)
    return out


def score_C_inflow_change(flows_m3h: pd.DataFrame) -> pd.Series:
    """Normalized |change| in external inflow p227+p235."""
    q_ext = flows_m3h["p227"].astype(float) + flows_m3h["p235"].astype(float)
    out = pd.Series(np.nan, index=flows_m3h.index, dtype=float)
    for t in flows_m3h.index:
        ref_idx = _ref_slice(flows_m3h.index, t)
        ref = q_ext.loc[ref_idx]
        ref = ref[np.isfinite(ref)]
        if len(ref) < REF_MIN_SAMPLES or not np.isfinite(q_ext.loc[t]):
            continue
        mu, sig = float(ref.mean()), float(ref.std(ddof=0))
        out.loc[t] = abs(float(q_ext.loc[t]) - mu) / max(sig, EPS_SIGMA)
    return out


def score_M_maxabs_local_change(
    qv_m3h: pd.DataFrame,
    *,
    sigma_m3h: pd.Series,
    raw_max_median: float,
    eps_sigma: float = EPS_SIGMA,
) -> pd.Series:
    """Network max |δ_i/σ_i| with training σ_i and empirical max calibration.

    Not equivalent to Method B (L2 / mean rolling σ). See METHOD_M_PROTOCOL.md.
    ``sigma_m3h`` indexed by sensor; ``raw_max_median`` = median SCALE raw max.
    """
    cols = [c for c in qv_m3h.columns if c in sigma_m3h.index and np.isfinite(sigma_m3h[c])]
    out = pd.Series(np.nan, index=qv_m3h.index, dtype=float)
    if not cols:
        return out
    sig = sigma_m3h.reindex(cols).astype(float).clip(lower=eps_sigma)
    cal = float(raw_max_median) if np.isfinite(raw_max_median) and raw_max_median > 1e-6 else 1.0
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t)
        if len(ref_idx) < REF_MIN_SAMPLES:
            continue
        row = qv_m3h.loc[t, cols].astype(float)
        ref = qv_m3h.loc[ref_idx, cols].astype(float)
        # eligible: finite recent + enough finite ref samples
        n_ref = ref.notna().sum(axis=0)
        ok = row.notna() & (n_ref >= REF_MIN_SAMPLES)
        if not bool(ok.any()):
            continue
        mu = ref.loc[:, ok.index[ok]].mean(axis=0)
        delta = row.loc[ok.index[ok]] - mu
        z = (delta / sig.loc[ok.index[ok]]).abs()
        z = z[np.isfinite(z)]
        if len(z) == 0:
            continue
        out.loc[t] = float(z.max()) / cal
    return out


def estimate_method_m_scales(
    qv_m3h: pd.DataFrame,
    scale_index: pd.DatetimeIndex,
    *,
    min_scale_samples: int = 24,
    eps_sigma: float = EPS_SIGMA,
) -> tuple[pd.Series, float, dict]:
    """Training-only σ_i from causal δ_i on SCALE hours; median raw max for calibration."""
    cols = list(qv_m3h.columns)
    # Precompute δ on full series then restrict (causal refs may start before SCALE)
    deltas = pd.DataFrame(np.nan, index=qv_m3h.index, columns=cols, dtype=float)
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t)
        if len(ref_idx) < REF_MIN_SAMPLES:
            continue
        row = qv_m3h.loc[t, cols].astype(float)
        ref = qv_m3h.loc[ref_idx, cols].astype(float)
        n_ref = ref.notna().sum(axis=0)
        ok = row.notna() & (n_ref >= REF_MIN_SAMPLES)
        if not bool(ok.any()):
            continue
        mu = ref.loc[:, ok.index[ok]].mean(axis=0)
        deltas.loc[t, ok.index[ok]] = row.loc[ok.index[ok]] - mu

    scale_idx = scale_index.intersection(deltas.index)
    d_scale = deltas.loc[scale_idx]
    sig_vals = {}
    dropped = []
    for c in cols:
        x = d_scale[c].astype(float)
        x = x[np.isfinite(x)]
        if len(x) < min_scale_samples:
            dropped.append(c)
            continue
        sig_vals[c] = float(max(float(x.std(ddof=0)), eps_sigma))
    sigma = pd.Series(sig_vals, dtype=float)

    # raw max |δ/σ| on SCALE for empirical max calibration
    raw_max = []
    for t in scale_idx:
        row = d_scale.loc[t]
        ok = [c for c in sigma.index if c in row.index and np.isfinite(float(row[c]))]
        if not ok:
            continue
        z = (row[ok].astype(float) / sigma.loc[ok]).abs()
        z = z[np.isfinite(z)]
        if len(z):
            raw_max.append(float(z.max()))
    med = float(np.median(raw_max)) if raw_max else float("nan")
    meta = {
        "n_scale_hours": int(len(scale_idx)),
        "n_sensors_kept": int(len(sigma)),
        "sensors_dropped": dropped,
        "raw_max_median": med,
        "raw_max_p90": float(np.quantile(raw_max, 0.9)) if raw_max else None,
        "n_raw_max": len(raw_max),
    }
    return sigma, med, meta


def build_all_scores(
    qv_m3h: pd.DataFrame,
    flows_m3h: pd.DataFrame,
) -> dict[str, pd.Series]:
    return {
        "A": score_A_signed_sum_change(qv_m3h),
        "B": score_B_vector_change(qv_m3h),
        "C": score_C_inflow_change(flows_m3h),
    }