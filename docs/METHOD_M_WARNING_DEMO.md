# Experimental Method M warning — short demo script

Grounded in the shipped UI on `integrate/method-m-experimental-warning`.
Keep saying: experimental anomaly warning ≠ confirmed leak; no pipe localization.

Jan 12 investigation preset stays unchanged. The warning demo is a **separate**
bookmark that jumps to a frozen January Method M notification.

## Script (~90s)

1. **Jan 12 baseline (no warning)** — Open Ripple. Use **Jan 12 preset →
   Illustrative Δ 15:00 (n54)**. Show pressure / 30-minute change and note the
   Experimental Method M panel: **no experimental warning**, hourly score below
   τ, investigation still usable.

2. **Warning demo bookmark** — Click **Method M notify 23:00 (15 Jan)** under
   *Experimental warning demo*. Cursor becomes `2019-01-15 23:00:00` (frozen
   hourly notification). Panel shows **Experimental warning active**, disclaimer
   “not a confirmed leak”, hourly resolution badge, threshold τ, data age.

3. **Sensor evidence** — In the Method M panel, read **contributing sensors**
   (measured dual context: |z|/cal, δ, σ_SCALE, q_v). Selected sensor is the
   notify-hour argmax (n506). Do **not** name a predicted leak pipe.

4. **Flow / tank context** — With the same cursor, show external inflows
   **p227 / p235**, internal **PUMP_1**, and **T1** tank level in the
   investigation panels — shared replay cursor, observation only.

5. **Saved investigation** — Open **Save investigation**, title e.g.
   “Method M experimental warn — 15 Jan 23:00”, optional public note that this
   is experimental (not a confirmed leak). Save, confirm restore URL loads the
   same cursor/window metadata; measurements reload live from historical tables.

## Do not say

- Confirmed leak, alert triage as operational truth, or predicted leak pipe
- Sub-hour detection timing (onset minutes) from the hourly notify
- Future episode peak or end before the cursor reaches them
- Evaluation labels (p523 / abrupt / carryover) in the product UI
