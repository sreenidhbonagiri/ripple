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


def build_all_scores(
    qv_m3h: pd.DataFrame,
    flows_m3h: pd.DataFrame,
) -> dict[str, pd.Series]:
    return {
        "A": score_A_signed_sum_change(qv_m3h),
        "B": score_B_vector_change(qv_m3h),
        "C": score_C_inflow_change(flows_m3h),
    }