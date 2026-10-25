# Event-level signal-preservation audit (diagnostic)

**No fitting, tuning, threshold changes, or sensor selection by leak location.**  
**Preserve** frozen calibration, measured-PUMP_1 boundary, and prior detection artifacts.

Frozen calibration sha256: `5fab3acbf13f018d321b2d6af8c1522276dd2190efbc0a88b426f8755540c921`  
Dual q_v / Method A scores: `outputs/detection_2018_measured_pump1/` (measured_pump1).  
Acknowledge: 2018 events already examined — all contrasts are **diagnostic**.

---

## Events

All registered abrupt onsets (DEV + DIAG) from `DETECTION_PROTOCOL.md`:
`p673`, `p538`, `p866`, `p183`, `p158`, `p369`.

---

## Identical windows

Hourly grid (`minute==0`), same for every quantity and every event/control:

| Window | Definition |
|--------|------------|
| **PRE** | \([t_0 - 6\mathrm{h},\, t_0)\) |
| **POST** | \([t_0,\, t_0 + 6\mathrm{h}]\) |

Contrast for a scalar or per-sensor series \(x\):  
\(\Delta = \mathrm{mean}(x_{\mathrm{POST}}) - \mathrm{mean}(x_{\mathrm{PRE}})\).

---

## Quantities (full sensor set; no leak-based selection)

1. **Measured pressure** \(P_i\) at all pressure sensors; network summaries: mean \(\Delta P\), \(\|\Delta\mathbf{P}\|_2\), mean \(|\Delta P_i|\).
2. **Measured external inflow** \(Q_{\mathrm{ext}}=q_{227}+q_{235}\) (not `PUMP_1`).
3. **Hydraulic prediction error** \(e_i = P_i^{\mathrm{meas}} - P_i^{\mathrm{sim}}\) under the **frozen calibrated primal** (same demand/roughness as the dual; INP pump controls — documents what calibration/boundary absorb). Also report **uncalibrated INP-nominal** error the same way as a secondary reference (`err_nominal`).
4. **Measured-PUMP_1 dual virtual flows** \(q_{v,i}\) (existing series); network: \(\Delta\Sigma q_v\), \(\|\Delta\mathbf{q}_v\|_2\), mean \(|\Delta q_{v,i}|\).
5. **Method A score** \(s_A(t)\) (existing); contrasts on the score series plus credit-window max for context (not used to retune \(\tau\)).

---

## Ordinary-period controls (operating-condition matched)

For each event onset \(t_0\):

- Candidate control onsets share the **same hour-of-day**.
- Exclude any candidate within **±72 h** of any abrupt onset.
- Match PRE operating state: minimize  
  \(|\overline{Q}_{\mathrm{ext}}^{\mathrm{PRE}}-\overline{Q}_{\mathrm{ext},0}^{\mathrm{PRE}}| + |\overline{\mathrm{PUMP}}_1^{\mathrm{PRE}}-\overline{\mathrm{PUMP}}_{1,0}^{\mathrm{PRE}}|\)  
  (m³/h), require both absolute deviations ≤ the 80th percentile of same-hour candidates (else take nearest 15).
- Keep up to **25** best matches.
- Ordinary variability = mean / std of the same contrast statistic across those controls.
- Event **SNR-like ratio**: \((\Delta_{\mathrm{event}} - \mathrm{mean}_{\mathrm{ctrl}}) / \max(\mathrm{std}_{\mathrm{ctrl}}, \varepsilon)\).

---

## Loss-stage labels (missed events only)

A DEV/DIAG abrupt event is **missed** for this audit if Method A credit-window max \(< 1.791\) (frozen operating-point \(\tau\) from `OPERATING_POINT_RESULTS.md`) — used only as a diagnostic miss flag, not retuned.

Assign the **earliest** applicable stage:

| Stage | Criterion (diagnostic; earliest dual-path loss) |
|-------|-------------------------|
| `weak_in_measurements` | P L2 and Q_ext SNR both \(< 1.5\), **and** dual \(\Sigma q_v\) / \(\|\Delta\mathbf{q}_v\|_2\) also not strong (\(< 1.5\)) |
| `explained_by_hydraulics` | Measurement SNR strong, but calibrated prediction-error L2 SNR \(< 1\) **and** dual \(q_v\) contrasts not strong |
| `canceled_by_signed_sum` | Per-sensor or vector \(q_v\) SNR strong, but \(\|\mathrm{SNR}(\Delta\Sigma q_v)\|< 1\) |
| `suppressed_by_temporal_score` | \(\Sigma q_v\) or vector \(q_v\) SNR \(\ge 1.5\), but Method A \(\Delta s_A\) and credit-max SNR both \(< 1.5\) |
| `survives_to_score_below_tau` | Score/credit SNR \(\ge 1.5\) vs ordinary controls, yet credit max still \(<\) frozen \(\tau\) |
| `unclear` | None of the above |

---

## Recommendation rule

Recommend **one** intervention only if a **specific** stage consistently removes useful signal across misses. Otherwise state that **no supported correction emerged**.

No 2019 / UI / Tiger / deploy / main / threshold changes.
