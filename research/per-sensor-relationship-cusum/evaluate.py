"""Pre-registered matching and metrics (notification-time primary)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from detector import Episode
from io_data import Leakage, open_leak_count

ABRUPT_POST_DAYS = 7.0
INCIPIENT_POST_DAYS = 14.0
DEV_START = np.datetime64("2018-01-01T00:00")
DEV_END = np.datetime64("2018-06-30T23:55")
DIAG_START = np.datetime64("2018-07-01T00:00")
DIAG_END = np.datetime64("2018-12-31T23:55")
STEPS_PER_DAY = 288
NULL_SHIFT_DAYS = list(range(1, 90))


@dataclass(frozen=True)
class PeriodSpec:
    name: str
    start: np.datetime64
    end: np.datetime64


DEV = PeriodSpec("DEV", DEV_START, DEV_END)
DIAG = PeriodSpec("DIAG", DIAG_START, DIAG_END)


def period_indices(timestamps: np.ndarray, period: PeriodSpec) -> tuple[int, int]:
    start_i = int(np.searchsorted(timestamps, period.start, side="left"))
    end_i = int(np.searchsorted(timestamps, period.end, side="right"))
    return start_i, end_i


def onsets_in_period(leakages: list[Leakage], period: PeriodSpec) -> list[Leakage]:
    return [L for L in leakages if period.start <= L.start <= period.end]


def abrupt_window(L: Leakage) -> tuple[np.datetime64, np.datetime64]:
    lo = L.start  # no pre-onset credit
    hi = min(L.start + np.timedelta64(int(ABRUPT_POST_DAYS * 24 * 60), "m"), L.end)
    return lo, hi


def incipient_window(L: Leakage) -> tuple[np.datetime64, np.datetime64]:
    lo = L.start
    hi = min(
        L.start + np.timedelta64(int(INCIPIENT_POST_DAYS * 24 * 60), "m"),
        L.peak,
        L.end,
    )
    return lo, hi


def match_episodes(
    timestamps: np.ndarray,
    episodes: list[Episode],
    onsets: list[Leakage],
    leakages_all: list[Leakage],
) -> tuple[list[dict], set[int]]:
    used: set[int] = set()
    results: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        if L.leak_type == "abrupt":
            lo, hi = abrupt_window(L)
        else:
            lo, hi = incipient_window(L)
        best_j = None
        best_t = None
        for j, ep in enumerate(episodes):
            if j in used:
                continue
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                if best_j is None or t < best_t:
                    best_j = j
                    best_t = t
        if best_j is None:
            results.append(
                {
                    "pipe": L.pipe,
                    "leak_type": L.leak_type,
                    "onset": str(L.start).replace("T", " "),
                    "matched": False,
                    "notify_time": None,
                    "delay_hours": None,
                    "stream_id": None,
                    "refs_used": None,
                    "pre_onset_notifications_nearby": _count_pre_onset(
                        timestamps, episodes, L.start, hours=24
                    ),
                }
            )
            continue
        used.add(best_j)
        ep = episodes[best_j]
        delay = float((best_t - L.start) / np.timedelta64(1, "h"))
        results.append(
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "matched": True,
                "notify_time": str(best_t).replace("T", " "),
                "delay_hours": delay,
                "stream_id": ep.stream_id,
                "refs_used": list(ep.refs_used),
                "change_estimate_time": str(
                    timestamps[ep.change_estimate_idx]
                ).replace("T", " "),
                "open_leaks_at_notify": open_leak_count(leakages_all, best_t),
                "episode_end": str(timestamps[ep.end_idx]).replace("T", " "),
            }
        )
    return results, used


def _count_pre_onset(
    timestamps: np.ndarray,
    episodes: list[Episode],
    onset: np.datetime64,
    hours: float,
) -> int:
    lo = onset - np.timedelta64(int(hours * 60), "m")
    n = 0
    for ep in episodes:
        t = timestamps[ep.notify_idx]
        if lo <= t < onset:
            n += 1
    return n


def period_metrics(
    timestamps: np.ndarray,
    period: PeriodSpec,
    episodes: list[Episode],
    matches: list[dict],
    matched_idx: set[int],
    *,
    settings: dict,
    runtime_s: float,
    method: str,
) -> dict:
    start_i, end_i = period_indices(timestamps, period)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(episodes) - len(matched_idx)

    durations_h = [
        float((ep.end_idx - ep.notify_idx) * 5 / 60.0) for ep in episodes
    ]
    time_in_alarm_h = float(sum(durations_h))
    longest = float(max(durations_h)) if durations_h else 0.0

    dup = 0
    notify_times = [timestamps[ep.notify_idx] for ep in episodes]
    for j, ep in enumerate(episodes):
        if j in matched_idx:
            continue
        t = notify_times[j]
        for k, t2 in enumerate(notify_times):
            if k == j:
                continue
            if abs(float((t - t2) / np.timedelta64(1, "h"))) <= 24.0:
                dup += 1
                break

    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    incip = [m for m in matches if m["leak_type"] == "incipient"]
    delays = [m["delay_hours"] for m in abrupt if m["matched"]]

    def recall(rows: list[dict]) -> float:
        if not rows:
            return float("nan")
        return sum(1 for m in rows if m["matched"]) / len(rows)

    return {
        "method": method,
        "period": period.name,
        "settings": settings,
        "n_onsets": len(matches),
        "n_abrupt": len(abrupt),
        "n_incipient": len(incip),
        "abrupt_recall": recall(abrupt),
        "incipient_recall": recall(incip),
        "onset_recall": recall(matches),
        "n_episodes": len(episodes),
        "n_matched_episodes": len(matched_idx),
        "n_unmatched_episodes": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "time_in_alarm_hours": time_in_alarm_h,
        "longest_episode_hours": longest,
        "median_episode_hours": float(np.median(durations_h)) if durations_h else None,
        "duplicate_unmatched_within_24h": dup,
        "abrupt_delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "p90": float(np.quantile(delays, 0.9)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
        },
        "period_weeks": weeks,
        "runtime_seconds": runtime_s,
        "matches": matches,
        "missed": [m for m in matches if not m["matched"]],
    }


def select_settings(
    candidates: list[dict], unmatched_cap: float = 3.0
) -> tuple[dict, bool]:
    eligible = [m for m in candidates if m["unmatched_per_week"] <= unmatched_cap]
    gate_met = bool(eligible)
    pool = eligible or candidates
    pool = sorted(
        pool,
        key=lambda m: (
            - (m["abrupt_recall"] if np.isfinite(m["abrupt_recall"]) else -1),
            m["unmatched_per_week"],
            -m["settings"]["cusum_h"],
            -(m["settings"].get("n_refs") or 0),
        ),
    )
    return pool[0], gate_met


def shift_episodes(
    episodes: list[Episode],
    delta_steps: int,
    analysis_start: int,
    analysis_end: int,
) -> list[Episode]:
    """Circular shift of notify/end/change indices; preserves gaps."""
    span = analysis_end - analysis_start
    if span <= 0 or not episodes:
        return []
    out: list[Episode] = []
    for ep in episodes:
        def sh(idx: int) -> int:
            rel = idx - analysis_start
            return analysis_start + ((rel + delta_steps) % span)

        out.append(
            Episode(
                stream_id=ep.stream_id,
                target_idx=ep.target_idx,
                notify_idx=sh(ep.notify_idx),
                end_idx=sh(ep.end_idx),
                change_estimate_idx=sh(ep.change_estimate_idx),
                refs_used=list(ep.refs_used),
                peak_cusum=ep.peak_cusum,
            )
        )
    out.sort(key=lambda e: e.notify_idx)
    return out


def null_notification_comparison(
    timestamps: np.ndarray,
    episodes: list[Episode],
    onsets: list[Leakage],
    leakages: list[Leakage],
    analysis_start: int,
    analysis_end: int,
) -> dict:
    abrupt = [L for L in onsets if L.leak_type == "abrupt"]
    obs_rows, _ = match_episodes(timestamps, episodes, onsets, leakages)
    obs_abr = sum(1 for m in obs_rows if m["leak_type"] == "abrupt" and m["matched"])

    null_counts = []
    for day in NULL_SHIFT_DAYS:
        shifted = shift_episodes(
            episodes, day * STEPS_PER_DAY, analysis_start, analysis_end
        )
        rows, _ = match_episodes(timestamps, shifted, onsets, leakages)
        null_counts.append(
            sum(1 for m in rows if m["leak_type"] == "abrupt" and m["matched"])
        )
    arr = np.asarray(null_counts, dtype=float)
    return {
        "n_abrupt_onsets": len(abrupt),
        "observed_abrupt_matches": obs_abr,
        "null_n_valid_shifts": len(NULL_SHIFT_DAYS),
        "null_match_median": float(np.median(arr)),
        "null_match_min": int(arr.min()),
        "null_match_max": int(arr.max()),
        "null_match_mean": float(arr.mean()),
        "fraction_shifts_ge_observed": float(np.mean(arr >= obs_abr)),
        "caveat": (
            "Overlapping daily shifts are dependent probes; n abrupt events is small. "
            "Descriptive only — beating null is necessary, not sufficient."
        ),
    }


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
