# Wave-5 Report — BASED / RETEST: post-cross re-admission

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE program spec; §2 tripwires
> and §4 constitution bind verbatim) and the binding pre-registration
> `research/entry_timing/WAVE5_PREREG.md` (v2, 2026-07-02, 4-reviewer adversarial panel). Problem
> statement: `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md`. Machinery reused by
> import (never reimplemented): `wave1.py` (`compute_outcomes`, `label_events`, `build_tf_grids`,
> `build_sector_d_matrix`, `get_cohort_frac`, capit/ATR constants), `wave2.py`
> (`compute_outcomes_w2`, `label_events_w2`, panel loaders, sector maps, `_serialize_d_matrix`
> FIX-1, the `Pool` pattern), `tuning_harness.py` (`rsi`, `ema`, `rsi_macd`, `stoch_rsi_kd`,
> `tf_bars`, `to_daily`, `VARIANTS`, `build_signals`), `engine/confluence_tiers.py` (`tier_stream`),
> `engine/signal_gate.py` (`gate`). New wave-5 code: the post-cross ladder, the seven entry
> policies, the causal ATR barriers, and the block-bootstrap.
>
> **Mandate (prereg §6):** grade BASED and RETEST against the pre-registered gates **exactly as
> written** — no re-interpretation, no threshold edits, no mid-run "improvement" (prereg §preamble,
> spec §7). Ship shape THIS wave, if anything ships, is a display chip + forward-ledger fields ONLY.
> The ship rule is applied verbatim; the kill rule is applied verbatim.

---

## 0. Verdict at a glance

| candidate | primary axis result | binding gates | **SHIP** |
|---|---|---|:--:|
| **BASED** chip (E_BASED, m2d_s3d, deep) | **E_BASED is byte-identical to P2 on every axis, split, stratum, and both triggers on both panels** | G5a **FAIL**, G5b FAIL, G5c FAIL, G5i FAIL (G5d/f/g PASS only trivially/hollow; G5j not run) | **NO** |
| **RETEST** marker (E_RETEST, frozen params) | non-inferior to FRESH **fails** (stop5 40.87 vs 40.68 bar; clean15 33.31 vs 34.91, −1.6pp) | G5r **FAIL** | **NO** |

**Ship recommendation (prereg §6 ship rule, verbatim, no reinterpretation):**
- BASED chip ships **iff G5a–G5j**. G5a, G5b, G5c, G5i are FAIL and G5j was not executed. → **BASED does NOT ship.**
- RETEST marker ships **iff additionally G5r**. G5r is FAIL, and the BASED prerequisite already failed. → **RETEST does NOT ship.**

**The one-sentence why (BASED):** the pre-registered `BASED_j` state, evaluated at the first eligible
day j = i+7, is *definitionally the same condition* as the P2 survival-parent (`NOT LAUNCHED_{i+7}
AND NOT BROKEN_{i+7}`), so `E_BASED` enters at i+7 for **every** P2-eligible fire and at the **same
price** — E_BASED and P2 are the identical policy, and "held-base flatness" carries **zero
incremental selection** over simply surviving seven days. The prereg's own corrected prior said this
was exactly the open question ("whether flatness carries any selection… stop-out improvement vs P2:
**uncertain**"); the answer is *none*.

**The one-sentence why (RETEST):** the frozen 2D re-cross event enters later, at a marginally worse
price, and is *worse* than the incumbent E_FRESH on both stop5 and clean15 — it misses its own
non-inferiority bar to FRESH and to BASED, so the tightened co-primary family fails outright.

---

## 1. Config & panels

Produced by `research/entry_timing/wave5.py` (imports wave1/wave2/tuning_harness primitives; new
code only for the ladder, the seven policies, the causal ATR barriers, and the block-bootstrap).
Fill = entry_bar + 1 close for every policy. Dates round-tripped as ISO strings in worker args
(the wave-2 ms→ns serialization bug class avoided via `_serialize_d_matrix` FIX-1). Multiprocessing:
6 workers, wave-2 `Pool` pattern.

| | **stocks** (deep panel) | **baskets** (decisive OOS) |
|---|---|---|
| panel glob | `data/stocks/*.parquet` | `data/baskets/ohlcv/*.parquet` |
| names (≥ min_bars) | **212** | **2,335** |
| min_bars | 1,500 | 1,000 |
| eval_start | 2012-01-01 | 2015-01-01 |
| time halves | pre / post 2020-01-01 | (OOS; halves same-sign check per G5d) |
| ticker halves | even / odd | even / odd |
| **fires (m2d_s3d, common fully-observed)** | **10,286** | **81,260** |
| fires (base3d, diagnostic) | 7,292 | 57,453 |
| dedupe | **21 trading days, first fire kept** (backward-looking) | 21 td, first fire |
| runtime | 95.7s | 424.3s |

**Fire sets & panels (prereg §2):** triggers `m2d_s3d` (primary) and `base3d` (diagnostic, cannot
ship), analyzed separately. Ladder j = i+1..i+30, LADDER_MAX = 30. **Common fully-observed fire
set** enforced once for all policies: a fire enters iff `i + LADDER_MAX + 1 + 126 ≤ n` — every policy
scored on the identical fire set, no per-policy end-of-panel censoring. CN deferred (prereg §2).

**Bootstrap / inference (prereg §4):** point estimates must clear their thresholds at the **90%
block-bootstrap lower bound, clustered on (name × 63-trading-day calendar block)**; n=1,000
resamples, α=0.10. Gate n-floors additionally require ≥ 60 distinct names and ≥ 40 distinct 63d
blocks. The stocks panel clears both floors (212 names, 56 blocks); baskets clears with margin
(2,334 names, 44 blocks).

**The seven policies (prereg §3), identical fire set, fill at bar+1 close:**

| policy | rule | role |
|---|---|---|
| `E_FRESH` | enters at i+1 | incumbent baseline |
| `P1 = E_STALE_i7` | enters at i+7 for EVERY common-set fire, no condition | immortal-time floor (reported, never a gate anchor) |
| `P2 = E_SURVIVE_i7` | enters at i+7 iff NOT LAUNCHED_{i+7} AND NOT BROKEN_{i+7} | **the correct parent class** — all BASED gates anchor here |
| `E_BASED` | first j ≥ i+7 with `BASED_j` = (j−i∈[7,24] ∧ ¬LAUNCHED_j ∧ ¬BROKEN_j) | the candidate |
| `E_DIP7` | lowest close in [i+7, i+24] among P2-survivors | hindsight-located placebo (never a candidate) |
| `E_LAUNCHED` | first j with LAUNCHED_j | negative control |
| `E_RETEST` | first j∈[i+3,i+30] with fresh 2D RSI-MACD cross-up, ¬LAUNCHED ∧ ¬BROKEN ∧ 3D-RSI14<65 | co-primary marker (frozen params) |

`LAUNCHED_j` = `maxup_j > 0.05 OR OBP_j` (OB-persist: 3D StochRSI k or d ≥ 80 on any bar in [i..j],
sticky — the JNJ loophole guard). `BROKEN_j` = `min(close[i+1..j]) < T×0.97`, T = trough over
`close[i−90..i]` (wave-1 capit window exactly).

---

## 2. The decisive structural finding — E_BASED ≡ P2 (identically, everywhere)

This is the report's headline and it is not a numerical near-miss: it is an **exact identity that
falls out of the pre-registered definitions.** Verified directly on both parquets:

```
both panels, both triggers:  E_BASED__fill_idx == P2__fill_idx  for 100% of filled rows
                             E_BASED__{stop5,clean15,dead_money,stop_atr,...} == P2__{...} EXACTLY
E_BASED entry offset:        always i+7 (no fire ever produced a later BASED entry)
n(E_BASED) == n(P2):         6,594 (stocks m2d) / 44,952 (baskets m2d) / 3,286 (stocks base3d) / 23,317 (baskets base3d)
```

**Why (mechanism, not a bug):** `E_BASED` is defined as the *first* j ≥ i+7 with `BASED_j`. At
j = i+7 the state `BASED_{i+7}` reduces to `(7 ∈ [7,24]) ∧ ¬LAUNCHED_{i+7} ∧ ¬BROKEN_{i+7}`, which is
*exactly* the P2 admission condition. So **every P2-eligible fire is already BASED at its first
eligible day**, and E_BASED can never wait past i+7. There is no fire that is P2-eligible but not
BASED-at-7, and none that becomes BASED only later. The prereg deleted the explicit ext floor/ceiling
band (amendment #1/#4) and anchored the state on trough (BROKEN) + launch (maxup/OB) — the very
guards that also define P2. The consequence is that BASED, as registered, is **the survival option
with a different name**, adding no selection.

Consequences that ripple through every gate below:
- Every `E_BASED − P2` difference is **0.000pp** on every axis, split, and stratum → the G5a stop5
  gap clause (needs ≤ −3pp) is exactly 0.0pp, and strict-superiority-over-FRESH cannot be met by a
  policy that equals the survival parent.
- G5g (per-name majority: E_BASED stop5 ≤ P2's) is **trivially 1.0** — E_BASED equals P2 on every
  name, so the "majority" clause passes for a reason that carries no information (flagged §5).
- G5f pooled |stop5(E_BASED) − stop5(P2)| = **0.0pp** → the H2 sub-gate is **not evaluated** by its
  own guard (correctly), not passed on merit.
- G5d "direction replicates" is satisfied because the direction is *identity* (0.0pp), not because
  BASED beat the parent OOS.

The honest translation: **the "held base" hypothesis, as pre-registered, is untestable against P2 —
it collapses onto P2 by construction.** The prereg's amendment #27 ("age-ceiling suspicion") already
suspected the [7,24] window might be the wrong instrument; the deeper problem is the state itself has
no content beyond survival-to-7. Any future wave must give BASED a *distinguishing* predicate
(e.g. an advance/level condition — the keeper's ext≥0 mechanism the prior flagged, or a tightness
band that is NOT co-extensive with survival) or it will keep collapsing.

---

## 3. §4 axes — every policy, both panels (primary trigger m2d_s3d)

Point estimates (means; stop5/clean15/dead_money/stop_atr/clean_atr are fractions×100 = pp;
mfe63/mae63/prem_trough as printed; days_to_10 in trading days). Bootstrap LBs for the gate-bearing
cells are in §6.

### stocks (deep panel), m2d_s3d, n_fires = 10,286

| policy | n | stop5 | clean15 | dead$ | stop_atr | clean_atr | mfe63 | mae63 | days→10 | prem_trough |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| E_FRESH | 10,286 | 40.18 | 34.91 | 14.90 | 60.56 | 38.24 | 12.1 | −7.3 | 47.9 | 14.0 |
| P1 | 10,286 | 40.20 | 34.30 | 15.00 | 61.40 | 37.40 | 11.9 | −7.4 | 48.2 | 14.6 |
| **P2** | **6,594** | **40.60** | **33.74** | **15.86** | **62.09** | **37.00** | **11.1** | **−7.2** | **49.7** | **11.6** |
| **E_BASED** | **6,594** | **40.60** | **33.74** | **15.86** | **62.09** | **37.00** | **11.1** | **−7.2** | **49.7** | **11.6** |
| E_DIP7 (placebo) | 6,594 | 20.11 | 48.67 | 13.20 | 40.20 | 58.30 | 14.3 | −4.7 | 40.6 | 8.9 |
| E_LAUNCHED (control) | 7,958 | 40.32 | 33.78 | 15.90 | 61.30 | 37.40 | 11.7 | −7.5 | 48.8 | 17.9 |
| E_RETEST | 2,405 | 40.87 | 33.31 | 16.80 | 62.20 | 37.00 | 10.9 | −7.0 | 51.4 | 13.1 |

### baskets (decisive OOS), m2d_s3d, n_fires = 81,260

| policy | n | stop5 | clean15 | dead$ | stop_atr | clean_atr | mfe63 | mae63 | days→10 | prem_trough |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| E_FRESH | 81,260 | 47.10 | 31.20 | 7.10 | 65.60 | 32.70 | 19.3 | −12.6 | 37.2 | 21.6 |
| P1 | 81,260 | 46.60 | 31.60 | 7.20 | 65.50 | 32.80 | 20.0 | −12.5 | 37.1 | 22.2 |
| **P2** | **44,952** | **46.00** | **31.30** | **8.80** | **65.70** | **32.90** | **17.9** | **−11.5** | **39.6** | **15.3** |
| **E_BASED** | **44,952** | **46.00** | **31.30** | **8.80** | **65.70** | **32.90** | **17.9** | **−11.5** | **39.6** | **15.3** |
| E_DIP7 (placebo) | 44,952 | 22.70 | 49.00 | 7.60 | 46.50 | 51.30 | 22.7 | −8.2 | 30.9 | 10.9 |
| E_LAUNCHED (control) | 62,792 | 47.50 | 30.90 | 7.10 | 65.80 | 32.70 | 19.6 | −12.7 | 37.2 | 27.9 |
| E_RETEST | 16,178 | 46.40 | 31.10 | 10.50 | 65.90 | 33.10 | 16.1 | −11.0 | 41.1 | 18.4 |

### Diagnostic trigger base3d (cannot ship — prereg §5)

| panel | policy | n | stop5 | clean15 | dead$ | stop_atr |
|---|---|---:|---:|---:|---:|---:|
| stocks | E_FRESH | 7,292 | 40.8 | 33.8 | 15.2 | 61.6 |
| stocks | P2 = E_BASED | 3,286 | 39.3 | 34.4 | 14.3 | 61.0 |
| stocks | E_RETEST | 1,135 | 40.2 | 34.5 | 17.4 | 60.6 |
| baskets | E_FRESH | 57,453 | 46.7 | 31.7 | 7.2 | 65.2 |
| baskets | P2 = E_BASED | 23,317 | 45.8 | 31.5 | 8.5 | 65.7 |
| baskets | E_RETEST | 8,176 | 46.1 | 30.7 | 10.1 | 66.0 |

`E_BASED == P2` exactly holds on base3d too (verified). The base3d read does not rescue BASED.

---

## 4. Splits and strata (primary: stocks m2d_s3d)

Because **E_BASED equals P2 in every cell**, the split/stratum tables serve two purposes: (a) confirm
the identity is not an artifact of any single slice, and (b) show, for the record, where E_BASED lands
relative to the *incumbent* E_FRESH (which is the only comparison where BASED could have shown a
Pareto win — it does not).

### 4.1 Splits — stop5 / clean15 (pp)

| split | n(FRESH) | n(P2=BASED) | E_FRESH s5 / c15 | P2=E_BASED s5 / c15 |
|---|---:|---:|---|---|
| ALL | 10,286 | 6,594 | 40.18 / 34.91 | 40.60 / 33.74 |
| time < 2020 | 5,728 | 3,854 | 38.72 / 34.10 | 39.08 / 33.76 |
| time ≥ 2020 | 4,558 | 2,740 | 42.01 / 35.94 | 42.74 / 33.72 |
| ticker even | 5,080 | 3,304 | 40.02 / 35.10 | 40.95 / 34.02 |
| ticker odd | 5,206 | 3,290 | 40.34 / 34.73 | 40.24 / 33.47 |
| excl-staples+healthcare (from gates.json) | — | 5,293 | — | 41.21 / 34.12 |
| excl-2025-01-01+ entries | 9,551 | 6,167 | 39.81 / 35.16 | 40.42 / 33.91 |

In every split E_BASED (= P2) is **worse than E_FRESH on stop5** (higher stop-out, +0.4 to +0.7pp)
and **worse on clean15** (−1.2 to −2.2pp). There is no split where the "held base" policy Pareto-beats
the incumbent; the direction is uniformly the wrong sign for the candidate.

### 4.2 Strata — E_BASED vs P2 (identity check) and vs E_FRESH (Pareto check)

| stratum | nB | E_BASED s5 / c15 | P2 s5 (==BASED?) | E_FRESH s5 / c15 |
|---|---:|---|---|---|
| cohort h6 ≥ 0.40 | 3,553 | 38.19 / 34.73 | 38.19 ✓ | 38.08 / 37.01 |
| cohort h6 < 0.40 | 3,013 | 43.38 / 32.49 | 43.38 ✓ | 42.24 / 32.77 |
| leadership lead63 ≥ 0 | 3,271 | 40.23 / 34.21 | 40.23 ✓ | 40.06 / 35.47 |
| leadership lead63 < 0 | 3,295 | 40.91 / 33.20 | 40.91 ✓ | 40.17 / 34.40 |
| chronic laggard lag252 < 0 | 2,793 | 41.64 / 35.02 | 41.64 ✓ | 40.45 / 35.43 |
| vol q1 (low ATR) | 1,484 | 38.68 / 30.32 | 38.68 ✓ | 38.58 / 30.32 |
| vol q2 | 1,433 | 39.01 / 32.52 | 39.01 ✓ | 37.77 / 33.59 |
| vol q3 | 1,407 | 41.86 / 34.04 | 41.86 ✓ | 42.39 / 32.91 |
| vol q4 | 1,257 | 40.02 / 36.20 | 40.02 ✓ | 41.08 / 37.19 |
| vol q5 (high ATR) | 1,013 | 44.62 / 37.02 | 44.62 ✓ | 41.08 / 40.54 |
| ext_j ≥ 0 at entry | 3,045 | 40.00 / 34.19 | 40.00 ✓ | 26.24 / 42.33 |
| ext_j < 0 at entry | 3,549 | 41.11 / 33.36 | 41.11 ✓ | 61.54 / 20.26 |
| above 200MA at entry | 4,013 | 40.94 / 33.14 | 40.94 ✓ | 40.97 / 32.37 |
| below 200MA at entry | 2,581 | 40.06 / 34.68 | 40.06 ✓ | 51.88 / 27.47 |
| H2-contrast: h2_good | 692 | 43.93 / 30.20 | 43.93 ✓ | 44.20 / 31.06 |
| H2-contrast: NOT h2_good | 5,902 | 40.21 / 34.16 | 40.21 ✓ | 39.63 / 35.44 |

**Every stratum confirms E_BASED == P2 (checkmark column).** The prereg's cohort-concentration
prediction (§1: "any real edge should CONCENTRATE in sector-favorable cells") has no edge to
concentrate — the cohort≥0.40 cell shows E_BASED s5 38.19 vs E_FRESH 38.08 (worse) and clean15 34.73
vs 37.01 (worse). The prereg's level-content probe (ext≥0 vs <0 stratification, added by amendment
#3) is uninformative for BASED because BASED equals P2 in both cells; the *E_FRESH* numbers in those
rows are the mechanical entry-endogeneity artifact of splitting by the entry-bar ext (fresh entries
at ext≥0 look great, at ext<0 look terrible — a tautology of where the split cuts, not a signal).

Baskets strata confirm the identity: cohort≥0.40 nB=6,449 E_BASED 40.70/33.99 == P2 40.70; cohort<0.40
nB=5,253 45.23/30.63 == P2 45.23; lead63≥0 43.89 == P2; lead63<0 41.47 == P2.

---

## 5. KM fire-survival curve, informative-dropout fractions

Because E_BASED = P2, the "informative dropout" (prereg §3: "fires eligible for P2 but never producing
a BASED entry") is **empty** — every P2-eligible fire produces a BASED entry at i+7. The informative
population is therefore the *upstream* dropout: fires that **fail P2-eligibility** by launching or
breaking in (i+1, i+7].

**Dropout composition (stocks m2d_s3d, N = 10,286 fires):**

| outcome by i+7 | n | fraction |
|---|---:|---:|
| P2-eligible → E_BASED enters at i+7 | 6,594 | **64.1%** |
| dropout — LAUNCHED by i+7 (maxup>5% or OB-persist) | 3,423 | **33.3%** |
| dropout — BROKEN by i+7 (only, not launched) | 269 | **2.6%** |

**KM-style fire-survival curve** — fraction of fires *still not launched* at offset j (first-launch
offset from `E_LAUNCHED__entry_off`; the launch leg is the dominant censoring event, breaks are 2.6%):

| j (offset) | i+1 | i+2 | i+3 | i+4 | i+5 | i+6 | **i+7** | i+10 | i+14 | i+18 | i+21 | **i+24** | i+30 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| survivors (%) | 95.0 | 91.9 | 88.2 | 83.2 | 77.7 | 72.0 | **66.7** | 56.6 | 46.7 | 38.4 | 33.2 | **29.0** | 22.6 |
| cum-launched (%) | 5.0 | 8.1 | 11.8 | 16.8 | 22.3 | 28.0 | **33.3** | 43.4 | 53.3 | 61.6 | 66.8 | **71.0** | 77.4 |

Reading: by the BASED window open (i+7) a third of fires have already launched — the m2d cross does
mostly work fast. Inside the [7,24] BASED window a further ~38pp of the panel launches (66.7% → 29.0%
survivors). The curve is smooth and monotone; there is no plateau at the window edge that would flag
the age-ceiling suspicion (amendment #27) as active in this panel — bases keep converting to launches
all the way to i+30. That does not save BASED (which equals P2), but it is the pre-named j-curve
arbiter and it argues *against* extending the window in a hypothetical wave-6: the density of "still
basing at day 24" is thin (29% survivors) and shrinking, not a reservoir of late launchers.

---

## 6. Gate table (G5a–G5j, G5r) — PASS/FAIL with decisive numbers

All bootstrap LBs from `wave5_gates.json` (n=1,000 block-resamples, α=0.10, 63d blocks; name-floor
60 / block-floor 40). Primary = E_BASED on m2d_s3d, deep panel unless noted.

| gate | clause (prereg §6) | decisive numbers | verdict |
|---|---|---|:--:|
| **G5a** existence | n≥400 + floors; stop5(BASED) ≤ stop5(P2)−3pp; clean15(BASED) ≥ clean15(P2)−1pp; non-inferior to FRESH; **strictly better than FRESH on ≥1 axis by ≥1pp** | n=6,594 ✓ (212 names, 56 blocks); **stop5 gap = 0.0pp** (need ≤ −3pp) ✗; clean gap 0.0pp ✓; ni_stop5 ✗ (BASED 40.60 lb 39.85 vs FRESH+1 = 41.18 — passes ni? point 40.60 > 40.18 so worse, ni_stop5=false); **strict_superiority = false** (no axis beats FRESH by 1pp) | **FAIL** |
| **G5b** ATR honesty | G5a stop clauses hold on stop_atr | stop_atr BASED 62.09 == P2 62.09 (gap 0.0pp, need ≤ −3pp); vs FRESH 60.56 (BASED worse) | **FAIL** |
| **G5c** anecdote independence | G5a inequalities at half margins, excl-staples+HC AND excl-2025+ | excl-staples+HC: BASED s5 41.21 == P2 41.21 (gap 0.0) ✗; excl-2025: BASED 40.46 == P2 40.46 (gap 0.0) ✗ | **FAIL** |
| **G5d** baskets OOS | G5a direction replicates; n≥1,200; both time halves same sign | n=44,952 ✓; BASED s5 45.99 == P2 45.99 → "direction" = identity (dir_ok=true, halves same sign=true) — passes **only because Δ=0**, not because BASED beat P2 | **PASS** (hollow — Δ=0) |
| **G5e** launched control + JNJ | stop5(LAUNCHED) ≥ FRESH+3pp OR clean15(LAUNCHED) ≤ FRESH−3pp; JNJ-2026 fixture | control: LAUNCHED s5 40.32 vs FRESH+3=43.18 ✗ AND clean15 33.78 vs FRESH−3=31.91 ✗ → **control_ok=false**; JNJ fixture **PASS** (OBP@j−i=7=True → E_BASED & E_RETEST both excluded before JNJ launch) | **FAIL** (control fails; fixture passes) |
| **G5f** H2 distinction | evaluated only if pooled \|stop5(BASED)−stop5(P2)\| ≥ 2pp | pooled gap = **0.0pp** < 2pp → **not evaluated** (guard) | **PASS** (vacuous — guard not met) |
| **G5g** per-name majority | frac(BASED s5 ≤ P2 AND clean15 within 2pp) ≥ 55% deep / 52% baskets, ticker-half stable | deep frac = **1.0** (212 names, both halves 1.0); baskets frac = 1.0 (2,323 names) — **trivially 1.0 because BASED==P2 on every name** | **PASS** (trivial — identity) |
| **G5i** placebo | BASED beats E_DIP7 on stop5 by ≥1pp AND clean15 not worse by >1pp | BASED s5 40.60 vs DIP7 20.11 → BASED s5 is **20.5pp HIGHER** (worse; DIP7 stops out far less) ✗; clean15 33.74 vs DIP7 48.67 → BASED −14.9pp ✗ | **FAIL** |
| **G5j** definitional stability | G5a verdict signs unchanged under maxup{4,5,6}×trough{.96,.97,.98} 3×3 sweep | **NOT EXECUTED** — gates.json records a stub ("requires re-run under alternate knobs; not on selftest"); SHIP block flags g5j_folded_in=false | **NOT RUN** |
| **G5r** RETEST (co-primary, tightened) | frozen params; ni to FRESH (s5 +0.5/c15 −1); ni to BASED (s5 +0.5/c15 −1); overlap ≤50%; JNJ; provisional disclosure | RETEST s5 40.87 vs FRESH+0.5=40.68 → **over by 0.19pp** → ni_fresh=false; c15 33.31 vs FRESH−1=33.91 → under by 0.60pp; ni_based=false; overlap 13.3% ✓; JNJ ✓ | **FAIL** |

**Note on G5a inference detail (from gates.json):** BASED stop5 point 40.598 (lb90 39.848), P2 stop5
40.598 — the `stop5_gap_ok` field is `false` (gap 0.0 ≥ −3pp bar). `clean_gap_ok` is `true` (0.0 ≥
−1pp). `ni_clean`/`ni_dead` mixed, but `strict_superiority` is `false` and `ni_stop5` is `false`, so
G5a fails on the strict-superiority floor (prereg's "no Pareto-loss chip" clause, amendment #9) even
before the stop-gap clause. E_BASED is, if anything, mildly *inferior* to FRESH (stop5 +0.42pp,
clean15 −1.17pp) — a Pareto loss, exactly what that floor was written to reject.

---

## 7. §7 leak-audit checklist (filled line-by-line)

| # | checklist item | status |
|---|---|---|
| 1 | Common fully-observed fire set `i + 31 + 126 ≤ n` enforced once for all policies | **OK** — single common set; n(all policies scored on the same 10,286 / 81,260 fires; P2/BASED/DIP7 share the 6,594/44,952 P2-eligible subset, no per-policy end-of-panel censoring). |
| 2 | Per-policy fill = entry_bar + 1; no policy fills before its signal knowable | **OK** — all `*__entry_off` ≥ 1; fill_idx = signal_idx + entry_off + 1 by construction; E_FRESH off=1, P1/P2/BASED off=7, verified. |
| 3 | E_RETEST 2D cross via `to_daily(...,'event')` known-date; assertion no fill precedes 2D known date | **OK** — E_RETEST located via event known-date mapping (not bin label); RETEST fills all at off ≥ 3; no fill precedes its 2D known date (harness assertion in wave5.py, no errors raised: `errors=0`). |
| 4 | ATR63 for barriers from bars ≤ fill_idx only (ewm atrp basis, read at fill) | **OK** — stop_atr/clean_atr use ATR63 = wave-1 ewm atrp basis read at the fill bar; no forward window. stop_atr numbers differ across policies by fill bar (FRESH 60.56 vs P2 62.09), consistent with per-fill-bar evaluation. |
| 5 | Leadership/laggard returns TRAILING, windows end at bar i | **OK** — lead63/lag252 computed as peers' trailing return to bar i minus SPY, bars ≤ i only (per prereg §4). |
| 6 | maxup_j/BROKEN_j/OBP_j windows bounded ≤ j; OB-persist scans [i..j] only | **OK** — LAUNCHED offset (E_LAUNCHED entry_off) is monotone-consistent with a ≤ j scan; OBP is sticky within [i..j]; JNJ fixture confirms OBP@j−i=7 fired correctly (backward-only). |
| 7 | trough_ref = close[max(0,i−90)..i] (pre-entry only, wave-1 capit basis) | **OK** — `trough` column = min over the 91-bar pre-cross window incl. i; identical to wave-1 capit; used in BROKEN only. |
| 8 | P1 "survives to i+7" = bar existence + common-set membership ONLY (no price cond.) | **OK** — P1 fills at i+7 for all 10,286 fires (== n_fires), no launch/break condition; it is the immortal-time floor. |
| 9 | Cohort matrix ISO-serialized (FIX-1); TF-native rolling before to_daily (FIX-2) | **OK** — sector D-matrix built via wave-2 `_serialize_d_matrix` (ISO strings in Pool args); D-matrix=211 close-matrix=211 built cleanly; no serialization error. |
| 10 | 21d dedupe keeps first fire, backward-looking only | **OK** — 21-trading-day per-name dedupe, first fire kept; selects on prior fires only (prereg §2). |
| 11 | dead_money end-of-panel dilution: common-set guard makes windows full — state it | **STATED** — the common fully-observed guard (`i+31+126 ≤ n`) makes every fire's 126d window fully observed, so dead_money is not diluted by truncated windows. |
| 12 | tier_stream (visibility) completed-bucket basis; provisional divergence disclosed | **DISCLOSED** — visibility descriptive uses `tier_stream` completed-bucket basis (§8); the 2D provisional-repaint rate (23.8% US, prereg §G5r) is the RETEST disclosure. |
| 13 | E_DIP7 hindsight-located BY DESIGN (placebo only, never a candidate) | **OK / DISCLOSED** — E_DIP7 = lowest close in [i+7,i+24], hindsight-located by design; used only as the G5i benchmark. Its stop5 (20.1%) is unattainable in real time. |
| 14 | JNJ-2026 fixture unit test runs BEFORE the panel | **OK** — JNJ@2026-06-05 (i=16214): first_launch_off=6, OBP@j−i=7=True, E_BASED_off=None, E_RETEST_off=None → PASS (excluded before launch via OB-persist). Recorded in gates.json `jnj_msg`. |
| 15 | No label field used as an input anywhere | **OK** — policies condition only on price/ATR/cohort features at bar ≤ j; label fields (stop5/clean15/...) are outputs, never inputs. |

**Leak audit: clean.** No policy fills before its signal is knowable; all barriers and states are
backward-bounded; the JNJ fixture passed pre-run. The E_BASED==P2 identity is a *definitional*
collapse, not a leak — both policies are legitimately causal, they are simply the same policy.

---

## 8. Descriptives (headline, non-binding — prereg §4)

From `wave5_descriptives_stocks.json` (stocks m2d_s3d):

- **Visibility-at-liftoff.** Among fires whose E_FRESH outcome was clean15 = 1 (n = 3,591 clean
  liftoffs), the fraction where `tier_stream` showed **no eligible tier on the liftoff day** (first
  close ≥ 1.05 × trailing-min) was **67.8%** under FRESH and **76.9%** under BASED (n = 6,591). So the
  incumbent gate is already blind to two-thirds of clean liftoffs at the moment of liftoff, and the
  BASED framing is *more* blind, not less — the "held base" names are, if anything, harder to see on
  the confluence stream, not a hidden reservoir the chip would surface. Descriptive only.
- **Natural re-trigger rate.** **77.6%** of BASED windows [i+7, i+24] already contain a fresh
  incumbent T1/T2/T3 re-fire. The gate largely self-heals: three-quarters of held bases get a new
  incumbent fire inside the window without any new chip. This undercuts the marginal value of a BASED
  chip even if it had shown selection.
- **Live-board sizing.** `surfaced_universe_size = 0` — the `us_standouts.json` was not present at
  descriptive-run time (produced only after a render), so the surfaced-vs-upstream-excluded split is
  deferred to the ship-PR against the live board (owner-review only, never a numeric gate). Not
  produced this wave.
- **Anchor-divergence study (ship-blocking check).** n_live = 98 names compared. Median j−i bar delta
  between the study raw-cross anchor (resample '3B') and the live `signal_gate` take_date anchor
  (session-grouped 3D) = **2.0 bars**; fraction with **> 2-bar** disagreement = **6.1%** (< 20%
  threshold). ext-delta: median −1.37%, abs-median 1.81%, fraction |Δext| > 5% = 15.3%. **ship_blocked
  = false** (the > 2-bar / > 20% rule is not tripped). The anchor study does NOT block a ship — but
  since nothing ships this wave, the reconciliation is moot; it is on record for whenever a chip is
  next proposed.

---

## 9. Ship verdict (prereg §6 ship rule, applied verbatim — no reinterpretation)

> Prereg §6: "**BASED chip iff G5a–G5j; RETEST marker iff additionally G5r.**" "Kill rule: failed
> gates → candidate does not ship; falsified cells appended to DURABLE_BOTTOM_FRAMEWORK §8 with numbers."

- **BASED chip requires G5a AND G5b AND G5c AND G5d AND G5e AND G5f AND G5g AND G5i AND G5j.**
  G5a FAIL, G5b FAIL, G5c FAIL, G5e FAIL, G5i FAIL; G5j NOT RUN. (G5d, G5f, G5g "pass" only because
  E_BASED ≡ P2 makes the Δ = 0 — hollow.) → **BASED does NOT ship.**
- **RETEST marker requires all of the above AND G5r.** G5r FAIL (non-inferior-to-FRESH missed on both
  axes); the BASED prerequisite already failed. → **RETEST does NOT ship.**

**Nothing ships this wave.** No `engine/coiled.py`, `scripts/build_stock_library.py`,
`scripts/grade_us_board.py`, or `templates/dashboard.html.j2` touch is triggered (prereg §6 required
touch-list is not exercised). `BUYABLE_TIERS`, `setups.json`, and discovery gating are untouched
regardless — consistent with the pre-registration. The falsified cells are appended to
`DURABLE_BOTTOM_FRAMEWORK.md` §8 per the kill rule.

**What was actually learned (the payload):** the "basing after confluence" intuition, *as
operationalized by the pre-registered `BASED_j` state*, is **not a distinct entry** — it is the
7-day survival option (P2) under another name, and the survival option is *mildly Pareto-inferior* to
entering fresh at i+1 (higher stop-out, lower clean15). The owner's live intuition (KO/MCD) is not
refuted at the *mechanism* level — it is that the mechanism the prereg wrote down does not isolate the
behavior the owner is pointing at (advance/reclaim/level-content), because the state has no predicate
beyond "didn't launch, didn't break." A future wave that wants to test "held base" must add a
*distinguishing* condition (a tightness or advance/level predicate that is NOT co-extensive with
survival-to-7) — otherwise it will keep collapsing onto P2.

---

## 10. Honest caveats

1. **The central result is a definitional collapse, not an estimated null.** E_BASED ≡ P2 is exact
   (0.0pp on every axis/split/stratum, both panels, both triggers). This is *stronger* than a
   statistical null — there is no sampling uncertainty in an identity — but it also means the wave
   **did not actually test "does a held base beat surviving 7 days"** with any power, because the two
   policies were made identical by the definitions. The honest verdict is "the pre-registered BASED
   state is untestable against P2," not "held bases have no edge." That distinction matters for
   whether a redesigned wave-6 is worth running (it is — see §9).

2. **G5j was not executed.** The 3×3 maxup×trough stability sweep is a stub in gates.json (deferred to
   an external sweep runner). Per the verbatim ship rule, a not-run gate cannot be treated as PASS, so
   BASED fails on G5j-not-satisfied independently of the G5a/b/c/e/i failures. Since BASED already
   fails five substantive gates and collapses onto P2, running G5j would not change the verdict — but
   the report does not claim G5j passed.

3. **Effective-n ≪ printed-n (overlapping windows).** Fires on the same name days apart share
   overlapping 126d forward windows → serially correlated outcomes; printed n (10,286 / 81,260)
   overstates independent sample size. The 21-day dedupe and the (name × 63d) block clustering in the
   bootstrap mitigate this, but the block floor on stocks (56 blocks) is modest — the "decisive"
   inference lives on the baskets panel (2,334 names, 44 blocks). None of this rescues BASED, whose
   failure is definitional, not marginal.

4. **RETEST's failure is on a real margin, not an identity.** Unlike BASED, E_RETEST is a genuinely
   distinct policy (n=2,405, overlap with incumbent 13.3%). Its failure is a true non-inferiority miss
   (stop5 40.87 vs 40.68 bar — over by 0.19pp; clean15 33.31 vs 33.91 bar — under by 0.60pp). The
   miss is small; a differently-parameterized retest is *not* falsified, but the frozen §3
   parameterization (the two live blockers removed, RSI14<65 + launch/broken/OB guard added) does not
   clear the tightened co-primary bar. The 23.8% 2D provisional-repaint rate is a further real-time
   hazard the marker would have had to disclose.

5. **Regime concentration.** The deep panel is 2012-2026 (14y, multiple regimes); the time-half split
   (pre/post-2020) is balanced (5,728 / 4,558 fires) — this is *not* a single-regime study, unlike the
   wave-3/4 CN legs. Good. But the excl-2025 split (which strips the owner's own KO/MCD episode) shows
   the same E_BASED==P2 identity, so the collapse is not a 2025-artifact.

6. **Survivorship.** The deep `data/stocks` panel is the surviving-names universe (212 names with ≥
   1,500 bars); delisted names are absent, so absolute stop5/clean15 rates are optimistic. The
   comparison is *within-panel* (BASED vs P2 vs FRESH on the same fires), so survivorship shifts all
   policies' absolute levels together and does not create the E_BASED==P2 identity — but it does mean
   the absolute rates (e.g. FRESH clean15 34.9%) should not be read as live-tradable hit-rates.

7. **The E_DIP7 placebo "wins" — read it correctly.** E_DIP7 has far lower stop5 (20.1%) and higher
   clean15 (48.7%) than everything, so G5i "fails" in the sense that BASED does not beat the placebo.
   This is *expected and by design*: E_DIP7 is hindsight-located (buys the actual lowest close in
   [i+7,i+24]), unattainable in real time (§7.13). It is a benchmark ceiling, not a candidate; its
   dominance simply confirms that a real dip-buyer would need forward knowledge BASED does not have.

8. **Descriptives are soft.** Live-board sizing was not produced (standouts.json absent pre-render);
   the anchor study ran on only 98 live names. Neither is gate-bearing, but the sizing descriptive the
   owner would review at ship time is deferred — moot this wave since nothing ships.

## 11. Wave-5b — registered post-gate strata (amendments #25/#26)

> **Discipline & honesty.** These are DIAGNOSTIC post-gate reads computed on the FROZEN wave-5 fire parquets *after* the §6 gate verdicts (all of which FAILED — nothing shipped). They cannot alter the wave-5 ship decision and are **promotable to a wave-6 primary only**. Multiplicity: 2 registered stratum families (#25 donor-unwind, 2 cells; #26 spring, 2 cells). Every feature uses bars ≤ entry (fill) only; the donor weekly bearish cross uses only COMPLETED W-FRI weeks (wave-1 `.shift(1)` prior-closed-week convention, mirrored for `xdn`); no outcome column is an input.

**Structural note carried from §2:** `E_BASED ≡ P2` exactly (E_BASED always enters at i+7 = the P2 entry), so the amendments' *E_BASED* reads are executed on the **P2** columns. The amendments predict where the (identical) P2/E_BASED clean15 and dead_money concentrate.

### 11.A Panel: stocks

Donor composites: 11 GICS sectors ({'Information Technology': 19, 'Health Care': 19, 'Consumer Staples': 19, 'Industrials': 21, 'Utilities': 19, 'Materials': 19, 'Real Estate': 19, 'Consumer Discretionary': 18, 'Financials': 20, 'Energy': 18, 'Communication Services': 20}). Entry-ticker GICS coverage: 10230/10286 fires (99%). Full coverage — donor + spring-group both clean.

#### #25 DONOR-UNWIND — {intact, cracking} × {P2, E_RETEST, E_FRESH}

`cracking` = donor_unwind TRUE (fresh weekly RSI-MACD bearish cross on the top-1 126d-EW-return GICS sector within the trailing 4 completed weeks, OR donor 20d EW return < 0 while still top-ranked). `intact` = otherwise.

| P2 | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 41.26 | 32.67 | 16.20 | 4561 | 212 |
| | cracking | 39.10 | 36.15 | 15.10 | 2033 | 212 |

| E_RETEST | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 41.58 | 31.33 | 16.79 | 1650 | 212 |
| | cracking | 39.34 | 37.62 | 16.95 | 755 | 206 |

| E_FRESH | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 41.24 | 32.91 | 15.14 | 6453 | 212 |
| | cracking | 38.40 | 38.27 | 14.56 | 3833 | 212 |

**Time halves + 2025+ (owner's episode), per policy:**

| P2 half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 39.79 | 32.24 | 20.27 | 2689 |
| pre2020 | cracking | 37.44 | 37.44 | 18.37 | 1154 |
| post2020 | intact | 43.38 | 33.28 | 10.36 | 1872 |
| post2020 | cracking | 41.30 | 34.47 | 10.81 | 879 |
| 2025+ | intact | 47.06 | 26.89 | 12.61 | 238 |
| 2025+ | cracking | 36.92 | 37.95 | 9.23 | 195 |

| E_RETEST half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 41.08 | 30.32 | 21.18 | 930 |
| pre2020 | cracking | 34.62 | 39.96 | 21.37 | 468 |
| post2020 | intact | 42.22 | 32.64 | 11.11 | 720 |
| post2020 | cracking | 47.04 | 33.80 | 9.76 | 287 |
| 2025+ | intact | 49.00 | 27.00 | 17.00 | 100 |
| 2025+ | cracking | 41.33 | 41.33 | 8.00 | 75 |

| E_FRESH half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 39.79 | 31.52 | 18.78 | 3604 |
| pre2020 | cracking | 36.87 | 38.57 | 18.79 | 2118 |
| post2020 | intact | 43.07 | 34.68 | 10.53 | 2849 |
| post2020 | cracking | 40.29 | 37.90 | 9.33 | 1715 |
| 2025+ | intact | 48.57 | 30.00 | 12.62 | 420 |
| 2025+ | cracking | 39.88 | 34.27 | 14.02 | 321 |

**Registered prediction #25 (two-sided, FULL panel):** clean15 concentrates in `cracking`; dead_money concentrates in `intact`. Held?

| policy | clean15↑ in cracking | dead_money↑ in intact | crack c15 / intact c15 | crack dm / intact dm |
|---|---|---|---|---|
| P2 | HELD | HELD | 36.15 / 32.67 | 15.10 / 16.20 |
| E_RETEST | HELD | FAILED | 37.62 / 31.33 | 16.95 / 16.79 |
| E_FRESH | HELD | HELD | 38.27 / 32.91 | 14.56 / 15.14 |

#### #26 SPRING — P2 entries, {spring, no_spring}

`spring` = (min close in [i+1..i+7] < pre-cross 10d min `min(close[i-10..i-1])`) AND (close[i+7] > that 10d min) — undercut the SHALLOW low and reclaimed it by entry. never-BROKEN guaranteed by P2. Price-only (H4 falsification bars volume legs).

| full | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 39.82 | 33.71 | 13.80 | 442 | 187 |
| | no_spring | 40.65 | 33.75 | 16.01 | 6152 | 212 |

**By GICS group (staples+healthcare vs rest):**

| staples_healthcare | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 35.80 | 32.10 | 12.35 | 81 | 34 |
| | no_spring | 38.28 | 32.21 | 20.49 | 1220 | 38 |

| rest | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 40.72 | 34.07 | 14.13 | 361 | 153 |
| | no_spring | 41.24 | 34.12 | 14.90 | 4932 | 174 |

**By vol quintile (ATR63% at fire bar; q1 = lowest ATR ~ registered low-beta read):**

| vol_q | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| q1 | spring | 42.17 | 27.71 | 30.12 | 83 |
| q1 | no_spring | 38.67 | 30.34 | 28.64 | 1236 |
| q2 | spring | 30.34 | 34.83 | 15.73 | 89 |
| q2 | no_spring | 38.94 | 31.87 | 23.33 | 1230 |
| q3 | spring | 37.89 | 38.95 | 13.68 | 95 |
| q3 | no_spring | 42.11 | 33.03 | 16.68 | 1223 |
| q4 | spring | 50.00 | 27.78 | 6.67 | 90 |
| q4 | no_spring | 38.97 | 37.35 | 8.14 | 1229 |
| q5 | spring | 38.82 | 38.82 | 3.53 | 85 |
| q5 | no_spring | 44.57 | 36.14 | 3.24 | 1234 |

**Registered prediction #26 (two-sided):** spring-present higher clean15 / lower dead_money than no-spring; strongest in low-beta/staples. Held?

| cohort | clean15 higher (spring) | dead_money lower (spring) | spring c15 / no c15 | spring dm / no dm | n spring / no |
|---|---|---|---|---|---|
| full | FAILED | HELD | 33.71 / 33.75 | 13.80 / 16.01 | 442 / 6152 |
| staples+healthcare | FAILED | HELD | 32.10 / 32.21 | 12.35 / 20.49 | 81 / 1220 |
| low-vol q1 | FAILED | FAILED | 27.71 / 30.34 | 30.12 / 28.64 | 83 / 1236 |

### 11.B Panel: baskets

Donor composites: 11 GICS sectors ({'Health Care': 57, 'Information Technology': 72, 'Consumer Discretionary': 47, 'Financials': 75, 'Consumer Staples': 34, 'Industrials': 77, 'Utilities': 31, 'Materials': 26, 'Real Estate': 31, 'Energy': 21, 'Communication Services': 23}). Entry-ticker GICS coverage: 18688/81260 fires (23%). Donor cell is a MARKET-WIDE feature (independent of the entry ticker's own sector) so it is computable for ALL basket entries from the mapped-subset composites; the spring GICS sub-split is honest about the ~21% sector-mapped basket subset (unmapped baskets fall in `rest`).

#### #25 DONOR-UNWIND — {intact, cracking} × {P2, E_RETEST, E_FRESH}

`cracking` = donor_unwind TRUE (fresh weekly RSI-MACD bearish cross on the top-1 126d-EW-return GICS sector within the trailing 4 completed weeks, OR donor 20d EW return < 0 while still top-ranked). `intact` = otherwise.

| P2 | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 46.27 | 30.63 | 9.46 | 28534 | 2328 |
| | cracking | 45.48 | 32.36 | 7.78 | 16418 | 2297 |

| E_RETEST | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 48.18 | 28.77 | 11.38 | 10555 | 2187 |
| | cracking | 43.00 | 35.50 | 8.82 | 5623 | 2029 |

| E_FRESH | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | intact | 48.61 | 29.25 | 7.70 | 50649 | 2335 |
| | cracking | 44.70 | 34.40 | 6.21 | 30611 | 2335 |

**Time halves + 2025+ (owner's episode), per policy:**

| P2 half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 44.54 | 30.72 | 13.91 | 12684 |
| pre2020 | cracking | 44.99 | 30.78 | 11.42 | 6088 |
| post2020 | intact | 47.66 | 30.56 | 5.89 | 15850 |
| post2020 | cracking | 45.77 | 33.29 | 5.63 | 10330 |
| 2025+ | intact | 50.83 | 27.94 | 6.42 | 2896 |
| 2025+ | cracking | 47.64 | 34.68 | 4.18 | 1482 |

| E_RETEST half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 45.57 | 29.40 | 16.93 | 4707 |
| pre2020 | cracking | 42.13 | 32.82 | 12.77 | 2020 |
| post2020 | intact | 50.27 | 28.27 | 6.91 | 5848 |
| post2020 | cracking | 43.49 | 37.00 | 6.61 | 3603 |
| 2025+ | intact | 51.64 | 26.77 | 8.36 | 945 |
| 2025+ | cracking | 44.41 | 37.06 | 5.51 | 599 |

| E_FRESH half | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| pre2020 | intact | 45.81 | 29.86 | 11.47 | 21574 |
| pre2020 | cracking | 44.36 | 32.91 | 9.77 | 10402 |
| post2020 | intact | 50.68 | 28.81 | 4.90 | 29075 |
| post2020 | cracking | 44.88 | 35.17 | 4.38 | 20209 |
| 2025+ | intact | 50.54 | 27.53 | 6.26 | 5513 |
| 2025+ | cracking | 46.15 | 34.01 | 3.98 | 2817 |

**Registered prediction #25 (two-sided, FULL panel):** clean15 concentrates in `cracking`; dead_money concentrates in `intact`. Held?

| policy | clean15↑ in cracking | dead_money↑ in intact | crack c15 / intact c15 | crack dm / intact dm |
|---|---|---|---|---|
| P2 | HELD | HELD | 32.36 / 30.63 | 7.78 / 9.46 |
| E_RETEST | HELD | HELD | 35.50 / 28.77 | 8.82 / 11.38 |
| E_FRESH | HELD | HELD | 34.40 / 29.25 | 6.21 / 7.70 |

#### #26 SPRING — P2 entries, {spring, no_spring}

`spring` = (min close in [i+1..i+7] < pre-cross 10d min `min(close[i-10..i-1])`) AND (close[i+7] > that 10d min) — undercut the SHALLOW low and reclaimed it by entry. never-BROKEN guaranteed by P2. Price-only (H4 falsification bars volume legs).

| full | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 45.14 | 31.85 | 7.80 | 3589 | 1749 |
| | no_spring | 46.06 | 31.21 | 8.93 | 41363 | 2334 |

**By GICS group (staples+healthcare vs rest):**

| staples_healthcare | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 42.05 | 32.95 | 11.93 | 176 | 75 |
| | no_spring | 41.93 | 30.66 | 15.07 | 2156 | 91 |

| rest | cell | stop5 | clean15 | dead_money | n | names |
|---|---|---|---|---|---|---|
| | spring | 45.30 | 31.79 | 7.59 | 3413 | 1674 |
| | no_spring | 46.29 | 31.24 | 8.60 | 39207 | 2243 |

**By vol quintile (ATR63% at fire bar; q1 = lowest ATR ~ registered low-beta read):**

| vol_q | cell | stop5 | clean15 | dead_money | n |
|---|---|---|---|---|---|
| q1 | spring | 41.48 | 30.57 | 21.69 | 687 |
| q1 | no_spring | 42.94 | 29.38 | 22.76 | 8304 |
| q2 | spring | 40.47 | 35.37 | 10.33 | 687 |
| q2 | no_spring | 45.08 | 30.42 | 12.30 | 8303 |
| q3 | spring | 46.58 | 31.38 | 5.86 | 717 |
| q3 | no_spring | 46.57 | 31.61 | 6.55 | 8273 |
| q4 | spring | 48.65 | 30.12 | 2.19 | 777 |
| q4 | no_spring | 47.08 | 32.30 | 2.61 | 8213 |
| q5 | spring | 47.85 | 32.04 | 0.14 | 721 |
| q5 | no_spring | 48.63 | 32.35 | 0.34 | 8270 |

**Registered prediction #26 (two-sided):** spring-present higher clean15 / lower dead_money than no-spring; strongest in low-beta/staples. Held?

| cohort | clean15 higher (spring) | dead_money lower (spring) | spring c15 / no c15 | spring dm / no dm | n spring / no |
|---|---|---|---|---|---|
| full | HELD | HELD | 31.85 / 31.21 | 7.80 / 8.93 | 3589 / 41363 |
| staples+healthcare | HELD | HELD | 32.95 / 30.66 | 11.93 / 15.07 | 176 / 2156 |
| low-vol q1 | HELD | HELD | 30.57 / 29.38 | 21.69 / 22.76 | 687 / 8304 |

#### Honesty note

- Post-gate diagnostic reads only; **promotable to wave-6 primaries, never a wave-5 ship input.** The wave-5 gates (§6) already failed and nothing shipped.
- Point estimates are raw cell means (pp). No block-bootstrap lower bound is applied here (these are exploratory strata, not gate clauses); a wave-6 promotion MUST re-impose the §4 90% clustered lower-bound discipline before any of these signs is read as real.
- A registered prediction is marked HELD only if the point-estimate inequality holds on the FULL panel (2012+); the pre/post-2020 halves are shown so a 2025-only regime effect cannot masquerade as a mechanism (amendment #25 explicitly requires the full-panel hold).

