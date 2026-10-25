#!/usr/bin/env python3
"""Synthetic feasibility stage for uncertainty-aware H0/H1 leak hypothesis testing.

Does not touch measured 2018/2019 events, Method M product freeze, Tiger, UI, or deploy.
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

from dual_model.hypothesis_baselines import (  # noqa: E402
    METHOD_M_CAL_SHA256,
    METHOD_M_TAU_5MIN,
    method_m_style_steady,
    select_signature_tau,
    select_sigma_floor,
    signature_match,
)
from dual_model.hypothesis_scenarios import (  # noqa: E402
    SPLIT_OF,
    all_scenario_ids,
    build_truth_and_obs,
    iter_split_scenario_ids,
    run_scenario,
)
from dual_model.hypothesis_test import HypothesisConfig, decide_hypothesis, decision_to_dict  # noqa: E402

OUT = ROOT / "outputs" / "hypothesis_synthetic"
SCRATCH = OUT / "_scratch"
CAL_HASH = "5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921"


def _seeds_for(scenario_id: str) -> list[int]:
    if "noise" in scenario_id:
        return [0, 1, 2]
    return [0]


def _apply_decision_rule(
    row: dict[str, Any],
    *,
    tau_dev: float,
    cfg: HypothesisConfig,
) -> dict[str, Any]:
    """Re-apply protocol decision from stored fits (no re-optimize)."""
    h = row["hypothesis"]
    delta_J = float(h["delta_J"])
    penalty = float(h["penalty"])
    threshold = penalty + float(tau_dev)
    q1 = float(h["leak_m3h"])
    best_c = h["best_candidate"]
    region = list(h["candidate_region"])
    d0 = float(h.get("H0_deltas_m3h", {}).get(best_c, 0.0)) if best_c else 0.0

    reasons: list[str] = []
    demand_leak_swap = (
        q1 >= cfg.q_min_m3h
        and abs(d0 - q1) <= cfg.ambiguity_delta_q_m3h
        and delta_J <= threshold + cfg.clear_margin_extra
    )
    if demand_leak_swap:
        decision = "inconclusive"
        reasons.append("demand_leak_swap_at_best_candidate")
    elif delta_J <= 1e-6 and q1 < cfg.q_min_m3h:
        decision = "no_new_leak"
        reasons.append("near_null_deltaJ_and_leak_below_qmin")
    elif 0.0 < delta_J <= threshold:
        decision = "inconclusive"
        reasons.append("improvement_inside_ambiguity_band")
    elif delta_J > threshold and q1 >= cfg.q_min_m3h:
        if len(region) >= max(2, (len(row["candidates"]) + 1) // 2) and delta_J <= threshold + cfg.clear_margin_extra:
            decision = "inconclusive"
            reasons.append("uninformative_candidate_region")
        else:
            decision = "leak"
            reasons.append("deltaJ_exceeds_penalty_and_qmin")
    else:
        decision = "no_new_leak"
        reasons.append("H0_preferred_or_leak_below_qmin")

    out = deepcopy(h)
    out["decision"] = decision
    out["tau_dev"] = float(tau_dev)
    out["reasons"] = reasons
    return out


def _select_tau_dev(dev_rows: list[dict[str, Any]], cfg: HypothesisConfig) -> float:
    """Grid on dev: maximize (TPR - FPR) - 0.5 * ambiguous_forced_leak_rate."""
    grid = [0.0, 0.02, 0.05, 0.08, 0.12, 0.2, 0.35, 0.5]
    best_tau, best_obj = 0.0, -1e9
    for tau in grid:
        tp = fp = n_pos = n_neg = 0
        amb_force = amb_n = 0
        for r in dev_rows:
            h = _apply_decision_rule(r, tau_dev=tau, cfg=cfg)
            pred_leak = h["decision"] == "leak"
            if r.get("ambiguous_by_design"):
                amb_n += 1
                amb_force += int(pred_leak)
            if r["has_new_leak"]:
                n_pos += 1
                tp += int(pred_leak)
            else:
                n_neg += 1
                fp += int(pred_leak)
        tpr = tp / n_pos if n_pos else 0.0
        fpr = fp / n_neg if n_neg else 0.0
        amb_rate = amb_force / amb_n if amb_n else 0.0
        obj = (tpr - fpr) - 0.5 * amb_rate
        if obj > best_obj:
            best_obj, best_tau = obj, tau
    return float(best_tau)


def _metrics(rows: list[dict[str, Any]], decision_key: str = "hypothesis") -> dict[str, Any]:
    n_pos = n_neg = tp = fp = 0
    incon = 0
    amb_incon = amb_n = 0
    loc_ok = loc_n = 0
    region_sizes: list[int] = []
    cover = cover_n = 0
    false_detect_non_incon = 0

    for r in rows:
        h = r[decision_key]
        dec = h["decision"]
        if dec == "inconclusive":
            incon += 1
        if r.get("ambiguous_by_design"):
            amb_n += 1
            amb_incon += int(dec == "inconclusive" or dec == "no_new_leak")
        pred = dec == "leak"
        if r["has_new_leak"]:
            n_pos += 1
            tp += int(pred)
            if pred:
                loc_n += 1
                loc_ok += int(r.get("localization_correct") is True or h.get("best_candidate") == r.get("true_leak_node"))
                region_sizes.append(int(h["region_size"]))
                cover_n += 1
                cover += int(r.get("true_leak_node") in h.get("candidate_region", []))
        else:
            n_neg += 1
            fp += int(pred)
            if pred:
                false_detect_non_incon += 1

    return {
        "n": len(rows),
        "n_leak": n_pos,
        "n_control": n_neg,
        "tpr_detect": (tp / n_pos) if n_pos else None,
        "fpr_detect": (fp / n_neg) if n_neg else None,
        "control_burden_fpr": (fp / n_neg) if n_neg else None,
        "false_detect_count_controls": false_detect_non_incon,
        "inconclusive_rate": incon / len(rows) if rows else None,
        "ambiguous_admit_rate": (amb_incon / amb_n) if amb_n else None,
        "n_ambiguous": amb_n,
        "localization_exact_among_detects": (loc_ok / loc_n) if loc_n else None,
        "localization_error_rate_among_detects": (1 - loc_ok / loc_n) if loc_n else None,
        "mean_candidate_region_size_among_detects": float(sum(region_sizes) / len(region_sizes)) if region_sizes else None,
        "region_coverage_among_detects": (cover / cover_n) if cover_n else None,
        "note": (
            "Exact-match localization is reported only among detects and is not the sole headline. "
            "Inconclusive and region coverage are first-class."
        ),
    }


def _baseline_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    n_pos = n_neg = tp = fp = 0
    loc_ok = loc_n = 0
    for r in rows:
        b = r.get(key) or {}
        pred = bool(b.get("detect"))
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
        "tpr_detect": (tp / n_pos) if n_pos else None,
        "fpr_detect": (fp / n_neg) if n_neg else None,
        "localization_exact_among_detects": (loc_ok / loc_n) if loc_n else None,
        "inconclusive_rate": None,
        "note": "Baselines force a detect/no-detect bit; they do not admit inconclusive.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cfg = HypothesisConfig(tau_dev=0.0)

    print("== fitting all scenarios (tau_dev=0 for raw ΔJ) ==")
    raw_rows: list[dict[str, Any]] = []
    for sid in all_scenario_ids():
        for seed in _seeds_for(sid):
            print(f"  {sid} seed={seed} ...", flush=True)
            row = run_scenario(sid, SCRATCH / sid / f"s{seed}", cfg=cfg, seed=seed)
            # Baselines need abs_sum for tau selection — fill placeholder then update.
            truth, wn_model, sensors, obs = build_truth_and_obs(sid, SCRATCH / sid / f"s{seed}" / "base", seed=seed)
            sig = signature_match(
                wn_model, sensors, obs, scratch=SCRATCH / sid / f"s{seed}" / "sig", tau_abs_sum_m3h=1e9
            )
            row["baseline_signature"] = sig
            row["_max_abs_qv"] = max(abs(v) for v in sig["q_v_m3h"].values())
            raw_rows.append(row)

    train_rows = [r for r in raw_rows if r["split"] == "train"]
    dev_rows = [r for r in raw_rows if r["split"] == "dev"]
    test_rows = [r for r in raw_rows if r["split"] == "test"]

    tau_dev = _select_tau_dev(dev_rows, cfg)
    print(f"== selected tau_dev={tau_dev} on development split ==")

    sigma_floor = select_sigma_floor(
        [r["_max_abs_qv"] for r in train_rows if not r["has_new_leak"]]
    )
    # Temporary signature abs sums already stored; select τ on dev using those.
    # Attach detect with a probe tau then select.
    for r in raw_rows:
        r["baseline_signature"]["tau_abs_sum_m3h"] = 0.0
    sig_tau = select_signature_tau(dev_rows)
    print(f"== signature tau={sig_tau}; method_m sigma_floor={sigma_floor} ==")

    final_rows: list[dict[str, Any]] = []
    for r in raw_rows:
        h = _apply_decision_rule(r, tau_dev=tau_dev, cfg=cfg)
        r2 = deepcopy(r)
        r2["hypothesis"] = h
        # refresh localization flags under final decision
        if r2["has_new_leak"] and h["decision"] == "leak":
            r2["localization_correct"] = h["best_candidate"] == r2["true_leak_node"]
            r2["region_covers_truth"] = r2["true_leak_node"] in h["candidate_region"]
        else:
            r2["localization_correct"] = None
            r2["region_covers_truth"] = None

        truth, wn_model, sensors, obs = build_truth_and_obs(
            r["scenario_id"], SCRATCH / r["scenario_id"] / f"s{r['seed']}" / "base2", seed=r["seed"]
        )
        r2["baseline_signature"] = signature_match(
            wn_model, sensors, obs,
            scratch=SCRATCH / r["scenario_id"] / f"s{r['seed']}" / "sig2",
            tau_abs_sum_m3h=sig_tau,
        )
        r2["baseline_method_m_style"] = method_m_style_steady(
            wn_model, sensors, obs,
            scratch=SCRATCH / r["scenario_id"] / f"s{r['seed']}" / "mm",
            sigma_floor_m3h=sigma_floor,
            tau=METHOD_M_TAU_5MIN,
        )
        r2.pop("_max_abs_qv", None)
        final_rows.append(r2)

    test_final = [r for r in final_rows if r["split"] == "test"]
    dev_final = [r for r in final_rows if r["split"] == "dev"]
    train_final = [r for r in final_rows if r["split"] == "train"]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "synthetic_feasibility",
        "branch": "research/uncertainty-aware-hypothesis",
        "calibration_sha256_ref": CAL_HASH,
        "method_m_tau_5min_ref": METHOD_M_TAU_5MIN,
        "method_m_cal_sha256_ref": METHOD_M_CAL_SHA256,
        "config": cfg.__dict__,
        "selected_tau_dev": tau_dev,
        "selected_signature_tau_m3h": sig_tau,
        "selected_method_m_sigma_floor_m3h": sigma_floor,
        "split_map": SPLIT_OF,
        "metrics": {
            "train_hypothesis": _metrics(train_final),
            "dev_hypothesis": _metrics(dev_final),
            "test_hypothesis": _metrics(test_final),
            "test_signature": _baseline_metrics(test_final, "baseline_signature"),
            "test_method_m_style": _baseline_metrics(test_final, "baseline_method_m_style"),
        },
        "rows": final_rows,
        "scope_exclusions": [
            "no_measured_event_tuning",
            "no_2019",
            "no_main_merge",
            "no_tiger",
            "no_ui",
            "no_deployment",
        ],
    }

    json_path = OUT / "synthetic_feasibility_results.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")

    md = _render_md(payload)
    (OUT / "SYNTHETIC_FEASIBILITY_RESULTS.md").write_text(md)
    print(f"Wrote {json_path}")
    print(f"Wrote {OUT / 'SYNTHETIC_FEASIBILITY_RESULTS.md'}")
    tm = payload["metrics"]["test_hypothesis"]
    print(
        "TEST hypothesis: "
        f"TPR={tm['tpr_detect']} FPR={tm['fpr_detect']} "
        f"inconclusive={tm['inconclusive_rate']} "
        f"region_cov={tm['region_coverage_among_detects']}"
    )
    return 0


def _render_md(payload: dict[str, Any]) -> str:
    tm = payload["metrics"]["test_hypothesis"]
    ts = payload["metrics"]["test_signature"]
    tmm = payload["metrics"]["test_method_m_style"]
    lines = [
        "# Uncertainty-aware H0/H1 — synthetic feasibility results",
        "",
        f"Generated: `{payload['generated_at_utc']}`",
        "",
        f"Branch: `{payload['branch']}`  ",
        f"Corrected calibration ref: `{payload['calibration_sha256_ref']}`  ",
        f"Selected `tau_dev`: **{payload['selected_tau_dev']}** (dev only)  ",
        f"Signature `τ_|Σqv|`: **{payload['selected_signature_tau_m3h']}** m³/h  ",
        f"Method M–style `σ_floor`: **{payload['selected_method_m_sigma_floor_m3h']}** m³/h; "
        f"τ_ref={payload['method_m_tau_5min_ref']}",
        "",
        "Protocol: `HYPOTHESIS_PROTOCOL.md`. Better fit ≠ proof of a leak. "
        "H1 nuisance bounds identical to H0.",
        "",
        "## Test-split headline metrics (hypothesis test)",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Detection TPR | {tm['tpr_detect']} |",
        f"| Control FPR / burden | {tm['fpr_detect']} |",
        f"| Inconclusive rate | {tm['inconclusive_rate']} |",
        f"| Ambiguous-family admit rate (dev+test amb rows in split metrics; see rows) | see per-split |",
        f"| Mean candidate region size (among detects) | {tm['mean_candidate_region_size_among_detects']} |",
        f"| Region coverage of true leak (among detects) | {tm['region_coverage_among_detects']} |",
        f"| Exact-match localization among detects (not sole headline) | {tm['localization_exact_among_detects']} |",
        f"| Localization error among detects | {tm['localization_error_rate_among_detects']} |",
        "",
        "## Baselines on the same test scenarios",
        "",
        "| Method | TPR | FPR | Exact loc among detects | Inconclusive |",
        "|--------|----:|----:|-------------------------:|-------------:|",
        f"| H0/H1 hypothesis | {tm['tpr_detect']} | {tm['fpr_detect']} | {tm['localization_exact_among_detects']} | {tm['inconclusive_rate']} |",
        f"| Dual signature | {ts['tpr_detect']} | {ts['fpr_detect']} | {ts['localization_exact_among_detects']} | n/a |",
        f"| Method M–style steady | {tmm['tpr_detect']} | {tmm['fpr_detect']} | {tmm['localization_exact_among_detects']} | n/a |",
        "",
        "Baselines do not admit ambiguity; elevated FPR on demand-mismatch controls is expected "
        "(see prior `demand_mismatch_no_leak` synthetic verification).",
        "",
        "## Per-scenario rows",
        "",
        "| ID | Split | Seed | Truth leak | Decision | ΔJ | Best c | Region | Sig detect | MM detect |",
        "|----|-------|-----:|:----------:|----------|---:|:------:|--------|:----------:|:---------:|",
    ]
    for r in payload["rows"]:
        h = r["hypothesis"]
        leak = r["true_leak_node"] or "—"
        lines.append(
            f"| `{r['scenario_id']}` | {r['split']} | {r['seed']} | {leak} | "
            f"**{h['decision']}** | {h['delta_J']:.4f} | {h['best_candidate']} | "
            f"{h['region_size']}:{','.join(h['candidate_region'])} | "
            f"{r['baseline_signature']['detect']} | {r['baseline_method_m_style']['detect']} |"
        )

    lines.extend(
        [
            "",
            "## Split metrics detail",
            "",
            "```json",
            json.dumps(payload["metrics"], indent=2),
            "```",
            "",
            "## Review gate",
            "",
            "Synthetic feasibility only. Stop for review before measured evaluation. "
            "No 2019 tuning, main merge, Tiger, UI, or deployment in this stage.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
