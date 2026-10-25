#!/usr/bin/env python3
"""Correct 2019 null diagnostics: each matching view × eligible event set × window.

Uses frozen notifications from year2019_inference.json. No detector re-run,
threshold change, or favorable relabeling of matches.
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

from evaluate import (  # noqa: E402
    NULL_SHIFT_DAYS,
    PeriodSpec,
    STEPS_PER_DAY,
    abrupt_window,
    incipient_window,
    iso_now,
    shift_episodes,
)
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402
from audit_occupancy_recovery import train_end_time  # noqa: E402

import importlib.util  # noqa: E402


def _load_local(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location("fmr3c_null_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_windows = _load_local("windows")
sys.modules["windows"] = _windows
_detector = _load_local("detector")
Episode = _detector.Episode
first_valid_t = _windows.first_valid_t
hours_to_steps = _windows.hours_to_steps

OUT = ROOT / "outputs"
YEAR2019 = PeriodSpec(
    "YEAR2019",
    np.datetime64("2019-01-01T00:00"),
    np.datetime64("2019-12-31T23:55"),
)
TRAIN_DAYS = 14
COST_INELIGIBLE = 1e9
COST_UNMATCHED_EVENT = 1e6
L_Q = 2.0
L_R = 48.0


def period_indices(timestamps, period):
    start_i = int(np.searchsorted(timestamps, period.start, side="left"))
    end_i = int(np.searchsorted(timestamps, period.end, side="right"))
    return start_i, end_i


def onsets_in_period(leakages, period):
    return [L for L in leakages if period.start <= L.start <= period.end]


def native_window(L: Leakage):
    if L.leak_type == "abrupt":
        return abrupt_window(L)
    return incipient_window(L)


def post_hours_window(L: Leakage, post_hours: float):
    lo = L.start
    hi = min(L.start + np.timedelta64(int(post_hours * 60), "m"), L.end)
    if L.leak_type != "abrupt":
        hi = min(hi, L.peak)
    return lo, hi


def match_row(L, ep, t, matched: bool, episode_idx=None):
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
        "episode_idx": episode_idx,
    }


def assign_A(timestamps, episodes, onsets, window_fn):
    """Chronological greedy; earliest unused notify in window_fn(L)."""
    used: set[int] = set()
    rows = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo, hi = window_fn(L)
        best_j = best_t = None
        for j, ep in enumerate(episodes):
            if j in used:
                continue
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi and (best_j is None or t < best_t):
                best_j, best_t = j, t
        if best_j is None:
            rows.append(match_row(L, None, None, False))
        else:
            used.add(best_j)
            rows.append(match_row(L, episodes[best_j], best_t, True, best_j))
    return rows, used


def assign_B(timestamps, episodes, onsets, window_fn):
    """Abrupt-only chronological greedy (incipient excluded from competition)."""
    abrupt = [L for L in onsets if L.leak_type == "abrupt"]
    return assign_A(timestamps, episodes, abrupt, window_fn)


def assign_C(timestamps, episodes, onsets, window_fn):
    """Max-cardinality then min-sum-delay (Hungarian)."""
    onsets_s = sorted(onsets, key=lambda x: (x.start, x.pipe))
    n_e, n_n = len(onsets_s), len(episodes)
    cost = np.full((n_e, n_n + 1), COST_INELIGIBLE, dtype=np.float64)
    cost[:, n_n] = COST_UNMATCHED_EVENT
    for i, L in enumerate(onsets_s):
        lo, hi = window_fn(L)
        for j, ep in enumerate(episodes):
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                cost[i, j] = float((t - L.start) / np.timedelta64(1, "h"))
    ri, cj = linear_sum_assignment(cost)
    rows, used = [], set()
    for i, j in zip(ri, cj):
        L = onsets_s[i]
        if j >= n_n or cost[i, j] >= COST_UNMATCHED_EVENT / 2:
            rows.append(match_row(L, None, None, False))
            continue
        ep = episodes[j]
        t = timestamps[ep.notify_idx]
        rows.append(match_row(L, ep, t, True, int(j)))
        used.add(int(j))
    rows = sorted(rows, key=lambda r: r["onset"])
    return rows, used


ASSIGNERS = {
    "A": ("A_original_chronological_greedy", assign_A, False),
    "B": ("B_abrupt_only", assign_B, True),
    "C": ("C_joint_max_cardinality", assign_C, False),
}


def abrupt_match_count(rows):
    return sum(1 for m in rows if m.get("leak_type") == "abrupt" and m.get("matched"))


def null_block(
    timestamps,
    episodes,
    onsets,
    *,
    view_key: str,
    window_name: str,
    window_fn,
    analysis_start: int,
    analysis_end: int,
):
    name, assigner, abrupt_only = ASSIGNERS[view_key]
    obs_rows, _ = assigner(timestamps, episodes, onsets, window_fn)
    n_abrupt = sum(1 for L in onsets if L.leak_type == "abrupt")
    # For B, onsets may be full list but assigner filters; count from full set abrupt
    if abrupt_only:
        n_abrupt = sum(1 for L in onsets if L.leak_type == "abrupt")
    obs_n = abrupt_match_count(obs_rows)
    counts = []
    for day in NULL_SHIFT_DAYS:
        sh = shift_episodes(episodes, day * STEPS_PER_DAY, analysis_start, analysis_end)
        rows, _ = assigner(timestamps, sh, onsets, window_fn)
        counts.append(abrupt_match_count(rows))
    arr = np.asarray(counts, dtype=float)
    return {
        "view": view_key,
        "assignment_procedure": name,
        "window": window_name,
        "n_abrupt_onsets": n_abrupt,
        "n_onsets_in_set": len(onsets),
        "n_incipient_in_set": sum(1 for L in onsets if L.leak_type == "incipient"),
        "observed_abrupt_matches": obs_n,
        "null_n_valid_shifts": len(NULL_SHIFT_DAYS),
        "null_match_median": float(np.median(arr)),
        "null_match_min": int(arr.min()),
        "null_match_max": int(arr.max()),
        "null_match_mean": float(arr.mean()),
        "fraction_shifts_ge_observed": float(np.mean(arr >= obs_n)),
        "observed_assignments_abrupt": [
            {
                "pipe": m["pipe"],
                "matched": m["matched"],
                "delay_hours": m["delay_hours"],
                "notify_time": m["notify_time"],
                "stream_id": m["stream_id"],
            }
            for m in obs_rows
            if m.get("leak_type") == "abrupt"
            or (abrupt_only and True and m.get("leak_type") == "abrupt")
        ],
        # For B, rows are abrupt-only already
        "observed_assignments_abrupt_clean": [
            {
                "pipe": m["pipe"],
                "matched": m["matched"],
                "delay_hours": m["delay_hours"],
                "notify_time": m["notify_time"],
                "stream_id": m["stream_id"],
            }
            for m in obs_rows
            if m.get("leak_type") == "abrupt"
        ],
        "caveat": (
            "Circular daily shifts of frozen notifications; overlapping and dependent. "
            "Same assignment procedure on observed and shifted notifies. "
            "Diagnostic only — not a detector change."
        ),
    }


def load_frozen_episodes(timestamps) -> tuple[list, dict]:
    inf = json.loads((OUT / "year2019_inference.json").read_text())
    episodes = []
    for row in inf["episodes"]:
        episodes.append(
            Episode(
                stream_id=row["stream_id"],
                target_idx=int(row["target_idx"]),
                notify_idx=int(row["notify_idx"]),
                end_idx=int(row["end_idx"]),
                change_estimate_idx=int(
                    np.searchsorted(
                        timestamps,
                        np.datetime64(row["change_estimate_time"].replace(" ", "T")),
                    )
                ),
                refs_used=list(row["refs_used"]),
                peak_score=float(row["peak_score"]),
                peak_cusum=float(row["peak_score"]),
            )
        )
    # Verify notify times match indices
    for row, ep in zip(inf["episodes"], episodes):
        assert str(timestamps[ep.notify_idx]).replace("T", " ") == row["notify_time"]
        assert str(timestamps[ep.end_idx]).replace("T", " ") == row["end_time"]
    return episodes, inf


def render(doc: dict) -> str:
    lines = [
        "# 2019 null correction — per matching view and eligible event set",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Preserves frozen FMR3C detector, τ, notifications, and "
        "`YEAR2019_EVALUATION.md` detector metrics. **No** threshold change, "
        "favorable relabeling, or re-inference.",
        "",
        "## Why this correction",
        "",
        "The original `YEAR2019_EVALUATION.md` §5 reported 0–2 h / 0–6 h nulls from a "
        "**single** shortened-window chronological matcher (`null_at_post_hours`), not "
        "from views A / B / C. View-native shift nulls were only shown for the "
        "**primary** eligible set. Those two choices mix procedures and hide "
        "eligible-set dependence.",
        "",
        "This report recomputes nulls on the **same frozen episodes**, crossing:",
        "",
        "- **Eligible sets:** `primary` (onset ≥ train_end), `post_fit` "
        "(onset ≥ earliest eligible notification)",
        "- **Views:** A (joint greedy), B (abrupt-only greedy), C (max-cardinality)",
        "- **Windows:** `native` (registered type windows), `0–2h`, `0–6h` "
        "(shortened post-onset; still using that view’s assignment rule)",
        "",
        f"- train_end: **{doc['train_end']}**",
        f"- earliest_eligible_notification: **{doc['earliest_eligible_notification']}**",
        f"- episodes_sha256 (frozen): `{doc['episodes_sha256']}`",
        f"- n_episodes: {doc['n_episodes']}",
        "",
        "## Eligible event sets",
        "",
    ]
    for name, info in doc["eligible_sets"].items():
        lines.append(
            f"- **{name}**: n={info['n']} "
            f"(abrupt={info['n_abrupt']}, incipient={info['n_incipient']}) — "
            f"{info['definition']}"
        )
        lines.append(
            "  - "
            + ", ".join(
                f"{p['pipe']}({p['leak_type']})" for p in info["members"]
            )
        )
    lines += [
        "",
        "## Null matrix (abrupt match counts)",
        "",
        "| Eligible set | View | Window | Obs abrupt hits | n abrupt | "
        "Null med (min–max) | Frac shifts ≥ obs |",
        "|--------------|------|--------|-----------------|----------|"
        "-------------------|-------------------|",
    ]
    for row in doc["null_matrix"]:
        lines.append(
            f"| {row['eligible_set']} | {row['view']} | {row['window']} | "
            f"**{row['observed_abrupt_matches']}** | {row['n_abrupt_onsets']} | "
            f"{row['null_match_median']} ({row['null_match_min']}–{row['null_match_max']}) | "
            f"**{row['fraction_shifts_ge_observed']:.2f}** |"
        )
    lines += [
        "",
        "### Reading rules",
        "",
        "- Compare each cell only to itself (same view, set, window).",
        "- Do **not** pick the most favorable cell as a headline replacement for "
        "registered view A / primary / native or abrupt-6h sensitivity.",
        "- View B excludes incipient from competition; its obs counts are not "
        "joint-detection claims.",
        "- Overlapping daily shifts are dependent; n abrupt is small.",
        "",
        "## Per-cell abrupt assignments (observed)",
        "",
    ]
    for cell in doc["null_matrix"]:
        lines.append(
            f"### {cell['eligible_set']} · view {cell['view']} · {cell['window']}"
        )
        lines.append("")
        abr = cell.get("observed_assignments_abrupt_clean") or []
        if not abr:
            lines.append("- *(no abrupt onsets in set)*")
        for m in abr:
            tag = "HIT" if m["matched"] else "MISS"
            lines.append(
                f"- {tag} {m['pipe']} delay_h={m['delay_hours']} "
                f"notify={m['notify_time']} sensor={m['stream_id']}"
            )
        lines.append("")
    lines += [
        "## Relation to original evaluation §5",
        "",
        doc["relation_to_original"],
        "",
        "## Non-goals",
        "",
        "- No detector / τ / notification changes",
        "- No favorable rematching of registered metrics",
        "- No production / Tiger / UI / main merge",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pb = load_pressures(DEFAULT_RAW / "2019_SCADA_Pressures.csv")
    leakages = load_leakages()
    g0, g1 = period_indices(pb.timestamps, YEAR2019)
    episodes, inf = load_frozen_episodes(pb.timestamps)
    # Recompute episode sha for integrity
    ep_bytes = json.dumps(inf["episodes"], sort_keys=True, separators=(",", ":")).encode()
    ep_sha = hashlib.sha256(ep_bytes).hexdigest()
    assert ep_sha == inf["episodes_sha256"], "frozen episode list hash mismatch"

    train_end = train_end_time(pb.timestamps, g0, TRAIN_DAYS)
    warm = first_valid_t(hours_to_steps(L_Q), hours_to_steps(L_R))
    earliest = pb.timestamps[inf["analysis_offset"] + warm]
    assert str(earliest).replace("T", " ") == inf["fitting"]["earliest_eligible_notification"]

    year_onsets = onsets_in_period(leakages, YEAR2019)
    primary = [L for L in year_onsets if L.start >= train_end]
    post_fit = [L for L in year_onsets if L.start >= earliest]

    def set_info(name, xs, definition):
        return {
            "definition": definition,
            "n": len(xs),
            "n_abrupt": sum(1 for L in xs if L.leak_type == "abrupt"),
            "n_incipient": sum(1 for L in xs if L.leak_type == "incipient"),
            "members": [
                {
                    "pipe": L.pipe,
                    "leak_type": L.leak_type,
                    "onset": str(L.start).replace("T", " "),
                }
                for L in sorted(xs, key=lambda x: x.start)
            ],
        }

    eligible_sets = {
        "primary": set_info(
            "primary",
            primary,
            "onset ≥ train_end (same as registered YEAR2019 primary)",
        ),
        "post_fit": set_info(
            "post_fit",
            post_fit,
            "onset ≥ earliest eligible notification (after FMR3C warm-up)",
        ),
    }

    windows = {
        "native": ("native type window (abrupt 7d / incipient to peak∩14d)", native_window),
        "0-2h": ("0–2 h post-onset (∩ end; incipient ∩ peak)", lambda L: post_hours_window(L, 2.0)),
        "0-6h": ("0–6 h post-onset (∩ end; incipient ∩ peak)", lambda L: post_hours_window(L, 6.0)),
    }

    analysis_start = int(inf["analysis_offset"])
    analysis_end = int(inf["analysis_end"])
    null_matrix = []
    for set_name, onset_list in (("primary", primary), ("post_fit", post_fit)):
        for view_key in ("A", "B", "C"):
            for win_key, (win_label, win_fn) in windows.items():
                print(
                    f"Null {set_name} view={view_key} window={win_key}…",
                    flush=True,
                )
                block = null_block(
                    pb.timestamps,
                    episodes,
                    onset_list,
                    view_key=view_key,
                    window_name=win_label,
                    window_fn=win_fn,
                    analysis_start=analysis_start,
                    analysis_end=analysis_end,
                )
                block["eligible_set"] = set_name
                block["window_key"] = win_key
                # drop redundant messy key
                block.pop("observed_assignments_abrupt", None)
                null_matrix.append(block)

    # Explain mismatch with original §5
    # Original used null_at_post_hours = chronological greedy on ALL onsets (joint)
    # with shortened window — closest to view A + 0-2h/0-6h on primary
    a_2 = next(
        r
        for r in null_matrix
        if r["eligible_set"] == "primary"
        and r["view"] == "A"
        and r["window_key"] == "0-2h"
    )
    a_6 = next(
        r
        for r in null_matrix
        if r["eligible_set"] == "primary"
        and r["view"] == "A"
        and r["window_key"] == "0-6h"
    )
    relation = (
        f"Original §5 used one shortened-window joint greedy (equivalent here to "
        f"**view A · primary · 0–2h/0–6h**): obs abrupt = {a_2['observed_abrupt_matches']} "
        f"(2h) / {a_6['observed_abrupt_matches']} (6h); frac≥obs = "
        f"{a_2['fraction_shifts_ge_observed']:.2f} / {a_6['fraction_shifts_ge_observed']:.2f}. "
        f"Those figures must not be read as view-B/C nulls or as post_fit nulls. "
        f"View-native primary nulls remain the shift diagnostics under registered "
        f"type windows (see matrix rows window=`native`)."
    )

    doc = {
        "generated_at": iso_now(),
        "preserves_detector": True,
        "train_end": str(train_end).replace("T", " "),
        "earliest_eligible_notification": str(earliest).replace("T", " "),
        "episodes_sha256": ep_sha,
        "n_episodes": len(episodes),
        "eligible_sets": eligible_sets,
        "null_matrix": null_matrix,
        "relation_to_original": relation,
        "correction_note": (
            "Reporting correction only. Registered YEAR2019 detector metrics unchanged."
        ),
    }

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
        return o

    (OUT / "year2019_null_correction.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "YEAR2019_NULL_CORRECTION.md").write_text(render(doc) + "\n")

    # Pointer in original evaluation report (additive; does not change metrics)
    eval_md = OUT / "YEAR2019_EVALUATION.md"
    text = eval_md.read_text()
    pointer = (
        "> **Null reporting correction:** §5 below used a single shortened-window "
        "matcher, not per-view nulls. See `YEAR2019_NULL_CORRECTION.md` for nulls "
        "separated by matching view (A/B/C), eligible set (primary / post_fit), and "
        "window (native / 0–2h / 0–6h). Detector outputs and registered metrics are "
        "unchanged.\n\n"
    )
    if "Null reporting correction" not in text:
        # insert after honesty paragraph / before ## 0
        marker = "## 0. Pre-inference freeze"
        if marker in text:
            text = text.replace(marker, pointer + marker, 1)
            eval_md.write_text(text)

    print(relation, flush=True)
    print(f"Wrote {OUT / 'YEAR2019_NULL_CORRECTION.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
