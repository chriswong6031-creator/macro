---
key: WATCHLIST-PORTFOLIO-CEO
title: Watchlist + Portfolio CEO revamp — compatibility redirect
objective: >
  Preserve the historical W0/P0-husk record and route any legacy continuation into
  WS:MARKET-OS without authorizing the stale persistence fork or the prior W2–W4 page
  hierarchy. Done means A1A is accepted and every remaining consumer no longer relies
  on this legacy readiness identity, after which this redirect can be parked.
status: active
program: terminal-user-services
p0: PRODUCT_TRUST_COHERENCE
repos: [macro, terminal]
owner: coo-fable
class: design
blast_radius: user_facing
ambiguity: scoped
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
    title: Compatibility redirect into Market OS A1A
    status: todo
    depends_on: [P0-HUSK]
    next_action: >
      Do not implement the legacy persistence proposal. Continue only through
      WS:MARKET-OS A1A Portfolio Population Truth + State Authority.
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
  is A1A Portfolio Population Truth + State Authority. This legacy record authorizes no
  implementation of its former W1 persistence proposal.
---

## Supersession and compatibility record

This workstream captured the first Watchlist/Portfolio revamp and the emergency husk
repair. Its original unresolved recommendation was a single positions table with a kind
discriminator. That fork is stale: the shared product now has separate canonical
`portfolio_positions`, `watchlists`, and `watchlist_symbols` stores, and Terminal has a
positions-only `/portfolio` implementation.

The larger Chairman commission also exceeds this workstream's scope. The flagship now
joins Market discovery, per-security research, actual Portfolio exposure, named
Watchlists, charting, changes, catalysts, evidence, and eventual continuous intelligence.
The durable successor is `WS:MARKET-OS`.

This record remains an active compatibility redirect for now because repository tests
and older session entry points still use its readiness identity as a fixture. `active`
and W1 `todo` mean only “follow the redirect”; they are not authority to resume the old
persistence design. A later bounded fixture-decoupling wave may park this record after
A1A is accepted and those consumers no longer rely on it.

## What remains reusable

- canonical shared user-state tables and RLS;
- local anonymous stores and one-shot account fold lessons;
- existing risk mathematics and Portfolio context;
- bilingual/light/dark/responsive regression assets;
- split-deploy and old-HTML/new-JS lessons;
- the principle that missing data degrades rather than sharpens.

Those assets are inputs to Market OS. The old page hierarchy is not its product
architecture.
