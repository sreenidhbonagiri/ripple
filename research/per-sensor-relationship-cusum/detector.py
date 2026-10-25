"""Sequential one-sided CUSUM with episode semantics (notification = crossing time).

Recovery modes
--------------
``cusum_zero`` (original frozen): while active, clear after ``recover_steps``
consecutive finite samples with ``C==0``.

``residual_le_k`` (registered variant): while active, clear after
``residual_recover_steps`` consecutive finite samples with ``z <= k``; on clear
reset ``C`` and rearm. See ``VARIANT_RESIDUAL_RECOVERY.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

RECOVERY_CUSUM_ZERO = "cusum_zero"
RECOVERY_RESIDUAL_LE_K = "residual_le_k"


@dataclass
class Episode:
    stream_id: str  # sensor name or "GLOBAL"
    target_idx: int  # -1 for global
    notify_idx: int  # absolute time index — PRIMARY
    end_idx: int  # absolute inclusive end (recovery or analysis end)
    change_estimate_idx: int  # diagnostic only (last zero before notify)
    refs_used: list[str] = field(default_factory=list)
    peak_cusum: float = 0.0
    recovery_mode: str = RECOVERY_CUSUM_ZERO


def run_cusum_episodes(
    z: np.ndarray,
    *,
    analysis_offset: int,
    stream_id: str,
    target_idx: int,
    refs: list[str],
    k: float,
    h: float,
    recover_steps: int,
    recovery_mode: str = RECOVERY_CUSUM_ZERO,
    residual_recover_steps: int = 12,
) -> list[Episode]:
    """One stream: z length = analysis span; indices relative then shifted by offset.

    Shared:
    - Missing z: hold C; break recovery streak; do not clear / do not notify.
    - Notification = first t with C>=h while inactive (not backdated).
    - No re-notify while active; rearm only after a documented clear.
    """
    if recovery_mode not in (RECOVERY_CUSUM_ZERO, RECOVERY_RESIDUAL_LE_K):
        raise ValueError(f"unknown recovery_mode={recovery_mode!r}")

    episodes: list[Episode] = []
    c = 0.0
    last_zero_local = 0
    active = False
    recover_run = 0
    notify_local = -1
    change_local = -1
    peak = 0.0

    def close_episode(end_local: int) -> None:
        nonlocal active, recover_run, notify_local, change_local, peak, c
        if not active:
            return
        episodes.append(
            Episode(
                stream_id=stream_id,
                target_idx=target_idx,
                notify_idx=analysis_offset + notify_local,
                end_idx=analysis_offset + end_local,
                change_estimate_idx=analysis_offset + change_local,
                refs_used=list(refs),
                peak_cusum=peak,
                recovery_mode=recovery_mode,
            )
        )
        active = False
        recover_run = 0
        notify_local = -1
        change_local = -1
        peak = 0.0
        c = 0.0

    for local, val in enumerate(z):
        if not np.isfinite(val):
            # hold C; never clear on missing
            if recovery_mode == RECOVERY_RESIDUAL_LE_K:
                recover_run = 0  # variant: missing breaks residual recovery streak
            # original cusum_zero: leave recover_run unchanged (finite C==0 samples only)
            continue

        if active:
            if recovery_mode == RECOVERY_RESIDUAL_LE_K:
                # Residual-normalization recovery (registered variant).
                if val <= k:
                    recover_run += 1
                else:
                    recover_run = 0
                if recover_run >= residual_recover_steps:
                    close_episode(local)
                    continue
                c = max(0.0, c + val - k)
                peak = max(peak, c)
                continue

            # Original: accumulate C first, then C==0 streak recovery.
            c = max(0.0, c + val - k)
            peak = max(peak, c)
            if c == 0.0:
                recover_run += 1
                if recover_run >= recover_steps:
                    close_episode(local)
            else:
                recover_run = 0
            continue

        # inactive — notification path identical for both modes
        c = max(0.0, c + val - k)
        if c == 0.0:
            last_zero_local = local
        if c >= h:
            active = True
            notify_local = local
            change_local = last_zero_local
            peak = c
            recover_run = 0

    if active:
        close_episode(len(z) - 1)
    return episodes


def run_all_targets(
    z_mat: np.ndarray,
    sensor_ids: list[str],
    target_models,
    *,
    analysis_offset: int,
    k: float,
    h: float,
    recover_hours: float,
    recovery_mode: str = RECOVERY_CUSUM_ZERO,
    residual_recover_steps: int = 12,
) -> list[Episode]:
    recover_steps = max(1, int(recover_hours * 12))
    out: list[Episode] = []
    for tm in target_models:
        i = tm.target
        refs = [sensor_ids[j] for j in tm.refs]
        out.extend(
            run_cusum_episodes(
                z_mat[:, i],
                analysis_offset=analysis_offset,
                stream_id=sensor_ids[i],
                target_idx=i,
                refs=refs,
                k=k,
                h=h,
                recover_steps=recover_steps,
                recovery_mode=recovery_mode,
                residual_recover_steps=residual_recover_steps,
            )
        )
    out.sort(key=lambda e: e.notify_idx)
    return out


def run_global_stream(
    s: np.ndarray,
    *,
    analysis_offset: int,
    k: float,
    h: float,
    recover_hours: float,
    recovery_mode: str = RECOVERY_CUSUM_ZERO,
    residual_recover_steps: int = 12,
) -> list[Episode]:
    recover_steps = max(1, int(recover_hours * 12))
    return run_cusum_episodes(
        s,
        analysis_offset=analysis_offset,
        stream_id="GLOBAL",
        target_idx=-1,
        refs=[],
        k=k,
        h=h,
        recover_steps=recover_steps,
        recovery_mode=recovery_mode,
        residual_recover_steps=residual_recover_steps,
    )
