"""Load official BattLeDIM SCADA CSVs (semicolon, decimal comma) for offline research."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = REPO_ROOT / "data" / "raw"
LEAKAGES_PATH = Path(__file__).with_name("leakages_2018_2019.json")

PRESSURE_SENSORS = [
    "n1",
    "n4",
    "n31",
    "n54",
    "n105",
    "n114",
    "n163",
    "n188",
    "n215",
    "n229",
    "n288",
    "n296",
    "n332",
    "n342",
    "n410",
    "n415",
    "n429",
    "n458",
    "n469",
    "n495",
    "n506",
    "n516",
    "n519",
    "n549",
    "n613",
    "n636",
    "n644",
    "n679",
    "n722",
    "n726",
    "n740",
    "n752",
    "n769",
]

CONTEXT_FLOW = ["p227", "p235", "PUMP_1"]
CONTEXT_LEVEL = ["T1"]

STEP = np.timedelta64(5, "m")
WEEK = np.timedelta64(7, "D")
MIN30 = np.timedelta64(30, "m")


def parse_eu_float(cell: str) -> float:
    cell = cell.strip()
    if not cell:
        return np.nan
    return float(cell.replace(",", "."))


def _parse_ts(s: str) -> np.datetime64:
    return np.datetime64(datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S"))


@dataclass(frozen=True)
class ScadaBundle:
    timestamps: np.ndarray  # datetime64[m]
    pressure_ids: list[str]
    pressures: np.ndarray  # float32 (T, S)
    flow_ids: list[str]
    flows: np.ndarray  # float32 (T, F)
    level_ids: list[str]
    levels: np.ndarray  # float32 (T, L)

    def index_of(self, ts: np.datetime64) -> int:
        i = int(np.searchsorted(self.timestamps, ts))
        if i >= len(self.timestamps) or self.timestamps[i] != ts:
            raise KeyError(f"timestamp not on grid: {ts}")
        return i


def load_scada_csv(path: Path, expected_ids: list[str] | None = None) -> tuple[np.ndarray, list[str], np.ndarray]:
    with path.open(newline="") as f:
        header = f.readline().rstrip("\r\n").split(";")
        if header[0] != "Timestamp":
            raise ValueError(f"unexpected header in {path}")
        ids = [c.strip() for c in header[1:]]
        if expected_ids is not None and ids != expected_ids:
            missing = set(expected_ids) - set(ids)
            extra = set(ids) - set(expected_ids)
            if missing or extra:
                raise ValueError(f"{path.name} column mismatch missing={missing} extra={extra}")
        rows_ts: list[np.datetime64] = []
        rows_val: list[list[float]] = []
        for line in f:
            parts = line.rstrip("\r\n").split(";")
            rows_ts.append(_parse_ts(parts[0]))
            rows_val.append([parse_eu_float(c) for c in parts[1:]])
    ts = np.asarray(rows_ts, dtype="datetime64[m]")
    vals = np.asarray(rows_val, dtype=np.float32)
    return ts, ids, vals


def load_2018_bundle(raw_dir: Path = DEFAULT_RAW) -> ScadaBundle:
    ts_p, p_ids, pressures = load_scada_csv(raw_dir / "2018_SCADA_Pressures.csv", PRESSURE_SENSORS)
    ts_f, f_ids, flows = load_scada_csv(raw_dir / "2018_SCADA_Flows.csv", CONTEXT_FLOW)
    ts_l, l_ids, levels = load_scada_csv(raw_dir / "2018_SCADA_Levels.csv", CONTEXT_LEVEL)
    if not (np.array_equal(ts_p, ts_f) and np.array_equal(ts_p, ts_l)):
        raise ValueError("2018 SCADA timestamp grids disagree across Pressures/Flows/Levels")
    return ScadaBundle(ts_p, p_ids, pressures, f_ids, flows, l_ids, levels)


@dataclass(frozen=True)
class Leakage:
    pipe: str
    start: np.datetime64
    end: np.datetime64
    diameter_m: float
    leak_type: str
    peak: np.datetime64


def load_leakages(path: Path = LEAKAGES_PATH) -> list[Leakage]:
    raw = json.loads(path.read_text())
    out: list[Leakage] = []
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
