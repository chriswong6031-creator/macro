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

## 3 · Results (run 2026-07-03, appended after the pre-registration commit)

Full numbers: `data/strategies/baskets_calibration.json` → `abs_escape_fit` /
`conviction_demotion_fit` / `rank_dd_modulation_fit`. Panel: 11 SPDR sectors,
1998-12-22 → 2026-07-01; 12,854 sampled events, 8,591 in-set; in-set base
P(dd21 < −8%) = 0.103.

### B1 — `no_incremental_edge` (NO-GO, with an honest near-miss)

| X (5d abs) | n_fired | hit P(dd<−8%) | lift CI | G1(b) paired t_dd | KILL t_ret | med fwd 21d abs ret |
|---|---|---|---|---|---|---|
| −3% | 461 | 0.219 | [1.61, 2.66] ✓ | **−1.99 ✗** | 1.13 (no kill) | +1.48% |
| **−5% (primary)** | 148 | 0.338 | [2.15, 4.47] ✓ | **−1.97 ✗** | −0.10 (no kill) | +1.84% |
| −7% | 79 | 0.418 | [2.55, 5.79] ✓ | −0.98 ✗ | 1.34 (no kill) | +2.11% |

* G1(a) and G1(c) pass everywhere: fired events run 2–4× the base rate of deep forward
  drawdowns, in both halves (primary: pre-2013 lift 2.71, post-2013 4.05).
* **The KILL gate did NOT fire** — the escape leg is *not* a sell-the-bottom generator
  (fired events' forward returns are statistically indistinguishable from same-day
  in-set peers; primary-cell paired t = −0.10).
* **G1(b) fails** — barely (−1.97/−1.99 vs the −2.0 bar at −5%/−3%). The same-day paired
  severity test is the leg's *theme-level* claim: does firing pick out sectors that draw
  down *worse than their same-day peers*? Answer: not measurably. The strong
  unconditional lift is mostly "these are crash days" — on an all-boats day the unfired
  in-set peers draw down almost as hard. The leg detects a **market state**, not a
  theme-level distinction — and market-state drawdown risk is already a separately
  measured channel (the macro `drawdown_risk` leg).
* The median fired event still resolves **up** (+1.84% abs over the next 21d at the
  primary cell) even though the deep-drawdown tail is 3× fatter — flipping a label to
  `fading`/`trim` on this signal would exit the median event near the low while
  protecting against the tail. That trade-off is a sizing question, not a labeling one.
* By the pre-registered conjunction, verdict = `no_incremental_edge`. The gates were set
  before the run; the near-miss does not promote. Any Phase-1 retry (e.g. a severity test
  designed for cross-sectional differentiation, or an abs-escape leg feeding the sizing
  throttle instead of the label) needs a fresh pre-registration.

### B2 — `no_pit_history_accrue` (cannot run; accrual defined; proxy uninformative)

* **PIT audit (programmatic, in the JSON):** `china_standout_track` = 3 days, no
  conviction field; `signal_archive/baskets` = 10 days, no member fields; git history of
  the rendered per-ticker stores = ~13 trading days (2026-06-13 → 2026-07-01) before the
  R2 untracking, current-state + formula-drifted; R2 = current-state only.
  **No usable PIT history exists — the real study cannot be run today.**
* **Proxy kill-test: structurally uninformative, not negative.** In 27 years the
  pre-registered collapse event (EW panel constructive AND member-median health ≤ 25)
  fired **zero times** — the median health of 11 broad sector ETFs never collapses while
  the panel itself is still constructive. The incident shape (a narrow theme whose
  members crater while the theme print stays strong) has no analogue on broad sectors.
  G2 concurs: the leg earned weight 0.0 in every fold. `proxy_no_signal`, carrying **no
  evidential weight either way** for the real member-conviction question.
* **Accrual (the deliverable):** archive daily, per basket and region — member
  `conviction.potential` median, IQR, n_members, theme score, label — via
  `engine.signal_archive` at render time. Re-run bar: ≥ 180 archived trading days
  (~9 months → first adequately-powered read ≈ 2027-04), gates in §2 unchanged.
* **Status 2026-07-03 — accrual WIRED.** `engine/conviction_accrual.py`, called
  best-effort from all five library builders (`scripts/build_*_library.py`, right
  after the potential attach + panel scoring). Daily rows land in
  `data/signal_archive/conviction_{us,china,hk,canada,intl}.parquet` (append-only,
  keep-first per as-of): per-basket {median, iqr, n, n_total, theme_score, label}
  + a deduped region roll-up; `theme_asof` records the label vintage (the basket
  build can be a session behind the library build). Write-only research ledger —
  `_label()` / `_reco()` / `allocate()` untouched.

### B3 — `no_edge` (NO-GO; SKIP_D keeps its rationale)

Base book: Sharpe 0.552, MaxDD −33.9%, CAGR 6.99% (net 10 bps).

| X (21d ret demotes) | Sharpe | MaxDD | CAGR | ΔSharpe CI | ΔDD CI (pp) | split-half ΔSharpe |
|---|---|---|---|---|---|---|
| −5% | 0.538 | −37.7% | 6.60% | [−0.077, −0.015, 0.052] | [−4.4, 0.3, 5.5] | −0.041 / +0.015 |
| **−10% (primary)** | 0.553 | −33.9% | 6.99% | [−0.014, 0.001, 0.015] | [−1.2, 0.0, 1.4] | +0.010 / −0.009 |
| −15% | 0.547 | −33.9% | 6.92% | [−0.018, −0.004, 0.004] | [−1.3, 0.0, 0.6] | 0.000 / −0.009 |

The mechanism is clean: at deep thresholds the demotion almost never binds — a name
ranked top-4 by 12−1 momentum *and* above its 200dma essentially never sits on a −10%
trailing month, so the rule is redundant with the trend gate already in the book. At the
shallow threshold it binds often enough to matter and **hurts** (deeper MaxDD, −0.39pp
CAGR, ΔSharpe median −0.015) — the short-term-reversal noise re-imported, exactly the
outcome `SKIP_D = 21` exists to avoid. No cell earns `ship_rank_modulation`;
the −5% cell's degradation is directional but its CI includes 0, so the label is
`no_edge` rather than `reversal_noise_reimported`.

> **In plain English:** we tested three "obvious" fixes from the incident. (1) Flagging a
> theme as fading because it fell hard in absolute terms does catch days with real crash
> risk — but only because *everything* is crashing on those days; it can't tell you this
> theme is worse than the others, and half the time the theme is higher a month later.
> (2) We can't yet test whether collapsing member conviction predicts theme drawdowns,
> because nobody has been writing that number down day by day — we now spec'd the ledger
> to start accruing it. (3) Kicking a recent loser out of the allocation ranking either
> does nothing (deep thresholds) or makes the book slightly worse (shallow) — the
> one-month skip in the ranker is there for a reason and survives its challenge.

## 4 · Decision

**All three studies: do not wire.** `abs_escape_fit = no_incremental_edge`,
`conviction_demotion_fit = no_pit_history_accrue`, `rank_dd_modulation_fit = no_edge` —
recorded additively in `data/strategies/baskets_calibration.json`; trial families
`baskets_abs_escape` / `baskets_conviction_demotion` / `baskets_rank_dd_mod` logged to
the Trial Ledger. `_label()` / `_reco()` / `allocate()` are untouched, as pre-committed.

Follow-ups this run motivates (each needs its own decision/pre-registration, not blind
wiring): start the B2 conviction-median accrual in the render pipeline; consider a
Phase-1 for the absolute-escape signal as a **book-level de-risk / sizing** input (where
its market-state nature belongs) rather than a per-theme label flip.
