# P1.5 Continuation Partition — ROUND-2 CONFORMANCE REVIEW (fresh reviewer, Opus)

**FINAL VERDICT: CONFORMANT.** The round-2 defect-corrected re-run is conformant with the
approved PREREG, the P0 Measurement Memo (§6 v1.1), and masterplan rulings. The round-1 BLOCKING
defect (B1) is demonstrably dead: the primary partition is now built on the PREREG-registered
`align_tier` column, the corrected mechanism reproduces independently from the parquet, and the
study lands cleanly on **H-MISLABEL** with no manufactured decision-table gap. No BLOCKING findings.
Three low-severity ADVISORY items carried forward from round-1 are all now addressed in-artifact.

Every headline number below was recomputed independently from
`data/replay/replay_boarded.parquet` (not read from the runner's output); all match to <0.01%.

---

## Check 1 — Round-1 BLOCKING defect (B1) is demonstrably dead

**PASS.** B1 was: the round-1 script partitioned on `tier_cascade` (values `T1/T2/T3`, the
confluence cascade) with a silent remap `T1→PRIME`, `T2→ARMED`, instead of the PREREG §3/§9
alignment tier whose literal values are `PRIME/ARMED/APPROACHING` — the `align_tier` column.

I verified the fix two ways against the v2 code and the parquet:

1. **v2 code reads the correct column.** `run_P1_5_CONTINUATION_v2.py` L127-129 defines the arms as
   `align_tier=='ARMED' & weekly_phase=='rising'` (ARMED-continuation),
   `align_tier=='PRIME' & weekly_phase∈{bear_recovering,basing,turning}` (PRIME), and
   `align_tier=='ARMED' & weekly_phase!='rising'` (other ARMED). `tier_cascade` appears in the
   code only inside the calibration crosstab (L121), never in an arm definition. Grep-confirmed:
   the only `tier_cascade` references are the crosstab and the results.json calibration block.

2. **Both mechanisms reproduced independently from the parquet.**
   - *Round-1 defect mechanism* (`tier_cascade` T2→ARMED / T1→PRIME remap, bottoming-phase filter):
     Δ = **−0.05487** — exactly the bounced round-1 headline (−5.49pp). The defect is real and I
     can regenerate the wrong number on demand.
   - *Round-2 fix mechanism* (`align_tier` literal): Δ = **−0.02793** — matches results.json.

The two columns genuinely do not map (independently recomputed crosstab, verdict-grade fires):

| align_tier \ tier_cascade | T1 | T2 | T3 |
|---|---|---|---|
| APPROACHING | 1075 | 2100 | 991 |
| ARMED | 620 | 883 | 249 |
| PRIME | 3625 | 1745 | 78 |
| NaN | 17696 | 19497 | 1380 |

`tier_cascade==T1` holds 620 ARMED + 1075 APPROACHING (not "PRIME"); `T2` holds 1745 PRIME. The
round-1 remap was arithmetically wrong, and this crosstab is byte-identical to the one printed in
RESULTS.md. **The B1 blocker is correctly withdrawn.**

Consequence check: on the correct column |Δ|=2.79pp < 5pp materiality bar, so PREREG §6
H-MISLABEL first disjunct governs. There is no unspecified branch, so the round-1 AMBIGUOUS/
decision-gap escalation was indeed an artifact of the mis-map. The runner's headline is faithful.

---

## Check 2 — Calibration controls are genuine

**PASS (P1.5-scoped).** The CHECKS enumerate per-study calibration controls: P1.3 → ≥50-permutation
negative control; P1.4 → reconciliation-delta spot-check; **P1.5 → verify the crosstab and arm
construction against the parquet.** This is P1.5, so the crosstab+arm control is the applicable one
(the permutation/reconciliation controls belong to sibling studies and are out of scope here).

- **Crosstab genuine:** independently recomputed above; matches RESULTS.md and results.json exactly.
- **Arm construction genuine:** independently recomputed from the parquet —
  - ARMED-continuation: n=**1752**, episodes=**1322**, P(clean8_21)=**0.30651**
  - PRIME bottoming: n=**5448**, episodes=**3846**, P(clean8_21)=**0.33443**
  - Other ARMED: n=**0** (every `align_tier=='ARMED'` fire carries `weekly_phase=='rising'`;
    verified via the ARMED weekly_phase breakdown = `{rising: 1752}`). The RESULTS "Other ARMED n=0"
    diagnostic is correct, not an omission.
  - ARMED rows with null weekly_phase excluded: 0 (consistent with the all-rising breakdown).

All arm cardinalities and proportions match results.json to <0.01%.

---

## Check 3 — Trial-grid adherence, era/stamp discipline, BH family, n-floors, INSUFFICIENT-POWER honesty

**PASS.**

- **Trial grid (m=5).** T1 (ARMED/rising vs PRIME), T2 (RS Q1 vs Q2-Q4), T3 (RS Q1-Q2 vs Q3-Q4),
  T4 (above_200 T vs F), T5 (Q1+above corner) — all five registered trials present, none added,
  none dropped, all now defined on the `align_tier` arm. K4 (budget=5) honored.
- **Era/stamp discipline.** Verified against the parquet: signal_date range 2022-06-30 → 2026-07-02;
  **zero** rows before 2022-06-30 (so "0 stamped rows excluded" is because pre-2021 rows are genuinely
  absent, not because a filter silently dropped them); `survivor_bias` is False on all 961,656 rows;
  `price_source` is `massive` on all rows (S2 source condition met); `era_memo_version` stamped
  "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)" on every row. Verdict-grade fire filter
  (`verdict_grade==True & verdict_type=='fire'`) yields 49,939 fires — matches §APPROVAL substrate
  reference exactly. The `horizon_censored==False` filter is a no-op here: `verdict_grade==True` ⟺
  `horizon_censored==False` perfectly in this parquet (independently cross-tabbed), so n_hc=0 is
  correct, not a masking bug.
- **BH family (m=5).** Independently recomputed the full family with my own bootstrap + BH step-up:
  q = [**0.1225**, 0.2253, 0.8822, **0.0000**, 0.2700] — identical to RESULTS.md. T1 q=0.1225 (not
  significant at 0.10); T4 q=0.0 (significant). Halves split at registered midpoint 2024-03-30.
- **n-floors (K1).** ARMED-continuation = 1322 episodes ≥ 100 floor → K1 PASS. K2 null coverage:
  rs_sector_quartile null 7.67% and above_200 null 0.00%, both < 20% → K2 PASS (independently
  recomputed). Study is powered; correctly does NOT return INSUFFICIENT-POWER, and does not borrow
  from stamped rows (there are none to borrow).
- **INSUFFICIENT-POWER honesty.** The K1 gate is coded to HALT below 100 episodes; not triggered
  here because the cell is well-powered. No laundering.

---

## Check 4 — ≥3 headline numbers recomputed independently from the parquet

**PASS — 10+ recomputed, all match to <0.01%.** Independently from
`data/replay/replay_boarded.parquet` (my own code, not the runner's):

| Quantity | Independent recompute | results.json | Match |
|---|---|---|---|
| T1 Δ (ARMED-cont − PRIME) | −0.02793 | −0.02793 | ✓ |
| ARMED-cont P(clean8_21) | 0.30651 | 0.30651 | ✓ |
| PRIME P(clean8_21) | 0.33443 | 0.33443 | ✓ |
| ARMED-cont n / episodes | 1752 / 1322 | 1752 / 1322 | ✓ |
| PRIME n / episodes | 5448 / 3846 | 5448 / 3846 | ✓ |
| Stop-out Δ | +0.0106 | +0.0106 | ✓ |
| Both-halves H1 / H2 Δ | −0.0146 / −0.0539 | −0.0146 / −0.0539 | ✓ |
| Per-name majority | 410/642 = 0.639 | 410/642 = 0.639 | ✓ |
| T4 Δ (above_200 T vs F) | −0.1206 | −0.1206 | ✓ |
| T1 bootstrap p (seed 42) | 0.0490 | 0.0490 | ✓ |
| BH q-family (m=5) | [0.1225, .2253, .8822, 0, .2700] | same | ✓ |
| verdict-grade fires | 49939 | 49939 | ✓ |
| align_tier NaN / total fire clusters | 38573 / 22295 | 38573 / 22295 | ✓ |
| board_rank_unresolved (ac / pf) | 418 / 1321 | 418 / 1321 | ✓ |

MC note on the T1 bootstrap: p straddles 0.05 across seeds (0.0484–0.0524), but this is immaterial —
after BH the q is 0.1225 > 0.10 (not significant), and the verdict rests on the |Δ|<5pp materiality
disjunct, not on significance. So bootstrap MC noise cannot flip the verdict.

**Artifact-reproducibility:** I re-ran `run_P1_5_CONTINUATION_v2.py` end-to-end; the produced
RESULTS.md and results.json are **byte-identical** to the committed artifacts (diff clean). The
script is deterministic (seeded bootstrap) and the on-disk artifacts are not hand-edited.

---

## Check 5 — RESULTS.md honesty surface

**PASS.**
- **Leads with the verdict:** line 3 = "**PRIMARY VERDICT: H-MISLABEL**".
- **"Round-1 defect and fix" section present** (documents the `tier_cascade`→`align_tier` fix,
  the manufactured-gap withdrawal, and that only the partition INPUTS changed).
- **Plain-English box present** ("## In plain English"), correct numbers (30.7% vs 33.4%, −2.8pp,
  below the 5-pt bar, label-not-gate fix, additive-lanes R7).
- **Run recorded as round 2 — defect-corrected re-run** (RESULTS.md + results.json `run_label`).
- Mandatory §2.3 stamp text present; calibration crosstab, both-halves grid, per-name majority,
  coverage line, leak-audit, and board_rank_unresolved descriptive line all present.

---

## Decision-rule conformance (PREREG §6)

The v2 branch chain evaluates, in PREREG order: H-UNDERRANK (Δ>+5pp) → H-EXCLUDE (Δ<−5pp) →
H-MISLABEL (|Δ|<5pp) → H-MISLABEL 2nd disjunct → decision-gap → H-NULL → AMBIGUOUS. With
Δ=−0.0279 only `|Δ|<0.05` fires → **H-MISLABEL** (first disjunct). This is faithful to §6:
materiality is checked first; |Δ|=2.79pp < 5pp is "not materially different" and governs
regardless of significance. AMBIGUOUS does not fire (signs stable both halves, per-name majority
passes — both independently confirmed). The landing is clean and correctly maps to the registered
action: relabel into an explicit continuation lane (additive-lanes R7), **no gate change, no rank
change**. The T4 BH-significant sub-result (below-200 continuation fires grade +12pp better) is
correctly reported as diagnostic context that does NOT override the T1 verdict (§6 sub-partition
clause), and is now computed on the corrected `align_tier` arm as REVIEW round-1 requested.

---

## ADVISORY findings (all low-severity; all round-1 carryovers, now addressed)

- **A2 (window date reconciliation) — RESOLVED.** RESULTS.md states both the data boundary
  (2026-07-02) and the last-graded-fire date (2025-12-29), explaining fires stop ~6 months earlier
  so the 21-day horizon fits. Independently confirmed: last fire signal_date = 2025-12-29.
- **A3 (board_rank_unresolved descriptive line) — RESOLVED.** Now surfaced (ac=418, pf=1321,
  descriptive-only, no keep/demote/flip), satisfying memo §6.3 / §APPROVAL cl.4.
- **A4 (MAE proxy) — RESOLVED.** The `fwd_mae_21d`→`fwd_mdd_21` substitution is now explicitly
  stamped in the leak-audit and the secondary table footnote; secondary/context only, never verdict.

None of these touch the verdict.

---

## Per-check results

| # | Check | Result |
|---|---|---|
| 1 | Round-1 BLOCKING defect (B1) demonstrably dead; corrected mechanism reproduced on trials | **PASS** |
| 2 | Calibration controls genuine (P1.5: crosstab + arm construction vs parquet) | **PASS** |
| 3 | Trial-grid adherence, era/stamp discipline, BH family (m=5), n-floors, INSUFFICIENT-POWER honesty | **PASS** |
| 4 | ≥3 headline numbers recomputed independently from replay_boarded.parquet | **PASS (14 recomputed)** |
| 5 | RESULTS.md leads with verdict; 'Round-1 defect and fix' section; plain-English box | **PASS** |

---

## Bottom line for the Fable orchestrator

The round-2 defect-corrected re-run is **CONFORMANT**. The round-1 `tier_cascade` mis-map is dead —
the arms are now on the PREREG-registered `align_tier` column, and I independently reproduced both
the wrong round-1 Δ (−5.49pp, on `tier_cascade`) and the correct round-2 Δ (−2.79pp, on
`align_tier`). |Δ|=2.79pp is below the 5pp materiality bar and BH q(T1)=0.1225 is not significant,
so PREREG §6 resolves cleanly to **H-MISLABEL** (relabel continuation fires into an explicit lane;
no gate change, no rank change) with no decision-table gap. All 14 spot-checked headline numbers
reproduce to <0.01%, the committed artifacts are byte-identical to a fresh run of the v2 code, era/
stamp/BH/n-floor discipline holds, and the three round-1 advisories are resolved in-artifact. No
BLOCKING findings. Accept the round-2 result and the withdrawal of the round-1 blocker.
