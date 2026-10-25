# Method M experimental integration — pre-integration verification

## One-to-one event matching (2019 abrupt)

Frozen notifications (9) matched one-to-one against abrupt onsets with a 6 h credit window
(earliest unused notify in window). Timestamps match `notifications_2019.txt`.

| Pipe | Onset | Matched notify | Hit |
|------|-------|----------------|:---:|
| p523 | 2019-01-15 23:00:00 | 2019-01-15 23:00:00 | yes |
| p827 | 2019-01-24 18:30:00 | 2019-01-24 19:00:00 | yes |
| p280 | 2019-02-10 13:05:00 | — | no |
| p710 | 2019-03-24 14:15:00 | — | no |
| p514 | 2019-04-02 20:40:00 | 2019-04-02 21:00:00 | yes |
| p331 | 2019-04-20 10:10:00 | — | no |
| p142 | 2019-06-12 19:55:00 | — | no |
| p680 | 2019-07-10 08:45:00 | — | no |
| p426 | 2019-10-25 13:25:00 | — | no |

- **Abrupt recall: 3/9**
- **Abrupt recall excluding development example p523: 2/8**

## Hourly scoring resolution

Method M scores and notifies on an **hourly** grid. Product copy must not imply
sub-hour precision (e.g. do not treat a notify at `19:00` as detecting an
`18:30` onset to the minute).

## Carryover counts

Carryover leaks open through 2019 list `n_2019_notifies_while_open = 9` for each
row. Those counts **reuse the same nine 2019 notifications**; they are not
independent detections.

## Tiger capacity (before derived records)

| Metric | Value |
|--------|------:|
| database_bytes | 100013759 |
| limit_bytes | 786432000 |
| working_ceiling (80%) | 629145600 |
| usable_bytes | 529131841 |
| est. Method M derived table | ~5.1 MiB |

**Decision:** capacity would allow a derived table, but January serving uses a
**file-backed artifact** (`artifacts/method_m_experimental_january/`) — no Tiger
derived table and no additional raw import.

## Serving package

- Hours: 744 (January 2019)
- January notifications: ['2019-01-15 23:00:00', '2019-01-24 19:00:00']
- Evaluation labels: **excluded** from serving files
- Version hashes: see `manifest.json`

## Pre-deploy verification (integration branch)

- Backend suite: **57 passed**
- Frontend: `tsc --noEmit` + `vite build` OK
- Docker: `Dockerfile.backend` copies `artifacts/`; Method M January JSON/MD not dockerignored (`scripts/verify_method_m_docker_artifacts.py`); local image `ripple-backend-method-m-verify:local` contains `/app/artifacts/method_m_experimental_january/{manifest,serving_hours,serving_notifications,INTEGRATION_VERIFY}`
- Browser: Jan 12 no-warning; warning-demo bookmark at frozen `2019-01-15 23:00:00`; loading on rapid seek (no stale warning); API `before_coverage` for pre-January cursor
- Hashes: serving `version_hashes` match frozen `pre_inference_hashes.json` / `pre_label_hashes.json`
- Notices: experimental / not confirmed leak / not localization / hourly resolution
- Demo script: `docs/METHOD_M_WARNING_DEMO.md`
- **Stop:** no merge to main, no production deployment on this pass
