---
key: WATCHLIST-PORTFOLIO-CEO
title: Watchlist + Portfolio CEO revamp (superseded by Market OS)
objective: >
  Preserve the historical W0/P0-husk record and prevent later sessions from resuming
  its stale persistence fork or treating its shipped W2–W4 information architecture as
  the final flagship. This workstream is parked; all continuation belongs to
  WS:MARKET-OS.
status: parked
program: terminal-user-services
p0: PRODUCT_TRUST_COHERENCE
repos: [macro, terminal]
owner: coo-fable
class: design
blast_radius: user_facing
ambiguity: specified
waves:
  - id: W0
    title: Initial revamp shipped
    status: done
    pr: 5457
  - id: P0-HUSK
    title: "P0 husk cured — 6-file shell, graded plane walled, shim trap closed"
    status: done
    pr: 5463
  - id: W1
    title: Persistence-model decision and continuation
    status: dropped
    depends_on: [P0-HUSK]
    next_action: >
      Do not resume. Separate canonical tables and the positions-only Terminal surface
      are already established; the product continuation is WS:MARKET-OS A1A.
decisions:
  - "DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE"
  - "DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT"
do_not_redo:
  - Do not reopen the stale one-table-versus-two-table CEO question.
  - Do not treat a Watchlist as owned Portfolio exposure.
  - Do not continue the six-tab Risk Center or giant drawer information architecture as the final design.
  - Do not call the prior revamp complete merely because W0–W4 runtime pieces exist.
next_action: >
  Use WS:MARKET-OS. After its M0 records merge, the only authorized runtime continuation
  is A1A Portfolio Population Truth + State Authority.
---

## Supersession record

This workstream captured the first Watchlist/Portfolio revamp and the emergency husk
repair. Its original unresolved recommendation was a single positions table with a kind
discriminator. That fork is stale: the shared product now has separate canonical
`portfolio_positions`, `watchlists`, and `watchlist_symbols` stores, and Terminal has a
positions-only `/portfolio` implementation.

The larger Chairman commission also exceeds this workstream's scope. The flagship now
joins Market discovery, per-security research, actual Portfolio exposure, named
Watchlists, charting, changes, catalysts, evidence, and eventual continuous intelligence.
The durable successor is `WS:MARKET-OS`.

## What remains reusable

- canonical shared user-state tables and RLS;
- local anonymous stores and one-shot account fold lessons;
- existing risk mathematics and Portfolio context;
- bilingual/light/dark/responsive regression assets;
- split-deploy and old-HTML/new-JS lessons;
- the principle that missing data degrades rather than sharpens.

Those assets are inputs to Market OS. The old page hierarchy is not its product
architecture.