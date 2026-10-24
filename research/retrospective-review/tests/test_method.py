"""Implementation-correctness tests (not BattLeDIM accuracy claims)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from method import (  # noqa: E402
    aggregate_score,
    build_model,
    fit_pairwise_ols,
    offline_cusum_candidates,
    run_interval,
)


def test_constant_inputs_yield_no_cusum_alarms():
    """Exact constants → no usable OLS pairs → no CUSUM alarms."""
    t, s = 5000, 6
    p = np.ones((t, s), dtype=np.float32) * 40.0
    _model, cands, scores = run_interval(
        p,
        interval_start=0,
        interval_end=t,
        train_days=2,
        steps_per_day=288,
        cusum_h=8.0,
        min_segment_hours=12.0,
    )
    assert np.all(~np.isfinite(scores)) or len(cands) == 0
    assert len(cands) == 0


def test_synthetic_step_recovered():
    t, s = 8000, 5
    rng = np.random.default_rng(1)
    p = 40 + 0.05 * rng.normal(size=(t, s)).astype(np.float32)
    # After train (2 days=576), inject persistent shift on sensor 0 relative to others
    shift_at = 2000
    p[shift_at:, 0] -= 1.5
    model, cands, scores = run_interval(
        p,
        interval_start=0,
        interval_end=t,
        train_days=2,
        steps_per_day=288,
        cusum_h=4.0,
        min_segment_hours=6.0,
    )
    assert cands, "expected at least one candidate for synthetic step"
    # change estimate should be near shift_at (allow slack)
    errs = [abs(c.change_idx - shift_at) for c in cands]
    assert min(errs) < 288  # within 1 day


def test_interval_end_bound_no_future_indices():
    t, s = 3000, 4
    rng = np.random.default_rng(2)
    p = 40 + rng.normal(0, 0.05, size=(t, s)).astype(np.float32)
    end = 2000
    _m, cands, scores = run_interval(
        p,
        interval_start=0,
        interval_end=end,
        train_days=1,
        steps_per_day=288,
        cusum_h=3.0,
        min_segment_hours=6.0,
    )
    assert len(scores) == end - 288
    for c in cands:
        assert c.change_idx < end
        assert c.alarm_idx < end
        assert c.evidence_through_idx < end


def test_missing_data_does_not_crash():
    t, s = 2000, 4
    p = np.ones((t, s), dtype=np.float32) * 42
    p[100:120, 1] = np.nan
    intercept, slope = fit_pairwise_ols(p, slice(0, 500))
    scores = aggregate_score(p, intercept, slope, 500, 1500)
    assert scores.shape[0] == 1000


def test_reproducibility():
    t, s = 2500, 4
    rng = np.random.default_rng(3)
    p = 40 + rng.normal(0, 0.1, size=(t, s)).astype(np.float32)
    a1 = run_interval(p, interval_start=0, interval_end=t, train_days=1, cusum_h=5.0)
    a2 = run_interval(p, interval_start=0, interval_end=t, train_days=1, cusum_h=5.0)
    assert [c.change_idx for c in a1[1]] == [c.change_idx for c in a2[1]]
    np.testing.assert_allclose(a1[2], a2[2], equal_nan=True)
