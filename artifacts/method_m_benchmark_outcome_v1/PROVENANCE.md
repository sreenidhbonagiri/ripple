# Method M benchmark outcome v1 — provenance

**Retrospective evaluation only.** This artifact is not available to the detector,
warning API, timeline API, saved investigations, or printed briefs. The product
opens it only after an explicit “Check benchmark outcome” action.

## Verified January 24 example (do not re-infer)

| Field | Value | Source |
|-------|-------|--------|
| Labeled pipe | **p827** | Official BattLeDIM `2019_Leakages.csv` (Zenodo 4017659) |
| Official onset | **2019-01-24 18:30:00** | First non-zero discharge on column `p827` |
| Frozen notify | **2019-01-24 18:30:00** | `notifications_2019.txt` (sha256 `7283a096…`) |
| Delay (5-min) | **0 steps / 0.0 h** | Same five-minute stamp; frozen matching row |
| Hit | yes | 6 h one-to-one abrupt credit matching |

Onset, pipe, and delay were taken from the official leakage file and the frozen
evaluation record — **not** inferred from chat or UI demos.

Official CSV sha256 (offline verification only; not shipped into serving):
`b2ffe56b6c2f3b6cdb6aae9aeb30b9c425ba911fff8e3716ae543a56ff7576cd`.

## Diagnostic totals (unchanged)

Copied from frozen `matching_verification` / `METHOD_M_5MIN_2019_RESULTS.md` /
`INTEGRATION_VERIFY.md`:

- Abrupt: **2/8** excluding development example p523; **3/9** inclusive
- Incipient: **0/10**
- Six unmatched notifications (2019)
- 2019 previously examined — **not a blind holdout**
- **No validated localization**

## Isolation

Serving Method M files keep `evaluation_labels_in_serving: false`. This
evaluation package is a separate versioned artifact under
`artifacts/method_m_benchmark_outcome_v1/`.
