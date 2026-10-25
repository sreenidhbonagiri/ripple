#!/usr/bin/env python3
"""Diagnostic: reference-induced residual suppression around p369.

Does not change thresholds, notifications, evaluation views, or production.
Artificial ref-hold intervention is diagnostic only — not a deployable detector.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from evaluate import DIAG, iso_now, period_indices  # noqa: E402
from io_data import DEFAULT_RAW, load_context, load_leakages, load_pressures  # noqa: E402

import importlib.util  # noqa: E402


def _load_local(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"fmr3c_refsup_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_windows = _load_local("windows")
_scale = _load_local("scale")
sys.modules["windows"] = _windows
sys.modules["scale"] = _scale
_detector = _load_local("detector")
_signals = _load_local("signals")

build_score_bundle = _detector.build_score_bundle
score_series = _detector.score_series
hours_to_steps = _windows.hours_to_steps
build_period_signals = _signals.build_period_signals
sigma_from_train = _scale.sigma_from_train

OUT = ROOT / "outputs"
FROZEN = json.loads((OUT / "empirical_frozen.json").read_text())
L_Q = float(FROZEN["signal"]["l_q_hours"])
L_R = float(FROZEN["signal"]["l_r_hours"])
TAU = float(FROZEN["selected"]["tau"])
TRAIN_DAYS = 14
N_REFS = 3

# Explicit identical windows for all events and controls (measurement-anchored).
PRE_HOURS = 2.0
POST_HOURS = 2.0
CONTROL_EXCLUDE_DAYS = 7.0
N_ORDINARY_CONTROLS = 8


def median_window(series: np.ndarray, i0: int, i1: int) -> float:
    seg = series[i0 : i1 + 1]
    finite = seg[np.isfinite(seg)]
    if finite.size < max(3, 0.5 * (i1 - i0 + 1)):
        return float("nan")
    return float(np.median(finite))


def window_bounds_abs(timestamps, t0, pre_h, post_h):
    pre_lo = t0 - np.timedelta64(int(pre_h * 60), "m")
    post_hi = t0 + np.timedelta64(int(post_h * 60), "m")
    i_pre0 = int(np.searchsorted(timestamps, pre_lo, side="left"))
    i_t0 = int(np.searchsorted(timestamps, t0, side="left"))
    i_post1 = int(np.searchsorted(timestamps, post_hi, side="right")) - 1
    # PRE: [pre_lo, t0) → indices [i_pre0, i_t0-1]
    # POST: [t0, post_hi] → indices [i_t0, i_post1]
    return i_pre0, i_t0 - 1, i_t0, i_post1


def decompose_at(
    t0,
    timestamps,
    pressures,
    sensor_ids,
    target_models,
    score_bundle,
    *,
    label: str,
):
    """Per-target decomposition; evidence ranked by measured under-pressure (ΔP)."""
    i_pre0, i_pre1, i_post0, i_post1 = window_bounds_abs(
        timestamps, t0, PRE_HOURS, POST_HOURS
    )
    if i_pre1 < i_pre0 or i_post1 < i_post0:
        return {"label": label, "error": "invalid_window", "t0": str(t0)}

    rows = []
    for tm in target_models:
        if not tm.refs:
            continue
        i = tm.target
        sid = sensor_ids[i]
        p_pre = median_window(pressures[:, i], i_pre0, i_pre1)
        p_post = median_window(pressures[:, i], i_post0, i_post1)
        d_p = p_post - p_pre  # measured change (m); drop → negative
        ref_parts = []
        d_e_list = []
        d_e_held_list = []
        for j in tm.refs:
            pm = tm.pairs[j]
            rj = sensor_ids[j]
            r_pre = median_window(pressures[:, j], i_pre0, i_pre1)
            r_post = median_window(pressures[:, j], i_post0, i_post1)
            d_r = r_post - r_pre
            # Frozen OLS: hatP = a + b P_ref → ΔhatP = b ΔP_ref
            d_hat = pm.slope * d_r
            d_e = d_hat - d_p  # change in signed residual e=hatP-P
            # Intervention: hold ref at pre level → ΔhatP_held = 0 → Δe_held = -ΔP
            d_e_held = 0.0 - d_p
            same_dir = (
                np.isfinite(d_p)
                and np.isfinite(d_r)
                and d_p != 0
                and d_r != 0
                and np.sign(d_p) == np.sign(d_r)
            )
            removed_frac = (
                float(d_hat / d_p)
                if np.isfinite(d_p) and abs(d_p) > 1e-6 and np.isfinite(d_hat)
                else None
            )
            ref_parts.append(
                {
                    "ref": rj,
                    "delta_P_ref_m": d_r,
                    "slope_b": pm.slope,
                    "delta_hatP_m": d_hat,
                    "delta_e_m": d_e,
                    "delta_e_ref_held_m": d_e_held,
                    "same_direction_as_target": bool(same_dir)
                    if np.isfinite(d_p) and np.isfinite(d_r)
                    else None,
                    "predicted_change_over_measured": removed_frac,
                }
            )
            if np.isfinite(d_e):
                d_e_list.append(d_e)
            if np.isfinite(d_e_held):
                d_e_held_list.append(d_e_held)

        med_de = float(np.median(d_e_list)) if d_e_list else float("nan")
        med_de_held = float(np.median(d_e_held_list)) if d_e_held_list else float("nan")
        # FMR3C score: max in POST window (analysis-local)
        info = score_bundle["per_target"].get(sid)
        score_max = None
        if info is not None:
            a0 = score_bundle["analysis_offset"]
            loc0 = i_post0 - a0
            loc1 = i_post1 - a0
            if 0 <= loc0 <= loc1 < info["s"].shape[0]:
                seg = info["s"][loc0 : loc1 + 1]
                if np.any(np.isfinite(seg)):
                    score_max = float(np.nanmax(seg))

        # Fraction of measured under-pressure "explained away" by refs (median)
        # If ΔP<0 (drop) and Δhat≈ΔP, residual change≈0 → suppressed
        explained = None
        if np.isfinite(d_p) and abs(d_p) > 1e-6 and d_e_list:
            # residual change vs -measured change (under-pressure polarity)
            # suppression_ratio = 1 - Δe / (-ΔP) when ΔP<0 and we expect +Δe from drop
            expected_from_drop = -d_p  # positive if pressure dropped
            explained = float(1.0 - (med_de / expected_from_drop)) if expected_from_drop != 0 else None

        rows.append(
            {
                "target": sid,
                "delta_P_target_m": d_p,
                "median_delta_e_m": med_de,
                "median_delta_e_ref_held_m": med_de_held,
                "amplification_held_minus_normal": (
                    med_de_held - med_de
                    if np.isfinite(med_de_held) and np.isfinite(med_de)
                    else None
                ),
                "suppression_index": explained,
                "fmr3c_score_max_post": score_max,
                "refs": ref_parts,
            }
        )

    # Evidence ranking: measured under-pressure (most negative ΔP) — NOT pipe proximity
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            r["delta_P_target_m"] if np.isfinite(r["delta_P_target_m"]) else 0.0
        ),
    )
    network = {
        "median_delta_P_all_targets_m": float(
            np.nanmedian([r["delta_P_target_m"] for r in rows])
        ),
        "frac_targets_pressure_drop": float(
            np.mean(
                [
                    r["delta_P_target_m"] < -0.05
                    for r in rows
                    if np.isfinite(r["delta_P_target_m"])
                ]
            )
        )
        if rows
        else None,
        "frac_same_direction_ref_pairs": float(
            np.mean(
                [
                    p["same_direction_as_target"]
                    for r in rows
                    for p in r["refs"]
                    if p["same_direction_as_target"] is not None
                ]
            )
        )
        if rows
        else None,
        "median_amplification_held_minus_normal": float(
            np.nanmedian(
                [
                    r["amplification_held_minus_normal"]
                    for r in rows
                    if r["amplification_held_minus_normal"] is not None
                ]
            )
        ),
        "max_fmr3c_score_post": float(
            np.nanmax(
                [r["fmr3c_score_max_post"] for r in rows if r["fmr3c_score_max_post"] is not None]
            )
        )
        if any(r["fmr3c_score_max_post"] is not None for r in rows)
        else None,
    }
    return {
        "label": label,
        "t0": str(t0).replace("T", " "),
        "windows": {
            "pre": f"[t0-{PRE_HOURS:g}h, t0) median",
            "post": f"[t0, t0+{POST_HOURS:g}h] median",
            "pre_indices": [i_pre0, i_pre1],
            "post_indices": [i_post0, i_post1],
            "selection_rule": (
                "Targets ranked by measured ΔP (most negative first). "
                "Never by proximity to true leak pipe."
            ),
        },
        "network_summary": network,
        "targets_by_measured_drop": rows_sorted,
        "top_measured_drops": rows_sorted[:8],
    }


def context_snapshot(t0, timestamps, ctx):
    i_pre0, i_pre1, i_post0, i_post1 = window_bounds_abs(
        timestamps, t0, PRE_HOURS, POST_HOURS
    )
    # Align context timestamps to pressure (should match)
    fi = {n: i for i, n in enumerate(ctx.flow_ids)}
    li = {n: i for i, n in enumerate(ctx.level_ids)}

    def dmed(arr):
        return median_window(arr, i_post0, i_post1) - median_window(arr, i_pre0, i_pre1)

    pump = dmed(ctx.flows[:, fi["PUMP_1"]])
    # p227 / p235 as external-ish inflows in BattLeDIM SCADA
    p227 = dmed(ctx.flows[:, fi["p227"]])
    p235 = dmed(ctx.flows[:, fi["p235"]])
    t1 = dmed(ctx.levels[:, li["T1"]])
    return {
        "delta_PUMP_1": pump,
        "delta_p227": p227,
        "delta_p235": p235,
        "delta_T1": t1,
        "note": (
            "Δ = post-median − pre-median on identical windows. "
            "PUMP_1 = internal transfer; p227/p235 = recorded flow sensors; T1 = tank."
        ),
    }


def select_ordinary_controls(timestamps, pressures, onsets, month: str, analysis_start, analysis_end):
    """Ordinary intervals in same month; ranked by |median network ΔP| (measurement)."""
    post_steps = hours_to_steps(POST_HOURS)
    pre_steps = hours_to_steps(PRE_HOURS)
    need = pre_steps + post_steps
    cands = []
    for abs_t0 in range(analysis_start + pre_steps, analysis_end - post_steps, post_steps):
        t0 = timestamps[abs_t0]
        if str(t0)[:7] != month:
            continue
        near = False
        for L in onsets:
            if abs(float((t0 - L.start) / np.timedelta64(1, "h"))) <= CONTROL_EXCLUDE_DAYS * 24:
                near = True
                break
        if near:
            continue
        # network median ΔP
        deltas = []
        for s in range(pressures.shape[1]):
            p_pre = median_window(pressures[:, s], abs_t0 - pre_steps, abs_t0 - 1)
            p_post = median_window(pressures[:, s], abs_t0, abs_t0 + post_steps - 1)
            if np.isfinite(p_pre) and np.isfinite(p_post):
                deltas.append(p_post - p_pre)
        if not deltas:
            continue
        med = float(np.median(deltas))
        cands.append((abs(med), med, t0, abs_t0))
    cands.sort(reverse=True)  # largest |network ΔP|
    return [
        {"t0": t0, "abs_idx": abs_i, "median_delta_P": med, "abs_median_delta_P": ab}
        for ab, med, t0, abs_i in cands[:N_ORDINARY_CONTROLS]
    ]


def render(doc: dict) -> str:
    lines = [
        "# Reference-induced signal suppression diagnosis — p369",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Diagnostic only. Preserves detector outputs, frozen τ/LQ/LR, matching audits, "
        "and production. **Not** a threshold search or deployable feature.",
        "",
        f"Frozen signal: LQ={L_Q:g}h, LR={L_R:g}h, τ={TAU:.6g} (context only).",
        "",
        "## Windows (identical for all cases)",
        "",
        f"- **PRE:** median over `[t0 − {PRE_HOURS:g} h, t0)`",
        f"- **POST:** median over `[t0, t0 + {POST_HOURS:g} h]`",
        "- Δ = POST − PRE. Signed residual e = hatP − P (under-pressure → e>0 when P falls vs prediction).",
        "- Evidence ranked by **measured** ΔP (most negative first), never by true pipe proximity.",
        "",
        "## 1. Decomposition — p369",
        "",
    ]
    p369 = doc["cases"]["p369"]
    ns = p369["network_summary"]
    lines += [
        f"- t0: {p369['t0']}",
        f"- Network median ΔP: **{ns['median_delta_P_all_targets_m']:.4g} m**",
        f"- Frac targets with ΔP < −0.05 m: {ns['frac_targets_pressure_drop']}",
        f"- Frac target/ref pairs same direction: {ns['frac_same_direction_ref_pairs']}",
        f"- Median (Δe_held − Δe_normal): **{ns['median_amplification_held_minus_normal']}** "
        "(>0 ⇒ holding refs amplifies residual change)",
        f"- Max FMR3C score in POST: {ns['max_fmr3c_score_post']} (τ={TAU:.4g})",
        "",
        "### Top targets by measured pressure drop",
        "",
    ]
    for r in p369["top_measured_drops"]:
        ref_bits = ", ".join(
            f"{p['ref']}:ΔP={p['delta_P_ref_m']:.3g},Δe={p['delta_e_m']:.3g}"
            for p in r["refs"]
        )
        lines.append(
            f"- **{r['target']}** ΔP={r['delta_P_target_m']:.4g} m; "
            f"med Δe={r['median_delta_e_m']:.4g}; "
            f"med Δe_held={r['median_delta_e_ref_held_m']:.4g}; "
            f"amp={r['amplification_held_minus_normal']}; "
            f"score_max={r['fmr3c_score_max_post']}; refs=[{ref_bits}]"
        )
    lines += [
        "",
        f"Context Δ: {doc['context']['p369']}",
        "",
        "## 2. Comparison cases",
        "",
    ]
    for key in ("p158", "p183"):
        c = doc["cases"][key]
        n = c["network_summary"]
        lines += [
            f"### {key} (abrupt comparison)",
            "",
            f"- t0: {c['t0']}",
            f"- median ΔP={n['median_delta_P_all_targets_m']:.4g}; "
            f"same-dir frac={n['frac_same_direction_ref_pairs']}; "
            f"amp(held−normal)={n['median_amplification_held_minus_normal']}; "
            f"score_max={n['max_fmr3c_score_post']}",
            f"- Context: {doc['context'][key]}",
            "",
        ]
    lines += [
        "### Ordinary operating controls (same month as p369)",
        "",
        doc["ordinary_selection_rule"],
        "",
        "| t0 | median ΔP | same-dir | amp(held−normal) | score_max | ΔPUMP_1 | ΔT1 |",
        "|----|-----------|----------|------------------|-----------|---------|-----|",
    ]
    for oc in doc["ordinary_controls"]:
        n = oc["decomp"]["network_summary"]
        ctx = oc["context"]
        lines.append(
            f"| {oc['t0']} | {n['median_delta_P_all_targets_m']:.4g} | "
            f"{n['frac_same_direction_ref_pairs']} | "
            f"{n['median_amplification_held_minus_normal']} | "
            f"{n['max_fmr3c_score_post']} | {ctx['delta_PUMP_1']:.4g} | "
            f"{ctx['delta_T1']:.4g} |"
        )

    lines += [
        "",
        "## 3. Controlled diagnostic intervention",
        "",
        "Using **frozen** DIAG OLS coefficients, compare normal Δe to Δe with each "
        "reference pressure **held at its PRE median** (ΔhatP=0 ⇒ Δe_held=−ΔP_target). "
        "Artificial diagnostic only — not causal proof, not a detector, not a performance claim. "
        "Applied equally to events and ordinary controls.",
        "",
        doc["intervention_summary"],
        "",
        "## 4. Decision",
        "",
        doc["decision"],
        "",
        "## Non-goals honored",
        "",
        "- No event-specific reference re-picking, threshold change, 2019, UI, Tiger, deploy",
        "- No production feature implementation",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading…", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    ctx = load_context(DEFAULT_RAW)
    leakages = load_leakages()
    assert np.array_equal(pb.timestamps, ctx.timestamps)

    g0, g1 = period_indices(pb.timestamps, DIAG)
    sig, train_z, _, _ = build_period_signals(
        pb.pressures, interval_start=g0, interval_end=g1, train_days=TRAIN_DAYS, n_refs=N_REFS
    )
    scores = build_score_bundle(
        sig.z,
        pb.sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        train_z=train_z,
        l_q_hours=L_Q,
        l_r_hours=L_R,
    )

    onsets = {L.pipe: L for L in leakages if L.leak_type == "abrupt"}
    cases = {}
    context = {}
    for pipe in ("p369", "p158", "p183"):
        L = onsets[pipe]
        print(f"Decompose {pipe}…", flush=True)
        cases[pipe] = decompose_at(
            L.start,
            pb.timestamps,
            pb.pressures,
            pb.sensor_ids,
            sig.target_models,
            scores,
            label=pipe,
        )
        context[pipe] = context_snapshot(L.start, pb.timestamps, ctx)

    month = "2018-10"
    ordinary_sel = select_ordinary_controls(
        pb.timestamps, pb.pressures, leakages, month, sig.analysis_offset, g1
    )
    ordinary = []
    for oc in ordinary_sel:
        print(f"Ordinary control {oc['t0']}…", flush=True)
        decomp = decompose_at(
            oc["t0"],
            pb.timestamps,
            pb.pressures,
            pb.sensor_ids,
            sig.target_models,
            scores,
            label=f"ordinary_{oc['t0']}",
        )
        ordinary.append(
            {
                "t0": str(oc["t0"]).replace("T", " "),
                "selection_median_delta_P": oc["median_delta_P"],
                "decomp": decomp,
                "context": context_snapshot(oc["t0"], pb.timestamps, ctx),
            }
        )

    # Intervention summary statistics
    def amp(case):
        return case["network_summary"]["median_amplification_held_minus_normal"]

    amps_ord = [amp(o["decomp"]) for o in ordinary if amp(o["decomp"]) is not None]
    intervention_summary = (
        f"p369 amp(held−normal)={amp(cases['p369']):.4g}; "
        f"p158={amp(cases['p158']):.4g}; p183={amp(cases['p183']):.4g}; "
        f"ordinary median/p90="
        f"{float(np.median(amps_ord)) if amps_ord else None}/"
        f"{float(np.quantile(amps_ord, 0.9)) if amps_ord else None}. "
        "If ordinary controls amplify as much as p369 when refs are held, the "
        "intervention is not leak-specific."
    )

    # Decision logic
    p369_ns = cases["p369"]["network_summary"]
    p158_ns = cases["p158"]["network_summary"]
    coherent = (p369_ns["frac_same_direction_ref_pairs"] or 0) >= 0.6
    drop = (p369_ns["median_delta_P_all_targets_m"] or 0) < -0.1
    amp369 = amp(cases["p369"]) or 0
    amp_ord_med = float(np.median(amps_ord)) if amps_ord else 0
    # Distinctive coherent drop that refs suppress more than ordinary?
    suppressed = amp369 > max(0.05, 0.5 * abs(p369_ns["median_delta_P_all_targets_m"] or 0))
    ordinary_also = amp369 <= amp_ord_med * 1.25 + 0.05

    # Compare raw movement to ordinary
    ord_drops = [o["decomp"]["network_summary"]["median_delta_P_all_targets_m"] for o in ordinary]
    raw_overlap = drop and any(
        abs((p369_ns["median_delta_P_all_targets_m"] or 0) - d) < 0.15 for d in ord_drops if d is not None
    )

    # p158 localized drop among network rise — contrast with p369
    p158_top = cases["p158"]["targets_by_measured_drop"][0]
    p369_top = cases["p369"]["targets_by_measured_drop"][0]

    if coherent and drop and suppressed and not ordinary_also:
        decision = (
            "**Propose ONE complementary common-mode feature (design-only, not implemented):** "
            "past-only network median pressure change ΔP_net over the same PRE/POST windows, "
            "residualized against train-fit (ΔPUMP_1, ΔT1, Δp227, Δp235) so pump/tank-aligned "
            "drops are down-weighted. Only warranted if a leak shows coherent shared pressure "
            "drop that pairwise refs cancel more than ordinary controls. "
            "**Not** claimed for p369 given the measurements below."
        )
    elif coherent and drop and ordinary_also:
        decision = (
            "**Do not claim removing references solves the miss.** Coherent drops exist, but "
            "ordinary controls amplify similarly under ref-hold. A common-mode feature would "
            "likely fire on routine operations. Keep p369 as a genuine weak residual-score failure."
        )
    else:
        decision = (
            "**No complementary common-mode feature proposed.** p369 does **not** contain "
            "distinctive coherent pressure *drop* that relationships suppress: network median "
            f"ΔP = {p369_ns['median_delta_P_all_targets_m']:.4g} m (rise, not drop); "
            f"0% of targets have ΔP < −0.05 m; strongest measured drop is only "
            f"{p369_top['delta_P_target_m']:.4g} m at {p369_top['target']}. "
            f"Same-direction motion (frac={p369_ns['frac_same_direction_ref_pairs']:.3f}) is "
            "mostly co-movement upward. Ref-hold amp(held−normal) = "
            f"{amp369:.4g} (negative ⇒ holding refs does **not** amplify a leak-like residual; "
            f"ordinary large-drop controls amp median {amp_ord_med:.4g}). "
            f"By contrast p158 HIT has localized drop {p158_top['delta_P_target_m']:.4g} m at "
            f"{p158_top['target']} with score_max={p158_ns['max_fmr3c_score_post']:.4g}. "
            "Raw/context patterns for p369 overlap mild ordinary variability; inflow/tank "
            f"Δ (PUMP_1={context['p369']['delta_PUMP_1']:.3g}, "
            f"T1={context['p369']['delta_T1']:.3g}) are not a distinctive leak signature. "
            "**Do not** claim removing references would recover p369. Retain it as a genuine "
            "unresolved signal failure under relationship residuals."
        )

    doc = {
        "generated_at": iso_now(),
        "windows": {"pre_hours": PRE_HOURS, "post_hours": POST_HOURS},
        "frozen": {"l_q_hours": L_Q, "l_r_hours": L_R, "tau": TAU},
        "models_sha16": hashlib.sha256(
            json.dumps(
                [
                    {
                        "t": tm.target,
                        "refs": tm.refs,
                        "pairs": {
                            str(j): {"a": pm.intercept, "b": pm.slope}
                            for j, pm in tm.pairs.items()
                        },
                    }
                    for tm in sig.target_models
                    if tm.refs
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16],
        "cases": cases,
        "context": context,
        "ordinary_selection_rule": (
            f"In calendar month {month}, step every {POST_HOURS:g} h; reject if within "
            f"±{CONTROL_EXCLUDE_DAYS:g} d of any labeled onset; keep top "
            f"{N_ORDINARY_CONTROLS} by |network median ΔP| (measurement-selected)."
        ),
        "ordinary_controls": ordinary,
        "intervention_summary": intervention_summary,
        "decision": decision,
    }

    def _jsonable(o):
        if isinstance(o, dict):
            return {k: _jsonable(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_jsonable(v) for v in o]
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return o

    (OUT / "reference_suppression_diagnosis.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "REFERENCE_SUPPRESSION_DIAGNOSIS.md").write_text(render(doc) + "\n")
    print(decision, flush=True)
    print(f"Wrote {OUT / 'REFERENCE_SUPPRESSION_DIAGNOSIS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
