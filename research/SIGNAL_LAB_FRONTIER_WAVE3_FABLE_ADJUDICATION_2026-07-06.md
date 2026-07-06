# Signal Lab frontier Wave 3 — Fable adjudication of the 48 `advance_to_fable` candidates — 2026-07-06

Wave 3 (research/SIGNAL_LAB_FRONTIER_WAVE3_PHASE0_2026-07-06.md) screened 500 candidates
across 50 lanes and advanced 48 under a self-described "strict contract" adopted in
response to the wave-2 audit. This is the Fable review.

## Structural finding: 48 advances = 4 feeds × a transform template

The docket restored the ≥10.0 bar in name and defeated it in mechanism:

1. **All 500 candidates are 10 generic transform templates** (level shock, acceleration
   impulse, breadth diffusion, dispersion fracture, persistence streak, baseline
   divergence, exposure-weighted event, backlog pressure, peer-relative reversal,
   compound stress) stamped onto 50 feeds.
2. **Scores are template-deterministic.** Within every lane the per-variant offsets are
   byte-identical (level +0.11 vs base, accel +0.07, breadth +0.04, compound +0.18, …).
   The bank lanes, the tax lane, and the Orange Book lane share the exact same offset
   sequence. The "score" is lane-base + fixed template constant; the strict bar merely
   selects lanes whose self-assessed base clears ~9.83.
3. **The 48 advances collapse to four data feeds**: FFIEC call reports (three bank lanes
   × 7 variants = 21, plus a fourth below-bar AOCI lane on the same feed), Census QTAX
   (10), FCC spectrum auctions (10), FDA Orange Book (7).

This violates standing rule 3 from the wave-2 adjudication — **one construct per feed;
variants share one family and one trial budget** — at maximum amplitude. A transform
grid is what `TrialLedger.log_grid` is for inside a single family's pre-registration.
It is not a candidate list. Under rule 3, wave 3 is a **4-candidate docket**, and it was
adjudicated as one.

## Rulings on the four feeds

### 1. FFIEC bank call-report stress → **QUEUE as ONE family** (`w3_bank_callreport_stress`)

The one genuinely valuable idea in the docket — with the naive version explicitly struck.

- **Receipt (verified):** FFIEC CDR bulk free 2001+, FDIC BankFind API free; the correct
  instrument for listed tickers is **FR Y-9C holding-company filings** (Chicago Fed bulk)
  joined via the NY Fed **PERMCO-RSSD crosswalk** (~500–800 listed BHCs). PIT law: signal
  timestamp = public release (~30–45d after quarter-end), never quarter-end. Known field
  caveats recorded: RCON5597 (uninsured deposits) only for ≥$1B banks with a 2009
  definition break; FHLB advances span multiple RC-M lines.
- **Repo truth:** our EDGAR fundamentals panel has zero bank-specific fields; a
  `regional_banks` basket (KRE proxy, 20 members) already exists as the tradable surface.
- **Red-team ruling (adopted in full):** the canonical post-SVB LEVEL ratios
  (uninsured share, AOCI/HTM gap, wholesale funding) are the most-screened bank metrics
  on earth since Jiang-Matvos-Piskorski-Seru 2023 and are front-run off 10-Qs — that leg
  is **spanned** and enters only as a control. The defensible sub-construct is the
  **CRE maturity-wall roll-through** (roll schedule + reset economics are not cleanly
  disclosed at name level; deterioration is multi-quarter and ongoing 2024–2026).
- **Frozen family design:** V1 CRE-roll (primary), V2 deposit-mix deterioration streak,
  V3 canonical-ratio level composite as a **spanned-ness control** (V1 must beat V3
  outside the 2023 window or the family carries no incremental information), V4 21d-ruler
  robustness (non-gated), V5 AVOID-side drawdown lens (non-gated, per the L1 short-side
  charter: AVOID-not-SHORT). Three gated trials, BH-FDR within family, DSR ≥0.90 the only
  door to GO.
- **Crisis-concentration honesty gate (binding):** 2018–2026 contains ~one bank-stress
  episode (Mar-2023); leave-one-crisis-out is impossible at n=1. Mandatory ex-2023
  decomposition; the pre-registered expectation is that the first adjudication lands
  **ACCRUE-with-clock awaiting a second independent episode**, not GO. A spectacular
  in-sample Sharpe here is the archetypal single-event dummy.
- **Position in queue:** behind the wave-2 spikes (KEV S1, NHTSA S2) and the wave-2
  queue. New ingestion plane (FFIEC/Y-9C) is a real build cost; it also has standalone
  data-product value adjacent to the fundamentals-metric-buildout program.

### 2. FDA Orange Book LOE cliff → **ROUTE to healthcare backlog as a display calendar; archival starts now**

- **Critical PIT hazard (receipt):** the live monthly file removes expired patents — it
  cannot reconstruct what was known at time t. Retrospective PIT exists only at ANNUAL
  granularity (NBER vintages 1985–2016, FDA annual editions 2016+), and the 2023–2025
  FTC delisting wave makes recent vintages anomalous. Any backtest claim on the live
  file is void by construction.
- Zero LOE coverage exists in the repo; LOE calendars are street-standard (every pharma
  desk runs them), so the expected home is desk context, not edge.
- **Action routed:** healthcare program may build an LOE display calendar; a monthly
  snapshot archive should start accruing NOW if any future signal work is wanted.

### 3. FCC spectrum-auction capital intensity → **KILL**

Receipt confirms ~13–15 auctions with material proceeds in 2010–2026, event-driven with
a 2.3-year authority lapse (2023–2025). Ten "variants" were advanced on a feed with
n≈14 events. No gate can pass; qualitative telecom-capex context at most.

### 4. Census QTAX state/local tax mix → **KILL**

Real, clean, 1962+ — and published ~10–11 weeks after quarter-end with no liquid mapped
instrument (we do not trade munis; the repo's only mention of "municipal" is a filter-out
list). A macro regime footnote, not a signal.

## Meta-ruling: generation moratorium

Three waves in one day: 1,260 candidates screened, 129 "advanced", **zero empirical
verdicts returned yet** — the wave-1 harnesses were still running while wave 3 was being
generated. The funnel is inverted ~100:1 generation-over-verification. Ruling:

1. **Wave-4 intake is CLOSED** until (a) all wave-1 lane verdicts and both wave-2 spike
   verdicts are on the books, and (b) the authorized queue has drained below three items.
2. **Docket cap:** future dockets ≤20 candidates, each with a fetch receipt attached at
   generation (URL + first/last date + fields + lag), one row per feed-construct, with
   transform variants declared inside the row as the family's trial grid.
3. **Template-deterministic scoring voids verdicts** (additive to wave-2 rule 4): if
   per-candidate scores are reconstructable as lane-base + fixed offsets, the docket's
   verdict column is void and only feed-level adjudication applies.
4. The screening model's role remains ranking and drafting; `ready` claims and advance
   verdicts are earned by receipts and Fable review. (Wave-1 rubric ruling, restated —
   it has now been violated in a different way in each of three consecutive waves.)

## Wave-3 scoreboard

**1 family QUEUED (absorbing 28 of the 48 ids across four FFIEC lanes) · 1 ROUTED
(Orange Book display + archive accrual) · 20 ids KILLED (FCC ×10, QTAX ×10) · docket
verdict column VOID under rule 3/rule "template scoring".**

*In plain English: wave 3 answered our audit by putting the pass bar back — and then
graded itself just above it. Five hundred "ideas" were really ten copy-paste transforms
applied to fifty data feeds, and the 48 winners boil down to four feeds. One of them —
bank balance-sheet stress from regulatory filings — is genuinely worth testing, but the
obvious version became the most-watched number in finance after SVB, so we're testing
the one corner that's still plausibly slow (commercial-real-estate loan walls rolling
through bank books), with the written-down expectation that the first verdict will be
"keep watching", because there's only been one banking crisis in the sample. The other
three feeds die on arithmetic: a handful of spectrum auctions can't support statistics,
and state tax data arrives three months late for markets we don't trade. And the idea
factory is now paused until the test bench catches up.*
