"""Episode-notification metrics on full synthetic trajectories.

Shared notifier: notifications.episodes_from_scores (threshold / τ/2 recovery).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from features import build_feature_matrix
from notifications import RECOVER_STEPS, episodes_from_scores
from simulate import DURATION_HOURS
from train_pilot import predict_proba
from schema import STEPS_PER_HOUR

CREDIT_HOURS = 6.0
CREDIT_STEPS = int(CREDIT_HOURS * STEPS_PER_HOUR)
SCENARIO_WEEKS = DURATION_HOURS / (24.0 * 7.0)


def score_full_trajectory(pressures, flows, levels, frozen: dict) -> np.ndarray:
    """Causal q(t) on the full scenario; NaN where features incomplete."""
    X, _ = build_feature_matrix(pressures, flows, levels)
    q = np.full(X.shape[0], np.nan, dtype=np.float64)
    ok = np.all(np.isfinite(X), axis=1)
    if ok.any():
        q[ok] = predict_proba(frozen, X[ok])
    return q


def onset_index_from_labels(y: np.ndarray) -> int | None:
    y = np.asarray(y, dtype=bool)
    if not y.any():
        return None
    return int(np.argmax(y))


def analyze_leak_scenario(q: np.ndarray, y: np.ndarray, *, tau: float) -> dict:
    """Full-trajectory episodes; 6h notify credit; blocking diagnostics."""
    y = np.asarray(y, dtype=bool)
    onset = onset_index_from_labels(y)
    episodes = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
    if onset is None:
        return {
            "has_onset": False,
            "episode_6h_hit": False,
            "row_credit_hit": bool((np.isfinite(q) & (q >= tau) & y).any()),
            "n_episodes": len(episodes),
            "delay_hours": None,
            "blocked_by_preonset_active": False,
            "preonset_notifies": [],
            "notifies_in_credit": [],
            "episodes": [],
            "row_vs_episode_disagree": False,
        }

    hi = onset + CREDIT_STEPS
    credit_notifies = []
    preonset = []
    for ep in episodes:
        if ep.notify_idx < onset:
            preonset.append(int(ep.notify_idx))
        elif onset <= ep.notify_idx <= hi:
            credit_notifies.append(
                {
                    "notify_idx": int(ep.notify_idx),
                    "delay_hours": float((ep.notify_idx - onset) / STEPS_PER_HOUR),
                    "end_idx": int(ep.end_idx),
                }
            )

    blocked = any(ep.notify_idx < onset <= ep.end_idx for ep in episodes)
    row_hit = bool((np.isfinite(q) & (q >= tau) & y).any())
    hit = len(credit_notifies) > 0
    delay = min(c["delay_hours"] for c in credit_notifies) if credit_notifies else None

    return {
        "has_onset": True,
        "onset_idx": onset,
        "credit_end_idx": int(hi),
        "episode_6h_hit": hit,
        "row_credit_hit": row_hit,
        "row_vs_episode_disagree": bool(row_hit) != bool(hit),
        "delay_hours": delay,
        "blocked_by_preonset_active": blocked,
        "preonset_notifies": preonset,
        "notifies_in_credit": credit_notifies,
        "n_episodes": len(episodes),
        "episodes": [
            {
                "notify_idx": int(e.notify_idx),
                "end_idx": int(e.end_idx),
                "peak_score": float(e.peak_score),
            }
            for e in episodes
        ],
    }


def analyze_control_scenario(q: np.ndarray, *, tau: float) -> dict:
    episodes = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
    return {
        "n_episodes": len(episodes),
        "notify_idxs": [int(e.notify_idx) for e in episodes],
    }


def _summarize_split(leak_rows, ctrl_rows, *, tau: float, split: str) -> dict:
    n_leak = len(leak_rows)
    n_hit = sum(1 for r in leak_rows if r.get("episode_6h_hit"))
    delays = [r["delay_hours"] for r in leak_rows if r.get("delay_hours") is not None]
    n_row_hit = sum(1 for r in leak_rows if r.get("row_credit_hit"))
    n_disagree = sum(1 for r in leak_rows if r.get("row_vs_episode_disagree"))
    n_blocked = sum(1 for r in leak_rows if r.get("blocked_by_preonset_active"))
    n_ctrl = len(ctrl_rows)
    n_ctrl_eps = sum(r["n_episodes"] for r in ctrl_rows)
    weeks = n_ctrl * SCENARIO_WEEKS if n_ctrl else float("nan")
    ctrl_ep_per_week = (n_ctrl_eps / weeks) if weeks and weeks > 0 else float("nan")
    n_leak_eps = sum(r.get("n_episodes", 0) for r in leak_rows)
    leak_weeks = n_leak * SCENARIO_WEEKS if n_leak else float("nan")
    return {
        "split": split,
        "tau": tau,
        "n_leak_scenarios": n_leak,
        "episode_6h_recall": (n_hit / n_leak) if n_leak else float("nan"),
        "n_episode_6h_hit": n_hit,
        "median_delay_h": float(np.median(delays)) if delays else None,
        "delays_h": delays,
        "row_credit_scenario_recall": (n_row_hit / n_leak) if n_leak else float("nan"),
        "n_row_credit_hit": n_row_hit,
        "n_row_vs_episode_disagree": n_disagree,
        "n_blocked_by_preonset_active": n_blocked,
        "n_control_scenarios": n_ctrl,
        "n_control_episodes": n_ctrl_eps,
        "control_episodes_per_week": ctrl_ep_per_week,
        "n_leak_scenario_episodes": n_leak_eps,
        "leak_episodes_per_week": (n_leak_eps / leak_weeks) if leak_weeks else float("nan"),
        "per_leak": leak_rows,
        "per_control": ctrl_rows,
        "label_note": (
            "y=1 is the registered 6h recent-onset credit window, not ongoing leak presence."
        ),
    }


def evaluate_split_episodes(
    sim_dir: Path,
    manifest: dict,
    assignments: dict[str, str],
    split: str,
    frozen: dict,
    *,
    tau: float | None = None,
) -> dict:
    tau = float(frozen["selected"]["tau"] if tau is None else tau)
    leak_rows = []
    ctrl_rows = []
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        sid = sc["spec"]["scenario_id"]
        if assignments.get(sid) != split:
            continue
        arr = np.load(sim_dir / sc["npz"])
        q = score_full_trajectory(
            arr["pressures"], arr["flows"], arr["levels"], frozen
        )
        if sc["spec"]["kind"] == "leak_abrupt":
            info = analyze_leak_scenario(q, arr["labels_abrupt_positive"], tau=tau)
            leak_rows.append({"scenario_id": sid, "pipe": sc["spec"]["pipe"], **info})
        elif sc["spec"]["kind"].startswith("control"):
            ctrl_rows.append(
                {
                    "scenario_id": sid,
                    "kind": sc["spec"]["kind"],
                    **analyze_control_scenario(q, tau=tau),
                }
            )
    return _summarize_split(leak_rows, ctrl_rows, tau=tau, split=split)
