"""Hourly score → episodes (Ripple-compatible τ / τ/2 recovery semantics)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .detection_protocol import RECOVER_STEPS


@dataclass
class Episode:
    notify_idx: int
    end_idx: int
    peak_score: float


def episodes_from_scores(
    s: np.ndarray,
    *,
    tau: float,
    recover_steps: int = RECOVER_STEPS,
) -> list[Episode]:
    """Notify when s>=tau while inactive; recover after recover_steps with s<tau/2."""
    tau_clear = tau / 2.0
    episodes: list[Episode] = []
    active = False
    recover_run = 0
    notify_local = -1
    peak = 0.0

    def close(end_local: int) -> None:
        nonlocal active, recover_run, notify_local, peak
        if not active:
            return
        episodes.append(Episode(notify_idx=notify_local, end_idx=end_local, peak_score=peak))
        active = False
        recover_run = 0
        notify_local = -1
        peak = 0.0

    for t in range(s.shape[0]):
        st = s[t]
        if not np.isfinite(st):
            recover_run = 0
            continue
        if active:
            if st < tau_clear:
                recover_run += 1
            else:
                recover_run = 0
            peak = max(peak, float(st))
            if recover_run >= recover_steps:
                close(t)
            continue
        if st >= tau:
            active = True
            notify_local = t
            peak = float(st)
            recover_run = 0
    if active:
        close(s.shape[0] - 1)
    return episodes