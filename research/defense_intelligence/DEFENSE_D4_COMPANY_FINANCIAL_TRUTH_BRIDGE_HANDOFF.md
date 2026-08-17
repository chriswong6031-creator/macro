# D4 — Company financial truth bridge

**Wave:** D4  
**Depends on:** D3 returned.  
**Status:** written, unauthorized.  
**Owner-plane law:** consume Earnings / SEC / estimates / prices. **Do not fork** a defense 10-K, transcript, or consensus store (`DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE`).

## Observable mission

One golden company dossier (frozen: **IRDM**) joins a reviewed procurement event (P00032) to reported backlog/segment commentary **if the Earnings/SEC packet exists**, prints nulls when it does not, and never confuses obligation, backlog, revenue, or cash. Target look: `evidence/compositions/d2-company-dossier-irdm.html`.

## Why it matters

The candidate already lists possible earnings channels and a **null denominator** (`exact_issuer_attributed_denominator_not_available`). The missing work is a join to the company-truth owner, not a GovRev parser.

## Authority precedence

- Award facts: GovRev.
- Filing/transcript/guidance: Earnings/SEC.
- Ticker/listing: Stock Identity (IRDM live as of 2026-08-13 snapshot).
- Estimates: licensed owner or **null**.
- Prices: market owner.
- Prophet / Neural Web: context consumers only; `is_neuralweb_trade_candidate` stays false unless those owners independently say otherwise — D4 must not flip it.

## Verified current state

L6 in `D0R_RUNTIME_LINEAGES.md`. Graph review fixtures under `tests/fixtures/govrev_issuer_evidence/` are **not** a live earnings print. Crosscheck legs `not_evaluated`.

## Exact scope / files

- Dossier panel on `templates/government-revenue-dossiers.js` / GovRev page
- Read APIs/packets already owned by earnings/company-intelligence (do not copy JSON into GovRev `data/`)
- Materiality block remains receipt-bound; denominator only if the earnings owner supplies an **issuer-attributed** figure with its own clock
- Tests: IRDM P00032 still null-ratio unless a real denominator packet is present; copy never says “revenue +$18.4M”

## Explicit non-goals

- No second EDGAR crawler.
- No scraped consensus.
- No frontend score, backlog/revenue ratio invented from USAspending.
- No expansion to 31 issuers (IRDM only).
- No Prophet authority.

## User journey

1. Open IRDM dossier.
2. Government rail: P00032 clocks + official URL.
3. Company rail: latest 10-K/10-Q/transcript packet from the earnings owner **or** “company packet unavailable”.
4. Divergence line: “award tape observed $18.4M obligation on 12 May; company packet does not yet attribute a denominator.”
5. Stance: Watch for the next print. Not a buy.

## Data / null / correction

If the earnings packet restates, follow that owner’s restatement clock. GovRev receipts stay immutable. Missing estimates → null, not zero.

## Government vs company divergence

Obligation ≠ funded backlog ≠ sales ≠ cash. D4’s only allowed inference is “join not comparable yet” (`comparison_state: not_comparable` already on the candidate).

## Ordered steps

1. Locate the live IRDM earnings/SEC packet on main (or document absence).
2. Add dossier sections that **embed** those packets by ticker + period.
3. Keep GovRev materiality null without a receipted denominator.
4. Tests + entitled screenshot vs the D2 HTML composition.
5. Stop.

## Tests and production proof

- Fixture: candidate with null denominator still renders no ratio.
- Production IRDM dossier: both rails visible; no “Members only”; no revenue mislabel.

## Rollback

Revert dossier UI. Earnings plane untouched.

## Stop condition

IRDM dossier proven. Do not build the backlog/revenue/cash cockpit for the whole golden set. Return before D5 program graph.

## Continuation

Record whether a live earnings packet existed. If not, D5 must not pretend D4 “joined financials.”
