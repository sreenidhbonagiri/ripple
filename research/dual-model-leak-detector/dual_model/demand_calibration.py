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


# Physical band for Area-C unmeasured scale (unchanged; do not widen for fit quality).
AREA_C_SCALE_BOUNDS: tuple[float, float] = (0.5, 1.5)
AB_SCALE_BOUNDS: tuple[float, float] = (0.7, 1.3)


def estimate_area_c_unmeasured_scale(
    q_area_c_m3h: pd.Series,
    amr_total_m3h: pd.Series,
    base_unmeasured_m3h: float,
    *,
    bounds: tuple[float, float] = AREA_C_SCALE_BOUNDS,
) -> dict[str, Any]:
    """Estimate Area-C unmeasured demand scale from **signed** residuals.

    residual(t) = Q_C(t) − ΣAMR(t). Mean is taken over timestamps where both
    series are finite (identical mask). Individual residuals are **not** clipped
    before averaging (that induced the superseded ~2.8 upward bias).

    Returns dict with signed mean residual, raw scale, clipped scale, bound flag,
    and ``physically_inconsistent`` when the signed aggregate residual (hence raw
    scale) is ≤ 0 — unmeasured demand cannot be negative; bounds still applied.
    """
    lo, hi = bounds
    q = q_area_c_m3h.astype(float)
    amr = amr_total_m3h.astype(float)
    aligned = pd.concat({"q_c": q, "amr": amr}, axis=1)
    # Identical mask: require both finite on the same timestamp.
    mask = aligned["q_c"].notna() & aligned["amr"].notna()
    n_total = int(len(aligned))
    n_used = int(mask.sum())
    residual = aligned.loc[mask, "q_c"] - aligned.loc[mask, "amr"]

    if n_used == 0 or base_unmeasured_m3h <= 0:
        mean_residual = float("nan")
        raw_scale = float("nan")
        physically_inconsistent = True
        inconsistency_reason = "no_aligned_samples_or_nonpositive_base"
    else:
        mean_residual = float(residual.mean())  # signed; no per-sample clip
        raw_scale = mean_residual / float(base_unmeasured_m3h)
        physically_inconsistent = bool(mean_residual <= 0.0 or raw_scale <= 0.0)
        inconsistency_reason = (
            "nonpositive_signed_mean_residual"
            if physically_inconsistent
            else None
        )

    if not np.isfinite(raw_scale):
        clipped = float(lo)  # fail-closed to lower physical bound
        bound_hit = "lower_fallback_nonfinite"
    else:
        clipped = float(np.clip(raw_scale, lo, hi))
        if raw_scale < lo:
            bound_hit = "lower"
        elif raw_scale > hi:
            bound_hit = "upper"
        else:
            bound_hit = "interior"

    # Legacy (buggy) statistic for regression tests / audit continuity only.
    clipped_before_mean = float(residual.clip(lower=0.0).mean()) if n_used else float("nan")
    legacy_raw_if_clip_before_mean = (
        clipped_before_mean / float(base_unmeasured_m3h)
        if n_used and base_unmeasured_m3h > 0
        else float("nan")
    )

    return {
        "mean_residual_signed_m3h": mean_residual,
        "raw_scale": raw_scale,
        "scale": clipped,
        "bounds": [lo, hi],
        "bound_hit": bound_hit,
        "physically_inconsistent": physically_inconsistent,
        "inconsistency_reason": inconsistency_reason,
        "n_timestamps_total": n_total,
        "n_timestamps_used": n_used,
        "frac_residual_negative": float((residual < 0).mean()) if n_used else float("nan"),
        "legacy_clip_before_mean_residual_m3h": clipped_before_mean,
        "legacy_raw_scale_if_clip_before_mean": legacy_raw_if_clip_before_mean,
        "base_unmeasured_m3h": float(base_unmeasured_m3h),
    }


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
    # Align pump, level, AMR on a common index before any residual math.
    lvl = levels_fit_m["T1"].astype(float)
    q_pump = flows_fit_m3h["PUMP_1"].astype(float)
    amr_m3h = (amr_fit_lh.sum(axis=1) / 1000.0).astype(float)
    aligned = pd.concat(
        {"pump": q_pump, "level": lvl, "amr_m3h": amr_m3h},
        axis=1,
    )
    mask = aligned["pump"].notna() & aligned["level"].notna() & aligned["amr_m3h"].notna()
    aligned = aligned.loc[mask]
    dV_dt = area * (aligned["level"].diff() * 12.0)  # m³/h; first step NaN
    # Drop the first diff NaN under the same mask discipline.
    q_area_c = aligned["pump"] - dV_dt
    scale_info = estimate_area_c_unmeasured_scale(
        q_area_c,
        aligned["amr_m3h"],
        base_unmeasured_m3h=sum(
            float(ts.base_value) * 3600.0
            for n in unmeas
            for ts in wn.get_node(n).demand_timeseries_list
        ),
        bounds=AREA_C_SCALE_BOUNDS,
    )
    area_c_unmeasured_scale = float(scale_info["scale"])

    q_ext = flows_fit_m3h["p227"].astype(float) + flows_fit_m3h["p235"].astype(float)
    ext_aligned = pd.concat({"ext": q_ext, "level": levels_fit_m["T1"].astype(float)}, axis=1)
    ext_mask = ext_aligned["ext"].notna() & ext_aligned["level"].notna()
    ext_aligned = ext_aligned.loc[ext_mask]
    dV_ext = area * (ext_aligned["level"].diff() * 12.0)
    target_series = ext_aligned["ext"] - dV_ext
    target = float(target_series.dropna().mean())
    total_base_m3h = 0.0
    for n in wn.junction_name_list:
        for ts in wn.get_node(n).demand_timeseries_list:
            total_base_m3h += float(ts.base_value) * 3600.0
    ab_raw = target / max(total_base_m3h * 0.85, 1e-6)
    ab_lo, ab_hi = AB_SCALE_BOUNDS
    ab_scale = float(np.clip(ab_raw, ab_lo, ab_hi))

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
            "mean_q_area_c_m3h": float(q_area_c.dropna().mean()),
            "mean_amr_m3h": float(aligned["amr_m3h"].mean()),
            "mean_residual_c_signed_m3h": scale_info["mean_residual_signed_m3h"],
            "area_c_unmeasured_scale_raw": scale_info["raw_scale"],
            "area_c_scale_bound_hit": scale_info["bound_hit"],
            "area_c_physically_inconsistent": scale_info["physically_inconsistent"],
            "area_c_inconsistency_reason": scale_info["inconsistency_reason"],
            "area_c_n_timestamps_used": scale_info["n_timestamps_used"],
            "area_c_frac_residual_negative": scale_info["frac_residual_negative"],
            "legacy_clip_before_mean_residual_m3h": scale_info[
                "legacy_clip_before_mean_residual_m3h"
            ],
            "legacy_raw_scale_if_clip_before_mean": scale_info[
                "legacy_raw_scale_if_clip_before_mean"
            ],
            "ab_scale_raw": ab_raw,
            "estimator": "signed_mean_residual_no_preclip_v2",
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
    fill_mode: str = "legacy",
    causal_fill_max_age_steps: int = 2,
) -> None:
    """Write calibrated demands into ``wn`` for an EPS over ``timestamps``.

    Shared patterns:
      - ``{prefix}_RES``, ``{prefix}_COM``: length n, values = T(t)*S(t)
      - ``{prefix}_AMR_{node}``: measured AMR m³/s for Area-C metered nodes
    Base demands carry physical scales (m³/s for AMR patterns with base=1).

    ``fill_mode``:
      - ``legacy``: interpolate + bfill/ffill (hourly Method M path).
      - ``causal_ffill``: past-only bounded ffill; no future observations.
        Leading gaps before any observation use T=1 / AMR=0 (non-sensor
        demand assist); pressure/pump staleness gates dual availability.
    """
    from .causal_fill import causal_ffill_frame, causal_ffill_series

    if fill_mode not in ("legacy", "causal_ffill"):
        raise ValueError(f"Unknown fill_mode={fill_mode!r}")

    n = len(timestamps)
    ac = area_c_junctions(wn)
    amr_set = set(load_amr_nodes())

    if amr_lh is not None:
        if fill_mode == "causal_ffill":
            tot_raw = amr_lh.sum(axis=1)
            tot_fill = causal_ffill_series(
                tot_raw.astype(float),
                index=timestamps,
                max_age_steps=causal_fill_max_age_steps,
            )
            tot = tot_fill.values.iloc[:, 0].ffill().fillna(float(model.T_weekly_mean_amr_lh))
        else:
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
        if fill_mode == "causal_ffill":
            amr_fill = causal_ffill_frame(
                amr_lh.astype(float),
                index=timestamps,
                max_age_steps=causal_fill_max_age_steps,
            )
            amr_m3s = lh_to_m3s(amr_fill.values.ffill().fillna(0.0))
        else:
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