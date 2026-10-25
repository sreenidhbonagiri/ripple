"""Select (C, τ) on synthetic DEV using episode-notification metrics.

Uses the same C_GRID / TAU_GRID / L2 logistic / StandardScaler as train_pilot.
Does not expand the candidate budget.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from episode_metrics import evaluate_split_episodes
from train_pilot import C_GRID, FEATURE_SET, TAU_GRID

GATE_RECALL = 2.0 / 3.0
GATE_CTRL_EP_PER_WEEK = 3.0

SELECTION_RULE = (
    "on synthetic_dev full trajectories: among (C,τ) with "
    f"episode_6h_recall>={GATE_RECALL:g} and control_episodes_per_week<={GATE_CTRL_EP_PER_WEEK:g}, "
    "max episode_6h_recall, then min control_episodes_per_week, then min median_delay_h, "
    "then min C, then min τ. If no candidate passes gates: report selection_failure=true "
    "and freeze rank-best under the same ordering without gates (gate_met=false)."
)


def _rank_key(rec: dict) -> tuple:
    """Higher is better under the declared selection ordering."""
    recall = rec["episode_6h_recall"]
    burden = rec["control_episodes_per_week"]
    delay = rec.get("median_delay_h")
    delay_key = delay if delay is not None and np.isfinite(delay) else 1e9
    recall_f = recall if np.isfinite(recall) else -1.0
    burden_f = burden if np.isfinite(burden) else 1e9
    return (
        recall_f,
        -burden_f,
        -delay_key,
        -float(rec["C"]),
        -float(rec["tau"]),
    )


def fit_select_episode(
    train: dict,
    sim_dir: Path,
    manifest: dict,
    assignments: dict[str, str],
) -> dict:
    Xtr, ytr = train["X"], train["y"]
    if Xtr.shape[0] < 50 or ytr.sum() < 5:
        raise RuntimeError(
            f"insufficient train rows/positives: n={Xtr.shape[0]} pos={int(ytr.sum())}"
        )

    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)

    by_C: dict[float, dict] = {}
    for C in C_GRID:
        clf = LogisticRegression(
            C=C,
            class_weight="balanced",
            solver="lbfgs",
            max_iter=2000,
            random_state=0,
        )
        clf.fit(Xtr_s, ytr)
        by_C[C] = {
            "coef": clf.coef_.ravel().tolist(),
            "intercept": float(clf.intercept_[0]),
        }

    records = []
    for C in C_GRID:
        frozen_C = {
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "coef": by_C[C]["coef"],
            "intercept": by_C[C]["intercept"],
            "selected": {"C": C, "tau": TAU_GRID[0]},  # tau overwritten per eval
        }
        for tau in TAU_GRID:
            summary = evaluate_split_episodes(
                sim_dir,
                manifest,
                assignments,
                "synthetic_dev",
                frozen_C,
                tau=tau,
            )
            # Drop heavy per-scenario lists from grid records (kept in final eval)
            rec = {
                "C": C,
                "tau": tau,
                "episode_6h_recall": summary["episode_6h_recall"],
                "n_episode_6h_hit": summary["n_episode_6h_hit"],
                "n_leak_scenarios": summary["n_leak_scenarios"],
                "median_delay_h": summary["median_delay_h"],
                "control_episodes_per_week": summary["control_episodes_per_week"],
                "n_control_episodes": summary["n_control_episodes"],
                "n_control_scenarios": summary["n_control_scenarios"],
                "row_credit_scenario_recall": summary["row_credit_scenario_recall"],
                "n_row_vs_episode_disagree": summary["n_row_vs_episode_disagree"],
                "n_blocked_by_preonset_active": summary["n_blocked_by_preonset_active"],
                "gate_recall_ok": bool(
                    np.isfinite(summary["episode_6h_recall"])
                    and summary["episode_6h_recall"] >= GATE_RECALL
                ),
                "gate_burden_ok": bool(
                    np.isfinite(summary["control_episodes_per_week"])
                    and summary["control_episodes_per_week"] <= GATE_CTRL_EP_PER_WEEK
                ),
            }
            rec["gate_met"] = rec["gate_recall_ok"] and rec["gate_burden_ok"]
            records.append(rec)

    gated = [r for r in records if r["gate_met"]]
    selection_failure = len(gated) == 0
    pool = gated if gated else records
    best = max(pool, key=_rank_key)

    C_sel = float(best["C"])
    tau_sel = float(best["tau"])
    # Refit selected C on train (deterministic; same as by_C)
    clf = LogisticRegression(
        C=C_sel,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        random_state=0,
    )
    clf.fit(Xtr_s, ytr)

    return {
        "feature_set": FEATURE_SET,
        "selected": {"C": C_sel, "tau": tau_sel},
        "gate_met": bool(best["gate_met"]),
        "selection_failure": selection_failure,
        "dev_metrics": {
            k: best[k]
            for k in (
                "episode_6h_recall",
                "n_episode_6h_hit",
                "n_leak_scenarios",
                "median_delay_h",
                "control_episodes_per_week",
                "n_control_episodes",
                "n_control_scenarios",
                "row_credit_scenario_recall",
                "n_row_vs_episode_disagree",
                "n_blocked_by_preonset_active",
                "gate_met",
            )
        },
        "grid_records": records,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": clf.coef_.ravel().tolist(),
        "intercept": float(clf.intercept_[0]),
        "n_train": int(Xtr.shape[0]),
        "n_train_pos": int(ytr.sum()),
        "budget": {
            "C_grid": C_GRID,
            "tau_grid": TAU_GRID,
            "feature_sets": [FEATURE_SET],
        },
        "selection_rule": SELECTION_RULE,
        "gates": {
            "episode_6h_recall_min": GATE_RECALL,
            "control_episodes_per_week_max": GATE_CTRL_EP_PER_WEEK,
        },
        "label_note": (
            "y=1 is the registered 6h recent-onset credit window, not ongoing "
            "leak presence. Labels unchanged for this controlled comparison."
        ),
    }
