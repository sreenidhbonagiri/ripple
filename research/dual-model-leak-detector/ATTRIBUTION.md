# Attribution and licenses

## Method references (not redistributed here)

This research package reimplements the **pressure–leak dual model** described in:

1. Steffelbauer, D. B., Deuerlein, J., Gilbert, D., Abraham, E., & Piller, O. (2022).
   Pressure-Leak Duality for Leak Detection and Localization in Water Distribution Systems.
   *Journal of Water Resources Planning and Management*, 148(3), 04021106.
   DOI: [10.1061/(ASCE)WR.1943-5452.0001515](https://doi.org/10.1061/(ASCE)WR.1943-5452.0001515)

2. Steffelbauer, D. B., Deuerlein, J., Gilbert, D., Piller, O., & Abraham, E. (2020).
   A Dual Model for Leak Detection and Localization (BattLeDIM report).
   Zenodo. DOI: [10.5281/zenodo.3923907](https://doi.org/10.5281/zenodo.3923907)
   License of the report PDF: **CC-BY-4.0**.

3. Campbell, E., Abraham, E., Koslowski, J., Piller, O., & Steffelbauer, D. B. (2024).
   The Dual Model under Pressure: How Robust Is Leak Detection under Uncertainties and Model Mismatches?
   *Engineering Proceedings*, 69(1), 89.
   DOI: [10.3390/engproc2024069089](https://doi.org/10.3390/engproc2024069089)

No upstream source code was published with those papers. This package is an
**independent engineering reconstruction** of the dual hydraulic construction
(virtual reservoirs + valves at pressure sensors → virtual leak flows). It is
**not** affiliated with the authors or team “Under Pressure.”

## Third-party software used at runtime

| Component | Role | License |
|-----------|------|---------|
| [WNTR](https://github.com/USEPA/WNTR) | EPANET network I/O and hydraulic simulation | MIT |
| EPANET (via WNTR) | Demand-driven hydraulic solver | Public domain / MIT (toolkit) |
| NumPy / pandas | Arrays and tables | BSD |

## This package

Original Ripple research code in this directory is provided for research isolation
only. It is **not** part of production, Tiger, or the UI. Do not merge to `main`
without a separate authorization.

BattLeDIM / L-Town network data (when used in later stages) remain under their
Zenodo / competition terms; this stage uses only synthetic networks generated here.
