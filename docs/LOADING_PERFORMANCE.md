# Loading performance measurements

Docker UI: `http://127.0.0.1:8080`. Tiger evidence stays collapsed until expanded.

## Readiness definitions (not interchangeable)

These are **different** readiness events. Do **not** treat them as a single
before/after speedup ratio.

### A — DOM-polled shell (pre-change baseline)

**Definition:** `performance.now()` when `.map-meta` exists, an “Illustrative”
presenter control is present, and the loading state title is gone.

| Run | Time |
| --- | ---: |
| before1 | 11.5 s |
| before2 | 5.6 s |
| before3 | 10.1 s |
| Prior quoted first-usable | ~9.2 s |

Under CDP automation this poller is easily starved by long main-thread work
(setTimeout / MutationObserver callbacks fire late even after the DOM is ready).
Treat these numbers as the historical **DOM-poll** baseline only.

### B — Instrumented marks (post-change)

**Definition (navigation-relative `performance.mark`):**

- `ripple-bootstrap-ready` — network + sensors + replay window + parallel
  initial snapshot responses applied (shell data ready).
- `ripple-cy-ready` — Cytoscape instance constructed after async import.

| Run | bootstrap-ready | cy-ready |
| --- | ---: | ---: |
| final2 | 0.46 s | 0.59 s |
| final3 | 0.52 s | 0.68 s |
| final4 | 0.61 s | 0.71 s |
| after-w2 | 0.36 s | 0.46 s |
| after-w3 | 0.51 s | 0.69 s |

Marks are set synchronously during app work; they are the authoritative
post-change timeline for bootstrap and map construction.

## API timings (resource timing — separate from browser readiness)

Report API durations from `PerformanceResourceTiming`, not from readiness marks.

| Phase | Pattern | Notes |
| --- | --- | --- |
| Before | network / sensors / window in parallel; **snapshot started after window** | Window often ~0.8–1.0 s; `apiMaxEnd` ~1.3–1.6 s |
| After | network + sensors + window + **snapshot at presenter start** all parallel | No duplicate bootstrap GETs; Tiger `/api/tiger/evidence` only on expand |

`/api/replay/window` `reading_count` uses Timescale `approximate_row_count` and
is labeled **estimated** in the API (`reading_count_estimated: true`) and UI.
Exact `COUNT(*)` totals remain on `/api/tiger/evidence` (Tiger panel).

## Critical path (after)

1. Main JS (~174 KB; Cytoscape / ECharts code-split)
2. Parallel APIs → `ripple-bootstrap-ready`
3. Async Cytoscape chunk + map init → `ripple-cy-ready`

Charts and hourly history load only after a sensor is selected.
