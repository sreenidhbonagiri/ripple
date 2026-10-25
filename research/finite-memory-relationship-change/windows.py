"""Exact recent / reference window index bounds (no overlap, causal)."""

from __future__ import annotations

STEPS_PER_HOUR = 12  # 5-minute SCADA


def hours_to_steps(hours: float) -> int:
    steps = int(round(hours * STEPS_PER_HOUR))
    if steps <= 0:
        raise ValueError(f"window hours must be positive, got {hours}")
    return steps


def window_bounds(t_local: int, n_q: int, n_r: int) -> tuple[int, int, int, int]:
    """Inclusive index bounds for Q and R at local analysis index ``t_local``.

    Discrete realization of continuous design:
      Q(t) = (t - L_Q, t]  → indices [t - n_q + 1, t]
      R(t) = (t - L_Q - L_R, t - L_Q] → indices [t - n_q - n_r + 1, t - n_q]

    Returns ``(q0, q1, r0, r1)`` inclusive. Caller must ensure ``r0 >= 0``.
    """
    if n_q <= 0 or n_r <= 0:
        raise ValueError("n_q and n_r must be positive")
    q1 = t_local
    q0 = t_local - n_q + 1
    r1 = t_local - n_q
    r0 = t_local - n_q - n_r + 1
    return q0, q1, r0, r1


def windows_valid(t_local: int, n_q: int, n_r: int) -> bool:
    q0, q1, r0, r1 = window_bounds(t_local, n_q, n_r)
    if r0 < 0:
        return False
    # no overlap: R ends at t-n_q, Q starts at t-n_q+1
    assert r1 + 1 == q0
    assert q1 == t_local
    assert (q1 - q0 + 1) == n_q
    assert (r1 - r0 + 1) == n_r
    return True


def first_valid_t(n_q: int, n_r: int) -> int:
    """Smallest local t with both windows inside [0, t]."""
    return n_q + n_r - 1
