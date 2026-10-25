#!/usr/bin/env python3
"""Run measured-PUMP_1 synthetic verification; write results under outputs/synthetic."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.scenarios_measured_pump import run_all_measured_pump_scenarios  # noqa: E402


def main() -> int:
    out_dir = ROOT / "outputs" / "synthetic"
    scratch = out_dir / "_scratch_measured_pump"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    rows = run_all_measured_pump_scenarios(scratch)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formulation": "PUMP1_MEASURED_BOUNDARY.md",
        "scenarios": rows,
        "all_passed": all(r["passed"] for r in rows),
    }
    (out_dir / "MEASURED_PUMP_SYNTHETIC_RESULTS.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )

    lines = [
        "# Measured PUMP_1 synthetic verification",
        "",
        f"Generated: `{payload['generated_at_utc']}`  ",
        "Formulation: `PUMP1_MEASURED_BOUNDARY.md`",
        "",
        f"**All passed:** `{payload['all_passed']}`",
        "",
        "| Scenario | Pass | Key metric |",
        "|----------|------|------------|",
    ]
    for r in rows:
        key = {
            "measured_pump_matched_transition": "max|Σ|",
            "measured_pump_leak_stable": "mean Σ",
            "measured_pump_leak_coincident_transition": "before/after / switch Δ",
            "measured_pump_noisy_missing": "max|Σ| / converged",
        }.get(r["id"], "result")
        res = r["result"]
        if r["id"] == "measured_pump_matched_transition":
            detail = f"{res['max_abs_sum_m3h']:.4f}"
        elif r["id"] == "measured_pump_leak_stable":
            detail = f"{res['mean_sum_m3h']:.4f}"
        elif r["id"] == "measured_pump_leak_coincident_transition":
            detail = (
                f"{res['mean_sum_before_m3h']:.3f}/{res['mean_sum_after_m3h']:.3f}/"
                f"Δ{res['sum_delta_at_switch_m3h']:.3f}"
            )
        else:
            detail = f"conv={res['converged']} max|Σ|={res['max_abs_sum_m3h']}"
        lines.append(f"| `{r['id']}` | {r['passed']} | {key}={detail} |")
        lines.append("")
        lines.append(f"### `{r['id']}`")
        lines.append("")
        lines.append(r["interpretation"])
        lines.append("")
        lines.append(f"Pass criterion: {r['pass_criterion']}")
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- Does not modify frozen calibration or baseline detection outputs.",
            "- Stop: no 2019 / UI / Tiger / production / main.",
            "",
        ]
    )
    (out_dir / "MEASURED_PUMP_SYNTHETIC_RESULTS.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"all_passed": payload["all_passed"], "n": len(rows)}))
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
