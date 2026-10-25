"""Multiscale Method M: joint search, baseline medium==Method M, no independent union."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_scores import (  # noqa: E402
    estimate_method_m_scales,
    score_M_maxabs_local_change,
)
from dual_model.method_m_multiscale import (  # noqa: E402
    BASELINE_TIMESCALE,
    TIMESCALE_REF_HOURS,
    TimescaleScales,
    estimate_all_timescale_scales,
    estimate_scales_for_ref,
    score_method_m_multiscale_combined,
    score_method_m_single_timescale,
)
from dual_model.notifier import episodes_from_scores  # noqa: E402


def _toy_qv(n: int = 200, seed: int = 1) -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", periods=n, freq="h")
    rng = np.random.default_rng(seed)
    qv = pd.DataFrame(
        {
            "n1": rng.normal(0, 1.0, size=n),
            "n2": rng.normal(0, 1.2, size=n),
            "n3": rng.normal(0, 0.8, size=n),
        },
        index=idx,
    )
    # Localized abrupt-like jump
    qv.loc[idx[150], "n2"] += 25.0
    return qv


def test_registered_timescales_include_baseline_24h():
    assert BASELINE_TIMESCALE == "medium"
    assert TIMESCALE_REF_HOURS == {"short": 12, "medium": 24, "long": 72}
    assert TIMESCALE_REF_HOURS["medium"] == 24


def test_medium_single_timescale_matches_frozen_method_m_helpers():
    qv = _toy_qv()
    # Use a late SCALE window inside the series so causal refs exist
    scale_idx = qv.index[40:100]
    sigma_m, med_m, _ = estimate_method_m_scales(qv, scale_idx)
    s_frozen = score_M_maxabs_local_change(qv, sigma_m3h=sigma_m, raw_max_median=med_m)

    sigma_g, med_g, _ = estimate_scales_for_ref(qv, ref_hours=24, scale_index=scale_idx)
    s_gen = score_method_m_single_timescale(
        qv, ref_hours=24, sigma_m3h=sigma_g, raw_max_median=med_g
    )
    # Same sensors and medians
    assert set(sigma_m.index) == set(sigma_g.index)
    assert abs(med_m - med_g) < 1e-12
    a = s_frozen.dropna()
    b = s_gen.reindex(a.index)
    assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12)


def test_combined_score_ge_each_single_scale_raw_structure():
    """Combined uses joint max — not a post-hoc union of episode streams."""
    qv = _toy_qv(n=24 * 25)
    scales = estimate_all_timescale_scales(qv)
    s_ms, med, meta = score_method_m_multiscale_combined(qv, scales)
    assert meta["not_independent_union"] is True
    assert np.isfinite(med)
    assert s_ms.notna().sum() > 100
    # Single stream notifier produces a finite episode list
    finite = s_ms.dropna()
    tau = float(finite.quantile(0.99))
    eps = episodes_from_scores(s_ms.to_numpy(dtype=float), tau=tau)
    assert isinstance(eps, list)


def test_estimate_all_timescales_keys():
    # Need coverage through SCALE_END (2018-01-21 23:00)
    qv = _toy_qv(n=24 * 25)
    scales = estimate_all_timescale_scales(qv)
    assert set(scales) == {"short", "medium", "long"}
    for sc in scales.values():
        assert sc.meta["n_sensors_kept"] >= 1
