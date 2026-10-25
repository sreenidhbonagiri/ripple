"""Build hourly dual q_v series under frozen calibration (chunked EPS)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import wntr

from .area_topology import build_roughness_clusters
from .demand_calibration import DemandModel
from .detection_protocol import REQUIRED_FROZEN_SHA256
from .ltown_hydraulics import load_nominal_wn, run_dual_window, subsample_hourly
from .scada_io import (
    load_amr_demands_2018,
    load_flows_2018,
    load_levels_2018,
    load_pressures_2018,
)


def verify_frozen_hash(frozen_path: Path) -> str:
    digest = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    if digest != REQUIRED_FROZEN_SHA256:
        raise RuntimeError(
            f"frozen_calibration sha256 mismatch: got {digest}, "
            f"required {REQUIRED_FROZEN_SHA256}"
        )
    return digest


def load_frozen(frozen_path: Path) -> tuple[DemandModel, dict[str, float], float]:
    verify_frozen_hash(frozen_path)
    doc = json.loads(frozen_path.read_text())
    dm = DemandModel.from_dict(doc["demand_model"])
    roughness = {k: float(v) for k, v in doc["roughness"]["values"].items()}
    tcv = float(doc["tcv_setting"])
    return dm, roughness, tcv


def build_dual_qv_hourly(
    start: str,
    end: str,
    *,
    frozen_path: Path,
    scratch: Path,
    chunk_days: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Return (q_v_m3h, flows_m3h_hourly, level_m_hourly) on hourly grid."""
    dm, roughness, tcv = load_frozen(frozen_path)
    wn = load_nominal_wn()
    clusters = build_roughness_clusters(wn)

    P = load_pressures_2018()
    F = load_flows_2018()
    L = load_levels_2018()
    A = load_amr_demands_2018()

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    chunks = []
    cur = start_ts
    while cur <= end_ts:
        chunk_end = min(cur + pd.Timedelta(days=chunk_days) - pd.Timedelta(minutes=5), end_ts)
        Ph = subsample_hourly(P.loc[cur:chunk_end])
        if len(Ph) < 2:
            cur = chunk_end + pd.Timedelta(minutes=5)
            continue
        Fh = subsample_hourly(F.loc[cur:chunk_end])
        Lh = subsample_hourly(L.loc[cur:chunk_end])
        Ah = subsample_hourly(A.loc[cur:chunk_end])
        # Align
        idx = Ph.index.intersection(Fh.index).intersection(Lh.index).intersection(Ah.index)
        Ph, Fh, Lh, Ah = Ph.loc[idx], Fh.loc[idx], Lh.loc[idx], Ah.loc[idx]
        dual = run_dual_window(
            wn,
            Ph.index,
            Ph,
            demand_model=dm,
            amr_lh=Ah,
            levels_m=Lh["T1"],
            scratch=scratch,
            roughness=roughness,
            clusters=clusters,
            tcv_setting=tcv,
            timestep_sec=3600,
        )
        qvh = dual.q_v_m3h
        qvh.index = Ph.index[: len(qvh)]
        chunks.append(qvh)
        cur = chunk_end + pd.Timedelta(minutes=5)

    qv = pd.concat(chunks).sort_index()
    qv = qv[~qv.index.duplicated(keep="first")]
    flows = subsample_hourly(F.loc[start_ts:end_ts]).reindex(qv.index)
    levels = subsample_hourly(L.loc[start_ts:end_ts])["T1"].reindex(qv.index)
    return qv, flows, levels