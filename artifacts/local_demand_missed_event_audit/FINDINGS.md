# Local demand-context & missed-event audit

Local analysis only. Production deployment was not modified. No Tiger imports. No practice-project code/artifacts copied.

## Prior knowledge (honest)
These five pipes (p280, p710, p331, p680, p426) were previously discussed in a separate development conversation about a practice BattLeDIM scanner as abrupt events that were harder to catch / “missed” relative to that practice detector’s alerts. They are already-examined development examples from official dataset_configuration.yaml leakages, not a blind holdout. This rippple repository has no detector implementation; practice scanner alert lists, suppression logic, and unmatched-alert tallies are not available here and are not reproduced. Therefore baseline suppression and notification-policy failures cannot be assessed from measurements alone in this audit.

## 1. Official AMR / demand data
- Source: `Zenodo 4017659 / 2019_SCADA_Demands.csv` (md5 `b3e111de397a1b06d33b8a9f13bc997d`)
- Units: **L/h (official README)**; separator `;` with decimal commas
- Meters: **82** (cfg == INP `;AMR` comments: True)
- Timestamps: `2019-01-01 00:00:00` → `2019-12-31 23:55:00` · rows **105120** (expected 105120 for 5‑min 2019: True)
- Missing cells: **0** · meters with any null: 0 · negative values: 0
- Overlap with pressure sensors (same node IDs): ['n1', 'n31', 'n4']
- Pressure sensors inside AMR coordinate bbox: ['n1', 'n4', 'n31']
- Area C: Official README describes 82 AMR devices in L-Town (L/h) without using the phrase "Area C". All 82 cfg amrs are marked ;AMR in L-TOWN.inp and form a compact coordinate cluster. Only pressure sensors n1,n4,n31 lie inside that AMR bounding box; the other 30 pressure sensors are outside it. Competition literature commonly calls this AMR-instrumented DMA Area C — treated here as that cluster, not as network-wide demand.
- **Do not treat the sum of the 82 AMRs as total network demand** (partial metering; L/h customer meters ≠ network mass balance).

## 2. What can be diagnosed here
- This repository is a historical investigation workspace **without a detector**.
- We can inspect SCADA pressure/flow/level and AMR context around official onsets.
- We **cannot** score detection latency, suppression, or unmatched alerts for the current codebase because it produces none.

## 3. Previously examined abrupt examples
Comparison rule (consistent): median(0–2h after onset) − median(2h before onset); excess versus the same clock window one week earlier.

### p280 · onset 2019-02-10 13:05:00 · Ø 0.0095 m
- Ends `n365`–`n23` · AMR endpoints: True · inside AMR bbox: True
- Nearest pressures: ['n31', 'n4', 'n54']
- Nearest AMRs plotted: ['n23', 'n365', 'n377', 'n361']
- Largest pressure excess vs prior week: `pressure_n31` = -0.090 m
- `flow_p227` excess vs prior week: -0.8
- `flow_p235` excess vs prior week: -0.33
- `flow_PUMP_1` excess vs prior week: 0.0
- `tank_T1` excess vs prior week: 0.0
- `amr_nearest_sum_Lph` excess vs prior week: 15.17
- Plot: `artifacts/local_demand_missed_event_audit/plots/p280_onset_context.png`

### p710 · onset 2019-03-24 14:15:00 · Ø 0.0093 m
- Ends `n648`–`n228` · AMR endpoints: False · inside AMR bbox: False
- Nearest pressures: ['n636', 'n644', 'n229']
- Nearest AMRs plotted: ['n343', 'n41', 'n44', 'n387']
- Largest pressure excess vs prior week: `pressure_n644` = -0.080 m
- `flow_p227` excess vs prior week: 3.31
- `flow_p235` excess vs prior week: 0.56
- `flow_PUMP_1` excess vs prior week: 0.0
- `tank_T1` excess vs prior week: -0.01
- `amr_nearest_sum_Lph` excess vs prior week: 39.2
- Plot: `artifacts/local_demand_missed_event_audit/plots/p710_onset_context.png`

### p331 · onset 2019-04-20 10:10:00 · Ø 0.0141 m
- Ends `n398`–`n399` · AMR endpoints: False · inside AMR bbox: False
- Nearest pressures: ['n429', 'n410', 'n54']
- Nearest AMRs plotted: ['n41', 'n343', 'n44', 'n36']
- Largest pressure excess vs prior week: `pressure_n410` = -0.450 m
- `flow_p227` excess vs prior week: 8.56
- `flow_p235` excess vs prior week: 8.38
- `flow_PUMP_1` excess vs prior week: 0.04
- `tank_T1` excess vs prior week: -0.43
- `amr_nearest_sum_Lph` excess vs prior week: 357.81
- Plot: `artifacts/local_demand_missed_event_audit/plots/p331_onset_context.png`

### p680 · onset 2019-07-10 08:45:00 · Ø 0.0097 m
- Ends `n626`–`n233` · AMR endpoints: False · inside AMR bbox: False
- Nearest pressures: ['n229', 'n215', 'n644']
- Nearest AMRs plotted: ['n343', 'n44', 'n387', 'n388']
- Largest pressure excess vs prior week: `pressure_n229` = -0.210 m
- `flow_p227` excess vs prior week: 2.38
- `flow_p235` excess vs prior week: -3.24
- `flow_PUMP_1` excess vs prior week: 0.01
- `tank_T1` excess vs prior week: -0.11
- `amr_nearest_sum_Lph` excess vs prior week: 147.72
- Plot: `artifacts/local_demand_missed_event_audit/plots/p680_onset_context.png`

### p426 · onset 2019-10-25 13:25:00 · Ø 0.0150 m
- Ends `n461`–`n462` · AMR endpoints: False · inside AMR bbox: False
- Nearest pressures: ['n342', 'n458', 'n429']
- Nearest AMRs plotted: ['n343', 'n41', 'n44', 'n387']
- Largest pressure excess vs prior week: `pressure_n429` = -0.340 m
- `flow_p227` excess vs prior week: 5.68
- `flow_p235` excess vs prior week: 4.38
- `flow_PUMP_1` excess vs prior week: -0.08
- `tank_T1` excess vs prior week: -0.01
- `amr_nearest_sum_Lph` excess vs prior week: -87.2
- Plot: `artifacts/local_demand_missed_event_audit/plots/p426_onset_context.png`

## 4. At most one detection experiment (recommendation)
**Recommended experiment (single):** pressure residual relative to a prior-week same-clock baseline at the nearest 2–3 pressure sensors, with an explicit **external-inflow / pump / tank covariate gate**.

**Why:** Across these development examples, abrupt onsets sit in SCADA pressure; several pipes (p710, p331, p680, p426) lie **outside** the AMR cluster, so AMR sum cannot be the primary cue. Network boundary flows (p227/p235), PUMP_1, and T1 can move with demand and operations and may absorb or confound leakage signatures—so they should be covariates/gates, not ignored.

**Inputs that might absorb leakage behavior:** p227/p235 (external supply), PUMP_1 (internal transfer), T1 (storage), and local AMR demand where available (p280 neighborhood).

**Evaluation (no threshold sweep in this task):**
- Sensitivity: fraction of official abrupt onsets (start with these five + other 2019 abrupt rows in `dataset_configuration.yaml`) with a residual excursion exceeding a pre-registered ordinary-day quantile within a fixed post-onset horizon (e.g. 2–6 h).
- Unmatched-alert burden: count residual excursions on randomly sampled non-onset weeks (or all weeks with no open leakage per ground truth), reported as alerts/week — not labeled “false positives” without a policy.
- Report both metrics together; do not optimize thresholds here.

If only AMR-rich Area C events mattered, a meter-balance experiment would be tempting; the geography of these missed examples argues against leading with that.

## Artifacts
- `/Users/sreenidhbonagiri/Desktop/rippple/artifacts/local_demand_missed_event_audit/findings.json`
- plots under `/Users/sreenidhbonagiri/Desktop/rippple/artifacts/local_demand_missed_event_audit/plots`