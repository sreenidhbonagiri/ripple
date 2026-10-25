# Experimental Method M warning — short demo script

Grounded in the shipped UI. Keep saying: experimental anomaly warning ≠ confirmed leak; no pipe localization.

Related: Tiger / Jan 12 observation walkthrough in [`PRESENTER_90S.md`](PRESENTER_90S.md).

**Diagnostic research context:** 2019 evaluation is not a blind holdout. Primary
abrupt recall **2/8** excl. development example p523; inclusive **3/9**;
incipient **0/10**; six unmatched notifications in 2019. Same detected events as
hourly Method M with earlier notifies on shared hits.

Jan 12 investigation preset stays unchanged. Warning demos are **separate**
bookmarks that jump to frozen January Method M notifications (five-minute grid).

**Primary warning demo:** `2019-01-24 18:30:00` (argmax contributing sensor from
the frozen artifact — not a guessed leak pipe).

## Script (~90s)

1. **Jan 12 baseline (no warning)** — Open Ripple. Use **Jan 12 preset →
   Illustrative Δ 15:00 (n54)**. Show pressure / 30-minute change and note the
   Experimental Method M panel: **no experimental warning**, five-minute score
   below τ, investigation still usable. Badge reads
   **Experimental · five-minute scoring**.

2. **Primary warning bookmark (24 Jan)** — Click **Method M notify 18:30 (24 Jan)**
   under *Experimental warning demo*. Cursor becomes `2019-01-24 18:30:00`
   (frozen five-minute notification). Panel shows **Experimental warning active**,
   disclaimer “not a confirmed leak”, five-minute resolution, threshold τ=4.517,
   data age. Selected sensor is the notify-stamp argmax from the serving artifact
   (**n726**). Use **Inspect sensor** on contributing sensors — observation only,
   not a leak location.

3. **Secondary notify (15 Jan)** — Optionally click **Method M notify 23:00 (15 Jan)**
   (`2019-01-15 23:00:00`, argmax **n506**) to show the other January frozen notify.

4. **Flow / tank context** — With the same cursor, show external inflows
   **p227 / p235**, internal **PUMP_1**, and **T1** tank level in the
   investigation panels — shared replay cursor, observation only.

5. **Saved investigation** — Open **Save investigation**, title e.g.
   “Method M experimental warn — 24 Jan 18:30”, optional public note that this
   is experimental (not a confirmed leak). Save, confirm restore URL loads the
   same cursor/window metadata; measurements reload live from historical tables;
   Method M panel reloads at the restored cursor without showing future notifies.
   Preset disclaimers match the active example (warning vs Jan 12 observation).

## Do not say

- Confirmed leak, alert triage as operational truth, or predicted leak pipe
- Sub-stamp detection timing finer than the five-minute notify grid
- Future episode peak or end before the cursor reaches them
- Evaluation labels (p523 / abrupt / carryover) in the product UI
- That 2019 was a blind holdout
- That Inspect sensor / contributing sensors identify the leaking pipe
