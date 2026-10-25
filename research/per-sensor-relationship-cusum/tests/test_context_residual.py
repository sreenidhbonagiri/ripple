"""Causal / unit sanity checks for context residual correction."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_residual import (  # noqa: E402
    FEATURE_NAMES,
    build_context_features,
    fit_ridge,
    predict_ridge,
)
from residual import TargetModel, PairModel  # noqa: E402
from context_residual import aggregate_raw_residuals  # noqa: E402


def test_context_features_are_causal_tank_lag():
    t = 100
    timestamps = np.arange("2018-01-01", "2018-01-01T08:20", dtype="datetime64[m]")
    assert len(timestamps) >= t
    timestamps = timestamps[:t]
    pump = np.linspace(0, 50, t)
    tank = np.linspace(10, 12, t)
    X = build_context_features(timestamps, pump, tank, 10, 50)
    assert X.shape == (40, len(FEATURE_NAMES))
    # d_tank at local 0 uses absolute start-1
    assert np.isfinite(X[0, FEATURE_NAMES.index("d_tank_T1")])
    # No NaNs in calendar / pump columns when inputs finite
    assert np.all(np.isfinite(X[:, :5]))


def test_features_do_not_use_future_tank():
    timestamps = np.arange("2018-03-01", "2018-03-02", dtype="datetime64[m]")[:50]
    pump = np.ones(50)
    tank = np.arange(50, dtype=np.float64)
    X = build_context_features(timestamps, pump, tank, 5, 15)
    # d_tank[local] = tank[abs]-tank[abs-1]; for abs=5..14 → diffs 1
    d = X[:, FEATURE_NAMES.index("d_tank_T1")]
    np.testing.assert_allclose(d, 1.0)


def test_ridge_predict_matches_fit_on_noise_free():
    rng = np.random.default_rng(0)
    n = 500
    X = rng.normal(size=(n, len(FEATURE_NAMES)))
    beta_true = np.array([0.5, 0.2, -0.1, 0.0, 0.3, 0.05, -0.02, 0.01])  # intercept+7
    y = beta_true[0] + X @ beta_true[1:]
    beta, n_fit, rmse = fit_ridge(X, y, alpha=1e-6)
    assert n_fit == n
    pred = predict_ridge(X, beta)
    assert float(np.sqrt(np.mean((pred - y) ** 2))) < 1e-3


def test_aggregate_residual_median_units_smoke():
    t, s = 200, 4
    p = 40 + np.random.default_rng(1).normal(0, 0.05, size=(t, s)).astype(np.float32)
    # Fake models: identity-ish
    models = []
    for i in range(s):
        refs = [j for j in range(s) if j != i][:2]
        pairs = {
            j: PairModel(0.0, 1.0, 0.1, 0.05, 100, 0.0, 0.05 * 1.4826) for j in refs
        }
        models.append(TargetModel(i, refs, pairs))
    r = aggregate_raw_residuals(p, models, 50, 150)
    assert r.shape == (100, s)
    assert np.nanmedian(np.abs(r)) < 1.0  # meters-scale small for near copies
