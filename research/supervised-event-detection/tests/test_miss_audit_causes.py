"""Reproducible miss-cause rules for the Arm A synthetic audit."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_arm_a_synth_misses import classify_miss
from notifications import Episode


def test_no_crossing_in_6h():
    onset = 160  # after feature warm-up (144)
    q = np.full(300, 0.2)
    q[:144] = np.nan
    episodes = []
    cl = classify_miss(onset=onset, q=q, tau=0.7, episodes=episodes, hit=False)
    assert bool(cl["causes"]["no_crossing_in_6h"]) is True
    assert bool(cl["causes"]["warmup_missingness"]) is False
    assert cl["primary"] == "no_crossing_in_6h"


def test_preonset_active_block_with_crossing():
    onset = 100
    q = np.full(200, 0.2)
    q[80:] = 0.9  # active from 80 through credit; crossings exist in window
    episodes = [Episode(notify_idx=80, end_idx=199, peak_score=0.95)]
    cl = classify_miss(onset=onset, q=q, tau=0.7, episodes=episodes, hit=False)
    assert bool(cl["causes"]["preonset_active_block"]) is True
    assert bool(cl["crossed_in_credit"]) is True
    assert cl["primary"] == "preonset_active_block"
    assert bool(cl["recovery_debt"]["persistent_high_probability"]) is True


def test_confirmation_always_false():
    onset = 50
    q = np.full(120, 0.1)
    cl = classify_miss(onset=onset, q=q, tau=0.7, episodes=[], hit=False)
    assert bool(cl["causes"]["confirmation_not_met"]) is False


def test_warmup_missingness():
    onset = 10  # before warm-up
    q = np.full(100, np.nan)
    cl = classify_miss(onset=onset, q=q, tau=0.7, episodes=[], hit=False)
    assert bool(cl["causes"]["warmup_missingness"]) is True
