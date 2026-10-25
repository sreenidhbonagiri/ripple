"""Hazen–Williams cluster calibration (box-constrained least squares).

Paper: projected Levenberg–Marquardt + Huber on week-1 pressures, κ=3, α=0,
bounds [60, 160]. We use ``scipy.optimize.least_squares`` (Trust Region Reflective)
with the same bounds and a Huber-like soft-L1 loss — departure: not a hand-rolled
LM with analytical hydraulic Jacobian (WNTR finite-difference / residual only).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import wntr
from scipy.optimize import least_squares

from .area_topology import RoughnessCluster, apply_cluster_roughness, build_roughness_clusters
from .demand_calibration import DemandModel
from .ltown_hydraulics import run_primal_window
from .area_topology import load_pressure_sensors


@dataclass
class RoughnessFitResult:
    values: dict[str, float]
    x0: dict[str, float]
    bounds: tuple[float, float]
    rmse_m: float
    success: bool
    nfev: int
    active_bounds: dict[str, str]
    cluster_sizes: dict[str, int]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fit_roughness_clusters(
    wn_template: wntr.network.WaterNetworkModel,
    timestamps: pd.DatetimeIndex,
    pressures_m: pd.DataFrame,
    levels_m: pd.Series,
    demand_model: DemandModel,
    amr_lh: pd.DataFrame,
    scratch: Path,
    *,
    bounds: tuple[float, float] = (60.0, 160.0),
    max_nfev: int = 25,
    subsample_stride: int = 2,
) -> RoughnessFitResult:
    """Fit cluster HW coefficients on FIT window (hourly series)."""
    clusters = build_roughness_clusters(wn_template)
    sensors = load_pressure_sensors()
    # Subsample timestamps for residual speed
    ts = timestamps[::subsample_stride]
    P_meas = pressures_m[list(sensors)].reindex(ts).interpolate(limit=1)
    lvl = levels_m.reindex(ts).interpolate(limit=1)
    amr = amr_lh.reindex(ts)

    x0 = np.array([cl.x0 for cl in clusters], dtype=float)
    names = [cl.name for cl in clusters]
    lo, hi = bounds
    lb = np.full_like(x0, lo)
    ub = np.full_like(x0, hi)

    def pack(x: np.ndarray) -> dict[str, float]:
        return {n: float(v) for n, v in zip(names, x)}

    def residuals(x: np.ndarray) -> np.ndarray:
        run = run_primal_window(
            wn_template,
            ts,
            demand_model=demand_model,
            amr_lh=amr,
            levels_m=lvl,
            scratch=scratch,
            roughness=pack(x),
            clusters=clusters,
            timestep_sec=int((ts[1] - ts[0]).total_seconds()) if len(ts) > 1 else 3600,
        )
        if not run.converged:
            return np.full(len(ts) * len(sensors), 1e3)
        err = (run.pressure_m[list(sensors)] - P_meas.loc[run.pressure_m.index]).values.ravel()
        err = err[np.isfinite(err)]
        if err.size == 0:
            return np.array([1e3])
        return err

    result = least_squares(
        residuals,
        x0,
        bounds=(lb, ub),
        loss="soft_l1",
        f_scale=3.0,  # κ≈3 m pressure (paper Huber κ=3 with σ=1)
        max_nfev=max_nfev,
        verbose=0,
    )
    vals = pack(result.x)
    # Final RMSE
    final = residuals(result.x)
    rmse = float(np.sqrt(np.mean(final**2))) if final.size else float("nan")
    active = {}
    for n, v in vals.items():
        if abs(v - lo) < 1e-6:
            active[n] = "lower"
        elif abs(v - hi) < 1e-6:
            active[n] = "upper"
        else:
            active[n] = "interior"

    return RoughnessFitResult(
        values=vals,
        x0={cl.name: cl.x0 for cl in clusters},
        bounds=bounds,
        rmse_m=rmse,
        success=bool(result.success),
        nfev=int(result.nfev),
        active_bounds=active,
        cluster_sizes={cl.name: len(cl.pipe_names) for cl in clusters},
        message=str(result.message),
    )