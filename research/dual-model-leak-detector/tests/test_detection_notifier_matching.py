"""Unit tests for detection notifier, scores, and matching helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_eval import select_tau_on_dev  # noqa: E402
from dual_model.detection_protocol import GATE_RECALL, GATE_UNMATCHED_PER_WEEK, TAU_GRID  # noqa: E402
from dual_model.detection_scores import (  # noqa: E402
    score_A_signed_sum_change,
    score_B_vector_change,
    score_C_inflow_change,
)
from dual_model.notifier import episodes_from_scores  # noqa: E402


def test_notifier_recovery_and_nan():
    s = np.array([0.0, 3.0, 3.0, 0.1, 0.1, 0.1, np.nan, 3.0, 0.0], dtype=float)
    eps = episodes_from_scores(s, tau=2.0, recover_steps=1)
    assert len(eps) >= 1
    assert eps[0].notify_idx == 1
    # After recovery below tau/2=1, second notify at index 7
    assert any(ep.notify_idx == 7 for ep in eps)


def test_score_B_no_cancellation():
    idx = pd.date_range("2018-02-01", periods=40, freq="h")
    # Opposite-signed sensor changes that cancel in the sum but not in L2
    qv = pd.DataFrame(
        {
            "n1": np.concatenate([np.zeros(30), np.full(10, 5.0)]),
            "n2": np.concatenate([np.zeros(30), np.full(10, -5.0)]),
        },
        index=idx,
    )
    a = score_A_signed_sum_change(qv)
    b = score_B_vector_change(qv)
    # Late times: sum change ~0 → |A| small; B retains spatial energy
    assert abs(a.iloc[-1]) < 1.0
    assert b.iloc[-1] > abs(a.iloc[-1]) + 0.5
    assert b.iloc[-1] > 1.0


def test_score_C_inflow():
    idx = pd.date_range("2018-02-01", periods=40, freq="h")
    flows = pd.DataFrame(
        {
            "p227": np.concatenate([np.full(30, 50.0), np.full(10, 80.0)]),
            "p235": np.full(40, 50.0),
        },
        index=idx,
    )
    c = score_C_inflow_change(flows)
    assert c.iloc[-1] > 1.0


def test_select_tau_pass_and_fail():
    # Fabricate DEV summaries
    by_tau = {}
    for t in TAU_GRID:
        by_tau[t] = {
            "abrupt_6h_recall": 1.0 if t <= 2.0 else 0.0,
            "unmatched_per_week": 1.0 if t >= 1.5 else 10.0,
            "gate_pass": (1.0 if t <= 2.0 else 0.0) >= GATE_RECALL
            and (1.0 if t >= 1.5 else 10.0) <= GATE_UNMATCHED_PER_WEEK,
            "occupancy": 0.1,
            "n_eligible_abrupt": 3,
            "n_hit": 3 if t <= 2.0 else 0,
        }
    sel = select_tau_on_dev(by_tau)
    assert sel["selection_passed"] is True
    assert sel["tau"] == 2.0  # largest passing

    for t in TAU_GRID:
        by_tau[t]["gate_pass"] = False
        by_tau[t]["abrupt_6h_recall"] = 0.5
        by_tau[t]["unmatched_per_week"] = 5.0
    sel2 = select_tau_on_dev(by_tau)
    assert sel2["selection_passed"] is False
    assert sel2["fallback"] is True


def test_missing_ref_yields_nan_score():
    idx = pd.date_range("2018-02-01", periods=5, freq="h")
    qv = pd.DataFrame({"n1": [1.0, 1.0, 1.0, 1.0, 5.0]}, index=idx)
    a = score_A_signed_sum_change(qv)
    # Too short for 24h ref → all NaN
    assert not np.isfinite(a).any()