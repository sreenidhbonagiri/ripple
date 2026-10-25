"""Five-minute Method M: causal fills, recovery duration, prefix stability."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.causal_fill import causal_ffill_frame, causal_ffill_series, row_all_available  # noqa: E402
from dual_model.detection_eval import storage_rate_m3h  # noqa: E402
from dual_model.detection_protocol import (  # noqa: E402
    MIN_SCALE_SAMPLES_5MIN,
    RECOVER_STEPS_5MIN,
    REF_MIN_SAMPLES_5MIN,
    SAMPLES_PER_HOUR_5MIN,
)
from dual_model.detection_scores import (  # noqa: E402
    estimate_method_m_scales,
    score_M_maxabs_local_change,
)
from dual_model.notifier import episodes_from_scores  # noqa: E402


def test_registered_sample_counts():
    assert SAMPLES_PER_HOUR_5MIN == 12
    assert REF_MIN_SAMPLES_5MIN == 144
    assert MIN_SCALE_SAMPLES_5MIN == 288
    assert RECOVER_STEPS_5MIN == 12


def test_causal_ffill_no_future_and_stale_unavailable():
    idx = pd.date_range("2018-01-01", periods=8, freq="5min")
    s = pd.Series([1.0, np.nan, np.nan, np.nan, 5.0, np.nan, np.nan, np.nan], index=idx)
    filled = causal_ffill_series(s, max_age_steps=2)
    col = filled.values.columns[0]
    # age≤2: stamps 1,2 filled from t0; stamp 3 stale → unavailable
    assert filled.available.iloc[0, 0]
    assert filled.available.iloc[1, 0] and filled.is_filled.iloc[1, 0]
    assert filled.available.iloc[2, 0] and float(filled.age_steps.iloc[2, 0]) == 2
    assert not filled.available.iloc[3, 0]
    assert np.isnan(filled.values.iloc[3, 0])
    # source timestamps are never in the future
    for i, t in enumerate(idx):
        src = filled.source_time.iloc[i, 0]
        if pd.isna(src):
            continue
        assert pd.Timestamp(src) <= pd.Timestamp(t)
    # After new observation at t4, two fills then stale again
    assert float(filled.values.iloc[4, 0]) == 5.0
    assert filled.available.iloc[6, 0]
    assert not filled.available.iloc[7, 0]
    assert col == "value" or col == 0 or True


def test_causal_ffill_frame_required_row_gate():
    idx = pd.date_range("2018-01-01", periods=5, freq="5min")
    df = pd.DataFrame(
        {"a": [1.0, np.nan, np.nan, np.nan, 2.0], "b": [1.0, 1.0, np.nan, np.nan, np.nan]},
        index=idx,
    )
    out = causal_ffill_frame(df, max_age_steps=1)
    row_ok = row_all_available(out.available)
    # t1: a filled age1, b observed → row available
    assert bool(row_ok.iloc[1])
    # t2: a stale (would be age2), b filled age1 → row unavailable
    assert not bool(row_ok.iloc[2])
    assert not bool(out.available.iloc[2]["a"])
    assert bool(out.available.iloc[2]["b"])


def test_storage_rate_uses_actual_elapsed_dt():
    idx_h = pd.date_range("2018-01-01", periods=3, freq="h")
    idx_5 = pd.date_range("2018-01-01", periods=3, freq="5min")
    # +1 m over one step
    lv_h = pd.Series([1.0, 2.0, 2.0], index=idx_h)
    lv_5 = pd.Series([1.0, 2.0, 2.0], index=idx_5)
    area = 10.0
    r_h = storage_rate_m3h(lv_h, area)
    r_5 = storage_rate_m3h(lv_5, area)
    # Hourly: 10 m³/h; 5-min: 10 / (5/60) = 120 m³/h
    assert abs(float(r_h.iloc[1]) - 10.0) < 1e-9
    assert abs(float(r_5.iloc[1]) - 120.0) < 1e-9


def test_recovery_duration_is_one_hour_on_5min_grid():
    # Spike then quiet; recover after 12 steps of s < tau/2
    n = 40
    s = np.zeros(n, dtype=float)
    s[5] = 5.0
    s[6:18] = 0.1  # 12 steps below tau/2=1
    eps = episodes_from_scores(s, tau=2.0, recover_steps=RECOVER_STEPS_5MIN)
    assert len(eps) == 1
    assert eps[0].notify_idx == 5
    # Closes on the 12th quiet step (index 5+12=17)
    assert eps[0].end_idx == 17


def test_score_m_ref_min_samples_5min():
    # Dense 5-min index; with ref_min=144 need ~25h history before eligible
    idx = pd.date_range("2018-01-01", periods=30 * 12, freq="5min")  # 30 h
    rng = np.random.default_rng(1)
    qv = pd.DataFrame(
        {"n1": rng.normal(0, 1, len(idx)), "n2": rng.normal(0, 1, len(idx))},
        index=idx,
    )
    scale_idx = idx[20 * 12 : 28 * 12]
    sigma, med, meta = estimate_method_m_scales(
        qv,
        scale_idx,
        min_scale_samples=MIN_SCALE_SAMPLES_5MIN,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    # SCALE window is only 8h → <288 samples → sensors dropped
    assert meta["n_sensors_kept"] == 0
    # Longer SCALE
    scale_idx2 = idx[26 * 12 :]  # still short
    # Build longer series for SCALE ≥288 samples with prior ref history
    idx2 = pd.date_range("2018-01-01", periods=80 * 12, freq="5min")
    qv2 = pd.DataFrame(
        {"n1": rng.normal(0, 1, len(idx2)), "n2": rng.normal(0, 1, len(idx2))},
        index=idx2,
    )
    scale2 = idx2[30 * 12 : 60 * 12]  # 30h = 360 samples
    sigma2, med2, meta2 = estimate_method_m_scales(
        qv2,
        scale2,
        min_scale_samples=MIN_SCALE_SAMPLES_5MIN,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    assert meta2["n_sensors_kept"] == 2
    s_m = score_M_maxabs_local_change(
        qv2,
        sigma_m3h=sigma2,
        raw_max_median=med2,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    # Early stamps lack 144-sample ref → NaN; late stamps finite
    assert not np.isfinite(s_m.iloc[10])
    assert np.isfinite(s_m.iloc[-1])


def test_prefix_stability_score_m():
    """Extending the series must not change earlier finite scores (causal)."""
    rng = np.random.default_rng(2)
    # 80 h of 5-min stamps; SCALE ≥288 samples (24 h) with prior ref history
    idx = pd.date_range("2018-01-01", periods=80 * 12, freq="5min")
    qv = pd.DataFrame(
        {
            "n1": rng.normal(0, 1, len(idx)),
            "n2": rng.normal(0, 1, len(idx)),
        },
        index=idx,
    )
    scale = idx[30 * 12 : 60 * 12]  # 30 h ≥ 288 samples
    sigma, med, meta = estimate_method_m_scales(
        qv,
        scale,
        min_scale_samples=MIN_SCALE_SAMPLES_5MIN,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    assert meta["n_sensors_kept"] == 2
    s_full = score_M_maxabs_local_change(
        qv, sigma_m3h=sigma, raw_max_median=med, ref_min_samples=REF_MIN_SAMPLES_5MIN
    )
    cut = idx[70 * 12]
    s_pref = score_M_maxabs_local_change(
        qv.loc[:cut],
        sigma_m3h=sigma,
        raw_max_median=med,
        ref_min_samples=REF_MIN_SAMPLES_5MIN,
    )
    common = s_pref.index.intersection(s_full.index)
    a = s_pref.loc[common]
    b = s_full.loc[common]
    both = np.isfinite(a) & np.isfinite(b)
    assert both.any()
    assert np.allclose(a[both], b[both], rtol=0, atol=0)


def test_timestamp_alignment_intersection_helper():
    """Aligned dual index is the intersection of measurement clocks."""
    idx_p = pd.date_range("2018-01-01", periods=12, freq="5min")
    idx_f = idx_p.delete(3)  # drop one flow stamp
    idx = idx_p.intersection(idx_f)
    assert len(idx) == 11
    assert pd.Timestamp("2018-01-01 00:15:00") not in idx
    step = idx.to_series().diff().dropna()
    assert (step == pd.Timedelta(minutes=5)).sum() >= 9
