---
key: MARKET-OS
title: Market OS — Market, Security, and My Market flagship
objective: >
  Turn the free stock dashboard, per-security dossiers, Portfolio, and named Watchlists
  into one coherent investing operating system. Done means a user can discover what
  changed, understand one security, track actual holdings and attention sets without
  population drift, receive source-grounded personal impact, and return through useful
  change monitoring across Macro and Terminal.
status: active
program: terminal-user-services
p0: PRODUCT_TRUST_COHERENCE
repos: [macro, terminal]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: M0
    title: Durable architecture, decisions, discoveries, and implementation handoff
    status: done
    next_action: Merge the records PR; do not start runtime work from the records branch.
  - id: A1A
    title: Portfolio Population Truth + State Authority
    status: todo
    depends_on: [M0]
    next_action: >
      After M0 merges, Fable refreshes current heads, worktrees, open PR path collisions,
      and the Active Build Map, then dispatches exactly one Macro runtime PR from the
      canonical A1A handoff. Stop after real production proof.
  - id: A1B
    title: Portfolio Fast Start Import
    status: todo
    depends_on: [A1A]
    next_action: >
      Do not start until Sol accepts A1A in production. Then ship reviewed paste to
      canonical positions with stable identity, atomic/idempotent persistence, and
      Macro/Terminal conformance.
  - id: A2-A6
    title: Persistent sizing assumptions, CSV import, My Market rail, universal add, and Watchlist workspace
    status: todo
    depends_on: [A1B]
    next_action: Commission one independently useful vertical at a time; no broad My Market rewrite.
  - id: B1-B6
    title: Canonical Security State and chart-first security cockpit
    status: todo
    depends_on: [A1A]
    next_action: >
      Build security_state.v1 into the existing stockdata plane and prove one real
      dossier consumer before changing the full dossier composition.
  - id: C1-C6
    title: What Changed and deterministic Market discovery
    status: todo
    depends_on: [B1-B6]
    next_action: Use compact Security State and Change Event projections; no fused rank.
  - id: D1-D9
    title: Portfolio Brief v3, Risk Packet, Holdings Map, visible risk sections, and scenarios
    status: todo
    depends_on: [A2-A6, B1-B6]
    next_action: Preserve the existing risk core and one Portfolio composer; current-context mode precedes forecast mode.
  - id: E1-E3
    title: My Market Overview, personalized change feed, alerts, and digest
    status: todo
    depends_on: [C1-C6, D1-D9]
    next_action: Use deterministic research-priority precedence and privacy-safe user joins.
  - id: F0-F5
    title: Forecast Packet, prospective ledgers, shadow evaluation, and earned promotion
    status: todo
    depends_on: [B1-B6, D1-D9]
    next_action: No live forward claim before point-in-time replay, calibration, forward shadow, and explicit authority promotion.
decisions:
  - "DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE"
  - "DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT"
discoveries:
  - "DSC:MARKET-OS-PASTE-FLOW-WRITES-WATCHLIST-NOT-PORTFOLIO"
  - "DSC:MARKET-OS-AUTHENTICATED-PORTFOLIO-FAILS-OPEN-TO-LOCAL"
landmines:
  - >-
    `templates/market_books.js::buildModel` currently unions Watchlist symbols with
    open Portfolio positions, and existing tests pin that rejected behavior.
  - >-
    `templates/watchlist.js::runEntry` currently mutates the Watchlist and a temporary
    ENTERED overlay; it is not a canonical Portfolio import.
  - >-
    An authenticated Portfolio cloud read failure currently falls through to the local
    anonymous Portfolio and routes later writes locally. That is not an offline outbox.
  - >-
    The Active Build Map is generated/advisory and can be stale relative to current
    main; regenerate and inspect live worktrees before every runtime dispatch.
  - >-
    Terminal PR #429 changes large-Portfolio quote demand; Terminal consumer work must
    re-census its disposition before editing PortfolioView or quote-demand paths.
do_not_redo:
  - Do not create another Portfolio, Watchlist, event, identity, risk, or brief store.
  - Do not merge Watchlist attention membership into Portfolio ownership semantics.
  - Do not call a temporary pasted basket a saved Portfolio.
  - Do not restore the old single-table persistence recommendation from WS:WATCHLIST-PORTFOLIO-CEO.
  - Do not invent a cluster by calling the largest half of the book a hidden bet.
  - Do not silently complete mixed sizing or mixed current/cost price bases.
  - Do not let LLM output originate a signal, rank, gate, size, forecast probability, or trade decision.
  - Do not treat the six-tab Risk Center or giant inline drawers as the final flagship design.
  - Do not call infrastructure or green CI product completion without a real production user journey.
artifacts:
  - research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_A1A_COMMISSIONING_2026-08-20.md
  - agentos/handoffs/MARKET-OS-2026-08-20.md
next_action: >
  Merge M0, then Fable issues A1A Portfolio Population Truth + State Authority as the
  only authorized runtime wave. A1B and every later wave remain blocked on A1A's live
  production acceptance.
---

## Current state

The product thesis and experience/intelligence architecture are frozen. The first six
planning turns established one product with three lenses: Market, Security, and My
Market; one shared Decision Spine; separate public intelligence and private exposure;
and explicit fact, deterministic-state, forecast, and decision authority.

The current Portfolio implementation is not a safe foundation for import or advanced
analysis because it can describe the Watchlist, a temporary basket, or canonical
positions through the same surface. A1A repairs that authority before adding a writer.

## Program-parent note

This workstream cites `terminal-user-services` because the existing semantic registry
owns the shared user-state and alert product boundary. Market OS does not transfer
identity, news, company-event, signal, risk, or forecast authority into that program;
those domain owners remain independent and are composed through governed contracts.
A later semantic-map amendment may introduce a dedicated flagship product program, but
that registry change is not required to begin the bounded A1A truth repair.