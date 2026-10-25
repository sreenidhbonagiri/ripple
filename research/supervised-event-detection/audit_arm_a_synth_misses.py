#!/usr/bin/env python3
"""Diagnostic audit: why Arm A misses episode-6h hits on synthetic_test.

Preserves Arm A/B freezes, prior reports, and production. No new fits or
threshold searches. Uses frozen Arm A (C, τ, coef, scaler) only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from features import build_feature_matrix
from notifications import RECOVER_STEPS, episodes_from_scores
from schema import FEATURE_CONFIG, FLOW_SENSORS, STEPS_PER_HOUR, STEP_SECONDS
from simulate import DURATION_HOURS, WARMUP_HOURS
from splits import assign_splits
from train_pilot import predict_proba

OUT = ROOT / "outputs"
SIM_DIR = OUT / "synthetic_scenarios"
ABL = OUT / "change_only_ablation"
AUDIT = OUT / "arm_a_synth_miss_audit"

CREDIT_STEPS = 6 * STEPS_PER_HOUR
SCENARIO_WEEKS = DURATION_HOURS / (24.0 * 7.0)
WARM = FEATURE_CONFIG.warm_up_steps  # 144


CAUSE_DEFS = {
    "no_crossing_in_6h": (
        "No finite q(t) ≥ τ for any t in [onset, onset+6h] (inclusive)."
    ),
    "preonset_active_block": (
        "Some episode has notify_idx < onset ≤ end_idx (notifier still active "
        "at onset), and no episode has notify_idx in [onset, onset+6h]."
    ),
    "confirmation_not_met": (
        "Reserved: this supervised notifier has no separate confirmation dwell "
        "beyond first q≥τ while inactive — always false for this pipeline."
    ),
    "warmup_missingness": (
        "Onset index < feature warm-up, or every score in the credit window is "
        "non-finite, or >50% of credit-window scores are non-finite."
    ),
}


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


def score_trajectory(pressures, flows, levels, frozen: dict) -> np.ndarray:
    X, names = build_feature_matrix(pressures, flows, levels)
    keep = frozen.get("feature_names")
    if keep is not None:
        X = np.ascontiguousarray(X[:, [names.index(n) for n in keep]])
    q = np.full(X.shape[0], np.nan, dtype=np.float64)
    ok = np.all(np.isfinite(X), axis=1)
    ok[:WARM] = False
    if ok.any():
        q[ok] = predict_proba(frozen, X[ok])
    return q


def notifier_state_series(q: np.ndarray, *, tau: float) -> dict:
    """Replay notifier; return per-step active flag and recovery run length."""
    tau_clear = tau / 2.0
    T = q.shape[0]
    active_arr = np.zeros(T, dtype=bool)
    recover_arr = np.zeros(T, dtype=np.int32)
    notify_mark = np.zeros(T, dtype=bool)
    active = False
    recover_run = 0
    for t in range(T):
        st = q[t]
        if not np.isfinite(st):
            recover_run = 0
            active_arr[t] = active
            recover_arr[t] = recover_run
            continue
        if active:
            if st < tau_clear:
                recover_run += 1
            else:
                recover_run = 0
            if recover_run >= RECOVER_STEPS:
                active = False
                recover_run = 0
        elif st >= tau:
            active = True
            recover_run = 0
            notify_mark[t] = True
        active_arr[t] = active
        recover_arr[t] = recover_run
    return {
        "active": active_arr,
        "recover_run": recover_arr,
        "notify_mark": notify_mark,
    }


def physical_context(pressures, flows, levels, t: int, *, win: int = 6) -> dict:
    """Descriptive local context at index t (not used for selection)."""
    t0 = max(0, t - win)
    t1 = min(pressures.shape[0], t + win + 1)
    P = pressures
    F = flows
    L = levels[:, 0]
    pump_i = FLOW_SENSORS.index("PUMP_1")
    dP = float(np.nanmedian(P[t])) - (
        float(np.nanmedian(P[t0])) if t > 0 else float("nan")
    )
    # network-wide median pressure level and short causal delta
    p_med = float(np.nanmedian(P[t]))
    if t >= 6:
        pd6 = float(np.nanmedian(P[t] - P[t - 6]))
        pd6_min = float(np.nanmin(P[t] - P[t - 6]))
    else:
        pd6 = pd6_min = float("nan")
    return {
        "t": t,
        "hour": t / STEPS_PER_HOUR,
        "P_median_m": p_med,
        "Pd_median_d6_m": pd6,
        "Pd_min_d6_m": pd6_min,
        "F_PUMP_1_m3h": float(F[t, pump_i]),
        "pump1_on": bool(F[t, pump_i] > 1.0),
        "L_T1_m": float(L[t]),
        "dP_median_vs_winstart_m": float(dP) if np.isfinite(dP) else None,
        "win_steps": win,
    }


def classify_miss(
    *,
    onset: int,
    q: np.ndarray,
    tau: float,
    episodes,
    hit: bool,
) -> dict:
    hi = onset + CREDIT_STEPS
    credit = slice(onset, hi + 1)
    q_c = q[credit]
    finite = np.isfinite(q_c)
    crossed = bool((finite & (q_c >= tau)).any())
    blocked = any(ep.notify_idx < onset <= ep.end_idx for ep in episodes)
    notify_in = any(onset <= ep.notify_idx <= hi for ep in episodes)
    assert hit == notify_in

    warmup = (
        onset < WARM
        or (finite.size > 0 and not finite.any())
        or (finite.size > 0 and finite.mean() < 0.5)
    )
    causes = {
        "no_crossing_in_6h": (not hit) and (not crossed),
        "preonset_active_block": (not hit) and blocked and crossed,
        # Also record block even without crossing (active but q never ≥τ in window)
        "preonset_active_at_onset": (not hit) and blocked,
        "confirmation_not_met": False,  # no confirmation stage in this notifier
        "warmup_missingness": (not hit) and warmup,
    }
    # Primary label for misses (ordered priority)
    if hit:
        primary = "hit_6h"
    elif causes["warmup_missingness"] and not crossed:
        primary = "warmup_missingness"
    elif causes["preonset_active_block"]:
        primary = "preonset_active_block"
    elif causes["preonset_active_at_onset"] and not crossed:
        primary = "preonset_active_no_crossing"
    elif causes["no_crossing_in_6h"]:
        primary = "no_crossing_in_6h"
    else:
        primary = "other_miss"

    # Persistent high-q vs recovery debt for blocked cases
    recovery_debt = None
    if blocked:
        covering = [ep for ep in episodes if ep.notify_idx < onset <= ep.end_idx]
        ep0 = covering[0]
        # From onset back to notify: fraction of finite q still ≥ τ/2 (not clearing)
        seg = q[ep0.notify_idx : onset + 1]
        fin = seg[np.isfinite(seg)]
        frac_above_clear = float((fin >= tau / 2).mean()) if fin.size else float("nan")
        frac_above_tau = float((fin >= tau).mean()) if fin.size else float("nan")
        # Steps still needed to recover at onset if below clear
        st = notifier_state_series(q, tau=tau)
        recovery_debt = {
            "covering_notify_idx": int(ep0.notify_idx),
            "covering_end_idx": int(ep0.end_idx),
            "covering_peak": float(ep0.peak_score),
            "hours_active_before_onset": float((onset - ep0.notify_idx) / STEPS_PER_HOUR),
            "frac_q_ge_tau_half_preonset_segment": frac_above_clear,
            "frac_q_ge_tau_preonset_segment": frac_above_tau,
            "active_at_onset": bool(st["active"][onset]),
            "recover_run_at_onset": int(st["recover_run"][onset]),
            "persistent_high_probability": bool(
                np.isfinite(frac_above_tau) and frac_above_tau >= 0.5
            ),
            "recovery_debt_dominant": bool(
                np.isfinite(frac_above_clear)
                and frac_above_clear >= 0.5
                and (not np.isfinite(frac_above_tau) or frac_above_tau < 0.5)
            ),
        }

    return {
        "primary": primary,
        "causes": causes,
        "crossed_in_credit": crossed,
        "blocked_at_onset": blocked,
        "notify_in_credit": notify_in,
        "recovery_debt": recovery_debt,
        "n_finite_in_credit": int(finite.sum()),
        "n_credit_steps": int(q_c.shape[0]),
        "max_q_in_credit": float(np.nanmax(q_c)) if finite.any() else None,
        "mean_q_in_credit": float(np.nanmean(q_c)) if finite.any() else None,
    }


def onset_aligned_signal(pressures, flows, levels, onset: int) -> dict:
    """GT-aligned descriptive windows only — not for prediction/selection."""
    def pack(t0, t1):
        t0 = max(0, t0)
        t1 = min(pressures.shape[0], t1)
        if t1 <= t0:
            return None
        P = pressures[t0:t1]
        F = flows[t0:t1]
        L = levels[t0:t1, 0]
        pump = F[:, FLOW_SENSORS.index("PUMP_1")]
        if t0 >= 6:
            d = pressures[t0:t1] - pressures[t0 - 6 : t1 - 6]
            pd_min = float(np.nanmean(np.nanmin(d, axis=1)))
            pd_med = float(np.nanmean(np.nanmedian(d, axis=1)))
        else:
            pd_min = pd_med = float("nan")
        return {
            "n_steps": int(t1 - t0),
            "P_median_mean": float(np.nanmean(np.nanmedian(P, axis=1))),
            "Pd_d6_min_mean": pd_min,
            "Pd_d6_median_mean": pd_med,
            "pump_on_frac": float((pump > 1.0).mean()),
            "F_PUMP_mean": float(np.nanmean(pump)),
            "L_T1_mean": float(np.nanmean(L)),
        }

    pre = pack(onset - CREDIT_STEPS, onset)
    post = pack(onset, onset + CREDIT_STEPS)
    return {"pre_6h": pre, "post_6h_credit": post}


def build_timeline_summary(
    *,
    sid: str,
    spec: dict,
    q: np.ndarray,
    y: np.ndarray,
    pressures,
    flows,
    levels,
    tau: float,
    episodes,
    kind: str,
) -> dict:
    st = notifier_state_series(q, tau=tau)
    onset = int(np.argmax(y)) if y.any() else None
    # Downsample timeline to key events + hourly samples for report size
    T = q.shape[0]
    hours = np.arange(T) / STEPS_PER_HOUR
    key_idx = set()
    for ep in episodes:
        key_idx.add(ep.notify_idx)
        key_idx.add(ep.end_idx)
    if onset is not None:
        key_idx.update(range(max(0, onset - 2), min(T, onset + CREDIT_STEPS + 3)))
    # hourly ticks after warm-up
    for h in range(WARMUP_HOURS, DURATION_HOURS + 1):
        key_idx.add(min(T - 1, h * STEPS_PER_HOUR))
    key_idx = sorted(i for i in key_idx if 0 <= i < T)

    samples = []
    for t in key_idx:
        samples.append(
            {
                "t": t,
                "hour": float(hours[t]),
                "q": float(q[t]) if np.isfinite(q[t]) else None,
                "y": bool(y[t]),
                "active": bool(st["active"][t]),
                "recover_run": int(st["recover_run"][t]),
                "notify": bool(st["notify_mark"][t]),
                "leak_open_sched": (
                    spec.get("leak_start_hour") is not None
                    and spec["leak_start_hour"]
                    <= hours[t]
                    < (spec.get("leak_end_hour") or 1e9)
                ),
                "ctx": physical_context(pressures, flows, levels, t),
            }
        )

    leak_flow_note = (
        "NPZ does not store continuous leak discharge; leak_open_sched is the "
        "registered [leak_start_hour, leak_end_hour) schedule from the scenario spec."
    )
    return {
        "scenario_id": sid,
        "kind": kind,
        "spec": {
            k: spec.get(k)
            for k in (
                "pipe",
                "pipe_group",
                "demand_scale",
                "leak_area_m2",
                "leak_start_hour",
                "leak_end_hour",
                "operating_realization",
            )
        },
        "tau": tau,
        "onset_idx": onset,
        "onset_hour": None if onset is None else onset / STEPS_PER_HOUR,
        "episodes": [
            {
                "notify_idx": int(e.notify_idx),
                "notify_hour": e.notify_idx / STEPS_PER_HOUR,
                "end_idx": int(e.end_idx),
                "end_hour": e.end_idx / STEPS_PER_HOUR,
                "peak_score": float(e.peak_score),
            }
            for e in episodes
        ],
        "leak_flow_note": leak_flow_note,
        "samples": samples,
    }


def construction_audit(manifest: dict, assignments: dict) -> dict:
    rows = []
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        spec = sc["spec"]
        sid = spec["scenario_id"]
        split = assignments.get(sid)
        rows.append(
            {
                "scenario_id": sid,
                "kind": spec["kind"],
                "split": split,
                "pipe": spec.get("pipe"),
                "pipe_group": spec.get("pipe_group"),
                "demand_scale": spec.get("demand_scale"),
                "leak_area_m2": spec.get("leak_area_m2"),
                "leak_start_hour": spec.get("leak_start_hour"),
                "leak_end_hour": spec.get("leak_end_hour"),
                "leak_duration_h": (
                    None
                    if spec.get("leak_start_hour") is None
                    else float(spec["leak_end_hour"] - spec["leak_start_hour"])
                ),
                "operating_realization": spec.get("operating_realization"),
                "hours_after_warmup_to_onset": (
                    None
                    if spec.get("leak_start_hour") is None
                    else float(spec["leak_start_hour"] - WARMUP_HOURS)
                ),
            }
        )

    def summarize_leaks(split: str) -> dict:
        L = [r for r in rows if r["kind"] == "leak_abrupt" and r["split"] == split]
        if not L:
            return {"n": 0}
        areas = [r["leak_area_m2"] for r in L]
        demands = [r["demand_scale"] for r in L]
        starts = [r["leak_start_hour"] for r in L]
        durs = [r["leak_duration_h"] for r in L]
        ops = [r["operating_realization"] for r in L]
        groups = [r["pipe_group"] for r in L]
        return {
            "n": len(L),
            "leak_area_m2": {
                "min": min(areas),
                "max": max(areas),
                "mean": float(np.mean(areas)),
            },
            "demand_scale": {
                "min": min(demands),
                "max": max(demands),
                "mean": float(np.mean(demands)),
            },
            "leak_start_hour": {
                "min": min(starts),
                "max": max(starts),
                "mean": float(np.mean(starts)),
            },
            "leak_duration_h": {
                "min": min(durs),
                "max": max(durs),
                "mean": float(np.mean(durs)),
            },
            "operating_realization_counts": {
                str(k): int(sum(1 for o in ops if o == k)) for k in sorted(set(ops))
            },
            "pipe_group_counts": {
                str(k): int(sum(1 for g in groups if g == k)) for k in sorted(set(groups))
            },
        }

    def summarize_controls(split: str) -> dict:
        C = [r for r in rows if r["kind"].startswith("control") and r["split"] == split]
        kinds = {}
        for r in C:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        demands = [r["demand_scale"] for r in C]
        return {
            "n": len(C),
            "kinds": kinds,
            "demand_scale": {
                "min": min(demands) if demands else None,
                "max": max(demands) if demands else None,
                "mean": float(np.mean(demands)) if demands else None,
            },
        }

    # Label vs phase: fraction of train positives by hour-of-scenario
    phase = {"note": (
        "Positives are always the first 6 h after leak_start on a 48 h trajectory "
        "with leaks drawn uniformly in [14 h, 38 h]. Absolute operating features "
        "can correlate with scenario clock time / diurnal phase."
    )}

    return {
        "warmup_hours": WARMUP_HOURS,
        "duration_hours": DURATION_HOURS,
        "feature_warmup_steps": WARM,
        "feature_warmup_hours": WARM / STEPS_PER_HOUR,
        "leak_start_sampling": (
            f"uniform in [{WARMUP_HOURS + 2}, {DURATION_HOURS - 10}] hours"
        ),
        "by_split_leaks": {
            s: summarize_leaks(s) for s in ("train", "synthetic_dev", "synthetic_test")
        },
        "by_split_controls": {
            s: summarize_controls(s) for s in ("train", "synthetic_dev", "synthetic_test")
        },
        "label_phase_encoding": phase,
        "control_burden_denominator": {
            "formula": "n_control_episodes / (n_control_scenarios * scenario_weeks)",
            "scenario_duration_hours": DURATION_HOURS,
            "scenario_weeks": SCENARIO_WEEKS,
            "synthetic_test_n_control": summarize_controls("synthetic_test")["n"],
            "synthetic_test_control_weeks_total": (
                summarize_controls("synthetic_test")["n"] * SCENARIO_WEEKS
            ),
            "disclosure": (
                f"Each control contributes only {DURATION_HOURS} h "
                f"({SCENARIO_WEEKS:.4g} weeks). With few controls, ep/wk is a "
                "noisy rate over a short simulated denominator — not a year-scale "
                "burden estimate."
            ),
        },
        "rows": rows,
    }


def decide(audit: dict) -> dict:
    misses = [r for r in audit["leak_results"] if not r["episode_6h_hit"]]
    n_miss = len(misses)
    prim = {}
    for m in misses:
        p = m["classification"]["primary"]
        prim[p] = prim.get(p, 0) + 1
    n_block = sum(
        1
        for m in misses
        if m["classification"]["causes"].get("preonset_active_block")
        or m["classification"]["primary"]
        in ("preonset_active_block", "preonset_active_no_crossing")
    )
    n_nocross = sum(
        1 for m in misses if m["classification"]["causes"]["no_crossing_in_6h"]
    )
    # Synchronized pre-onset notify cluster
    pre_idx = []
    for r in audit["leak_results"]:
        pre_idx.extend(r.get("preonset_notify_idxs", []))
    cluster_199 = sum(1 for i in pre_idx if 195 <= i <= 205)

    # Physical signal: compare mean Pd_d6_min post-onset vs pre for hits vs misses
    sig = audit["signal_summary"]

    votes = {"A": 0, "B": 0, "C": 0}
    evidence = []

    if n_miss and n_nocross / n_miss >= 0.4:
        votes["A"] += 2
        evidence.append(
            f"{n_nocross}/{n_miss} misses have no q≥τ in the 6 h credit window "
            "(insufficient score response at frozen τ)."
        )
    if sig.get("miss_post_minus_pre_pd_min_mean") is not None and abs(
        sig["miss_post_minus_pre_pd_min_mean"]
    ) < 0.05:
        votes["A"] += 1
        evidence.append(
            "Onset-aligned network Pd_d6_min shift on misses is near zero vs pre-window."
        )

    if n_miss and n_block / n_miss >= 0.4:
        votes["B"] += 2
        evidence.append(
            f"{n_block}/{n_miss} misses are pre-onset-active blocked (notifier state "
            "prevents a new credit-window notify)."
        )
    n_disagree = audit["counts"]["row_credit_hit_but_episode_miss"]
    if n_disagree >= 2:
        votes["B"] += 1
        evidence.append(
            f"{n_disagree} scenarios have row-credit hits but episode-6h misses "
            "(objective/notifier mismatch with row labels)."
        )

    if cluster_199 >= 5:
        votes["C"] += 2
        evidence.append(
            f"{cluster_199} pre-onset notifies cluster at indices ~199 "
            "(~16.6 h scenario time) across leaks — shared operating/phase cue."
        )
    # Controls also fire
    ctrl_rate = audit["control_test"]["episodes_per_week"]
    if ctrl_rate >= 3:
        votes["C"] += 1
        evidence.append(
            f"Synthetic_test controls alone yield {ctrl_rate:.3g} ep/wk under the "
            "same freeze — false episodes without leaks."
        )

    # Pick
    order = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
    top, top_v = order[0]
    second_v = order[1][1]
    if top_v == 0 or top_v == second_v:
        decision = "D"
        label = "Mixed or unresolved"
    else:
        decision = top
        label = {
            "A": "Mainly insufficient discriminative signal/features",
            "B": "Mainly notifier/learning-objective mismatch",
            "C": "Mainly simulator/scenario construction artifacts",
        }[top]

    # Single next intervention (at most one; not implemented here)
    if decision == "D":
        next_iv = (
            "Single next step: on synthetic DEV only, add an explicit "
            "preonset_active_block / inactive-at-onset constraint to the existing "
            "episode-selection gates (same C/τ budget; no post-hoc expansion), "
            "because the dominant miss pattern is a shared ~16.6 h operating-phase "
            "latch that also fires on controls and then blocks onset credit. "
            "Scenario-clock redesign is the alternate if gating cannot find any "
            "passing candidate. Do not implement in this audit."
        )
    elif decision == "B":
        next_iv = (
            "Keep Arm A features/labels frozen; redesign selection (and evaluation "
            "diagnostics) to penalize pre-onset latching explicitly — e.g. require "
            "inactive-at-onset for credit, or add a synthetic-DEV gate on "
            "preonset_active_block rate — without expanding the (C,τ) grid after "
            "seeing test. Do not implement in this audit."
        )
    elif decision == "C":
        next_iv = (
            "Redesign synthetic scenario clocks / operating randomization so leak "
            "credit windows are not systematically aligned with shared diurnal "
            "transitions that also fire on controls; re-run under the same episode "
            "objective. Do not implement in this audit."
        )
    else:  # A
        next_iv = (
            "Replace or augment features with onset-aligned residual/change "
            "summaries that separate leak post-onset windows from controls under "
            "the frozen episode metric (still no measured retune). Do not implement "
            "in this audit."
        )

    return {
        "decision": decision,
        "label": label,
        "votes": votes,
        "primary_cause_counts_among_misses": prim,
        "evidence": evidence,
        "recommended_next_intervention": next_iv,
    }


def render(doc: dict) -> str:
    lines = [
        "# Arm A synthetic-test miss audit (diagnostic only)",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "**Question:** Why does the full-feature classifier fail episode detection "
        "even on held-out synthetic scenarios?",
        "",
        "Preserves Arm A/B freezes, ablation reports, episode-objective outputs, "
        "and production. **No** new fits, threshold searches, simulations, or 2019.",
        "",
        f"Frozen Arm A: C={doc['frozen']['C']}, τ={doc['frozen']['tau']} "
        f"(from `outputs/change_only_ablation/arm_A_frozen_model.json`).",
        "",
        "## Cause definitions (reproducible)",
        "",
    ]
    for k, v in CAUSE_DEFS.items():
        lines.append(f"- **{k}**: {v}")
    lines += [
        "",
        "## Synthetic_test headline",
        "",
        f"- Leak scenarios: {doc['counts']['n_leak']} "
        f"(hits={doc['counts']['n_hit']}, misses={doc['counts']['n_miss']})",
        f"- Episode_6h recall: {doc['counts']['episode_6h_recall']}",
        f"- Row-credit scenario recall: {doc['counts']['row_credit_scenario_recall']}",
        f"- Row-credit hit but episode miss: "
        f"{doc['counts']['row_credit_hit_but_episode_miss']}",
        f"- Pre-onset active at onset (any miss/hit flag): "
        f"{doc['counts']['n_blocked_flag']}",
        "",
        "### Miss primary classifications",
        "",
    ]
    for k, v in sorted(doc["decision"]["primary_cause_counts_among_misses"].items()):
        lines.append(f"- `{k}`: {v}")

    lines += [
        "",
        "## Per-leak miss detail",
        "",
        "| scenario | primary | crossed | blocked | max q credit | "
        "preonset notify hrs | recovery debt |",
        "|----------|---------|---------|---------|--------------|"
        "--------------------|---------------|",
    ]
    for r in doc["leak_results"]:
        if r["episode_6h_hit"]:
            continue
        cl = r["classification"]
        rd = cl.get("recovery_debt") or {}
        lines.append(
            f"| `{r['scenario_id']}` | {cl['primary']} | {cl['crossed_in_credit']} | "
            f"{cl['blocked_at_onset']} | {cl['max_q_in_credit']} | "
            f"{r['preonset_notify_hours']} | "
            f"persist={rd.get('persistent_high_probability')} "
            f"debt={rd.get('recovery_debt_dominant')} |"
        )

    lines += [
        "",
        "### Pre-onset blocked deep dive",
        "",
    ]
    for r in doc["preonset_blocked_detail"]:
        lines.append(
            f"- `{r['scenario_id']}`: covering notify t={r['covering_notify_idx']} "
            f"({r['covering_notify_hour']:.3g} h), end={r['covering_end_idx']}; "
            f"context@notify: P_med={r['ctx_at_notify']['P_median_m']:.4g}, "
            f"Pd_d6_min={r['ctx_at_notify']['Pd_min_d6_m']}, "
            f"pump_on={r['ctx_at_notify']['pump1_on']}, "
            f"L_T1={r['ctx_at_notify']['L_T1_m']:.4g}; "
            f"similar_control_notifies_near_hour="
            f"{r['n_control_notifies_within_1h_of_covering']}"
        )

    lines += [
        "",
        "## Controls (synthetic_test only — not invented pairs)",
        "",
        f"- n_control={doc['control_test']['n_scenarios']}, "
        f"n_episodes={doc['control_test']['n_episodes']}, "
        f"ep/wk={doc['control_test']['episodes_per_week']:.4g}",
        f"- Denominator: {doc['construction']['control_burden_denominator']['disclosure']}",
        "",
        "Control notify hours:",
        "",
    ]
    for c in doc["control_test"]["per_control"]:
        lines.append(
            f"- `{c['scenario_id']}` ({c['kind']}): notify_hours={c['notify_hours']}"
        )

    lines += [
        "",
        "## Scenario construction audit",
        "",
        f"- Hydraulic warm-up: {doc['construction']['warmup_hours']} h; "
        f"feature warm-up: {doc['construction']['feature_warmup_hours']} h; "
        f"duration: {doc['construction']['duration_hours']} h",
        f"- Leak start sampling: {doc['construction']['leak_start_sampling']}",
        "",
        "Leak covariates by split:",
        "",
    ]
    for split, s in doc["construction"]["by_split_leaks"].items():
        lines.append(f"- **{split}**: `{json.dumps(s)}`")
    lines += ["", "Controls by split:", ""]
    for split, s in doc["construction"]["by_split_controls"].items():
        lines.append(f"- **{split}**: `{json.dumps(s)}`")
    lines += [
        "",
        doc["construction"]["label_phase_encoding"]["note"],
        "",
        f"Pre-onset notify index histogram (all test leaks): "
        f"`{doc['preonset_notify_histogram']}`",
        "",
        "## Onset-aligned physical signal (descriptive; GT windows only)",
        "",
        f"`{json.dumps(doc['signal_summary'], indent=2)}`",
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
        f"Votes: `{doc['decision']['votes']}`",
        "",
        "### Recommended next intervention (not implemented)",
        "",
        doc["decision"]["recommended_next_intervention"],
        "",
        "## Artifacts",
        "",
        "- Per-scenario timelines: `timelines/*.json`",
        "- Machine-readable summary: `summary.json`",
        "",
        "## Non-goals",
        "",
        "- No new fits, grid expansion, simulations, 2019, main merge, Tiger, UI, deploy",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "timelines").mkdir(exist_ok=True)

    frozen = json.loads((ABL / "arm_A_frozen_model.json").read_text())
    tau = float(frozen["selected"]["tau"])
    manifest = json.loads((SIM_DIR / "scenario_manifest.json").read_text())
    split_info = assign_splits(manifest)
    assignments = split_info["assignments"]

    leak_results = []
    timelines = []
    control_rows = []
    signal_rows = []

    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        sid = sc["spec"]["scenario_id"]
        if assignments.get(sid) != "synthetic_test":
            continue
        arr = np.load(SIM_DIR / sc["npz"])
        q = score_trajectory(arr["pressures"], arr["flows"], arr["levels"], frozen)
        episodes = episodes_from_scores(q, tau=tau, recover_steps=RECOVER_STEPS)
        spec = sc["spec"]
        kind = spec["kind"]

        if kind.startswith("control"):
            control_rows.append(
                {
                    "scenario_id": sid,
                    "kind": kind,
                    "n_episodes": len(episodes),
                    "notify_idxs": [int(e.notify_idx) for e in episodes],
                    "notify_hours": [e.notify_idx / STEPS_PER_HOUR for e in episodes],
                    "operating_realization": spec.get("operating_realization"),
                    "demand_scale": spec.get("demand_scale"),
                }
            )
            tl = build_timeline_summary(
                sid=sid,
                spec=spec,
                q=q,
                y=arr["labels_abrupt_positive"],
                pressures=arr["pressures"],
                flows=arr["flows"],
                levels=arr["levels"],
                tau=tau,
                episodes=episodes,
                kind=kind,
            )
            timelines.append(tl)
            (AUDIT / "timelines" / f"{sid}.json").write_text(
                json.dumps(_jsonable(tl), indent=2) + "\n"
            )
            continue

        if kind != "leak_abrupt":
            continue

        y = arr["labels_abrupt_positive"].astype(bool)
        onset = int(np.argmax(y))
        hi = onset + CREDIT_STEPS
        hit = any(onset <= e.notify_idx <= hi for e in episodes)
        row_hit = bool((np.isfinite(q) & (q >= tau) & y).any())
        preonset = [int(e.notify_idx) for e in episodes if e.notify_idx < onset]
        cl = classify_miss(
            onset=onset, q=q, tau=tau, episodes=episodes, hit=hit
        )
        sig = onset_aligned_signal(
            arr["pressures"], arr["flows"], arr["levels"], onset
        )
        signal_rows.append({"scenario_id": sid, "hit": hit, **sig})

        ctx_notify = None
        if cl.get("recovery_debt"):
            t_n = cl["recovery_debt"]["covering_notify_idx"]
            ctx_notify = physical_context(
                arr["pressures"], arr["flows"], arr["levels"], t_n
            )

        row = {
            "scenario_id": sid,
            "pipe": spec.get("pipe"),
            "pipe_group": spec.get("pipe_group"),
            "demand_scale": spec.get("demand_scale"),
            "leak_area_m2": spec.get("leak_area_m2"),
            "leak_start_hour": spec.get("leak_start_hour"),
            "leak_end_hour": spec.get("leak_end_hour"),
            "operating_realization": spec.get("operating_realization"),
            "onset_idx": onset,
            "onset_hour": onset / STEPS_PER_HOUR,
            "episode_6h_hit": hit,
            "row_credit_hit": row_hit,
            "preonset_notify_idxs": preonset,
            "preonset_notify_hours": [i / STEPS_PER_HOUR for i in preonset],
            "classification": cl,
            "signal": sig,
            "ctx_at_covering_notify": ctx_notify,
            "episodes": [
                {
                    "notify_idx": int(e.notify_idx),
                    "end_idx": int(e.end_idx),
                    "peak_score": float(e.peak_score),
                }
                for e in episodes
            ],
        }
        leak_results.append(row)

        tl = build_timeline_summary(
            sid=sid,
            spec=spec,
            q=q,
            y=y,
            pressures=arr["pressures"],
            flows=arr["flows"],
            levels=arr["levels"],
            tau=tau,
            episodes=episodes,
            kind=kind,
        )
        tl["classification"] = cl
        timelines.append(tl)
        (AUDIT / "timelines" / f"{sid}.json").write_text(
            json.dumps(_jsonable(tl), indent=2) + "\n"
        )

    # Pre-onset blocked detail + control similarity
    ctrl_notify_hours = [
        h for c in control_rows for h in c["notify_hours"]
    ]
    preonset_blocked_detail = []
    for r in leak_results:
        cl = r["classification"]
        if not (
            cl["primary"] in ("preonset_active_block", "preonset_active_no_crossing")
            or cl["causes"].get("preonset_active_block")
        ):
            if not (not r["episode_6h_hit"] and cl["blocked_at_onset"]):
                continue
        rd = cl.get("recovery_debt") or {}
        hour = rd.get("covering_notify_idx", 0) / STEPS_PER_HOUR
        n_sim = sum(1 for h in ctrl_notify_hours if abs(h - hour) <= 1.0)
        preonset_blocked_detail.append(
            {
                "scenario_id": r["scenario_id"],
                "covering_notify_idx": rd.get("covering_notify_idx"),
                "covering_notify_hour": hour,
                "covering_end_idx": rd.get("covering_end_idx"),
                "ctx_at_notify": r.get("ctx_at_covering_notify"),
                "recovery_debt": rd,
                "n_control_notifies_within_1h_of_covering": n_sim,
            }
        )

    # Histogram of preonset notify indices
    hist = {}
    for r in leak_results:
        for i in r["preonset_notify_idxs"]:
            # bin by 1h
            b = int(i // STEPS_PER_HOUR)
            hist[str(b)] = hist.get(str(b), 0) + 1

    n_leak = len(leak_results)
    n_hit = sum(1 for r in leak_results if r["episode_6h_hit"])
    n_miss = n_leak - n_hit
    n_row = sum(1 for r in leak_results if r["row_credit_hit"])
    n_row_miss_ep = sum(
        1 for r in leak_results if r["row_credit_hit"] and not r["episode_6h_hit"]
    )
    n_blocked_flag = sum(
        1 for r in leak_results if r["classification"]["blocked_at_onset"]
    )

    n_ctrl = len(control_rows)
    n_ctrl_eps = sum(c["n_episodes"] for c in control_rows)
    ctrl_weeks = n_ctrl * SCENARIO_WEEKS

    # Signal summary
    def mean_delta(rows, hit_val):
        diffs = []
        for r in rows:
            if r["hit"] != hit_val:
                continue
            pre = r["pre_6h"]
            post = r["post_6h_credit"]
            if not pre or not post:
                continue
            if np.isfinite(pre["Pd_d6_min_mean"]) and np.isfinite(post["Pd_d6_min_mean"]):
                diffs.append(post["Pd_d6_min_mean"] - pre["Pd_d6_min_mean"])
        return float(np.mean(diffs)) if diffs else None

    # Control reference: use mid-trajectory window as pseudo "onset" at mean leak start
    # Better: aggregate control random windows — use hour 20-26 as a clock-matched
    # reference near common leak starts without claiming pairing.
    ctrl_pd = []
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        if assignments.get(sc["spec"]["scenario_id"]) != "synthetic_test":
            continue
        if not sc["spec"]["kind"].startswith("control"):
            continue
        arr = np.load(SIM_DIR / sc["npz"])
        # clock window ~16–22 h (near notify cluster) and a later window
        for t0 in (16 * STEPS_PER_HOUR, 24 * STEPS_PER_HOUR):
            sig = onset_aligned_signal(
                arr["pressures"], arr["flows"], arr["levels"], t0
            )
            if sig["post_6h_credit"]:
                ctrl_pd.append(sig["post_6h_credit"]["Pd_d6_min_mean"])

    signal_summary = {
        "hit_post_minus_pre_pd_min_mean": mean_delta(signal_rows, True),
        "miss_post_minus_pre_pd_min_mean": mean_delta(signal_rows, False),
        "control_clock_windows_pd_d6_min_mean": (
            float(np.nanmean(ctrl_pd)) if ctrl_pd else None
        ),
        "note": (
            "Ground-truth onset defines leak pre/post windows for description only. "
            "Control windows are clock-based (16 h and 24 h), not paired scenarios."
        ),
    }

    construction = construction_audit(manifest, assignments)

    doc = {
        "generated_at": iso_now(),
        "experiment": "arm_a_synth_miss_audit",
        "frozen": {
            "C": frozen["selected"]["C"],
            "tau": tau,
            "gate_met": frozen.get("gate_met"),
            "selection_failure": frozen.get("selection_failure"),
            "source": "outputs/change_only_ablation/arm_A_frozen_model.json",
        },
        "cause_definitions": CAUSE_DEFS,
        "counts": {
            "n_leak": n_leak,
            "n_hit": n_hit,
            "n_miss": n_miss,
            "episode_6h_recall": n_hit / n_leak if n_leak else None,
            "row_credit_scenario_recall": n_row / n_leak if n_leak else None,
            "row_credit_hit_but_episode_miss": n_row_miss_ep,
            "n_blocked_flag": n_blocked_flag,
        },
        "leak_results": leak_results,
        "preonset_blocked_detail": preonset_blocked_detail,
        "preonset_notify_histogram": hist,
        "control_test": {
            "n_scenarios": n_ctrl,
            "n_episodes": n_ctrl_eps,
            "scenario_weeks_each": SCENARIO_WEEKS,
            "total_control_weeks": ctrl_weeks,
            "episodes_per_week": (n_ctrl_eps / ctrl_weeks) if ctrl_weeks else None,
            "per_control": control_rows,
        },
        "construction": {
            k: construction[k]
            for k in construction
            if k != "rows"
        },
        "construction_rows": construction["rows"],
        "signal_summary": signal_summary,
    }
    doc["decision"] = decide(doc)

    (AUDIT / "summary.json").write_text(json.dumps(_jsonable(doc), indent=2) + "\n")
    (AUDIT / "ARM_A_SYNTH_MISS_AUDIT.md").write_text(render(doc) + "\n")
    print(json.dumps(doc["decision"], indent=2))
    print(f"Wrote {AUDIT / 'ARM_A_SYNTH_MISS_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
