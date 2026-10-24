"""Causality and missing-history checks for the research detector."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import (  # noqa: E402
    STEPS_30M,
    STEPS_PER_WEEK,
    build_episodes,
    raw_drop_scores,
    week_residual_scores,
)
from evaluate import select_baseline_tau, select_residual_tau  # noqa: E402
from evaluate import PeriodMetrics  # noqa: E402


def _synthetic_pressures(t: int = 3000, s: int = 4) -> np.ndarray:
    rng = np.random.default_rng(0)
    base = 40 + rng.normal(0, 0.05, size=(t, s)).cumsum(axis=0) * 0.0 + 40
    # mild diurnal-ish wave
    wave = 0.3 * np.sin(np.arange(t) / (288 / (2 * np.pi)))[:, None]
    return (base + wave).astype(np.float32)


def test_week_residual_ignores_future_mutation():
    p = _synthetic_pressures()
    # Inject a drop at index 2500 relative to week prior
    i = STEPS_PER_WEEK + 200
    p[i, 2] = p[i - STEPS_PER_WEEK, 2] - 1.5
    series = week_residual_scores(p)
    assert not series.missing_history[i]
    assert series.score[i] >= 1.4
    assert series.strongest_sensor_idx[i] == 2

    mutated = p.copy()
    mutated[i + 50 :] += 10.0
    series2 = week_residual_scores(mutated)
    assert series.score[i] == series2.score[i]
    assert series.strongest_sensor_idx[i] == series2.strongest_sensor_idx[i]


def test_warm_prefix_all_missing():
    p = _synthetic_pressures()
    series = week_residual_scores(p)
    assert np.all(series.missing_history[:STEPS_PER_WEEK])
    assert not series.missing_history[STEPS_PER_WEEK]


def test_missing_history_not_scored_as_zero():
    p = _synthetic_pressures()
    p[STEPS_PER_WEEK + 10, :] = np.nan
    series = week_residual_scores(p)
    assert series.missing_history[STEPS_PER_WEEK + 10]
    assert np.isnan(series.score[STEPS_PER_WEEK + 10])


def test_episodes_require_confirmation_and_are_causal():
    p = _synthetic_pressures()
    # Three consecutive large drops on sensor 0
    i0 = STEPS_PER_WEEK + 100
    for k in range(5):
        p[i0 + k, 0] = p[i0 + k - STEPS_PER_WEEK, 0] - 2.0
    series = week_residual_scores(p)
    eps = build_episodes(series, tau=1.0, confirm_k=3, clear_m=6)
    assert eps, "expected an episode"
    assert eps[0].notify_idx == i0 + 2  # third exceedance


def test_raw_baseline_lag():
    p = _synthetic_pressures()
    i = STEPS_30M + 20
    p[i, 1] = p[i - STEPS_30M, 1] - 0.8
    series = raw_drop_scores(p)
    assert series.score[i] >= 0.79
    assert series.strongest_sensor_idx[i] == 1


def test_selection_rules():
    def m(tau, abrupt, unmatched, tia=0.1, onset=0.5):
        return PeriodMetrics(
            period="DEV",
            method="week_residual",
            tau=tau,
            n_onsets=4,
            n_abrupt_onsets=2,
            onset_recall=onset,
            abrupt_onset_recall=abrupt,
            matched_delays_hours={},
            n_episodes=10,
            n_matched_episodes=2,
            n_unmatched_episodes=8,
            unmatched_episodes_per_week=unmatched,
            time_in_alarm_fraction=tia,
            longest_episode_hours=1.0,
            period_weeks=26.0,
            matches=[],
        )

    chosen = select_residual_tau(
        [m(0.5, 0.5, 1.5), m(0.75, 1.0, 1.8), m(0.35, 1.0, 3.0), m(1.0, 1.0, 1.8, tia=0.05)]
    )
    # Among unmatched<=2 with abrupt=1.0, prefer lower tia then larger tau → 1.0
    assert chosen.tau == 1.0

    base = select_baseline_tau(
        [m(0.25, 0.5, 1.0), m(0.5, 0.5, 1.7), m(0.75, 0.5, 2.5), m(1.25, 0.0, 0.2)],
        target_unmatched_per_week=1.8,
    )
    # 0.2/wk is below 0.5*1.8 floor → ignored; closest remaining is 1.7 @ tau=0.5
    assert base.tau == 0.5
