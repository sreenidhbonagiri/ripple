"""Row-hit inside the credit window ≠ episode-notification 6h hit."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from episode_metrics import analyze_leak_scenario
from notifications import RECOVER_STEPS, episodes_from_scores
from schema import STEPS_PER_HOUR


def test_row_hit_while_episode_already_active_is_not_new_detection():
    """Pre-onset latch stays active through onset → row credit without notify credit."""
    T = 200
    onset = 100
    credit = 6 * STEPS_PER_HOUR
    y = np.zeros(T, dtype=bool)
    y[onset : onset + credit] = True

    # Notify well before onset; stay high through the credit window (no recovery).
    q = np.full(T, 0.1, dtype=np.float64)
    q[80:] = 0.9  # active from t=80 through end
    tau = 0.5

    eps = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
    assert len(eps) == 1
    assert eps[0].notify_idx == 80
    assert eps[0].notify_idx < onset

    info = analyze_leak_scenario(q, y, tau=tau)
    assert info["row_credit_hit"] is True
    assert info["episode_6h_hit"] is False
    assert info["row_vs_episode_disagree"] is True
    assert info["blocked_by_preonset_active"] is True
    assert info["notifies_in_credit"] == []


def test_fresh_notify_inside_credit_window_is_episode_hit():
    T = 200
    onset = 100
    credit = 6 * STEPS_PER_HOUR
    y = np.zeros(T, dtype=bool)
    y[onset : onset + credit] = True

    q = np.full(T, 0.1, dtype=np.float64)
    q[onset + 6 :] = 0.9  # first crossing after onset
    tau = 0.5

    info = analyze_leak_scenario(q, y, tau=tau)
    assert info["episode_6h_hit"] is True
    assert info["row_credit_hit"] is True
    assert info["row_vs_episode_disagree"] is False
    assert info["delay_hours"] == 6 / STEPS_PER_HOUR
    assert not info["blocked_by_preonset_active"]


def test_preonset_notify_gets_no_onset_credit_even_if_rows_later_cross():
    """After pre-onset notify, recovery then re-notify after credit window ends."""
    T = 300
    onset = 100
    credit = 6 * STEPS_PER_HOUR
    y = np.zeros(T, dtype=bool)
    y[onset : onset + credit] = True

    q = np.full(T, 0.05, dtype=np.float64)
    # Pre-onset episode
    q[40:55] = 0.9
    # Recover fully (12 steps below tau/2)
    q[55:80] = 0.05
    # High again only after credit window (onset+72 = 172)
    q[onset + credit + 5 :] = 0.9
    # Also: during credit, rows would count if we only looked at q>=tau & y —
    # keep q low in credit so this case isolates "no notify in window".
    tau = 0.5

    info = analyze_leak_scenario(q, y, tau=tau)
    assert info["episode_6h_hit"] is False
    assert info["row_credit_hit"] is False
    assert info["preonset_notifies"] == [40]


def test_positive_rows_during_active_episode_are_not_new_detection():
    """Onset notify once; sustained high q through positives → one episode only."""
    T = 200
    onset = 50
    credit = 6 * STEPS_PER_HOUR
    y = np.zeros(T, dtype=bool)
    y[onset : onset + credit] = True

    q = np.full(T, 0.1, dtype=np.float64)
    q[onset:] = 0.95
    tau = 0.5

    eps = episodes_from_scores(q, tau=tau)
    assert len(eps) == 1
    assert eps[0].notify_idx == onset

    info = analyze_leak_scenario(q, y, tau=tau)
    assert info["episode_6h_hit"] is True
    assert info["n_episodes"] == 1
    # Many positive rows above tau, but still a single notification episode
    assert int(((q >= tau) & y).sum()) > 1
