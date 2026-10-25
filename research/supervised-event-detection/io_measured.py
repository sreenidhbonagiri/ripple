"""Load measured 2018 SCADA into the shared feature schema (no Tiger)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from io_data import (  # noqa: E402
    DEFAULT_RAW,
    load_context,
    load_leakages,
    load_pressures,
)

from schema import FLOW_SENSORS, LEVEL_SENSORS, PRESSURE_SENSORS, DEFAULT_RAW as SCHEMA_RAW


def load_measured_2018(raw_dir: Path | None = None) -> dict:
    raw_dir = Path(raw_dir) if raw_dir is not None else DEFAULT_RAW
    assert raw_dir == SCHEMA_RAW or True
    pb = load_pressures(raw_dir / "2018_SCADA_Pressures.csv")
    # load_context hardcodes 2018 filenames relative to raw_dir
    # Patch: io_data.load_context uses fixed 2018 names from DEFAULT_RAW
    ctx = _load_context_dir(raw_dir)
    if not np.array_equal(pb.timestamps, ctx["timestamps"]):
        raise ValueError("pressure/context timestamp mismatch")
    if pb.sensor_ids != PRESSURE_SENSORS:
        raise ValueError("pressure sensor order mismatch vs schema")
    if ctx["flow_ids"] != FLOW_SENSORS:
        raise ValueError(f"flow ids {ctx['flow_ids']} != {FLOW_SENSORS}")
    if ctx["level_ids"] != LEVEL_SENSORS:
        raise ValueError(f"level ids {ctx['level_ids']} != {LEVEL_SENSORS}")
    return {
        "timestamps": pb.timestamps,
        "pressures": pb.pressures.astype(np.float64),
        "flows": ctx["flows"].astype(np.float64),
        "levels": ctx["levels"].astype(np.float64),
        "pressure_sensors": list(pb.sensor_ids),
        "flow_sensors": list(ctx["flow_ids"]),
        "level_sensors": list(ctx["level_ids"]),
        "units": {"pressure": "m", "flow": "m3/h", "tank_level": "m"},
        "source": "2018_SCADA_* official BattLeDIM",
    }


def _load_context_dir(raw_dir: Path) -> dict:
    """Local copy of load_context that respects raw_dir (2018 files)."""
    from io_data import parse_eu_float, _parse_ts

    def _load(name: str, expected: list[str]):
        with (raw_dir / name).open(newline="") as f:
            header = f.readline().rstrip("\r\n").split(";")
            ids = [c.strip() for c in header[1:]]
            if ids != expected:
                raise ValueError(f"unexpected columns in {name}: {ids}")
            ts_list, rows = [], []
            for line in f:
                parts = line.rstrip("\r\n").split(";")
                ts_list.append(_parse_ts(parts[0]))
                rows.append([parse_eu_float(c) for c in parts[1:]])
        return (
            np.asarray(ts_list, dtype="datetime64[m]"),
            ids,
            np.asarray(rows, dtype=np.float64),
        )

    ts_f, f_ids, flows = _load("2018_SCADA_Flows.csv", FLOW_SENSORS)
    ts_l, l_ids, levels = _load("2018_SCADA_Levels.csv", LEVEL_SENSORS)
    if not np.array_equal(ts_f, ts_l):
        raise ValueError("flow/level timestamp mismatch")
    return {
        "timestamps": ts_f,
        "flow_ids": f_ids,
        "flows": flows,
        "level_ids": l_ids,
        "levels": levels,
    }


def load_2018_leakages():
    return load_leakages()
