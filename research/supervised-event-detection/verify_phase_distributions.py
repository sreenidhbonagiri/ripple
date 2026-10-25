"""Pre-fit checks: phase and onset distributions for phase-corrected scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simulate import DURATION_HOURS, WARMUP_HOURS
from simulate_phase import PHASE_PERIOD_HOURS


def verify_phase_onset_distributions(manifest: dict) -> dict:
    leak_phase = []
    ctrl_phase = []
    leak_onset = []
    paired_phase_match = []
    by_pair: dict[str, dict] = {}

    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        spec = sc["spec"]
        ph = float(spec["pattern_phase_offset_hours"])
        pid = spec.get("pair_id")
        if spec["kind"] == "leak_abrupt":
            leak_phase.append(ph)
            onset = float(spec["leak_start_hour"])
            leak_onset.append(onset)
            if pid:
                by_pair.setdefault(pid, {})["leak_phase"] = ph
                by_pair[pid]["onset"] = onset
        elif spec["kind"].startswith("control"):
            ctrl_phase.append(ph)
            if pid:
                by_pair.setdefault(pid, {})["ctrl_phase"] = ph

    for pid, d in by_pair.items():
        if "leak_phase" in d and "ctrl_phase" in d:
            paired_phase_match.append(
                abs(d["leak_phase"] - d["ctrl_phase"]) < 1e-12
            )

    leak_phase = np.asarray(leak_phase)
    ctrl_phase = np.asarray(ctrl_phase)
    leak_onset = np.asarray(leak_onset)

    # Independence: |corr(phase, onset)| should be small under independent sampling
    if leak_phase.size >= 3:
        corr = float(np.corrcoef(leak_phase, leak_onset)[0, 1])
    else:
        corr = float("nan")

    checks = {
        "n_leak": int(leak_phase.size),
        "n_control": int(ctrl_phase.size),
        "phase_in_range_leaks": bool(
            leak_phase.size and leak_phase.min() >= 0 and leak_phase.max() < PHASE_PERIOD_HOURS
        ),
        "phase_in_range_controls": bool(
            ctrl_phase.size
            and ctrl_phase.min() >= 0
            and ctrl_phase.max() < PHASE_PERIOD_HOURS
        ),
        "onset_after_warmup": bool(
            leak_onset.size and leak_onset.min() >= WARMUP_HOURS + 2 - 1e-9
        ),
        "onset_before_horizon": bool(
            leak_onset.size and leak_onset.max() <= DURATION_HOURS - 10 + 1e-6
        ),
        "paired_phases_identical": bool(paired_phase_match) and all(paired_phase_match),
        "n_pairs_checked": len(paired_phase_match),
        "corr_phase_onset": corr,
        "corr_phase_onset_abs_lt_0_5": bool(np.isfinite(corr) and abs(corr) < 0.5),
        "leak_phase_mean": float(leak_phase.mean()) if leak_phase.size else None,
        "ctrl_phase_mean": float(ctrl_phase.mean()) if ctrl_phase.size else None,
        "leak_phase_std": float(leak_phase.std()) if leak_phase.size else None,
        "ctrl_phase_std": float(ctrl_phase.std()) if ctrl_phase.size else None,
        "onset_mean": float(leak_onset.mean()) if leak_onset.size else None,
        "onset_std": float(leak_onset.std()) if leak_onset.size else None,
        # Same distribution family: both Unif-like on [0,24); mean near 12
        "phase_means_within_6h": bool(
            leak_phase.size
            and ctrl_phase.size
            and abs(float(leak_phase.mean()) - float(ctrl_phase.mean())) < 6.0
        ),
    }
    checks["all_passed"] = all(
        [
            checks["phase_in_range_leaks"],
            checks["phase_in_range_controls"],
            checks["onset_after_warmup"],
            checks["onset_before_horizon"],
            checks["paired_phases_identical"],
            checks["corr_phase_onset_abs_lt_0_5"],
            checks["phase_means_within_6h"],
            checks["n_leak"] >= 8,
            checks["n_control"] >= 4,
        ]
    )
    return checks


def load_and_verify(sim_dir: Path) -> dict:
    manifest = json.loads((sim_dir / "scenario_manifest.json").read_text())
    return verify_phase_onset_distributions(manifest)
