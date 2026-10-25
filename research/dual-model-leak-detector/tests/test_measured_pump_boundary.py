"""Unit + synthetic checks for measured PUMP_1 internal-transfer boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.pump_boundary import prepare_pump_series_causal  # noqa: E402
from dual_model.scenarios_measured_pump import (  # noqa: E402
    run_all_measured_pump_scenarios,
    scenario_leak_coincident_transition_measured,
    scenario_leak_stable_measured,
    scenario_matched_transition_measured,
    scenario_noisy_missing_pump_measured,
)


def test_prepare_pump_series_causal_no_lookahead():
    prep = prepare_pump_series_causal([10.0, float("nan"), 12.0, float("nan")])
    assert prep.values_m3h == [10.0, 10.0, 12.0, 12.0]
    assert prep.n_ffill == 2
    assert prep.n_zero_impute == 0
    # Leading NaN → zero impute
    prep2 = prepare_pump_series_causal([float("nan"), 5.0])
    assert prep2.values_m3h == [0.0, 5.0]
    assert prep2.n_zero_impute == 1


def test_matched_transition(tmp_path):
    r = scenario_matched_transition_measured(tmp_path)
    assert r["passed"], r


def test_leak_stable(tmp_path):
    r = scenario_leak_stable_measured(tmp_path)
    assert r["passed"], r


def test_leak_coincident_transition(tmp_path):
    r = scenario_leak_coincident_transition_measured(tmp_path)
    assert r["passed"], r


def test_noisy_missing(tmp_path):
    r = scenario_noisy_missing_pump_measured(tmp_path)
    assert r["passed"], r


def test_all_scenarios_report(tmp_path):
    rows = run_all_measured_pump_scenarios(tmp_path)
    assert len(rows) == 4
    assert all(r["passed"] for r in rows), rows
