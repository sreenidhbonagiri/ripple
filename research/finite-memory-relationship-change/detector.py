"""FMR3C: finite-memory recent–reference residual change detector."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from scale import sigma_from_train
from windows import first_valid_t, hours_to_steps, window_bounds

COVERAGE_MIN = 0.80
RECOVER_STEPS = 12  # fixed 1 h; not swept


@dataclass
class Episode:
    stream_id: str
    target_idx: int
    notify_idx: int
    end_idx: int
    change_estimate_idx: int
    refs_used: list[str] = field(default_factory=list)
    peak_score: float = 0.0


def _window_median(z: np.ndarray, i0: int, i1: int, n_design: int) -> float:
    """Median of finite values in inclusive [i0, i1]; NaN if coverage < 80%."""
    seg = z[i0 : i1 + 1]
    finite = seg[np.isfinite(seg)]
    if finite.size < COVERAGE_MIN * n_design - 1e-9:
        return float("nan")
    return float(np.median(finite))


def score_series(
    z: np.ndarray,
    *,
    n_q: int,
    n_r: int,
    sigma: float,
) -> np.ndarray:
    """Causal s(t) for one target; NaN before warm-up / missing / ineligible sigma."""
    z = np.asarray(z, dtype=np.float64)
    T = z.shape[0]
    s = np.full(T, np.nan, dtype=np.float64)
    if not np.isfinite(sigma) or sigma <= 0:
        return s
    t0 = first_valid_t(n_q, n_r)
    for t in range(t0, T):
        q0, q1, r0, r1 = window_bounds(t, n_q, n_r)
        # Causal: only indices <= t (ensured by bounds)
        assert q1 == t and r1 < q0
        m_q = _window_median(z, q0, q1, n_q)
        m_r = _window_median(z, r0, r1, n_r)
        if not np.isfinite(m_q) or not np.isfinite(m_r):
            continue
        s[t] = (m_q - m_r) / sigma
    return s


def run_target_episodes(
    z: np.ndarray,
    *,
    analysis_offset: int,
    stream_id: str,
    target_idx: int,
    refs: list[str],
    n_q: int,
    n_r: int,
    sigma: float,
    tau: float,
    recover_steps: int = RECOVER_STEPS,
) -> tuple[list[Episode], np.ndarray]:
    """Notify on s>=tau while inactive; recover after recover_steps with s<tau/2.

    Missing s: hold state; do not notify; do not advance recovery.
    """
    s = score_series(z, n_q=n_q, n_r=n_r, sigma=sigma)
    tau_clear = tau / 2.0
    episodes: list[Episode] = []
    active = False
    recover_run = 0
    notify_local = -1
    change_local = -1
    peak = 0.0

    def close(end_local: int) -> None:
        nonlocal active, recover_run, notify_local, change_local, peak
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
                peak_score=peak,
            )
        )
        active = False
        recover_run = 0
        notify_local = -1
        change_local = -1
        peak = 0.0

    for t in range(s.shape[0]):
        st = s[t]
        if not np.isfinite(st):
            # missing: hold; break recovery streak; no notify / no clear
            recover_run = 0
            continue
        if active:
            if st < tau_clear:
                recover_run += 1
            else:
                recover_run = 0
            peak = max(peak, st)
            if recover_run >= recover_steps:
                close(t)
            continue
        # inactive
        if st >= tau:
            active = True
            notify_local = t
            change_local = t  # diagnostic: first exceedance
            peak = st
            recover_run = 0

    if active:
        close(s.shape[0] - 1)

    return episodes, s


def run_all_targets(
    z: np.ndarray,
    sensor_ids: list[str],
    target_models,
    *,
    analysis_offset: int,
    train_z: np.ndarray,
    l_q_hours: float,
    l_r_hours: float,
    tau: float,
    recover_steps: int = RECOVER_STEPS,
) -> tuple[list[Episode], dict]:
    """Full 33-sensor (or whatever) pipeline. Scales from train_z only."""
    n_q = hours_to_steps(l_q_hours)
    n_r = hours_to_steps(l_r_hours)
    episodes: list[Episode] = []
    scale_meta: dict = {}
    scores: dict[str, np.ndarray] = {}

    for tm in target_models:
        i = tm.target
        sid = sensor_ids[i]
        refs = [sensor_ids[j] for j in tm.refs]
        sigma, meta = sigma_from_train(train_z[:, i], n_q, n_r)
        scale_meta[sid] = meta
        if not meta.get("eligible", False):
            continue
        eps, s = run_target_episodes(
            z[:, i],
            analysis_offset=analysis_offset,
            stream_id=sid,
            target_idx=i,
            refs=refs,
            n_q=n_q,
            n_r=n_r,
            sigma=sigma,
            tau=tau,
            recover_steps=recover_steps,
        )
        episodes.extend(eps)
        scores[sid] = s

    episodes.sort(key=lambda e: (e.notify_idx, e.target_idx))
    return episodes, {"scale_meta": scale_meta, "scores": scores, "n_q": n_q, "n_r": n_r}
