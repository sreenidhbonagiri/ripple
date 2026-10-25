"""Registered paired arms for the change-only feature ablation."""

from __future__ import annotations

from features import feature_names

# Absolute operating-state / level proxies removed in Arm B (protocol §Arms).
ARM_B_REMOVED: list[str] = [
    "P_median",
    "P_p10",
    "P_p90",
    "P_max",
    "P_min",
    "F_p227",
    "F_p235",
    "F_PUMP_1",
    "L_T1",
    "pump1_on",
]

PUMP_CHANGE_FEATURES: list[str] = [
    "Fd_PUMP_1_d1",
    "Fd_PUMP_1_d6",
    "Fd_PUMP_1_d24",
]


def arm_a_names() -> list[str]:
    return list(feature_names())


def arm_b_names() -> list[str]:
    full = feature_names()
    removed = set(ARM_B_REMOVED)
    missing = removed - set(full)
    if missing:
        raise RuntimeError(f"Arm B removed names not in builder: {sorted(missing)}")
    return [n for n in full if n not in removed]


def column_indices(all_names: list[str], keep: list[str]) -> list[int]:
    idx_map = {n: i for i, n in enumerate(all_names)}
    try:
        return [idx_map[n] for n in keep]
    except KeyError as e:
        raise KeyError(f"feature missing from matrix: {e}") from e


def subset_X(X, all_names: list[str], keep: list[str]):
    import numpy as np

    idx = column_indices(all_names, keep)
    # Fancy indexing yields non-contiguous arrays; sklearn/BLAS paths can
    # then produce different LogisticRegression solutions for identical values.
    return np.ascontiguousarray(np.asarray(X, dtype=np.float64)[:, idx])


def arm_registry() -> dict:
    a = arm_a_names()
    b = arm_b_names()
    return {
        "arm_A": {
            "id": "arm_A",
            "label": "full_pressure_context_v1",
            "n_features": len(a),
            "feature_names": a,
            "removed": [],
        },
        "arm_B": {
            "id": "arm_B",
            "label": "change_residual_only",
            "n_features": len(b),
            "feature_names": b,
            "removed": list(ARM_B_REMOVED),
        },
        "n_full": len(a),
        "note": (
            "Arm B drops absolute P/F/L levels and pump1_on; retains Pd_*/Fd_*/Ld_* "
            "and P_spread_p90_p10. No new features."
        ),
    }
