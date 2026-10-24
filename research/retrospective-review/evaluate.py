"""Pre-registered matching and metrics (labels for eval only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np

from io_data import Leakage, open_leak_count
from method import Candidate

MATCH_PRE_HOURS = 6.0
MATCH_POST_DAYS = 14.0
DEV_START = np.datetime64("2018-01-01T00:00")
DEV_END = np.datetime64("2018-06-30T23:55")
DIAG_START = np.datetime64("2018-07-01T00:00")
DIAG_END = np.datetime64("2018-12-31T23:55")


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


def match_candidates(
    timestamps: np.ndarray,
    candidates: list[Candidate],
    onsets: list[Leakage],
    leakages_all: list[Leakage],
) -> tuple[list[dict], set[int]]:
    used: set[int] = set()
    results: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo = L.start - np.timedelta64(int(MATCH_PRE_HOURS * 60), "m")
        hi = min(L.start + np.timedelta64(int(MATCH_POST_DAYS * 24 * 60), "m"), L.end)
        best_j = None
        best_t = None
        for j, c in enumerate(candidates):
            if j in used:
                continue
            t = timestamps[c.change_idx]
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
                    "change_time": None,
                    "error_hours": None,
                    "open_leaks_at_change": None,
                }
            )
            continue
        used.add(best_j)
        c = candidates[best_j]
        err_h = float((best_t - L.start) / np.timedelta64(1, "h"))
        results.append(
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "matched": True,
                "change_time": str(best_t).replace("T", " "),
                "error_hours": err_h,
                "open_leaks_at_change": open_leak_count(leakages_all, best_t),
                "alarm_time": str(timestamps[c.alarm_idx]).replace("T", " "),
                "evidence_through": str(timestamps[c.evidence_through_idx]).replace("T", " "),
            }
        )
    return results, used


def period_metrics(
    timestamps: np.ndarray,
    period: PeriodSpec,
    candidates: list[Candidate],
    matches: list[dict],
    matched_idx: set[int],
    *,
    settings: dict,
    runtime_s: float,
    n_rows: int,
    n_sensors: int,
) -> dict:
    start_i, end_i = period_indices(timestamps, period)
    weeks = float((end_i - start_i) * 5 / (60 * 24 * 7))
    unmatched = len(candidates) - len(matched_idx)
    durations_h = []
    for c in candidates:
        durations_h.append(
            float((c.evidence_through_idx - c.change_idx) * 5 / 60.0)
        )
    # duplicate burden: unmatched candidates within 24h of another candidate
    dup = 0
    change_times = [timestamps[c.change_idx] for c in candidates]
    for j, c in enumerate(candidates):
        if j in matched_idx:
            continue
        t = change_times[j]
        for k, t2 in enumerate(change_times):
            if k == j:
                continue
            if abs(float((t - t2) / np.timedelta64(1, "h"))) <= 24.0:
                dup += 1
                break

    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    incip = [m for m in matches if m["leak_type"] == "incipient"]
    errs = [m["error_hours"] for m in matches if m["matched"]]

    def recall(rows: list[dict]) -> float:
        if not rows:
            return float("nan")
        return sum(1 for m in rows if m["matched"]) / len(rows)

    return {
        "period": period.name,
        "settings": settings,
        "n_onsets": len(matches),
        "n_abrupt": len(abrupt),
        "n_incipient": len(incip),
        "onset_recall": recall(matches),
        "abrupt_recall": recall(abrupt),
        "incipient_recall": recall(incip),
        "n_candidates": len(candidates),
        "n_matched_candidates": len(matched_idx),
        "n_unmatched_candidates": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "median_candidate_duration_hours": float(np.median(durations_h)) if durations_h else None,
        "duplicate_unmatched_within_24h": dup,
        "change_time_error_hours": {
            "n": len(errs),
            "median": float(np.median(errs)) if errs else None,
            "p90": float(np.quantile(errs, 0.9)) if errs else None,
            "max_abs": float(np.max(np.abs(errs))) if errs else None,
        },
        "period_weeks": weeks,
        "runtime_seconds": runtime_s,
        "analyzed_rows": n_rows,
        "analyzed_sensors": n_sensors,
        "volume_row_x_sensor": n_rows * n_sensors,
        "matches": matches,
        "missed": [m for m in matches if not m["matched"]],
    }


def select_settings(
    candidates: list[dict], unmatched_cap: float = 3.0
) -> tuple[dict, bool]:
    """Return (chosen metrics row, gate_met).

    If no setting meets unmatched/wk ≤ cap, fall back to the full pool for a
    diagnostic freeze but report ``gate_met=False`` (pre-registered failure).
    """
    eligible = [m for m in candidates if m["unmatched_per_week"] <= unmatched_cap]
    gate_met = bool(eligible)
    pool = eligible or candidates
    pool = sorted(
        pool,
        key=lambda m: (
            - (m["abrupt_recall"] if np.isfinite(m["abrupt_recall"]) else -1),
            - (m["onset_recall"] if np.isfinite(m["onset_recall"]) else -1),
            m["unmatched_per_week"],
            -m["settings"]["cusum_h"],
        ),
    )
    return pool[0], gate_met


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
