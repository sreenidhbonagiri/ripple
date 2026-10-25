"""Mechanism tests: when virtual flows do / do not indicate leaks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.scenarios import (
    scenario_demand_change_matched,
    scenario_demand_mismatch,
    scenario_known_leak,
    scenario_no_leak_correct,
    scenario_pump_tank_transition,
    scenario_roughness_mismatch,
    scenario_sensor_datum_mismatch,
)


def test_no_leak_correct(tmp_path):
    r = scenario_no_leak_correct(tmp_path)
    assert r["passed"]


def test_known_leak_recovers_discharge_and_locus(tmp_path):
    r = scenario_known_leak(tmp_path, leak_node="J3", leak_m3h=5.0)
    assert r["passed"]
    assert abs(r["result"]["sum_m3h"] - 5.0) < 0.1
    assert r["dominant_sensor"] == "J3"


def test_matched_demand_change_no_false_leak(tmp_path):
    assert scenario_demand_change_matched(tmp_path)["passed"]


def test_demand_mismatch_confounds(tmp_path):
    r = scenario_demand_mismatch(tmp_path)
    assert r["passed"]
    assert r["distinguishes_leak"] is False
    assert r["confounder"] is True


def test_roughness_mismatch_confounds(tmp_path):
    r = scenario_roughness_mismatch(tmp_path)
    assert r["passed"]
    assert r["distinguishes_leak"] is False


def test_sensor_datum_mismatch_confounds(tmp_path):
    r = scenario_sensor_datum_mismatch(tmp_path)
    assert r["passed"]
    assert r["distinguishes_leak"] is False


def test_pump_tank_transition_matched(tmp_path):
    r = scenario_pump_tank_transition(tmp_path)
    assert r["passed"], r