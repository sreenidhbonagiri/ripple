# Nominal L-Town dual-solver audit

Snapshot `2018-01-01 00:00:00` (start of FIT_W1).

- Pressure sensors mapped: **33**; missing: `[]`
- AMRs outside Area C: `[]` (expect none)
- Nominal pressure RMSE vs SCADA: **0.024 m**
- External inflow error (p227+p235): **13.12 m³/h**
- Tank level error: **-0.000 m**
- TCV K sweep (leak-free snapshot criterion) → freeze **K=0.001**

See JSON for per-K rows and cluster sizes.
