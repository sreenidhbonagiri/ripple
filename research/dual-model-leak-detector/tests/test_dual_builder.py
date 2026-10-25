"""Unit tests for dual network construction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.dual_builder import DualModelSpec, attach_virtual_reservoirs, pressure_to_head
from dual_model.synthetic_networks import build_branched_three_sensor_network


def test_pressure_to_head():
    assert pressure_to_head(30.0, 70.0) == 100.0


def test_attach_virtual_reservoirs_names(tmp_path):
    wn, sensors = build_branched_three_sensor_network()
    spec = DualModelSpec(sensor_nodes=sensors)
    heads = {s: 100.0 for s in sensors}
    wd = attach_virtual_reservoirs(wn, spec, heads=heads, scratch_dir=tmp_path)
    for s in sensors:
        assert spec.vr_name(s) in wd.node_name_list
        assert spec.tcv_name(s) in wd.link_name_list
        tcv = wd.get_link(spec.tcv_name(s))
        assert tcv.link_type == "Valve"
        assert tcv.valve_type == "TCV"
        assert tcv.start_node_name == s
        assert tcv.end_node_name == spec.vr_name(s)


def test_attach_requires_exactly_one_head_source(tmp_path):
    wn, sensors = build_branched_three_sensor_network()
    spec = DualModelSpec(sensor_nodes=sensors)
    with pytest.raises(ValueError):
        attach_virtual_reservoirs(wn, spec, scratch_dir=tmp_path)
    with pytest.raises(ValueError):
        attach_virtual_reservoirs(
            wn,
            spec,
            heads={s: 1.0 for s in sensors},
            head_timeseries={s: [1.0, 2.0] for s in sensors},
            scratch_dir=tmp_path,
        )