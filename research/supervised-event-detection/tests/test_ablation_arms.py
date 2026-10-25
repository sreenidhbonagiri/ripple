"""Registered change-only ablation feature lists."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation_arms import (
    ARM_B_REMOVED,
    arm_a_names,
    arm_b_names,
    arm_registry,
    subset_X,
)
from features import feature_names
import numpy as np


def test_arm_a_is_full_53():
    assert arm_a_names() == feature_names()
    assert len(arm_a_names()) == 53


def test_arm_b_removes_exactly_registered_absolutes():
    a = set(arm_a_names())
    b = arm_b_names()
    removed = set(ARM_B_REMOVED)
    assert removed == {
        "P_median",
        "P_p10",
        "P_p90",
        "P_max",
        "P_min",
        "F_p227",
        "F_p235",
        "F_PUMP_1",
        "L_T1",
        "pump1_on",
    }
    assert set(b) == a - removed
    assert len(b) == 43
    # Retained change features present
    for n in (
        "Pd_d1_min",
        "Fd_PUMP_1_d24",
        "Ld_T1_d1",
        "P_spread_p90_p10",
    ):
        assert n in b
    # Removed absents
    for n in ARM_B_REMOVED:
        assert n not in b


def test_no_new_feature_names_invented():
    assert set(arm_b_names()).issubset(set(feature_names()))
    reg = arm_registry()
    assert reg["arm_A"]["n_features"] == 53
    assert reg["arm_B"]["n_features"] == 43


def test_subset_preserves_column_order():
    names = feature_names()
    X = np.arange(len(names) * 2, dtype=np.float64).reshape(2, len(names))
    keep = arm_b_names()
    Xs = subset_X(X, names, keep)
    assert Xs.shape == (2, len(keep))
    assert Xs.flags["C_CONTIGUOUS"]
    for j, n in enumerate(keep):
        assert np.allclose(Xs[:, j], X[:, names.index(n)])


def test_arm_a_subset_matches_full_matrix_values_and_layout():
    names = feature_names()
    rng = np.random.default_rng(0)
    X = rng.normal(size=(20, len(names)))
    Xs = subset_X(X, names, arm_a_names())
    assert np.array_equal(Xs, X)
    assert Xs.flags["C_CONTIGUOUS"]
