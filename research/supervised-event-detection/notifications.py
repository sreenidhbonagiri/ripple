"""Score → episode notifications (FMR3C-compatible recovery semantics)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

RECOVER_STEPS = 12  # 1 h at 5-min grid


@dataclass
class Episode:
    notify_idx: int
    end_idx: int
    peak_score: float
    stream_id: str = "supervised_pilot"
    refs_used: list[str] = field(default_factory=list)


def episodes_from_scores(
    q: np.ndarray,
    *,
    tau: float,
    recover_steps: int = RECOVER_STEPS,
    analysis_offset: int = 0,
) -> list[Episode]:
    """Notify when q>=tau while inactive; recover after recover_steps with q<tau/2."""
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
        episodes.append(
            Episode(
                notify_idx=analysis_offset + notify_local,
                end_idx=analysis_offset + end_local,
                peak_score=peak,
            )
        )
        active = False
        recover_run = 0
        notify_local = -1
        peak = 0.0

    for t in range(q.shape[0]):
        st = q[t]
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
        close(q.shape[0] - 1)
    return episodes
