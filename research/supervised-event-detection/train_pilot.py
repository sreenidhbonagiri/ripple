"""Fit one L2 logistic classifier under the registered small budget."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Registered budget (DESIGN.md §8) — do not expand because synthetic looks good
C_GRID = [0.01, 0.1, 1.0, 10.0, 100.0]  # ≤5
TAU_GRID = [0.3, 0.5, 0.7, 0.85, 0.95]  # probability threshold ≤5
FEATURE_SET = "pressure_context_v1"  # single pre-declared set for pilot


def _scenario_metrics(y_true, y_prob, scenario_ids, tau: float) -> dict:
    """Simple synthetic dev metric: row recall/precision at tau + scenario hit rate."""
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    pred = y_prob >= tau
    pos = y_true == 1
    hit = pred & pos
    recall = float(hit.sum() / pos.sum()) if pos.any() else float("nan")
    prec = float(hit.sum() / pred.sum()) if pred.any() else float("nan")
    # Scenario-level: fraction of leak scenarios with ≥1 positive-row hit in credit window
    scen_hit = {}
    for sid in sorted(set(scenario_ids)):
        m = np.array([s == sid for s in scenario_ids])
        if not (y_true[m] == 1).any():
            continue  # control scenario
        scen_hit[sid] = bool(((y_prob[m] >= tau) & (y_true[m] == 1)).any())
    scen_recall = float(np.mean(list(scen_hit.values()))) if scen_hit else float("nan")
    fp_rate = float((pred & ~pos).mean()) if pred.size else float("nan")
    return {
        "row_recall": recall,
        "row_precision": prec,
        "scenario_recall": scen_recall,
        "n_leak_scenarios_eval": len(scen_hit),
        "fp_row_rate": fp_rate,
        "n_pred": int(pred.sum()),
        "n_pos": int(pos.sum()),
    }


def fit_select(train: dict, dev: dict) -> dict:
    Xtr, ytr = train["X"], train["y"]
    Xdv, ydv = dev["X"], dev["y"]
    if Xtr.shape[0] < 50 or ytr.sum() < 5:
        raise RuntimeError(
            f"insufficient train rows/positives: n={Xtr.shape[0]} pos={int(ytr.sum())}"
        )

    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)
    Xdv_s = scaler.transform(Xdv)

    records = []
    best = None
    for C in C_GRID:
        clf = LogisticRegression(
            C=C,
            class_weight="balanced",
            solver="lbfgs",
            max_iter=2000,
            random_state=0,
        )
        clf.fit(Xtr_s, ytr)
        prob_dv = clf.predict_proba(Xdv_s)[:, 1]
        for tau in TAU_GRID:
            m = _scenario_metrics(ydv, prob_dv, dev["scenario_ids"], tau)
            row = {"C": C, "tau": tau, **m}
            records.append(row)
            # Selection: max scenario_recall, then max row_recall, then min fp_row_rate
            key = (
                m["scenario_recall"] if np.isfinite(m["scenario_recall"]) else -1,
                m["row_recall"] if np.isfinite(m["row_recall"]) else -1,
                -(m["fp_row_rate"] if np.isfinite(m["fp_row_rate"]) else 1),
                -C,
                -tau,
            )
            if best is None or key > best["key"]:
                best = {
                    "key": key,
                    "C": C,
                    "tau": tau,
                    "metrics_dev": m,
                    "coef": clf.coef_.ravel().tolist(),
                    "intercept": float(clf.intercept_[0]),
                }

    assert best is not None
    # Refit selected C on train only (tau is notification threshold, not fit param)
    clf = LogisticRegression(
        C=best["C"],
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        random_state=0,
    )
    clf.fit(Xtr_s, ytr)
    return {
        "feature_set": FEATURE_SET,
        "selected": {"C": best["C"], "tau": best["tau"]},
        "dev_metrics": best["metrics_dev"],
        "grid_records": records,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": clf.coef_.ravel().tolist(),
        "intercept": float(clf.intercept_[0]),
        "n_train": int(Xtr.shape[0]),
        "n_train_pos": int(ytr.sum()),
        "n_dev": int(Xdv.shape[0]),
        "n_dev_pos": int(ydv.sum()),
        "budget": {"C_grid": C_GRID, "tau_grid": TAU_GRID, "feature_sets": [FEATURE_SET]},
        "selection_rule": (
            "on synthetic_dev: max scenario_recall, then row_recall, then min fp_row_rate"
        ),
    }


def predict_proba(frozen: dict, X: np.ndarray) -> np.ndarray:
    mean = np.asarray(frozen["scaler_mean"], dtype=np.float64)
    scale = np.asarray(frozen["scaler_scale"], dtype=np.float64)
    scale = np.where(scale < 1e-12, 1.0, scale)
    Xs = (X - mean) / scale
    coef = np.asarray(frozen["coef"], dtype=np.float64)
    logit = Xs @ coef + float(frozen["intercept"])
    # stable sigmoid
    return 1.0 / (1.0 + np.exp(-np.clip(logit, -50, 50)))


def evaluate_synthetic_split(frozen: dict, split: dict) -> dict:
    if split["n_rows"] == 0:
        return {"empty": True}
    prob = predict_proba(frozen, split["X"])
    tau = frozen["selected"]["tau"]
    m = _scenario_metrics(split["y"], prob, split["scenario_ids"], tau)
    return {"empty": False, "tau": tau, **m}
