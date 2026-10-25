"""Signal-path tests for residual-normalization recovery variant."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import (  # noqa: E402
    RECOVERY_CUSUM_ZERO,
    RECOVERY_RESIDUAL_LE_K,
    run_cusum_episodes,
)


K = 0.5
H = 8.0
N_REC = 12


def test_residual_recovery_clears_despite_cusum_debt():
    """Large C from a pulse, then z<=k for 12 steps → clear even if C would stay >0."""
    z = np.zeros(200)
    z[10:40] = 3.0  # build debt / notify
    z[40:80] = 0.0  # normalized; under original C==0 recovery this also clears eventually,
    # but with high C, residual path clears after 12 steps of z<=k without waiting for C drain
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert len(eps) == 1
    # notify when C crosses h during pulse (~10 + ceil((8)/(3-0.5)) ≈ 14)
    assert eps[0].notify_idx < 40
    # clears 12 steps into the z<=k region starting at 40
    assert eps[0].end_idx == 40 + N_REC - 1


def test_sustained_elevated_residual_single_episode():
    z = np.zeros(500)
    z[20:] = 2.0  # stays elevated (>k)
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert len(eps) == 1
    assert eps[0].end_idx == len(z) - 1  # right-censored / never recovered


def test_second_incident_after_recovery_can_notify():
    z = np.zeros(400)
    z[20:50] = 2.0
    z[50:80] = 0.0  # recover
    z[200:230] = 2.0
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert len(eps) == 2
    assert eps[1].notify_idx > eps[0].end_idx


def test_missing_gaps_cannot_manufacture_recovery():
    z = np.full(120, np.nan)
    z[0:30] = 2.0  # notify
    # 11 finite z<=k, then gap, then more z<=k — must not clear across gap
    z[30:41] = 0.0
    z[41:45] = np.nan
    z[45:60] = 0.0
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert len(eps) == 1
    # recovery only after 12 consecutive finite z<=k starting at 45
    assert eps[0].end_idx == 45 + N_REC - 1


def test_notification_timing_matches_original_before_first_recovery():
    rng = np.random.default_rng(0)
    z = rng.normal(0, 0.2, size=800)
    z[100:160] = 2.5
    z[160:220] = 0.0
    common = dict(
        analysis_offset=1000,
        stream_id="n0",
        target_idx=0,
        refs=["n1"],
        k=K,
        h=H,
        recover_steps=288,
        residual_recover_steps=N_REC,
    )
    e0 = run_cusum_episodes(z, recovery_mode=RECOVERY_CUSUM_ZERO, **common)
    e1 = run_cusum_episodes(z, recovery_mode=RECOVERY_RESIDUAL_LE_K, **common)
    assert e0 and e1
    assert e0[0].notify_idx == e1[0].notify_idx
    assert e0[0].change_estimate_idx == e1[0].change_estimate_idx


def test_warmed_prefix_and_no_future_indices():
    z = np.zeros(300)
    z[50:] = 2.0
    off = 5000
    eps = run_cusum_episodes(
        z,
        analysis_offset=off,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert eps
    assert eps[0].notify_idx >= off
    assert eps[0].end_idx < off + len(z)
    # mutating z after the run must not affect recorded episodes (no shared buffers)
    notify = eps[0].notify_idx
    z[:] = 0
    assert eps[0].notify_idx == notify


def test_elevated_z_resets_recovery_counter():
    z = np.zeros(100)
    z[10:25] = 2.0
    z[25:35] = 0.0  # 10 steps <=k — not enough
    z[35] = 1.0  # elevated (>k) resets
    z[36:50] = 0.0
    eps = run_cusum_episodes(
        z,
        analysis_offset=0,
        stream_id="n0",
        target_idx=0,
        refs=[],
        k=K,
        h=H,
        recover_steps=288,
        recovery_mode=RECOVERY_RESIDUAL_LE_K,
        residual_recover_steps=N_REC,
    )
    assert len(eps) == 1
    assert eps[0].end_idx == 36 + N_REC - 1
