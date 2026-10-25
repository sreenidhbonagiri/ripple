"""Whole-scenario splits for phase-corrected scenarios; keep matched pairs together."""

from __future__ import annotations

from collections import defaultdict


def assign_splits_phase(
    manifest: dict, *, holdout_pipe_groups: tuple[int, ...] = (3, 4)
) -> dict:
    """Assign splits by scenario; matched pair_id members share the leak's split.

    Base rules (same spirit as splits.assign_splits):
    - Leak pipe_group in holdout → synthetic_test
    - Else operating_realization 0–1 train, 2 synth_dev, 3 synth_test
    - Control without pair follows its own operating_realization
    - Control with pair_id copies the paired leak's assignment
    """
    by_id = {}
    for sc in manifest["scenarios"]:
        by_id[sc["spec"]["scenario_id"]] = sc

    # First pass: assign all leaks
    assignments: dict[str, str] = {}
    pair_split: dict[str, str] = {}
    counts: dict[str, int] = defaultdict(int)

    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            assignments[sc["spec"]["scenario_id"]] = "failed"
            counts["failed"] += 1
            continue
        spec = sc["spec"]
        if spec["kind"] != "leak_abrupt":
            continue
        sid = spec["scenario_id"]
        op = int(spec["operating_realization"])
        if spec.get("pipe_group") in holdout_pipe_groups:
            split = "synthetic_test"
        elif op in (0, 1):
            split = "train"
        elif op == 2:
            split = "synthetic_dev"
        else:
            split = "synthetic_test"
        assignments[sid] = split
        counts[split] += 1
        pid = spec.get("pair_id")
        if pid:
            pair_split[pid] = split

    # Second pass: controls (and any non-leak)
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        spec = sc["spec"]
        sid = spec["scenario_id"]
        if sid in assignments:
            continue
        pid = spec.get("pair_id")
        if pid and pid in pair_split:
            split = pair_split[pid]
        else:
            op = int(spec["operating_realization"])
            if op in (0, 1):
                split = "train"
            elif op == 2:
                split = "synthetic_dev"
            else:
                split = "synthetic_test"
        assignments[sid] = split
        counts[split] += 1

    # Verify pairs co-located
    pair_members: dict[str, list[str]] = defaultdict(list)
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        pid = sc["spec"].get("pair_id")
        if pid:
            pair_members[pid].append(sc["spec"]["scenario_id"])
    pair_ok = True
    for pid, members in pair_members.items():
        splits = {assignments[m] for m in members}
        if len(splits) != 1:
            pair_ok = False

    return {
        "holdout_pipe_groups": list(holdout_pipe_groups),
        "assignments": assignments,
        "counts": dict(counts),
        "pairs_colocated": pair_ok,
        "n_pairs": len(pair_members),
        "rules": (
            "Whole-scenario assignment. Matched pair_id members share the leak "
            f"member's split. Leak pipe_groups {list(holdout_pipe_groups)} → "
            "synthetic_test. Else op 0–1 train, 2 synth_dev, 3 synth_test."
        ),
    }
