#!/usr/bin/env python3
"""Frozen Method M on 2019 — diagnostic evaluation (not a blind holdout).

Order: hash frozen bundle → build 2019 dual → score/notify → hash scores/notifies
→ only then load labels and evaluate. No retuning.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_protocol import (  # noqa: E402
    CREDIT_HOURS,
    REQUIRED_FROZEN_SHA256,
    WARMUP_HOURS,
)
from dual_model.detection_scores import score_M_maxabs_local_change  # noqa: E402
from dual_model.dual_series import build_dual_qv_hourly, verify_frozen_hash  # noqa: E402
from dual_model.notifier import episodes_from_scores  # noqa: E402

OUT = ROOT / "outputs" / "detection_2019_method_m"
M2018 = ROOT / "outputs" / "detection_2018_measured_pump1"
FROZEN_CAL = ROOT / "outputs" / "calibration" / "frozen_calibration.json"
TAU = 4.347
EVAL_START = pd.Timestamp("2019-01-01 00:00:00")
EVAL_END = pd.Timestamp("2019-12-31 23:00:00")
N_NULLS = 200


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


@dataclass(frozen=True)
class LeakEvent:
    pipe: str
    start: pd.Timestamp
    end: pd.Timestamp
    leak_type: str  # abrupt | incipient
    peak: pd.Timestamp
    diameter_m: float


def parse_leak_catalog() -> list[LeakEvent]:
    cfg_path = ROOT.parents[1] / "data" / "raw" / "dataset_configuration.yaml"
    raw = cfg_path.read_text().splitlines()
    events = []
    for line in raw:
        line = line.strip()
        if not line.startswith("- p"):
            continue
        if "incipient" not in line and "abrupt" not in line:
            continue
        body = line.lstrip("- ").strip()
        parts = [p.strip() for p in body.split(",")]
        if len(parts) < 6:
            continue
        pipe, start, end, diam, ltype, peak = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
            parts[5],
        )
        events.append(
            LeakEvent(
                pipe=pipe,
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
                leak_type=ltype,
                peak=pd.Timestamp(peak),
                diameter_m=float(diam),
            )
        )
    if not events:
        raise RuntimeError(f"No leak events parsed from {cfg_path}")
    return events


def record_pre_inference_hashes() -> dict:
    m2018 = json.loads((M2018 / "method_m_results.json").read_text())
    scale = m2018["scale"]
    scale_blob = json.dumps(
        {"sigma_m3h": scale["sigma_m3h"], "raw_max_median": scale["raw_max_median"]},
        sort_keys=True,
    )
    tau_blob = f"{TAU:.12g}"
    paths = {
        "frozen_calibration.json": FROZEN_CAL,
        "METHOD_M_PROTOCOL.md": M2018 / "METHOD_M_PROTOCOL.md",
        "PUMP1_MEASURED_BOUNDARY.md": ROOT / "PUMP1_MEASURED_BOUNDARY.md",
        "pump_boundary.py": ROOT / "dual_model" / "pump_boundary.py",
        "notifier.py": ROOT / "dual_model" / "notifier.py",
        "detection_scores.py": ROOT / "dual_model" / "detection_scores.py",
        "OPERATING_POINT_PROTOCOL.md": M2018 / "OPERATING_POINT_PROTOCOL.md",
        "method_m_results.json": M2018 / "method_m_results.json",
    }
    file_hashes = {k: sha256_file(p) for k, p in paths.items() if p.exists()}
    cal_hash = file_hashes["frozen_calibration.json"]
    if cal_hash != REQUIRED_FROZEN_SHA256:
        raise RuntimeError(f"calibration hash mismatch: {cal_hash}")
    payload = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "acknowledgement": (
            "2019 has already been examined during previous research; "
            "this is a frozen diagnostic evaluation, not a blind holdout."
        ),
        "file_sha256": file_hashes,
        "calibration_sha256": cal_hash,
        "sensor_scales_sha256": sha256_text(scale_blob),
        "sensor_scales_n": len(scale["sigma_m3h"]),
        "raw_max_median": scale["raw_max_median"],
        "tau": TAU,
        "tau_sha256": sha256_text(tau_blob),
        "causality": {
            "calibration_uses_future_2019": False,
            "scales_use_future_2019": False,
            "tau_selected_on_2019": False,
            "score_ref_looks_ahead": False,
            "pump_bc_looks_ahead": False,
            "notes": (
                "Scales from 2018 SCALE; τ from 2018 DEV; dual/score use only "
                "measurements at/before analysis time."
            ),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pre_inference_hashes.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload, scale


def event_rows_for(
    events: list[LeakEvent],
    *,
    notify_times: list[pd.Timestamp],
    score: pd.Series,
    active: np.ndarray,
    index: pd.DatetimeIndex,
    eval_start: pd.Timestamp,
    eval_end: pd.Timestamp,
    warm_end: pd.Timestamp,
    kind: str,
) -> list[dict]:
    rows = []
    for ev in events:
        onset = ev.start
        if onset < eval_start or onset > eval_end:
            continue
        credit_end = onset + pd.Timedelta(hours=CREDIT_HOURS)
        in_warmup = onset < warm_end
        # pre-onset blocking: active on last index strictly before onset
        before = index[index < onset]
        blocked = False
        if len(before):
            i_before = index.get_loc(before[-1])
            if isinstance(i_before, (slice, np.ndarray)):
                i_before = int(np.asarray(i_before).ravel()[0])
            blocked = bool(active[int(i_before)])
        cands = [t for t in notify_times if onset <= t <= credit_end]
        hit = len(cands) > 0
        delay = float((min(cands) - onset).total_seconds() / 3600.0) if hit else None
        credit = score.loc[(score.index >= onset) & (score.index <= credit_end)]
        credit = credit[np.isfinite(credit)]
        rows.append(
            {
                "pipe": ev.pipe,
                "leak_type": kind,
                "onset": str(onset),
                "peak": str(ev.peak),
                "end": str(ev.end),
                "excluded_warmup": bool(in_warmup),
                "hit": hit and not in_warmup,
                "hit_including_warmup": hit,
                "delay_hours": delay if not in_warmup else None,
                "pre_onset_blocked": blocked,
                "credit_max_score": float(credit.max()) if len(credit) else None,
                "n_credit_notifies": len(cands),
                "score_finite_in_credit": int(len(credit)),
            }
        )
    return rows


def timing_null_detail(
    score: pd.Series,
    events: list[dict],
    *,
    tau: float,
    notify_times: list[pd.Timestamp],
    eval_start: pd.Timestamp,
    eval_end: pd.Timestamp,
    warm_end: pd.Timestamp,
    rng: np.random.Generator,
    n_nulls: int = N_NULLS,
) -> dict:
    """Identical matching rules to detection_eval.timing_nulls; return counts."""
    eligible = [
        e for e in events if not e["excluded_warmup"] and pd.Timestamp(e["onset"]) >= warm_end
    ]
    if not eligible:
        return {"n_nulls": 0, "n_events": 0}
    true_onsets = [pd.Timestamp(e["onset"]) for e in eligible]
    index = score.index[(score.index >= eval_start) & (score.index <= eval_end)]
    eligible_hours = index[(index >= warm_end) & (index <= eval_end)]
    hod = [t.hour for t in true_onsets]
    pools = {h: eligible_hours[eligible_hours.hour == h] for h in range(24)}

    def recall_for(onsets: list[pd.Timestamp]) -> float:
        hits = 0
        for onset in onsets:
            ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
            if any(onset <= t <= ce for t in notify_times):
                hits += 1
        return hits / len(onsets)

    true_recall = recall_for(true_onsets)
    null_recalls = []
    n_draws = 0
    for _ in range(n_nulls):
        sampled = []
        for h in hod:
            pool = pools.get(int(h), eligible_hours)
            if len(pool) == 0:
                pool = eligible_hours
            sampled.append(pd.Timestamp(rng.choice(pool)))
            n_draws += 1
        null_recalls.append(recall_for(sampled))
    arr = np.asarray(null_recalls, dtype=float)
    cnt = Counter(np.round(arr, 6))
    return {
        "n_null_replicates": n_nulls,
        "n_events_E": len(true_onsets),
        "n_onset_timestamp_draws_total": n_draws,
        "n_fixed_notifies_in_eval": len(
            [t for t in notify_times if eval_start <= t <= eval_end]
        ),
        "true_recall": true_recall,
        "null_recall_mean": float(arr.mean()),
        "null_recall_std": float(arr.std(ddof=0)),
        "true_percentile_vs_null": float((arr <= true_recall).mean()),
        "n_nulls_recall_le_true": int((arr <= true_recall).sum()),
        "n_nulls_recall_ge_true": int((arr >= true_recall).sum()),
        "null_recall_value_counts": {str(k): int(v) for k, v in sorted(cnt.items())},
        "assignment_rules": (
            "For each of N replicates, sample |E| onsets from eligible eval hours "
            "matching each true event's hour-of-day; hit if any frozen notify lies in "
            "[onset, onset+6h]. Percentile = fraction of null recalls ≤ true recall."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = OUT / "_scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    print("=== Phase 0: pre-inference hashes (no 2019 labels) ===", flush=True)
    pre, scale = record_pre_inference_hashes()
    sigma = pd.Series(scale["sigma_m3h"], dtype=float)
    cal = float(scale["raw_max_median"])
    print(f"calibration={pre['calibration_sha256'][:16]}… τ={TAU} scales_n={pre['sensor_scales_n']}", flush=True)

    print("=== Phase 1: 2019 measured-PUMP_1 dual (frozen cal) ===", flush=True)
    qv19, flows19, levels19, meta19 = build_dual_qv_hourly(
        "2019-01-01 00:00:00",
        "2019-12-31 23:00:00",
        frozen_path=FROZEN_CAL,
        scratch=scratch,
        chunk_days=7,
        pump_boundary="measured_pump1",
        scada_year=2019,
    )
    qv19.to_csv(OUT / "dual_qv_hourly_2019.csv")
    print(
        f"q_v2019 shape={qv19.shape} solver_failures={meta19['n_solver_failures']}/{meta19['n_chunks']}",
        flush=True,
    )

    # Prior-year history for causal ref + notifier continuity (no retune)
    qv18 = pd.read_csv(M2018 / "dual_qv_hourly.csv", index_col=0, parse_dates=True)
    # align columns
    cols = [c for c in sigma.index if c in qv18.columns and c in qv19.columns]
    qv18, qv19 = qv18[cols], qv19[cols]
    qv_all = pd.concat([qv18, qv19]).sort_index()
    qv_all = qv_all[~qv_all.index.duplicated(keep="last")]

    print("=== Phase 2: Method M scores (frozen σ, cal) — continuous ===", flush=True)
    score_all = score_M_maxabs_local_change(
        qv_all, sigma_m3h=sigma.reindex(cols), raw_max_median=cal
    )
    score_2019 = score_all.loc[(score_all.index >= EVAL_START) & (score_all.index <= EVAL_END)]
    score_2019.to_csv(OUT / "score_M_2019.csv", header=["score"])

    # Notifier on full concat so state carries across year boundary; no monthly reset
    print("=== Phase 3: notifications (continuous state) ===", flush=True)
    eps = episodes_from_scores(score_all.to_numpy(), tau=TAU)
    index_all = score_all.index
    notify_all = [
        index_all[ep.notify_idx] for ep in eps if 0 <= ep.notify_idx < len(index_all)
    ]
    active = np.zeros(len(index_all), dtype=bool)
    for ep in eps:
        if ep.notify_idx < 0:
            continue
        active[ep.notify_idx : ep.end_idx + 1] = True

    notify_2019 = [t for t in notify_all if EVAL_START <= t <= EVAL_END]
    # Availability: first finite score time in 2019
    finite_2019 = score_2019[np.isfinite(score_2019)]
    first_avail = str(finite_2019.index[0]) if len(finite_2019) else None
    n_nan_2019 = int((~np.isfinite(score_2019)).sum())

    # Hash scores and notifications BEFORE labels
    score_bytes = score_2019.to_csv(header=["score"]).encode("utf-8")
    notify_blob = "\n".join(str(t) for t in notify_2019) + "\n"
    pre_label = {
        "hashed_at_utc": datetime.now(timezone.utc).isoformat(),
        "score_M_2019_sha256": sha256_bytes(score_bytes),
        "n_score_hours": int(len(score_2019)),
        "n_finite_scores": int(np.isfinite(score_2019).sum()),
        "n_nan_scores": n_nan_2019,
        "first_notification_available_score_time": first_avail,
        "notifications_2019_sha256": sha256_text(notify_blob),
        "n_notifications_2019": len(notify_2019),
        "n_episodes_total_concat": len(eps),
        "solver_failures_2019": meta19["n_solver_failures"],
        "n_chunks_2019": meta19["n_chunks"],
        "missing_data_handling": {
            "score_NaN": "no notify; reset recovery counter (notifier.py)",
            "pump_missing": "causal ffill within dual chunk; else 0 with flag (pump_boundary)",
            "dual_nonconverged_chunk": "NaN q_v rows for chunk; propagates to score NaN",
        },
        "state_carry": {
            "notifier_reset_at_leak_onsets": False,
            "notifier_reset_at_month_boundaries": False,
            "score_history_includes_2018_for_ref_and_state": True,
        },
    }
    (OUT / "pre_label_hashes.json").write_text(json.dumps(pre_label, indent=2) + "\n")
    (OUT / "notifications_2019.txt").write_text(notify_blob)
    print(
        f"pre-label hashes written; n_notif_2019={len(notify_2019)} "
        f"score_sha={pre_label['score_M_2019_sha256'][:16]}…",
        flush=True,
    )

    print("=== Phase 4: load labels and evaluate (diagnostic) ===", flush=True)
    catalog = parse_leak_catalog()
    abrupt_2019 = [
        e for e in catalog if e.leak_type == "abrupt" and EVAL_START <= e.start <= EVAL_END
    ]
    incipient_2019 = [
        e for e in catalog if e.leak_type == "incipient" and EVAL_START <= e.start <= EVAL_END
    ]
    carryover = [
        e
        for e in catalog
        if e.start < EVAL_START and e.end >= EVAL_START
    ]

    warm_end = EVAL_START + pd.Timedelta(hours=WARMUP_HOURS)
    # Map active mask onto full index for blocking
    abrupt_rows = event_rows_for(
        abrupt_2019,
        notify_times=notify_all,
        score=score_all,
        active=active,
        index=index_all,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        kind="abrupt",
    )
    incip_rows = event_rows_for(
        incipient_2019,
        notify_times=notify_all,
        score=score_all,
        active=active,
        index=index_all,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        kind="incipient",
    )

    def summarize(rows: list[dict]) -> dict:
        elig = [r for r in rows if not r["excluded_warmup"]]
        warm = [r for r in rows if r["excluded_warmup"]]
        n_hit = sum(1 for r in elig if r["hit"])
        delays = [r["delay_hours"] for r in elig if r["delay_hours"] is not None]
        return {
            "n_listed": len(rows),
            "n_eligible": len(elig),
            "n_warmup_excluded": len(warm),
            "n_hit": n_hit,
            "recall": float(n_hit / len(elig)) if elig else float("nan"),
            "mean_delay_hours": float(np.mean(delays)) if delays else None,
            "delays_hours": delays,
            "n_pre_onset_blocked_among_eligible": sum(1 for r in elig if r["pre_onset_blocked"]),
            "events": rows,
        }

    abrupt_sum = summarize(abrupt_rows)
    incip_sum = summarize(incip_rows)

    # Unmatched / occupancy on 2019
    matched_notifies: set[pd.Timestamp] = set()
    for r in abrupt_rows + incip_rows:
        if r["excluded_warmup"]:
            continue
        onset = pd.Timestamp(r["onset"])
        ce = onset + pd.Timedelta(hours=CREDIT_HOURS)
        cands = [t for t in notify_2019 if onset <= t <= ce]
        if cands:
            matched_notifies.add(min(cands))
    unmatched = [t for t in notify_2019 if t not in matched_notifies]
    weeks = max((EVAL_END - EVAL_START).total_seconds() / (7 * 24 * 3600), 1e-9)
    # occupancy on 2019 hours
    mask_2019 = (index_all >= EVAL_START) & (index_all <= EVAL_END)
    occ = float(active[mask_2019].mean()) if mask_2019.any() else float("nan")

    # Carryover leak report (not counted in 2019 onset recall)
    carry_rows = []
    for e in carryover:
        # any notify in 2019 while leak still open?
        open_end = min(e.end, EVAL_END)
        n_in = sum(1 for t in notify_2019 if EVAL_START <= t <= open_end)
        carry_rows.append(
            {
                "pipe": e.pipe,
                "leak_type": e.leak_type,
                "start": str(e.start),
                "end": str(e.end),
                "n_2019_notifies_while_open": n_in,
            }
        )

    nulls = timing_null_detail(
        score_2019,
        abrupt_rows,
        tau=TAU,
        notify_times=notify_2019,
        eval_start=EVAL_START,
        eval_end=EVAL_END,
        warm_end=warm_end,
        rng=np.random.default_rng(2019),
        n_nulls=N_NULLS,
    )

    results = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "frozen_diagnostic_not_blind_holdout",
        "acknowledgement": pre["acknowledgement"],
        "pre_inference": {
            "calibration_sha256": pre["calibration_sha256"],
            "sensor_scales_sha256": pre["sensor_scales_sha256"],
            "tau": TAU,
            "tau_sha256": pre["tau_sha256"],
        },
        "pre_label": pre_label,
        "dual_2019_meta": {
            "n_chunks": meta19["n_chunks"],
            "n_solver_failures": meta19["n_solver_failures"],
            "pump_boundary": meta19["pump_boundary"],
            "failed_chunks": [c for c in meta19["chunks"] if not c.get("converged", True)],
        },
        "abrupt": abrupt_sum,
        "incipient": incip_sum,
        "carryover_leaks_from_before_2019": carry_rows,
        "burden": {
            "n_notifications_2019": len(notify_2019),
            "n_unmatched": len(unmatched),
            "unmatched_per_week": float(len(unmatched) / weeks),
            "occupancy": occ,
            "matching_note": (
                "Notify matched if it falls in any eligible abrupt OR incipient "
                "6h credit window; else unmatched."
            ),
        },
        "timing_nulls_abrupt": nulls,
    }
    (OUT / "method_m_2019_results.json").write_text(json.dumps(results, indent=2) + "\n")

    # Markdown report
    lines = [
        "# Frozen Method M on 2019 — diagnostic evaluation",
        "",
        f"**Not a blind holdout.** {pre['acknowledgement']}",
        "",
        f"Generated: `{results['generated_at_utc']}`  ",
        f"τ=`{TAU}` (frozen). Calibration `{pre['calibration_sha256'][:16]}…`.  ",
        f"Pre-label score hash `{pre_label['score_M_2019_sha256'][:16]}…`; "
        f"notify hash `{pre_label['notifications_2019_sha256'][:16]}…`.",
        "",
        "See `PRE_INFERENCE_FROZEN_BUNDLE.md` and `pre_inference_hashes.json`.",
        "",
        "## Dual / availability",
        "",
        f"- Solver failures: **{meta19['n_solver_failures']}** / {meta19['n_chunks']} chunks",
        f"- 2019 score hours: {len(score_2019)} (finite {pre_label['n_finite_scores']}, "
        f"NaN {n_nan_2019})",
        f"- First finite score in 2019: `{first_avail}`",
        f"- Notifier: continuous across 2018→2019 concat; **no** reset at onsets/months",
        "",
        "## Abrupt six-hour recall (2019 onsets)",
        "",
        f"| n eligible | n warmup excl. | recall | mean delay h | pre-onset blocked |",
        f"|----------:|---------------:|-------:|-------------:|------------------:|",
        f"| {abrupt_sum['n_eligible']} | {abrupt_sum['n_warmup_excluded']} | "
        f"{abrupt_sum['recall']} | {abrupt_sum['mean_delay_hours']} | "
        f"{abrupt_sum['n_pre_onset_blocked_among_eligible']} |",
        "",
        "| Pipe | Onset | Hit | Delay h | Pre-onset blocked | Credit max | Warm-up excl. |",
        "|------|-------|:---:|--------:|:-----------------:|-----------:|:-------------:|",
    ]
    for r in abrupt_rows:
        lines.append(
            f"| {r['pipe']} | {r['onset']} | {r['hit']} | {r['delay_hours']} | "
            f"{r['pre_onset_blocked']} | {r['credit_max_score']} | {r['excluded_warmup']} |"
        )

    lines.extend(
        [
            "",
            "## Incipient (separate; 6 h from catalog startTime)",
            "",
            f"Eligible recall: **{incip_sum['recall']}** "
            f"({incip_sum['n_hit']}/{incip_sum['n_eligible']}); "
            f"warmup excluded {incip_sum['n_warmup_excluded']}.",
            "",
            "| Pipe | Onset | Peak | Hit | Delay h | Pre-onset blocked | Credit max |",
            "|------|-------|------|:---:|--------:|:-----------------:|-----------:|",
        ]
    )
    for r in incip_rows:
        if r["excluded_warmup"]:
            continue
        lines.append(
            f"| {r['pipe']} | {r['onset']} | {r['peak']} | {r['hit']} | {r['delay_hours']} | "
            f"{r['pre_onset_blocked']} | {r['credit_max_score']} |"
        )

    lines.extend(
        [
            "",
            "## Burden",
            "",
            f"- Notifications (2019): **{len(notify_2019)}**",
            f"- Unmatched/week: **{results['burden']['unmatched_per_week']:.3f}** "
            f"({len(unmatched)} unmatched)",
            f"- Alarm occupancy (2019 hours): **{occ:.4f}**",
            "",
            "## Carryover leaks (started before 2019-01-01)",
            "",
            "| Pipe | Type | Start | End | n 2019 notifies while open |",
            "|------|------|-------|-----|---------------------------:|",
        ]
    )
    for r in carry_rows:
        lines.append(
            f"| {r['pipe']} | {r['leak_type']} | {r['start']} | {r['end']} | "
            f"{r['n_2019_notifies_while_open']} |"
        )

    tn = nulls
    lines.extend(
        [
            "",
            "## Timing nulls (abrupt; identical matching rules)",
            "",
            f"- N replicates: **{tn['n_null_replicates']}**; |E|=**{tn['n_events_E']}**; "
            f"onset draws=**{tn['n_onset_timestamp_draws_total']}**",
            f"- Fixed 2019 notifies used: **{tn['n_fixed_notifies_in_eval']}**",
            f"- True recall: **{tn['true_recall']}**",
            f"- Null mean±std: **{tn['null_recall_mean']:.4f} ± {tn['null_recall_std']:.4f}**",
            f"- Percentile (null≤true): **{tn['true_percentile_vs_null']}** "
            f"({tn['n_nulls_recall_le_true']}/{tn['n_null_replicates']})",
            f"- Nulls with recall≥true: **{tn['n_nulls_recall_ge_true']}/{tn['n_null_replicates']}**",
            f"- Value counts: `{tn['null_recall_value_counts']}`",
            "",
            tn["assignment_rules"],
            "",
            "## Stop",
            "",
            "No parameter changes after results. No UI / Tiger / deployment / main merge. "
            "Artifacts preserved under `outputs/detection_2019_method_m/` for review.",
            "",
        ]
    )
    (OUT / "METHOD_M_2019_RESULTS.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "METHOD_M_2019_RESULTS.md", flush=True)
    print(
        json.dumps(
            {
                "abrupt_recall": abrupt_sum["recall"],
                "incipient_recall": incip_sum["recall"],
                "unmatched_per_week": results["burden"]["unmatched_per_week"],
                "occupancy": occ,
                "solver_failures": meta19["n_solver_failures"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
