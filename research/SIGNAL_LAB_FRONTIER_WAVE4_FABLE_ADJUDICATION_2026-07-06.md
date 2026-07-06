# Signal Lab frontier Wave 4 — Fable adjudication of the 8 source-family constructs — 2026-07-06

Wave 4 (research/SIGNAL_LAB_FRONTIER_WAVE4_PHASE0_2026-07-06.md): 500 raw ideas → 100
independent source/feed constructs → 8 advanced under a rebuilt contract adopted in
response to the wave-3 audit. Triage: Haiku structural extraction + Sonnet fetch
receipts + Sonnet repo/surface census + Opus adversarial judgment.

## Process verdict first: the contract improvements are real

- **Quarantine held.** Wave-3's 48 advances were not re-admitted; the 8 came from the
  fresh 100-construct screen.
- **One-advance-per-feed-family: VERIFIED** — 8 distinct sources, no feed with 2+ advances;
  probe rows stayed probes.
- **No transform-grid residue** in the advances.
- **Bar re-registration accepted.** The doc explicitly declares a strict advance score of
  8.5 with justification (wave-3's collapse redefined what "advance" claims: a plausible
  source path + surface + named baseline, *not* empirical merit). That satisfies wave-3
  standing rule 2, so the 8.63–9.44 scores are not a violation.

The funnel is now trustworthy on **feed discipline**. This wave exposed the next blind
spot: **payoff discipline**.

## The central finding: five feeds, one bet

Six of eight advances (LVCVA, NJ DGE, NV GCB, NY GC, PGCB, and Ticketmaster's venue
geography) pay off through the same ~8 names — MGM, CZR, LVS, WYNN, DKNG, FLUT, PENN
(+LYV). All of them live in the existing `travel` basket. "One advance per feed family"
was honored while five regulators fired into one basket: **one bet dressed as five.**

## Rulings

### CONSOLIDATE → ONE family queued: `w4_multistate_gaming_tape` (absorbs W4-061/076/081/086/091)

Receipts: all five feeds are genuinely **ready** — free, machine-readable or parseable,
with reconstructable history (NY weekly Excel since 2022-01; NJ monthly since 2013-11
for iGaming; NV monthly since 2004; PA slots since FY2006-07 / iGaming 2019; LVCVA
monthly to 2004, annual to 1970). Every single-state print is heavily spanned — trade
press covers releases within hours and DKNG/FLUT move same-day — so no single state is
a candidate. The only defensible edge claim is the one no wire headline provides:
**cross-state aggregation, exposure-weighted per operator** (state-revenue weights from
10-Q segment disclosures), producing a consolidated-revenue nowcast that leads each
operator's quarterly report. Three deliberately orthogonal lanes:

1. **WIN** — NV (regional mix, longest land-based history) + PA (broadest categories);
2. **iGAMING/SPORTS** — NY weekly spine (timeliest, Excel) + NJ (longest online history);
3. **DEMAND** — LVCVA occupancy/ADR/convention attendance (least-spanned lane; reads
   forward, not backward).

Pre-registered nulls: the "trade the state headline same-day" strategy and consensus
revenue estimates — the family must beat both or it is context. Event-study ruler:
operator earnings-surprise vs the nowcast's lead, HAC + BH-FDR across operators, DSR.
Ingestion order: NY+PA Excel first, NJ+NV PDF second, LVCVA last (the
`china_official_corpora` paced-scraper pattern is the in-house template; negligible
nightly load vs the 138 existing collectors).

**Queue position: behind the wave-2 queue, ahead of the FFIEC bank family** —
NHTSA (in flight) → WARN → ITC-337 → CMDI → housing → TSA → **gaming tape** → FFIEC.
It does not jump the queue on the strength of six correlated advances.

### PARK: W4-111 FBI NICS firearm demand

The mechanism is real and genuinely orthogonal to the gaming vertical, but three blocks:
(1) the clean series is proprietary (NSSF-Adjusted; the raw series is distorted by state
permit rechecks — Kentucky/Illinois); (2) decades of prior art — NICS-as-proxy is one of
the most-published alt-data trades in existence; (3) capacity: the payoff set
(SWBI/RGR/AOUT/VSTO) is micro/small-cap and **not in our price-store universe**.
Re-enters only with a legitimate adjusted series and a passed capacity screen.

### KILL: W4-021 Ticketmaster live-event supply

Receipt refuted the premise: the Discovery API is a live catalogue, not an archive —
historical event-supply counts **cannot be reconstructed** (forward-accrual only), and
the ToS prohibits storing event content beyond service needs and deriving revenue from
it. The advance gate ("run the study only if source ingest is real") is structurally
unsatisfiable. Any revisit is a forward-accrual pre-registration with legal clearance,
not an advance.

### KILL: W4-246 California ZEV sales share

Dominated disclosure: for the named payoff surface (TSLA), the ticker's **own quarterly
delivery print (~2-3 days after quarter-end) strictly leads the CEC/DMV data by weeks to
months**. A feed the payoff name front-runs with its own disclosure cannot carry edge for
that name. A non-TSLA maker-mix construct would be a different candidate with a
different surface — re-screen from scratch if wanted.

## Scoreboard

**8 advances → 1 consolidated family QUEUED (5 ids) · 1 PARKED · 2 KILLED.**

## Wave-5 standing rules (adopted; additive to waves 1–3 rules)

- **PO-1 Payoff-orthogonality:** max ONE advance per tradable vertical — a vertical is
  the set of names a construct pays off through, not the source it reads. Constructs
  declare their payoff ticker-set before advancing; >~50% overlap (or a shared basket)
  collapses the group into one consolidated-family representative.
- **PO-2 Dominated-disclosure screen:** kill any construct whose payoff ticker
  self-discloses the same information earlier than the feed publishes (CA-ZEV-vs-Tesla
  is canonical). Receipts must check this explicitly.
- **PO-3 Backtestable-history gate:** forward-accrual-only feeds with no archive cannot
  advance — only pre-register for accrual. "Testable history exists" is a gate, not a
  score component.
- **PO-4 Capacity screen:** payoff sets absent from the price-store universe are not
  advance-ready.
- **The moratorium stands.** Wave-5 intake remains closed until all wave-1 lane verdicts
  and both wave-2 spike verdicts are on the books and the queue is below three items.
  Applied retroactively, PO-1..4 alone collapse wave-4's 8 advances to exactly the
  disposition above — evidence the rules are calibrated, not punitive.

*In plain English: wave 4 fixed the factory — real sources, one idea per feed, honest
labels. The catch it couldn't see: five different state gambling regulators all move the
same eight casino stocks, so five "ideas" were one trade wearing five badges. We merged
them into the one version actually worth testing — stitch all the states together,
weight them by where each company actually earns its revenue, and see if that composite
predicts earnings better than the headlines everyone already trades same-day. The
firearms idea waits (the clean data costs money and the stocks are too small for us),
the Ticketmaster idea dies (no history exists to test), and the California EV idea dies
because Tesla itself tells you the answer weeks earlier.*
