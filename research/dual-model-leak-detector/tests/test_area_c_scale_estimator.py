"""Regression tests for Area-C unmeasured-scale estimator (signed mean)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.demand_calibration import (  # noqa: E402
    AREA_C_SCALE_BOUNDS,
    estimate_area_c_unmeasured_scale,
)


def test_negative_noisy_samples_positive_signed_mean():
    """Negatives allowed in the sample; signed mean stays positive → interior scale."""
    rng = np.random.default_rng(0)
    # True unmeasured demand ≈ 2 m³/h; base = 2 → scale ≈ 1.
    # Add noise that produces many negative residuals.
    n = 500
    true = 2.0
    noise = rng.normal(0.0, 3.0, size=n)  # often |noise| > true
    residual = true + noise
    assert (residual < 0).mean() > 0.2
    assert residual.mean() > 0.5  # signed mean still positive

    q_c = pd.Series(10.0 + residual)
    amr = pd.Series(np.full(n, 10.0))
    out = estimate_area_c_unmeasured_scale(q_c, amr, base_unmeasured_m3h=2.0)
    assert out["mean_residual_signed_m3h"] == pytest.approx(float(residual.mean()), rel=1e-12)
    assert out["raw_scale"] == pytest.approx(float(residual.mean()) / 2.0, rel=1e-12)
    assert out["physically_inconsistent"] is False
    assert out["bound_hit"] == "interior"
    assert AREA_C_SCALE_BOUNDS[0] <= out["scale"] <= AREA_C_SCALE_BOUNDS[1]


def test_old_clipping_induced_upward_bias():
    """Document that clip-before-mean inflates scale vs signed mean (the bug)."""
    # Construct FIT-like noise: signed mean ~1.7, ~32% negative (matches audit).
    residual = np.array([1.7] * 68 + [-3.0] * 32, dtype=float)
    assert (residual < 0).mean() == pytest.approx(0.32)
    assert residual.mean() == pytest.approx(0.196)  # 1.7*0.68 - 3*0.32
    q_c = pd.Series(20.0 + residual)
    amr = pd.Series(np.full(len(residual), 20.0))
    base = 1.84
    out = estimate_area_c_unmeasured_scale(q_c, amr, base_unmeasured_m3h=base)

    signed = out["mean_residual_signed_m3h"]
    legacy = out["legacy_clip_before_mean_residual_m3h"]
    # Clip-before-mean zeros the -3s → mean = 1.7*0.68 = 1.156 ≫ signed 0.196
    assert legacy == pytest.approx(1.7 * 0.68)
    assert legacy > signed + 0.5
    assert out["legacy_raw_scale_if_clip_before_mean"] > out["raw_scale"] + 0.3
    assert out["raw_scale"] == pytest.approx(signed / base, rel=1e-12)
    assert out["bound_hit"] == "lower"  # signed raw ≪ 0.5 → hits lower, not upper
    # Legacy inflated raw would be much larger (the superseded ~2.8 failure mode).
    assert out["legacy_raw_scale_if_clip_before_mean"] > 0.5


def test_missing_data_alignment():
    """NaNs are dropped under an identical mask; remaining pairs drive the mean."""
    idx = pd.date_range("2018-01-01", periods=6, freq="5min")
    q_c = pd.Series([10.0, np.nan, 12.0, 11.0, 13.0, np.nan], index=idx)
    amr = pd.Series([9.0, 8.0, np.nan, 10.0, 11.0, 7.0], index=idx)
    # Valid pairs: t0 (10-9=1), t3 (11-10=1), t4 (13-11=2) → mean 4/3
    out = estimate_area_c_unmeasured_scale(q_c, amr, base_unmeasured_m3h=1.0)
    assert out["n_timestamps_total"] == 6
    assert out["n_timestamps_used"] == 3
    assert out["mean_residual_signed_m3h"] == pytest.approx(4.0 / 3.0)
    assert out["raw_scale"] == pytest.approx(4.0 / 3.0)
    assert out["bound_hit"] == "interior"
    assert out["physically_inconsistent"] is False


def test_negative_aggregate_requires_explicit_diagnostic():
    """Signed mean residual ≤ 0 → physically_inconsistent; bounds unchanged."""
    q_c = pd.Series([5.0, 6.0, 4.0, 5.5])
    amr = pd.Series([8.0, 9.0, 7.0, 8.5])  # AMR always above Q_C
    out = estimate_area_c_unmeasured_scale(q_c, amr, base_unmeasured_m3h=2.0)
    assert out["mean_residual_signed_m3h"] < 0
    assert out["raw_scale"] < 0
    assert out["physically_inconsistent"] is True
    assert out["inconsistency_reason"] == "nonpositive_signed_mean_residual"
    # Bounds not widened: clipped to lower bound 0.5
    assert out["scale"] == AREA_C_SCALE_BOUNDS[0]
    assert out["bound_hit"] == "lower"
    assert out["bounds"] == list(AREA_C_SCALE_BOUNDS)