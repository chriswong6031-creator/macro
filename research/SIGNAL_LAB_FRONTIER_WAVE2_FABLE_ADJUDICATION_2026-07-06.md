# Signal Lab frontier Wave 2 — Fable adjudication of the 58 `advance_to_fable` candidates — 2026-07-06

Codex's wave-2 screen (research/SIGNAL_LAB_FRONTIER_WAVE2_PHASE0_2026-07-06.md) screened
200 candidates across 20 lanes and advanced 58. This is the Fable review, run the same
day as the wave-1 adjudication and under the standing rule wave 1 established: **a
`data_state` tag must be earned by a fetch receipt, not asserted.** Every one of the 58
got a receipt check (true source, URL, first date, fields, lag, access tier), a
duplication/routing census against the repo, and an adversarial materiality review.

## The screen itself regressed from wave 1 — findings

1. **Threshold regression.** Wave 1 required all-gates AND score ≥10.0 to advance.
   Wave-2 advances score 6.93–9.35 — zero would clear wave 1's own bar. Nothing in the
   docket declares the change. The two waves' "advance" verdicts are not comparable.
2. **Lane-constant scores.** Every candidate in a lane carries an identical score
   (all 8 weather advances = 9.35, all freight = 8.17, …). The score ranks lanes, not
   candidates; sibling selection was an unstated top-k quota, with
   `not_wave2_strategic_priority` as a filler blocker (a tautology, not a diagnosis).
3. **Placeholder sources.** The Source column is lane boilerplate and frequently wrong:
   NHTSA/EPA/OSHA candidates "sourced" to USPTO trademark data; remittances and customs
   to NASA MODIS NDVI; rail carloads to NOAA AIS. Receipts had to re-derive the true
   source for nearly every candidate.
4. **Cross-listing inflation.** The same feed appears as multiple "advances"
   (NHTSA twice: W2-096/156; KEV twice: W2-031/033; night-lights three times:
   W2-021/181/185; one Redfin feed = three housing advances). The 58 reduce to roughly
   a dozen distinct viable mechanisms.

**Receipt outcome across the 58: 13 ready · 40 partial · 5 refuted** — the same
self-assessment failure wave 1 measured, at larger scale.

## Scoreboard

**2 spike families AUTHORIZED (4 ids) · 5 QUEUED (7 ids) · 11 ROUTED · 10 PARKED/WATCH · 26 KILLED.**

Capacity law applied: nine wave-1 build lanes are in flight today, the nightly render
budget is hard-capped, and every collector is permanent maintenance. Wave 2 therefore
earns **zero new nightly collectors today**. Authorized work runs as bounded, off-render
phase-0 spikes; a collector is only built after a spike clears its pre-registered gates.

## AUTHORIZED — off-render phase-0 spikes (no nightly collectors yet)

| # | IDs | Family | Why it made the cut |
|---|---|---|---|
| S1 (dispatch now) | W2-031 + W2-033 | **CISA KEV vendor-exposure shock** (`w2031_kev_vendor_shock`) | The consensus best row: free keyless daily feed, PIT-clean (`dateAdded` is carried in the catalog), event-study native, maps to liquid US software single names, catalog since 2021-11 aligns with our 5y price store. W2-033 (patch-deadline wall) folds in as a pre-registered variant of the same family — same feed, one trial budget. Honest prior: breach-event literature says small/transient effects; expected home is event-context display for the special-situations desk. |
| S2 (dispatch when a wave-1 lane frees) | W2-096 + W2-156 | **NHTSA defect escalation** (`w2096_nhtsa_defect`) | Free keyless ODI API with deep history (complaints to 1995), cleanly ticker-mappable (automakers/suppliers). W2-156 (complaint acceleration) folds in as a variant; its "per active fleet" denominator is struck (registration data is paid) — sales-proxy denominator pre-registered instead. |

## QUEUED — one at a time, behind the spikes and wave-1 verdicts

| IDs | What | Condition |
|---|---|---|
| W2-044 | WARN layoff intensity phase-0 | Only via the Cleveland Fed consolidated WARN database (a 50-state scrape is rejected as permanent maintenance); verify its coverage/lag first. |
| W2-153 | ITC Section 337 exclusion-risk event study | Free USITC docket; sharp rare events; run as bounded spike. |
| W2-104 | CMDI conditioning study | NY Fed CMDI is free/monthly/2005+; test as SPY-drawdown de-escalation input **vs the existing HY-OAS timer baseline** — the credit lane's only free survivor. |
| W2-051/052/054 | ONE consolidated housing high-frequency product (Redfin weekly + ZORI monthly) | Display/conditioning for cycle-intelligence; three "advances" are one build. Expect macro-spanned; gate vs mortgage-rate + XHB-trend baselines. |
| W2-061 | TSA throughput | Trivial collector, national aggregate only, heavily watched — a conditions-desk display series, not a signal family. Build when a collector slot is free. |

## ROUTED to existing programs (no new families)

- **W2-034 cyber 8-K Item 1.05** → special-situations desk: add item 1.05 to the existing
  item-code taxonomy (trivial extension) and ACCRUE. Receipt refuted it as a backtest:
  the item exists only since 2023-12 and most incidents still file under 8.01 — n is not
  viable for gates yet.
- **W2-091 Federal Register comment surge** → foresight desk (collectors/federal_register.py
  already exists; this is an extension, not a family).
- **W2-121/122/124 grid (ERCOT, PJM, data-center load)** → institutional-sector-intelligence
  backlog. W2-124 is topical and genuinely un-spanned but its assembly (queue spreadsheets +
  IRP PDFs) is heavy; the program decides if it's worth the weight.
- **W2-127 LNG feedgas** → EIA collector extension (weekly LNG exports are free); commodity
  desk backlog.
- **W2-081/082/083 flu / wastewater / FAERS** → healthcare/foresight backlog as seasonal
  conditioners; FAERS' prescription denominator is annual-only (CMS Part D), stated up front.
- **W2-131/132 TIC / reserve drawdown** → intl program backlog (deep-lag, EM-facing; the
  intl program owns that surface).

## PARKED / WATCH (10)

W2-001 (PortWatch has the right fields but only ~2.5y — accruing; NOAA AIS spine is heavy),
W2-003 (container-rate history is request-gated/paywalled; SCFI mirror is the only free leg),
W2-004 (weekly AAR breadth beyond 2 weeks is paid; monthly FRED total is spanned),
W2-011 (CDD/HDD — utilities conditioning if sector-pulse wants it), W2-013 (drought — ag-equity
surface is weak), W2-062 (OpenTable access is gray), W2-119 (BDC discount — real but niche;
credit backlog), W2-146 (app reviews — no free API, gray ToS), W2-151 (trademark pipeline —
assignee mapping is the build), W2-161 (arXiv — sector-level only, spanned by tech trend).

## KILLED (26)

- **Refuted constructs:** W2-041 (ticker-level postings don't exist free — Hiring Lab is
  aggregate, and conditions.py already consumes it), W2-117 (private marks are paid),
  W2-092/093 (issuer-exposure mapping requires a paid supply-chain graph; policy desks
  already cover the theme), W2-046 (aggregate wage data already in repo via ECI).
- **Already built:** W2-133 (BIS credit — collectors/bis.py is live), W2-141 (three GDELT
  layers exist; tone work belongs to the news desk), W2-149 (narrative crowding — the
  narrative-momentum family already measured rank-IC≈0).
- **Off-surface lanes** (payoff lives in instruments the house does not trade):
  agriculture cluster W2-071/072/074/077, weather W2-014/017, water/carbon
  W2-171/172/173/175, fixed-income plumbing W2-101/103, satellite/EM
  W2-021/028/181/182/185, standards W2-168.

## Standing rules for wave-3 dockets (additive to wave 1's fetch-receipt law)

1. **No lane quotas.** An advance must clear a declared absolute bar; "top-k per lane"
   verdicts are void.
2. **One bar across waves.** The wave-1 bar (all gates + score ≥10) stands until a
   docket explicitly re-registers a different one with justification.
3. **One construct per feed.** Multiple candidates on the same feed must be declared as
   variants of one family sharing one trial budget, not separate advances.
4. **Per-candidate sources.** Lane-templated Source/PIT/Years fields void the affected
   verdicts automatically.

*In plain English: wave 2 proposed 58 ideas, but the screening quality dropped — scores
were copied per theme, sources were wrong, and the pass bar was quietly lowered, so an
"advance" stopped meaning much. After verifying every data source, most ideas were
duplicates, unbuildable without paid data, or bets on markets we don't trade. Two things
were genuinely good and cheap to test — cyber-vulnerability shocks hitting software
vendors, and safety-defect escalations hitting automakers — and those are being tested
properly. A handful more wait in line; the rest are recorded with reasons so nobody
re-proposes them cold.*
