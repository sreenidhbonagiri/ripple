"""Frozen chronological windows — must match CALIBRATION_WINDOWS.md."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeWindow:
    id: str
    start: str
    end: str
    role: str
    note: str = ""


FIT_W1 = TimeWindow(
    id="FIT_W1",
    start="2018-01-01 00:00:00",
    end="2018-01-07 23:55:00",
    role="fit",
    note="Paper-aligned first week; precedes p257 onset 2018-01-08 13:30",
)

VAL_WINDOWS = (
    TimeWindow("VAL_APR", "2018-04-02 00:00:00", "2018-04-08 23:55:00", "validation", "spring"),
    TimeWindow("VAL_JUL", "2018-07-02 00:00:00", "2018-07-08 23:55:00", "validation", "summer"),
    TimeWindow("VAL_OCT", "2018-10-01 00:00:00", "2018-10-07 23:55:00", "validation", "autumn"),
    TimeWindow("VAL_DEC", "2018-12-03 00:00:00", "2018-12-09 23:55:00", "validation", "winter"),
)

ALL_EVAL_WINDOWS = (FIT_W1, *VAL_WINDOWS)

# Abrupt 2018 onsets for post-freeze diagnostic only (not calibration targets).
DIAGNOSTIC_ONSETS = (
    {"leak_pipe": "p673", "onset": "2018-03-05 15:45:00", "kind": "abrupt"},
    {"leak_pipe": "p538", "onset": "2018-05-18 08:35:00", "kind": "abrupt"},
    {"leak_pipe": "p866", "onset": "2018-06-01 09:05:00", "kind": "abrupt"},
    {"leak_pipe": "p183", "onset": "2018-08-07 02:35:00", "kind": "abrupt"},
    {"leak_pipe": "p158", "onset": "2018-10-06 02:35:00", "kind": "abrupt"},
)