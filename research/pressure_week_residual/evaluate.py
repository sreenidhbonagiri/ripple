"""Onset matching and period metrics (labels for eval only; never for sensor selection)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np

from detector import Episode, ScoreSeries  # noqa: E402
from io_scada import Leakage, ScadaBundle, open_leak_count  # noqa: E402

MATCH_HORIZON = np.timedelta64(24, "h")
DEV_START = np.datetime64("2018-01-08T00:00")
DEV_END = np.datetime64("2018-06-30T23:55")
DIAG_START = np.datetime64("2018-07-01T00:00")
DIAG_END = np.datetime64("2018-12-31T23:55")


@dataclass
class PeriodSpec:
    name: str
    start: np.datetime64
    end: np.datetime64


DEV = PeriodSpec("DEV", DEV_START, DEV_END)
DIAG = PeriodSpec("DIAG", DIAG_START, DIAG_END)


def period_slice(bundle: ScadaBundle, period: PeriodSpec) -> tuple[int, int]:
    start_i = int(np.searchsorted(bundle.timestamps, period.start, side="left"))
    end_i = int(np.searchsorted(bundle.timestamps, period.end, side="right"))
    return start_i, end_i


def onsets_in_period(leakages: list[Leakage], period: PeriodSpec) -> list[Leakage]:
    return [L for L in leakages if period.start <= L.start <= period.end]


@dataclass
class MatchResult:
    pipe: str
    leak_type: str
    onset: str
    matched: bool
    notify: str | None
    delay_hours: float | None
    episode_peak_score: float | None
    strongest_sensor: str | None
    open_leaks_at_notify: int | None
    context_at_notify: dict | None


@dataclass
class PeriodMetrics:
    period: str
    method: str
    tau: float
    n_onsets: int
    n_abrupt_onsets: int
    onset_recall: float
    abrupt_onset_recall: float
    matched_delays_hours: dict
    n_episodes: int
    n_matched_episodes: int
    n_unmatched_episodes: int
    unmatched_episodes_per_week: float
    time_in_alarm_fraction: float
    longest_episode_hours: float
    period_weeks: float
    matches: list[dict]


def _fmt(ts: np.datetime64) -> str:
    return str(ts).replace("T", " ")


def match_episodes(
    bundle: ScadaBundle,
    episodes: list[Episode],
    onsets: list[Leakage],
    series: ScoreSeries,
    leakages_all: list[Leakage],
    sensor_ids: list[str],
) -> tuple[list[MatchResult], set[int]]:
    """Greedy match by onset time; episode used at most once."""
    used_eps: set[int] = set()
    results: list[MatchResult] = []
    ordered = sorted(onsets, key=lambda L: L.start)

    for L in ordered:
        window_end = L.start + MATCH_HORIZON
        best_j: int | None = None
        best_notify = None
        for j, ep in enumerate(episodes):
            if j in used_eps:
                continue
            t_n = bundle.timestamps[ep.notify_idx]
            # Already-active before onset does not count.
            if t_n < L.start or t_n > window_end:
                continue
            if best_j is None or t_n < best_notify:
                best_j = j
                best_notify = t_n
        if best_j is None:
            results.append(
                MatchResult(
                    pipe=L.pipe,
                    leak_type=L.leak_type,
                    onset=_fmt(L.start),
                    matched=False,
                    notify=None,
                    delay_hours=None,
                    episode_peak_score=None,
                    strongest_sensor=None,
                    open_leaks_at_notify=None,
                    context_at_notify=None,
                )
            )
            continue
        used_eps.add(best_j)
        ep = episodes[best_j]
        delay_h = float((best_notify - L.start) / np.timedelta64(1, "h"))
        strong = sensor_ids[ep.strongest_sensor_idx] if ep.strongest_sensor_idx >= 0 else None
        results.append(
            MatchResult(
                pipe=L.pipe,
                leak_type=L.leak_type,
                onset=_fmt(L.start),
                matched=True,
                notify=_fmt(best_notify),
                delay_hours=delay_h,
                episode_peak_score=ep.peak_score,
                strongest_sensor=strong,
                open_leaks_at_notify=open_leak_count(leakages_all, best_notify),
                context_at_notify=None,  # filled by runner
            )
        )
    return results, used_eps


def compute_metrics(
    bundle: ScadaBundle,
    period: PeriodSpec,
    method: str,
    tau: float,
    episodes: list[Episode],
    matches: list[MatchResult],
    matched_episode_idxs: set[int],
) -> PeriodMetrics:
    start_i, end_i = period_slice(bundle, period)
    period_steps = end_i - start_i
    step = np.timedelta64(5, "m")
    period_hours = float(period_steps * step / np.timedelta64(1, "h"))
    period_weeks = period_hours / (24.0 * 7.0)

    alarm_steps = 0
    longest = 0
    for ep in episodes:
        # Clip episode to period for time-in-alarm accounting.
        a = max(ep.notify_idx, start_i)
        b = min(ep.end_idx, end_i - 1)
        if b >= a:
            dur = b - a + 1
            alarm_steps += dur
            longest = max(longest, dur)

    delays = [m.delay_hours for m in matches if m.matched and m.delay_hours is not None]
    abrupt = [m for m in matches if m.leak_type == "abrupt"]
    n_onsets = len(matches)
    n_abrupt = len(abrupt)
    n_matched = sum(1 for m in matches if m.matched)
    n_abrupt_matched = sum(1 for m in abrupt if m.matched)
    n_unmatched = len(episodes) - len(matched_episode_idxs)

    def _pct(xs: list[float], q: float) -> float | None:
        if not xs:
            return None
        return float(np.quantile(np.asarray(xs, dtype=float), q))

    return PeriodMetrics(
        period=period.name,
        method=method,
        tau=tau,
        n_onsets=n_onsets,
        n_abrupt_onsets=n_abrupt,
        onset_recall=(n_matched / n_onsets) if n_onsets else float("nan"),
        abrupt_onset_recall=(n_abrupt_matched / n_abrupt) if n_abrupt else float("nan"),
        matched_delays_hours={
            "median": _pct(delays, 0.5),
            "p90": _pct(delays, 0.9),
            "max": max(delays) if delays else None,
            "n": len(delays),
        },
        n_episodes=len(episodes),
        n_matched_episodes=len(matched_episode_idxs),
        n_unmatched_episodes=n_unmatched,
        unmatched_episodes_per_week=(n_unmatched / period_weeks) if period_weeks else float("nan"),
        time_in_alarm_fraction=(alarm_steps / period_steps) if period_steps else float("nan"),
        longest_episode_hours=float(longest * step / np.timedelta64(1, "h")),
        period_weeks=period_weeks,
        matches=[asdict(m) for m in matches],
    )


def select_residual_tau(
    candidates: list[PeriodMetrics],
    unmatched_cap: float = 2.0,
) -> PeriodMetrics:
    """Pre-registered DEV selection rule from DESIGN.md."""
    eligible = [m for m in candidates if m.unmatched_episodes_per_week <= unmatched_cap]
    if not eligible:
        # Fallback: lowest unmatched burden, then best abrupt recall.
        eligible = sorted(
            candidates,
            key=lambda m: (m.unmatched_episodes_per_week, -m.abrupt_onset_recall, -m.onset_recall),
        )
        return eligible[0]
    eligible.sort(
        key=lambda m: (
            -m.abrupt_onset_recall,
            -m.onset_recall,
            m.time_in_alarm_fraction,
            -m.tau,
        )
    )
    return eligible[0]


def select_baseline_tau(
    candidates: list[PeriodMetrics],
    target_unmatched_per_week: float,
) -> PeriodMetrics:
    """Closest unmatched/wk to residual, preferring non-collapsed baselines."""
    floor = 0.5 * target_unmatched_per_week
    pool = [m for m in candidates if m.unmatched_episodes_per_week >= floor]
    if not pool:
        pool = candidates
    return min(
        pool,
        key=lambda m: (
            abs(m.unmatched_episodes_per_week - target_unmatched_per_week),
            m.time_in_alarm_fraction,
            m.tau,
        ),
    )


def warm_prefix_report(series: ScoreSeries, first_scorable_idx: int) -> dict:
    warm = series.missing_history[:first_scorable_idx]
    after = series.missing_history[first_scorable_idx:]
    return {
        "first_scorable_idx": first_scorable_idx,
        "warm_missing_fraction": float(np.mean(warm)) if len(warm) else None,
        "post_warm_missing_fraction": float(np.mean(after)) if len(after) else None,
        "warm_all_missing": bool(np.all(warm)) if len(warm) else True,
    }


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
