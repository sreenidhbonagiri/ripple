# Method M experimental integration — five-minute pre-merge verification

**Diagnostic evaluation, not a blind holdout.** 2019 was already examined in
research; product serving uses the frozen five-minute Method M January artifact
only (no evaluation labels in serving files).

## One-to-one event matching (2019 abrupt)

Frozen notifications (9) matched against abrupt onsets with a 6 h credit window.
January serving ships the two January notifies only.

| Pipe | Onset | Matched notify (5-min) | Hit |
|------|-------|------------------------|:---:|
| p523 | 2019-01-15 23:00:00 | 2019-01-15 23:00:00 | yes |
| p827 | 2019-01-24 18:30:00 | 2019-01-24 18:30:00 | yes |
| p280 | 2019-02-10 13:05:00 | — | no |
| p710 | 2019-03-24 14:15:00 | — | no |
| p514 | 2019-04-02 20:40:00 | 2019-04-02 20:45:00 | yes |
| p331 | 2019-04-20 10:10:00 | — | no |
| p142 | 2019-06-12 19:55:00 | — | no |
| p680 | 2019-07-10 08:45:00 | — | no |
| p426 | 2019-10-25 13:25:00 | — | no |

### Evaluation summary (frozen diagnostic)

- **Primary abrupt recall: 2/8** (excluding development example **p523**)
- **Inclusive abrupt recall: 3/9**
- **Incipient: 0/10**
- **Six unmatched notifications** across 2019
- **Same detected abrupt events** as hourly Method M; **earlier notifications**
  on shared hits where the five-minute grid allows (e.g. p827 18:30 vs hourly 19:00)

## Five-minute scoring resolution

Method M scores and notifies on a **native five-minute** grid. Product copy must
not imply finer-than-stamp precision. Badge: **Experimental · five-minute scoring**.

## Carryover counts

Carryover leaks open through 2019 reuse the same nine 2019 notifications; they
are not independent detections.

## Tiger capacity (before derived records)

| Metric | Value |
|--------|------:|
| database_bytes | 100013759 |
| limit_bytes | 786432000 |
| working_ceiling (80%) | 629145600 |
| usable_bytes | 529131841 |
| est. Method M derived table (5-min Jan density) | ~60 MiB |

**Decision:** capacity would allow a derived table, but January serving uses a
**file-backed artifact** (`artifacts/method_m_experimental_january/`) — no Tiger
derived table and no additional raw import.

## Serving package

- Score stamps: 8928 (January 2019, 5-minute)
- January notifications: `2019-01-15 23:00:00`, `2019-01-24 18:30:00`
- Frozen τ: **4.517**; recover = τ/2 for 12 steps (1 h)
- Evaluation labels: **excluded** from serving files
- Version hashes: see `manifest.json` (must match research
  `detection_2019_method_m_5min/pre_inference_hashes.json` /
  `pre_label_hashes.json`)

## Pre-merge verification (integration branch)

Recorded on `integrate/method-m-5min-experimental` before merge/deploy:

- Backend suite: **58 passed** (incl. Method M cursor/provenance/hash tests)
- Frontend: `tsc --noEmit` + `vite build` OK
- Docker: `scripts/verify_method_m_docker_artifacts.py` OK; local image
  `ripple-backend-method-m-5min-verify:local` contains
  `/app/artifacts/method_m_experimental_january/{manifest,serving_hours,serving_notifications,INTEGRATION_VERIFY}`
- Backward seeks / rapid seek: earlier cursor must not show a later notify (unit + API)
- Save/reopen: backend `test_saved_investigations` suite green; Method M API at
  warning-demo cursor shows active warn and seek-back clears warn (investigation
  UX unchanged)
- Hashes: serving `version_hashes` match frozen
  `detection_2019_method_m_5min/pre_inference_hashes.json` /
  `pre_label_hashes.json`
- Notices: experimental / not confirmed leak / not localization / five-minute
- Demo script: `docs/METHOD_M_WARNING_DEMO.md`
- **Stop:** no merge to main, no production deployment on this pass
