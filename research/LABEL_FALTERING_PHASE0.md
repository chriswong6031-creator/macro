# LABEL-FALTERING PHASE-0 — pre-registered calibrations (B1 / B2 / B3)

**Status: PRE-REGISTERED 2026-07-03, before any study was run.** The gates in §2 were
committed before the results in §3 existed. Nothing here wires into `_label()` /
`_reco()` / `allocate()` regardless of verdict — that is a separate reviewed decision.

## 1 · Why these three studies

During the 2026-07-03 incident ("ACCUMULATE while the bubble pops") three engine gaps were
identified but deliberately **not** patched blind:

1. **The fading guard is relative-only.** `engine/theme_scoring._label` fires `fading` off
   the 5-day RELATIVE return (`delta_5d <= -1.5%` rollover guard, and `falling = 5d rel < 0`
   in the extended-fade branch). In an all-boats selloff the relative read stays positive
   while the absolute tape collapses — verified live: `cn_semis` printed 5d rel **+2.21%**
   while 1d abs was **−7.03%**, so the label stayed DOMINANT/ACCUMULATE.
2. **Member conviction has no feedback into the label.** The theme scored 72 while the
   member-conviction median was ~14/100. Nothing demotes a theme whose members' per-stock
   conviction profiles have collapsed.
3. **The allocation rank is blind to the last month by construction.**
   `engine/narrative_rotation` momentum legs skip the most recent 21 sessions
   (`SKIP_D = 21`, the standard short-term-reversal skip), so a leader in a sharp current
   drawdown keeps its rank for up to a month.

Each gap suggests an "obvious" fix. Each obvious fix has a known way to backfire — the
absolute escape leg can systematically **sell bottoms**, the conviction demotion may be
**redundant** with breadth legs already measured, and de-ranking on recent drawdown
**re-imports the short-term-reversal noise** `SKIP_D` exists to avoid. Hence Phase-0
kill-tests first. **An honest NO-GO on any or all is an expected, valid outcome.**

## 2 · Pre-registered designs and gates (stated before results)

Shared harness (`scripts/calibrate_baskets.py`, same substrate as every shipped verdict in
`data/strategies/baskets_calibration.json`): the ~27y SPDR sector-ETF proxy panel
(11 sectors, 1998→present, survivorship-light), forward-21d outcomes, `DD_RISK = −8%`
(`_fwd_dd` forward 21d max drawdown), 5-day event sampling, Newey-West HAC t on
daily-collapsed series (lags = ⌈21/5⌉), date-blocked bootstrap CIs (whole bars resampled),
split-half at 2013-01-01, and Trial-Ledger multiple-testing accounting per family.
B1 and B3 fit **no parameters** (all thresholds pre-declared here), so no CV folds are
needed — inference is guarded by HAC + date-blocked bootstrap + split-half. B2's
incremental leg **does** fit weights → purged, 21-bar-embargoed, date-blocked 5-fold OOS
(the `run_rollover_fit` machinery).

Proxy-mapping caveat (same as `run_breadth_divergence`): the SPDR panel has no intra-theme
members, so "members" = the 11 sector ETFs, "the basket" = the EW panel level, and member
breadth is the documented panel-breadth stand-in. Reported, not hidden.

### B1 — absolute-return escape leg in the fading path (`abs_escape_fit`)

**Candidate live rule** (not wired in this task): in `_label`, additionally fire `fading`
when the 5d **ABSOLUTE** return ≤ X **and** breadth is deteriorating, even if the relative
read is fine.

* Event set: per-(sector, day) where the current relative-path label is **not** already
  `fading`/`deteriorating` (i.e. the escape leg would be the *only* thing catching it —
  labels `dominant`/`emerging`/`neutral`, the "in-set").
* Fire(X): in-set AND 5d absolute return ≤ X AND breadth deterioration
  (panel proxy, pre-declared: `net_nh ≤ 0 OR pct50 < 0.5`).
* Grid: X ∈ {−3%, −5%, −7%}. **Primary cell X = −5%**; ±2% cells are sensitivity only.
  Ledger family `baskets_abs_escape` (3 cells + declared budget 12).
* Outcomes per event: forward 21d basket drawdown (`fwd_dd21`), forward 21d **absolute**
  return (`fwd_ret21`), forward 21d relative return (context).

**G1 (risk claim — must pass):**
  (a) date-blocked bootstrap CI of the hit lift `P(dd21<−8% | fired) / P(dd21<−8% | in-set)`
      has lower bound > 1.0;
  (b) paired same-day-diff HAC t (fired-mean `dd21` − same-day unfired in-set mean) ≤ −2.0;
  (c) the hit lift is > 1 in **both** halves (pre/post-2013).

**KILL (overrides everything):** paired same-day-diff HAC t of `fwd_ret21`
  (fired − unfired in-set) ≥ +2.0 → the leg fires at bottoms that resolve UP — it is a
  **sell-the-bottom generator**. Verdict `sell_the_bottom_generator`, do not ship.

**Verdicts:** `ship_escape_leg` (G1 passes, no kill, and neither sensitivity cell kills) /
`sell_the_bottom_generator` / `no_incremental_edge`. Verdict is taken from the primary
cell; sensitivity cells are reported and can only veto (via a kill), never promote.

### B2 — member-conviction-median demotion leg (`conviction_demotion_fit`)

**Question:** does a collapse of the member-conviction median (the per-stock
`conviction.potential` score, `engine/name_score.potential_score`) LEAD theme-level
forward drawdown, out-of-sample?

**Part 1 — PIT source audit (run first; determines whether the real study can run):**
the study needs a dated history of per-basket member-conviction medians. Candidate
sources audited programmatically: `data/china_standout_track/board.parquet`,
`data/signal_archive/*.parquet`, git history of the rendered per-ticker stores
(`site/chinastockdata/*.json` etc.), the R2 data plane. If no source has both the
conviction field and ≥ ~6 months of dated depth, the honest primary verdict is
**`no_pit_history_accrue`** — report it plainly and define the accrual.

**Part 2 — accrual spec (pre-committed if Part 1 finds no history):** archive daily, per
basket and region, {member-conviction median, IQR, n_members, theme score, label} via
`engine.signal_archive` at render time. Re-run bar: ≥ 180 archived trading days (~9
months, ≈ 36 non-overlapping 21d windows/basket × ~25 baskets, date-blocked pooling).
The re-run reuses the gates below unchanged.

**Part 3 — SPDR price-proxy kill-test (prior-setting only, can never ship the leg):**
proxy member health h_m(t) = 25·1[px>50dMA] + 25·1[px>200dMA] + 25·1[20d ret>0] +
25·1[drawdown from 252d high > −15%]; med_h = cross-member median. "Constructive basket"
= EW panel above its 200dMA AND 20d panel return > 0. Event = constructive AND
med_h ≤ 25 (theme still constructive while members collapsed — the incident shape).
  * G1 standalone: date-blocked bootstrap CI of `P(panel dd21<−8% | event) /
    P(panel dd21<−8% | constructive)` lower bound > 1.0.
  * G2 incremental (the redundancy null — this is the expected failure mode): the event
    flag joins the 5-leg rollover logistic as a 6th sign-constrained leg with **prior
    weight 0.0** (it must EARN weight against the L2 pull), purged/embargoed 5-fold OOS;
    pass requires `fit6 > hand + 0.05` AND `fit6 > fit5` AND full-fit w6 > 0.02
    (the `run_breadth_divergence` G2 bar, verbatim).
  * Proxy verdicts: `proxy_supports` (G1+G2) / `proxy_redundant_with_breadth` (G1 only) /
    `proxy_no_signal`. In ALL cases the study-level verdict stays
    `no_pit_history_accrue` until real accrued history exists — the proxy only sets the
    prior for the future re-run.

Ledger family `baskets_conviction_demotion` (1 declared design + budget 12).

### B3 — allocation-rank modulation for recent absolute drawdown (`rank_dd_modulation_fit`)

**Candidate live rule** (not wired in this task): at rank time in
`narrative_rotation.rank_themes`, demote a candidate whose trailing 21d ABSOLUTE return
≤ X (exactly the window `SKIP_D` blinds).

* Base book: the harness's validated dual-momentum rotation (`_rotation_book`: monthly
  12−1 momentum, top-4 above own 200d trend, EW, net 10 bps) — identical to the
  `run_sizing` base.
* Modulated book: same ranking, but at each monthly decision any candidate with trailing
  21d return ≤ X is excluded from selection (next eligible name refills the slot).
* Grid: X ∈ {−5%, −10%, −15%}. **Primary cell X = −10%**; others sensitivity.
  Ledger family `baskets_rank_dd_mod` (3 cells + declared budget 12).
* Metrics: net Sharpe (the book runs vs cash → Sharpe is the IR here), CAGR, MaxDD;
  paired circular-block bootstrap CI (21d blocks) on the **Sharpe difference**;
  `_dd_reduction_ci` on the drawdown difference; split-half Sharpe-diff signs.

**GO** requires, on the primary cell:
  Sharpe-diff CI lower bound > 0 (a real risk-adjusted improvement), **or**
  (DD-reduction CI favorable AND median Sharpe diff ≥ −0.02 — a real drawdown cut that
  is not paid for with Sharpe).
**NO-GO labels:** `reversal_noise_reimported` if the Sharpe-diff CI upper bound < 0
  (the modulation measurably hurts — the reversal literature wins), else `no_edge`.

## 3 · Results

*(Appended after the run — empty at pre-registration commit.)*

## 4 · Decision

*(Appended after the run.)*
