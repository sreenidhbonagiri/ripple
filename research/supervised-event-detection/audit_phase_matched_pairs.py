#!/usr/bin/env python3
"""Audit phase-matched leak/control pairs — no refit.

Compares identical scenario timestamps around leak onset. Ground truth
aligns windows only; never enters prediction or selection.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from features import build_feature_matrix, feature_names
from notifications import RECOVER_STEPS, episodes_from_scores
from schema import FEATURE_CONFIG, FLOW_SENSORS, STEPS_PER_HOUR
from splits_phase import assign_splits_phase
from train_pilot import predict_proba

SIM_DIR = ROOT / "outputs" / "synthetic_scenarios_phase"
FROZEN_PATH = ROOT / "outputs" / "phase_correction" / "frozen_model.json"
OUT = ROOT / "outputs" / "phase_pair_audit"

CREDIT_STEPS = 6 * STEPS_PER_HOUR
WARM = FEATURE_CONFIG.warm_up_steps
PRE_STEPS = CREDIT_STEPS


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if o is None or isinstance(o, (str, bool, int, float)):
        return o
    return str(o)


def score_and_features(pressures, flows, levels, frozen: dict):
    X, names = build_feature_matrix(pressures, flows, levels)
    keep = frozen.get("feature_names") or names
    if keep != names:
        X = np.ascontiguousarray(X[:, [names.index(n) for n in keep]])
    else:
        X = np.ascontiguousarray(X)
    q = np.full(X.shape[0], np.nan, dtype=np.float64)
    ok = np.all(np.isfinite(X), axis=1)
    ok[:WARM] = False
    if ok.any():
        q[ok] = predict_proba(frozen, X[ok])
    return X, keep, q


def notifier_active_series(q: np.ndarray, tau: float) -> np.ndarray:
    eps = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
    active = np.zeros(q.shape[0], dtype=bool)
    for e in eps:
        active[e.notify_idx : e.end_idx + 1] = True
    return active


def collect_pairs(manifest: dict) -> list[dict]:
    by_pair: dict[str, dict] = {}
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        pid = sc["spec"].get("pair_id")
        if not pid:
            continue
        slot = "leak" if sc["spec"]["kind"] == "leak_abrupt" else "control"
        by_pair.setdefault(pid, {})[slot] = sc
    out = []
    for pid, d in sorted(by_pair.items()):
        if "leak" in d and "control" in d:
            out.append({"pair_id": pid, "leak": d["leak"], "control": d["control"]})
    return out


def audit_pair(pair: dict, frozen: dict, names: list[str], split: str) -> dict:
    tau = float(frozen["selected"]["tau"])
    leak_sc = pair["leak"]
    ctrl_sc = pair["control"]
    L = np.load(SIM_DIR / leak_sc["npz"])
    C = np.load(SIM_DIR / ctrl_sc["npz"])
    Xl, _, ql = score_and_features(L["pressures"], L["flows"], L["levels"], frozen)
    Xc, _, qc = score_and_features(C["pressures"], C["flows"], C["levels"], frozen)
    T = min(Xl.shape[0], Xc.shape[0])
    Xl, Xc, ql, qc = Xl[:T], Xc[:T], ql[:T], qc[:T]
    act_l = notifier_active_series(ql, tau)
    act_c = notifier_active_series(qc, tau)

    onset = int(np.argmax(L["labels_abrupt_positive"][:T]))
    pre0, pre1 = onset - PRE_STEPS, onset
    cred0, cred1 = onset, onset + CREDIT_STEPS

    # Paired deltas at each t (leak - control); GT used only to choose windows
    dX = Xl - Xc
    mean = np.asarray(frozen["scaler_mean"], dtype=np.float64)
    scale = np.asarray(frozen["scaler_scale"], dtype=np.float64)
    scale = np.where(scale < 1e-12, 1.0, scale)
    coef = np.asarray(frozen["coef"], dtype=np.float64)

    def win_delta(t0, t1):
        t0 = max(0, t0)
        t1 = min(T, t1)
        if t1 <= t0:
            return None
        fin = (
            np.all(np.isfinite(Xl[t0:t1]), axis=1)
            & np.all(np.isfinite(Xc[t0:t1]), axis=1)
            & np.isfinite(ql[t0:t1])
            & np.isfinite(qc[t0:t1])
        )
        if not fin.any():
            return None
        d = dX[t0:t1][fin]
        d_mean = d.mean(axis=0)
        # Ordinary control change: control feature change over same wall duration
        # using control's own pre→credit temporal delta (not leak)
        if (t1 - t0) > STEPS_PER_HOUR and fin.sum() > STEPS_PER_HOUR:
            ctrl_temporal_std = np.nanstd(Xc[t0:t1], axis=0)
        else:
            ctrl_temporal_std = np.full(len(names), np.nan)
        z_d = d_mean / scale
        logit_contrib = z_d * coef  # how paired delta projects onto classifier
        abs_d = np.abs(d_mean)
        # exceed ordinary: |paired delta| > 2 * control temporal std
        exceed = abs_d > (2.0 * np.where(np.isfinite(ctrl_temporal_std), ctrl_temporal_std, np.inf))
        top_abs = np.argsort(-abs_d)[:10]
        top_logit = np.argsort(-np.abs(logit_contrib))[:10]
        # change-feature subset (Pd_/Fd_/Ld_)
        change_idx = [i for i, n in enumerate(names) if n.startswith(("Pd_", "Fd_", "Ld_"))]
        abs_idx = [i for i, n in enumerate(names) if i not in change_idx]
        return {
            "n_finite": int(fin.sum()),
            "mean_abs_delta": float(np.mean(abs_d)),
            "mean_abs_delta_change_feats": float(np.mean(abs_d[change_idx])),
            "mean_abs_delta_abs_feats": float(np.mean(abs_d[abs_idx])),
            "frac_feats_exceed_2x_ctrl_std": float(np.mean(exceed)),
            "frac_change_feats_exceed_2x_ctrl_std": float(np.mean(exceed[change_idx])),
            "sum_abs_logit_contrib_from_delta": float(np.sum(np.abs(logit_contrib))),
            "net_logit_contrib_from_delta": float(np.sum(logit_contrib)),
            "top_abs_delta_features": [
                {
                    "name": names[i],
                    "delta_mean": float(d_mean[i]),
                    "ctrl_temporal_std": float(ctrl_temporal_std[i])
                    if np.isfinite(ctrl_temporal_std[i])
                    else None,
                    "exceed_2x": bool(exceed[i]),
                    "logit_contrib": float(logit_contrib[i]),
                }
                for i in top_abs
            ],
            "top_logit_contrib_features": [
                {
                    "name": names[i],
                    "delta_mean": float(d_mean[i]),
                    "logit_contrib": float(logit_contrib[i]),
                }
                for i in top_logit
            ],
            "ql_mean": float(ql[t0:t1][fin].mean()),
            "qc_mean": float(qc[t0:t1][fin].mean()),
            "q_gap_leak_minus_ctrl": float(
                ql[t0:t1][fin].mean() - qc[t0:t1][fin].mean()
            ),
            "frac_leak_active": float(act_l[t0:t1][fin].mean()),
            "frac_ctrl_active": float(act_c[t0:t1][fin].mean()),
            "frac_leak_q_ge_tau": float((ql[t0:t1][fin] >= tau).mean()),
            "frac_ctrl_q_ge_tau": float((qc[t0:t1][fin] >= tau).mean()),
        }

    pre = win_delta(pre0, pre1)
    credit = win_delta(cred0, cred1)

    # Inflow context: PUMP_1 as external supply proxy (leak discharge not stored in NPZ)
    pump_i = FLOW_SENSORS.index("PUMP_1")
    Fp_l = L["flows"][:T, pump_i]
    Fp_c = C["flows"][:T, pump_i]

    def pump_win(t0, t1):
        t0, t1 = max(0, t0), min(T, t1)
        if t1 <= t0:
            return None
        pl, pc = Fp_l[t0:t1], Fp_c[t0:t1]
        return {
            "pump_leak_mean_m3h": float(np.nanmean(pl)),
            "pump_ctrl_mean_m3h": float(np.nanmean(pc)),
            "pump_delta_mean_m3h": float(np.nanmean(pl - pc)),
            "pump_delta_over_ctrl_abs": float(
                np.nanmean(pl - pc) / (np.nanmean(np.abs(pc)) + 1e-6)
            ),
        }

    # Episode outcomes on leak (for context; not selection)
    eps_l = episodes_from_scores(ql, tau=tau)
    hit = any(onset <= e.notify_idx <= onset + CREDIT_STEPS for e in eps_l)
    blocked = any(e.notify_idx < onset <= e.end_idx for e in eps_l)

    # Signal usefulness heuristics (descriptive)
    useful_physical = False
    ignored_by_clf = False
    if credit and pre:
        # Leak-induced change grows in credit vs pre on change features
        physical_lift = (
            credit["mean_abs_delta_change_feats"] - pre["mean_abs_delta_change_feats"]
        )
        useful_physical = (
            credit["frac_change_feats_exceed_2x_ctrl_std"] >= 0.15
            or physical_lift > 0.05
        )
        # Classifier: credit q_gap should rise if it uses the signal
        q_gap_lift = credit["q_gap_leak_minus_ctrl"] - pre["q_gap_leak_minus_ctrl"]
        ignored_by_clf = bool(
            useful_physical
            and q_gap_lift < 0.05
            and credit["q_gap_leak_minus_ctrl"] < 0.1
        )

    return {
        "pair_id": pair["pair_id"],
        "split": split,
        "leak_id": leak_sc["spec"]["scenario_id"],
        "control_id": ctrl_sc["spec"]["scenario_id"],
        "control_kind": ctrl_sc["spec"]["kind"],
        "phase_hours": leak_sc["spec"]["pattern_phase_offset_hours"],
        "onset_hour": leak_sc["spec"]["leak_start_hour"],
        "onset_idx": onset,
        "leak_demand_scale": leak_sc["spec"]["demand_scale"],
        "ctrl_demand_scale": ctrl_sc["spec"]["demand_scale"],
        "episode_6h_hit": hit,
        "blocked_at_onset": blocked,
        "pre_6h": pre,
        "credit_6h": credit,
        "pump_pre": pump_win(pre0, pre1),
        "pump_credit": pump_win(cred0, cred1),
        "leak_flow_note": (
            "Emitter/leak discharge was not stored in NPZs; PUMP_1 flow is the "
            "external-inflow proxy. Leak-induced effect is measured as paired "
            "leak−control feature/pump deltas at identical timestamps."
        ),
        "flags": {
            "useful_physical_delta": useful_physical,
            "classifier_ignores_delta": ignored_by_clf,
        },
    }


def summarize_group(rows: list[dict], label: str) -> dict:
    if not rows:
        return {"label": label, "n_pairs": 0}

    def mean_key(path_pre, path_cred, key):
        vals_pre, vals_cred = [], []
        for r in rows:
            if r.get(path_pre) and r.get(path_cred):
                vals_pre.append(r[path_pre][key])
                vals_cred.append(r[path_cred][key])
        return {
            "pre_mean": float(np.mean(vals_pre)) if vals_pre else None,
            "credit_mean": float(np.mean(vals_cred)) if vals_cred else None,
            "lift_credit_minus_pre": (
                float(np.mean(vals_cred) - np.mean(vals_pre))
                if vals_pre and vals_cred
                else None
            ),
        }

    n_phys = sum(1 for r in rows if r["flags"]["useful_physical_delta"])
    n_ign = sum(1 for r in rows if r["flags"]["classifier_ignores_delta"])
    n_hit = sum(1 for r in rows if r["episode_6h_hit"])
    return {
        "label": label,
        "n_pairs": len(rows),
        "n_episode_6h_hit": n_hit,
        "episode_6h_recall": n_hit / len(rows),
        "n_useful_physical_delta": n_phys,
        "n_classifier_ignores_delta": n_ign,
        "frac_useful_physical": n_phys / len(rows),
        "frac_classifier_ignores": n_ign / len(rows),
        "mean_abs_delta_change_feats": mean_key(
            "pre_6h", "credit_6h", "mean_abs_delta_change_feats"
        ),
        "frac_change_feats_exceed_2x_ctrl_std": mean_key(
            "pre_6h", "credit_6h", "frac_change_feats_exceed_2x_ctrl_std"
        ),
        "q_gap_leak_minus_ctrl": mean_key(
            "pre_6h", "credit_6h", "q_gap_leak_minus_ctrl"
        ),
        "sum_abs_logit_contrib_from_delta": mean_key(
            "pre_6h", "credit_6h", "sum_abs_logit_contrib_from_delta"
        ),
        "net_logit_contrib_from_delta": mean_key(
            "pre_6h", "credit_6h", "net_logit_contrib_from_delta"
        ),
        "pump_delta_over_ctrl": {
            "pre_mean": float(
                np.mean(
                    [
                        r["pump_pre"]["pump_delta_over_ctrl_abs"]
                        for r in rows
                        if r.get("pump_pre")
                    ]
                )
            )
            if any(r.get("pump_pre") for r in rows)
            else None,
            "credit_mean": float(
                np.mean(
                    [
                        r["pump_credit"]["pump_delta_over_ctrl_abs"]
                        for r in rows
                        if r.get("pump_credit")
                    ]
                )
            )
            if any(r.get("pump_credit") for r in rows)
            else None,
        },
    }


def decide(train_dev: dict, test: dict) -> dict:
    """Primary decision from train+DEV; test is diagnostic only."""
    # Prefer train_dev evidence
    g = train_dev if train_dev["n_pairs"] else test
    phys = g.get("frac_useful_physical") or 0
    ign = g.get("frac_classifier_ignores") or 0
    q_lift = (g.get("q_gap_leak_minus_ctrl") or {}).get("lift_credit_minus_pre")
    feat_lift = (g.get("mean_abs_delta_change_feats") or {}).get(
        "lift_credit_minus_pre"
    )
    exceed_cred = (g.get("frac_change_feats_exceed_2x_ctrl_std") or {}).get(
        "credit_mean"
    )

    evidence = []
    if exceed_cred is not None:
        evidence.append(
            f"Train/DEV: mean fraction of change-features with |leak−ctrl| > 2× "
            f"control temporal std in credit window = {exceed_cred:.3g}."
        )
    if feat_lift is not None:
        evidence.append(
            f"Train/DEV: lift in mean |Δ| change-features (credit−pre) = {feat_lift:.4g}."
        )
    if q_lift is not None:
        evidence.append(
            f"Train/DEV: lift in mean (q_leak−q_ctrl) (credit−pre) = {q_lift:.4g}."
        )
    evidence.append(
        f"Train/DEV: frac useful_physical={phys:.3g}; frac classifier_ignores={ign:.3g} "
        f"(n={g['n_pairs']})."
    )
    if test["n_pairs"]:
        evidence.append(
            f"Test diagnostic (not for decision): frac useful_physical="
            f"{test.get('frac_useful_physical')}; "
            f"frac classifier_ignores={test.get('frac_classifier_ignores')}; "
            f"q_gap lift={(test.get('q_gap_leak_minus_ctrl') or {}).get('lift_credit_minus_pre')}."
        )

    # Decision rules
    if phys >= 0.5 and ign >= 0.4:
        decision = "1"
        label = "Useful leak signals exist but the classifier ignores them"
        next_iv = (
            "Keep the phase-corrected scenarios; replace or reweight the supervised "
            "objective/features toward paired leak−control change residuals at onset "
            "(e.g. train on ΔX = X_leak−X_ctrl or constrain coefficients on absolute "
            "levels) under the same episode-notification gates — do not implement yet."
        )
    elif (exceed_cred is not None and exceed_cred < 0.15) and (
        feat_lift is None or feat_lift < 0.05
    ):
        decision = "2"
        label = (
            "Existing features do not reliably distinguish leaks from operations"
        )
        next_iv = (
            "Under phase-corrected scenarios, engineer or select features that "
            "measure localized pressure-drop / imbalance signatures exceeding "
            "paired control variability (current 53-D summaries are too weak or "
            "too global) — do not implement yet."
        )
    elif phys >= 0.4 and (q_lift is None or q_lift < 0.05):
        decision = "1"
        label = "Useful leak signals exist but the classifier ignores them"
        next_iv = (
            "Retarget learning to paired onset deltas / change-only directions that "
            "already move in the credit window, with episode-notification selection "
            "unchanged — do not implement yet."
        )
    else:
        decision = "2"
        label = (
            "Existing features do not reliably distinguish leaks from operations"
        )
        next_iv = (
            "Prioritize stronger leak-sensitive representations on phase-corrected "
            "matched pairs (global absolute/context features remain confounded with "
            "operations) — do not implement yet."
        )

    return {
        "decision": decision,
        "label": label,
        "evidence": evidence,
        "recommended_next_intervention": next_iv,
        "decision_basis_split_group": "train_and_synthetic_dev",
        "test_is_diagnostic_only": True,
    }


def render(doc: dict) -> str:
    lines = [
        "# Phase-matched leak/control pair audit",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Frozen phase-correction model only — **no refit**. Ground truth aligns "
        "onset windows for diagnostics; it does not enter prediction.",
        "",
        f"Frozen: C={doc['frozen']['C']}, τ={doc['frozen']['tau']} "
        f"(`outputs/phase_correction/frozen_model.json`).",
        "",
        "## Method",
        "",
        "- 16 matched pairs share `pattern_phase_offset_hours` (demand scales may differ).",
        "- At each scenario timestamp t: compare leak vs control features, q, notifier state.",
        "- Windows: pre = [onset−6h, onset), credit = [onset, onset+6h] (GT alignment only).",
        "- “Exceed ordinary control”: |mean Δfeature| > 2× control’s within-window temporal std.",
        "- Leak discharge not in NPZ; PUMP_1 is external-inflow proxy; effect = paired deltas.",
        "",
        "## Train + synthetic_dev (decision basis)",
        "",
        f"```json\n{json.dumps(doc['summary_train_dev'], indent=2)}\n```",
        "",
        "## Synthetic_test (diagnostic only)",
        "",
        f"```json\n{json.dumps(doc['summary_test'], indent=2)}\n```",
        "",
        "## Per-pair credit-window snapshot",
        "",
        "| pair | split | hit6 | phys | ignore | |Δ|chg pre→cred | q_gap pre→cred | "
        "exceed chg | pump Δ/|ctrl| |",
        "|------|-------|------|------|--------|-----------------|----------------|"
        "------------|----------------|",
    ]
    for r in doc["pairs"]:
        pre, cred = r.get("pre_6h") or {}, r.get("credit_6h") or {}
        if not cred:
            continue
        lines.append(
            f"| {r['pair_id']} | {r['split']} | {r['episode_6h_hit']} | "
            f"{r['flags']['useful_physical_delta']} | "
            f"{r['flags']['classifier_ignores_delta']} | "
            f"{pre.get('mean_abs_delta_change_feats')}→{cred.get('mean_abs_delta_change_feats')} | "
            f"{pre.get('q_gap_leak_minus_ctrl')}→{cred.get('q_gap_leak_minus_ctrl')} | "
            f"{cred.get('frac_change_feats_exceed_2x_ctrl_std')} | "
            f"{(r.get('pump_credit') or {}).get('pump_delta_over_ctrl_abs')} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        f"**{doc['decision']['decision']}. {doc['decision']['label']}**",
        "",
        "Evidence:",
        "",
    ]
    for e in doc["decision"]["evidence"]:
        lines.append(f"- {e}")
    lines += [
        "",
        "### Recommended next intervention (not implemented)",
        "",
        doc["decision"]["recommended_next_intervention"],
        "",
        "## Non-goals",
        "",
        "- No refit, measured eval, 2019, UI, Tiger, deployment",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(FROZEN_PATH.read_text())
    names = frozen.get("feature_names") or feature_names()
    manifest = json.loads((SIM_DIR / "scenario_manifest.json").read_text())
    split_info = assign_splits_phase(manifest)
    assignments = split_info["assignments"]

    pairs = collect_pairs(manifest)
    rows = []
    for p in pairs:
        leak_id = p["leak"]["spec"]["scenario_id"]
        split = assignments[leak_id]
        # control must same split
        assert assignments[p["control"]["spec"]["scenario_id"]] == split
        row = audit_pair(p, frozen, names, split)
        rows.append(row)
        print(
            f"{row['pair_id']} {split}: phys={row['flags']['useful_physical_delta']} "
            f"ignore={row['flags']['classifier_ignores_delta']} "
            f"hit={row['episode_6h_hit']}",
            flush=True,
        )

    train_dev = [r for r in rows if r["split"] in ("train", "synthetic_dev")]
    test = [r for r in rows if r["split"] == "synthetic_test"]
    # Slim per-pair for JSON (drop large nested if needed — already compact)

    doc = {
        "generated_at": iso_now(),
        "experiment": "phase_matched_pair_audit",
        "frozen": {
            "C": frozen["selected"]["C"],
            "tau": frozen["selected"]["tau"],
            "source": str(FROZEN_PATH),
        },
        "n_pairs": len(rows),
        "summary_train_dev": summarize_group(train_dev, "train_and_synthetic_dev"),
        "summary_test": summarize_group(test, "synthetic_test_diagnostic"),
        "pairs": rows,
        "preserves": [
            "outputs/phase_correction/",
            "outputs/synthetic_scenarios_phase/",
            "outputs/synthetic_scenarios/",
        ],
    }
    doc["decision"] = decide(doc["summary_train_dev"], doc["summary_test"])

    (OUT / "summary.json").write_text(json.dumps(_jsonable(doc), indent=2) + "\n")
    (OUT / "PHASE_PAIR_AUDIT.md").write_text(render(doc) + "\n")
    print(json.dumps(doc["decision"], indent=2), flush=True)
    print(f"Wrote {OUT / 'PHASE_PAIR_AUDIT.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
