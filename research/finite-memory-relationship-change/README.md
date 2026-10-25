# Finite-memory relationship-change (research design)

**Design only** — see [`DESIGN.md`](DESIGN.md). No detector implementation or evaluation runs in this package yet.

## Question

Can recent changes in signed per-target relationship residuals distinguish new events better than accumulated departure from a fitted baseline?

## Relation to prior work

- Closes further threshold tuning of `research/per-sensor-relationship-cusum` (CUSUM family).
- Does not revive `research/retrospective-review` (global offline screening — unsuccessful).
- Does not copy practice two-window scanner code; documentation-only comparison in `DESIGN.md`.

## Boundary

No production/UI/Tiger/main changes. Preserve all historical research reports.
