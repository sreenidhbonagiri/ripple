"""Baselines for comparable synthetic tasks: dual signature + Method M–style score.

Does not retune frozen Method M product constants on measured data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .dual_builder import DualModelSpec
from .simulate import run_dual_steady, summarize_qv


# Frozen five-minute Method M τ (product/research freeze) — used only as a
# reference scale for the steady dual analogue, not re-estimated here.
METHOD_M_TAU_5MIN = 4.517
METHOD_M_CAL_SHA256 = "5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921"


def signature_match(
    wn_model,
    sensors: Sequence[str],
    obs_heads: Mapping[str, float],
    *,
    scratch: Path,
    tau_abs_sum_m3h: float,
) -> dict[str, Any]:
    """Dual signature: detect if |Σ q_v| > τ; localize argmax |q_v|."""
    spec = DualModelSpec(sensor_nodes=tuple(sensors), tcv_setting=1e-3)
    dual = run_dual_steady(wn_model, spec, obs_heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    qv = summary["q_v_m3h"]
    dominant = max(qv, key=lambda k: abs(qv[k]))
    abs_sum = abs(float(summary["sum_m3h"]))
    detect = abs_sum > float(tau_abs_sum_m3h)
    return {
        "method": "dual_signature",
        "sum_m3h": float(summary["sum_m3h"]),
        "abs_sum_m3h": abs_sum,
        "tau_abs_sum_m3h": float(tau_abs_sum_m3h),
        "detect": detect,
        "localized_node": dominant if detect else None,
        "q_v_m3h": qv,
    }


def method_m_style_steady(
    wn_model,
    sensors: Sequence[str],
    obs_heads: Mapping[str, float],
    *,
    scratch: Path,
    sigma_floor_m3h: float,
    tau: float = METHOD_M_TAU_5MIN,
) -> dict[str, Any]:
    """One-shot Method M analogue on steady dual residuals.

    score = max_s |q_v,s| / σ_floor  (SCALE≡1 for single snapshot).
    Comparable as anomaly-vs-control only — not BattLeDIM operating-point transfer.
    """
    spec = DualModelSpec(sensor_nodes=tuple(sensors), tcv_setting=1e-3)
    dual = run_dual_steady(wn_model, spec, obs_heads, scratch_dir=scratch)
    summary = summarize_qv(dual)
    qv = summary["q_v_m3h"]
    sigma = max(float(sigma_floor_m3h), 1e-6)
    scores = {k: abs(float(v)) / sigma for k, v in qv.items()}
    best = max(scores, key=scores.get)
    score = float(scores[best])
    detect = score >= float(tau)
    return {
        "method": "method_m_style_steady",
        "score": score,
        "tau": float(tau),
        "sigma_floor_m3h": sigma,
        "detect": detect,
        "localized_node": best if detect else None,
        "per_sensor_score": scores,
        "method_m_cal_sha256_ref": METHOD_M_CAL_SHA256,
        "note": "Steady dual analogue; not a claim of five-minute product parity on BattLeDIM.",
    }


def select_signature_tau(dev_rows: list[dict[str, Any]]) -> float:
    """Pick |Σq_v| threshold on dev: maximize TPR−FPR among a small grid."""
    # Collect abs sums with labels from rows that already have signature abs_sum.
    grid = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    best_tau, best_obj = grid[0], -1e9
    for tau in grid:
        tp = fp = n_pos = n_neg = 0
        for r in dev_rows:
            sig = r.get("baseline_signature") or {}
            if "abs_sum_m3h" not in sig:
                continue
            pred = sig["abs_sum_m3h"] > tau
            # Recompute detect at this tau
            pred = float(sig["abs_sum_m3h"]) > tau
            if r["has_new_leak"]:
                n_pos += 1
                tp += int(pred)
            else:
                n_neg += 1
                fp += int(pred)
        tpr = tp / n_pos if n_pos else 0.0
        fpr = fp / n_neg if n_neg else 0.0
        obj = tpr - fpr
        if obj > best_obj:
            best_obj, best_tau = obj, tau
    return float(best_tau)


def select_sigma_floor(train_control_abs_qv: list[float]) -> float:
    """Noise floor from train no-leak max|q_v| percentiles."""
    if not train_control_abs_qv:
        return 0.5
    return float(max(0.25, np.percentile(train_control_abs_qv, 75)))
