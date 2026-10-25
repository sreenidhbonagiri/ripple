"""Bounded past-only fills with source timestamps and freshness flags.

No look-ahead: never interpolate using future observations or bfill.
If a required series has no source within ``max_age_steps``, that stamp is
unavailable and downstream dual/score results must be treated as missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class CausalFillFrame:
    """Causal fill of a DataFrame (or single-column Series promoted to frame)."""

    values: pd.DataFrame
    source_time: pd.DataFrame  # datetime64; NaT when unavailable
    age_steps: pd.DataFrame  # float; 0 = observed at stamp; NaN when unavailable
    is_filled: pd.DataFrame  # bool; True when value came from a past stamp
    available: pd.DataFrame  # bool; False when no past source within max_age_steps
    max_age_steps: int
    notes: dict[str, Any]


def _fill_one_column(
    values: np.ndarray,
    times: np.ndarray,
    max_age_steps: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    src_ord = np.empty(n, dtype="datetime64[ns]")
    src_ord[:] = np.datetime64("NaT", "ns")
    age = np.full(n, np.nan, dtype=float)
    filled = np.zeros(n, dtype=bool)
    avail = np.zeros(n, dtype=bool)
    last_val = np.nan
    last_t = np.datetime64("NaT", "ns")
    cur_age = 0
    for i in range(n):
        v = values[i]
        if np.isfinite(v):
            out[i] = v
            src_ord[i] = times[i]
            age[i] = 0.0
            filled[i] = False
            avail[i] = True
            last_val = v
            last_t = times[i]
            cur_age = 0
        elif np.isfinite(last_val) and cur_age < max_age_steps:
            cur_age += 1
            out[i] = last_val
            src_ord[i] = last_t
            age[i] = float(cur_age)
            filled[i] = True
            avail[i] = True
        else:
            if np.isfinite(last_val):
                cur_age = max_age_steps + 1
    return out, src_ord, age, filled, avail


def causal_ffill_frame(
    df: pd.DataFrame,
    *,
    index: pd.DatetimeIndex | None = None,
    max_age_steps: int = 2,
) -> CausalFillFrame:
    """Reindex to ``index`` (optional) and causally ffill with bounded age.

    ``max_age_steps`` is the maximum number of consecutive missing stamps that
    may inherit the last finite observation (age 1 … max_age_steps). Age 0 is
    an observed finite value at the stamp itself.
    """
    if max_age_steps < 0:
        raise ValueError("max_age_steps must be >= 0")
    raw = df if index is None else df.reindex(index)
    idx = raw.index
    cols = list(raw.columns)
    times = idx.to_numpy(dtype="datetime64[ns]")

    values = pd.DataFrame(index=idx, columns=cols, dtype=float)
    source_time = pd.DataFrame(index=idx, columns=cols, dtype="datetime64[ns]")
    age_steps = pd.DataFrame(index=idx, columns=cols, dtype=float)
    is_filled = pd.DataFrame(False, index=idx, columns=cols)
    available = pd.DataFrame(False, index=idx, columns=cols)

    n_obs = 0
    n_fill = 0
    n_unavail = 0
    for c in cols:
        col = raw[c].to_numpy(dtype=float, copy=True)
        out, src, age, filled, avail = _fill_one_column(col, times, max_age_steps)
        values[c] = out
        source_time[c] = src
        age_steps[c] = age
        is_filled[c] = filled
        available[c] = avail
        n_obs += int(np.sum(avail & ~filled))
        n_fill += int(np.sum(filled))
        n_unavail += int(np.sum(~avail))

    n_cells = int(len(idx) * max(len(cols), 1))
    notes = {
        "n_cells": n_cells,
        "n_observed": int(n_obs),
        "n_filled": int(n_fill),
        "n_unavailable": int(n_unavail),
        "frac_observed": float(n_obs / max(n_cells, 1)),
        "frac_filled": float(n_fill / max(n_cells, 1)),
        "frac_unavailable": float(n_unavail / max(n_cells, 1)),
        "max_age_steps": int(max_age_steps),
    }
    return CausalFillFrame(
        values=values,
        source_time=source_time,
        age_steps=age_steps,
        is_filled=is_filled,
        available=available,
        max_age_steps=max_age_steps,
        notes=notes,
    )


def causal_ffill_series(
    s: pd.Series,
    *,
    index: pd.DatetimeIndex | None = None,
    max_age_steps: int = 2,
) -> CausalFillFrame:
    name = s.name if s.name is not None else "value"
    return causal_ffill_frame(s.to_frame(name=name), index=index, max_age_steps=max_age_steps)


def row_all_available(available: pd.DataFrame, columns: list[str] | None = None) -> pd.Series:
    """True only when every required column is available at the stamp."""
    cols = list(columns) if columns is not None else list(available.columns)
    if not cols:
        return pd.Series(True, index=available.index)
    return available[cols].all(axis=1)
