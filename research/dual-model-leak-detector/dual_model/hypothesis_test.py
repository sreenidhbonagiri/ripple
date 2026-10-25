"""H0/H1 uncertainty-aware hydraulic leak hypothesis test (synthetic stage).

H0: constrained demand deltas + roughness scale (no new leak).
H1: identical nuisance bounds + nonnegative leak at a candidate node.

H1 never receives wider nuisance flexibility than H0.
Better fit alone is not treated as proof of a leak (complexity penalty +
inconclusive admissions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import wntr
import wntr.network.io
from scipy.optimize import minimize

from .synthetic_networks import inject_nodal_leak, scale_all_roughness
from .units import m3h_to_m3s, m3s_to_m3h


@dataclass(frozen=True)
class HypothesisConfig:
    """Protocol defaults for synthetic feasibility (see HYPOTHESIS_PROTOCOL.md)."""

    delta_min_m3h: float = -3.0
    delta_max_m3h: float = 3.0
    rho_min: float = 0.92
    rho_max: float = 1.08
    q_max_m3h: float = 12.0
    q_min_m3h: float = 0.25
    lambda_delta: float = 1e-3
    lambda_rho: float = 1e-2
    pi0_m2: float = 0.05
    region_eps_m2: float = 0.02
    ambiguity_delta_q_m3h: float = 0.5
    clear_margin_extra: float = 0.05
    # Development-selected margin (frozen after dev grid; default until selected).
    tau_dev: float = 0.0


@dataclass
class FitResult:
    junction_names: list[str]
    deltas_m3h: dict[str, float]
    rho: float
    leak_node: str | None
    leak_m3h: float
    pred_heads: dict[str, float]
    J: float
    residual_ss: float
    success: bool
    message: str = ""


@dataclass
class HypothesisDecision:
    decision: str  # no_new_leak | leak | inconclusive
    J_H0: float
    J_H1: float
    delta_J: float
    penalty: float
    tau_dev: float
    best_candidate: str | None
    leak_m3h: float
    candidate_region: list[str]
    region_size: int
    fit_H0: FitResult
    fit_H1_by_candidate: dict[str, FitResult]
    reasons: list[str] = field(default_factory=list)


def candidate_nodes_from_topology(network_id: str) -> tuple[str, ...]:
    """Fixed candidates from topology — not from evaluation leak locations."""
    if network_id == "branched3":
        return ("J1", "J2", "J3")
    if network_id == "pump_tank":
        return ("J1", "J2")
    raise ValueError(f"unknown network_id={network_id}")


def _clone(wn: wntr.network.WaterNetworkModel, scratch: Path) -> wntr.network.WaterNetworkModel:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"hyp_clone_{id(wn)}_{np.random.randint(1e9)}.inp"
    wntr.network.io.write_inpfile(wn, str(path))
    return wntr.network.WaterNetworkModel(str(path))


def _junction_names(wn: wntr.network.WaterNetworkModel) -> list[str]:
    return list(wn.junction_name_list)


def _apply_demand_deltas(
    wn: wntr.network.WaterNetworkModel,
    base_demands_m3s: Mapping[str, float],
    deltas_m3h: Mapping[str, float],
) -> None:
    for name, base in base_demands_m3s.items():
        node = wn.get_node(name)
        if not node.demand_timeseries_list:
            continue
        node.demand_timeseries_list[0].base_value = float(base) + m3h_to_m3s(float(deltas_m3h.get(name, 0.0)))


def _snapshot_base_demands(wn: wntr.network.WaterNetworkModel) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in wn.junction_name_list:
        node = wn.get_node(name)
        if node.demand_timeseries_list:
            out[name] = float(node.demand_timeseries_list[0].base_value)
        else:
            out[name] = 0.0
    return out


def predict_heads(
    wn_template: wntr.network.WaterNetworkModel,
    sensors: Sequence[str],
    *,
    deltas_m3h: Mapping[str, float],
    rho: float,
    leak_node: str | None,
    leak_m3h: float,
    scratch: Path,
    base_demands_m3s: Mapping[str, float] | None = None,
) -> dict[str, float]:
    wn = _clone(wn_template, scratch)
    bases = dict(base_demands_m3s) if base_demands_m3s is not None else _snapshot_base_demands(wn)
    # Reset then apply deltas relative to template bases stored from template clone.
    _apply_demand_deltas(wn, bases, deltas_m3h)
    if abs(rho - 1.0) > 1e-12:
        scale_all_roughness(wn, float(rho))
    if leak_node is not None and leak_m3h > 0:
        inject_nodal_leak(wn, leak_node, float(leak_m3h))
    res = wntr.sim.EpanetSimulator(wn).run_sim()
    # Prefer first report row (steady / snapshot).
    return {s: float(res.node["head"].iloc[0][s]) for s in sensors}


def _objective(
    x: np.ndarray,
    *,
    wn_template: wntr.network.WaterNetworkModel,
    sensors: Sequence[str],
    obs: Mapping[str, float],
    junction_names: Sequence[str],
    cfg: HypothesisConfig,
    scratch: Path,
    base_demands_m3s: Mapping[str, float],
    leak_node: str | None,
    include_leak: bool,
) -> float:
    n_j = len(junction_names)
    deltas = {junction_names[i]: float(x[i]) for i in range(n_j)}
    rho = float(x[n_j])
    leak = float(x[n_j + 1]) if include_leak else 0.0
    try:
        pred = predict_heads(
            wn_template,
            sensors,
            deltas_m3h=deltas,
            rho=rho,
            leak_node=leak_node if include_leak else None,
            leak_m3h=leak if include_leak else 0.0,
            scratch=scratch,
            base_demands_m3s=base_demands_m3s,
        )
    except Exception:
        return 1e6
    resid = sum((pred[s] - float(obs[s])) ** 2 for s in sensors)
    reg = cfg.lambda_delta * sum(v * v for v in deltas.values()) + cfg.lambda_rho * (rho - 1.0) ** 2
    return float(resid + reg)


def fit_hypothesis(
    wn_template: wntr.network.WaterNetworkModel,
    sensors: Sequence[str],
    obs_heads: Mapping[str, float],
    *,
    cfg: HypothesisConfig,
    scratch: Path,
    leak_node: str | None = None,
) -> FitResult:
    """Fit H0 (leak_node is None) or H1 at a fixed candidate leak_node."""
    wn0 = _clone(wn_template, scratch)
    junctions = _junction_names(wn0)
    bases = _snapshot_base_demands(wn0)
    include_leak = leak_node is not None
    n_j = len(junctions)
    x0 = np.zeros(n_j + 1 + (1 if include_leak else 0), dtype=float)
    x0[n_j] = 1.0
    bounds = [(cfg.delta_min_m3h, cfg.delta_max_m3h)] * n_j + [(cfg.rho_min, cfg.rho_max)]
    if include_leak:
        bounds.append((0.0, cfg.q_max_m3h))

    def fun(x: np.ndarray) -> float:
        return _objective(
            x,
            wn_template=wn_template,
            sensors=sensors,
            obs=obs_heads,
            junction_names=junctions,
            cfg=cfg,
            scratch=scratch,
            base_demands_m3s=bases,
            leak_node=leak_node,
            include_leak=include_leak,
        )

    # Multi-start: nominal + mild demand bumps (keeps synthetic stage cheap).
    starts = [x0.copy()]
    for j in range(min(3, n_j)):
        xs = x0.copy()
        xs[j] = 0.5
        starts.append(xs)
    if include_leak:
        xs = x0.copy()
        xs[-1] = 2.0
        starts.append(xs)

    best_x = x0
    best_J = float("inf")
    best_msg = "init"
    ok = False
    for xs in starts:
        res = minimize(fun, xs, method="L-BFGS-B", bounds=bounds, options={"maxiter": 40, "ftol": 1e-9})
        if res.fun < best_J:
            best_J = float(res.fun)
            best_x = np.asarray(res.x, dtype=float)
            best_msg = str(res.message)
            ok = bool(res.success) or best_J < 1e5

    deltas = {junctions[i]: float(best_x[i]) for i in range(n_j)}
    rho = float(best_x[n_j])
    leak_m3h = float(best_x[n_j + 1]) if include_leak else 0.0
    pred = predict_heads(
        wn_template,
        sensors,
        deltas_m3h=deltas,
        rho=rho,
        leak_node=leak_node if include_leak else None,
        leak_m3h=leak_m3h if include_leak else 0.0,
        scratch=scratch,
        base_demands_m3s=bases,
    )
    resid = sum((pred[s] - float(obs_heads[s])) ** 2 for s in sensors)
    return FitResult(
        junction_names=junctions,
        deltas_m3h=deltas,
        rho=rho,
        leak_node=leak_node if include_leak else None,
        leak_m3h=leak_m3h if include_leak else 0.0,
        pred_heads=pred,
        J=best_J,
        residual_ss=float(resid),
        success=ok,
        message=best_msg,
    )


def decide_hypothesis(
    wn_template: wntr.network.WaterNetworkModel,
    sensors: Sequence[str],
    obs_heads: Mapping[str, float],
    candidates: Sequence[str],
    *,
    cfg: HypothesisConfig,
    scratch: Path,
) -> HypothesisDecision:
    fit0 = fit_hypothesis(wn_template, sensors, obs_heads, cfg=cfg, scratch=scratch, leak_node=None)
    fits1: dict[str, FitResult] = {}
    for c in candidates:
        fits1[c] = fit_hypothesis(
            wn_template, sensors, obs_heads, cfg=cfg, scratch=scratch, leak_node=c
        )

    best_c = min(fits1, key=lambda c: fits1[c].J)
    fit1 = fits1[best_c]
    delta_J = float(fit0.J - fit1.J)
    penalty = float(cfg.pi0_m2 * len(sensors))
    threshold = penalty + float(cfg.tau_dev)
    region = sorted(
        c for c, f in fits1.items() if f.J <= fit1.J + cfg.region_eps_m2
    )

    reasons: list[str] = []
    decision = "no_new_leak"

    # Ambiguity: H0 demand at best node ≈ H1 leak mass and improvement weak.
    d0 = float(fit0.deltas_m3h.get(best_c, 0.0))
    q1 = float(fit1.leak_m3h)
    demand_leak_swap = (
        q1 >= cfg.q_min_m3h
        and abs(d0 - q1) <= cfg.ambiguity_delta_q_m3h
        and delta_J <= threshold + cfg.clear_margin_extra
    )

    if demand_leak_swap:
        decision = "inconclusive"
        reasons.append("demand_leak_swap_at_best_candidate")
    elif delta_J <= 1e-6 and q1 < cfg.q_min_m3h:
        # Matched null / no useful leak mass — prefer H0 explicitly.
        decision = "no_new_leak"
        reasons.append("near_null_deltaJ_and_leak_below_qmin")
    elif 0.0 < delta_J <= threshold:
        decision = "inconclusive"
        reasons.append("improvement_inside_ambiguity_band")
    elif delta_J > threshold and q1 >= cfg.q_min_m3h:
        # Uninformative region with marginal improvement → inconclusive
        if len(region) >= max(2, (len(candidates) + 1) // 2) and delta_J <= threshold + cfg.clear_margin_extra:
            decision = "inconclusive"
            reasons.append("uninformative_candidate_region")
        else:
            decision = "leak"
            reasons.append("deltaJ_exceeds_penalty_and_qmin")
    else:
        decision = "no_new_leak"
        reasons.append("H0_preferred_or_leak_below_qmin")

    return HypothesisDecision(
        decision=decision,
        J_H0=float(fit0.J),
        J_H1=float(fit1.J),
        delta_J=delta_J,
        penalty=penalty,
        tau_dev=float(cfg.tau_dev),
        best_candidate=best_c,
        leak_m3h=q1,
        candidate_region=region,
        region_size=len(region),
        fit_H0=fit0,
        fit_H1_by_candidate=fits1,
        reasons=reasons,
    )


def decision_to_dict(d: HypothesisDecision) -> dict[str, Any]:
    return {
        "decision": d.decision,
        "J_H0": d.J_H0,
        "J_H1": d.J_H1,
        "delta_J": d.delta_J,
        "penalty": d.penalty,
        "tau_dev": d.tau_dev,
        "best_candidate": d.best_candidate,
        "leak_m3h": d.leak_m3h,
        "candidate_region": d.candidate_region,
        "region_size": d.region_size,
        "reasons": d.reasons,
        "H0_deltas_m3h": d.fit_H0.deltas_m3h,
        "H0_rho": d.fit_H0.rho,
        "H1_deltas_m3h": d.fit_H1_by_candidate[d.best_candidate].deltas_m3h
        if d.best_candidate
        else {},
        "H1_rho": d.fit_H1_by_candidate[d.best_candidate].rho if d.best_candidate else None,
    }
