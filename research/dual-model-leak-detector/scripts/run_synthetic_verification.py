#!/usr/bin/env python3
"""Run synthetic dual-model mechanism verification (stages 1–2).

Does not touch measured 2018/2019 SCADA, calibration, or detection evaluation.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.scenarios import run_all_scenarios  # noqa: E402


def main() -> int:
    scratch = ROOT / "outputs" / "synthetic" / "_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    results = run_all_scenarios(scratch)

    out_dir = ROOT / "outputs" / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "1_solver_and_2_synthetic_verification",
        "n_scenarios": len(results),
        "n_passed": sum(1 for r in results if r.get("passed")),
        "scenarios": results,
    }
    json_path = out_dir / "verification_results.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")

    md_lines = [
        "# Synthetic dual-model verification results",
        "",
        f"Generated: `{payload['generated_at_utc']}`",
        "",
        f"Passed **{payload['n_passed']}/{payload['n_scenarios']}** scenario checks.",
        "",
        "| ID | Passed | Actual leak (m³/h) | sum q_v (m³/h) | Distinguishes? |",
        "|----|--------|--------------------:|---------------:|----------------|",
    ]
    for r in results:
        res = r.get("result", {})
        if "sum_m3h" in res:
            s = f"{res['sum_m3h']:.4f}"
        elif "max_abs_sum_m3h" in res:
            s = f"max|Σ|={res['max_abs_sum_m3h']:.4f}"
        else:
            s = "—"
        dist = r.get("distinguishes_leak")
        dist_s = {True: "yes", False: "no (confounder)", None: "n/a"}[dist]
        md_lines.append(
            f"| `{r['id']}` | {'PASS' if r.get('passed') else 'FAIL'} | "
            f"{r.get('actual_leak_m3h', 0):.2f} | {s} | {dist_s} |"
        )

    md_lines.extend(
        [
            "",
            "## Per-scenario interpretation",
            "",
        ]
    )
    for r in results:
        md_lines.append(f"### `{r['id']}`")
        md_lines.append("")
        md_lines.append(r["description"])
        md_lines.append("")
        md_lines.append(r["interpretation"])
        md_lines.append("")
        md_lines.append(f"- Pass criterion: {r['pass_criterion']}")
        md_lines.append(f"- Passed: **{r.get('passed')}**")
        md_lines.append("")

    md_path = out_dir / "SYNTHETIC_VERIFICATION_RESULTS.md"
    md_path.write_text("\n".join(md_lines) + "\n")
    print(json.dumps({"json": str(json_path), "md": str(md_path), **{k: payload[k] for k in ('n_passed', 'n_scenarios')}}, indent=2))
    return 0 if payload["n_passed"] == payload["n_scenarios"] else 1


if __name__ == "__main__":
    raise SystemExit(main())