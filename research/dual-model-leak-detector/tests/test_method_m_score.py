"""Method M is not Method B; basic scale / max behavior."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dual_model.detection_scores import (  # noqa: E402
    estimate_method_m_scales,
    score_B_vector_change,
    score_M_maxabs_local_change,
)


def test_method_m_not_equal_method_b():
    idx = pd.date_range("2018-01-01", periods=120, freq="h")
    rng = np.random.default_rng(0)
    qv = pd.DataFrame(
        {
            "n1": rng.normal(0, 1, size=len(idx)),
            "n2": rng.normal(0, 1, size=len(idx)),
            "n3": rng.normal(0, 1, size=len(idx)),
        },
        index=idx,
    )
    # Localized spike on one sensor only
    qv.loc[idx[90], "n2"] += 20.0
    scale_idx = idx[30:70]  # ≥24h with causal ref history available
    sigma, med, meta = estimate_method_m_scales(qv, scale_idx)
    assert meta["n_sensors_kept"] == 3
    s_m = score_M_maxabs_local_change(qv, sigma_m3h=sigma, raw_max_median=med)
    s_b = score_B_vector_change(qv)
    # Both finite at spike hour, but not identical series
    assert np.isfinite(s_m.iloc[90]) and np.isfinite(s_b.iloc[90])
    assert not np.allclose(
        s_m.dropna().to_numpy(),
        s_b.reindex(s_m.dropna().index).to_numpy(),
        rtol=1e-3,
        atol=1e-3,
    )
    # Max-|z| should respond strongly to a single-sensor spike
    assert float(s_m.iloc[90]) > float(s_m.iloc[80])
