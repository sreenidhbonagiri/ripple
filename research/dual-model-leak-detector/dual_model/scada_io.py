"""Load BattLeDIM SCADA CSVs (European decimal commas; semicolon separators)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_DATA = Path(__file__).resolve().parents[3] / "data"
RAW = REPO_DATA / "raw"
INP_PATH = REPO_DATA / "L-TOWN.inp"


def _read_scada_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", decimal=",")
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.set_index("Timestamp").sort_index()
    return df.apply(pd.to_numeric, errors="coerce")


def load_pressures_2018() -> pd.DataFrame:
    return _read_scada_csv(RAW / "2018_SCADA_Pressures.csv")


def load_flows_2018() -> pd.DataFrame:
    """Columns: p227, p235, PUMP_1 in m³/h."""
    return _read_scada_csv(RAW / "2018_SCADA_Flows.csv")


def load_levels_2018() -> pd.DataFrame:
    """Tank level T1 in metres."""
    return _read_scada_csv(RAW / "2018_SCADA_Levels.csv")


def load_amr_demands_2018() -> pd.DataFrame:
    """AMR demands in L/h (convert to m³/s with / 3.6e6)."""
    return _read_scada_csv(RAW / "2018_SCADA_Demands.csv")


def load_leakages_2018() -> pd.DataFrame:
    """Leak discharges in m³/h (diagnostic use only; not for fitting)."""
    return _read_scada_csv(RAW / "2018_Leakages.csv")


def load_pressures_2019() -> pd.DataFrame:
    return _read_scada_csv(RAW / "2019_SCADA_Pressures.csv")


def load_flows_2019() -> pd.DataFrame:
    return _read_scada_csv(RAW / "2019_SCADA_Flows.csv")


def load_levels_2019() -> pd.DataFrame:
    return _read_scada_csv(RAW / "2019_SCADA_Levels.csv")


def load_amr_demands_2019() -> pd.DataFrame:
    return _read_scada_csv(RAW / "2019_SCADA_Demands.csv")


def load_leakages_2019() -> pd.DataFrame:
    """Leak discharges in m³/h (labels only; never for fitting)."""
    # Prefer local raw copy if present; else upstream BattLeDIM ground truth.
    local = RAW / "2019_Leakages.csv"
    if local.exists():
        return _read_scada_csv(local)
    alt = (
        Path(__file__).resolve().parents[2]
        / "lila-identification-reproduction"
        / "upstream"
        / "_utils"
        / "Data"
        / "leak_ground_truth"
        / "2019_Leakages.csv"
    )
    return _read_scada_csv(alt)


def slice_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df.loc[start:end]


def lh_to_m3s(q_lh: float | pd.Series | pd.DataFrame):
    """Litres/hour → m³/s."""
    return q_lh / 3.6e6


def m3h_to_m3s(q_m3h: float | pd.Series | pd.DataFrame):
    return q_m3h / 3600.0