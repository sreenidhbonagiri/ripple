"""Synthetic-stage checks for H0/H1 hypothesis test (no measured data)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.hypothesis_scenarios import SPLIT_OF, run_scenario
from dual_model.hypothesis_test import HypothesisConfig, candidate_nodes_from_topology


def test_candidates_independent_of_eval_leaks():
    assert candidate_nodes_from_topology("branched3") == ("J1", "J2", "J3")
    assert candidate_nodes_from_topology("pump_tank") == ("J1", "J2")


def test_whole_scenario_splits_cover_all_ids():
    assert set(SPLIT_OF) >= {
        "nl_nominal",
        "leak_nominal_J3",
        "ambiguous_demand_J1",
        "leak_demand_var_J2",
    }
    assert set(SPLIT_OF.values()) == {"train", "dev", "test"}


def test_clear_leak_can_prefer_h1(tmp_path):
    cfg = HypothesisConfig(tau_dev=0.0)
    row = run_scenario("leak_nominal_J3", tmp_path, cfg=cfg, seed=0)
    assert row["has_new_leak"] is True
    # Raw ΔJ should be positive for a clear matched leak (penalty may still gate).
    assert row["hypothesis"]["delta_J"] > 0.0


def test_ambiguous_demand_does_not_force_confident_wrong_proof(tmp_path):
    cfg = HypothesisConfig(tau_dev=0.05)
    row = run_scenario("ambiguous_demand_J1", tmp_path, cfg=cfg, seed=0)
    assert row["ambiguous_by_design"] is True
    assert row["has_new_leak"] is False
    # Must not claim a confirmed leak as the only admissible outcome.
    assert row["hypothesis"]["decision"] in {"inconclusive", "no_new_leak"}


def test_h1_nuisance_bounds_match_config():
    cfg = HypothesisConfig()
    assert cfg.delta_min_m3h == -3.0 and cfg.delta_max_m3h == 3.0
    assert cfg.rho_min < 1.0 < cfg.rho_max
