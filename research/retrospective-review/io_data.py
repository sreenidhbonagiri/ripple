"""Local official SCADA + leakage labels (evaluation only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data" / "raw"
LEAKAGES_PATH = Path(__file__).with_name("leakages_2018_2019.json")

PRESSURE_SENSORS = [
    "n1", "n4", "n31", "n54", "n105", "n114", "n163", "n188", "n215", "n229",
    "n288", "n296", "n332", "n342", "n410", "n415", "n429", "n458", "n469", "n495",
    "n506", "n516", "n519", "n549", "n613", "n636", "n644", "n679", "n722", "n726",
    "n740", "n752", "n769",
]


def parse_eu_float(cell: str) -> float:
    cell = cell.strip()
    if not cell:
        return np.nan
    return float(cell.replace(",", "."))


def _parse_ts(s: str) -> np.datetime64:
    return np.datetime64(datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S"))


@dataclass(frozen=True)
class PressureBundle:
    timestamps: np.ndarray
    sensor_ids: list[str]
    pressures: np.ndarray  # float32 (T, S)


@dataclass(frozen=True)
class ContextBundle:
    timestamps: np.ndarray
    flow_ids: list[str]
    flows: np.ndarray
    level_ids: list[str]
    levels: np.ndarray


@dataclass(frozen=True)
class Leakage:
    pipe: str
    start: np.datetime64
    end: np.datetime64
    diameter_m: float
    leak_type: str
    peak: np.datetime64


def load_pressures(path: Path) -> PressureBundle:
    with path.open(newline="") as f:
        header = f.readline().rstrip("\r\n").split(";")
        ids = [c.strip() for c in header[1:]]
        if ids != PRESSURE_SENSORS:
            raise ValueError(f"unexpected pressure columns in {path.name}")
        ts_list: list[np.datetime64] = []
        rows: list[list[float]] = []
        for line in f:
            parts = line.rstrip("\r\n").split(";")
            ts_list.append(_parse_ts(parts[0]))
            rows.append([parse_eu_float(c) for c in parts[1:]])
    return PressureBundle(
        np.asarray(ts_list, dtype="datetime64[m]"),
        ids,
        np.asarray(rows, dtype=np.float32),
    )


def load_context(raw_dir: Path = DEFAULT_RAW) -> ContextBundle:
    def _load(name: str, expected: list[str]):
        with (raw_dir / name).open(newline="") as f:
            header = f.readline().rstrip("\r\n").split(";")
            ids = [c.strip() for c in header[1:]]
            if ids != expected:
                raise ValueError(f"unexpected columns in {name}: {ids}")
            ts_list = []
            rows = []
            for line in f:
                parts = line.rstrip("\r\n").split(";")
                ts_list.append(_parse_ts(parts[0]))
                rows.append([parse_eu_float(c) for c in parts[1:]])
        return np.asarray(ts_list, dtype="datetime64[m]"), ids, np.asarray(rows, dtype=np.float32)

    ts_f, f_ids, flows = _load("2018_SCADA_Flows.csv", ["p227", "p235", "PUMP_1"])
    ts_l, l_ids, levels = _load("2018_SCADA_Levels.csv", ["T1"])
    if not np.array_equal(ts_f, ts_l):
        raise ValueError("flow/level timestamp mismatch")
    return ContextBundle(ts_f, f_ids, flows, l_ids, levels)


def load_leakages(path: Path = LEAKAGES_PATH) -> list[Leakage]:
    raw = json.loads(path.read_text())
    out = []
    for row in raw["leakages"]:
        out.append(
            Leakage(
                pipe=row["pipe"],
                start=np.datetime64(row["start"].replace(" ", "T")),
                end=np.datetime64(row["end"].replace(" ", "T")),
                diameter_m=float(row["diameter_m"]),
                leak_type=row["type"],
                peak=np.datetime64(row["peak"].replace(" ", "T")),
            )
        )
    return out


def open_leak_count(leakages: list[Leakage], t: np.datetime64) -> int:
    return sum(1 for L in leakages if L.start <= t <= L.end)
