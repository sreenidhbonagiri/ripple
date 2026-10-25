# Chronological fit / validation windows (declared before fitting)

**Registered:** 2026-10-25 — before any measured-data parameter estimation in this package.  
**Data year:** 2018 only. **No 2019.**  
**Leak labels:** not used as calibration targets; not absorbed into demand.

## Information-availability rules

1. Fit uses only measurements available inside the fit window (and the static INP).
2. Validation windows are held out: parameters frozen after fit; no re-estimation.
3. Known 2018 leak onsets (from BattLeDIM config) are **not** used to choose windows
   for better scores, except the paper-aligned fact that week 1 precedes the first
   reported 2018 leak (`p257` starts 2018-01-08 13:30).
4. Validation spans multiple seasons / operating regimes — not January alone.
5. Post-freeze leak-onset inspection is **diagnostic**, not a detection score and
   not a reason to retune calibration.

## Fit window (parameter estimation)

| ID | Start (inclusive) | End (inclusive) | Role |
|----|-------------------|-----------------|------|
| `FIT_W1` | 2018-01-01 00:00 | 2018-01-07 23:55 | Demand TSA + roughness WLS (paper: first week 2018) |

SCADA cadence: 5 min. Hydraulic calibration internally may aggregate to 1 h
(declared engineering choice; see `DEPARTURES.md`).

## Validation windows (frozen parameters; no refit)

| ID | Start | End | Operating regime |
|----|-------|-----|------------------|
| `VAL_APR` | 2018-04-02 00:00 | 2018-04-08 23:55 | Spring |
| `VAL_JUL` | 2018-07-02 00:00 | 2018-07-08 23:55 | Summer (higher demand seasonality) |
| `VAL_OCT` | 2018-10-01 00:00 | 2018-10-07 23:55 | Autumn |
| `VAL_DEC` | 2018-12-03 00:00 | 2018-12-09 23:55 | Early winter |

These weeks are chronological and multi-season. They are **not** claimed leak-free;
ongoing background leaks (e.g. unrepaired `p257`/`p427`/…) will appear in residuals
and virtual flows. That is expected and must not be fitted away.

## Metrics (pre-declared)

### Calibration fit (`FIT_W1`)

- Pressure RMSE / bias at 33 sensors (m)
- External inflow error: `(q_p227 + q_p235)_sim − (q_p227 + q_p235)_meas` (m³/h)
- Tank level RMSE (m)
- Roughness parameter bounds activity / confidence proxies

### Independent validation (`VAL_*`)

Same metrics as fit, plus:

- Per-sensor signed virtual flows `q_v` (m³/h): mean, std, and **signed sum**
- Report that cancellation in the sum can hide large opposing `q_v`
- Operating-state bias: day vs night (00–05 vs 10–15 local) mean Σq_v

### Post-freeze diagnostic (not detection accuracy)

- At selected 2018 abrupt onsets with clear SCADA coverage, compare ΔΣq_v and
  nearest-sensor `q_v` in a ±24 h window vs a matched ordinary hour-of-week
  contrast from the fit week. **No threshold search. No event-specific retune.**

## Resistance (TCV) policy

Virtual-reservoir TCV setting `K` is audited for numerical sensitivity on
**leak-free FIT_W1 snapshots** (pressure consistency / Σq_v magnitude under the
nominal model). **`K` is not selected using leak-detection outcomes.**
Default remains `K = 1e-3` unless the audit shows numerical failure.
