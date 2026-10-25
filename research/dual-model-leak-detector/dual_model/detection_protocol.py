"""Frozen detection-protocol constants (must match DETECTION_PROTOCOL.md)."""

from __future__ import annotations

from dataclasses import dataclass

REQUIRED_FROZEN_SHA256 = "5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921"

FIT_END = "2018-01-07 23:55:00"
DEV_START = "2018-01-08 00:00:00"
DEV_END = "2018-06-30 23:55:00"
DIAG_START = "2018-07-01 00:00:00"
DIAG_END = "2018-12-31 23:55:00"

REF_HOURS = 24
REF_GAP_HOURS = 1
REF_MIN_SAMPLES = 12
EPS_SIGMA = 1e-3  # m³/h

CREDIT_HOURS = 6
RECOVER_STEPS = 1  # 1 h on hourly grid
WARMUP_HOURS = 25  # ref + gap + margin

# Native five-minute Method M (METHOD_M_5MIN_PROTOCOL.md): same physical
# durations; sample counts scaled by 12 relative to the hourly grid.
TIMESTEP_SEC_5MIN = 300
SAMPLES_PER_HOUR_5MIN = 12
REF_MIN_SAMPLES_5MIN = REF_MIN_SAMPLES * SAMPLES_PER_HOUR_5MIN  # 144
MIN_SCALE_SAMPLES_5MIN = 24 * SAMPLES_PER_HOUR_5MIN  # 288
RECOVER_STEPS_5MIN = RECOVER_STEPS * SAMPLES_PER_HOUR_5MIN  # 12 ≈ 1 h
CAUSAL_FILL_MAX_AGE_STEPS_5MIN = 2  # ≤10 min past-only ffill

TAU_GRID = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)
GATE_RECALL = 2.0 / 3.0
GATE_UNMATCHED_PER_WEEK = 3.0
FALLBACK_TAU = 2.5
N_TIMING_NULLS = 200

PUMP_TRANSITION_M3H = 10.0
STORAGE_TRANSITION_M3H = 15.0


@dataclass(frozen=True)
class AbruptEvent:
    pipe: str
    onset: str
    period: str  # DEV | DIAG


ABRUPT_EVENTS = (
    AbruptEvent("p673", "2018-03-05 15:45:00", "DEV"),
    AbruptEvent("p538", "2018-05-18 08:35:00", "DEV"),
    AbruptEvent("p866", "2018-06-01 09:05:00", "DEV"),
    AbruptEvent("p183", "2018-08-07 02:35:00", "DIAG"),
    AbruptEvent("p158", "2018-10-06 02:35:00", "DIAG"),
    AbruptEvent("p369", "2018-10-26 02:05:00", "DIAG"),
)