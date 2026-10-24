"""Controlled synthetic checks of the signed residual + episode path (not BattLeDIM accuracy)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import run_all_targets, run_cusum_episodes  # noqa: E402
from residual import build_signals, expected_pressure_series, select_references  # noqa: E402


def _base(t=4000, s=6, seed=0):
    rng = np.random.default_rng(seed)
    # Near unit-slope relationships so additive common-mode largely cancels.
    common = 2.0 * np.sin(np.linspace(0, 20, t))
    p = np.zeros((t, s), dtype=np.float64)
    for i in range(s):
        p[:, i] = 40.0 + 0.2 * i + common + 0.03 * rng.normal(size=t)
    return p.astype(np.float32)


def test_target_only_drop_raises_positive_z_and_expected_tracks_ref():
    p = _base()
    train_days = 2
    steps = 288
    # Inject drop on sensor 0 after training
    drop_at = train_days * steps + 200
    p[drop_at:, 0] -= 1.5
    bundle = build_signals(
        p, interval_start=0, interval_end=len(p), train_days=train_days, n_refs=3
    )
    z0 = bundle.z[:, 0]
    # After drop, z should trend positive (under-pressure)
    post = z0[200:800]
    assert np.nanmedian(post) > 0.5
    tm = bundle.target_models[0]
    assert tm.refs
    ref = tm.refs[0]
    hat = expected_pressure_series(p, tm, ref, bundle.analysis_offset, len(p))
    # Expected should follow reference, not the dropped measurement
    measured = p[bundle.analysis_offset :, 0]
    # After drop, hat - measured should be large positive
    assert np.nanmedian((hat - measured)[200:800]) > 1.0


def test_common_mode_drop_suppresses_target_z():
    p = _base(seed=1)
    train_days = 2
    steps = 288
    drop_at = train_days * steps + 200
    p[drop_at:, :] -= 1.5  # all sensors
    bundle = build_signals(
        p, interval_start=0, interval_end=len(p), train_days=train_days, n_refs=3
    )
    post = bundle.z[200:800, 0]
    # Common-mode should largely cancel — |median z| small vs target-only case
    assert abs(float(np.nanmedian(post))) < 0.75


def test_reference_disturbance_can_create_spurious_signal():
    """With K=1, a disturbed reference biases the sole residual (median cannot vote it down)."""
    p = _base(seed=2)
    train_days = 2
    steps = 288
    bundle0 = build_signals(
        p, interval_start=0, interval_end=len(p), train_days=train_days, n_refs=1
    )
    tm = bundle0.target_models[0]
    assert tm.refs
    ref = tm.refs[0]
    drop_at = train_days * steps + 200
    p2 = p.copy()
    p2[drop_at:, ref] -= 2.0  # disturb reference only
    bundle = build_signals(
        p2, interval_start=0, interval_end=len(p2), train_days=train_days, n_refs=1
    )
    post = bundle.z[200:800, 0]
    assert abs(float(np.nanmedian(post))) > 0.5


def test_two_incidents_after_recovery():
    # Gap long enough for CUSUM to drain to 0 and meet recover_steps
    z = np.zeros(3000)
    z[100:140] = 2.0
    z[1200:1240] = 2.0
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=["n1"],
        k=0.5,
        h=4.0,
        recover_steps=24,
    )
    assert len(eps) == 2
    assert eps[1].notify_idx > eps[0].end_idx


def test_sustained_change_single_episode():
    z = np.zeros(3000)
    z[100:] = 2.0
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=0.5,
        h=4.0,
        recover_steps=48,
    )
    assert len(eps) == 1


def test_missing_gaps_hold_cusum():
    z = np.full(500, np.nan)
    z[:50] = 0.0
    z[50:80] = 3.0
    z[100:200] = 3.0  # gap 80-100 missing
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=0.5,
        h=5.0,
        recover_steps=1000,
    )
    assert len(eps) >= 1
    # notification at actual finite crossing, not during NaN
    assert np.isfinite(z[eps[0].notify_idx])


def test_warmed_prefix_no_alarm_in_training_span():
    p = _base(t=3000, seed=3)
    train_days = 2
    bundle = build_signals(
        p, interval_start=0, interval_end=len(p), train_days=train_days, n_refs=3
    )
    ids = [f"n{i}" for i in range(p.shape[1])]
    eps = run_all_targets(
        bundle.z,
        ids,
        bundle.target_models,
        analysis_offset=bundle.analysis_offset,
        k=0.5,
        h=8.0,
        recover_hours=12,
    )
    for ep in eps:
        assert ep.notify_idx >= bundle.analysis_offset


def test_reference_selection_ignores_labels():
    """Smoke: selection returns K refs from training metrics only."""
    p = _base(seed=4)
    models = select_references(p, slice(0, 576), n_refs=3)
    assert len(models) == p.shape[1]
    assert all(len(m.refs) <= 3 for m in models)
