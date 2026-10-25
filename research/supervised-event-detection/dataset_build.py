"""Build feature matrices from synthetic scenarios with warm-up masking."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from features import build_feature_matrix, feature_manifest
from schema import FEATURE_CONFIG, STEPS_PER_HOUR
from splits import assign_splits


def load_scenario_arrays(sim_dir: Path, scenario_id: str) -> dict:
    z = np.load(sim_dir / f"{scenario_id}.npz")
    return {k: z[k] for k in z.files}


def build_split_tables(sim_dir: Path) -> dict:
    manifest = json.loads((sim_dir / "scenario_manifest.json").read_text())
    split_info = assign_splits(manifest)
    warm = FEATURE_CONFIG.warm_up_steps
    # Pilot uses 12 h scenario warm-up for labels; feature warm-up may be longer —
    # clamp to available trajectory: use max(feature deltas, scenario WARMUP)
    scenario_warm = 12 * STEPS_PER_HOUR
    start_i = max(warm, scenario_warm)  # actually warm_up_steps is 24h > 12h duration issue!

    # FIX: FeatureConfig.warm_up_steps=24h but scenarios are 48h — OK (24h warm-up).
    # For labels, leak starts after 12h+ so positives exist after warm-up.

    tables = {k: {"X": [], "y": [], "scenario_ids": [], "meta": []} for k in ("train", "synthetic_dev", "synthetic_test")}
    feat_names = None
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        sid = sc["spec"]["scenario_id"]
        split = split_info["assignments"][sid]
        if split not in tables:
            continue
        arr = load_scenario_arrays(sim_dir, sid)
        X, names = build_feature_matrix(arr["pressures"], arr["flows"], arr["levels"])
        feat_names = names
        y = arr["labels_abrupt_positive"].astype(np.int32)
        # Drop warm-up rows (insufficient causal history / trajectory spin-up)
        sl = slice(start_i, None)
        Xs = X[sl]
        ys = y[sl]
        # Drop rows with any non-finite feature
        ok = np.all(np.isfinite(Xs), axis=1)
        Xs, ys = Xs[ok], ys[ok]
        for i in range(Xs.shape[0]):
            tables[split]["X"].append(Xs[i])
            tables[split]["y"].append(int(ys[i]))
            tables[split]["scenario_ids"].append(sid)
            tables[split]["meta"].append(
                {
                    "kind": sc["spec"]["kind"],
                    "pipe": sc["spec"]["pipe"],
                    "pipe_group": sc["spec"]["pipe_group"],
                    "operating_realization": sc["spec"]["operating_realization"],
                }
            )

    out = {
        "feature_manifest": feature_manifest(),
        "split_info": split_info,
        "row_start_index": start_i,
        "feature_names": feat_names,
        "splits": {},
    }
    for k, tab in tables.items():
        X = np.asarray(tab["X"], dtype=np.float64) if tab["X"] else np.zeros((0, len(feat_names or [])))
        y = np.asarray(tab["y"], dtype=np.int32)
        out["splits"][k] = {
            "X": X,
            "y": y,
            "scenario_ids": tab["scenario_ids"],
            "meta": tab["meta"],
            "n_rows": int(X.shape[0]),
            "n_pos": int(y.sum()) if y.size else 0,
            "n_scenarios": len(set(tab["scenario_ids"])),
        }
    return out
