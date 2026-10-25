"""Demand model from Area-C AMRs + INP patterns for unmeasured nodes.

Follows Steffelbauer et al. (2022) multiplicative form
    d(t) = d_base · T(t) · S(t)
Departures: see DEPARTURES.md (stage 3 section).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import wntr

from .area_topology import area_c_junctions, load_amr_nodes
from .scada_io import lh_to_m3s


@dataclass
class DemandModel:
    S_residential: list[float]
    S_commercial: list[float]
    T_weekly_mean_amr_lh: float
    amr_type: dict[str, str]
    ab_scale: float
    area_c_unmeasured_scale: float
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "DemandModel":
        return DemandModel(**d)

    def S(self, kind: str) -> np.ndarray:
        return np.asarray(
            self.S_residential if kind == "residential" else self.S_commercial,
            dtype=float,
        )

    def seasonality_factor(self, ts: pd.Timestamp, kind: str) -> float:
        step = (ts.dayofweek * 288 + (ts.hour * 60 + ts.minute) // 5) % 2016
        return float(self.S(kind)[step])


def _inp_pattern_array(wn: wntr.network.WaterNetworkModel, name: str) -> np.ndarray:
    return np.asarray(wn.get_pattern(name).multipliers, dtype=float)


def _classify_amr(amr: pd.DataFrame, S_res: np.ndarray, S_com: np.ndarray) -> dict[str, str]:
    out: dict[str, str] = {}
    steps = np.array(
        [(t.dayofweek * 288 + (t.hour * 60 + t.minute) // 5) % 2016 for t in amr.index],
        dtype=int,
    )
    s_r, s_c = S_res[steps], S_com[steps]
    for col in amr.columns:
        y = amr[col].astype(float).values
        if np.nanstd(y) < 1e-9:
            out[col] = "residential"
            continue
        y0 = y - np.nanmean(y)
        cr = float(np.nanmean(y0 * (s_r - s_r.mean())))
        cc = float(np.nanmean(y0 * (s_c - s_c.mean())))
        out[col] = "residential" if cr >= cc else "commercial"
    return out


def _estimate_S_from_amr(amr_lh: pd.DataFrame, kind_map: dict[str, str], kind: str) -> np.ndarray:
    cols = [c for c, k in kind_map.items() if k == kind]
    if not cols:
        return np.ones(2016)
    S = np.zeros(2016)
    counts = np.zeros(2016)
    for c in cols:
        y = amr_lh[c].astype(float)
        trend = y.rolling(288, min_periods=36, center=True).mean()
        ratio = y / trend.replace(0, np.nan)
        for ts, val in ratio.items():
            if not np.isfinite(val):
                continue
            step = (ts.dayofweek * 288 + (ts.hour * 60 + ts.minute) // 5) % 2016
            S[step] += float(val)
            counts[step] += 1
    for i in range(2016):
        S[i] = S[i] / counts[i] if counts[i] > 0 else 1.0
    return S / max(S.mean(), 1e-12)


def fit_demand_model(
    wn: wntr.network.WaterNetworkModel,
    amr_fit_lh: pd.DataFrame,
    flows_fit_m3h: pd.DataFrame,
    levels_fit_m: pd.DataFrame,
) -> DemandModel:
    S_res_inp = _inp_pattern_array(wn, "P-Residential")
    S_com_inp = _inp_pattern_array(wn, "P-Commercial")
    kind_map = _classify_amr(amr_fit_lh, S_res_inp, S_com_inp)
    S_res = 0.5 * _estimate_S_from_amr(amr_fit_lh, kind_map, "residential") + 0.5 * (
        S_res_inp / S_res_inp.mean()
    )
    S_com = 0.5 * _estimate_S_from_amr(amr_fit_lh, kind_map, "commercial") + 0.5 * (
        S_com_inp / S_com_inp.mean()
    )

    ac = area_c_junctions(wn)
    amr_nodes = set(load_amr_nodes())
    unmeas = sorted(ac - amr_nodes)

    tank = wn.get_node("T1")
    area = np.pi * (tank.diameter / 2.0) ** 2
    lvl = levels_fit_m["T1"].astype(float)
    dV_dt = area * (lvl.diff().fillna(0.0) * 12.0)  # m³/h
    q_pump = flows_fit_m3h["PUMP_1"].astype(float)
    q_area_c = q_pump - dV_dt
    amr_m3h = amr_fit_lh.sum(axis=1) / 1000.0
    residual_c = (q_area_c - amr_m3h).clip(lower=0.0)

    base_unmeas = 0.0
    for n in unmeas:
        for ts in wn.get_node(n).demand_timeseries_list:
            base_unmeas += float(ts.base_value) * 3600.0
    raw_scale = float(np.nanmean(residual_c) / max(base_unmeas, 1e-12))
    area_c_unmeasured_scale = float(np.clip(raw_scale, 0.5, 1.5))

    q_ext = flows_fit_m3h["p227"].astype(float) + flows_fit_m3h["p235"].astype(float)
    total_base_m3h = 0.0
    for n in wn.junction_name_list:
        for ts in wn.get_node(n).demand_timeseries_list:
            total_base_m3h += float(ts.base_value) * 3600.0
    target = float((q_ext - dV_dt).mean())
    ab_scale = float(np.clip(target / max(total_base_m3h * 0.85, 1e-6), 0.7, 1.3))

    return DemandModel(
        S_residential=S_res.tolist(),
        S_commercial=S_com.tolist(),
        T_weekly_mean_amr_lh=float(amr_fit_lh.sum(axis=1).mean()),
        amr_type=kind_map,
        ab_scale=ab_scale,
        area_c_unmeasured_scale=area_c_unmeasured_scale,
        meta={
            "n_amr": len(amr_nodes),
            "n_area_c_unmeasured": len(unmeas),
            "mean_q_ext_m3h": float(q_ext.mean()),
            "mean_q_area_c_m3h": float(q_area_c.mean()),
            "mean_amr_m3h": float(amr_m3h.mean()),
            "mean_residual_c_m3h": float(residual_c.mean()),
            "area_c_unmeasured_scale_raw": raw_scale,
        },
    )


def _node_base_and_kind(node) -> tuple[float, str]:
    base = 0.0
    kind = "residential"
    industrial = False
    for ts in node.demand_timeseries_list:
        base += float(ts.base_value)
        pname = str(ts.pattern_name or "")
        if "Commercial" in pname:
            kind = "commercial"
        if "Industrial" in pname:
            industrial = True
    if industrial:
        kind = "industrial"
    return base, kind


def apply_demand_model(
    wn: wntr.network.WaterNetworkModel,
    model: DemandModel,
    timestamps: pd.DatetimeIndex,
    amr_lh: pd.DataFrame | None,
    *,
    pattern_prefix: str = "CAL",
) -> None:
    """Write calibrated demands into ``wn`` for an EPS over ``timestamps``.

    Shared patterns:
      - ``{prefix}_RES``, ``{prefix}_COM``: length n, values = T(t)*S(t)
      - ``{prefix}_AMR_{node}``: measured AMR m³/s for Area-C metered nodes
    Base demands carry physical scales (m³/s for AMR patterns with base=1).
    """
    n = len(timestamps)
    ac = area_c_junctions(wn)
    amr_set = set(load_amr_nodes())

    if amr_lh is not None:
        tot = amr_lh.sum(axis=1).reindex(timestamps).interpolate(limit=12).bfill().ffill()
        T = (tot / model.T_weekly_mean_amr_lh).clip(0.5, 1.5).fillna(1.0)
    else:
        T = pd.Series(1.0, index=timestamps)

    S_res = [float(T.loc[t]) * model.seasonality_factor(t, "residential") for t in timestamps]
    S_com = [float(T.loc[t]) * model.seasonality_factor(t, "commercial") for t in timestamps]
    S_flat = [float(T.loc[t]) for t in timestamps]

    res_name, com_name, flat_name = f"{pattern_prefix}_RES", f"{pattern_prefix}_COM", f"{pattern_prefix}_FLAT"
    for name, vals in ((res_name, S_res), (com_name, S_com), (flat_name, S_flat)):
        if name in wn.pattern_name_list:
            wn.patterns[name].multipliers = vals
        else:
            wn.add_pattern(name, vals)

    amr_m3s = None
    if amr_lh is not None:
        amr_m3s = lh_to_m3s(amr_lh.reindex(timestamps).interpolate(limit=3).bfill().ffill())

    for jname in list(wn.junction_name_list):
        node = wn.get_node(jname)
        base, kind = _node_base_and_kind(node)
        node.demand_timeseries_list.clear()

        if amr_m3s is not None and jname in amr_m3s.columns:
            pat = f"{pattern_prefix}_AMR_{jname}"
            series = amr_m3s[jname].astype(float).fillna(0.0).tolist()
            if pat in wn.pattern_name_list:
                wn.patterns[pat].multipliers = series
            else:
                wn.add_pattern(pat, series)
            node.add_demand(1.0, pat)
            continue

        if jname in ac:
            scale = model.area_c_unmeasured_scale
        else:
            scale = model.ab_scale

        if kind == "commercial":
            pat = com_name
        elif kind == "industrial":
            pat = flat_name
        else:
            pat = res_name
        node.add_demand(base * scale, pat)