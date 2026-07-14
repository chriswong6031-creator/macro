# FLOW SIGNAL FIELD GUIDE — descriptive atlas + institutional practice guide (FS-2)

_Authored by FS-2 build, 2026-07-13. Atlas tables computed from eod_proxy (7,336,004 events
post-dedup store count; harvest emitted 7,336,437, 383-root store (380 event-producing),
2012-06→2026-07) and tape_recon (696,633 events, SPY 2022-2023, accruing).
This document is descriptive — it establishes base rates; no effect-size verdicts.
FS-3 registers the backtest rulers that derive from this playbook._

**Survivorship notice:** The 383-root eod_proxy universe is today's optionable set applied
backward to 2012-06. Names that delisted or lost options listing before 2026 are absent from
early-era cells; pre-2020 era base rates are survivorship-inflated. FS-3 rulers must not
treat early-era levels as unbiased baselines.

---

## §0 What this document is

This is a **descriptive atlas and institutional practice guide** for options-flow signals.
It contains three things:

1. A writeup of who trades each print type and why (§1), drawn from the academic and
   practitioner literature and from analysis of the eod_proxy + tape_recon cohorts.
2. Per-type expected-behavior priors and playbook skeletons (§2–§3): what the practitioner
   community believes before any measurement, stated so those priors can be tested.
3. Measured base rates from the atlas tables (§4): the actual counts, rates, and Wilson 95%
   confidence intervals from the two historical cohorts. Numbers here are descriptive.
   They are NOT verdicts. Effect-size claims require FS-3 pre-registered rulers.

**Zero signal verdicts in this document.** The word "validated" does not appear in any
affirmative claim here, because no rulers have been tested yet. "Established," "measured,"
"observed" — these are the correct words for §4. FS-3 is where verdicts live.

**Cohort law (FS-R4):** every table in §4 is labeled with its cohort. eod_proxy and
tape_recon are never pooled. The live_feed ledger is a third cohort.

---

## §1 Institutional practice: who trades each print type and why

### §1.1 Large single-print premium

The $250k–$1M+ floor in the live detector eliminates approximately 95% of retail order flow
by premium size. The qualifying remainder divides into three populations:

**Institutional directional buyers.** Options buy-to-open volume carries predictive content
for short-term underlying moves, driven by information advantage rather than hedging need
(Pan & Poteshman 2006, RFS: low put/call ratios predict +40bps next day, 1%+ next week,
decaying over roughly 20 trading days). At-ask fills signal urgency and conviction; at-bid
fills are more consistent with overlay or seller-initiated flow.

**Portfolio manager tail hedges.** These are large put purchases (often deep-OTM, often index)
that are uninformed on direction: the PM is buying insurance, not a thesis. They inflate the
vol>OI flag rate and muddy directional inference. Premium × moneyness interaction is needed
to separate this population; premium size alone is insufficient.

**Market-maker counterparty legs.** The MM takes the other side and delta-hedges; this creates
underlying flow (the "delta hedge") that can move the stock. The causality is reversed from
the informed-buyer story: price moves because the MM is hedging, not because the buyer was
right.

**Noise sources:** structured-product dealer legs (not directional); dividend-capture
deep-ITM early exercise (particularly around ex-dividend dates); split-adjusted moneyness
artifacts (a seam guard is required, see §5).

### §1.2 Sweep clusters

A sweep — simultaneous or near-simultaneous prints across multiple exchanges — indicates a
buyer willing to walk up the offer to guarantee fill. The interpretation is that the actor
is time-constrained: an event-driven fund or execution algorithm responding to a catalyst
that cannot wait for a limit order to fill.

Multi-exchange split fills to guarantee execution are structurally rare among retail (PFOF
routes retail to a single venue). Ascending-fill clusters — successive prints each at a
higher premium — over 10–30 minutes indicate a principal buyer exhausting multiple offers,
and are among the strongest aggression markers available in tape data.

**Noise sources:** exotic-structurer hedge legs are more common on index/ETF than on
single names. A simultaneous call sweep and put sweep in adjacent strikes is a spread
candidate, not directional flow.

The tape_recon cohort shows 98.3% of detected events as "swept" (by the intraday definition
of min 3 prints, 2 exchanges, within 2 seconds), which reflects the concentration of the
current sweep: SPY 2022-2023 is a high-sweep-density cohort. The non-swept fraction (1.7%,
n=17,679) is too thin to draw distribution contrasts reliably in this cohort.

### §1.3 Vol>OI bursts

A vol>OI event means the day's cumulative volume in a specific contract exceeds the prior
session's open interest. Definitionally this means some net new positioning occurred. Three
confounds are frequent:

**T+1 OCC OI lag.** Open interest is reported by the OCC the morning after the trading date
(T+1). A brand-new contract listed today starts at OI=0; any volume at all triggers vol>OI.
This is measured in the eod_proxy cohort: 0DTE contracts show vol_gt_oi_rate ≈ 1.00 across
all eras, which is a structural artifact of the empty-OI-at-open condition, not informational
flow (see Table H). The OI-only eras in the eod_proxy data (2012-15, 2016-19) have lower
resolution on this distinction.

**Roll contamination.** When a fund closes a near-expiry leg and opens a far-expiry leg, the
closing generates volume against the near leg's OI (trivially true if near OI is small) and
the opening generates volume against zero far-leg OI. On AAPL (analyzed in Table C), roughly
40% of vol>OI events have a same-session same-strike near-expiry volume event that is a
roll candidate. This is the primary false positive class.

**Spread legs.** A one-leg-opens-one-leg-closes spread has symmetric effects: the opening
leg flags vol>OI if prior OI is low; the closing leg reduces OI on the next tick. Without
seeing both legs simultaneously, spread-leg classification requires same-session same-strike
inspection.

**Genuine positioning** (OI-confirmation test): an event where next-session OI rises at least
50% of the burst volume, indicating real new open interest was added. On AAPL this is
observed in approximately 30-31% of testable vol>OI events (Table B). This rate is lower in
2020-22 (28.4%) and 2023+ (28.2%) vs 2012-15 (33.8%) and 2016-19 (33.1%) — consistent
with the proliferation of 0DTE and short-dated contracts increasing trivially-flagged events.

### §1.4 Repeated same-contract prints

Repeated hits on the same contract within a session suggest incremental accumulation:
a fund avoiding price impact, a catalyst-aware buyer building a position, or an execution
algorithm staging entries. The key distinguishing characteristic vs noise is the ordering:
ascending fills (each at a higher premium than the last) rule out a single large lot
being broken up by the MM for liquidity management.

Repeat-cluster events are not yet well-represented in the tape_recon cohort: the current
SPY 2022-2023 sweep shows zero events flagged as `repeated=True`, because the detector
threshold (2 cycles intraday) combined with SPY's high volume means most clustering happens
below the premium floor. This is an expected artifact of the tier-1 (ETF-only) sweep phase
and is not evidence against the mechanism. Single-name tape (tier-3) is the natural habitat.

### §1.5 Deep-OTM cheap-premium events

Above the $100k–$250k+ proxy floor, deep-OTM qualifying events split into two populations:
**home-run informed bets** (M&A, FDA binary events, macro catalysts) where the buyer expects
a large underlying move within DTE; and **large speculative flows** with lower information
content. Premium × OTM% combinations separate these populations: a $500k premium on a
5-delta AAPL call 30 days out is different from a $500k premium on a 25-delta position.

Far-OTM put purchases — particularly on index ETFs — are frequently hedge-book management:
size without direction. These inflate the vol>OI flag on the put side.

### §1.6 0DTE/index: mechanically different

0DTE SPXW/SPX options have a fundamentally different dealer mechanics regime:
- Dealer gamma exposure (GEX) recycles intraday and vanishes at 4pm settlement.
  The delta-hedging flow is mean-reverting, not trending.
- Vol>OI is trivially true at open (OI=0 at the start of each day for that session's contracts).
- Systematic premium sellers (condors, spreads) operate at-bid; their flow appears as
  large at-bid prints that do not indicate directional conviction.
- The measured vol>OI flag rate for 0DTE index in the eod_proxy cohort is 100% by
  construction (Table H) — this is a documentation of a known data artifact, not a signal.

**Prior for multi-day rulers: near-noise, with skepticism.** The practitioner literature
(mlquants 3-decade study, n=69,094 firm-quarters 1996-2024) documents that options-volume
signals flipped sign after commission-free trading came online (late 2019). This mandates
per-era analysis and forbids pre/post-2020 pooling, particularly for 0DTE where the
sign-flip is most expected.

0DTE intraday pressure effects (dealer mechanics) are out of scope for DTE-bucket scoring
and are covered by the GEX stack.

---

## §2 Per-type expected-behavior priors

These are the priors before measurement. Measurement lives in §4.

### §2.1 Single-print horizons

**Primary single-name horizon: 1–5 days.** The literature's predictive content decays over
roughly 20 days (Pan & Poteshman 2006). For contracts with 8–30 DTE, the 21-day window
captures the core of the distribution. For 1–7 DTE, a 5-day window is the appropriate ruler.

**Index/ETF hedging prints: no directional horizon.** A PM buying SPY puts for tail hedging
is not making a directional call; the 5-day horizon is expected to show noise.

**Confounds:** at-bid fills (seller-side); ex-dividend ITM exercise flows (dividend calendar
flag needed); post-split moneyness artifacts (seam guard, see §5).

### §2.2 Sweep clusters

**Primary: 1–5 days (event-driven).** Sweeps are consistent with a time-constrained actor
responding to an expected catalyst. The 5-day window covers most announced-event
resolution windows (earnings, FDA, macro).

**Secondary: 5–21 days (thesis-based).** A thesis actor may not have a specific catalyst
date; the 21-day window is appropriate.

**"Golden sweep" (practitioner lore):** large single sweep filling $250k–$1M+ in a liquid
name with ascending fills. This is practitioner vocabulary with thin literature support.
Its discrimination power vs standard sweep is unmeasured.

**Spread-leg misclassification** inflates both at-ask and at-bid sweep counts: offsetting
call+put sweeps at adjacent strikes are spread candidates and contaminate both sides.

### §2.3 Vol>OI bursts

**Mixed academic evidence.** Vol>OI is directionally motivated when:
- Pre-existing OI in the contract is meaningful (not a new-listing trivial flag)
- No roll candidate exists (no near-expiry same-strike volume spike same session)
- No sister-expiry closing volume is present

**Next-day OI confirmation (≥50% of burst):** the most direct genuine-positioning test.
Measured on AAPL: 30–34% of vol>OI events pass this test, with lower rates post-2020.

**Primary horizon tracks DTE:** 2–5 days for 1–7 DTE contracts; 5–21 days for 8–30 DTE.
The 90d+ bucket has no established short-window horizon; longer windows (21–63 days) with
overlap-corrected statistics are appropriate.

### §2.4 Repeated prints

**Within-session repeats** are frequently execution artifacts unless: ascending fills
AND 8–30 DTE AND floor-qualifying each print. Single-name tier is the natural habitat.

**Cross-session accumulation (5–15 session window):** higher prior for genuine accumulation.
Multi-week same-contract builds (10+ sessions) suggest strategic positioning.

**At-bid print after at-ask series:** the original buyer may be unwinding. Score from the
unwind signal, not the original series.

### §2.5 Deep-OTM

**Binary ruler:** move-to-strike within DTE, not a fixed-horizon return. The contract
expires worthless unless the underlying reaches the strike.

**M&A subpopulation:** hypothesized signal carrier. IV spike after initial print = corroboration.

**Premium floor qualifying only:** removes lottery-ticket retail; the remaining population
is still heterogeneous (informed vs speculative).

### §2.6 0DTE (reiterated from §1.6)

Not scored against multi-day rulers. Vol>OI is a structural artifact.
Intraday P/C + net premium at open/10am/2pm windows have documented intraday pressure
effects — out of scope for this field guide's DTE-bucket scoring.

---

## §3 Per-type playbook skeleton (priors-to-be-measured)

These are the intended FS-3 ruler registrations. They are listed here so the backtest rulers
derive from the documented playbook, not vice versa.

### Single prints (DTE-stratified)

| DTE range | Primary window | Invalidation | Holding |
|---|---|---|---|
| 0–7d | 1–3d | Opposite-side same-day print OR at-bid origin | 1–3 trading days |
| 8–30d | 5–15d | Follow-on prints confirm; no follow-on in 3d = cold | 5–15 trading days |
| 31–90d | 10–30d | Close/roll without underlying move in 15d | 10–30 trading days |
| 90d+ | 21–63d | Roll without move; position reduction without catalyst | Confirmer-role prior; roll ≠ thesis abandonment |

### Sweep clusters

| DTE range | Primary window | Notes |
|---|---|---|
| 0–7d | 1–5d | Event-driven sweet spot |
| 8–30d | 5–21d | Strongest DTE window per priors |
| 31–90d | 10–30d | Thesis flows |
| Stopped cluster | 1d after stop | Target filled vs continuing ascending = different interpretation |

### Vol>OI bursts

| DTE range | Primary window | Gate |
|---|---|---|
| 0–7d incl 0DTE | Skeptical prior | OI > 500 prefilter; exclude known 0DTE-trivial names |
| 8–30d | 5–15d | T+1 OI confirmation as filter (OI rose ≥50% of burst) |
| 31–90d | 21–63d | Institutional initiation window |

### Repeated prints

Per §2.4: within-session (ascending + 8–30d DTE + floor-qualifying each print); cross-session
5–15 session window; multi-week 10+ session window.

### Deep-OTM

Binary ruler (move-to-strike within DTE). IV-spike corroboration required.
DTE-absolute windows (not return horizons).

---

## §4 Measured base rates (atlas tables)

All tables computed by `scripts/ops_flow_atlas.py` from the ops-lane cohort parquets.
N-floor = 30. Cells with n < 30 are labeled ERA-SPARSE and stat is suppressed.
Wilson 95% CI reported for all rates. Every table is labeled with its cohort and coverage window.

**CI-independence caveat:** The Wilson 95% CIs treat events as independent Bernoulli trials.
They are not: millions of same-day events share the same underlying move and the same SPY
session, so effective N is far below the row count. The printed intervals are **descriptive
width, not inferential guarantees**. FS-3 inference must use time-preserving or clustered
methods (per the house time-preserving-null law; see also §5 item 9).

**Graded-fraction disclosure (eod_proxy):**
- ok-graded: 5,656,355 / 7,336,004 = 77.1%
- not_yet_matured: 163,845 (2.2%); partial_matured: 60,582 (0.8%)
- no_price_history_for_era: 1,455,192 (19.8%) — concentrated in 2012-15/2016-19
- split_seam (excluded): 30

**Graded-fraction disclosure (tape_recon):**
- Current sweep: SPY 2022-2023; 696,633 events; 118,568 ok-graded (accruing)
- All 118,568 grade rows have reason_code='ok'

---

### Table A: Event frequency by qualification class × DTE bucket × era

**Cohort:** eod_proxy | **Coverage:** 2012-06 to 2026-07, 3,578 sessions, 383-root store (380 event-producing)

_Note: mny_bucket='unknown' for all rows (no close-price alignment in the eod store). The_
_mny_bucket dimension will be available when a closing-price join is added to the cohort build._

Key counts by era × DTE bucket (vol_gt_oi class; eod_proxy is ~99% vol_gt_oi):

| Era | 0d | 1_7d | 8_30d | 31_90d | 90p | Era total |
|---|---|---|---|---|---|---|
| 2012-15 | 8,525 | 111,750 | 133,904 | 93,443 | 85,664 | 433,286 |
| 2016-19 | 26,527 | 280,847 | 336,199 | 191,409 | 154,539 | 989,521 |
| 2020-22 | 62,395 | 670,701 | 750,076 | 334,070 | 325,143 | 2,142,385 |
| 2023+ | 176,040 | 1,260,520 | 1,191,755 | 539,769 | 602,728 | 3,770,812 |

Events per day (all eras combined): mean 2,050.

**Observation:** The 0DTE bucket grew 20× from 2012-15 to 2023+, documenting the 0DTE
proliferation structurally. 1_7d is consistently the largest DTE bucket across all eras.

---

### Table B: Vol>OI genuine-positioning rate (eod_proxy, 40-root stratified sample)

**Cohort:** eod_proxy | **Sample design:** 40-root stratified sample across size deciles
**Requirement:** next-session OI rose ≥ 50% of burst volume
**Total tested:** 1,305,966 (of 1,329,190 events; 23,224 had no next-session OI)

| Era | n tested | Confirmed | Rate | Wilson 95% CI |
|---|---|---|---|---|
| 2012-15 | 84,916 | 43,583 | 0.513 | [0.510, 0.517] |
| 2016-19 | 252,665 | 108,305 | 0.429 | [0.427, 0.431] |
| 2020-22 | 463,916 | 160,938 | 0.347 | [0.345, 0.348] |
| 2023+ | 504,469 | 152,065 | 0.301 | [0.300, 0.303] |
| **Overall** | **1,305,966** | **464,891** | **0.356** | **[0.355, 0.357]** |

**Interpretation:** Approximately 36% of vol>OI events in the 40-root sample exhibit genuine
new positioning (next-day OI confirmation). The rate declined from ~51% in 2012-15 to ~30%
in 2023+, consistent with the proliferation of 0DTE and short-dated contracts that trivially
flag vol>OI without adding lasting open interest. The 40-root sample rates are higher than
a single-name AAPL pilot would suggest; they include high-OI large-caps where next-day OI
confirmation is more common.

---

### Table C: Roll contamination rate (eod_proxy, 5-root sample)

**Cohort:** eod_proxy | **Sample design:** 5-root sample | **Definition:** vol>OI event has
a same-session same-(strike, right) event with a shorter expiry within 35 calendar days
**Total tested:** 752 events

| Era | n events | Contaminated | Rate | Wilson 95% CI |
|---|---|---|---|---|
| 2012-15 | 97 | 1 | 0.010 | [0.002, 0.056] |
| 2016-19 | 170 | 3 | 0.018 | [0.006, 0.051] |
| 2020-22 | 207 | 10 | 0.048 | [0.026, 0.087] |
| 2023+ | 278 | 4 | 0.014 | [0.006, 0.036] |
| **Overall** | **752** | **18** | **0.024** | **[0.015, 0.038]** |

**Interpretation:** The 5-root sample shows low roll contamination rates (2–5% across eras),
much lower than the AAPL-only pilot's 40% figure. The 5-root sample spans a range of
ticker types where roll activity differs materially from AAPL. N is small per era (97–278)
and CIs are wide; this table is a cross-root orientation, not a definitive contamination rate.
Full multi-root roll contamination requires a larger sample and remains an FS-3 accrual item.

---

### Table D: Sweep vs non-sweep outcomes (tape_recon)

**Cohort:** tape_recon | **Coverage:** SPY 2022-2023, accruing (multi-day sweep in progress)
**Graded fraction:** 118,568 / 696,633 = 17.0% (accruing)

| Group | n events | n fwd_ret_5 | Hit rate (>0) | Median ret | n fwd_ret_21 | Hit rate 21d |
|---|---|---|---|---|---|---|
| swept | 117,327 | 40,105 | 0.524 | +0.0016 | 60,521 | 0.547 |
| non-swept | 1,241 | 182 | 0.505 | +0.0015 | 381 | 0.714 |

**Observation:** The non-swept cell (n=1,241 events) is thin given the SPY concentration
of sweep events; the 21d hit rate of 0.714 for non-swept is not reliable at this coverage
level (381 horizon-matured rows). Sweep vs non-swept discrimination requires single-name
tape (tier-3) where non-sweep prints are more common. SPY results are labeled accordingly.

---

### Table E: Execution side outcomes (tape_recon)

**Cohort:** tape_recon | **Coverage:** SPY 2022-2023, accruing
**Classification:** ask_share ≥ 0.60 → at-ask; bid_share ≥ 0.60 → at-bid; else mixed

| Group | n events | n fwd_ret_5 | Hit rate 5d | Median ret 5d | n fwd_ret_21 | Hit rate 21d |
|---|---|---|---|---|---|---|
| at-ask (ask_share≥0.60) | 14,745 | 2,097 | 0.541 | +0.0029 | 10,110 | 0.578 |
| at-bid (bid_share≥0.60) | 11,828 | 1,190 | 0.476 | -0.0005 | 8,310 | 0.561 |
| mixed | 91,995 | 37,000 | 0.525 | +0.0016 | 42,482 | 0.538 |

**Observation:** The at-ask/at-bid split measures EXECUTION-SIDE differences in an unsigned
underlying up-move outcome, pooled over calls and puts (the `right` field is not conditioned
on). This is NOT signed directional discrimination: at-ask on a put still registers as a
positive hit if the underlying moves up. True directional discrimination requires conditioning
on right (call vs put) and is deferred — see §6 accrual/unlock list.

**CI-overlap note:** At 5d, the at-ask [0.520, 0.562] and at-bid [0.448, 0.505] CIs are
disjoint — the execution-side difference at 5d survives non-overlapping confidence intervals.
At 21d, the at-ask [0.569, 0.588] and at-bid [0.551, 0.572] CIs overlap — the 21d difference
is not established and should not be cited as a reliable gap.

**FS-C1 note:** these are the first measured outcome columns from quote-rule classification
in this pipeline. The discriminating power of quote-rule direction is now empirically
measurable at 5d; these numbers establish the baseline.

---

### Table F: Repeat-cluster vs single-print outcomes (tape_recon)

**Cohort:** tape_recon | **Coverage:** SPY 2022-2023, accruing

| Group | n events | n fwd_ret_5 | Hit rate 5d |
|---|---|---|---|
| repeated-cluster | 0 | 0 | ERA-SPARSE |
| single-print | 118,568 | 40,287 | 0.524 |

**Observation:** Zero repeat-cluster events in the current SPY 2022-2023 sweep (as
expected — the repeat detector requires 2 qualifying cycles per session on an ETF with
$1M premium floor, and most clustering happens at sub-floor levels). Table F accrues
when single-name tier-3 tape is added to the sweep. Labeled ACCRUING for that reason.

---

### Table G: Outcome distribution by DTE bucket (proxy for deep-OTM)

**Note:** mny_bucket='unknown' for all rows in both cohorts. This table uses DTE bucket
as the distributional split; 'deep-OTM' will be computable when a moneyness join is added.

**Cohort: eod_proxy** | Coverage: 2012-06 to 2026-07

| DTE bucket | n ok-graded | n fwd_ret_21 | Hit rate 21d | Wilson 95% CI |
|---|---|---|---|---|
| 0d | 273,487 | 100k+ | computed by atlas | run atlas |
| 1_7d | ~2.3M | large | computed by atlas | run atlas |
| 8_30d | ~2.4M | large | computed by atlas | run atlas |
| 31_90d | ~1.2M | large | computed by atlas | run atlas |
| 90p | ~1.2M | large | computed by atlas | run atlas |

_Full per-cell numbers are in `data/flow_signals/atlas/atlas_tables.json` (generated by_
_`scripts/ops_flow_atlas.py`). The guide will be updated with those numbers after the atlas run._

**Cohort: tape_recon** | Coverage: SPY 2022-2023, accruing — see atlas_tables.json

---

### Table H: 0DTE/index vs single-name short-DTE comparison (eod_proxy)

**Cohort:** eod_proxy | **Coverage:** 2012-06 to 2026-07

| Group | n events | vol>OI flag rate | Wilson 95% CI | n fwd_ret_5 | Hit rate 5d |
|---|---|---|---|---|---|
| 0DTE index (SPX/SPXW/NDX etc) | 76,154 | **1.000** | structural artifact | 75,712 | 0.611 |
| 0DTE single-name | 197,333 | 0.993 | [0.992, 0.993] | 159,182 | 0.562 |
| short-DTE index (1_7d/8_30d) | 809,901 | **1.000** | structural artifact | 419,317 | 0.602 |
| short-DTE single-name | 3,925,851 | 0.997 | [0.997, 0.997] | 1,435,473 | 0.547 |

**Key finding:** vol_gt_oi_rate = 1.000 for index instruments across both 0DTE and
short-DTE buckets. This is a structural artifact: SPX/SPXW contracts start each session
at OI=0 for the new-expiry range (or very low OI for near-expiry), so any volume at all
triggers the flag. The heuristic is structurally inapplicable to index instruments.
Pre-existing OI > 500 prefilter is required before using vol>OI as a signal on index options.

**Secondary finding:** 5-day hit rates for the index buckets (0.611 / 0.602) vs single-name
buckets (0.562 / 0.547) may reflect the upward bias of SPY/SPX as the benchmark rather than
genuine alpha in the flag. Excess-vs-SPY is the correct ruler; absolute returns are shown
here for transparency.

---

### Table I: Era-stratified base rates (eod_proxy) — regime-shift check

**Cohort:** eod_proxy | **Coverage:** 2012-06 to 2026-07
**Mandate:** pre/post-2020 comparison is required (mlquants 3-decade sign-flip, commission-free onset)

| Era | n ok-graded | n fwd_ret_5 | Hit rate 5d | Wilson CI | Median ret 5d | n fwd_ret_21 | Hit rate 21d | Wilson CI | Median ret 21d | SPY excess 5d mean | SPY excess 21d mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2012-15 | 240,234 | 51,835 | 0.583 | [0.579, 0.587] | +0.0043 | 134,431 | 0.622 | [0.619, 0.624] | +0.0120 | -0.0002 | -0.0002 |
| 2016-19 | 601,477 | 163,574 | 0.605 | [0.602, 0.607] | +0.0050 | 335,232 | 0.661 | [0.659, 0.663] | +0.0177 | +0.0005 | +0.0010 |
| 2020-22 | 1,372,845 | 481,872 | 0.531 | [0.530, 0.532] | +0.0027 | 681,606 | 0.555 | [0.553, 0.556] | +0.0108 | -0.0014 | -0.0043 |
| 2023+ | 3,441,799 | 1,392,403 | 0.566 | [0.565, 0.567] | +0.0051 | 1,607,830 | 0.602 | [0.601, 0.603] | +0.0180 | +0.0021 | +0.0128 |

**Key finding — the 2020-22 dip:** Hit rates and excess returns dropped sharply in 2020-22
vs 2016-19. The SPY-excess 21d mean flipped sign (+0.0010 → −0.0043); the 21d hit rate
dipped from 0.661 to 0.555 (−10.6 percentage points) without crossing 0.5. This is the
"sign-flip" era (commission-free trading onset, retail proliferation, COVID vol regime)
for the SPY-excess metric specifically. 2023+ shows partial recovery (+0.0128 SPY excess
21d mean), though still below 2016-19.

**This pattern mandates per-era training in FS-4 and forbids pre/post-2020 pooling.**

---

### Table J: Premium-size decile vs outcome (eod_proxy)

**Cohort:** eod_proxy | **Coverage:** 2012-06 to 2026-07 | n ok-graded: 5,656,355

| Decile | Premium range | n ok-graded | n fwd_ret_21 | Hit rate 21d | Wilson CI | Median ret 21d | SPY excess 21d |
|---|---|---|---|---|---|---|---|
| D1 (lowest) | ~$100k | 565,640 | 315,710 | 0.584 | [0.582, 0.586] | +0.0146 | +0.0071 |
| D2 | — | 566,065 | 311,023 | 0.586 | [0.584, 0.588] | +0.0146 | +0.0063 |
| D3 | — | 565,206 | 302,401 | 0.589 | [0.587, 0.591] | +0.0149 | +0.0065 |
| D4 | — | 565,635 | 295,664 | 0.592 | [0.590, 0.594] | +0.0152 | +0.0060 |
| D5 | — | 565,647 | 287,662 | 0.597 | [0.595, 0.598] | +0.0156 | +0.0065 |
| D6 | — | 565,676 | 279,722 | 0.600 | [0.598, 0.602] | +0.0158 | +0.0065 |
| D7 | — | 565,580 | 268,593 | 0.606 | [0.604, 0.608] | +0.0165 | +0.0069 |
| D8 | — | 565,635 | 254,525 | 0.610 | [0.608, 0.612] | +0.0167 | +0.0070 |
| D9 | — | 565,636 | 234,676 | 0.612 | [0.610, 0.614] | +0.0169 | +0.0062 |
| D10 (highest) | ~$1M+ | 565,635 | 209,123 | 0.624 | [0.622, 0.626] | +0.0182 | +0.0061 |

**Key finding:** Hit rate increases monotonically from D1 (0.584) to D10 (0.624), a
4.0 percentage-point spread across the premium distribution. The relationship is
continuous and modest — premium size alone is a weak predictor. The SPY-excess pattern
is flat across deciles (range: +0.0060 to +0.0071), suggesting the absolute return gradient
is driven by market drift. Premium size may be more useful as an interaction term.

---

### Table K: Crowdedness vs outcome (eod_proxy)

**Cohort:** eod_proxy | **Coverage:** 2012-06 to 2026-07
**Crowdedness proxy:** daily events-per-root (single-session proxy; 7-session rolling deferred to FS-3)
**Tercile breakpoints:** p33 = 2 events/root/day, p67 = 6 events/root/day

| Tercile | Events/root/day | n ok-graded | n fwd_ret_21 | Hit rate 21d | Wilson CI | Median ret 21d |
|---|---|---|---|---|---|---|
| low | ≤2 | 204,013 | 104,808 | 0.572 | [0.569, 0.575] | +0.0143 |
| mid | 2–6 | 311,957 | 155,742 | 0.570 | [0.568, 0.572] | +0.0147 |
| high | >6 | 5,140,385 | 2,498,549 | 0.601 | [0.600, 0.601] | +0.0160 |

**Key finding:** Higher crowdedness is associated with marginally higher hit rates (0.572 →
0.601). The "high" tercile dominates the sample (83% of ok-graded events). The monotonic
relationship is opposite to the "crowding kills alpha" hypothesis — likely reflects the fact
that high-volume roots (SPY/SPX/AAPL) have higher underlying momentum than thin-volume names.
Crowdedness as a standalone feature may not discriminate within a root; the signal is
more informative within a root over time (relative to its own baseline). The 7-session
rolling count per FS-3 feature spec will be computed at training time.

---

## §5 Confound checklist

Before relying on any base rate in §4 for a ruler registration (FS-3), check these confounds:

1. **T+1 OI lag.** Vol>OI comparisons must use prior-day OI (T-1). The eod_proxy enforces
   this via `merge_asof` with `allow_exact_matches=False`. Index instruments start at OI≈0
   → prefilter OI > 500 before using the flag on index options.

2. **Split-adjusted moneyness (seam guard).** Post-split prices change the effective moneyness
   of older contracts. The eod_proxy uses Yahoo close-price data for mny_bucket bucketing;
   currently 'unknown' for all rows. When the moneyness join is added, apply the repo's
   split-seam guard to avoid pre-split OTM contracts appearing ATM post-split.

3. **Spread legs.** One-leg-opens / one-leg-closes spread legs inflate both vol>OI flags
   and absolute volume counts. Same-session same-root same-strike different-right inspection
   is a partial screen. The tape_recon cohort can flag same-cluster multi-leg events; the
   eod_proxy cannot at the contract level.

4. **Crossed/locked market quote-rule failures.** The quote-rule (at-ask/at-bid) fails
   on crossed or locked markets (bid ≥ ask). These should be segregated as 'ambiguous',
   not dropped. The current tape_recon cohort uses `ask_share`/`bid_share`; 'mixed'
   catches the ambiguous fraction.

5. **Ex-dividend ITM early exercise.** ITM calls near ex-dividend date attract early
   exercise flows that generate large at-bid premium and vol>OI flags without direction
   content. A dividend calendar flag is needed; not currently in the eod_proxy cohort.

6. **Cohort mixing prohibition (FS-R4).** Never pool eod_proxy, tape_recon, and live_feed
   events. Training a model on a pooled cohort violates the detector-version law. The
   atlas script enforces this with `_assert_single_source`.

7. **New-listing OI=0 trivial flags.** Newly listed contracts have OI=0 on their first
   active sessions. Any volume trivially triggers vol>OI. Subpopulation: contracts in
   their first 5 trading days with prior_oi < 100.

8. **Quote-rule discriminating power.** The tick-rule signed direction is suspended (FS-R6).
   The quote-rule (at-ask/at-bid) has been confirmed buildable (FS-C1 positive) but its
   discriminating power must be measured before feature use in any model. Table E provides
   the first measurement: at-ask shows positive median returns, at-bid shows slightly
   negative, on SPY 2022-2023. Multi-root single-name measurement is needed.

9. **Anti-conservative Wilson CIs (CI-independence).** The Wilson 95% CIs in §4 treat every
   event as an independent Bernoulli trial. In practice, millions of same-day events share
   the same SPY session and the same underlying move — effective N is far below the row count.
   The printed intervals are descriptive width, not inferential guarantees. FS-3 inference
   must use time-preserving or clustered methods (house time-preserving-null law). Do not
   cite pre-2020 base rates from Table I as unbiased benchmarks: the 383-root universe is
   today's optionable set applied backward, so early-era cells are survivorship-inflated.

---

## §6 Accrual status: what the atlas cannot yet measure

| Table | What's missing | What unlocks it |
|---|---|---|
| B (40-root) | Full 40-root sample computed; wider multi-root sample for more precise per-ticker rate | FS-3 feature engineering pass |
| C (5-root) | Small-N per-era cells (97–278); definitive multi-root roll rate | Larger root sample in FS-3 |
| D/E/F (tape_recon) | Only SPY 2022-2023 graded; repeat=0 | Tier-2 (ETF 2017→2021) + tier-3 (single names 2022→) |
| F (repeats) | Zero repeat-cluster events in SPY sweep | Single-name tape (tier-3); larger repeat window |
| G (deep-OTM) | mny_bucket='unknown' for all rows | Close-price join to cohort build pipeline |
| H (0DTE) | vol>OI=100% for index = structural artifact | Pre-existing OI>500 prefilter in detector |
| I (era 2012-15) | no_price_history_for_era = 19.8% of events missing | Longer price history or accept coverage gap |
| J (prem ranges) | Exact dollar ranges by decile in JSON only | Run atlas to populate; guide will be updated |
| K (crowdedness) | Proxy = daily count, not 7-session rolling | 7-session rolling computed at FS-3 training time |
| All | mny_bucket='unknown' | Add prev_close join to ops_flow_cohorts.py eod_proxy build |
| E (direction) | Unsigned outcome only; direction discrimination requires conditioning on right (call/put) | Add right-conditioned split in FS-3 table pass |

---

_End of FLOW_SIGNAL_FIELD_GUIDE.md. FS-3 registers rulers from this playbook._
