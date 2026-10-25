#!/usr/bin/env python3
"""Audit event↔notification assignment on frozen FMR3C DIAG outputs.

Does not change scores, thresholds, notifications, or original RESULTS /
EMPIRICAL reports. Views B/C are post-hoc diagnostic only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from audit_occupancy_recovery import (  # noqa: E402
    split_eligible_onsets,
    train_end_time,
)
from evaluate import (  # noqa: E402
    ABRUPT_POST_DAYS,
    DIAG,
    INCIPIENT_POST_DAYS,
    NULL_SHIFT_DAYS,
    STEPS_PER_DAY,
    abrupt_window,
    incipient_window,
    iso_now,
    match_episodes,
    onsets_in_period,
    period_indices,
    shift_episodes,
)
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402

import importlib.util  # noqa: E402


def _load_local(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"fmr3c_match_{name}", path)
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
run_all_targets_from_scores = _detector.run_all_targets_from_scores
build_period_signals = _signals.build_period_signals

OUT = ROOT / "outputs"
FROZEN = json.loads((OUT / "empirical_frozen.json").read_text())
TAU = float(FROZEN["selected"]["tau"])
L_Q = float(FROZEN["signal"]["l_q_hours"])
L_R = float(FROZEN["signal"]["l_r_hours"])
TRAIN_DAYS = 14
N_REFS = 3
# Dummy / ineligible costs for Hungarian (max-cardinality then min sum delay)
COST_INELIGIBLE = 1e9
COST_UNMATCHED_EVENT = 1e6  # prefer real edges over leaving event unmatched


def eligibility_window(L: Leakage) -> tuple[np.datetime64, np.datetime64]:
    if L.leak_type == "abrupt":
        return abrupt_window(L)
    return incipient_window(L)


def eligible_notifications(
    timestamps, episodes, L: Leakage, used: set[int] | None = None
) -> list[dict]:
    lo, hi = eligibility_window(L)
    out = []
    for j, ep in enumerate(episodes):
        if used is not None and j in used:
            continue
        t = timestamps[ep.notify_idx]
        if lo <= t <= hi:
            out.append(
                {
                    "episode_idx": j,
                    "stream_id": ep.stream_id,
                    "notify_time": str(t).replace("T", " "),
                    "notify_idx": int(ep.notify_idx),
                    "delay_hours": float((t - L.start) / np.timedelta64(1, "h")),
                    "end": str(timestamps[ep.end_idx]).replace("T", " "),
                    "already_assigned": False,  # plain bool for JSON
                }
            )
    return out


def match_row(L, ep, t, matched: bool) -> dict:
    if not matched:
        return {
            "pipe": L.pipe,
            "leak_type": L.leak_type,
            "onset": str(L.start).replace("T", " "),
            "matched": False,
            "notify_time": None,
            "delay_hours": None,
            "stream_id": None,
            "episode_idx": None,
        }
    return {
        "pipe": L.pipe,
        "leak_type": L.leak_type,
        "onset": str(L.start).replace("T", " "),
        "matched": True,
        "notify_time": str(t).replace("T", " "),
        "delay_hours": float((t - L.start) / np.timedelta64(1, "h")),
        "stream_id": ep.stream_id,
        "episode_idx": None,  # filled by caller
    }


def view_A_chronological(timestamps, episodes, onsets, leakages):
    """Original registered greedy: onsets by start; earliest unused eligible notify."""
    used: set[int] = set()
    rows: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo, hi = eligibility_window(L)
        best_j = None
        best_t = None
        for j, ep in enumerate(episodes):
            if j in used:
                continue
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                if best_j is None or t < best_t:
                    best_j = j
                    best_t = t
        if best_j is None:
            rows.append(match_row(L, None, None, False))
            continue
        used.add(best_j)
        ep = episodes[best_j]
        r = match_row(L, ep, best_t, True)
        r["episode_idx"] = best_j
        rows.append(r)
    # Cross-check against registered match_episodes
    ref_rows, ref_used = match_episodes(timestamps, episodes, onsets, leakages)
    assert len(used) == len(ref_used)
    for a, b in zip(rows, ref_rows):
        assert a["pipe"] == b["pipe"] and a["matched"] == b["matched"]
        if a["matched"]:
            assert a["notify_time"] == b["notify_time"]
    return {
        "name": "A_original_chronological_greedy",
        "label": "Original registered evaluation (unchanged)",
        "post_hoc": False,
        "description": (
            "Onsets chronological; each takes earliest unused notification in its "
            "type-specific eligibility window (abrupt 7d / incipient to peak∩14d)."
        ),
        "matches": rows,
        "used_episode_indices": sorted(used),
    }


def view_B_abrupt_only(timestamps, episodes, onsets, leakages):
    """Match against abrupt onsets only — abrupt sensitivity, not joint all-leak detection."""
    abrupt = [L for L in onsets if L.leak_type == "abrupt"]
    incip = [L for L in onsets if L.leak_type != "abrupt"]
    rows, used = match_episodes(timestamps, episodes, abrupt, leakages)
    for r in rows:
        # fill episode idx
        if r["matched"]:
            for j, ep in enumerate(episodes):
                if (
                    ep.stream_id == r["stream_id"]
                    and str(timestamps[ep.notify_idx]).replace("T", " ") == r["notify_time"]
                ):
                    r["episode_idx"] = j
                    break
    # report incipient as not evaluated under this view
    skipped = [
        {
            "pipe": L.pipe,
            "leak_type": L.leak_type,
            "onset": str(L.start).replace("T", " "),
            "matched": None,
            "note": "excluded_from_abrupt_only_view",
        }
        for L in incip
    ]
    return {
        "name": "B_abrupt_only",
        "label": "Post-hoc diagnostic: abrupt-only matching",
        "post_hoc": True,
        "description": (
            "Same chronological greedy rule, but only abrupt onsets compete for "
            "notifications. Measures abrupt-onset sensitivity, not joint detection "
            "of all leaks. Incipient events are excluded (not scored as misses)."
        ),
        "matches": rows,
        "excluded_incipient": skipped,
        "used_episode_indices": sorted(used),
    }


def view_C_max_cardinality(timestamps, episodes, onsets, leakages):
    """Max-cardinality bipartite matching; min sum delay among max matchings.

    Deterministic tie-break: Hungarian on cost matrix where
      cost[i,j] = delay_hours if notify in eligibility window for onset i
      else COST_INELIGIBLE
    Unmatched events use a dummy column with cost COST_UNMATCHED_EVENT.
    This yields maximum number of real assignments, then minimum total delay
    among such assignments (delays ≥ 0 so earlier notifies preferred).
    Secondary: scipy returns a deterministic optimum for a fixed cost matrix.
    """
    onsets_s = sorted(onsets, key=lambda x: (x.start, x.pipe))
    n_e = len(onsets_s)
    n_n = len(episodes)
    # cost: events × (episodes + dummy)
    cost = np.full((n_e, n_n + 1), COST_INELIGIBLE, dtype=np.float64)
    cost[:, n_n] = COST_UNMATCHED_EVENT
    eligible_edges = []
    for i, L in enumerate(onsets_s):
        lo, hi = eligibility_window(L)
        for j, ep in enumerate(episodes):
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                delay = float((t - L.start) / np.timedelta64(1, "h"))
                cost[i, j] = delay
                eligible_edges.append(
                    {
                        "pipe": L.pipe,
                        "episode_idx": j,
                        "stream_id": ep.stream_id,
                        "notify_time": str(t).replace("T", " "),
                        "delay_hours": delay,
                    }
                )
    ri, cj = linear_sum_assignment(cost)
    rows = []
    used = set()
    for i, j in zip(ri, cj):
        L = onsets_s[i]
        if j >= n_n or cost[i, j] >= COST_UNMATCHED_EVENT / 2:
            rows.append(match_row(L, None, None, False))
            continue
        ep = episodes[j]
        t = timestamps[ep.notify_idx]
        r = match_row(L, ep, t, True)
        r["episode_idx"] = int(j)
        rows.append(r)
        used.add(int(j))
    # Preserve onset order in report (chronological)
    rows = sorted(rows, key=lambda r: r["onset"])
    return {
        "name": "C_joint_max_cardinality",
        "label": "Post-hoc diagnostic: joint max-cardinality + min-sum-delay",
        "post_hoc": True,
        "description": (
            "Bipartite assignment over original eligibility windows. Maximize number "
            "of matched events; among maxima minimize sum of notification delays "
            "(Hungarian / linear_sum_assignment). One notification → at most one event. "
            "Does not prove causation from temporal proximity."
        ),
        "tie_break": (
            "Primary: maximum cardinality (dummy cost >> any delay). "
            "Secondary: minimize sum of delay_hours on assigned edges. "
            "Tertiary: deterministic solver output for the fixed cost matrix."
        ),
        "n_eligible_edges": len(eligible_edges),
        "matches": rows,
        "used_episode_indices": sorted(used),
    }


def metrics_for_view(view, episodes, weeks: float) -> dict:
    rows = view["matches"]
    abrupt = [m for m in rows if m.get("leak_type") == "abrupt"]
    incip = [m for m in rows if m.get("leak_type") == "incipient"]
    # abrupt-only view has no incipient in matches
    def recall(xs):
        if not xs:
            return float("nan")
        return sum(1 for m in xs if m.get("matched")) / len(xs)

    delays = [m["delay_hours"] for m in abrupt if m.get("matched")]
    n_matched_ep = len({m["episode_idx"] for m in rows if m.get("matched") and m.get("episode_idx") is not None})
    unmatched = len(episodes) - n_matched_ep
    return {
        "n_abrupt": len(abrupt),
        "n_incipient": len(incip),
        "abrupt_recall": recall(abrupt),
        "incipient_recall": recall(incip) if incip else None,
        "abrupt_delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "values": delays,
        },
        "n_episodes": len(episodes),
        "n_matched_episodes": n_matched_ep,
        "n_unmatched_episodes": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "assignments": rows,
    }


def null_for_view(
    view_builder,
    timestamps,
    episodes,
    onsets,
    leakages,
    analysis_start,
    analysis_end,
    *,
    abrupt_only: bool,
):
    """Shifted-null using the SAME assignment procedure on observed and shifted notifies."""
    pool = [L for L in onsets if L.leak_type == "abrupt"] if abrupt_only else onsets
    obs_view = view_builder(timestamps, episodes, pool if abrupt_only else onsets, leakages)
    if abrupt_only:
        # view_B expects full onsets list for excluded note; call properly
        obs_view = view_builder(timestamps, episodes, onsets, leakages)
    obs_rows = obs_view["matches"]
    obs_n = sum(1 for m in obs_rows if m.get("leak_type") == "abrupt" and m.get("matched"))
    counts = []
    for day in NULL_SHIFT_DAYS:
        sh = shift_episodes(episodes, day * STEPS_PER_DAY, analysis_start, analysis_end)
        if abrupt_only:
            v = view_builder(timestamps, sh, onsets, leakages)
        else:
            v = view_builder(timestamps, sh, onsets, leakages)
        rows = v["matches"]
        counts.append(
            sum(1 for m in rows if m.get("leak_type") == "abrupt" and m.get("matched"))
        )
    arr = np.asarray(counts, dtype=float)
    return {
        "observed_abrupt_matches": obs_n,
        "n_abrupt_onsets": sum(1 for L in onsets if L.leak_type == "abrupt"),
        "null_n_valid_shifts": len(NULL_SHIFT_DAYS),
        "null_match_median": float(np.median(arr)),
        "null_match_min": int(arr.min()),
        "null_match_max": int(arr.max()),
        "null_match_mean": float(arr.mean()),
        "fraction_shifts_ge_observed": float(np.mean(arr >= obs_n)),
        "assignment_procedure": obs_view["name"],
        "caveat": (
            "Same assignment view applied to circularly shifted notifications. "
            "Overlapping shifts; small n; diagnostic only."
        ),
    }


def conflict_detail(timestamps, episodes, leakages, onsets_eligible, view_a):
    """Focus on p810 vs p183 matching conflict."""
    by_pipe = {L.pipe: L for L in onsets_eligible}
    # also need p810 even if — it's in eligible
    out = {}
    assignment_a = {m["pipe"]: m for m in view_a["matches"]}
    used_a = set(view_a["used_episode_indices"])

    for pipe in ("p810", "p183"):
        L = by_pipe[pipe]
        lo, hi = eligibility_window(L)
        all_elig = eligible_notifications(timestamps, episodes, L, used=None)
        avail = eligible_notifications(timestamps, episodes, L, used=used_a)
        # Mark which were unavailable due to prior assignment under A
        assigned_to = {}
        for m in view_a["matches"]:
            if m.get("matched") and m.get("episode_idx") is not None:
                assigned_to[m["episode_idx"]] = m["pipe"]
        for e in all_elig:
            j = e["episode_idx"]
            if j in assigned_to and assigned_to[j] != pipe:
                e["already_assigned"] = True
                e["assigned_to"] = assigned_to[j]
            elif j in assigned_to and assigned_to[j] == pipe:
                e["already_assigned"] = False
                e["assigned_to"] = pipe
        out[pipe] = {
            "onset": str(L.start).replace("T", " "),
            "leak_type": L.leak_type,
            "end": str(L.end).replace("T", " "),
            "peak": str(L.peak).replace("T", " ") if L.peak is not None else None,
            "matching_interval": [
                str(lo).replace("T", " "),
                str(hi).replace("T", " "),
            ],
            "all_eligible_notifications": all_elig,
            "eligible_after_view_A_assignments": avail,
            "original_assignment_A": assignment_a.get(pipe),
            "note": (
                "Eligible list is membership in the official window only — "
                "temporal proximity does not prove which leak caused a notification."
            ),
        }

    # Independent support for p810: eligible notifies not needed by p183 / not only shared
    p810_elig = out["p810"]["all_eligible_notifications"]
    p183_idxs = {e["episode_idx"] for e in out["p183"]["all_eligible_notifications"]}
    exclusive = [e for e in p810_elig if e["episode_idx"] not in p183_idxs]
    shared = [e for e in p810_elig if e["episode_idx"] in p183_idxs]
    out["p810_support_analysis"] = {
        "n_eligible": len(p810_elig),
        "n_shared_with_p183_window": len(shared),
        "n_exclusive_to_p810_window": len(exclusive),
        "exclusive_notifications": exclusive,
        "shared_notifications": shared,
        "interpretation": (
            "If exclusive_to_p810_window is empty, p810's only eligible notifies "
            "also fall in p183's window (or there are none). Presence of exclusive "
            "notifies would be independent eligibility support for p810 — still not "
            "proof of causation."
        ),
    }
    return out


def classify_misses(timestamps, episodes, onsets_all_period, eligible, prefix, views, train_end):
    """Classify each onset under original view A and note B/C changes."""
    a = {m["pipe"]: m for m in views["A"]["matches"]}
    b = {m["pipe"]: m for m in views["B"]["matches"]}
    c = {m["pipe"]: m for m in views["C"]["matches"]}
    classes = []
    for L in sorted(onsets_all_period, key=lambda x: x.start):
        in_prefix = L.start < train_end
        in_primary = L in eligible or (
            L.start >= train_end and any(x.pipe == L.pipe and x.start == L.start for x in eligible)
        )
        # rebuild eligibility membership
        primary = L.start >= train_end
        elig_all = eligible_notifications(timestamps, episodes, L, used=None)
        active = [
            {
                "stream": ep.stream_id,
                "notify": str(timestamps[ep.notify_idx]).replace("T", " "),
            }
            for ep in episodes
            if timestamps[ep.notify_idx] < L.start <= timestamps[ep.end_idx]
        ]
        ma = a.get(L.pipe)
        # prefix events may be in prefix list not A primary
        if not primary:
            cls = "training_prefix_ineligibility"
            detail = "Onset before pairwise-training end; excluded from primary recall."
        elif L.pipe == "p369" and ma and not ma.get("matched"):
            cls = "genuine_signal_failure_weak_score"
            detail = (
                "Preserved transfer diagnosis: 6 h network max ≪ τ and overlaps "
                "ordinary same-month controls. Matching views cannot create a score."
            )
        elif not elig_all:
            if active:
                cls = "already_active_episode_suppression_or_no_new_notify"
                detail = (
                    "No notify in eligibility window; episode(s) already active at onset "
                    f"{active}. May reflect no crossing after onset or active-state policy."
                )
            else:
                cls = "no_eligible_notification"
                detail = "No notification timestamp falls in the official eligibility window."
        elif ma and not ma.get("matched") and elig_all:
            # had eligible but A didn't assign
            cls = "assignment_ambiguity_or_conflict"
            detail = (
                "Eligible notification(s) exist but chronological greedy assigned them "
                "elsewhere (or left unmatched under competition)."
            )
        elif ma and ma.get("matched"):
            cls = "matched_under_A"
            detail = "Matched under original view A."
        else:
            cls = "other"
            detail = ""

        classes.append(
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "primary_eligible": primary,
                "classification": cls,
                "detail": detail,
                "n_eligible_notifications": len(elig_all),
                "already_active_at_onset": active,
                "view_A": ma,
                "view_B": b.get(L.pipe),
                "view_C": c.get(L.pipe),
            }
        )
    return classes


def render(doc: str | dict) -> str:
    if isinstance(doc, str):
        return doc
    lines = [
        "# Matching-assignment audit — frozen FMR3C DIAG notifications",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Preserves original registered evaluation, `EMPIRICAL_CALIBRATION_RESULTS.md`, "
        "scores, thresholds, and notification lists. **No** detector re-tuning.",
        "",
        f"Frozen notifications: LQ={L_Q:g}h, LR={L_R:g}h, τ={TAU:.6g} (DIAG replay for audit).",
        "",
        "## 1. Matching conflict: p810 vs p183",
        "",
        "Temporal proximity does **not** prove which leak caused a notification.",
        "",
    ]
    conf = doc["conflict"]
    for pipe in ("p810", "p183"):
        c = conf[pipe]
        lines += [
            f"### {pipe}",
            "",
            f"- Type / onset / end / peak: **{c['leak_type']}** / {c['onset']} / "
            f"{c['end']} / {c['peak']}",
            f"- Matching interval: `{c['matching_interval'][0]}` → `{c['matching_interval'][1]}`",
            f"- Original assignment (view A): {c['original_assignment_A']}",
            "",
            "Eligible notifications (full window):",
            "",
        ]
        if not c["all_eligible_notifications"]:
            lines.append("- *(none)*")
        for e in c["all_eligible_notifications"]:
            tag = ""
            if e.get("already_assigned") and e.get("assigned_to") != pipe:
                tag = f" — **unavailable under A** (assigned to {e['assigned_to']})"
            elif e.get("assigned_to") == pipe:
                tag = " — **assigned to this event under A**"
            lines.append(
                f"- ep#{e['episode_idx']} {e['stream_id']} @ {e['notify_time']} "
                f"delay_h={e['delay_hours']:.4g}{tag}"
            )
        lines.append("")
    ps = conf["p810_support_analysis"]
    lines += [
        "### Independent eligibility support for p810?",
        "",
        f"- n eligible for p810: {ps['n_eligible']}",
        f"- shared with p183 window: {ps['n_shared_with_p183_window']}",
        f"- exclusive to p810 window: {ps['n_exclusive_to_p810_window']}",
        f"- exclusive list: {ps['exclusive_notifications']}",
        "",
        ps["interpretation"],
        "",
        "### Does joint assignment resolve the conflict?",
        "",
        doc["conflict_resolution_note"],
        "",
        "## 2. Evaluation views",
        "",
    ]
    for key in ("A", "B", "C"):
        v = doc["views"][key]
        m = doc["metrics"][key]
        lines += [
            f"### View {key}: {v['label']}",
            "",
            f"- Post-hoc diagnostic: **{v['post_hoc']}**",
            f"- {v['description']}",
        ]
        if key == "C":
            lines.append(f"- Tie-break: {v['tie_break']}")
        lines += [
            "",
            f"- Abrupt recall: **{m['abrupt_recall']}** (n={m['n_abrupt']})",
            f"- Incipient recall: {m['incipient_recall']}",
            f"- Abrupt delays: {m['abrupt_delay_hours']}",
            f"- Unmatched episodes: {m['n_unmatched_episodes']} "
            f"({m['unmatched_per_week']:.4g}/wk)",
            "",
            "Assignments:",
            "",
        ]
        for row in m["assignments"]:
            tag = "HIT" if row.get("matched") else "MISS"
            if row.get("matched") is None:
                tag = "N/A"
            lines.append(
                f"- {tag} {row.get('pipe')} ({row.get('leak_type')}) "
                f"notify={row.get('notify_time')} delay_h={row.get('delay_hours')} "
                f"sensor={row.get('stream_id')} ep={row.get('episode_idx')}"
            )
        if key == "B" and v.get("excluded_incipient"):
            lines.append("")
            lines.append("Excluded from scoring (incipient):")
            for row in v["excluded_incipient"]:
                lines.append(f"- {row['pipe']} ({row['leak_type']}) {row['note']}")
        n6 = doc["nulls"][key]
        lines += [
            "",
            f"Shifted null (same assignment procedure as view {key}):",
            "",
            f"- Observed abrupt matches: **{n6['observed_abrupt_matches']}** / "
            f"{n6['n_abrupt_onsets']}",
            f"- Null median (min–max): {n6['null_match_median']} "
            f"({n6['null_match_min']}–{n6['null_match_max']})",
            f"- Frac shifts ≥ obs: **{n6['fraction_shifts_ge_observed']:.2f}**",
            f"- {n6['caveat']}",
            "",
        ]

    lines += [
        "## 3. Miss classification (primary period onsets)",
        "",
        "p369 remains a **genuine unresolved signal failure** (weak score); matching "
        "corrections do not solve it.",
        "",
    ]
    for row in doc["miss_classes"]:
        lines.append(
            f"- **{row['pipe']}** ({row['leak_type']}): `{row['classification']}` — "
            f"{row['detail']} | A={row['view_A']} | B={row['view_B']} | C={row['view_C']}"
        )
    lines += [
        "",
        "## 4. Summary",
        "",
        doc["summary"],
        "",
        "## Non-goals",
        "",
        "- Original EMPIRICAL / RESULTS reports untouched as the registered headline",
        "- No threshold change, 2019, UI, Tiger, deployment, or main merge",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading + rebuilding frozen DIAG notifications (audit only)…", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2018_SCADA_Pressures.csv")
    leakages = load_leakages()
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
    episodes = run_all_targets_from_scores(scores, tau=TAU)
    # Verify episode count vs preserved empirical DIAG
    emp = json.loads((OUT / "empirical_calibration_summary.json").read_text())
    n_emp = emp["DIAG"]["n_episodes"]
    assert len(episodes) == n_emp, f"episode replay {len(episodes)} != preserved {n_emp}"

    train_end = train_end_time(pb.timestamps, g0, TRAIN_DAYS)
    period_onsets = onsets_in_period(leakages, DIAG)
    eligible, prefix = split_eligible_onsets(period_onsets, train_end)
    weeks = float((g1 - g0) * 5 / (60 * 24 * 7))

    print("Views A/B/C…", flush=True)
    # Primary metrics use post-training eligible onsets (registered)
    vA = view_A_chronological(pb.timestamps, episodes, eligible, leakages)
    vB = view_B_abrupt_only(pb.timestamps, episodes, eligible, leakages)
    vC = view_C_max_cardinality(pb.timestamps, episodes, eligible, leakages)

    metrics = {
        "A": metrics_for_view(vA, episodes, weeks),
        "B": metrics_for_view(vB, episodes, weeks),
        "C": metrics_for_view(vC, episodes, weeks),
    }

    print("Nulls…", flush=True)
    nulls = {
        "A": null_for_view(
            view_A_chronological,
            pb.timestamps,
            episodes,
            eligible,
            leakages,
            sig.analysis_offset,
            g1,
            abrupt_only=False,
        ),
        "B": null_for_view(
            view_B_abrupt_only,
            pb.timestamps,
            episodes,
            eligible,
            leakages,
            sig.analysis_offset,
            g1,
            abrupt_only=True,
        ),
        "C": null_for_view(
            view_C_max_cardinality,
            pb.timestamps,
            episodes,
            eligible,
            leakages,
            sig.analysis_offset,
            g1,
            abrupt_only=False,
        ),
    }

    conflict = conflict_detail(pb.timestamps, episodes, leakages, eligible, vA)
    # Resolution note
    a183 = next(m for m in vA["matches"] if m["pipe"] == "p183")
    c183 = next(m for m in vC["matches"] if m["pipe"] == "p183")
    a810 = next(m for m in vA["matches"] if m["pipe"] == "p810")
    c810 = next(m for m in vC["matches"] if m["pipe"] == "p810")
    b183 = next(m for m in vB["matches"] if m["pipe"] == "p183")
    if c183.get("matched") and not a183.get("matched"):
        resolution = (
            f"Joint max-cardinality (C) assigns a notify to p183 "
            f"({c183.get('notify_time')}, ep={c183.get('episode_idx')}) while A left "
            f"p183 unmatched. Under C, p810 matched={c810.get('matched')} "
            f"(notify={c810.get('notify_time')}). This **reassigns credit** among "
            "competing eligibility windows — it does not prove the notification was "
            "caused by p183, nor that the conflict is 'resolved' in a causal sense; "
            "it shows the chronological greedy rule (A) chose a different one-to-one "
            f"allocation (A: p810→{a810.get('notify_time')}, p183 unmatched)."
        )
    elif b183.get("matched") and not a183.get("matched"):
        resolution = (
            "Abrupt-only (B) matches p183 because incipient p810 no longer competes. "
            "That measures abrupt sensitivity with incipient ignored — not joint "
            "detection — and does not prove causation."
        )
    else:
        resolution = (
            "Joint assignment does not create a new p183 match beyond what A/B show; "
            "see per-view tables. Credit may still move between events without adding "
            "notifications."
        )

    miss_classes = classify_misses(
        pb.timestamps,
        episodes,
        period_onsets,
        eligible,
        prefix,
        {"A": vA, "B": vB, "C": vC},
        train_end,
    )

    summary = (
        f"View A (registered): abrupt_recall={metrics['A']['abrupt_recall']}, "
        f"p183 matched={a183.get('matched')}, p810 matched={a810.get('matched')}. "
        f"View B (abrupt-only, post-hoc): abrupt_recall={metrics['B']['abrupt_recall']}, "
        f"p183 matched={b183.get('matched')}. "
        f"View C (joint max-cardinality, post-hoc): abrupt_recall={metrics['C']['abrupt_recall']}, "
        f"p183 matched={c183.get('matched')}, p810 matched={c810.get('matched')}. "
        "p369 remains unmatched across views when no eligible notify exists — signal failure. "
        "B/C must not replace A as the registered headline."
    )

    doc = {
        "generated_at": iso_now(),
        "frozen": {"l_q_hours": L_Q, "l_r_hours": L_R, "tau": TAU},
        "n_episodes_replayed": len(episodes),
        "n_episodes_preserved_empirical": n_emp,
        "train_end": str(train_end).replace("T", " "),
        "conflict": conflict,
        "conflict_resolution_note": resolution,
        "views": {"A": vA, "B": vB, "C": vC},
        "metrics": metrics,
        "nulls": nulls,
        "miss_classes": miss_classes,
        "summary": summary,
        "holdout_honesty": (
            "DIAG notifications and labels were previously examined. Views B/C are "
            "post-hoc diagnostics, not a new blind evaluation."
        ),
    }
    # JSON-serializable views without huge episode objects
    for k in ("A", "B", "C"):
        doc["views"][k] = {
            kk: vv
            for kk, vv in doc["views"][k].items()
            if kk != "matches"  # matches duplicated in metrics
        }
        doc["views"][k]["matches"] = metrics[k]["assignments"]

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

    (OUT / "matching_assignment_audit.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "MATCHING_ASSIGNMENT_AUDIT.md").write_text(render(doc) + "\n")
    print(summary, flush=True)
    print(f"Wrote {OUT / 'MATCHING_ASSIGNMENT_AUDIT.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
