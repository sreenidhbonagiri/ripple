"""Causal multivariate features shared by synthetic and measured inputs.

No leak pipe identity, nearest-sensor selection, or future samples.
"""

from __future__ import annotations

import numpy as np

from schema import (
    FEATURE_CONFIG,
    FEATURE_SET_NAME,
    FLOW_SENSORS,
    LEVEL_SENSORS,
    PRESSURE_SENSORS,
    PUMP_ON_EPS,
    FeatureConfig,
)


def _causal_delta(x: np.ndarray, lag: int) -> np.ndarray:
    """x[t] - x[t-lag]; NaN for t < lag. x shape (T,) or (T, D)."""
    out = np.full_like(x, np.nan, dtype=np.float64)
    if lag <= 0:
        raise ValueError("lag must be positive")
    if x.ndim == 1:
        out[lag:] = x[lag:] - x[:-lag]
    else:
        out[lag:] = x[lag:] - x[:-lag]
    return out


def _nanpercentile_1d(a: np.ndarray, q: float) -> float:
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan")
    return float(np.percentile(a, q))


def feature_names(cfg: FeatureConfig = FEATURE_CONFIG) -> list[str]:
    names: list[str] = []
    # Pressure level summaries (network-wide; not location-weighted)
    names += [
        "P_median",
        "P_p10",
        "P_p90",
        "P_max",
        "P_min",
        "P_spread_p90_p10",
    ]
    for lag in cfg.delta_steps:
        tag = f"d{lag}"
        names += [
            f"Pd_{tag}_median",
            f"Pd_{tag}_p10",
            f"Pd_{tag}_p90",
            f"Pd_{tag}_min",  # most negative (pressure drop)
            f"Pd_{tag}_max_abs",
        ]
        for k in range(cfg.top_k_pressure_delta):
            names.append(f"Pd_{tag}_topneg{k+1}")  # k-th most negative delta
    # Flows / pump / tank (scalars + deltas)
    for fid in FLOW_SENSORS:
        names.append(f"F_{fid}")
        for lag in cfg.delta_steps:
            names.append(f"Fd_{fid}_d{lag}")
    names.append("pump1_on")
    for lid in LEVEL_SENSORS:
        names.append(f"L_{lid}")
        for lag in cfg.delta_steps:
            names.append(f"Ld_{lid}_d{lag}")
    if cfg.include_calendar:
        names += ["sin_tod", "cos_tod", "is_weekend"]
    return names


def build_feature_matrix(
    pressures: np.ndarray,
    flows: np.ndarray,
    levels: np.ndarray,
    *,
    cfg: FeatureConfig = FEATURE_CONFIG,
    timestamps_hour: np.ndarray | None = None,
    timestamps_weekday: np.ndarray | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Build (T, F) causal features.

    pressures: (T, 33) in meters
    flows: (T, 3) in m³/h, columns = FLOW_SENSORS
    levels: (T, 1) in meters, columns = LEVEL_SENSORS
    """
    pressures = np.asarray(pressures, dtype=np.float64)
    flows = np.asarray(flows, dtype=np.float64)
    levels = np.asarray(levels, dtype=np.float64)
    if pressures.ndim != 2 or pressures.shape[1] != len(PRESSURE_SENSORS):
        raise ValueError(f"pressures shape {pressures.shape} != (T, {len(PRESSURE_SENSORS)})")
    if flows.ndim != 2 or flows.shape[1] != len(FLOW_SENSORS):
        raise ValueError(f"flows shape {flows.shape} != (T, {len(FLOW_SENSORS)})")
    if levels.ndim != 2 or levels.shape[1] != len(LEVEL_SENSORS):
        raise ValueError(f"levels shape {levels.shape} != (T, {len(LEVEL_SENSORS)})")

    T = pressures.shape[0]
    names = feature_names(cfg)
    X = np.full((T, len(names)), np.nan, dtype=np.float64)
    col = {n: i for i, n in enumerate(names)}

    # Pressure summaries at t
    with np.errstate(all="ignore"):
        X[:, col["P_median"]] = np.nanmedian(pressures, axis=1)
        X[:, col["P_p10"]] = np.nanpercentile(pressures, 10, axis=1)
        X[:, col["P_p90"]] = np.nanpercentile(pressures, 90, axis=1)
        X[:, col["P_max"]] = np.nanmax(pressures, axis=1)
        X[:, col["P_min"]] = np.nanmin(pressures, axis=1)
        X[:, col["P_spread_p90_p10"]] = X[:, col["P_p90"]] - X[:, col["P_p10"]]

    for lag in cfg.delta_steps:
        tag = f"d{lag}"
        d = _causal_delta(pressures, lag)
        with np.errstate(all="ignore"):
            # nanmedian/nanmin warn on all-NaN warm-up rows; values stay NaN.
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                X[:, col[f"Pd_{tag}_median"]] = np.nanmedian(d, axis=1)
                X[:, col[f"Pd_{tag}_p10"]] = np.nanpercentile(d, 10, axis=1)
                X[:, col[f"Pd_{tag}_p90"]] = np.nanpercentile(d, 90, axis=1)
                X[:, col[f"Pd_{tag}_min"]] = np.nanmin(d, axis=1)
                X[:, col[f"Pd_{tag}_max_abs"]] = np.nanmax(np.abs(d), axis=1)
            # top-k most negative (pressure drops) — values only, no sensor ids
            # argsort ascending → most negative first
            order = np.argsort(np.where(np.isfinite(d), d, np.inf), axis=1)
            for k in range(cfg.top_k_pressure_delta):
                idx = order[:, k]
                vals = d[np.arange(T), idx]
                # if non-finite source, leave nan
                bad = ~np.isfinite(d[np.arange(T), idx])
                vals = vals.astype(np.float64)
                vals[bad] = np.nan
                X[:, col[f"Pd_{tag}_topneg{k+1}"]] = vals

    for j, fid in enumerate(FLOW_SENSORS):
        X[:, col[f"F_{fid}"]] = flows[:, j]
        for lag in cfg.delta_steps:
            X[:, col[f"Fd_{fid}_d{lag}"]] = _causal_delta(flows[:, j], lag)
    pump = flows[:, FLOW_SENSORS.index("PUMP_1")]
    X[:, col["pump1_on"]] = (pump > PUMP_ON_EPS).astype(np.float64)

    for j, lid in enumerate(LEVEL_SENSORS):
        X[:, col[f"L_{lid}"]] = levels[:, j]
        for lag in cfg.delta_steps:
            X[:, col[f"Ld_{lid}_d{lag}"]] = _causal_delta(levels[:, j], lag)

    if cfg.include_calendar:
        if timestamps_hour is None or timestamps_weekday is None:
            raise ValueError("calendar features require timestamps_hour/weekday")
        hour = np.asarray(timestamps_hour, dtype=np.float64)
        X[:, col["sin_tod"]] = np.sin(2 * np.pi * hour / 24.0)
        X[:, col["cos_tod"]] = np.cos(2 * np.pi * hour / 24.0)
        X[:, col["is_weekend"]] = (np.asarray(timestamps_weekday) >= 5).astype(np.float64)

    return X, names


def feature_manifest(cfg: FeatureConfig = FEATURE_CONFIG) -> dict:
    return {
        "feature_set": FEATURE_SET_NAME,
        "n_features": len(feature_names(cfg)),
        "names": feature_names(cfg),
        "pressure_sensors": list(PRESSURE_SENSORS),
        "flow_sensors": list(FLOW_SENSORS),
        "level_sensors": list(LEVEL_SENSORS),
        "delta_steps": list(cfg.delta_steps),
        "top_k_pressure_delta": cfg.top_k_pressure_delta,
        "include_calendar": cfg.include_calendar,
        "warm_up_steps": cfg.warm_up_steps,
        "forbidden": [
            "true_leak_pipe_id",
            "nearest_sensor_to_leak",
            "future_observations",
            "2019_labels_in_features",
        ],
        "units": {
            "pressure": "m",
            "flow": "m3/h",
            "tank_level": "m",
        },
    }
