#!/usr/bin/env python3
"""Synthetic-trained detection pilot — orchestrate sim → fit → 2018 transfer.

Preserves FMR3C and production. No 2019 training/tuning. No Tiger.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dataset_build import build_split_tables
from evaluate_measured import (
    abrupt_6h,
    eval_period,
    run_fmr3c_baseline,
    run_supervised_on_measured,
)
from features import feature_manifest
from io_measured import load_measured_2018
from schema import DEFAULT_INP, DEFAULT_RAW, FEATURE_CONFIG
from simulate import run_all_scenarios
from train_pilot import evaluate_synthetic_split, fit_select

CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))
from evaluate import DEV, DIAG, period_indices  # noqa: E402
from io_data import load_leakages  # noqa: E402
from audit_occupancy_recovery import train_end_time  # noqa: E402

OUT = ROOT / "outputs"
SIM_DIR = OUT / "synthetic_scenarios"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(doc: dict) -> str:
    lines = [
        "# Synthetic-trained detection pilot",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Preserves production, frozen FMR3C, and all prior evaluations. "
        "**No** 2019 train/tune, Tiger, UI, or main merge.",
        "",
        "## Question",
        "",
        "Can a simple L2 logistic classifier trained on varied hydraulic leak "
        "scenarios recognize event patterns in measured 2018 SCADA?",
        "",
        "## 0. Feature pipeline",
        "",
        f"- Feature set: `{doc['feature_manifest']['feature_set']}` "
        f"({doc['feature_manifest']['n_features']} dims)",
        f"- Units: {doc['feature_manifest']['units']}",
        f"- Forbidden inputs: {doc['feature_manifest']['forbidden']}",
        f"- INP: `{doc['inp_sha256'][:16]}…` (`L-TOWN.inp`)",
        f"- Tests: {doc['tests']}",
        "",
        "## 1. Synthetic dataset (bounded pilot)",
        "",
        f"- Master seed: **{doc['synthetic']['master_seed']}**",
        f"- Planned / ok / failed: {doc['synthetic']['n_planned']} / "
        f"{doc['synthetic']['n_ok']} / {doc['synthetic']['n_failed']}",
        f"- Leak pipe sampling: {doc['synthetic']['leak_sampling_note']}",
        f"- Similarity: {doc['synthetic']['similarity_note']}",
        "",
        "Failures (recorded, not dropped silently):",
        "",
    ]
    if not doc["synthetic"]["failures"]:
        lines.append("- *(none)*")
    for f in doc["synthetic"]["failures"]:
        lines.append(
            f"- `{f['spec']['scenario_id']}`: {f.get('error')}"
        )
    sp = doc["splits"]
    lines += [
        "",
        "### Splits (whole-scenario)",
        "",
        f"- Rules: {sp['rules']}",
        f"- Counts: `{sp['counts']}`",
        f"- Holdout pipe groups: {sp['holdout_pipe_groups']}",
        "",
        "## 2. Synthetic performance (separate from measured)",
        "",
        f"- Selected: C={doc['frozen']['selected']['C']}, "
        f"τ_prob={doc['frozen']['selected']['tau']}",
        f"- Selection rule: {doc['frozen']['selection_rule']}",
        f"- Budget: {doc['frozen']['budget']}",
        "",
        "| Split | Scenario recall | Row recall | FP row rate | n_pos rows | n_scen |",
        "|-------|-----------------|------------|-------------|------------|--------|",
    ]
    for name in ("train_replay", "synthetic_dev", "synthetic_test"):
        m = doc["synthetic_eval"][name]
        if m.get("empty"):
            lines.append(f"| {name} | — | — | — | 0 | 0 |")
        else:
            lines.append(
                f"| {name} | {m.get('scenario_recall')} | {m.get('row_recall')} | "
                f"{m.get('fp_row_rate')} | {m.get('n_pos')} | "
                f"{m.get('n_leak_scenarios_eval')} |"
            )
    lines += [
        "",
        "Synthetic events are **not** additional independent real leak events.",
        "Probability calibration is **not** claimed to transfer to measured data.",
        "",
        "## 3. Measured 2018 transfer (diagnostic — prior examination)",
        "",
        "Eligible onsets use the same post-14-day-prefix rule as FMR3C. "
        "Matching: joint chronological greedy (registered).",
        "",
    ]
    for period in ("DEV", "DIAG"):
        s = doc["measured"]["supervised"][period]
        f = doc["measured"]["fmr3c"][period]
        lines += [
            f"### {period}",
            "",
            f"Eligible onsets (n={s['n_eligible_onsets']}): "
            + ", ".join(
                f"{o['pipe']}({o['leak_type']})" for o in s["eligible_onsets"]
            ),
            "",
            "| Detector | Abrupt 6h | Abrupt hits/n | Unmatched/wk | Dup24h | "
            "Union% | Episodes |",
            "|----------|-----------|---------------|--------------|-------|"
            "--------|----------|",
            f"| Supervised pilot | **{s['abrupt_6h']['recall']}** | "
            f"{s['abrupt_6h']['n_hit']}/{s['abrupt_6h']['n_abrupt']} | "
            f"{s['unmatched_per_week']:.4g} | {s['duplicate_unmatched_within_24h']} | "
            f"{s['occupancy']['union_alarm_pct_of_analysis']:.4g} | {s['n_episodes']} |",
            f"| Frozen FMR3C | **{f['abrupt_6h']['recall']}** | "
            f"{f['abrupt_6h']['n_hit']}/{f['abrupt_6h']['n_abrupt']} | "
            f"{f['unmatched_per_week']:.4g} | {f['duplicate_unmatched_within_24h']} | "
            f"{f['occupancy']['union_alarm_pct_of_analysis']:.4g} | {f['n_episodes']} |",
            "",
            "Supervised per-event (abrupt):",
            "",
        ]
        for row in s["abrupt_6h"]["per_event"]:
            tag = "HIT6" if row["within_6h"] else ("HIT>6" if row["matched"] else "MISS")
            lines.append(
                f"- {tag} {row['pipe']} delay_h={row['delay_hours']} "
                f"notify={row['notify_time']}"
            )
        lines += ["", "Misses (all types under supervised):", ""]
        for m in s["misses"]:
            lines.append(
                f"- MISS {m['pipe']} ({m['leak_type']}) onset={m['onset']}"
            )
        lines.append("")

    lines += [
        "## 4. Diagnosis",
        "",
        doc["diagnosis"],
        "",
        "## Non-goals / stop",
        "",
        "- No measured DIAG retuning",
        "- No 2019 in this round",
        "- No simulator/model search expansion",
        "- FMR3C artifacts untouched",
        "",
    ]
    return "\n".join(lines)


def diagnose(doc: dict) -> str:
    s_dev = doc["measured"]["supervised"]["DEV"]["abrupt_6h"]
    f_dev = doc["measured"]["fmr3c"]["DEV"]["abrupt_6h"]
    s_diag = doc["measured"]["supervised"]["DIAG"]["abrupt_6h"]
    f_diag = doc["measured"]["fmr3c"]["DIAG"]["abrupt_6h"]
    syn_test = doc["synthetic_eval"]["synthetic_test"]
    syn_ok = (
        not syn_test.get("empty")
        and np.isfinite(syn_test.get("scenario_recall", np.nan))
        and syn_test["scenario_recall"] >= 0.5
    )
    meas_weak = (
        (s_dev["recall"] if np.isfinite(s_dev["recall"]) else 0) < 0.5
        and (s_diag["recall"] if np.isfinite(s_diag["recall"]) else 0) < 0.5
    )
    parts = [
        f"Synthetic test scenario recall={syn_test.get('scenario_recall')}; "
        f"DEV supervised abrupt6h={s_dev['recall']} vs FMR3C={f_dev['recall']}; "
        f"DIAG supervised={s_diag['recall']} vs FMR3C={f_diag['recall']}.",
    ]
    if syn_ok and meas_weak:
        parts.append(
            "**Transfer failure diagnosis: domain mismatch is the leading explanation** "
            "(separability exists under the nominal hydraulic model, but measured 2018 "
            "SCADA patterns are not recovered by the same linear score). "
            "Do not expand the simulator search in this pilot."
        )
    elif not syn_ok and meas_weak:
        parts.append(
            "**Failure diagnosis: lack of separability even in synthetic pilot** "
            "(and no measured transfer). The bounded scenario set / linear features "
            "may be insufficient — still not a license to enlarge the search here."
        )
    elif not meas_weak and (
        s_dev["recall"] >= f_dev["recall"] or s_diag["recall"] >= f_diag["recall"]
    ):
        parts.append(
            "Measured transfer shows some abrupt timing signal versus FMR3C on at least "
            "one period; still diagnostic (prior examination), not validated detection. "
            "Calibration of probabilities is not claimed."
        )
    else:
        parts.append(
            "Mixed / weak measured transfer. Treat as pilot evidence only; "
            "no DIAG retune; no 2019."
        )
    um = doc["measured"]["supervised"]["DIAG"]["unmatched_per_week"]
    if um > 10:
        parts.append(
            f"Supervised unmatched/wk on DIAG={um:.3g} indicates burden may be "
            "unmanageable even if a few hits appear."
        )
    return " ".join(parts)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== Tests (before fitting) ===", flush=True)
    import pytest

    tr = pytest.main([str(ROOT / "tests"), "-q"])
    if tr != 0:
        print("TESTS FAILED — aborting before fit", flush=True)
        return 1

    print("=== Simulate bounded pilot ===", flush=True)
    t0 = time.perf_counter()
    syn = run_all_scenarios(SIM_DIR, DEFAULT_INP)
    print(
        f"Sim done in {time.perf_counter()-t0:.1f}s ok={syn['n_ok']} fail={syn['n_failed']}",
        flush=True,
    )

    print("=== Build tables + fit ===", flush=True)
    tables = build_split_tables(SIM_DIR)
    frozen = fit_select(tables["splits"]["train"], tables["splits"]["synthetic_dev"])
    frozen["frozen_at"] = iso_now()
    frozen["feature_names"] = tables["feature_names"]
    (OUT / "pilot_frozen_model.json").write_text(json.dumps(frozen, indent=2) + "\n")

    syn_eval = {
        "train_replay": evaluate_synthetic_split(frozen, tables["splits"]["train"]),
        "synthetic_dev": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_dev"]
        ),
        "synthetic_test": evaluate_synthetic_split(
            frozen, tables["splits"]["synthetic_test"]
        ),
    }
    (OUT / "pilot_synthetic_eval.json").write_text(json.dumps(syn_eval, indent=2) + "\n")
    print(f"Frozen C={frozen['selected']['C']} tau={frozen['selected']['tau']}", flush=True)
    print(f"Synth test: {syn_eval['synthetic_test']}", flush=True)

    print("=== Measured 2018 transfer ===", flush=True)
    measured = load_measured_2018(DEFAULT_RAW)
    episodes, q = run_supervised_on_measured(frozen, measured)
    np.savez_compressed(OUT / "pilot_measured_2018_scores.npz", q=q)
    leakages = load_leakages()

    measured_out = {"supervised": {}, "fmr3c": {}}
    for period, name in ((DEV, "DEV"), (DIAG, "DIAG")):
        g0, g1 = period_indices(measured["timestamps"], period)
        # Supervised uses full-year continuous scores; restrict episodes by period notify
        measured_out["supervised"][name] = eval_period(
            measured["timestamps"],
            episodes,
            leakages,
            period,
            analysis_start=g0,
            analysis_end=g1,
            n_sensors=1,
            label="supervised_pilot",
        )
        print(
            f"Supervised {name} abrupt6h="
            f"{measured_out['supervised'][name]['abrupt_6h']['recall']}",
            flush=True,
        )
        measured_out["fmr3c"][name] = run_fmr3c_baseline(
            DEFAULT_RAW / "2018_SCADA_Pressures.csv", name
        )
        print(
            f"FMR3C {name} abrupt6h="
            f"{measured_out['fmr3c'][name]['abrupt_6h']['recall']}",
            flush=True,
        )

    doc = {
        "generated_at": iso_now(),
        "tests": "passed",
        "feature_manifest": feature_manifest(),
        "inp_sha256": file_sha256(DEFAULT_INP),
        "raw_pressure_sha256": file_sha256(DEFAULT_RAW / "2018_SCADA_Pressures.csv"),
        "synthetic": {
            "master_seed": syn["master_seed"],
            "n_planned": syn["n_planned"],
            "n_ok": syn["n_ok"],
            "n_failed": syn["n_failed"],
            "leak_sampling_note": syn["leak_sampling_note"],
            "similarity_note": syn["similarity_note"],
            "failures": syn["failures"],
        },
        "splits": tables["split_info"],
        "split_row_counts": {
            k: {
                "n_rows": v["n_rows"],
                "n_pos": v["n_pos"],
                "n_scenarios": v["n_scenarios"],
            }
            for k, v in tables["splits"].items()
        },
        "frozen": {
            "selected": frozen["selected"],
            "selection_rule": frozen["selection_rule"],
            "budget": frozen["budget"],
            "dev_metrics": frozen["dev_metrics"],
            "n_train": frozen["n_train"],
            "n_train_pos": frozen["n_train_pos"],
        },
        "synthetic_eval": syn_eval,
        "measured": measured_out,
        "holdout_honesty": (
            "2018 measured evaluation is diagnostic (events previously examined). "
            "2019 not used. Synthetic metrics kept separate."
        ),
    }
    doc["diagnosis"] = diagnose(doc)

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

    (OUT / "pilot_summary.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "PILOT_RESULTS.md").write_text(render(doc) + "\n")
    print(doc["diagnosis"], flush=True)
    print(f"Wrote {OUT / 'PILOT_RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
