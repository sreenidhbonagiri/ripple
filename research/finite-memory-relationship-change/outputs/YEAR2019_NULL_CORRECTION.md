# 2019 null correction — per matching view and eligible event set

Generated: 2026-10-24T22:20:08-04:00

Preserves frozen FMR3C detector, τ, notifications, and `YEAR2019_EVALUATION.md` detector metrics. **No** threshold change, favorable relabeling, or re-inference.

## Why this correction

The original `YEAR2019_EVALUATION.md` §5 reported 0–2 h / 0–6 h nulls from a **single** shortened-window chronological matcher (`null_at_post_hours`), not from views A / B / C. View-native shift nulls were only shown for the **primary** eligible set. Those two choices mix procedures and hide eligible-set dependence.

This report recomputes nulls on the **same frozen episodes**, crossing:

- **Eligible sets:** `primary` (onset ≥ train_end), `post_fit` (onset ≥ earliest eligible notification)
- **Views:** A (joint greedy), B (abrupt-only greedy), C (max-cardinality)
- **Windows:** `native` (registered type windows), `0–2h`, `0–6h` (shortened post-onset; still using that view’s assignment rule)

- train_end: **2019-01-15 00:00**
- earliest_eligible_notification: **2019-01-17 01:55**
- episodes_sha256 (frozen): `3db05ac9472fffe4dab923a11cdf5801afd967356723a5b740782c7cb3fb7064`
- n_episodes: 74

## Eligible event sets

- **primary**: n=19 (abrupt=9, incipient=10) — onset ≥ train_end (same as registered YEAR2019 primary)
  - p523(abrupt), p827(abrupt), p280(abrupt), p653(incipient), p710(abrupt), p514(abrupt), p331(abrupt), p193(incipient), p277(incipient), p142(abrupt), p680(abrupt), p586(incipient), p721(incipient), p800(incipient), p123(incipient), p455(incipient), p762(incipient), p426(abrupt), p879(incipient)
- **post_fit**: n=18 (abrupt=8, incipient=10) — onset ≥ earliest eligible notification (after FMR3C warm-up)
  - p827(abrupt), p280(abrupt), p653(incipient), p710(abrupt), p514(abrupt), p331(abrupt), p193(incipient), p277(incipient), p142(abrupt), p680(abrupt), p586(incipient), p721(incipient), p800(incipient), p123(incipient), p455(incipient), p762(incipient), p426(abrupt), p879(incipient)

## Null matrix (abrupt match counts)

| Eligible set | View | Window | Obs abrupt hits | n abrupt | Null med (min–max) | Frac shifts ≥ obs |
|--------------|------|--------|-----------------|----------|-------------------|-------------------|
| primary | A | native type window (abrupt 7d / incipient to peak∩14d) | **4** | 9 | 3.0 (0–6) | **0.11** |
| primary | A | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–1) | **0.00** |
| primary | A | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–2) | **0.00** |
| primary | B | native type window (abrupt 7d / incipient to peak∩14d) | **5** | 9 | 3.0 (0–6) | **0.08** |
| primary | B | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–1) | **0.00** |
| primary | B | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–2) | **0.00** |
| primary | C | native type window (abrupt 7d / incipient to peak∩14d) | **5** | 9 | 3.0 (0–6) | **0.08** |
| primary | C | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–1) | **0.00** |
| primary | C | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 9 | 0.0 (0–2) | **0.00** |
| post_fit | A | native type window (abrupt 7d / incipient to peak∩14d) | **3** | 8 | 2.0 (0–5) | **0.48** |
| post_fit | A | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–1) | **0.00** |
| post_fit | A | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–2) | **0.00** |
| post_fit | B | native type window (abrupt 7d / incipient to peak∩14d) | **4** | 8 | 2.0 (0–5) | **0.08** |
| post_fit | B | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–1) | **0.00** |
| post_fit | B | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–2) | **0.00** |
| post_fit | C | native type window (abrupt 7d / incipient to peak∩14d) | **4** | 8 | 2.0 (0–5) | **0.08** |
| post_fit | C | 0–2 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–1) | **0.00** |
| post_fit | C | 0–6 h post-onset (∩ end; incipient ∩ peak) | **3** | 8 | 0.0 (0–2) | **0.00** |

### Reading rules

- Compare each cell only to itself (same view, set, window).
- Do **not** pick the most favorable cell as a headline replacement for registered view A / primary / native or abrupt-6h sensitivity.
- View B excludes incipient from competition; its obs counts are not joint-detection claims.
- Overlapping daily shifts are dependent; n abrupt is small.

## Per-cell abrupt assignments (observed)

### primary · view A · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- MISS p142 delay_h=None notify=None sensor=None
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### primary · view A · 0–2 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### primary · view A · 0–6 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### primary · view B · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### primary · view B · 0–2 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### primary · view B · 0–6 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### primary · view C · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p523 delay_h=53.583333333333336 notify=2019-01-18 04:35 sensor=n644
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### primary · view C · 0–2 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### primary · view C · 0–6 h post-onset (∩ end; incipient ∩ peak)

- MISS p523 delay_h=None notify=None sensor=None
- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view A · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- MISS p142 delay_h=None notify=None sensor=None
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### post_fit · view A · 0–2 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view A · 0–6 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view B · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### post_fit · view B · 0–2 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view B · 0–6 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view C · native type window (abrupt 7d / incipient to peak∩14d)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- HIT p426 delay_h=7.083333333333333 notify=2019-10-25 20:30 sensor=n644

### post_fit · view C · 0–2 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

### post_fit · view C · 0–6 h post-onset (∩ end; incipient ∩ peak)

- HIT p827 delay_h=0.9166666666666666 notify=2019-01-24 19:25 sensor=n726
- MISS p280 delay_h=None notify=None sensor=None
- MISS p710 delay_h=None notify=None sensor=None
- MISS p514 delay_h=None notify=None sensor=None
- MISS p331 delay_h=None notify=None sensor=None
- HIT p142 delay_h=1.0 notify=2019-06-12 20:55 sensor=n613
- HIT p680 delay_h=1.3333333333333333 notify=2019-07-10 10:05 sensor=n229
- MISS p426 delay_h=None notify=None sensor=None

## Relation to original evaluation §5

Original §5 used one shortened-window joint greedy (equivalent here to **view A · primary · 0–2h/0–6h**): obs abrupt = 3 (2h) / 3 (6h); frac≥obs = 0.00 / 0.00. Those figures must not be read as view-B/C nulls or as post_fit nulls. View-native primary nulls remain the shift diagnostics under registered type windows (see matrix rows window=`native`).

## Non-goals

- No detector / τ / notification changes
- No favorable rematching of registered metrics
- No production / Tiger / UI / main merge

