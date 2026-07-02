# Wave-2 Report — Out-of-Sample Confirmation of the COILED Ranking Bonus

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE spec; §8 ledger carries the
> wave-2 directive) and `research/entry_timing/WAVE1_REPORT.md` (wave-1 results). Machinery reused:
> `research/entry_timing/wave1.py` (labels, features, fires via `tuning_harness`, per-fire outcomes),
> extended by `research/entry_timing/wave2.py`.
>
> **Mandate (spec §8 wave-2 directive):** confirm that the wave-1 COILED / STAR edge —
> `m2d_s3d trigger × cohort-washout arming (H6) × bullish-divergence co-condition (H3)` — survives
> **out of sample** before any engine wiring, shipped as a **ranking bonus / surfacing tier, NOT a
> hard gate**. The gates below (G1-G4, STAR additivity) were **pre-registered in wave 1** and are
> graded here **exactly as written — no re-interpretation, no threshold edits** (spec §7).

---

## 0. Verdict at a glance

| gate | verdict | headline numbers |
|---|---|---|
| **G1** fold stability (stocks) | **PASS** | 4/5 folds spread>0; pooled +6.69pp; COILED stop5 39.07 ≤ NCW 44.54 |
| **G2** basket replication (OOS, decisive) | **PASS** | sector-cohort +7.54pp; both time halves same sign; stop5 −5.64pp (better); n_COILED=6,842; per-name maj 65.24% |
| **G3** robustness (both panels) | **PASS** | clean10/15/20/30/h189 all positive both panels; COILED dead-money < NCW both panels |
| **G4** ranking (both panels) | **PASS** | Spearman=1.0, Q4−Q1 +10.19pp (stocks) / +10.5pp (baskets) |
| **STAR additivity** (report) | **holds, both panels** | STAR clean15 ≥ COILED AND STAR stop5 ≤ COILED on stocks and baskets |

**SHIP RULE (pre-committed): ship the COILED ranking bonus iff G1 AND G2 AND G3 all pass.**
G1, G2, G3 all PASS → **SHIP the COILED ranking bonus** (surfacing tier / ranking weight, not a hard
gate — per the spec directive; T8 recall shows a hard gate would gut the watchlist). G4 passing on both
panels supports a **graded** (quartile-scored) rather than binary bonus. STAR is the higher-conviction
sub-cell.

---

## 1. Config & panels

Two panels, produced by `research/entry_timing/wave2.py` (reuses `wave1.py` labels/features/outcomes):

| | **stocks (in-sample-tuned)** | **baskets (OUT-OF-SAMPLE, decisive for G2)** |
|---|---|---|
| data_dir | `data/stocks/*.parquet` | `data/baskets/ohlcv/*.parquet` |
| names (≥ min_bars) | 211 | **2,336** |
| min_bars | 1,500 | 1,000 |
| eval_start | 2012-01-01 | 2015-01-01 |
| m2d_s3d fires | 12,797 | **102,408** |
| base3d fires | 8,020 | 64,378 |
| cohort source | `constituents.parquet` (503) | basket_sector_map (503) ⊕ constituents (503), union 504 |
| runtime | 73.5s (6 workers) | 840.5s (6 workers) |

- **Trigger:** `m2d_s3d` (2D MACD × 3D StochRSI) — the wave-1 gate passer. `base3d` carried as reference.
- **COILED (sector):** `in_washout_ctx AND h6_cohort_sector ≥ 0.40` (≥40% of GICS-sector peers weekly-D<30).
- **noncoiled_washout (NCW):** `in_washout_ctx AND h6_cohort_sector < 0.40` (in-washout but lone).
- **STAR:** `COILED AND bull_div` (H6 ∩ H3).
- **Per-fire metrics (§4.2):** stop5 (−5% before +5%), clean15 (+15% before −5% within 126d), plus
  clean10/20/30 and clean15_h189 (189d horizon), dead_money (63d, never ±8%, ends < +5%).
- **Splits:** time half = fill pre/post-2020-01-01; folds = fill-date quintiles with a 180-calendar-day
  purge after each fold boundary (T2, stocks); active/inactive basket membership; theme vs sector cohort.

**The basket panel is the OOS answer.** The COILED thresholds (H6 ≥ 0.40, the STAR = COILED∩bull_div
composite) were **fixed in wave 1 on the 211-name stocks panel**. The 2,336-name basket panel — a
different universe, a different eval window (2015+ vs 2012+), a different cohort construction — was never
used to tune anything. G2 is graded there precisely so the verdict cannot be a selection artifact of the
stocks panel (see §7 caveats).

---

## 2. Verbatim gate grading (with numbers)

### G1 — fold stability, stocks
> *COILED-vs-noncoiled_washout clean15 spread > 0 in ≥ 4/5 time folds AND pooled spread ≥ 4pp AND
> pooled COILED stop5 ≤ noncoiled stop5.*

Per-fold clean15 spread (COILED − NCW), stocks T2 (fill-date quintiles, 180d purge):

| fold | window | n_COILED | n_NCW | clean15 spread | stop5 spread |
|---:|---|---:|---:|---:|---:|
| 0 | 2012-01 → 2015-03 | 382 | 488 | **−2.76** | +2.53 |
| 1 | 2015-08 → 2017-12 | 407 | 517 | **+13.96** | −9.30 |
| 2 | 2018-06 → 2020-09 | 601 | 773 | **+12.25** | −8.49 |
| 3 | 2021-03 → 2023-05 | 769 | 555 | **+8.70** | −10.34 |
| 4 | 2023-11 → 2025-12 | 490 | 596 | **+8.75** | −6.55 |

- Spread > 0 in **4 of 5 folds** (all but fold 0). **≥ 4/5 → PASS clause.** ✓
- Pooled (T1): COILED clean15 39.29 − NCW 32.60 = **+6.69pp ≥ 4pp.** ✓
- Pooled COILED stop5 **39.07 ≤** NCW stop5 **44.54.** ✓

**G1 = PASS.** (Fold 0, 2012-15, is the only miss — a low-dispersion post-GFC bull leg where the cohort
signal is weak and stop5 spread also inverts; every fold from 2015 on is strongly positive on clean15
and strongly negative on stop5, i.e. COILED both cleans more and stops less.)

### G2 — basket replication (decisive, OOS)
> *sector-cohort COILED-vs-noncoiled clean15 spread ≥ 3pp; same sign in BOTH time halves; COILED stop5
> not worse than noncoiled by > 1pp; n_COILED ≥ 500; per-name majority ≥ 55% (T4, ≥ 3 fires each stratum).*

Baskets T1 (sector cohort) + T3 (time halves) + T4 (per-name):

| metric | value | clause | verdict |
|---|---|---|---|
| sector COILED clean15 | 38.70 (n=6,842) | | |
| sector NCW clean15 | 31.16 (n=6,893) | | |
| **clean15 spread** | **+7.54pp** | ≥ 3pp | ✓ |
| pre-2020 spread | COILED 40.15 − NCW 27.66 = **+12.49** (n_C=2,426) | sign + | ✓ |
| post-2020 spread | COILED 37.91 − NCW 33.11 = **+4.80** (n_C=4,416) | sign + | ✓ |
| both halves same sign (positive) | yes | required | ✓ |
| COILED stop5 vs NCW stop5 | 40.22 vs 45.86 → COILED **−5.64pp (better)** | not worse by >1pp | ✓ |
| **n_COILED** | **6,842** | ≥ 500 | ✓ |
| per-name majority (T4, ≥3 fires each) | **65.24%** of 492 qualifying names | ≥ 55% | ✓ |

**G2 = PASS.** Every clause clears with margin. The edge is *larger* OOS on the spread axis (+7.54pp vs
+6.69pp stocks) and identical in shape (COILED cleans more, stops less, dead-moneys less). The magnitude
attenuates post-2020 (+12.49 → +4.80) but stays clearly positive and above the 3pp bar in the post-half
alone.

### G3 — robustness (both panels)
> *COILED clean-spread sign preserved at clean10/clean20/clean30 and clean15_h189 on BOTH panels;
> COILED dead_money < noncoiled dead_money on both panels.*

COILED − NCW spread (pp) at every horizon:

| horizon | stocks | baskets |
|---|---:|---:|
| clean10 | +5.49 | +7.19 |
| clean15 | +6.69 | +7.54 |
| clean20 | +6.09 | +6.50 |
| clean30 | +4.90 | +3.76 |
| clean15_h189 | +6.12 | +7.11 |
| **dead_money (COILED < NCW?)** | 7.28 < 9.48 ✓ | 6.15 < 8.33 ✓ |

**G3 = PASS.** All five clean-liftoff horizons are positive on **both** panels, and COILED carries lower
dead-money on both. The edge is not a clean15-barrier artifact — it holds from +10% through +30% and out
to a 189-day window.

### G4 — ranking (informs graded-vs-binary bonus; NOT a ship blocker)
> *T5 quartiles: Spearman of quartile clean15 means > 0 AND Q4−Q1 ≥ 3pp, on both panels.*

Quartiles cut by cohort-washout intensity (T5):

| panel | Q1 clean15 | Q2 | Q3 | Q4 | Spearman r | Q4−Q1 |
|---|---:|---:|---:|---:|---:|---:|
| stocks | 31.55 | 33.60 | 36.87 | 41.74 | **1.0** | **+10.19** |
| baskets | 30.78 | 31.58 | 36.05 | 41.28 | **1.0** | **+10.5** |

**G4 = PASS on both panels.** Quartile clean15 is **monotone** (Spearman 1.0) and Q4−Q1 ≥ 3pp on both.
This supports a **graded** ranking bonus (score by cohort intensity) rather than a binary COILED flag —
the discrimination is continuous, not a threshold cliff.

### STAR additivity (report only)
> *STAR clean15 ≥ COILED clean15 AND STAR stop5 ≤ COILED stop5, directionally on both panels.*

| panel | STAR clean15 | COILED clean15 | STAR stop5 | COILED stop5 | additive? |
|---|---:|---:|---:|---:|:--|
| stocks | 41.09 | 39.29 | 34.71 | 39.07 | **yes** (+1.80 clean, −4.36 stop) |
| baskets | 39.69 | 38.70 | 37.83 | 40.22 | **yes** (+0.99 clean, −2.39 stop) |

**STAR additivity holds on both panels.** The divergence co-condition (H3) supplies the stop-out relief
COILED lacks — STAR stops out materially less than COILED while cleaning at least as often, reproducing
the wave-1 "STAR beats the oracle on clean15 with the best stop-out" story out of sample. The clean-lift
increment shrinks OOS (+0.99pp vs +1.80pp), but the **stop-out** relief is the load-bearing STAR virtue
and survives clearly on both panels.

---

## 3. T1–T8 highlights

**T1 (per-stratum economics), m2d_s3d:**
- The ladder is monotone on both panels: **ALL < in_washout < NCW < coiled_no_div < COILED < STAR** on
  clean15, with the mirror ordering on stop5. On baskets: ALL clean15 31.14 / stop5 47.44 → COILED
  38.70 / 40.22 → STAR 39.69 / 37.83.
- **`div_only_noncoiled`** (bull_div but NOT cohort-confirmed) is a dud on both panels: baskets clean15
  31.63 / stop5 48.46 (worse than ALL). Divergence **alone** carries no edge — it only pays off *inside*
  the cohort-washout (STAR). This is the OOS confirmation that H3 is a co-condition, never a standalone
  (matching wave-1 §2 "H3 fails alone").
- **base3d** carries the same COILED edge but weaker (stocks COILED clean15 37.47 vs m2d 39.29; baskets
  36.95 vs 38.70) — confirming wave-1's finding that the 2D trigger's earlier, cohort-catching fires are
  what push the stratum over the bar.

**T2 (stocks folds):** see G1. Every fold from 2015 on: clean15 +8.7 to +14.0pp, stop5 −6.6 to −10.3pp.

**T3 (baskets cuts):** time halves both positive (G2). **Active vs inactive:** COILED fires are almost
entirely on **active** members (n=6,842 active vs 0 inactive on the sector cohort) — the sector cohort is
built from current basket members, so delisted/removed names have no sector peers and never reach COILED.
This is a **selection caveat, not a leak** (see §6): the OOS COILED cell is effectively an active-name
cell. Theme-cohort inactive cells exist but are tiny (n=28/27) and non-load-bearing.

**T4 (per-name majority):** stocks coiled_vs_ncw 65.55% of 209 names; baskets 65.24% of 492 names — a
clean ~2:1 per-name majority on both, so the pooled spread is not a few-name artifact. STAR vs
non-star-washout: stocks 62.22% (180 names), baskets 55.85% (410 names) — STAR majority holds OOS but is
thinner (55.85%, just over the 55% bar had it been required for STAR).

**T5 (ranking):** see G4 — Spearman 1.0 both panels.

**T6 (threshold sensitivity):** the COILED edge is stable across cohort thresholds {0.3, 0.4, 0.5} and
robust to the peer-D definition (proxy stored-D<30 vs exact D<30 give identical rows). Baskets clean15
spread: 0.3→+5.93, 0.4→+7.54, 0.5→+7.41. The 0.40 threshold (chosen in wave 1) is near the peak and not
a knife-edge — reassuring against threshold-mining.

**T8 (recall economics — the hard-gate warning):** on baskets, ALL m2d_s3d fires recall 59.71% of B15
durable bottoms; **COILED recalls only 7.35%, STAR only 1.89%.** COILED is ~6.7% of fire volume; a HARD
COILED gate would cut durable-bottom recall by ~88% — exactly the §9.3 watchlist-gutting the spec forbids.
This is the mechanical reason the directive specifies a **ranking bonus / surfacing tier, not a gate**,
and the numbers confirm it OOS. COILED's *trap-fire* rate is correspondingly low (baskets 4.14% vs ALL
50.91%): COILED is a high-precision, low-recall surfacing cell — the right shape for a ranking bonus.

---

## 4. Side-study readings (spec §8: wave-2 side studies)

Stocks-panel T7 (m2d_s3d). These are exploratory, not gated.

- **trap_state dead-money veto (H5 carry-over):** *within COILED*, splitting on `trap_state` gives
  COILED_trap_T clean15 38.67 / dead_money 6.54 vs COILED_trap_F clean15 39.95 / dead_money 8.07. The
  wave-1 hope was that trap_state=T marks *lower* dead-money; **inside COILED that inverts** —
  trap_state=T has the *lower* dead-money here but also *lower* clean15, and the gap is small (≈1.3pp
  clean, ≈1.5pp dead). Net: **trap_state adds nothing useful once you are already COILED** — the cohort
  arming already captured the dead-money relief (COILED dead-money 7.28 vs ALL 14.60). The trap_state
  veto is **not worth carrying** as a COILED refinement.

- **failed2 (self-aware "cried-wolf"):** the wave-1 inversion **replicates**. `ALL_failed2_T` clean15
  36.35 / dead_money 11.06 vs `ALL_failed2_F` clean15 33.20 / dead_money 16.61 — fires *with* ≥2 recent
  failed fires clean15 **higher** and dead-money **much lower**. Serial failure is mean-reversion fuel,
  not a veto (confirms wave-1 ledger). *Within STAR*, failed2 is a wash (T 40.66 / F 41.58 clean15,
  n=455/392) — STAR already selects the good cell, so failed2 no longer discriminates.

- **fromos3 rescue (deep-capitulation origin, D(3D) 8-bar min < 20):** the `fromos3 × COILED` 2×2 is the
  cleanest side-study. `fromos3_T_COILED_T` (n=2,614): clean15 38.83 / stop5 39.48 / dead 7.04, vs
  `fromos3_T_COILED_F` (n=5,983): clean15 33.08 / stop5 40.82 / dead 16.90. **COILED does the work on
  both the clean15 and (especially) the dead-money axis regardless of fromos3.** fromos3 alone
  (`fromos3_F_COILED_T`, n=560) is actually the highest clean15 cell (41.43) but small; the dominant
  read is that **COILED is the load-bearing split, fromos3 is a minor modifier.** No standalone fromos3
  rescue of the non-COILED cohort.

---

## 5. Active-vs-inactive and theme-vs-sector cohort comparisons (baskets)

**Active vs inactive (T3, sector cohort):** COILED fires land almost entirely on active members
(6,842 active / 0 inactive), because the sector cohort matrix is built only from tickers with a mapped
sector (current basket members). Consequence: the OOS COILED result is effectively an **active-name
result**. This does *not* invalidate G2 (the spread is COILED-vs-NCW *within the same active universe*),
but it means the COILED bonus, as built, only fires on names that currently have live sector peers — see
the survivorship caveat in §6.

**Theme vs sector cohort (T3):** the mechanism generalizes to the *theme* cohort (co-members across all
baskets, not just GICS sector):

| cohort | COILED clean15 | NCW clean15 | spread | COILED stop5 | NCW stop5 |
|---|---:|---:|---:|---:|---:|
| **sector** (all) | 38.70 (n=6,842) | 31.16 (n=6,893) | **+7.54** | 40.22 | 45.86 |
| **theme** (all) | 37.30 (n=9,333) | 31.40 (n=8,872) | **+5.90** | 42.28 | 46.62 |

Both time halves positive on the theme cohort too (pre +10.36, post +3.52). The **sector** cohort is the
sharper discriminator (larger spread, lower COILED stop5), so sector cohort is the recommended arming
signal; theme cohort is a valid fallback where a name has basket co-members but no mapped GICS sector.

---

## 6. Honest caveats

1. **Selection-effect defense.** The obvious objection is that COILED/STAR were *chosen* on the stocks
   panel, so their stocks-panel win is circular. Defense: (a) the thresholds (H6 ≥ 0.40, STAR = COILED ∩
   bull_div) were **pre-registered in wave 1** and are unchanged here — no wave-2 threshold search; (b)
   the **basket panel is the OOS answer** — a 2,336-name universe, different eval window, different cohort
   construction, never used to fit anything — and G2 passes there with a *larger* spread (+7.54 vs +6.69).
   The wave-2 gates were also pre-registered. This is confirmation, not mining. T6 further shows the edge
   is not a knife-edge at the chosen threshold.

2. **Overlapping-fire serial correlation → effective n < printed n.** Fires on the same name days apart
   share overlapping 126-day forward windows, so outcomes are serially correlated; the printed n
   (3,174 COILED stocks; 6,842 baskets) **overstates** the independent sample size. The per-name majority
   tests (T4: 65% of 209 / 492 names) and the fold/time-half splits (G1, G2) are the defenses — they show
   the edge is spread across *names and regimes*, not concentrated in a few autocorrelated clusters. But
   all standard errors on the pooled rates should be read as wider than iid would imply; treat the pooled
   spreads as directional, and lean on the per-name majority + split consistency for confidence.

3. **Survivorship / active-name bias (baskets).** COILED fires only on active members with live sector
   peers (T3: 0 inactive COILED fires). The 199 delisted names (`_closes_delisted.parquet`) and removed
   members are effectively outside the COILED cell. Absolute clean15 rates are therefore inflated by
   survivorship (as in every panel here); the load-bearing quantity remains the **stratum-vs-stratum
   spread within the same universe**, which survivorship biases roughly equally on both sides.

4. **Close-based barriers.** stop5/clean15 use close crossings, not intrabar highs/lows (no US intraday,
   no open). Real fills clip stops slightly more often; the bias applies equally to COILED and NCW, so it
   shifts absolute rates, not the spread verdicts. Baskets carry full OHLCV, so the secondary `low_stop5`
   lens is available there if a follow-up wants the intrabar read.

5. **Fold 0 (2012-15) miss on stocks.** G1 tolerates 1/5 by design; fold 0 is a genuine regime where the
   cohort signal is weak (low cross-sectional dispersion, post-GFC melt-up). The edge is a
   **washout/dispersion-regime** phenomenon — expect it to be quiet in low-vol bull legs. This is
   consistent with the post-2020 attenuation on baskets (+12.49 → +4.80). The bonus should be understood
   as *conditional on there being cohort washouts to detect*, not an all-weather constant.

6. **Recall floor (T8).** COILED/STAR are high-precision, low-recall cells (COILED recalls 7% of durable
   bottoms). Shipped as a **ranking bonus / surfacing tier** this is correct (it re-orders the watchlist,
   it does not remove names). Shipped as a hard gate it would gut recall ~88% and violate §4.3 / §9.3 —
   do **not** wire it as a gate.

---

## 7. Ship recommendation

**SHIP the COILED ranking bonus** — G1 ∧ G2 ∧ G3 all pass (the pre-committed ship rule). Specifically:

- **Form:** a **graded ranking bonus / surfacing tier** (G4 supports graded over binary — quartile
  clean15 is monotone with Spearman 1.0 on both panels), applied to `m2d_s3d` fires, **never a hard gate**
  (T8: hard gate guts recall ~88%).
- **Arming:** sector cohort `h6_cohort_sector ≥ 0.40` on `in_washout_ctx` fires = COILED; add
  `bull_div` = STAR (higher-conviction sub-cell, better stop-out on both panels).
- **Cohort:** sector cohort preferred (sharper); theme cohort as fallback for unmapped names (§5).
- **Do NOT carry:** trap_state refinement (adds nothing inside COILED), failed2 as a veto (inverts —
  it is mean-reversion fuel), div_only (H3 alone is a dud), fromos3 as a standalone rescue.
- **Next before engine wiring (spec directive):** the directive also names `walk_forward.py`
  (train/test, purge, ≥70%-of-names OOS) as a pre-wiring step. G1's 180d-purge folds + G2's independent
  basket panel + T4 per-name majorities cover the OOS-generalization intent; a `walk_forward.py --gold`
  pass on the COILED subset would be the final belt-and-suspenders check before touching `engine/`.

---

## 8. Ledger entries (for §8 of the spec)

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-01 | **Wave 2 — COILED ranking bonus** (m2d_s3d × H6 cohort-washout × H3 divergence), stocks (211) + baskets (2,336) panels | **SHIP (G1∧G2∧G3 pass)** | G1 4/5 folds + pooled +6.69pp, stop 39.07≤44.54; G2 (OOS baskets) +7.54pp, both halves +, stop −5.64pp, n=6,842, maj 65.24%/492; G3 all horizons + both panels, dead-money COILED<NCW both | this report §2 |
| 2026-07-01 | **G4 ranking** | PASS both panels | Spearman 1.0, Q4−Q1 +10.19 (stocks) / +10.5 (baskets) → graded bonus | this report §2/§3 |
| 2026-07-01 | **STAR (COILED ∩ bull_div) additivity** | holds both panels | stocks STAR clean15 41.09 / stop5 34.71 vs COILED 39.29/39.07; baskets 39.69/37.83 vs 38.70/40.22 | this report §2 |
| 2026-07-01 | **div_only (H3 without cohort)** | FAILS OOS | baskets clean15 31.63 / stop5 48.46 (worse than ALL) — divergence pays off only inside cohort washout | this report §3 |
| 2026-07-01 | **trap_state veto within COILED** | not worth carrying | inside COILED, trap_state=T lower dead-money but lower clean15; cohort already captured the relief | this report §4 |
| 2026-07-01 | **failed2 inversion** | replicates (mean-reversion fuel, not a veto) | ALL_failed2_T clean15 36.35 / dead 11.06 vs F 33.20 / 16.61 | this report §4 |
| 2026-07-01 | **hard-gate recall check (T8)** | do NOT ship as gate | COILED recalls 7.35% of B15 (baskets) vs ALL 59.71% — hard gate guts recall ~88%; ship as ranking bonus | this report §3 |
