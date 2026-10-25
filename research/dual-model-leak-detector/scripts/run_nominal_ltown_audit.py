#!/usr/bin/env python3
"""Stage 3.1 — nominal L-Town dual-solver audit (before calibration).

Does not select TCV resistance using leak-detection outcomes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.area_topology import (  # noqa: E402
    area_b_junctions,
    area_c_junctions,
    build_roughness_clusters,
    load_amr_nodes,
    load_pressure_sensors,
)
from dual_model.dual_builder import DualModelSpec, attach_virtual_reservoirs, sensor_elevations  # noqa: E402
from dual_model.ltown_hydraulics import clone_wn, load_nominal_wn  # noqa: E402
from dual_model.scada_io import load_flows_2018, load_levels_2018, load_pressures_2018  # noqa: E402
from dual_model.simulate import _extract_qv  # noqa: E402
from dual_model.windows import FIT_W1  # noqa: E402
import wntr  # noqa: E402


def main() -> int:
    out_dir = ROOT / "outputs" / "calibration"
    scratch = out_dir / "_scratch_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    wn = load_nominal_wn()
    sensors = load_pressure_sensors()
    amrs = load_amr_nodes()
    ac = area_c_junctions(wn)
    ab = area_b_junctions(wn)
    clusters = build_roughness_clusters(wn)

    elev = sensor_elevations(wn, sensors)
    P = load_pressures_2018()
    F = load_flows_2018()
    L = load_levels_2018()
    # Snapshot: first hour of FIT week
    t0 = pd.Timestamp(FIT_W1.start)
    P0 = P.loc[t0, list(sensors)].astype(float)
    heads = {s: float(P0[s] + elev[s]) for s in sensors}

    # --- Sensor mapping audit
    missing_sensors = [s for s in sensors if s not in wn.node_name_list]
    amr_outside_c = sorted(set(amrs) - ac)

    # --- Nominal primal short run (1 h)
    wn_p = clone_wn(wn, scratch)
    wn_p.options.time.duration = 3600
    wn_p.options.time.hydraulic_timestep = 300
    wn_p.options.time.report_timestep = 300
    tank = wn_p.get_node("T1")
    tank.init_level = float(L.loc[t0, "T1"])
    res_p = wntr.sim.EpanetSimulator(wn_p).run_sim()
    P_sim = res_p.node["pressure"].iloc[0]
    press_err = {s: float(P_sim[s] - P0[s]) for s in sensors}
    flow_err = {
        "p227_m3h": float(res_p.link["flowrate"].iloc[0]["p227"] * 3600 - F.loc[t0, "p227"]),
        "p235_m3h": float(res_p.link["flowrate"].iloc[0]["p235"] * 3600 - F.loc[t0, "p235"]),
        "PUMP_1_m3h": float(res_p.link["flowrate"].iloc[0]["PUMP_1"] * 3600 - F.loc[t0, "PUMP_1"]),
        "external_sum_err_m3h": float(
            (res_p.link["flowrate"].iloc[0]["p227"] + res_p.link["flowrate"].iloc[0]["p235"]) * 3600
            - (F.loc[t0, "p227"] + F.loc[t0, "p235"])
        ),
    }
    level_err = float(res_p.node["pressure"].iloc[0]["T1"] - L.loc[t0, "T1"])

    # --- Dual with measured heads; nominal demands; K sweep (leak-free snapshot criterion)
    K_grid = [1e-4, 1e-3, 1e-2, 1e-1]
    k_rows = []
    for K in K_grid:
        spec = DualModelSpec(sensor_nodes=sensors, tcv_setting=K)
        wd = attach_virtual_reservoirs(wn, spec, heads=heads, scratch_dir=scratch)
        wd.options.time.duration = 0
        wd.options.time.hydraulic_timestep = 3600
        wd.options.time.report_timestep = 3600
        tank = wd.get_node("T1")
        tank.init_level = float(L.loc[t0, "T1"])
        try:
            res_d = wntr.sim.EpanetSimulator(wd).run_sim()
            qv = _extract_qv(res_d.link["flowrate"], spec).iloc[0]
            row = {
                "K": K,
                "converged": True,
                "sum_qv_m3h": float(qv.sum() * 3600),
                "mean_abs_qv_m3h": float(qv.abs().mean() * 3600),
                "max_abs_qv_m3h": float(qv.abs().max() * 3600),
                "n_nan": int(qv.isna().sum()),
            }
        except Exception as exc:  # noqa: BLE001
            row = {"K": K, "converged": False, "error": str(exc)}
        k_rows.append(row)

    # Choose K by numerical criterion only: smallest mean|q_v| among converged
    # with K>=1e-4 (avoid 0). Not leak-detection based.
    ok = [r for r in k_rows if r.get("converged")]
    recommended_K = min(ok, key=lambda r: r["mean_abs_qv_m3h"])["K"] if ok else 1e-3

    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_time": str(t0),
        "sensor_mapping": {
            "n_pressure_sensors": len(sensors),
            "missing_in_inp": missing_sensors,
            "n_amr": len(amrs),
            "amr_outside_area_c": amr_outside_c,
            "n_area_c_junctions": len(ac),
            "n_area_b_junctions": len(ab),
            "flow_roles": {
                "p227": "external inflow R1→network",
                "p235": "external inflow R2→network",
                "PUMP_1": "internal transfer n54→T1 (Area C supply)",
            },
            "head_conversion": "H = P_m + elevation_m (pressure in metres water)",
            "qv_sign": "positive = sensor→VR outflow (virtual leak)",
        },
        "tank_pump": {
            "tank_init_from_SCADA_m": float(L.loc[t0, "T1"]),
            "controls": [str(wn.get_control(c)) for c in wn.control_name_list],
            "level_err_nominal_m": level_err,
        },
        "nominal_primal_snapshot": {
            "pressure_rmse_m": float(np.sqrt(np.mean([e**2 for e in press_err.values()]))),
            "pressure_bias_m": float(np.mean(list(press_err.values()))),
            "flow_errors_m3h": flow_err,
        },
        "roughness_clusters_nominal": {
            cl.name: {"n_pipes": len(cl.pipe_names), "x0": cl.x0} for cl in clusters
        },
        "tcv_resistance_sweep": {
            "criterion": "minimize mean|q_v| on FIT_W1 t0 snapshot with measured heads + nominal model; not leak-detection",
            "grid": k_rows,
            "recommended_K": recommended_K,
            "default_retained_if_close": 1e-3,
            "K_frozen_for_stage3": 1e-3 if abs(recommended_K - 1e-3) / 1e-3 < 5 else recommended_K,
        },
    }
    # Freeze K=1e-3 if within factor 5 of recommended; else use recommended
    audit["tcv_resistance_sweep"]["K_frozen_for_stage3"] = (
        1e-3 if recommended_K in (1e-4, 1e-3, 1e-2) else recommended_K
    )
    # Prefer default 1e-3 when it converges and is competitive
    by_k = {r["K"]: r for r in ok}
    if 1e-3 in by_k and by_k[1e-3]["mean_abs_qv_m3h"] <= 1.5 * min(r["mean_abs_qv_m3h"] for r in ok):
        audit["tcv_resistance_sweep"]["K_frozen_for_stage3"] = 1e-3

    path = out_dir / "NOMINAL_LTOWN_AUDIT.json"
    path.write_text(json.dumps(audit, indent=2) + "\n")
    md = out_dir / "NOMINAL_LTOWN_AUDIT.md"
    md.write_text(
        "\n".join(
            [
                "# Nominal L-Town dual-solver audit",
                "",
                f"Snapshot `{t0}` (start of FIT_W1).",
                "",
                f"- Pressure sensors mapped: **{len(sensors)}**; missing: `{missing_sensors}`",
                f"- AMRs outside Area C: `{amr_outside_c}` (expect none)",
                f"- Nominal pressure RMSE vs SCADA: "
                f"**{audit['nominal_primal_snapshot']['pressure_rmse_m']:.3f} m**",
                f"- External inflow error (p227+p235): "
                f"**{flow_err['external_sum_err_m3h']:.2f} m³/h**",
                f"- Tank level error: **{level_err:.3f} m**",
                f"- TCV K sweep (leak-free snapshot criterion) → freeze "
                f"**K={audit['tcv_resistance_sweep']['K_frozen_for_stage3']}**",
                "",
                "See JSON for per-K rows and cluster sizes.",
                "",
            ]
        )
    )
    print(json.dumps({"audit_json": str(path), "K": audit["tcv_resistance_sweep"]["K_frozen_for_stage3"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())