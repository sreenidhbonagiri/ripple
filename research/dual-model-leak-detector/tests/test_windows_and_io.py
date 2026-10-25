"""Stage-3 window registry and SCADA I/O smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.windows import FIT_W1, VAL_WINDOWS
from dual_model.scada_io import RAW, load_pressures_2018


def test_fit_precedes_first_leak_and_vals_are_later():
    assert FIT_W1.start.startswith("2018-01-01")
    assert FIT_W1.end.startswith("2018-01-07")
    for w in VAL_WINDOWS:
        assert w.start > FIT_W1.end
        assert w.start.startswith("2018-")


def test_pressure_csv_loads_with_numeric_columns():
    if not (RAW / "2018_SCADA_Pressures.csv").exists():
        return
    P = load_pressures_2018()
    assert "n1" in P.columns
    assert P["n1"].dtype.kind == "f"
    assert len(P.loc[FIT_W1.start:FIT_W1.end]) > 1000