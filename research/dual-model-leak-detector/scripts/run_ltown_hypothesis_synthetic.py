#!/usr/bin/env python3
"""Calibrated L-Town synthetic H0/H1 feasibility with train/DEV region freeze.

Preserves toy results under outputs/hypothesis_synthetic/ (not modified).
Does not tune on the fresh TEST split. Method M temporal comparison: N/A.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.ltown_hypothesis import (  # noqa: E402
    CAL_SHA256,
    LTownHypConfig,
    apply_region_eps,
    registered_candidates,
)
from dual_model.ltown_hypothesis_scenarios import (  # noqa: E402
    SPLIT_OF,
    all_scenario_ids,
    run_ltown_scenario,
)

OUT = ROOT / "outputs" / "hypothesis_ltown_synthetic"
SCRATCH = OUT / "_scratch"


def _seeds(sid: str) -> list[int]:
    return [0, 1] if "noise" in sid else [0]


def _apply_detection(h: dict[str, Any], tau_dev: float, cfg: LTownHypConfig) -> dict[str, Any]:
    out = deepcopy(h)
    delta_J = float(out["delta_J"])
    penalty = float(out["penalty"])
    threshold = penalty + float(tau_dev)
    q1 = float(out["leak_m3h"])
    out["tau_dev"] = float(tau_dev)
    reasons: list[str] = []
    if delta_J <= 1e-6 and q1 < cfg.q_min_m3h:
        decision = "no_new_leak"
        reasons.append("near_null")
    elif 0.0 < delta_J <= threshold:
        decision = "inconclusive"
        reasons.append("ambiguity_band")
    elif delta_J > threshold and q1 >= cfg.q_min_m3h:
        decision = "leak"
        reasons.append("deltaJ_exceeds_penalty")
    else:
        decision = "no_new_leak"
        reasons.append("H0_preferred")
    out["decision"] = decision
    out["reasons"] = reasons
    return out


def _select_tau_dev(dev_rows: list[dict[str, Any]], cfg: LTownHypConfig) -> float:
    grid = [0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0]
    best_tau, best_obj = 0.0, -1e9
    for tau in grid:
        tp = fp = n_pos = n_neg = 0
        dem_force = dem_n = 0
        for r in dev_rows:
            h = _apply_detection(r["hypothesis"], tau, cfg)
            pred = h["decision"] == "leak"
            if "demand_only" in r["factors"] and not r["has_new_leak"]:
                dem_n += 1
                dem_force += int(pred)
            if r["has_new_leak"]:
                n_pos += 1
                tp += int(pred)
            else:
                n_neg += 1
                fp += int(pred)
        tpr = tp / n_pos if n_pos else 0.0
        fpr = fp / n_neg if n_neg else 0.0
        dem_rate = dem_force / dem_n if dem_n else 0.0
        obj = (tpr - fpr) - 0.5 * dem_rate
        if obj > best_obj:
            best_obj, best_tau = obj, tau
    return float(best_tau)


def _select_region_eps(dev_rows: list[dict[str, Any]], tau_dev: float, cfg: LTownHypConfig) -> float:
    """Smallest ε with DEV coverage ≥ intended among detects (labels allowed on DEV)."""
    detects = []
    for r in dev_rows:
        h = _apply_detection(r["hypothesis"], tau_dev, cfg)
        if h["decision"] == "leak" and r["has_new_leak"] and r["true_leak_node"]:
            detects.append((r, h))
    if not detects:
        return float(cfg.region_eps)
    target = cfg.intended_coverage
    grid = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0]
    for eps in grid:
        cover = 0
        for r, h in detects:
            J_by = h["J_by_candidate"]
            Jstar = float(J_by[h["best_candidate"]])
            region = [c for c, j in J_by.items() if float(j) <= Jstar + eps]
            cover += int(r["true_leak_node"] in region)
        if cover / len(detects) >= target - 1e-12:
            return float(eps)
    return float(grid[-1])


def _signature_decide(abs_sum: float, tau: float, tau_lo: float) -> str:
    if abs_sum <= tau_lo:
        return "no_new_leak"
    if abs_sum <= tau:
        return "inconclusive"
    return "leak"


def _select_signature_thresholds(dev_rows: list[dict[str, Any]], target_fpr: float, target_abstain: float) -> tuple[float, float]:
    """Pick (tau_lo, tau) to approximate hypothesis DEV FPR and abstention."""
    abs_sums = [float(r["baseline_signature_raw"]["abs_sum_m3h"]) for r in dev_rows]
    grid = sorted(set([0.5, 1, 2, 3, 4, 5, 8, 10, 15, 20] + abs_sums))
    best = (0.0, 3.0)
    best_obj = 1e9
    for i, tau_lo in enumerate(grid):
        for tau in grid[i:]:
            fp = n_neg = abstain = 0
            for r in dev_rows:
                a = float(r["baseline_signature_raw"]["abs_sum_m3h"])
                d = _signature_decide(a, tau, tau_lo)
                if d == "inconclusive":
                    abstain += 1
                if not r["has_new_leak"]:
                    n_neg += 1
                    fp += int(d == "leak")
            fpr = fp / n_neg if n_neg else 0.0
            ar = abstain / len(dev_rows) if dev_rows else 0.0
            obj = abs(fpr - target_fpr) + abs(ar - target_abstain)
            if obj < best_obj:
                best_obj = obj
                best = (float(tau_lo), float(tau))
    return best


def _metrics(rows: list[dict[str, Any]], key: str = "hypothesis") -> dict[str, Any]:
    n_pos = n_neg = tp = fp = 0
    abstain = 0
    region_sizes: list[int] = []
    cover = cover_n = 0
    loc_ok = loc_n = 0
    for r in rows:
        h = r[key]
        dec = h["decision"]
        if dec == "inconclusive":
            abstain += 1
        pred = dec == "leak"
        if r["has_new_leak"]:
            n_pos += 1
            tp += int(pred)
            if pred:
                loc_n += 1
                loc_ok += int(h.get("best_candidate") == r.get("true_leak_node"))
                region_sizes.append(int(h["region_size"]))
                cover_n += 1
                cover += int(r.get("true_leak_node") in h.get("candidate_region", []))
        else:
            n_neg += 1
            fp += int(pred)
    return {
        "n": len(rows),
        "n_leak": n_pos,
        "n_control": n_neg,
        "tpr_detect": (tp / n_pos) if n_pos else None,
        "fpr_detect": (fp / n_neg) if n_neg else None,
        "abstention_rate": abstain / len(rows) if rows else None,
        "mean_region_size_among_detects": float(sum(region_sizes) / len(region_sizes)) if region_sizes else None,
        "region_coverage_among_detects": (cover / cover_n) if cover_n else None,
        "n_detects_for_region_metrics": cover_n,
        "exact_loc_among_detects": (loc_ok / loc_n) if loc_n else None,
        "counts": {
            "tp": tp, "fp": fp, "n_pos": n_pos, "n_neg": n_neg, "abstain": abstain,
            "region_cover_num": cover, "region_cover_den": cover_n,
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cfg = LTownHypConfig()
    cands = registered_candidates()
    print(f"candidates={len(cands)} cal={CAL_SHA256[:12]}…", flush=True)

    raw: list[dict[str, Any]] = []
    for sid in all_scenario_ids():
        for seed in _seeds(sid):
            print(f"  {sid} seed={seed}", flush=True)
            raw.append(run_ltown_scenario(sid, SCRATCH / sid / f"s{seed}", cfg=cfg, seed=seed))

    train = [r for r in raw if r["split"] == "train"]
    dev = [r for r in raw if r["split"] == "dev"]
    test = [r for r in raw if r["split"] == "test"]

    tau_dev = _select_tau_dev(dev, cfg)
    print(f"frozen tau_dev={tau_dev}", flush=True)
    # provisional decisions for region eps
    for r in raw:
        r["hypothesis"] = _apply_detection(r["hypothesis"], tau_dev, cfg)

    eps = _select_region_eps(dev, tau_dev, cfg)
    print(f"frozen region_eps={eps} (intended coverage {cfg.intended_coverage})", flush=True)

    final: list[dict[str, Any]] = []
    for r in raw:
        h = _apply_detection(r["hypothesis"], tau_dev, cfg)
        h = apply_region_eps(h, eps, r["n_candidates"], cfg)
        r2 = deepcopy(r)
        r2["hypothesis"] = h
        final.append(r2)

    dev_f = [r for r in final if r["split"] == "dev"]
    test_f = [r for r in final if r["split"] == "test"]
    train_f = [r for r in final if r["split"] == "train"]
    m_dev = _metrics(dev_f)
    # Signature thresholds matched to hypothesis DEV burden/abstention
    tau_lo, tau_sig = _select_signature_thresholds(
        dev_f, target_fpr=m_dev["fpr_detect"] or 0.0, target_abstain=m_dev["abstention_rate"] or 0.0
    )
    print(f"signature tau_lo={tau_lo} tau={tau_sig}", flush=True)

    for r in final:
        a = float(r["baseline_signature_raw"]["abs_sum_m3h"])
        dec = _signature_decide(a, tau_sig, tau_lo)
        r["baseline_signature"] = {
            **r["baseline_signature_raw"],
            "tau_lo": tau_lo,
            "tau": tau_sig,
            "decision": dec,
            "detect": dec == "leak",
            "localized_node": r["baseline_signature_raw"]["dominant"] if dec == "leak" else None,
            "abstain": dec == "inconclusive",
        }

    def sig_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n_pos = n_neg = tp = fp = abstain = 0
        loc_ok = loc_n = 0
        for r in rows:
            b = r["baseline_signature"]
            if b["decision"] == "inconclusive":
                abstain += 1
            pred = b["decision"] == "leak"
            if r["has_new_leak"]:
                n_pos += 1
                tp += int(pred)
                if pred:
                    loc_n += 1
                    loc_ok += int(b.get("localized_node") == r.get("true_leak_node"))
            else:
                n_neg += 1
                fp += int(pred)
        return {
            "n": len(rows),
            "tpr_detect": (tp / n_pos) if n_pos else None,
            "fpr_detect": (fp / n_neg) if n_neg else None,
            "abstention_rate": abstain / len(rows) if rows else None,
            "exact_loc_among_detects": (loc_ok / loc_n) if loc_n else None,
            "counts": {"tp": tp, "fp": fp, "n_pos": n_pos, "n_neg": n_neg, "abstain": abstain},
            "note": "Signature region = singleton dominant sensor; no calibrated multi-node region.",
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "ltown_synthetic_feasibility",
        "preserves_toy_results": "outputs/hypothesis_synthetic/ (untouched)",
        "calibration_sha256": CAL_SHA256,
        "n_candidates": len(cands),
        "candidates": list(cands),
        "candidate_rule": "all_pressure_sensors_from_sensors_metadata_yaml",
        "injected_leaks_represented_in_candidates": True,
        "generator": {
            "observations": "EPANET steady on calibrated L-Town + scenario perturbation",
            "H0_H1_predictions": "same EPANET generator",
            "linear_approximation": False,
            "h1_nuisance": "nested_frozen_at_H0_MLE",
        },
        "config": cfg.__dict__,
        "frozen_from_dev": {
            "tau_dev": tau_dev,
            "region_eps": eps,
            "intended_coverage": cfg.intended_coverage,
            "signature_tau_lo": tau_lo,
            "signature_tau": tau_sig,
            "region_eps_is_probability": False,
        },
        "split_map": SPLIT_OF,
        "method_m_temporal_comparison": "inapplicable_vs_steady_snapshots",
        "metrics": {
            "train_hypothesis": _metrics(train_f),
            "dev_hypothesis": _metrics(dev_f),
            "test_hypothesis": _metrics(test_f),
            "dev_signature": sig_metrics(dev_f),
            "test_signature": sig_metrics(test_f),
        },
        "rows": final,
        "scope_exclusions": [
            "no_measured_evaluation",
            "no_2019",
            "no_production",
            "no_tiger",
            "no_ui",
            "no_deployment",
            "no_tuning_on_test",
            "no_retune_of_frozen_toy",
        ],
    }

    (OUT / "ltown_synthetic_feasibility_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    (OUT / "LTOWN_SYNTHETIC_FEASIBILITY_RESULTS.md").write_text(_render(payload))
    print("TEST", payload["metrics"]["test_hypothesis"])
    print("TEST signature", payload["metrics"]["test_signature"])
    return 0


def _render(payload: dict[str, Any]) -> str:
    th = payload["metrics"]["test_hypothesis"]
    ts = payload["metrics"]["test_signature"]
    dh = payload["metrics"]["dev_hypothesis"]
    lines = [
        "# Calibrated L-Town H0/H1 — synthetic feasibility",
        "",
        f"Generated: `{payload['generated_at_utc']}`",
        "",
        f"Frozen calibration: `{payload['calibration_sha256']}`  ",
        f"Candidates: **{payload['n_candidates']}** pressure-sensor junctions (all represented eval leaks)  ",
        f"DEV-frozen: `tau_dev={payload['frozen_from_dev']['tau_dev']}`, "
        f"`region_eps={payload['frozen_from_dev']['region_eps']}` "
        f"(not a probability; intended coverage {payload['frozen_from_dev']['intended_coverage']})  ",
        f"Signature (DEV-matched burden): `tau_lo={payload['frozen_from_dev']['signature_tau_lo']}`, "
        f"`tau={payload['frozen_from_dev']['signature_tau']}`",
        "",
        "Toy stage preserved under `outputs/hypothesis_synthetic/` (see `AUDIT_TOY_SYNTHETIC.md`).  ",
        "**Method M temporal comparison: inapplicable** vs isolated steady snapshots.",
        "",
        "## Generator / bounds",
        "",
        "- Obs and H0/H1: same nonlinear EPANET on calibrated L-Town (no linear approx for reported J).",
        "- H1 nested: nuisance frozen at H0 MLE; only q_c>=0 added (no extra flexibility).",
        "- Scenario perturbations designed inside scale/rho/q boxes (see per-row `bound_notes`).",
        "",
        "## DEV freeze check (exact counts in JSON)",
        "",
        f"- Hypothesis DEV: TPR={dh['tpr_detect']} FPR={dh['fpr_detect']} "
        f"abstain={dh['abstention_rate']} "
        f"region_cov={dh['region_coverage_among_detects']} "
        f"(n_detects={dh['n_detects_for_region_metrics']}) "
        f"mean_|R|={dh['mean_region_size_among_detects']}",
        "",
        "## TEST metrics (fresh scenarios; not used for eps/tau)",
        "",
        "| Method | n | TPR | FPR | Abstention | mean |R| | Coverage | Exact loc / detects |",
        "|--------|--:|----:|----:|-----------:|--------:|---------:|--------------------:|",
        f"| H0/H1 | {th['n']} | {th['tpr_detect']} | {th['fpr_detect']} | {th['abstention_rate']} | "
        f"{th['mean_region_size_among_detects']} | {th['region_coverage_among_detects']} | {th['exact_loc_among_detects']} |",
        f"| Signature (matched) | {ts['n']} | {ts['tpr_detect']} | {ts['fpr_detect']} | {ts['abstention_rate']} | "
        f"1 (singleton) | n/a (singleton) | {ts['exact_loc_among_detects']} |",
        "",
        f"Counts hypothesis test: `{th['counts']}`  ",
        f"Counts signature: `{ts['counts']}`",
        "",
        "## Per-scenario",
        "",
        "| ID | Split | Truth | Decision | dJ | Best | |R| | Cover | Sig |",
        "|----|-------|-------|----------|---:|------|----:|:----:|-----|",
    ]
    for r in payload["rows"]:
        h = r["hypothesis"]
        truth = r["true_leak_node"] or "—"
        cover = "—"
        if r["has_new_leak"] and h["decision"] == "leak":
            cover = "Y" if r["true_leak_node"] in h["candidate_region"] else "N"
        lines.append(
            f"| `{r['scenario_id']}` | {r['split']} | {truth} | **{h['decision']}** | "
            f"{h['delta_J']:.4f} | {h['best_candidate']} | {h['region_size']} | {cover} | "
            f"{r['baseline_signature']['decision']} |"
        )
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "Synthetic only. No measured evaluation, 2019, production, Tiger, UI, or deployment.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
