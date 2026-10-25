"""Scenario-level splits — never random 5-minute row shuffles."""

from __future__ import annotations

from collections import defaultdict


def assign_splits(manifest: dict, *, holdout_pipe_groups: tuple[int, ...] = (3, 4)) -> dict:
    """Split by scenario, operating realization, and held-out pipe groups.

    Rules:
    - Entire scenario → one split (all windows stay together).
    - Leak scenarios whose pipe_group ∈ holdout_pipe_groups → synthetic_test
      (held-out pipes).
    - Remaining leaks: operating_realization 0,1 → train; 2 → synth_dev; 3 → synth_test
      (if not already pipe-held-out).
    - Controls follow operating_realization the same way (no pipe group).
    """
    assignments = {}
    counts = defaultdict(int)
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            assignments[sc["spec"]["scenario_id"]] = "failed"
            counts["failed"] += 1
            continue
        spec = sc["spec"]
        sid = spec["scenario_id"]
        op = int(spec["operating_realization"])
        if spec["kind"] == "leak_abrupt" and spec.get("pipe_group") in holdout_pipe_groups:
            split = "synthetic_test"
        elif op in (0, 1):
            split = "train"
        elif op == 2:
            split = "synthetic_dev"
        else:
            split = "synthetic_test"
        assignments[sid] = split
        counts[split] += 1

    return {
        "holdout_pipe_groups": list(holdout_pipe_groups),
        "assignments": assignments,
        "counts": dict(counts),
        "rules": (
            "Whole-scenario assignment only. No neighboring 5-minute row splits. "
            f"Leak pipe_groups {list(holdout_pipe_groups)} held out to synthetic_test. "
            "operating_realization 0–1 train, 2 synth_dev, 3 synth_test."
        ),
    }
