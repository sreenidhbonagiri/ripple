"""Calibrated L-Town H0/H1 hypothesis test (synthetic feasibility).

Observations and H0/H1 predictions use the same nonlinear EPANET generator on
the corrected frozen-calibration roughness template. No linear response library
is used for reported J (optional diagnostics may note linear screening if added).

Nuisance under H0 and H1 (identical bounds): area demand scales + global HW scale.
H1 adds nonnegative leak at one registered candidate (pressure-sensor junctions).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import wntr
import wntr.network.io
from scipy.optimize import minimize, minimize_scalar

from .area_topology import (
    apply_cluster_roughness,
    area_b_junctions,
    area_c_junctions,
    build_roughness_clusters,
    load_pressure_sensors,
)
from .ltown_hydraulics import load_nominal_wn
from .synthetic_networks import inject_nodal_leak
from .units import m3h_to_m3s

CAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "calibration"
    / "frozen_calibration.json"
)
CAL_SHA256 = "5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921"


@dataclass(frozen=True)
class LTownHypConfig:
    # Area scales: wide enough for registered demand-only scenarios (≤1.12),
    # but ridge-penalized so they cannot freely absorb a localized leak.
    scale_min: float = 0.88
    scale_max: float = 1.12
    rho_min: float = 0.95
    rho_max: float = 1.05
    q_max_m3h: float = 15.0
    q_min_m3h: float = 0.35
    lambda_scale: float = 2.0
    lambda_rho: float = 0.5
    # Steady L-Town head SSE for ~5 m³/h nodal leaks is O(0.02 m²); penalty must
    # sit below that scale or H1 never wins. Not a probability.
    pi0_m2: float = 0.0002
    clear_margin_extra: float = 0.05
    ambiguity_scale_q: float = 0.4
    tau_dev: float = 0.0
    region_eps: float = 0.02  # overwritten by DEV calibration
    r_max_frac: float = 0.5
    intended_coverage: float = 0.90


@dataclass
class LTownFit:
    scales: dict[str, float]  # A, B, C
    rho: float
    leak_node: str | None
    leak_m3h: float
    pred_heads: dict[str, float]
    J: float
    residual_ss: float
    success: bool


@dataclass
class LTownDecision:
    decision: str
    J_H0: float
    J_H1: float
    delta_J: float
    penalty: float
    tau_dev: float
    region_eps: float
    best_candidate: str | None
    leak_m3h: float
    candidate_region: list[str]
    region_size: int
    J_by_candidate: dict[str, float]
    fit_H0: LTownFit
    reasons: list[str] = field(default_factory=list)


def load_frozen_roughness() -> dict[str, float]:
    cal = json.loads(CAL_PATH.read_text())
    return {k: float(v) for k, v in cal["roughness"]["values"].items()}


def registered_candidates() -> tuple[str, ...]:
    """Pressure-sensor junctions only — fixed before any scenario truth leaks."""
    return tuple(sorted(load_pressure_sensors()))


def build_calibrated_template(scratch: Path) -> tuple[Any, tuple[str, ...], dict[str, set[str]]]:
    """Nominal L-Town + frozen HW clusters. Returns wn, sensors, area→junctions."""
    wn = load_nominal_wn()
    clusters = build_roughness_clusters(wn)
    apply_cluster_roughness(wn, clusters, load_frozen_roughness())
    # Persist a clean copy
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / "calibrated_base.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    wn = wntr.network.WaterNetworkModel(str(path))
    sensors = load_pressure_sensors()
    ac = area_c_junctions(wn)
    ab = area_b_junctions(wn)
    aa = set(wn.junction_name_list) - ac - ab
    areas = {"A": aa, "B": ab, "C": ac}
    return wn, sensors, areas


def _clone(wn, scratch: Path) -> Any:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"c_{np.random.randint(1e12)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def _snapshot_bases(wn) -> dict[str, float]:
    out = {}
    for name in wn.junction_name_list:
        node = wn.get_node(name)
        if node.demand_timeseries_list:
            out[name] = float(node.demand_timeseries_list[0].base_value)
        else:
            out[name] = 0.0
    return out


def _apply_area_scales(wn, bases: Mapping[str, float], areas: Mapping[str, set[str]], scales: Mapping[str, float]) -> None:
    scale_of = {}
    for area, nodes in areas.items():
        s = float(scales.get(area, 1.0))
        for n in nodes:
            scale_of[n] = s
    for name, base in bases.items():
        node = wn.get_node(name)
        if not node.demand_timeseries_list:
            continue
        node.demand_timeseries_list[0].base_value = float(base) * float(scale_of.get(name, 1.0))


def _apply_rho(wn, rho: float, pipe_rough0: Mapping[str, float]) -> None:
    for pname, r0 in pipe_rough0.items():
        wn.get_link(pname).roughness = float(r0) * float(rho)


def predict_heads(
    wn_template,
    sensors: Sequence[str],
    areas: Mapping[str, set[str]],
    pipe_rough0: Mapping[str, float],
    bases: Mapping[str, float],
    *,
    scales: Mapping[str, float],
    rho: float,
    leak_node: str | None,
    leak_m3h: float,
    scratch: Path,
) -> dict[str, float]:
    wn = _clone(wn_template, scratch)
    _apply_area_scales(wn, bases, areas, scales)
    _apply_rho(wn, rho, pipe_rough0)
    if leak_node is not None and leak_m3h > 0:
        inject_nodal_leak(wn, leak_node, float(leak_m3h))
    wn.options.time.duration = 0
    wn.options.time.hydraulic_timestep = 3600
    wn.options.time.report_timestep = 3600
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    return {s: float(res.node["head"].iloc[0][s]) for s in sensors}


def _pack_scales(x: np.ndarray) -> dict[str, float]:
    return {"A": float(x[0]), "B": float(x[1]), "C": float(x[2])}


def fit_H0(
    wn_template,
    sensors: Sequence[str],
    areas: Mapping[str, set[str]],
    obs: Mapping[str, float],
    *,
    cfg: LTownHypConfig,
    scratch: Path,
) -> LTownFit:
    bases = _snapshot_bases(wn_template)
    pipe_rough0 = {p: float(wn_template.get_link(p).roughness) for p in wn_template.pipe_name_list}
    bounds = [
        (cfg.scale_min, cfg.scale_max),
        (cfg.scale_min, cfg.scale_max),
        (cfg.scale_min, cfg.scale_max),
        (cfg.rho_min, cfg.rho_max),
    ]
    x0 = np.array([1.0, 1.0, 1.0, 1.0], dtype=float)

    def fun(x: np.ndarray) -> float:
        scales = _pack_scales(x)
        rho = float(x[3])
        try:
            pred = predict_heads(
                wn_template, sensors, areas, pipe_rough0, bases,
                scales=scales, rho=rho, leak_node=None, leak_m3h=0.0, scratch=scratch,
            )
        except Exception:
            return 1e6
        resid = sum((pred[s] - float(obs[s])) ** 2 for s in sensors)
        reg = cfg.lambda_scale * sum((scales[a] - 1.0) ** 2 for a in scales) + cfg.lambda_rho * (rho - 1.0) ** 2
        return float(resid + reg)

    res = minimize(fun, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 30, "ftol": 1e-10})
    x = np.asarray(res.x, dtype=float)
    scales = _pack_scales(x)
    rho = float(x[3])
    pred = predict_heads(
        wn_template, sensors, areas, pipe_rough0, bases,
        scales=scales, rho=rho, leak_node=None, leak_m3h=0.0, scratch=scratch,
    )
    resid = sum((pred[s] - float(obs[s])) ** 2 for s in sensors)
    return LTownFit(
        scales=scales, rho=rho, leak_node=None, leak_m3h=0.0,
        pred_heads=pred, J=float(res.fun), residual_ss=float(resid), success=bool(res.success) or res.fun < 1e5,
    )


def fit_H1_candidate(
    wn_template,
    sensors: Sequence[str],
    areas: Mapping[str, set[str]],
    obs: Mapping[str, float],
    candidate: str,
    *,
    cfg: LTownHypConfig,
    scratch: Path,
    warm: LTownFit,
) -> LTownFit:
    """Nested H1: identical nuisance point estimate as H0, plus q≥0 at candidate.

    Freezing scales/ρ at the H0 MLE gives H1 no extra nuisance flexibility.
    Reported J uses the same nonlinear EPANET generator as observations.
    """
    bases = _snapshot_bases(wn_template)
    pipe_rough0 = {p: float(wn_template.get_link(p).roughness) for p in wn_template.pipe_name_list}

    def fun_q(q: float) -> float:
        try:
            pred = predict_heads(
                wn_template, sensors, areas, pipe_rough0, bases,
                scales=warm.scales, rho=warm.rho, leak_node=candidate, leak_m3h=float(q),
                scratch=scratch,
            )
        except Exception:
            return 1e6
        resid = sum((pred[s] - float(obs[s])) ** 2 for s in sensors)
        reg = (
            cfg.lambda_scale * sum((warm.scales[a] - 1.0) ** 2 for a in warm.scales)
            + cfg.lambda_rho * (warm.rho - 1.0) ** 2
        )
        return float(resid + reg)

    br = minimize_scalar(fun_q, bounds=(0.0, cfg.q_max_m3h), method="bounded", options={"xatol": 0.02})
    q = float(br.x)
    pred = predict_heads(
        wn_template, sensors, areas, pipe_rough0, bases,
        scales=warm.scales, rho=warm.rho, leak_node=candidate, leak_m3h=q, scratch=scratch,
    )
    resid = sum((pred[s] - float(obs[s])) ** 2 for s in sensors)
    return LTownFit(
        scales=dict(warm.scales), rho=float(warm.rho), leak_node=candidate, leak_m3h=q,
        pred_heads=pred, J=float(br.fun), residual_ss=float(resid), success=True,
    )


def decide_ltown(
    wn_template,
    sensors: Sequence[str],
    areas: Mapping[str, set[str]],
    obs: Mapping[str, float],
    candidates: Sequence[str],
    *,
    cfg: LTownHypConfig,
    scratch: Path,
) -> LTownDecision:
    fit0 = fit_H0(wn_template, sensors, areas, obs, cfg=cfg, scratch=scratch / "h0")
    fits: dict[str, LTownFit] = {}
    J_by: dict[str, float] = {}
    for c in candidates:
        fits[c] = fit_H1_candidate(
            wn_template, sensors, areas, obs, c, cfg=cfg, scratch=scratch / f"h1_{c}", warm=fit0
        )
        J_by[c] = float(fits[c].J)

    best_c = min(J_by, key=J_by.get)
    fit1 = fits[best_c]
    delta_J = float(fit0.J - fit1.J)
    penalty = float(cfg.pi0_m2 * len(sensors))
    threshold = penalty + float(cfg.tau_dev)
    region = sorted(c for c, j in J_by.items() if j <= fit1.J + cfg.region_eps)
    r_max = max(1, int(np.ceil(cfg.r_max_frac * len(candidates))))

    reasons: list[str] = []
    # Nested model: demand–leak ambiguity when ΔJ is tiny despite q̂>0 (H0 already absorbed mass).
    demand_leak_swap = (
        fit1.leak_m3h >= cfg.q_min_m3h
        and delta_J <= threshold + cfg.clear_margin_extra
        and fit0.residual_ss <= fit1.residual_ss + 1e-6
    )

    if demand_leak_swap and delta_J <= threshold:
        decision = "inconclusive"
        reasons.append("demand_leak_indifferent")
    elif delta_J <= 1e-6 and fit1.leak_m3h < cfg.q_min_m3h:
        decision = "no_new_leak"
        reasons.append("near_null")
    elif 0.0 < delta_J <= threshold:
        decision = "inconclusive"
        reasons.append("ambiguity_band")
    elif delta_J > threshold and fit1.leak_m3h >= cfg.q_min_m3h:
        if len(region) > r_max and delta_J <= threshold + cfg.clear_margin_extra:
            decision = "inconclusive"
            reasons.append("uninformative_region")
        else:
            decision = "leak"
            reasons.append("deltaJ_exceeds_penalty")
    else:
        decision = "no_new_leak"
        reasons.append("H0_preferred")

    return LTownDecision(
        decision=decision,
        J_H0=float(fit0.J),
        J_H1=float(fit1.J),
        delta_J=delta_J,
        penalty=penalty,
        tau_dev=float(cfg.tau_dev),
        region_eps=float(cfg.region_eps),
        best_candidate=best_c,
        leak_m3h=float(fit1.leak_m3h),
        candidate_region=region,
        region_size=len(region),
        J_by_candidate=J_by,
        fit_H0=fit0,
        reasons=reasons,
    )


def decision_to_dict(d: LTownDecision) -> dict[str, Any]:
    return {
        "decision": d.decision,
        "J_H0": d.J_H0,
        "J_H1": d.J_H1,
        "delta_J": d.delta_J,
        "penalty": d.penalty,
        "tau_dev": d.tau_dev,
        "region_eps": d.region_eps,
        "best_candidate": d.best_candidate,
        "leak_m3h": d.leak_m3h,
        "candidate_region": d.candidate_region,
        "region_size": d.region_size,
        "J_by_candidate": d.J_by_candidate,
        "reasons": d.reasons,
        "H0_scales": d.fit_H0.scales,
        "H0_rho": d.fit_H0.rho,
        "generator": "epanet_nonlinear_same_as_obs",
        "linear_approximation_for_reported_J": False,
        "h1_nuisance": "frozen_at_H0_MLE_nested",
        "note": "H1 does not widen scale/ρ bounds; only adds q≥0 at a candidate.",
    }


def apply_region_eps(decision_dict: dict[str, Any], region_eps: float, n_cand: int, cfg: LTownHypConfig) -> dict[str, Any]:
    """Recompute region from stored J_by_candidate after freezing ε (no re-fit)."""
    out = dict(decision_dict)
    J_by = out["J_by_candidate"]
    best = out["best_candidate"]
    Jstar = float(J_by[best])
    region = sorted(c for c, j in J_by.items() if float(j) <= Jstar + float(region_eps))
    out["region_eps"] = float(region_eps)
    out["candidate_region"] = region
    out["region_size"] = len(region)
    # Re-evaluate uninformative-region abstention if was leak
    r_max = max(1, int(np.ceil(cfg.r_max_frac * n_cand)))
    if out["decision"] == "leak" and len(region) > r_max:
        thr = float(out["penalty"]) + float(out["tau_dev"])
        if float(out["delta_J"]) <= thr + cfg.clear_margin_extra:
            out["decision"] = "inconclusive"
            out["reasons"] = list(out.get("reasons") or []) + ["uninformative_region_after_eps"]
    return out
