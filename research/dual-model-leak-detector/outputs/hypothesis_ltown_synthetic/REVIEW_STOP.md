# Review stop — toy audit + L-Town synthetic feasibility

## Preserved (not retuned)

- `outputs/hypothesis_synthetic/synthetic_feasibility_results.json` and markdown  
- Audit: `outputs/hypothesis_synthetic/AUDIT_TOY_SYNTHETIC.md`  
- Explains 50% singleton coverage as **1/2 test detects**, wrong best under demand+leak, plus **uncalibrated** `region_eps=0.02` — **not** candidate omission; bounds contained perturbations; same nonlinear EPANET generator.

## New (this stage)

| Artifact | Role |
|----------|------|
| `REGION_CONSTRUCTION_PROTOCOL.md` | Train/DEV-only ε with 90% intended coverage; size/coverage/abstention separate; ΔJ not a probability |
| `ltown_synthetic_feasibility_results.json` | Fresh whole-scenario L-Town run |
| `LTOWN_SYNTHETIC_FEASIBILITY_RESULTS.md` | Human summary |

**Network:** L-TOWN.inp + frozen HW clusters (`5fab3acb…`).  
**Candidates:** 33 pressure sensors; all injected leaks ∈ candidates.  
**H1:** nested (H0 MLE scales/ρ frozen + q≥0). Same EPANET generator; no linear approx for reported J.  
**Method M temporal vs steady snapshots:** **inapplicable**.

### DEV-frozen (before test)

- `tau_dev=0.05`, `region_eps=0.0` (DEV detects already exact → smallest ε for ≥90% coverage)  
- Signature matched: `tau_lo=0.5`, `tau≈5.69`

### TEST snapshot (exact counts in JSON)

| | H0/H1 | Signature (matched) |
|--|------:|--------------------:|
| n | 6 | 6 |
| TPR | 1/4 = 0.25 | 1/4 = 0.25 |
| FPR | 0/2 = 0 | 0/2 = 0 |
| Abstention | 4/6 ≈ 0.67 | 3/6 = 0.50 |
| mean \|R\| among detects | 1.0 (n_detect=1) | singleton |
| Coverage among detects | 1/1 = 1.0 | n/a |
| Exact loc among detects | 1/1 | 1/1 |

Low TPR / high abstention reflects **small steady head SSE** (O(0.02 m²) for ~5 m³/h leaks) vs a DEV threshold raised to keep demand/mismatch controls from false detects — method **admits ambiguity** rather than forcing locations.

## Out of scope

No measured evaluation, 2019, production, Tiger, UI, or deployment.
