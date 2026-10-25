"""Implementation tests for causal features — run before fitting."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from features import build_feature_matrix, feature_manifest, feature_names
from schema import (
    FLOW_SENSORS,
    LEVEL_SENSORS,
    PRESSURE_SENSORS,
    FEATURE_CONFIG,
    STEP_SECONDS,
)


def _toy(T=100, seed=0):
    rng = np.random.default_rng(seed)
    P = 30 + rng.normal(0, 0.2, size=(T, len(PRESSURE_SENSORS)))
    F = rng.uniform(0, 50, size=(T, len(FLOW_SENSORS)))
    L = 3 + rng.normal(0, 0.05, size=(T, len(LEVEL_SENSORS)))
    return P, F, L


def test_feature_dim_stable():
    names = feature_names()
    P, F, L = _toy()
    X, n2 = build_feature_matrix(P, F, L)
    assert n2 == names
    assert X.shape == (P.shape[0], len(names))
    man = feature_manifest()
    assert man["n_features"] == len(names)
    assert "true_leak_pipe_id" in str(man["forbidden"])


def test_no_future_leakage_in_deltas():
    P, F, L = _toy(T=80)
    # Spike only at t=50 on pressures
    P = P.copy()
    P[50, :] += 5.0
    X, names = build_feature_matrix(P, F, L)
    # At t=49, 5-min delta (lag=1) must not see the spike
    i_d1_max = names.index("Pd_d1_max_abs")
    assert X[49, i_d1_max] < 1.0 or not np.isfinite(X[49, i_d1_max])
    # At t=50, lag-1 delta should reflect spike
    assert X[50, i_d1_max] > 3.0


def test_warm_up_nans_for_long_lag():
    P, F, L = _toy(T=30)
    X, names = build_feature_matrix(P, F, L)
    i = names.index("Pd_d24_median")
    assert np.all(~np.isfinite(X[:24, i]))
    assert np.isfinite(X[24, i])


def test_topneg_has_no_sensor_id_columns():
    names = feature_names()
    assert not any("n644" in n or "pipe" in n.lower() for n in names)
    man = feature_manifest()
    assert man["pressure_sensors"] == PRESSURE_SENSORS


def test_flow_level_column_counts():
    P, F, L = _toy()
    with pytest.raises(ValueError):
        build_feature_matrix(P, F[:, :2], L)
    with pytest.raises(ValueError):
        build_feature_matrix(P[:, :10], F, L)


def test_units_documented():
    man = feature_manifest()
    assert man["units"]["pressure"] == "m"
    assert man["units"]["flow"] == "m3/h"
    assert man["units"]["tank_level"] == "m"
    assert STEP_SECONDS == 300
