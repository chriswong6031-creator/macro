# COILED-CA — Durable-Bottom Detector on Canada · Phase-0 PRE-REGISTRATION

> Battery **COILED-CA** of the HK/Canada program (masterplan
> `research/HK_CANADA_STOCKS_MASTERPLAN_BY_FABLE.md`; §6 constitution binds).
> Written and committed **BEFORE** any run. Harness: `research/entry_timing/wave3_ca.py`
> (a real fork of `research/entry_timing/wave3.py`'s close-only path — leak-free math
> reused verbatim, NOT reimplemented). Report: `reports/coiled-ca-phase0.md`.
> **NO WIRING in this PR** (collision pact §8.1: china_alpha owns `engine/coiled.py`).

---

## 0. The one question this battery closes

`engine/coiled.py` (the COILED cohort-washout + bullish-divergence durable-bottom
detector) is **VALIDATED** on US (`DURABLE_BOTTOM_FRAMEWORK.md` waves 1-4) and **CN**
(wave-3: COILED-vs-noncoiled_washout clean15 **+7.33pp**, stop5 **−6.21pp**, shipped as
the CN graded bonus) and **REFUTED on HK** (wave-3: spread −0.84pp wrong sign, halves
flip, per-name minority — mechanism: 157 names / ~12 macro-correlated sectors → cohort
washout is near-universal in HK drawdowns, carries no discrimination; `coiled.py:337`).

**Canada was never tested.** CA (219 names, 11 sectors, developed market) structurally
resembles the two validated panels (US/CN) far more than it resembles HK. This battery
replicates the **exact CN wave-3 gate** on the CA panel and closes the "why not just port
the US/CN system to Canada?" question for this engine **with data**, either way:

- **PASS** ⇒ the COILED ranking bonus wires into the CA board exactly as CN's did — as a
  **follow-up wiring PR, not this one**.
- **FAIL** ⇒ CA joins HK on the do-not-port list with its own evidence.

This is pre-committed. The verdict is whatever the gate returns.

---

## 1. Panels, data, honest power

### 1.1 Primary — CA names panel (the decision panel)
- Store: `data/canada_search/closes.parquet` (219 columns, `.TO` tickers) +
  `data/canada_search/members.parquet` (`sector`, 11 sectors). **219/219 tickers map to a
  sector**; column format `.TO` matches on both sides (verified).
- Span: **2021-06-14 → 2026-06-30** (1,267 daily bars). **215 of 219** names clear the
  `min_bars=800` floor (4 dropped, reported).
- **Close-only** (the `canada_search` store carries no volume/high/low). Therefore, exactly
  as on the CN/HK close-only panels: **H4 volume features and `low_stop5` are skipped**;
  `stop5`/`clean15` use the close series (synthetic hi/lo = close, wave3 close-only path).
- **EVAL_START = 2022-09-01.** The `washout_ctx` detector needs 308 daily bars (217 capit
  window + 91 look-back), and outcomes need 126 forward bars — so fires are only scored on
  ~2022-09 → ~2025-12 (the trailing 126 bars have no full outcome window). Usable eval span
  ≈ **2.8 years, one macro cycle** (BoC hiking peak → hold → first cuts). **This is thin.**

**Honest power (pre-run probe, no cohort/outcome filter yet).** A raw `m2d_s3d` fire count
over the eval span (≥126 forward bars) yielded **~3,105 fires over 215 names** (median 15
/name); with the CN COILED share (~50% of m2d fires were COILED), the expected **n_COILED
is ~1,500** — comfortably above the pre-registered `n_COILED ≥ 400` floor. So the gate is
runnable **with real power**, but ~7× thinner than CN's 10,784 COILED fires and spanning
**one** macro regime, not multiple. The split-half is a within-single-cycle split, not a
cross-regime replication. Stated on every headline number.

**Cohort eligibility (11 sectors, min_peers=5, self-excluded).** 9 sectors have ≥6 members
(Materials 60, Energy 38, Industrials 30, Financials 22, Real Estate 18, Utilities 14,
Consumer Staples 10, Info Tech 9, Consumer Disc 8) → cohort-eligible. **Communication (5)
and Health Care (5)** yield only 4 peers after self-exclusion → those ≤10 names get
`cohort=None` and are **excluded from COILED/NCW by construction** (same rule as CN/HK; no
special-casing). This is a design property, not a filter I chose post-hoc.

### 1.2 Secondary — deep TSX sector-ETF panel (context only, DIFFERENT mechanism)
- 9 continuously-listed TSX sector ETFs: XEG/XGD/XFN/XIT (2001-03→), XRE (2002-10→),
  XMA (2005-12→), **XBM/XUT/XST (2012-01→)**. Span 2001→2026 (~24y — the deep leg).
- **PRE-STATED CAVEAT — the cohort mechanic does NOT transfer at the ETF level.** COILED's
  H6 cohort = "fraction of a name's *sector peers* washed out." An ETF *is* its sector
  (singleton), so it has no sector peers. The deep-ETF secondary therefore treats the 9
  ETFs as **one cross-ETF cohort** ("what fraction of TSX sectors are simultaneously washed
  out"). This is a **genuinely different object** from the per-name sector-cohort mechanic
  and is reported as **descriptive context only — it does NOT feed the CA verdict** (which
  is decided solely on the names panel, §3). Its role: does the coiled *idea* (washout ×
  breadth-of-washout × divergence) carry any signal on a survivorship-clean 24y panel where
  the names panel is survivorship-biased and short. Interpreted qualitatively, never gated.

### 1.3 Survivorship
`canada_search/closes.parquet` is **current-constituent** (219 names on today's TSX). Delisted
losers are absent → durable-bottom liftoff rates are biased **up** uniformly, but the
COILED-vs-NCW **spread** (both strata drawn from the same survivor panel) is the object of
interest and is far less sensitive to the level bias (same argument the US/CN waves made).
No dead-name store exists ex-US → a worst-case delisted-imputation lower bound cannot be
computed; the survivorship **bound** is stated as: a names-panel COILED-PASS is an optimistic
upper bound, a COILED-FAIL is conservative (survivorship only helps liftoff, so a fail on the
survivor panel is a strong fail). The deep-ETF secondary is survivorship-clean (sleeves are
continuously listed).

---

## 2. Method — the CN wave-3 gate, replicated verbatim

Fires, labels, outcomes, cohort fraction, and COILED/STAR assignment are computed by the
**unmodified** wave3/wave2/wave1 primitives (imported, not copied):
`label_events_w2` (durable/trap labels: DD_MIN 15%, durability no close < P0·0.97 for 126d,
liftoff ≥ P0·1.20 within 126d), `compute_outcomes_w2` (`clean15` = +15% before −5% within
126d; `stop5` = −5% before +5%; `dead_money` = 63d < +5% & never ±8%; **next-bar fill**
`pos = fill_idx = sig_idx + 1`), `compute_features_w2` (H1 washout_ctx, H3 bull_div, H6
sector-cohort fraction), and the wave3 table builders `build_T1_w3` / `build_T3_w3` /
`build_T4_w3` (`_rate_row`). Trigger = **`m2d_s3d`** (the CN/US COILED platform); `base3d`
printed for reference.

Strata (identical to CN wave-3):
- **COILED** = `washout_ctx` AND `cohort_sector ≥ 0.40`.
- **noncoiled_washout (NCW)** = `washout_ctx` AND `cohort_sector < 0.40` (the fair
  same-washout control — NOT "all fires").
- **STAR** = COILED AND `bull_div`.

Primary metric: **COILED clean15 − NCW clean15** (percentage points), plus stop5 and
dead-money on each stratum.

---

## 3. PRE-REGISTERED GATE (mirrors the CN wave-3 G-CN gate verbatim, plus the program constitution)

Let `Δclean15 = clean15(COILED) − clean15(NCW)` and `Δstop5 = stop5(COILED) − stop5(NCW)`.

**G-CA (primary, names panel) — ALL must hold for PASS:**
1. **Lift:** `Δclean15 ≥ +3.0pp` (the CN precedent threshold).
2. **Stop not worse:** `Δstop5 ≤ +1.0pp` (COILED stop-out not worse than NCW by >1pp).
3. **Count:** `n_COILED ≥ 400`.
4. **Split-half sign-stability:** `Δclean15 > 0` in **both** time halves (cut = **2024-01-01**,
   the mechanical near-midpoint of the usable 2022-09→2026-06 span, pre-registered here).
5. **Per-name majority:** among names with ≥3 fires in **each** of {COILED, NCW},
   `% where COILED clean15 > NCW clean15 ≥ 55%`.
6. **Multiple-testing-aware significance (constitution §6 DSR analog):** a **name-clustered
   block bootstrap** (resample whole names with replacement, B=5000, seed=17 — the
   independent-episode / effective-N unit is the NAME, not the overlapping fire) gives a
   **one-sided 90% lower bound on Δclean15 that is > 0.** *Rationale:* COILED is an
   event-rate spread, not a Sharpe series, so `deflated_sharpe` on a return curve does not
   apply (the CN/HK wave-3 gate itself used no DSR-on-Sharpe). The honest constitution-
   compliant analog is a cluster bootstrap whose resampling unit is the independent name and
   whose 0.90 threshold matches DSR≥0.90; the family multiple-testing budget is registered
   via `TrialLedger.with_declared_budget(40, "coiled_ca_phase0")` (masterplan program budget
   ≈40) and the bootstrap is one-sided at the same 0.90 level. Reported alongside a naive
   two-sample interval so the clustering haircut is visible.

**Robustness (all must hold on a PASS, else downgrade to ACCRUE):**
- Spread sign preserved at **clean10** and **clean20** barriers (+10% / +20% before −5%).
- COILED **dead-money lower** than NCW.

**Verdict mapping (GO / NO-GO / KILL / ACCRUE — constitution wording):**
- **GO (PASS)** ⇒ G-CA gates 1-6 all hold **and** robustness holds. Consequence: COILED
  ranking bonus wires into the CA board (follow-up PR).
- **KILL** ⇒ `Δclean15 < 0` (wrong sign) with `n_COILED ≥ 400` (powered wrong-sign — the HK
  outcome). Consequence: CA joins HK on the do-not-port list.
- **NO-GO** ⇒ gates fail but sign is right and not powered-wrong (e.g. lift < 3pp, or
  split-half flips, or per-name minority, or bootstrap LB ≤ 0). Do-not-wire; may re-open.
- **ACCRUE** ⇒ gates 1-5 hold but the bootstrap LB (gate 6) sits just ≤ 0, or robustness
  fails — a right-signed, sub-threshold edge worth forward-grading, never wired now.
- **INCONCLUSIVE** ⇒ `n_COILED < 400` (insufficient power) — not expected given the probe.

The deep-ETF secondary (§1.2) is reported qualitatively and **cannot change** the G-CA
verdict.

---

## 4. Kill-rule integrity (pre-committed, cannot be relaxed post-hoc)

- Thresholds (3pp / 1pp / 400 / 55% / 0.90 / clean10-20 / dead-money) are **fixed here** and
  are the CN wave-3 values verbatim — no CA-specific loosening.
- half-cut 2024-01-01 is fixed here; it will **not** be moved to make split-half pass.
- `m2d_s3d` is the sole decision trigger (the CN/US platform); no trigger sweep in this
  battery (a trigger study is a separate wave, out of scope).
- Next-bar fills only. Leak-free known-date mapping inherited from the unmodified harness.
- Report carries a **bold verdict**, the full gate table, the survivorship bound (§1.3), and
  an explicit **"What this does NOT show"** section. Registry append at END. **No wiring.**

## 5. What this battery does NOT test (pre-stated)
Only the COILED cohort-washout × bullish-divergence detector as a CA standout-board ranking
bonus, on the `m2d_s3d` trigger. It does **not** test: any other trigger; the COILED-FIRE
marker (wave-4 C2); alternative cohort definitions (theme baskets — CA theme membership not
wired here); volume/participation (no CA search-store volume); the deep-ETF cohort as a
*decision* leg (context only, different mechanism); or any CA edge outside COILED (C1
commodity→sector, C-BANK, momentum — separate batteries, already resolved in masterplan
§6.1). A CA NO-GO/KILL here is a verdict on **this engine's portability to CA**, not on
whether Canada has any tradable durable-bottom timing edge.
