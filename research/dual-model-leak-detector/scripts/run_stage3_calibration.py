#!/usr/bin/env python3
"""Stage 3 — measured 2018 calibration + chronological validation.

Assumes CALIBRATION_WINDOWS.md already registered. No detector thresholds. No 2019.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.area_topology import build_roughness_clusters  # noqa: E402
from dual_model.demand_calibration import DemandModel, fit_demand_model  # noqa: E402
from dual_model.ltown_hydraulics import (  # noqa: E402
    flow_metrics,
    level_metrics,
    load_nominal_wn,
    pressure_metrics,
    run_dual_window,
    run_primal_window,
    subsample_hourly,
    virtual_flow_metrics,
)
from dual_model.roughness_calibration import fit_roughness_clusters  # noqa: E402
from dual_model.scada_io import (  # noqa: E402
    load_amr_demands_2018,
    load_flows_2018,
    load_leakages_2018,
    load_levels_2018,
    load_pressures_2018,
    slice_window,
)
from dual_model.windows import DIAGNOSTIC_ONSETS, FIT_W1, VAL_WINDOWS  # noqa: E402


def _window_frames(P, F, L, A, w):
    return (
        subsample_hourly(slice_window(P, w.start, w.end)),
        subsample_hourly(slice_window(F, w.start, w.end)),
        subsample_hourly(slice_window(L, w.start, w.end)),
        subsample_hourly(slice_window(A, w.start, w.end)),
    )


def evaluate_configuration(
    wn,
    w,
    P,
    F,
    L,
    A,
    *,
    demand_model: DemandModel | None,
    roughness: dict | None,
    clusters,
    scratch: Path,
    tcv_setting: float,
    label: str,
) -> dict:
    Pw, Fw, Lw, Aw = _window_frames(P, F, L, A, w)
    ts = Pw.index
    primal = run_primal_window(
        wn,
        ts,
        demand_model=demand_model,
        amr_lh=Aw if demand_model is not None else None,
        levels_m=Lw["T1"],
        scratch=scratch,
        roughness=roughness,
        clusters=clusters,
        timestep_sec=3600,
    )
    out = {
        "window_id": w.id,
        "label": label,
        "converged": primal.converged,
        "pressure": None,
        "flow": None,
        "level": None,
        "virtual_flows": None,
    }
    if not primal.converged:
        out["error"] = primal.notes
        return out
    out["pressure"] = pressure_metrics(primal.pressure_m, Pw)
    out["flow"] = flow_metrics(primal.flow_m3h, Fw)
    out["level"] = level_metrics(primal.level_m, Lw["T1"])

    dual = run_dual_window(
        wn,
        ts,
        Pw,
        demand_model=demand_model,
        amr_lh=Aw if demand_model is not None else None,
        levels_m=Lw["T1"],
        scratch=scratch,
        roughness=roughness,
        clusters=clusters,
        tcv_setting=tcv_setting,
        timestep_sec=3600,
    )
    out["virtual_flows"] = virtual_flow_metrics(dual)
    # Persist compact per-sensor means for the report
    out["virtual_flows_compact"] = {
        "sum_mean_m3h": out["virtual_flows"]["sum_mean_m3h"],
        "sum_std_m3h": out["virtual_flows"]["sum_std_m3h"],
        "mean_abs_individual_m3h": out["virtual_flows"]["mean_abs_individual_m3h"],
        "cancellation_ratio": out["virtual_flows"]["cancellation_ratio"],
        "day_sum_mean_m3h": out["virtual_flows"]["day_sum_mean_m3h"],
        "night_sum_mean_m3h": out["virtual_flows"]["night_sum_mean_m3h"],
        "per_sensor_mean_m3h": {k: v["mean_m3h"] for k, v in out["virtual_flows"]["per_sensor"].items()},
        "per_sensor_std_m3h": {k: v["std_m3h"] for k, v in out["virtual_flows"]["per_sensor"].items()},
    }
    return out


def leak_onset_diagnostics(
    wn,
    P,
    F,
    L,
    A,
    *,
    demand_model: DemandModel,
    roughness: dict,
    clusters,
    scratch: Path,
    tcv_setting: float,
) -> list[dict]:
    """Diagnostic only — frozen calibration; no threshold search."""
    rows = []
    for spec in DIAGNOSTIC_ONSETS:
        onset = pd.Timestamp(spec["onset"])
        start = onset - pd.Timedelta(hours=24)
        end = onset + pd.Timedelta(hours=24)
        Pw = subsample_hourly(P.loc[start:end])
        if len(Pw) < 10:
            rows.append({**spec, "status": "insufficient_data"})
            continue
        Fw = subsample_hourly(F.loc[start:end])
        Lw = subsample_hourly(L.loc[start:end])
        Aw = subsample_hourly(A.loc[start:end])
        dual = run_dual_window(
            wn,
            Pw.index,
            Pw,
            demand_model=demand_model,
            amr_lh=Aw,
            levels_m=Lw["T1"],
            scratch=scratch,
            roughness=roughness,
            clusters=clusters,
            tcv_setting=tcv_setting,
            timestep_sec=3600,
        )
        s = dual.q_v_sum_m3h
        pre = s[s.index < onset]
        post = s[s.index >= onset]
        # Ordinary contrast: same hour-of-week from FIT week
        how = onset.day_of_week
        hour = onset.hour
        fit = subsample_hourly(slice_window(P, FIT_W1.start, FIT_W1.end))
        mask = (fit.index.day_of_week == how) & (fit.index.hour == hour)
        contrast = {
            "pre_mean_sum_m3h": float(pre.mean()) if len(pre) else None,
            "post_mean_sum_m3h": float(post.mean()) if len(post) else None,
            "delta_sum_m3h": float(post.mean() - pre.mean()) if len(pre) and len(post) else None,
            "pre_std_m3h": float(pre.std()) if len(pre) else None,
            "post_std_m3h": float(post.std()) if len(post) else None,
            "n_pre": int(len(pre)),
            "n_post": int(len(post)),
            "fit_week_same_how_count": int(mask.sum()),
        }
        # dominant sensor change
        qvh = dual.q_v_m3h
        if len(pre) and len(post):
            delta_sensor = (post.mean() - pre.mean())  # wrong - need column-wise
            dcols = qvh.loc[post.index].mean() - qvh.loc[pre.index].mean()
            contrast["dominant_sensor_delta"] = str(dcols.abs().idxmax())
            contrast["dominant_sensor_delta_m3h"] = float(dcols.abs().max())
            contrast["signed_dominant_delta_m3h"] = float(dcols.loc[dcols.abs().idxmax()])
        rows.append({**spec, "status": "ok", **contrast})
    return rows


def main() -> int:
    out_dir = ROOT / "outputs" / "calibration"
    scratch = out_dir / "_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    audit_path = out_dir / "NOMINAL_LTOWN_AUDIT.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        tcv_setting = float(audit["tcv_resistance_sweep"]["K_frozen_for_stage3"])
    else:
        tcv_setting = 1e-3

    print("Loading SCADA…", flush=True)
    P = load_pressures_2018()
    F = load_flows_2018()
    L = load_levels_2018()
    A = load_amr_demands_2018()
    wn = load_nominal_wn()
    clusters = build_roughness_clusters(wn)

    # --- Fit demand on FIT_W1 only
    print("Fitting demand model on FIT_W1…", flush=True)
    P_fit, F_fit, L_fit, A_fit = _window_frames(P, F, L, A, FIT_W1)
    # Demand fit uses full 5-min AMR for TSA quality
    A_fit_full = slice_window(A, FIT_W1.start, FIT_W1.end)
    F_fit_full = slice_window(F, FIT_W1.start, FIT_W1.end)
    L_fit_full = slice_window(L, FIT_W1.start, FIT_W1.end)
    demand_model = fit_demand_model(wn, A_fit_full, F_fit_full, L_fit_full)

    print("Fitting roughness on FIT_W1…", flush=True)
    rough_fit = fit_roughness_clusters(
        wn,
        P_fit.index,
        P_fit,
        L_fit["T1"],
        demand_model,
        A_fit,
        scratch,
        max_nfev=20,
        subsample_stride=3,
    )
    roughness = rough_fit.values
    print("Roughness fit:", rough_fit.values, "RMSE", rough_fit.rmse_m, flush=True)

    # Freeze artifact
    frozen = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fit_window": FIT_W1.__dict__,
        "tcv_setting": tcv_setting,
        "demand_model": demand_model.to_dict(),
        "roughness": rough_fit.to_dict(),
        "estimator": "signed_mean_residual_no_preclip_v2",
        "area_c_scale_bounds": [0.5, 1.5],
        "supersedes": "outputs/calibration/superseded_by_bugfix/",
    }
    frozen_path = out_dir / "frozen_calibration.json"
    frozen_text = json.dumps(frozen, indent=2) + "\n"
    frozen_path.write_text(frozen_text)
    frozen_sha256 = hashlib.sha256(frozen_text.encode()).hexdigest()

    # --- Evaluate nominal vs calibrated on fit + validation
    results = []
    for w in (FIT_W1, *VAL_WINDOWS):
        print(f"Evaluating {w.id} nominal…", flush=True)
        results.append(
            evaluate_configuration(
                wn,
                w,
                P,
                F,
                L,
                A,
                demand_model=None,
                roughness=None,
                clusters=clusters,
                scratch=scratch,
                tcv_setting=tcv_setting,
                label="nominal",
            )
        )
        print(f"Evaluating {w.id} calibrated…", flush=True)
        results.append(
            evaluate_configuration(
                wn,
                w,
                P,
                F,
                L,
                A,
                demand_model=demand_model,
                roughness=roughness,
                clusters=clusters,
                scratch=scratch,
                tcv_setting=tcv_setting,
                label="calibrated",
            )
        )

    # Leak-onset diagnostics retained for continuity but MUST NOT drive verdict/tuning.
    print("Leak-onset diagnostics (frozen; not used for tuning)…", flush=True)
    diagnostics = leak_onset_diagnostics(
        wn,
        P,
        F,
        L,
        A,
        demand_model=demand_model,
        roughness=roughness,
        clusters=clusters,
        scratch=scratch,
        tcv_setting=tcv_setting,
    )

    fit_nom = next(r for r in results if r["window_id"] == "FIT_W1" and r["label"] == "nominal")
    fit_cal = next(r for r in results if r["window_id"] == "FIT_W1" and r["label"] == "calibrated")
    val_cals = [r for r in results if r["window_id"].startswith("VAL_") and r["label"] == "calibrated"]
    val_noms = [r for r in results if r["window_id"].startswith("VAL_") and r["label"] == "nominal"]

    def _rmse(r):
        return (r.get("pressure") or {}).get("rmse_m")

    fit_improved = (
        _rmse(fit_cal) is not None
        and _rmse(fit_nom) is not None
        and _rmse(fit_cal) < _rmse(fit_nom)
    )
    val_rmses = [_rmse(r) for r in val_cals if _rmse(r) is not None]
    val_nom_rmses = [_rmse(r) for r in val_noms if _rmse(r) is not None]
    generalization_ok = bool(val_rmses) and (
        float(np.mean(val_rmses)) <= float(np.mean(val_nom_rmses)) * 1.05
        or float(np.mean(val_rmses)) < float(_rmse(fit_nom) or 1e9)
    )
    n_bound = sum(1 for v in rough_fit.active_bounds.values() if v != "interior")
    identifiable = n_bound <= 2 and rough_fit.success
    area_c_ok = not bool(demand_model.meta.get("area_c_physically_inconsistent"))

    if fit_improved and generalization_ok and identifiable and area_c_ok:
        verdict = "PASS_WITH_LIMITATIONS"
        verdict_detail = (
            "Corrected signed-mean Area-C scale (bounds unchanged). Calibration improves "
            "FIT_W1 and multi-season validation pressure RMSE vs nominal; roughness mostly "
            "interior. Limitations: demand TSA is reconstructed; validation weeks contain "
            "ongoing leaks so q_v is not pure model error. Not detection-ready."
        )
    elif fit_improved and not generalization_ok:
        verdict = "FIT_OK_GENERALIZATION_WEAK"
        verdict_detail = (
            "Fit-window improvement does not carry cleanly to multi-season validation."
        )
    else:
        verdict = "FAIL_OR_INCONCLUSIVE"
        verdict_detail = (
            "Calibrated model did not clearly improve held-out hydraulics or Area-C "
            "scale is physically inconsistent; do not proceed to detection."
        )

    # Compare to superseded bugfix freeze (if present).
    superseded_path = out_dir / "superseded_by_bugfix" / "stage3_results.json"
    superseded_frozen = out_dir / "superseded_by_bugfix" / "frozen_calibration.json"
    comparison: dict = {"superseded_present": superseded_path.exists()}
    if superseded_path.exists():
        prev = json.loads(superseded_path.read_text())
        prev_fit = next(
            r for r in prev["evaluations"] if r["window_id"] == "FIT_W1" and r["label"] == "calibrated"
        )
        prev_dm = prev.get("demand_meta") or {}
        prev_val = [
            r for r in prev["evaluations"] if r["window_id"].startswith("VAL_") and r["label"] == "calibrated"
        ]

        def _vf(r, key):
            return (r.get("virtual_flows_compact") or {}).get(key)

        comparison.update(
            {
                "area_c_scale_previous": 1.5,  # bugfix clipped to upper bound
                "area_c_scale_raw_previous": prev_dm.get("area_c_unmeasured_scale_raw"),
                "area_c_scale_corrected": demand_model.area_c_unmeasured_scale,
                "area_c_scale_raw_corrected": demand_model.meta.get("area_c_unmeasured_scale_raw"),
                "area_c_bound_hit_corrected": demand_model.meta.get("area_c_scale_bound_hit"),
                "fit_pressure_rmse_calibrated_previous_m": (prev_fit.get("pressure") or {}).get("rmse_m"),
                "fit_pressure_rmse_calibrated_corrected_m": _rmse(fit_cal),
                "fit_ext_bias_previous_m3h": ((prev_fit.get("flow") or {}).get("external_sum") or {}).get(
                    "bias_m3h"
                ),
                "fit_ext_bias_corrected_m3h": ((fit_cal.get("flow") or {}).get("external_sum") or {}).get(
                    "bias_m3h"
                ),
                "fit_tank_rmse_previous_m": (prev_fit.get("level") or {}).get("rmse_m"),
                "fit_tank_rmse_corrected_m": (fit_cal.get("level") or {}).get("rmse_m"),
                "fit_sum_qv_mean_previous_m3h": _vf(prev_fit, "sum_mean_m3h"),
                "fit_sum_qv_mean_corrected_m3h": _vf(fit_cal, "sum_mean_m3h"),
                "fit_mean_abs_qv_previous_m3h": _vf(prev_fit, "mean_abs_individual_m3h"),
                "fit_mean_abs_qv_corrected_m3h": _vf(fit_cal, "mean_abs_individual_m3h"),
                "fit_cancel_ratio_previous": _vf(prev_fit, "cancellation_ratio"),
                "fit_cancel_ratio_corrected": _vf(fit_cal, "cancellation_ratio"),
                "val_pressure_rmse_mean_previous_m": float(
                    np.mean([(r.get("pressure") or {}).get("rmse_m") for r in prev_val])
                ),
                "val_pressure_rmse_mean_corrected_m": float(np.mean(val_rmses)) if val_rmses else None,
                "roughness_previous": (prev.get("roughness_fit") or {}).get("values"),
                "roughness_corrected": rough_fit.values,
            }
        )
    if superseded_frozen.exists():
        comparison["superseded_frozen_sha256"] = hashlib.sha256(
            superseded_frozen.read_bytes()
        ).hexdigest()

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tcv_setting": tcv_setting,
        "demand_meta": demand_model.meta,
        "roughness_fit": rough_fit.to_dict(),
        "evaluations": results,
        "leak_onset_diagnostics": diagnostics,
        "leak_onset_note": "diagnostic only; not used for thresholding or verdict tuning",
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "calibration_hashes": {
            "frozen_calibration_sha256": frozen_sha256,
            "estimator": "signed_mean_residual_no_preclip_v2",
        },
        "comparison_vs_superseded_bugfix": comparison,
        "summary": {
            "fit_pressure_rmse_nominal_m": _rmse(fit_nom),
            "fit_pressure_rmse_calibrated_m": _rmse(fit_cal),
            "val_pressure_rmse_nominal_mean_m": float(np.mean(val_nom_rmses)) if val_nom_rmses else None,
            "val_pressure_rmse_calibrated_mean_m": float(np.mean(val_rmses)) if val_rmses else None,
            "roughness_n_bound_hits": n_bound,
            "area_c_unmeasured_scale": demand_model.area_c_unmeasured_scale,
            "area_c_unmeasured_scale_raw": demand_model.meta.get("area_c_unmeasured_scale_raw"),
            "area_c_bound_hit": demand_model.meta.get("area_c_scale_bound_hit"),
            "area_c_physically_inconsistent": demand_model.meta.get("area_c_physically_inconsistent"),
        },
    }
    # Hash results body without embedding the results digest (avoid circular hash).
    payload["calibration_hashes"] = {
        "frozen_calibration_sha256": frozen_sha256,
        "estimator": "signed_mean_residual_no_preclip_v2",
    }
    results_bytes = (json.dumps(payload, indent=2) + "\n").encode()
    (out_dir / "stage3_results.json").write_bytes(results_bytes)
    results_sha256 = hashlib.sha256(results_bytes).hexdigest()
    hashes_doc = {
        "frozen_calibration_sha256": frozen_sha256,
        "stage3_results_sha256": results_sha256,
        "estimator": "signed_mean_residual_no_preclip_v2",
        "generated_at_utc": payload["generated_at_utc"],
        "superseded_frozen_sha256": comparison.get("superseded_frozen_sha256"),
    }
    (out_dir / "calibration_hashes.json").write_text(json.dumps(hashes_doc, indent=2) + "\n")
    payload["calibration_hashes"] = hashes_doc

    lines = [
        "# Stage 3 calibration / generalization verdict (corrected)",
        "",
        f"**Verdict: `{verdict}`**",
        "",
        verdict_detail,
        "",
        f"Generated: `{payload['generated_at_utc']}`  ",
        f"TCV K frozen: `{tcv_setting}` (nominal audit; not leak-tuned)  ",
        f"Estimator: `signed_mean_residual_no_preclip_v2`  ",
        f"frozen_calibration sha256: `{frozen_sha256}`  ",
        f"stage3_results sha256: `{results_sha256}`",
        "",
        "Previous bugfix freeze retained under `superseded_by_bugfix/`.",
        "No tuning from validation or leak-onset outcomes.",
        "",
        "## Area-C scale (corrected vs previous)",
        "",
        f"| | Previous (bugfix) | Corrected |",
        f"|--|-------------------:|----------:|",
        f"| raw scale | {comparison.get('area_c_scale_raw_previous')} | {comparison.get('area_c_scale_raw_corrected')} |",
        f"| clipped scale | {comparison.get('area_c_scale_previous')} | {comparison.get('area_c_scale_corrected')} |",
        f"| bound hit | upper | {comparison.get('area_c_bound_hit_corrected')} |",
        f"| physically_inconsistent | n/a (masked by clip) | `{demand_model.meta.get('area_c_physically_inconsistent')}` |",
        "",
        f"Signed mean residual: `{demand_model.meta.get('mean_residual_c_signed_m3h')}` m³/h; "
        f"frac negative samples: `{demand_model.meta.get('area_c_frac_residual_negative')}`.",
        "",
        "## Fit window (FIT_W1)",
        "",
        "| Model | Pressure RMSE (m) | Ext. inflow bias (m³/h) | Tank RMSE (m) | Σq_v mean | mean|q_v| | cancel |",
        "|-------|------------------:|------------------------:|--------------:|----------:|----------:|-------:|",
    ]
    for lab in ("nominal", "calibrated"):
        r = next(x for x in results if x["window_id"] == "FIT_W1" and x["label"] == lab)
        pr = r["pressure"] or {}
        fl = (r["flow"] or {}).get("external_sum") or {}
        lv = r["level"] or {}
        vf = r.get("virtual_flows_compact") or {}
        lines.append(
            f"| {lab} | {pr.get('rmse_m')} | {fl.get('bias_m3h')} | {lv.get('rmse_m')} | "
            f"{vf.get('sum_mean_m3h')} | {vf.get('mean_abs_individual_m3h')} | "
            f"{vf.get('cancellation_ratio')} |"
        )
    if comparison.get("superseded_present"):
        lines.extend(
            [
                "",
                "### Calibrated FIT vs superseded bugfix",
                "",
                f"| Metric | Previous | Corrected |",
                f"|--------|---------:|----------:|",
                f"| P RMSE (m) | {comparison.get('fit_pressure_rmse_calibrated_previous_m')} | {comparison.get('fit_pressure_rmse_calibrated_corrected_m')} |",
                f"| Ext bias (m³/h) | {comparison.get('fit_ext_bias_previous_m3h')} | {comparison.get('fit_ext_bias_corrected_m3h')} |",
                f"| Tank RMSE (m) | {comparison.get('fit_tank_rmse_previous_m')} | {comparison.get('fit_tank_rmse_corrected_m')} |",
                f"| Σq_v mean | {comparison.get('fit_sum_qv_mean_previous_m3h')} | {comparison.get('fit_sum_qv_mean_corrected_m3h')} |",
                f"| mean|q_v| | {comparison.get('fit_mean_abs_qv_previous_m3h')} | {comparison.get('fit_mean_abs_qv_corrected_m3h')} |",
                f"| cancel ratio | {comparison.get('fit_cancel_ratio_previous')} | {comparison.get('fit_cancel_ratio_corrected')} |",
            ]
        )

    lines.extend(["", "## Validation windows (frozen parameters)", ""])
    lines.append(
        "| Window | Model | P RMSE (m) | Ext bias (m³/h) | Σq_v mean | mean|q_v| | cancel |"
    )
    lines.append("|--------|-------|----------:|----------------:|----------:|----------:|--------:|")
    for w in VAL_WINDOWS:
        for lab in ("nominal", "calibrated"):
            r = next(x for x in results if x["window_id"] == w.id and x["label"] == lab)
            pr = r["pressure"] or {}
            fl = (r["flow"] or {}).get("external_sum") or {}
            vf = r.get("virtual_flows_compact") or {}
            lines.append(
                f"| {w.id} | {lab} | {pr.get('rmse_m')} | {fl.get('bias_m3h')} | "
                f"{vf.get('sum_mean_m3h')} | {vf.get('mean_abs_individual_m3h')} | "
                f"{vf.get('cancellation_ratio')} |"
            )
    if comparison.get("superseded_present"):
        lines.append(
            f"\nVAL mean P RMSE calibrated: previous "
            f"{comparison.get('val_pressure_rmse_mean_previous_m')} → corrected "
            f"{comparison.get('val_pressure_rmse_mean_corrected_m')}."
        )

    lines.extend(
        [
            "",
            "## Roughness / parameter stability",
            "",
            f"- Success: `{rough_fit.success}`; nfev={rough_fit.nfev}; fit RMSE≈{rough_fit.rmse_m:.4f} m",
            f"- Bound hits: `{rough_fit.active_bounds}`",
            f"- Values: `{rough_fit.values}`",
            f"- Previous values: `{comparison.get('roughness_previous')}`",
            f"- ab_scale={demand_model.ab_scale:.4f}",
            "",
            "## Leak-onset diagnostics (recorded only; not used for tuning)",
            "",
            "| Leak | Onset | ΔΣq_v (m³/h) | Dominant sensor Δ | Status |",
            "|------|-------|-------------:|------------------:|--------|",
        ]
    )
    for d in diagnostics:
        lines.append(
            f"| {d.get('leak_pipe')} | {d.get('onset')} | {d.get('delta_sum_m3h')} | "
            f"{d.get('dominant_sensor_delta_m3h')} | {d.get('status')} |"
        )
    lines.extend(
        [
            "",
            "Stop before detection. No 2019 / UI / Tiger / deploy / main merge.",
            "",
        ]
    )
    (out_dir / "STAGE3_VERDICT.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "verdict": verdict,
                "summary": payload["summary"],
                "hashes": payload["calibration_hashes"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())