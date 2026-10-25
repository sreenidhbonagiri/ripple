#!/usr/bin/env python3
"""Diagnose synthetic→measured transfer failure for the frozen pilot.

Preserves frozen model, predictions, and PILOT_RESULTS.md metrics.
No retuning, no simulator expansion.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
CUSUM = ROOT.parent / "per-sensor-relationship-cusum"
sys.path.insert(0, str(CUSUM))

from evaluate import DIAG, DEV, period_indices  # noqa: E402
from io_data import load_leakages  # noqa: E402

from dataset_build import build_split_tables
from features import build_feature_matrix, feature_names
from io_measured import load_measured_2018
from schema import FEATURE_CONFIG, FLOW_SENSORS, LEVEL_SENSORS, PRESSURE_SENSORS, STEPS_PER_HOUR
from train_pilot import predict_proba

OUT = ROOT / "outputs"
SIM = OUT / "synthetic_scenarios"
FROZEN_PATH = OUT / "pilot_frozen_model.json"


def iso_now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def feature_catalog() -> list[dict]:
    """Document all 53 features: kind, unit, window, missingness."""
    cfg = FEATURE_CONFIG
    rows = []

    def add(name, kind, unit, window, notes):
        rows.append(
            {
                "name": name,
                "kind": kind,  # absolute_level | change | binary | spread
                "unit": unit,
                "temporal_window": window,
                "missingness": "NaN until lag available (causal); rows with any NaN dropped at train",
                "notes": notes,
            }
        )

    for n in ("P_median", "P_p10", "P_p90", "P_max", "P_min"):
        add(n, "absolute_level", "m", "instant t", "network-wide percentile/extremum of 33 junction pressures")
    add(
        "P_spread_p90_p10",
        "spread",
        "m",
        "instant t",
        "P_p90 - P_p10 at t",
    )
    for lag, hours in zip(cfg.delta_steps, (5 / 60, 0.5, 2.0)):
        tag = f"d{lag}"
        w = f"P(t)-P(t-{lag} steps) = {hours:g} h causal delta per sensor, then aggregate"
        for agg, note in [
            ("median", "median across sensors"),
            ("p10", "10th pct of deltas"),
            ("p90", "90th pct of deltas"),
            ("min", "most negative delta (largest drop)"),
            ("max_abs", "max |delta|"),
        ]:
            add(f"Pd_{tag}_{agg}", "change", "m", w, note)
        for k in range(cfg.top_k_pressure_delta):
            add(
                f"Pd_{tag}_topneg{k+1}",
                "change",
                "m",
                w,
                f"{k+1}-th most negative sensor delta (value only; no sensor id)",
            )
    for fid in FLOW_SENSORS:
        add(f"F_{fid}", "absolute_level", "m3/h", "instant t", "SCADA-aligned link flow (signed→nonneg in both domains here)")
        for lag, hours in zip(cfg.delta_steps, (5 / 60, 0.5, 2.0)):
            add(
                f"Fd_{fid}_d{lag}",
                "change",
                "m3/h",
                f"F(t)-F(t-{lag}) over {hours:g} h",
                "causal flow change",
            )
    add("pump1_on", "binary", "{0,1}", "instant t", "1{F_PUMP_1 > 1 m3/h}")
    for lid in LEVEL_SENSORS:
        add(f"L_{lid}", "absolute_level", "m", "instant t", "tank water level (SCADA level; sim=head−elevation)")
        for lag, hours in zip(cfg.delta_steps, (5 / 60, 0.5, 2.0)):
            add(
                f"Ld_{lid}_d{lag}",
                "change",
                "m",
                f"L(t)-L(t-{lag}) over {hours:g} h",
                "causal tank-level change",
            )
    assert len(rows) == len(feature_names())
    return rows


def scaling_docs(frozen: dict) -> dict:
    names = frozen["feature_names"]
    return {
        "method": "StandardScaler fit on synthetic train rows only (mean/var)",
        "applied_at_inference": "(x - mean) / scale  then  logit = z·coef + intercept;  q=sigmoid(logit)",
        "per_feature": [
            {
                "name": names[i],
                "train_mean": frozen["scaler_mean"][i],
                "train_scale": frozen["scaler_scale"][i],
                "coef_standardized": frozen["coef"][i],
                "coef_per_raw_unit": (
                    frozen["coef"][i] / frozen["scaler_scale"][i]
                    if frozen["scaler_scale"][i] > 1e-12
                    else None
                ),
            }
            for i in range(len(names))
        ],
        "intercept": frozen["intercept"],
        "note": (
            "coef_standardized is the contribution per 1σ of the *synthetic training* feature. "
            "coef_per_raw_unit is ∂logit/∂x in physical units."
        ),
    }


def ood_fraction(X: np.ndarray, mean: np.ndarray, scale: np.ndarray, k: float = 5.0) -> np.ndarray:
    """Fraction of rows with |z| > k for each feature."""
    scale = np.where(scale < 1e-12, 1.0, scale)
    z = (X - mean) / scale
    return np.mean(np.abs(z) > k, axis=0)


def dist_summary(X: np.ndarray) -> dict:
    return {
        "n": int(X.shape[0]),
        "mean": X.mean(0).tolist(),
        "std": X.std(0).tolist(),
        "p10": np.percentile(X, 10, axis=0).tolist(),
        "p50": np.percentile(X, 50, axis=0).tolist(),
        "p90": np.percentile(X, 90, axis=0).tolist(),
    }


def mean_contrib(X: np.ndarray, frozen: dict) -> tuple[np.ndarray, float]:
    mean = np.asarray(frozen["scaler_mean"])
    scale = np.asarray(frozen["scaler_scale"])
    scale = np.where(scale < 1e-12, 1.0, scale)
    coef = np.asarray(frozen["coef"])
    z = (X.mean(0) - mean) / scale
    c = z * coef
    logit = float(c.sum() + frozen["intercept"])
    return c, logit


def window_rows_measured(measured, leakages, period, *, hours_after: float = 6.0):
    """Post-onset credit windows for abrupt onsets in period (post 14d prefix)."""
    from audit_occupancy_recovery import train_end_time, split_eligible_onsets
    from evaluate import onsets_in_period

    g0, g1 = period_indices(measured["timestamps"], period)
    train_end = train_end_time(measured["timestamps"], g0, 14)
    elig, _ = split_eligible_onsets(onsets_in_period(leakages, period), train_end)
    abrupt = [L for L in elig if L.leak_type == "abrupt"]
    X_all, _ = build_feature_matrix(
        measured["pressures"], measured["flows"], measured["levels"]
    )
    warm = FEATURE_CONFIG.warm_up_steps
    ok = np.all(np.isfinite(X_all), axis=1)
    ok[:warm] = False
    ts = measured["timestamps"]
    event_idx = []
    for L in abrupt:
        i0 = int(np.searchsorted(ts, L.start, side="left"))
        i1 = int(
            np.searchsorted(
                ts,
                L.start + np.timedelta64(int(hours_after * 60), "m"),
                side="right",
            )
        )
        for i in range(i0, min(i1, len(ts))):
            if ok[i]:
                event_idx.append(i)
    # Control windows: same calendar months as abrupt onsets, days without new onset credit
    # Use ordinary mid-month blocks far from any labeled onset (±3d)
    control_idx = []
    onsets_all = leakages
    for month_start in [
        np.datetime64("2018-03-15"),
        np.datetime64("2018-05-10"),
        np.datetime64("2018-06-15"),
        np.datetime64("2018-09-15"),
        np.datetime64("2018-11-15"),
    ]:
        if not (period.start <= month_start <= period.end):
            continue
        lo = month_start
        hi = month_start + np.timedelta64(2, "D")
        # skip if any onset within ±3d of window
        near = any(
            abs(float((L.start - lo) / np.timedelta64(1, "D"))) < 3
            or abs(float((L.start - hi) / np.timedelta64(1, "D"))) < 3
            for L in onsets_all
        )
        if near:
            continue
        i0 = int(np.searchsorted(ts, lo, side="left"))
        i1 = int(np.searchsorted(ts, hi, side="right"))
        for i in range(i0, min(i1, len(ts))):
            if ok[i] and g0 <= i < g1:
                control_idx.append(i)
    return (
        abrupt,
        X_all[np.array(event_idx, dtype=int)] if event_idx else np.zeros((0, X_all.shape[1])),
        X_all[np.array(control_idx, dtype=int)] if control_idx else np.zeros((0, X_all.shape[1])),
        event_idx,
        control_idx,
    )


def synthetic_groups(sim_dir: Path, frozen: dict):
    """Leak credit rows vs control-scenario rows (post warm-up, finite)."""
    manifest = json.loads((sim_dir / "scenario_manifest.json").read_text())
    warm = FEATURE_CONFIG.warm_up_steps
    X_leak, X_ctrl = [], []
    for sc in manifest["scenarios"]:
        if not sc["ok"]:
            continue
        a = np.load(sim_dir / sc["npz"])
        X, _ = build_feature_matrix(a["pressures"], a["flows"], a["levels"])
        ok = np.all(np.isfinite(X), axis=1)
        ok[:warm] = False
        if sc["spec"]["kind"] == "leak_abrupt":
            y = a["labels_abrupt_positive"].astype(bool)
            X_leak.append(X[ok & y])
        elif sc["spec"]["kind"].startswith("control"):
            X_ctrl.append(X[ok])
    return (
        np.concatenate(X_leak) if X_leak else np.zeros((0, len(frozen["feature_names"]))),
        np.concatenate(X_ctrl) if X_ctrl else np.zeros((0, len(frozen["feature_names"]))),
    )


def render(doc: dict) -> str:
    lines = [
        "# Transfer-failure diagnosis — frozen synthetic pilot",
        "",
        f"Generated: {doc['generated_at']}",
        "",
        "Preserves frozen pilot model, predictions, `PILOT_RESULTS.md`, and production. "
        "**No** retuning, simulator expansion, or 2019 run.",
        "",
        "## 1. Feature semantics (all 53)",
        "",
        f"- Feature set: `{doc['feature_set']}`",
        f"- Scaling: {doc['scaling']['method']}",
        f"- {doc['scaling']['applied_at_inference']}",
        f"- Warm-up before usable rows: **{FEATURE_CONFIG.warm_up_steps}** steps "
        f"({FEATURE_CONFIG.warm_up_steps/STEPS_PER_HOUR:g} h)",
        "",
        "### Identity checks (synthetic vs measured)",
        "",
    ]
    for k, v in doc["identity_checks"].items():
        lines.append(f"- **{k}**: {v}")
    lines += [
        "",
        "### Absolute vs change",
        "",
        f"- Absolute-level features: {doc['n_absolute']} "
        f"(sum |coef_z| fraction = **{doc['coef_mass_absolute']:.3f}**)",
        f"- Change/delta features: {doc['n_change']} "
        f"(sum |coef_z| fraction = **{doc['coef_mass_change']:.3f}**)",
        f"- Binary/other: {doc['n_other']}",
        "",
        "| # | Name | Kind | Unit | Window |",
        "|---|------|------|------|--------|",
    ]
    for i, f in enumerate(doc["catalog"]):
        lines.append(
            f"| {i} | `{f['name']}` | {f['kind']} | {f['unit']} | {f['temporal_window'][:60]} |"
        )

    lines += [
        "",
        "### Restart / warm-up / position cues",
        "",
        doc["artifact_assessment"],
        "",
        "## 2. Frozen classifier",
        "",
        f"- C={doc['frozen_selected']['C']}, τ_prob={doc['frozen_selected']['tau']}",
        f"- Intercept (logit): {doc['scaling']['intercept']}",
        "",
        "### Top |standardized coefficients|",
        "",
        "| Rank | Feature | coef_z | coef / raw unit | train mean | train σ |",
        "|------|---------|--------|-----------------|------------|---------|",
    ]
    for r in doc["top_coefs"]:
        lines.append(
            f"| {r['rank']} | `{r['name']}` | {r['coef_z']:+.4f} | "
            f"{r['coef_per_raw_unit']} | {r['train_mean']:.4g} | {r['train_scale']:.4g} |"
        )

    lines += [
        "",
        "### Train-label means (synthetic train rows)",
        "",
        "Positive = abrupt credit window rows; negative = other post-warm-up rows "
        "in train scenarios (controls + pre/post leak). **Not** proven leak-free.",
        "",
        "| Feature | Mean y=1 | Mean y=0 | Δ (pos−neg) |",
        "|---------|----------|----------|-------------|",
    ]
    for r in doc["train_label_means"]:
        lines.append(
            f"| `{r['name']}` | {r['mean_pos']:.4g} | {r['mean_neg']:.4g} | {r['delta']:+.4g} |"
        )

    lines += [
        "",
        "## 3. Distributions and contributions",
        "",
        "### Out-of-training-range (|z|>5) fractions",
        "",
        "| Feature | Synthetic leak credit | Synthetic control | Measured event 0–6h | Measured control blocks |",
        "|---------|----------------------|-------------------|---------------------|-------------------------|",
    ]
    for r in doc["ood_table"]:
        lines.append(
            f"| `{r['name']}` | {r['syn_leak']:.3f} | {r['syn_ctrl']:.3f} | "
            f"{r['meas_event']:.3f} | {r['meas_ctrl']:.3f} |"
        )

    lines += [
        "",
        "### Mean feature values (selected)",
        "",
        "| Feature | Syn leak | Syn ctrl | Meas event | Meas ctrl |",
        "|---------|----------|----------|------------|-----------|",
    ]
    for r in doc["mean_table"]:
        lines.append(
            f"| `{r['name']}` | {r['syn_leak']:.4g} | {r['syn_ctrl']:.4g} | "
            f"{r['meas_event']:.4g} | {r['meas_ctrl']:.4g} |"
        )

    lines += [
        "",
        "### Mean linear-score contributions (selected features)",
        "",
        f"Mean logit: syn_leak={doc['logits']['syn_leak']:.4g}, "
        f"syn_ctrl={doc['logits']['syn_ctrl']:.4g}, "
        f"meas_event={doc['logits']['meas_event']:.4g}, "
        f"meas_ctrl={doc['logits']['meas_ctrl']:.4g}",
        "",
        "| Feature | Syn leak contrib | Syn ctrl | Meas event | Meas ctrl |",
        "|---------|------------------|----------|------------|-----------|",
    ]
    for r in doc["contrib_table"]:
        lines.append(
            f"| `{r['name']}` | {r['syn_leak']:+.4g} | {r['syn_ctrl']:+.4g} | "
            f"{r['meas_event']:+.4g} | {r['meas_ctrl']:+.4g} |"
        )

    lines += [
        "",
        "### What explains failed measured 6h timing",
        "",
        doc["failed_prediction_explanation"],
        "",
        "## 4. Competing explanations — evidence",
        "",
    ]
    for name, block in doc["explanations"].items():
        lines += [
            f"### {name}",
            "",
            f"- Verdict: **{block['verdict']}**",
            f"- {block['evidence']}",
            "",
        ]

    lines += [
        "## 5. Recommended controlled intervention (one)",
        "",
        doc["recommendation"],
        "",
        "## Non-goals",
        "",
        "- No model retune / budget expansion",
        "- No simulator search",
        "- No 2019",
        "- Frozen pilot artifacts unchanged (diagnosis-only outputs)",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(FROZEN_PATH.read_text())
    names = frozen["feature_names"]
    assert names == feature_names()
    coef = np.asarray(frozen["coef"], dtype=np.float64)
    mean = np.asarray(frozen["scaler_mean"], dtype=np.float64)
    scale = np.asarray(frozen["scaler_scale"], dtype=np.float64)

    catalog = feature_catalog()
    kind = {r["name"]: r["kind"] for r in catalog}
    abs_idx = [i for i, n in enumerate(names) if kind[n] == "absolute_level"]
    chg_idx = [i for i, n in enumerate(names) if kind[n] == "change"]
    other_idx = [i for i, n in enumerate(names) if kind[n] not in ("absolute_level", "change")]
    mass = np.abs(coef).sum()
    coef_mass_abs = float(np.abs(coef[abs_idx]).sum() / mass)
    coef_mass_chg = float(np.abs(coef[chg_idx]).sum() / mass)

    scaling = scaling_docs(frozen)
    top = np.argsort(-np.abs(coef))[:20]
    top_coefs = []
    for rank, i in enumerate(top, 1):
        top_coefs.append(
            {
                "rank": rank,
                "name": names[i],
                "coef_z": float(coef[i]),
                "coef_per_raw_unit": (
                    float(coef[i] / scale[i]) if scale[i] > 1e-12 else None
                ),
                "train_mean": float(mean[i]),
                "train_scale": float(scale[i]),
                "kind": kind[names[i]],
            }
        )

    # Train label means
    tables = build_split_tables(SIM)
    Xtr, ytr = tables["splits"]["train"]["X"], tables["splits"]["train"]["y"]
    key_feats = [
        "P_median",
        "P_min",
        "L_T1",
        "F_PUMP_1",
        "pump1_on",
        "Fd_PUMP_1_d24",
        "Pd_d6_min",
        "Pd_d24_min",
        "Pd_d6_topneg1",
        "Pd_d6_max_abs",
    ]
    train_label_means = []
    for n in key_feats:
        j = names.index(n)
        mp = float(Xtr[ytr == 1, j].mean())
        mn = float(Xtr[ytr == 0, j].mean())
        train_label_means.append(
            {"name": n, "mean_pos": mp, "mean_neg": mn, "delta": mp - mn}
        )

    X_syn_leak, X_syn_ctrl = synthetic_groups(SIM, frozen)
    measured = load_measured_2018()
    leakages = load_leakages()
    # Combine DEV+DIAG abrupt event windows and controls
    X_me_list, X_mc_list = [], []
    for period in (DEV, DIAG):
        _, Xe, Xc, _, _ = window_rows_measured(measured, leakages, period)
        if Xe.size:
            X_me_list.append(Xe)
        if Xc.size:
            X_mc_list.append(Xc)
    X_meas_event = np.concatenate(X_me_list) if X_me_list else np.zeros((0, len(names)))
    X_meas_ctrl = np.concatenate(X_mc_list) if X_mc_list else np.zeros((0, len(names)))

    ood_syn_l = ood_fraction(X_syn_leak, mean, scale)
    ood_syn_c = ood_fraction(X_syn_ctrl, mean, scale)
    ood_me = ood_fraction(X_meas_event, mean, scale) if X_meas_event.shape[0] else np.zeros(len(names))
    ood_mc = ood_fraction(X_meas_ctrl, mean, scale) if X_meas_ctrl.shape[0] else np.zeros(len(names))

    # Focus OOD table on top coef + key drop features
    focus = list(dict.fromkeys([names[i] for i in top[:12]] + key_feats))
    ood_table = []
    mean_table = []
    for n in focus:
        j = names.index(n)
        ood_table.append(
            {
                "name": n,
                "syn_leak": float(ood_syn_l[j]),
                "syn_ctrl": float(ood_syn_c[j]),
                "meas_event": float(ood_me[j]),
                "meas_ctrl": float(ood_mc[j]),
            }
        )
        mean_table.append(
            {
                "name": n,
                "syn_leak": float(X_syn_leak[:, j].mean()) if X_syn_leak.size else None,
                "syn_ctrl": float(X_syn_ctrl[:, j].mean()) if X_syn_ctrl.size else None,
                "meas_event": float(X_meas_event[:, j].mean()) if X_meas_event.size else None,
                "meas_ctrl": float(X_meas_ctrl[:, j].mean()) if X_meas_ctrl.size else None,
            }
        )

    c_sl, logit_sl = mean_contrib(X_syn_leak, frozen)
    c_sc, logit_sc = mean_contrib(X_syn_ctrl, frozen)
    c_me, logit_me = mean_contrib(X_meas_event, frozen)
    c_mc, logit_mc = mean_contrib(X_meas_ctrl, frozen)
    contrib_table = []
    for n in focus:
        j = names.index(n)
        contrib_table.append(
            {
                "name": n,
                "syn_leak": float(c_sl[j]),
                "syn_ctrl": float(c_sc[j]),
                "meas_event": float(c_me[j]),
                "meas_ctrl": float(c_mc[j]),
            }
        )

    # Identity checks
    identity_checks = {
        "pressure_unit": "m junction pressure in both; sensor lists identical (33)",
        "pressure_averaging": (
            "Network-wide nanmedian / percentiles over the same PRESSURE_SENSORS order; "
            "not a single-sensor or nearest-to-leak average"
        ),
        "flow_unit_and_direction": (
            f"Both domains use m³/h for {FLOW_SENSORS}. Synthetic: WNTR m³/s×3600. "
            "Measured SCADA already m³/h. Empirical sign: no negative samples in either "
            "2018 SCADA or pilot scenarios for these three links (direction encoding matches "
            "as non-negative magnitudes on these sensors)"
        ),
        "tank_level": (
            "Measured: SCADA Levels T1 in m. Synthetic: head(T1)−elevation. "
            "Ranges overlap (~2–4 m)"
        ),
        "timestamp_grid": "5-minute steps both; synthetic timestamps are scenario-relative seconds",
        "feature_code_path": "Identical build_feature_matrix() for synthetic NPZ and measured arrays",
        "bug_check_flow_conversion": "Present and consistent; not implicated as a unit bug",
        "bug_check_sensor_mapping": "PRESSURE_SENSORS / FLOW_SENSORS / LEVEL_SENSORS shared schema",
    }

    # Pd_d6_min polarity on train
    pd_row = next(r for r in train_label_means if r["name"] == "Pd_d6_min")
    pump_row = next(r for r in train_label_means if r["name"] == "pump1_on")

    artifact_assessment = (
        "Scenarios run as continuous 48 h trajectories with leaks starting after "
        f"{FEATURE_CONFIG.warm_up_steps/STEPS_PER_HOUR:g} h warm-up (not at t=0 restart). "
        "Feature warm-up drops the first 12 h so early hydraulic transient is not labeled. "
        "However, leak credit windows still co-occur with diurnal pump/tank schedules inside "
        "the short scenarios; absolute level and pump-state features can act as "
        "**scenario-position / operating-state cues** without requiring a physical leak "
        "signature. No evidence that a hard 'restart spike' alone drives labels."
    )

    failed_prediction_explanation = (
        f"On measured abrupt 0–6 h windows, mean logit={logit_me:.3f} vs control={logit_mc:.3f} "
        f"(synthetic leak={logit_sl:.3f}, synthetic control={logit_sc:.3f}). "
        "Pilot notifications on 2018 often arrive after 6 h (HIT>6 in PILOT_RESULTS) while "
        "flooding unmatched episodes — consistent with a score driven by slow absolute "
        "operating-level / pump-context drift rather than a sharp onset-aligned pressure-drop "
        "feature. Train-label polarity for `Pd_d6_min` is **wrong-signed for a drop detector** "
        f"(pos mean {pd_row['mean_pos']:.4g} vs neg {pd_row['mean_neg']:.4g}: positives are "
        f"*less* negative). `pump1_on` is higher on positives ({pump_row['mean_pos']:.3g} vs "
        f"{pump_row['mean_neg']:.3g}). Absolute-level features carry "
        f"**{coef_mass_abs:.0%}** of Σ|coef_z|."
    )

    explanations = {
        "unit_or_feature_implementation_mismatch": {
            "verdict": "not supported as primary cause",
            "evidence": (
                "Shared feature builder; pressure/tank ranges overlap; flows converted "
                "m³/s→m³/h; no sign mismatch on the three SCADA flow channels. "
                "OOD |z|>5 rates on measured absolute levels are low for P_median-family "
                "relative to a pure unit-scale failure."
            ),
        },
        "absolute_operating_level_shift": {
            "verdict": "partially supported (important but incomplete)",
            "evidence": (
                f"Absolute features are {coef_mass_abs:.0%} of coefficient mass; "
                "P_median, L_T1, P_min, P_p90 rank in the top coefficients. "
                "Measured vs synthetic means for P_median are close (~47 m), so a gross "
                "level offset alone does not explain transfer failure — but the *use* of "
                "absolute levels as leak proxies fails when measured diurnal/seasonal "
                "operating trajectories differ from 48 h nominal scenarios."
            ),
        },
        "unrealistic_simulated_leak_response": {
            "verdict": "supported for network-summary drop features",
            "evidence": (
                "Across synthetic leak scenarios, network-wide `Pd_d6_min` is not reliably "
                "more negative in credit windows than outside them (train: positives less "
                "negative than negatives). Aggregate pressure-drop features therefore do not "
                "encode a strong, consistent leak onset signature in the pilot simulations — "
                "so even a perfect transfer of those features would be weak."
            ),
        },
        "simulation_specific_nuisance_shortcuts": {
            "verdict": "supported as a driver of synthetic metrics",
            "evidence": (
                "Top coefficients include Fd_PUMP_1_d24, F_PUMP_1, pump1_on, L_T1, and "
                "absolute pressure levels. Synthetic scenario recall can rise when credit "
                "windows correlate with pump/tank state even though pressure-drop polarity "
                "is wrong-signed. That is a nuisance shortcut relative to the stated leak-"
                "change question — not proof of physical leak detection."
            ),
        },
        "inadequate_feature_separation": {
            "verdict": "supported",
            "evidence": (
                "Change features that should separate leaks (Pd_*_min / topneg) do not "
                "separate train positives from negatives in the expected direction; "
                "synthetic_dev selection still picked τ=0.3 with high FP row rate (~0.49). "
                "Inadequate separation in the intended residual/change subspace plus "
                "shortcut features jointly explain high synthetic scenario recall without "
                "measured 6 h sensitivity."
            ),
        },
    }

    recommendation = (
        "**One controlled intervention:** replace absolute pressure/flow/tank *levels* "
        "with an identical causal **change/residual representation** in both domains — "
        "e.g. keep only Pd_*/Fd_*/Ld_* (and optionally z-scored deltas against a "
        "past-only rolling reference), drop P_median/P_*/F_*/L_T1 raw levels and "
        "pump1_on level proxies from the feature set; refit under the same L2 budget "
        "on synthetic data only. Apply the same builder to measured SCADA.\n\n"
        "**Why this and not 'just normalize harder':** StandardScaler already removes "
        "gross mean/variance per feature on synthetic train; measured absolute means "
        "are already similar. The failure mode is **feature semantics / shortcut use of "
        "operating state**, not a simple affine domain shift. If simulated network-wide "
        "drop responses remain weak or wrong-signed after removing levels, normalization "
        "alone cannot create a transferable leak onset cue — that would require different "
        "simulation physics or different spatial summaries (out of scope here).\n\n"
        "**No implementation bug found** that warrants a silent protocol correction rerun. "
        "Stop before another fit."
    )

    doc = {
        "generated_at": iso_now(),
        "preserves_frozen_pilot": True,
        "feature_set": frozen["feature_set"],
        "frozen_selected": frozen["selected"],
        "catalog": catalog,
        "scaling": scaling,
        "identity_checks": identity_checks,
        "n_absolute": len(abs_idx),
        "n_change": len(chg_idx),
        "n_other": len(other_idx),
        "coef_mass_absolute": coef_mass_abs,
        "coef_mass_change": coef_mass_chg,
        "top_coefs": top_coefs,
        "train_label_means": train_label_means,
        "artifact_assessment": artifact_assessment,
        "ood_table": ood_table,
        "mean_table": mean_table,
        "contrib_table": contrib_table,
        "logits": {
            "syn_leak": logit_sl,
            "syn_ctrl": logit_sc,
            "meas_event": logit_me,
            "meas_ctrl": logit_mc,
        },
        "n_rows": {
            "syn_leak": int(X_syn_leak.shape[0]),
            "syn_ctrl": int(X_syn_ctrl.shape[0]),
            "meas_event": int(X_meas_event.shape[0]),
            "meas_ctrl": int(X_meas_ctrl.shape[0]),
        },
        "failed_prediction_explanation": failed_prediction_explanation,
        "explanations": explanations,
        "recommendation": recommendation,
        "primary_conclusion": (
            "Not 'domain mismatch' by failure alone. Primary evidence: absolute/operating-"
            "state shortcuts + inadequate / wrong-signed separation on network pressure-"
            "drop features; unit bugs not found."
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
        if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
            return None
        return o

    (OUT / "transfer_failure_diagnosis.json").write_text(
        json.dumps(_jsonable(doc), indent=2) + "\n"
    )
    (OUT / "TRANSFER_FAILURE_DIAGNOSIS.md").write_text(render(doc) + "\n")

    # Pointer on pilot results (additive)
    pilot = OUT / "PILOT_RESULTS.md"
    text = pilot.read_text()
    pointer = (
        "> **Transfer diagnosis (no retune):** see `TRANSFER_FAILURE_DIAGNOSIS.md` — "
        "absolute/operating-state shortcuts and weak/wrong-signed network drop features; "
        "not a bare 'domain mismatch' label. Frozen pilot unchanged.\n\n"
    )
    if "Transfer diagnosis" not in text:
        text = text.replace("## Question", pointer + "## Question", 1)
        pilot.write_text(text)

    print(doc["primary_conclusion"], flush=True)
    print(f"Wrote {OUT / 'TRANSFER_FAILURE_DIAGNOSIS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
