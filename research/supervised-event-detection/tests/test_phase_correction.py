"""Phase-correction planning, splits, and distribution gates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulate_phase import PHASE_PERIOD_HOURS, build_phase_scenario_plan
from splits_phase import assign_splits_phase
from verify_phase_distributions import verify_phase_onset_distributions


def test_phase_plan_independent_onset_and_matched_phases():
    specs = build_phase_scenario_plan()
    leaks = [s for s in specs if s.kind == "leak_abrupt"]
    ctrls = [s for s in specs if s.kind.startswith("control")]
    assert len(leaks) == 24
    assert len(ctrls) == 16
    for s in specs:
        assert 0.0 <= s.pattern_phase_offset_hours < PHASE_PERIOD_HOURS
    for s in leaks:
        assert s.leak_start_hour is not None and s.leak_start_hour >= 14.0
    # Matched pairs share phase
    by_pair = {}
    for s in specs:
        if s.pair_id:
            by_pair.setdefault(s.pair_id, []).append(s)
    assert len(by_pair) == 16
    for members in by_pair.values():
        phases = {m.pattern_phase_offset_hours for m in members}
        assert len(phases) == 1
        assert any(m.kind == "leak_abrupt" for m in members)
        assert any(m.kind.startswith("control") for m in members)


def test_splits_keep_pairs_together():
    specs = build_phase_scenario_plan()
    manifest = {
        "scenarios": [
            {"spec": s.__dict__, "ok": True, "npz": f"{s.scenario_id}.npz"}
            for s in specs
        ]
    }
    info = assign_splits_phase(manifest)
    assert info["pairs_colocated"] is True
    # spot-check one pair
    leak = next(s for s in specs if s.pair_id == "pair_000" and s.kind == "leak_abrupt")
    ctrl = next(s for s in specs if s.pair_id == "pair_000" and s.kind.startswith("control"))
    assert info["assignments"][leak.scenario_id] == info["assignments"][ctrl.scenario_id]


def test_distribution_verifier_on_plan():
    specs = build_phase_scenario_plan()
    manifest = {"scenarios": [{"spec": s.__dict__, "ok": True} for s in specs]}
    checks = verify_phase_onset_distributions(manifest)
    assert checks["all_passed"] is True
    assert checks["paired_phases_identical"] is True
