"""Multiscale Method M: joint max |δ|/σ over sensors × timescales (one stream).

See outputs/.../method_m_multiscale/METHOD_M_MULTISCALE_PROTOCOL.md.
Does not alter frozen single-scale Method M helpers in detection_scores.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .detection_protocol import EPS_SIGMA, REF_GAP_HOURS, REF_MIN_SAMPLES
from .detection_scores import score_M_maxabs_local_change, estimate_method_m_scales

# Registered timescale set (ref hours). Medium == frozen Method M baseline.
TIMESCALE_REF_HOURS: dict[str, int] = {
    # 12h = shortest ref that still admits REF_MIN_SAMPLES=12 on an hourly grid.
    "short": 12,
    "medium": 24,  # baseline Method M
    "long": 72,
}
BASELINE_TIMESCALE = "medium"
SCALE_START = pd.Timestamp("2018-01-09 01:00:00")
SCALE_END = pd.Timestamp("2018-01-21 23:00:00")


@dataclass(frozen=True)
class TimescaleScales:
    name: str
    ref_hours: int
    sigma_m3h: pd.Series
    raw_max_median: float
    meta: dict


def _ref_slice(
    index: pd.DatetimeIndex,
    t: pd.Timestamp,
    *,
    ref_hours: int,
    gap_hours: int = REF_GAP_HOURS,
) -> pd.DatetimeIndex:
    end = t - pd.Timedelta(hours=gap_hours)
    start = end - pd.Timedelta(hours=ref_hours)
    return index[(index >= start) & (index <= end)]


def causal_deltas(
    qv_m3h: pd.DataFrame,
    *,
    ref_hours: int,
    gap_hours: int = REF_GAP_HOURS,
    min_ref: int = REF_MIN_SAMPLES,
) -> pd.DataFrame:
    """Causal δ_i(t) = q_v,i(t) − mean(ref) for a fixed reference length."""
    cols = list(qv_m3h.columns)
    out = pd.DataFrame(np.nan, index=qv_m3h.index, columns=cols, dtype=float)
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t, ref_hours=ref_hours, gap_hours=gap_hours)
        if len(ref_idx) < min_ref:
            continue
        row = qv_m3h.loc[t, cols].astype(float)
        ref = qv_m3h.loc[ref_idx, cols].astype(float)
        n_ref = ref.notna().sum(axis=0)
        ok = row.notna() & (n_ref >= min_ref)
        if not bool(ok.any()):
            continue
        use = ok.index[ok]
        mu = ref.loc[:, use].mean(axis=0)
        out.loc[t, use] = row.loc[use] - mu
    return out


def estimate_scales_for_ref(
    qv_m3h: pd.DataFrame,
    *,
    ref_hours: int,
    scale_index: pd.DatetimeIndex,
    min_scale_samples: int = 24,
    eps_sigma: float = EPS_SIGMA,
) -> tuple[pd.Series, float, dict]:
    """Training-only σ_i and SCALE median raw max for one reference length."""
    deltas = causal_deltas(qv_m3h, ref_hours=ref_hours)
    scale_idx = scale_index.intersection(deltas.index)
    d_scale = deltas.loc[scale_idx]
    sig_vals: dict[str, float] = {}
    dropped: list[str] = []
    for c in deltas.columns:
        x = d_scale[c].astype(float)
        x = x[np.isfinite(x)]
        if len(x) < min_scale_samples:
            dropped.append(c)
            continue
        sig_vals[c] = float(max(float(x.std(ddof=0)), eps_sigma))
    sigma = pd.Series(sig_vals, dtype=float)

    raw_max: list[float] = []
    for t in scale_idx:
        row = d_scale.loc[t]
        ok = [c for c in sigma.index if np.isfinite(float(row[c]))]
        if not ok:
            continue
        z = (row[ok].astype(float) / sigma.loc[ok]).abs()
        z = z[np.isfinite(z)]
        if len(z):
            raw_max.append(float(z.max()))
    med = float(np.median(raw_max)) if raw_max else float("nan")
    meta = {
        "ref_hours": int(ref_hours),
        "n_scale_hours": int(len(scale_idx)),
        "n_sensors_kept": int(len(sigma)),
        "sensors_dropped": dropped,
        "raw_max_median": med,
        "n_raw_max": len(raw_max),
    }
    return sigma, med, meta


def estimate_all_timescale_scales(
    qv_m3h: pd.DataFrame,
    scale_index: pd.DatetimeIndex | None = None,
) -> dict[str, TimescaleScales]:
    if scale_index is None:
        scale_index = qv_m3h.index[(qv_m3h.index >= SCALE_START) & (qv_m3h.index <= SCALE_END)]
    out: dict[str, TimescaleScales] = {}
    for name, ref_h in TIMESCALE_REF_HOURS.items():
        sigma, med, meta = estimate_scales_for_ref(
            qv_m3h, ref_hours=ref_h, scale_index=scale_index
        )
        out[name] = TimescaleScales(
            name=name, ref_hours=ref_h, sigma_m3h=sigma, raw_max_median=med, meta=meta
        )
    return out


def score_method_m_single_timescale(
    qv_m3h: pd.DataFrame,
    *,
    ref_hours: int,
    sigma_m3h: pd.Series,
    raw_max_median: float,
    eps_sigma: float = EPS_SIGMA,
) -> pd.Series:
    """Per-timescale max |δ/σ| / median (generalizes frozen Method M ref length)."""
    cols = [c for c in qv_m3h.columns if c in sigma_m3h.index and np.isfinite(sigma_m3h[c])]
    out = pd.Series(np.nan, index=qv_m3h.index, dtype=float)
    if not cols:
        return out
    sig = sigma_m3h.reindex(cols).astype(float).clip(lower=eps_sigma)
    cal = float(raw_max_median) if np.isfinite(raw_max_median) and raw_max_median > 1e-6 else 1.0
    for t in qv_m3h.index:
        ref_idx = _ref_slice(qv_m3h.index, t, ref_hours=ref_hours)
        if len(ref_idx) < REF_MIN_SAMPLES:
            continue
        row = qv_m3h.loc[t, cols].astype(float)
        ref = qv_m3h.loc[ref_idx, cols].astype(float)
        n_ref = ref.notna().sum(axis=0)
        ok = row.notna() & (n_ref >= REF_MIN_SAMPLES)
        if not bool(ok.any()):
            continue
        use = ok.index[ok]
        mu = ref.loc[:, use].mean(axis=0)
        delta = row.loc[use] - mu
        z = (delta / sig.loc[use]).abs()
        z = z[np.isfinite(z)]
        if len(z) == 0:
            continue
        out.loc[t] = float(z.max()) / cal
    return out


def score_method_m_multiscale_combined(
    qv_m3h: pd.DataFrame,
    scales: dict[str, TimescaleScales],
    *,
    eps_sigma: float = EPS_SIGMA,
) -> tuple[pd.Series, float, dict]:
    """One stream: max |δ_{i,w}/σ_{i,w}| over sensors and timescales, SCALE-calibrated.

    Returns (s_MS, combined_raw_max_median, meta).
    """
    per_scale_raw: dict[str, pd.Series] = {}
    for name, sc in scales.items():
        # raw_max_median=1 → uncalibrated max_i |δ/σ| for this timescale
        per_scale_raw[name] = score_method_m_single_timescale(
            qv_m3h,
            ref_hours=sc.ref_hours,
            sigma_m3h=sc.sigma_m3h,
            raw_max_median=1.0,
            eps_sigma=eps_sigma,
        )
    raw_df = pd.DataFrame(per_scale_raw)
    raw = raw_df.max(axis=1, skipna=True)
    # Ties: first timescale in column order among equals; all-NaN rows → NA
    winner = pd.Series(pd.NA, index=raw_df.index, dtype=object)
    finite_any = raw_df.notna().any(axis=1)
    if bool(finite_any.any()):
        winner.loc[finite_any] = raw_df.loc[finite_any].idxmax(axis=1)

    scale_idx = raw.index[(raw.index >= SCALE_START) & (raw.index <= SCALE_END)]
    scale_vals = raw.loc[scale_idx]
    scale_vals = scale_vals[np.isfinite(scale_vals)]
    med = float(scale_vals.median()) if len(scale_vals) else float("nan")
    cal = med if np.isfinite(med) and med > 1e-6 else 1.0
    s_ms = raw / cal
    win_scale = winner.loc[scale_idx].dropna()
    win_counts = {k: int((win_scale == k).sum()) for k in scales}
    meta = {
        "combined_raw_max_median": med,
        "n_scale_raw": int(len(scale_vals)),
        "timescales": {k: v.meta for k, v in scales.items()},
        "scale_period_winner_counts": win_counts,
        "calibration": "joint_max_abs_z_over_sensor_and_timescale_div_scale_median",
        "not_independent_union": True,
    }
    return s_ms, med, meta


def reproduce_baseline_method_m(
    qv_m3h: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, float, dict]:
    """Exact frozen Method M path (REF=24) for baseline comparison."""
    scale_idx = qv_m3h.index[(qv_m3h.index >= SCALE_START) & (qv_m3h.index <= SCALE_END)]
    sigma, med, meta = estimate_method_m_scales(qv_m3h, scale_idx)
    s = score_M_maxabs_local_change(qv_m3h, sigma_m3h=sigma, raw_max_median=med)
    return s, sigma, med, meta
