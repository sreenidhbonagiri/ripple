#!/usr/bin/env python3
"""Evaluate frozen FMR3C (LQ=2h, LR=48h, τ from empirical_frozen) on continuous 2019.

Protocol: YEAR2019_EVALUATION_PROTOCOL.md (written before inference).
Does not overwrite prior experiment reports. No τ retune / features / Tiger.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from audit_occupancy_recovery import (  # noqa: E402
    null_at_post_hours,
    occupancy_report,
    split_eligible_onsets,
    train_end_time,
)
from evaluate import (  # noqa: E402
    ABRUPT_POST_DAYS,
    INCIPIENT_POST_DAYS,
    NULL_SHIFT_DAYS,
    PeriodSpec,
    STEPS_PER_DAY,
    abrupt_window,
    incipient_window,
    iso_now,
    match_episodes,
    shift_episodes,
)
from io_data import DEFAULT_RAW, Leakage, load_leakages, load_pressures  # noqa: E402
from run_residual_recovery_variant import duplicate_unmatched, recall_block  # noqa: E402

import importlib.util  # noqa: E402


def _load_local(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"fmr3c_y2019_{name}", path)
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

RECOVER_STEPS = _detector.RECOVER_STEPS
build_score_bundle = _detector.build_score_bundle
run_all_targets_from_scores = _detector.run_all_targets_from_scores
build_period_signals = _signals.build_period_signals
first_valid_t = _windows.first_valid_t
hours_to_steps = _windows.hours_to_steps

OUT = ROOT / "outputs"
FROZEN_PATH = OUT / "empirical_frozen.json"
PROTOCOL_PATH = ROOT / "YEAR2019_EVALUATION_PROTOCOL.md"

YEAR2019 = PeriodSpec(
    "YEAR2019",
    np.datetime64("2019-01-01T00:00"),
    np.datetime64("2019-12-31T23:55"),
)
YEAR_START = np.datetime64("2019-01-01T00:00")
TRAIN_DAYS = 14
N_REFS = 3
COST_INELIGIBLE = 1e9
COST_UNMATCHED_EVENT = 1e6

CODE_FILES = [
    "DESIGN.md",
    "YEAR2019_EVALUATION_PROTOCOL.md",
    "detector.py",
    "scale.py",
    "windows.py",
    "signals.py",
    "run_year2019_evaluation.py",
    "run_empirical_calibration.py",
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def period_indices(timestamps: np.ndarray, period: PeriodSpec) -> tuple[int, int]:
    start_i = int(np.searchsorted(timestamps, period.start, side="left"))
    end_i = int(np.searchsorted(timestamps, period.end, side="right"))
    return start_i, end_i


def onsets_in_period(leakages: list[Leakage], period: PeriodSpec) -> list[Leakage]:
    return [L for L in leakages if period.start <= L.start <= period.end]


def abrupt_6h(matches: list[dict]) -> dict:
    abrupt = [m for m in matches if m["leak_type"] == "abrupt"]
    n = len(abrupt)
    hits = [
        m
        for m in abrupt
        if m["matched"]
        and m["delay_hours"] is not None
        and m["delay_hours"] <= 6.0 + 1e-12
    ]
    delays = [m["delay_hours"] for m in hits]
    return {
        "n_abrupt": n,
        "n_hit": len(hits),
        "recall": (len(hits) / n) if n else float("nan"),
        "delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
            "values": delays,
        },
        "per_event": [
            {
                "pipe": m["pipe"],
                "onset": m["onset"],
                "matched": m["matched"],
                "notify_time": m.get("notify_time"),
                "delay_hours": m.get("delay_hours"),
                "within_6h": bool(
                    m["matched"]
                    and m.get("delay_hours") is not None
                    and m["delay_hours"] <= 6.0 + 1e-12
                ),
                "stream_id": m.get("stream_id"),
            }
            for m in abrupt
        ],
    }


def latch_note(row: dict) -> dict:
    occ = row["occupancy"]
    union = occ["union_alarm_pct_of_analysis"]
    um = row["unmatched_per_week"]
    n_ep = row["n_episodes"]
    cens = occ["n_episodes_right_censored"]
    longest = occ["episode_length_hours"]["max"] or 0
    latched = bool(
        um <= 3.0
        and (union >= 90.0 or (n_ep > 0 and cens / n_ep >= 0.25 and longest >= 500))
    )
    return {
        "latched_suspect": latched,
        "union_pct": union,
        "sensor_pct": occ["summed_sensor_alarm_pct_of_eligible"],
        "note": (
            "Low unmatched with high union / long censored episodes can reflect "
            "latched alarms rather than cleared nuisance."
            if latched
            else "No strong latched-only signature under declared heuristics."
        ),
    }


def eligibility_window(L: Leakage) -> tuple[np.datetime64, np.datetime64]:
    if L.leak_type == "abrupt":
        return abrupt_window(L)
    return incipient_window(L)


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
        "episode_idx": None,
    }


def view_A(timestamps, episodes, onsets, leakages):
    used: set[int] = set()
    rows: list[dict] = []
    for L in sorted(onsets, key=lambda x: x.start):
        lo, hi = eligibility_window(L)
        best_j = best_t = None
        for j, ep in enumerate(episodes):
            if j in used:
                continue
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                if best_j is None or t < best_t:
                    best_j, best_t = j, t
        if best_j is None:
            rows.append(match_row(L, None, None, False))
            continue
        used.add(best_j)
        r = match_row(L, episodes[best_j], best_t, True)
        r["episode_idx"] = best_j
        rows.append(r)
    ref_rows, ref_used = match_episodes(timestamps, episodes, onsets, leakages)
    assert len(used) == len(ref_used)
    for a, b in zip(rows, ref_rows):
        assert a["pipe"] == b["pipe"] and a["matched"] == b["matched"]
        if a["matched"]:
            assert a["notify_time"] == b["notify_time"]
    return {
        "name": "A_original_chronological_greedy",
        "label": "Registered joint chronological greedy",
        "post_hoc": False,
        "registered": True,
        "description": (
            "Onsets chronological; earliest unused notify in type window "
            f"(abrupt {ABRUPT_POST_DAYS:g}d / incipient to peak∩{INCIPIENT_POST_DAYS:g}d)."
        ),
        "matches": rows,
        "used_episode_indices": sorted(used),
    }


def view_B(timestamps, episodes, onsets, leakages):
    abrupt = [L for L in onsets if L.leak_type == "abrupt"]
    incip = [L for L in onsets if L.leak_type != "abrupt"]
    rows, used = match_episodes(timestamps, episodes, abrupt, leakages)
    for r in rows:
        if r["matched"]:
            for j, ep in enumerate(episodes):
                if (
                    ep.stream_id == r["stream_id"]
                    and str(timestamps[ep.notify_idx]).replace("T", " ") == r["notify_time"]
                ):
                    r["episode_idx"] = j
                    break
    return {
        "name": "B_abrupt_only",
        "label": "Secondary: abrupt-only matching",
        "post_hoc": True,
        "registered": False,
        "description": (
            "Same greedy rule on abrupt onsets only. Incipient excluded from scoring."
        ),
        "matches": rows,
        "excluded_incipient": [
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "matched": None,
                "note": "excluded_from_abrupt_only_view",
            }
            for L in incip
        ],
        "used_episode_indices": sorted(used),
    }


def view_C(timestamps, episodes, onsets, leakages):
    onsets_s = sorted(onsets, key=lambda x: (x.start, x.pipe))
    n_e, n_n = len(onsets_s), len(episodes)
    cost = np.full((n_e, n_n + 1), COST_INELIGIBLE, dtype=np.float64)
    cost[:, n_n] = COST_UNMATCHED_EVENT
    for i, L in enumerate(onsets_s):
        lo, hi = eligibility_window(L)
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
        r = match_row(L, ep, t, True)
        r["episode_idx"] = int(j)
        rows.append(r)
        used.add(int(j))
    rows = sorted(rows, key=lambda r: r["onset"])
    return {
        "name": "C_joint_max_cardinality",
        "label": "Secondary: joint max-cardinality + min-sum-delay",
        "post_hoc": True,
        "registered": False,
        "description": (
            "Hungarian: max matched events, then min sum delay. One notify → one event."
        ),
        "tie_break": (
            "Primary max cardinality; secondary min sum delay_hours; "
            "tertiary deterministic solver."
        ),
        "matches": rows,
        "used_episode_indices": sorted(used),
    }


def metrics_for_view(view, episodes, weeks: float, occupancy: dict, dup: int) -> dict:
    rows = view["matches"]
    abrupt = [m for m in rows if m.get("leak_type") == "abrupt"]
    incip = [m for m in rows if m.get("leak_type") == "incipient"]

    def recall(xs):
        if not xs:
            return float("nan")
        return sum(1 for m in xs if m.get("matched")) / len(xs)

    delays = [m["delay_hours"] for m in abrupt if m.get("matched")]
    n_matched_ep = len(
        {
            m["episode_idx"]
            for m in rows
            if m.get("matched") and m.get("episode_idx") is not None
        }
    )
    unmatched = len(episodes) - n_matched_ep
    a6 = abrupt_6h(rows)
    return {
        "n_abrupt": len(abrupt),
        "n_incipient": len(incip),
        "abrupt_recall": recall(abrupt),
        "incipient_recall": recall(incip) if incip else None,
        "abrupt_6h": a6,
        "abrupt_delay_hours": {
            "n": len(delays),
            "median": float(np.median(delays)) if delays else None,
            "max": float(np.max(delays)) if delays else None,
            "values": delays,
        },
        "n_episodes": len(episodes),
        "n_matched_episodes": n_matched_ep,
        "n_unmatched_episodes": unmatched,
        "unmatched_per_week": unmatched / weeks if weeks else float("nan"),
        "duplicate_unmatched_within_24h": dup,
        "occupancy": occupancy,
        "assignments": rows,
        "misses": [m for m in rows if m.get("matched") is False],
    }


def null_view_abrupt_counts(
    view_builder, timestamps, episodes, onsets, leakages, analysis_start, analysis_end
):
    obs = view_builder(timestamps, episodes, onsets, leakages)
    obs_n = sum(
        1 for m in obs["matches"] if m.get("leak_type") == "abrupt" and m.get("matched")
    )
    counts = []
    for day in NULL_SHIFT_DAYS:
        sh = shift_episodes(episodes, day * STEPS_PER_DAY, analysis_start, analysis_end)
        v = view_builder(timestamps, sh, onsets, leakages)
        counts.append(
            sum(
                1
                for m in v["matches"]
                if m.get("leak_type") == "abrupt" and m.get("matched")
            )
        )
    arr = np.asarray(counts, dtype=float)
    return {
        "observed_abrupt_matches": obs_n,
        "n_abrupt_onsets": sum(1 for L in onsets if L.leak_type == "abrupt"),
        "null_n_valid_shifts": len(NULL_SHIFT_DAYS),
        "null_match_median": float(np.median(arr)),
        "null_match_min": int(arr.min()) if arr.size else None,
        "null_match_max": int(arr.max()) if arr.size else None,
        "null_match_mean": float(arr.mean()) if arr.size else None,
        "fraction_shifts_ge_observed": float(np.mean(arr >= obs_n)) if arr.size else None,
        "assignment_procedure": obs["name"],
        "caveat": (
            "Same assignment view on circularly shifted notifications. "
            "Overlapping shifts; small n; diagnostic only."
        ),
    }


def credit_conflicts(timestamps, episodes, onsets):
    """Notifications that fall in ≥2 onset eligibility windows."""
    by_ep: dict[int, list[dict]] = {}
    for L in onsets:
        lo, hi = eligibility_window(L)
        for j, ep in enumerate(episodes):
            t = timestamps[ep.notify_idx]
            if lo <= t <= hi:
                by_ep.setdefault(j, []).append(
                    {
                        "pipe": L.pipe,
                        "leak_type": L.leak_type,
                        "onset": str(L.start).replace("T", " "),
                        "delay_hours": float((t - L.start) / np.timedelta64(1, "h")),
                    }
                )
    conflicts = []
    for j, claimants in sorted(by_ep.items()):
        if len(claimants) < 2:
            continue
        ep = episodes[j]
        conflicts.append(
            {
                "episode_idx": j,
                "stream_id": ep.stream_id,
                "notify_time": str(timestamps[ep.notify_idx]).replace("T", " "),
                "n_claimants": len(claimants),
                "claimants": claimants,
                "note": (
                    "One notification cannot credit multiple events under any view; "
                    "temporal co-eligibility ≠ causation."
                ),
            }
        )
    return conflicts


def episodes_to_json(timestamps, episodes) -> list[dict]:
    return [
        {
            "episode_idx": i,
            "stream_id": ep.stream_id,
            "target_idx": int(ep.target_idx),
            "notify_time": str(timestamps[ep.notify_idx]).replace("T", " "),
            "notify_idx": int(ep.notify_idx),
            "end_time": str(timestamps[ep.end_idx]).replace("T", " "),
            "end_idx": int(ep.end_idx),
            "change_estimate_time": str(timestamps[ep.change_estimate_idx]).replace(
                "T", " "
            ),
            "refs_used": list(ep.refs_used),
            "peak_score": float(ep.peak_score),
            "duration_hours": float((ep.end_idx - ep.notify_idx) * 5 / 60.0),
        }
        for i, ep in enumerate(episodes)
    ]


def classify_strata(
    leakages: list[Leakage],
    *,
    train_end: np.datetime64,
    earliest_notify: np.datetime64,
    year: PeriodSpec,
) -> dict:
    year_onsets = onsets_in_period(leakages, year)
    carryover = [
        L
        for L in leakages
        if L.start < YEAR_START and L.end >= YEAR_START
    ]
    primary, prefix = split_eligible_onsets(year_onsets, train_end)
    warm = [L for L in primary if L.start < earliest_notify]
    post = [L for L in primary if L.start >= earliest_notify]
    post_abr = [L for L in post if L.leak_type == "abrupt"]
    post_inc = [L for L in post if L.leak_type == "incipient"]
    p523 = [L for L in leakages if L.pipe == "p523"]

    def brief(xs: list[Leakage]) -> list[dict]:
        return [
            {
                "pipe": L.pipe,
                "leak_type": L.leak_type,
                "onset": str(L.start).replace("T", " "),
                "end": str(L.end).replace("T", " "),
                "peak": str(L.peak).replace("T", " "),
            }
            for L in sorted(xs, key=lambda x: x.start)
        ]

    return {
        "carryover": brief(carryover),
        "training_prefix_onsets": brief(prefix),
        "warm_up_onsets": brief(warm),
        "post_fit_abrupt": brief(post_abr),
        "post_fit_incipient": brief(post_inc),
        "primary_eligible_all": brief(primary),
        "p523": brief(p523),
        "counts": {
            "carryover": len(carryover),
            "training_prefix_onsets": len(prefix),
            "warm_up_onsets": len(warm),
            "post_fit_abrupt": len(post_abr),
            "post_fit_incipient": len(post_inc),
            "primary_eligible": len(primary),
            "year_onsets": len(year_onsets),
        },
    }


def hash_scores(score_bundle: dict) -> str:
    h = hashlib.sha256()
    for sid in sorted(score_bundle["per_target"]):
        s = np.ascontiguousarray(score_bundle["per_target"][sid]["s"], dtype=np.float64)
        h.update(sid.encode())
        h.update(s.tobytes())
    return h.hexdigest()


def freeze_record(tau: float, l_q: float, l_r: float) -> dict:
    code_hashes = {name: file_sha256(ROOT / name) for name in CODE_FILES}
    input_hashes = {
        "2019_SCADA_Pressures.csv": file_sha256(
            DEFAULT_RAW / "2019_SCADA_Pressures.csv"
        ),
        "2019_SCADA_Flows.csv": file_sha256(DEFAULT_RAW / "2019_SCADA_Flows.csv"),
        "2019_SCADA_Levels.csv": file_sha256(DEFAULT_RAW / "2019_SCADA_Levels.csv"),
        "leakages_2018_2019.json": file_sha256(CUSUM / "leakages_2018_2019.json"),
        "empirical_frozen.json": file_sha256(FROZEN_PATH),
        "YEAR2019_EVALUATION_PROTOCOL.md": file_sha256(PROTOCOL_PATH),
    }
    # Code tree hash of FMR3C package py + protocol + frozen config
    pkg = hashlib.sha256()
    for name in sorted(code_hashes):
        pkg.update(name.encode())
        pkg.update(code_hashes[name].encode())
    pkg.update(input_hashes["empirical_frozen.json"].encode())
    return {
        "frozen_at": iso_now(),
        "protocol": "YEAR2019_EVALUATION_PROTOCOL.md",
        "git_commit_at_freeze": _git_head(),
        "method": {
            "l_q_hours": l_q,
            "l_r_hours": l_r,
            "tau": tau,
            "tau_source": "outputs/empirical_frozen.json selected.tau",
            "train_days": TRAIN_DAYS,
            "n_refs": N_REFS,
            "recover_steps": RECOVER_STEPS,
            "period": {
                "name": YEAR2019.name,
                "start": str(YEAR2019.start).replace("T", " "),
                "end": str(YEAR2019.end).replace("T", " "),
            },
        },
        "code_file_sha256": code_hashes,
        "package_config_sha256": pkg.hexdigest(),
        "input_sha256": input_hashes,
        "note": (
            "Recorded before 2019 score inference. τ not recomputed from 2019. "
            "Fit uses first 14 days of 2019 only."
        ),
    }


def _git_head() -> str:
    head = ROOT.parents[1] / ".git" / "HEAD"
    try:
        import subprocess

        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(ROOT.parents[1]), text=True
            ).strip()
        )
    except Exception:
        return str(head)


def render(doc: dict) -> str:
    fr = doc["freeze"]
    inf = doc["inference"]
    ev = doc["evaluation"]
    lines = [
        "# FMR3C frozen detector — 2019 full-year evaluation",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Preserves production and all prior FMR3C / CUSUM research reports. "
        "**No** feature addition, τ retune, Tiger, UI, or deployment.",
        "",
        "Honesty: prior 2019 examination is acknowledged — this is **not** an "
        "untouched holdout. Method and τ were frozen from 2018 DEV empirical "
        "calibration (`empirical_frozen.json`).",
        "",
        "## 0. Pre-inference freeze",
        "",
        f"- Protocol: `{fr['protocol']}`",
        f"- Git at freeze: `{fr['git_commit_at_freeze']}`",
        f"- Package+config sha256: `{fr['package_config_sha256']}`",
        f"- τ (exact loaded): **{fr['method']['tau']}** "
        f"(LQ={fr['method']['l_q_hours']:g}h, LR={fr['method']['l_r_hours']:g}h)",
        "",
        "### Input hashes",
        "",
    ]
    for k, v in fr["input_sha256"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "### Code file hashes",
        "",
    ]
    for k, v in fr["code_file_sha256"].items():
        lines.append(f"- `{k}`: `{v}`")

    fit = inf["fitting"]
    lines += [
        "",
        "## 1. Fitting prefix (2019)",
        "",
        f"- Fit slice: **{fit['train_start']}** → **{fit['train_last_sample']}** "
        f"(exclusive end index at {fit['train_end']})",
        f"- Fitting completion (`train_end`): **{fit['train_end']}**",
        f"- Warm-up steps (n_Q+n_R-1): **{fit['warm_up_steps']}** "
        f"({fit['warm_up_hours']:.4g} h)",
        f"- Earliest eligible notification: **{fit['earliest_eligible_notification']}**",
        f"- Eligible sensors: **{inf['n_eligible_sensors']}** / {inf['n_sensors']}",
        f"- Analysis span steps: {inf['analysis_steps']}",
        f"- z sha256[:16]: `{inf['z_sha256_16']}`",
        f"- scores sha256: `{inf['scores_sha256']}`",
        f"- notifications/episodes sha256: `{inf['episodes_sha256']}`",
        f"- n_episodes (pre-GT): **{inf['n_episodes']}**",
        f"- Inference runtime_s: {inf['runtime_seconds']:.2f}",
        "",
        "Scores and notifications were hashed **before** loading ground truth "
        "into the evaluation stage.",
        "",
        "## 2. Event strata",
        "",
    ]
    st = ev["strata"]
    lines.append(f"Counts: `{st['counts']}`")
    lines += ["", "### Carryover (open in 2019; onset before 2019)", ""]
    for row in st["carryover"]:
        lines.append(
            f"- {row['pipe']} ({row['leak_type']}) onset={row['onset']} end={row['end']}"
        )
    lines += ["", "### Training / warm-up onsets", ""]
    if not st["training_prefix_onsets"] and not st["warm_up_onsets"]:
        lines.append("- *(none)*")
    for row in st["training_prefix_onsets"]:
        lines.append(f"- PREFIX {row['pipe']} ({row['leak_type']}) {row['onset']}")
    for row in st["warm_up_onsets"]:
        lines.append(f"- WARM-UP {row['pipe']} ({row['leak_type']}) {row['onset']}")
    lines += ["", "### Post-fit abrupt", ""]
    for row in st["post_fit_abrupt"]:
        lines.append(f"- {row['pipe']} onset={row['onset']}")
    lines += ["", "### Post-fit incipient", ""]
    for row in st["post_fit_incipient"]:
        lines.append(f"- {row['pipe']} onset={row['onset']} peak={row['peak']}")
    lines += ["", "### Development example p523", ""]
    for row in st["p523"]:
        lines.append(
            f"- {row['pipe']} ({row['leak_type']}) onset={row['onset']} end={row['end']}"
        )
        p523_detail = ev.get("p523_detail")
        if p523_detail:
            lines.append(f"  - stratum: `{p523_detail['stratum']}`")
            for vk in ("A", "B", "C"):
                m = p523_detail["views"].get(vk)
                if m is None:
                    lines.append(f"  - view {vk}: *(not in onset set)*")
                else:
                    tag = "HIT" if m.get("matched") else "MISS"
                    lines.append(
                        f"  - view {vk}: {tag} notify={m.get('notify_time')} "
                        f"delay_h={m.get('delay_hours')} sensor={m.get('stream_id')}"
                    )

    lines += [
        "",
        "## 3. Matching views (primary eligible onsets)",
        "",
        "Registered headline is **view A**. Views B/C are secondary. "
        "One notification never double-credits two events.",
        "",
    ]
    for key in ("A", "B", "C"):
        v = ev["views"][key]
        m = ev["metrics"][key]
        lines += [
            f"### View {key}: {v['label']}",
            "",
            f"- Registered: **{v.get('registered', False)}**; post-hoc: {v['post_hoc']}",
            f"- {v['description']}",
        ]
        if key == "C":
            lines.append(f"- Tie-break: {v['tie_break']}")
        lines += [
            "",
            f"- Abrupt recall (type window): **{m['abrupt_recall']}** (n={m['n_abrupt']})",
            f"- Abrupt 6h recall: **{m['abrupt_6h']['recall']}** "
            f"({m['abrupt_6h']['n_hit']}/{m['abrupt_6h']['n_abrupt']})",
            f"- Incipient recall: {m['incipient_recall']}",
            f"- Abrupt delays (matched, full window): {m['abrupt_delay_hours']}",
            f"- Unmatched episodes: {m['n_unmatched_episodes']} "
            f"(**{m['unmatched_per_week']:.4g}**/wk); "
            f"dup24h: {m['duplicate_unmatched_within_24h']}",
            f"- Union%: {m['occupancy']['union_alarm_pct_of_analysis']:.4g}; "
            f"sensor%: {m['occupancy']['summed_sensor_alarm_pct_of_eligible']:.4g}",
            f"- Episode length h median/max: "
            f"{m['occupancy']['episode_length_hours']['median']}/"
            f"{m['occupancy']['episode_length_hours']['max']}; "
            f"right-censored: {m['occupancy']['n_episodes_right_censored']}",
            "",
            "Per-event assignments:",
            "",
        ]
        for row in m["assignments"]:
            tag = "HIT" if row.get("matched") else "MISS"
            if row.get("matched") is None:
                tag = "N/A"
            lines.append(
                f"- {tag} {row.get('pipe')} ({row.get('leak_type')}) "
                f"onset={row.get('onset')} notify={row.get('notify_time')} "
                f"delay_h={row.get('delay_hours')} sensor={row.get('stream_id')} "
                f"ep={row.get('episode_idx')}"
            )
        if key == "B" and v.get("excluded_incipient"):
            lines.append("")
            lines.append("Excluded incipient:")
            for row in v["excluded_incipient"]:
                lines.append(f"- {row['pipe']} ({row['leak_type']}) {row['onset']}")
        lines += [
            "",
            "Abrupt 6h detail:",
            "",
        ]
        for row in m["abrupt_6h"]["per_event"]:
            tag = "HIT6" if row["within_6h"] else ("HIT>6" if row["matched"] else "MISS")
            lines.append(
                f"- {tag} {row['pipe']} delay_h={row['delay_hours']} "
                f"notify={row['notify_time']} sensor={row.get('stream_id')}"
            )
        nshift = ev["nulls_by_view"][key]
        lines += [
            "",
            f"Shifted null (same assignment as view {key}; abrupt match counts):",
            "",
            f"- Observed: **{nshift['observed_abrupt_matches']}** / "
            f"{nshift['n_abrupt_onsets']}",
            f"- Null median (min–max): {nshift['null_match_median']} "
            f"({nshift['null_match_min']}–{nshift['null_match_max']})",
            f"- Frac shifts ≥ obs: **{nshift['fraction_shifts_ge_observed']:.2f}**",
            f"- {nshift['caveat']}",
            "",
        ]

    lines += [
        "## 4. Credit conflicts",
        "",
        "Notifications co-eligible for ≥2 primary onsets (views still assign once):",
        "",
    ]
    if not ev["credit_conflicts"]:
        lines.append("- *(none)*")
    for c in ev["credit_conflicts"]:
        claimants = ", ".join(
            f"{x['pipe']}({x['leak_type']},d={x['delay_hours']:.3g}h)" for x in c["claimants"]
        )
        lines.append(
            f"- ep#{c['episode_idx']} {c['stream_id']} @ {c['notify_time']}: {claimants}"
        )

    lines += [
        "",
        "## 5. Notification-time nulls (0–2 h / 0–6 h, registered windows shortened)",
        "",
    ]
    for label, key in (("0–2 h", "null_2h"), ("0–6 h", "null_6h")):
        n = ev[key]
        lines += [
            f"### {label}",
            "",
            f"- Observed abrupt matches: **{n['observed_abrupt_matches']}** / "
            f"{n['n_abrupt_onsets']}",
            f"- Null median (min–max): {n['null_match_median']} "
            f"({n['null_match_min']}–{n['null_match_max']})",
            f"- Frac shifts ≥ obs: **{n['fraction_shifts_ge_observed']:.2f}**",
            "",
            n["caveat"],
            "",
        ]

    lines += [
        "## 6. Post-fit stratum under registered view A",
        "",
        f"- Post-fit abrupt 6h: **{ev['post_fit_under_A']['abrupt_6h']['recall']}** "
        f"({ev['post_fit_under_A']['abrupt_6h']['n_hit']}/"
        f"{ev['post_fit_under_A']['abrupt_6h']['n_abrupt']})",
        f"- Post-fit abrupt (full window): "
        f"**{ev['post_fit_under_A']['abrupt_recall']}**",
        f"- Post-fit incipient: **{ev['post_fit_under_A']['incipient_recall']}**",
        "",
        "Post-fit abrupt detail:",
        "",
    ]
    for row in ev["post_fit_under_A"]["abrupt_6h"]["per_event"]:
        tag = "HIT6" if row["within_6h"] else ("HIT>6" if row["matched"] else "MISS")
        lines.append(
            f"- {tag} {row['pipe']} delay_h={row['delay_hours']} notify={row['notify_time']}"
        )
    lines += ["", "Warm-up onset results (view A primary set includes them):", ""]
    for row in ev["warm_up_under_A"]:
        tag = "HIT" if row.get("matched") else "MISS"
        lines.append(
            f"- {tag} {row.get('pipe')} delay_h={row.get('delay_hours')} "
            f"notify={row.get('notify_time')}"
        )

    lines += [
        "",
        "## 7. Candid assessment",
        "",
        doc["assessment"],
        "",
        "## Non-goals / stop",
        "",
        "- No threshold adjustment or selective rerun",
        "- No feature addition (including p369-targeted)",
        "- No main merge, UI, Tiger, or deployment",
        "- Prior registered 2018 reports untouched",
        "",
    ]
    return "\n".join(lines)


def assess(ev: dict, inf: dict) -> str:
    mA = ev["metrics"]["A"]
    mB = ev["metrics"]["B"]
    a6 = mA["abrupt_6h"]["recall"]
    a6b = mB["abrupt_6h"]["recall"]
    um = mA["unmatched_per_week"]
    union = mA["occupancy"]["union_alarm_pct_of_analysis"]
    latched = ev["latch"]["latched_suspect"]
    null6 = ev["null_6h"]
    post = ev["post_fit_under_A"]["abrupt_6h"]

    parts = [
        f"Registered view A on primary eligible 2019 onsets: abrupt 6h recall "
        f"**{a6:.2f}** ({mA['abrupt_6h']['n_hit']}/{mA['abrupt_6h']['n_abrupt']}), "
        f"abrupt full-window **{mA['abrupt_recall']:.2f}**, "
        f"incipient **{mA['incipient_recall']}**, "
        f"unmatched/wk **{um:.3g}**, union% **{union:.3g}**, "
        f"dup24h={mA['duplicate_unmatched_within_24h']}, "
        f"episodes={inf['n_episodes']}.",
        f"Secondary abrupt-only view B abrupt 6h **{a6b:.2f}** "
        f"(not a joint-detection claim). View C abrupt 6h "
        f"**{ev['metrics']['C']['abrupt_6h']['recall']:.2f}**.",
        f"Post-fit-only abrupt 6h (onset ≥ earliest eligible notify): "
        f"**{post['recall']:.2f}** ({post['n_hit']}/{post['n_abrupt']}).",
        f"0–6 h shortened-window null: observed {null6['observed_abrupt_matches']}/"
        f"{null6['n_abrupt_onsets']}, frac shifts≥obs="
        f"{null6['fraction_shifts_ge_observed']:.2f}.",
        ev["latch"]["note"],
    ]
    useful = (
        np.isfinite(a6)
        and a6 >= 2.0 / 3.0
        and um <= 3.0
        and not latched
        and union < 50
    )
    manageable = um <= 3.0 and not latched and union < 25
    if useful and manageable:
        verdict = (
            "**Candid:** frozen FMR3C shows usable six-hour abrupt sensitivity with "
            "manageable unmatched burden on this 2019 run under provisional engineering "
            "targets — still diagnostic given prior examination, not validated detection."
        )
    elif manageable and (not np.isfinite(a6) or a6 < 2.0 / 3.0):
        verdict = (
            "**Candid:** burden looks manageable (low unmatched/wk / occupancy), but "
            "six-hour abrupt sensitivity on the broader year is **not** useful enough "
            "under the same provisional bar used on DEV (≥2/3). Do not treat low FP "
            "rate alone as success."
        )
    elif useful and not manageable:
        verdict = (
            "**Candid:** abrupt timing looks stronger, but notification / occupancy "
            "burden is not clearly manageable for operations under the provisional caps."
        )
    else:
        verdict = (
            "**Candid:** frozen detector does **not** jointly deliver useful six-hour "
            "abrupt sensitivity and manageable burden across 2019 under the declared "
            "provisional targets. Consistent with the 2018 DIAG empirical no-go on "
            "abrupt timing; 2019 does not rehabilitate the frozen threshold."
        )
    parts.append(verdict)
    parts.append(
        "Do not select a secondary view as the sole headline; registered view remains A."
    )
    return " ".join(parts)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen_emp = json.loads(FROZEN_PATH.read_text())
    tau = float(frozen_emp["selected"]["tau"])
    l_q = float(frozen_emp["signal"]["l_q_hours"])
    l_r = float(frozen_emp["signal"]["l_r_hours"])
    assert abs(l_q - 2.0) < 1e-12 and abs(l_r - 48.0) < 1e-12

    print("=== Stage 0: freeze hashes (before inference) ===", flush=True)
    freeze = freeze_record(tau, l_q, l_r)
    (OUT / "year2019_freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
    print(f"Wrote {OUT / 'year2019_freeze.json'}; tau={tau}", flush=True)

    print("=== Stage 1: inference (pressures only; GT sealed) ===", flush=True)
    pb = load_pressures(DEFAULT_RAW / "2019_SCADA_Pressures.csv")
    g0, g1 = period_indices(pb.timestamps, YEAR2019)
    assert str(pb.timestamps[g0]).replace("T", " ") == "2019-01-01 00:00"
    assert str(pb.timestamps[g1 - 1]).replace("T", " ") == "2019-12-31 23:55"

    t_inf0 = time.perf_counter()
    sig, train_z, tr0, tr1 = build_period_signals(
        pb.pressures,
        interval_start=g0,
        interval_end=g1,
        train_days=TRAIN_DAYS,
        n_refs=N_REFS,
    )
    train_end = train_end_time(pb.timestamps, g0, TRAIN_DAYS)
    assert sig.analysis_offset == tr1
    assert train_end == pb.timestamps[tr1]

    n_q = hours_to_steps(l_q)
    n_r = hours_to_steps(l_r)
    warm_steps = first_valid_t(n_q, n_r)
    earliest_idx = sig.analysis_offset + warm_steps
    earliest_notify = pb.timestamps[earliest_idx]

    scores = build_score_bundle(
        sig.z,
        pb.sensor_ids,
        sig.target_models,
        analysis_offset=sig.analysis_offset,
        train_z=train_z,
        l_q_hours=l_q,
        l_r_hours=l_r,
    )
    episodes = run_all_targets_from_scores(scores, tau=tau)
    runtime = time.perf_counter() - t_inf0

    z_sha = hashlib.sha256(np.ascontiguousarray(sig.z).tobytes()).hexdigest()
    scores_sha = hash_scores(scores)
    ep_json = episodes_to_json(pb.timestamps, episodes)
    ep_bytes = json.dumps(ep_json, sort_keys=True, separators=(",", ":")).encode()
    ep_sha = hashlib.sha256(ep_bytes).hexdigest()

    # Persist inference artifacts before GT
    score_meta = {
        sid: {
            "target_idx": info["target_idx"],
            "refs": info["refs"],
            "sigma": info["sigma"],
            "n_finite": int(np.sum(np.isfinite(info["s"]))),
            "max": float(np.nanmax(info["s"])) if np.any(np.isfinite(info["s"])) else None,
        }
        for sid, info in scores["per_target"].items()
    }
    inference = {
        "generated_at": iso_now(),
        "gt_loaded": False,
        "fitting": {
            "train_start": str(pb.timestamps[tr0]).replace("T", " "),
            "train_last_sample": str(pb.timestamps[tr1 - 1]).replace("T", " "),
            "train_end": str(train_end).replace("T", " "),
            "train_days": TRAIN_DAYS,
            "warm_up_steps": warm_steps,
            "warm_up_hours": warm_steps * 5 / 60.0,
            "earliest_eligible_notification": str(earliest_notify).replace("T", " "),
            "n_q": n_q,
            "n_r": n_r,
        },
        "tau": tau,
        "l_q_hours": l_q,
        "l_r_hours": l_r,
        "n_sensors": len(pb.sensor_ids),
        "n_eligible_sensors": len(scores["per_target"]),
        "analysis_offset": int(sig.analysis_offset),
        "analysis_end": int(g1),
        "analysis_steps": int(g1 - sig.analysis_offset),
        "z_sha256": z_sha,
        "z_sha256_16": z_sha[:16],
        "scores_sha256": scores_sha,
        "episodes_sha256": ep_sha,
        "n_episodes": len(episodes),
        "runtime_seconds": runtime,
        "score_meta": score_meta,
        "scale_meta": scores["scale_meta"],
        "episodes": ep_json,
        "first_notification": ep_json[0]["notify_time"] if ep_json else None,
        "note": "Ground truth not used for scoring or episode generation.",
    }
    (OUT / "year2019_inference.json").write_text(
        json.dumps(inference, indent=2) + "\n"
    )
    # Compact score dump for audit (npz-free npz)
    np.savez_compressed(
        OUT / "year2019_scores.npz",
        **{sid: info["s"] for sid, info in scores["per_target"].items()},
    )
    print(
        f"Inference done: episodes={len(episodes)} earliest_eligible={earliest_notify} "
        f"scores_sha={scores_sha[:16]}…",
        flush=True,
    )

    print("=== Stage 2: evaluation (load GT) ===", flush=True)
    leakages = load_leakages()
    strata = classify_strata(
        leakages,
        train_end=train_end,
        earliest_notify=earliest_notify,
        year=YEAR2019,
    )
    year_onsets = onsets_in_period(leakages, YEAR2019)
    primary, in_prefix = split_eligible_onsets(year_onsets, train_end)
    weeks = float((g1 - g0) * 5 / (60 * 24 * 7))

    views = {
        "A": view_A(pb.timestamps, episodes, primary, leakages),
        "B": view_B(pb.timestamps, episodes, primary, leakages),
        "C": view_C(pb.timestamps, episodes, primary, leakages),
    }
    occ = occupancy_report(
        pb.timestamps,
        episodes,
        sig.analysis_offset,
        g1,
        n_sensors=len(pb.sensor_ids),
    )
    occ_slim = {
        k: occ[k]
        for k in (
            "summed_sensor_alarm_pct_of_eligible",
            "union_alarm_pct_of_analysis",
            "n_notifications",
            "n_episodes_right_censored",
            "episode_length_hours",
            "active_sensors",
            "summed_sensor_alarm_hours",
            "union_alarm_hours",
        )
    }

    metrics = {}
    for key, v in views.items():
        used = set(v["used_episode_indices"])
        dup = duplicate_unmatched(pb.timestamps, episodes, used)
        metrics[key] = metrics_for_view(v, episodes, weeks, occ_slim, dup)

    nulls_by_view = {
        "A": null_view_abrupt_counts(
            view_A, pb.timestamps, episodes, primary, leakages, sig.analysis_offset, g1
        ),
        "B": null_view_abrupt_counts(
            view_B, pb.timestamps, episodes, primary, leakages, sig.analysis_offset, g1
        ),
        "C": null_view_abrupt_counts(
            view_C, pb.timestamps, episodes, primary, leakages, sig.analysis_offset, g1
        ),
    }
    null2 = null_at_post_hours(
        pb.timestamps, episodes, primary, leakages, sig.analysis_offset, g1, 2.0
    )
    null6 = null_at_post_hours(
        pb.timestamps, episodes, primary, leakages, sig.analysis_offset, g1, 6.0
    )

    conflicts = credit_conflicts(pb.timestamps, episodes, primary)

    # Post-fit subset metrics under A assignments
    a_by_pipe = {m["pipe"]: m for m in views["A"]["matches"]}
    post_fit_onsets = [
        L for L in primary if L.start >= earliest_notify
    ]
    post_rows = []
    for L in sorted(post_fit_onsets, key=lambda x: x.start):
        m = a_by_pipe.get(L.pipe)
        if m is None:
            post_rows.append(match_row(L, None, None, False))
        else:
            post_rows.append(m)
    post_fit_under_A = {
        "abrupt_recall": recall_block(post_rows)["abrupt_recall"],
        "incipient_recall": recall_block(post_rows)["incipient_recall"],
        "abrupt_6h": abrupt_6h(post_rows),
        "assignments": post_rows,
    }
    warm_under_A = [
        a_by_pipe[L.pipe]
        for L in primary
        if L.start < earliest_notify and L.pipe in a_by_pipe
    ]

    # p523 detail
    p523_stratum = "absent"
    if strata["p523"]:
        onset = np.datetime64(strata["p523"][0]["onset"].replace(" ", "T"))
        if onset < train_end:
            p523_stratum = "training_prefix"
        elif onset < earliest_notify:
            p523_stratum = "warm_up"
        else:
            p523_stratum = "post_fit"
    p523_detail = {
        "stratum": p523_stratum,
        "views": {
            k: next(
                (m for m in views[k]["matches"] if m.get("pipe") == "p523"),
                None,
            )
            for k in ("A", "B", "C")
        },
    }

    prefix_matches, _ = match_episodes(pb.timestamps, episodes, in_prefix, leakages)

    latch = latch_note(
        {
            "occupancy": occ_slim,
            "unmatched_per_week": metrics["A"]["unmatched_per_week"],
            "n_episodes": len(episodes),
        }
    )

    evaluation = {
        "gt_loaded_at": iso_now(),
        "weeks_in_period": weeks,
        "strata": strata,
        "views": views,
        "metrics": metrics,
        "nulls_by_view": nulls_by_view,
        "null_2h": null2,
        "null_6h": null6,
        "credit_conflicts": conflicts,
        "post_fit_under_A": post_fit_under_A,
        "warm_up_under_A": warm_under_A,
        "in_prefix_matches": prefix_matches,
        "p523_detail": p523_detail,
        "latch": latch,
        "primary_onset_count": len(primary),
    }

    # Mark inference as sealed then evaluated
    inference["gt_loaded"] = True
    inference["gt_loaded_at"] = evaluation["gt_loaded_at"]
    (OUT / "year2019_inference.json").write_text(
        json.dumps(inference, indent=2) + "\n"
    )

    assessment = assess(evaluation, inference)
    doc = {
        "generated_at": iso_now(),
        "freeze": freeze,
        "inference": {
            k: v
            for k, v in inference.items()
            if k not in ("episodes", "score_meta", "scale_meta")
        },
        "evaluation": evaluation,
        "assessment": assessment,
        "holdout_honesty": (
            "Prior 2019 examination acknowledged; not an untouched holdout. "
            "τ frozen from 2018 DEV; not recomputed from 2019 scores."
        ),
    }
    # JSON may contain numpy types from occupancy — sanitize
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
        return o

    (OUT / "year2019_evaluation.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "YEAR2019_EVALUATION.md").write_text(render(doc) + "\n")
    print(assessment, flush=True)
    print(f"Wrote {OUT / 'YEAR2019_EVALUATION.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
