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
    status: done
    depends_on: [M0]
    next_action: >
      ACCEPTED IN PRODUCTION by Sol on 2026-08-23 under
      DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION. Engineering closed across #6098,
      #6109, #6136, and #6160; PD1 Terminal mutation authority repair #456 is
      merged/deployed; the semantic-v2 restoration blocker was resolved under
      DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS; the
      one-row restoration probe passed; and the final authenticated production matrix
      passed true-zero, one-position, all-unsized equal-assumption, mixed-sizing
      abstention, degraded-last-good, first-read explicit unknown, continuous
      Macro-Terminal conformance, privacy, exact temporary cleanup, sequential
      semantic-v2 restoration, and immediate plus delayed reconciliation. The sealed
      canonical 13-row Portfolio and four-list/134-membership Watchlist baselines were
      restored with no temporary residue. Do not repeat the matrix absent contradictory
      production evidence or explicit recommission. A1A acceptance does not implement
      or automatically start A1B. Scene 9 was intentionally prohibited by the later,
      specific authenticated-matrix authorities and was not executed; Sol's final
      acceptance supersedes the older account-transition production-proof clause in
      DEC:MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED for A1A completion.
      That clause is not hidden A1A debt, while the merged #6160 auth-generation
      protections remain intact.
  - id: A1B
    title: Portfolio Fast Start Import
    status: todo
    depends_on: [A1A]
    next_action: >
      A1A is now accepted, so A1B is eligible for a separate bounded Sol commission.
      Before any code write, refresh current Macro main, protected Terminal master,
      open PR/worktree/path collisions, the Active Build Map, and the canonical
      portfolio_positions mutation/identity contracts. Then ship one reviewed paste
      to canonical positions vertical with stable identity, atomic/idempotent
      persistence, lost-response safety, and Macro/Terminal conformance. Do not absorb
      A2-A6 or a broad My Market rewrite.
  - id: A2-A6
    title: Persistent sizing assumptions, CSV import, My Market rail, universal add, and Watchlist workspace
    status: todo
    depends_on: [A1B]
    next_action: Commission one independently useful vertical at a time; no broad My Market rewrite.
  - id: B1A
    title: security_state.v1 golden AAPL product vertical (contract + compiler + producer + dossier Decision Spine)
    status: in_review
    depends_on: [A1A]
    next_action: >
      DELIVERED-HELD 2026-08-24 under the Chairman dispatch of the prepared B1A
      commission: identity gate adjudicated PASSED instance-scoped via the exact
      owner-backed chain (DEC:MARKET-OS-B1A-IDENTITY-GATE-OWNER-BACKED-CHAIN —
      adversarial BLOCKED verdict preserved inside as dissent), K1 evidence
      composition runs cik-native (four-owner golden fixture untouched, still
      REFUSED), producer is a frozen ("AAPL",) allowlist stage in
      build_stock_library, consumer is the server-rendered Decision Spine on the
      AAPL dossier. The B1A PR is DRAFT + HOLD-FOR-SOL — Sol reviews the
      adjudication, implementation, and browser evidence; do not arm or merge.
      Production proof (live object + live page) executes only after Sol accepts
      and merges; capability is BUILT_NOT_PROVEN until then. Universe expansion
      beyond AAPL is BLOCKED on the owner-routed ListingAlias→ListingKey
      renderer + K1 vocabulary triple repair (named Sol item), and
      CIK_LEG_UNOWNED_ACCESS names the reader-surface repair
      (expose issuer_cik on lib.dataos.identity readers).
  - id: B1B-B6
    title: Terminal/Desk projection and chart-first security cockpit over frozen security_state.v1
    status: todo
    depends_on: [B1A]
    next_action: >
      Separate commission after Sol accepts B1A; B1B requires the frozen
      security_state.v1 surface plus the identity-renderer repair before any
      second issuer.
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
  - "DEC:MARKET-OS-B1A-IDENTITY-GATE-OWNER-BACKED-CHAIN"
  - "DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE"
  - "DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT"
  - "DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS"
  - "DEC:MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED"
  - "DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION"
discoveries:
  - "DSC:MARKET-OS-PASTE-FLOW-WRITES-WATCHLIST-NOT-PORTFOLIO"
  - "DSC:MARKET-OS-AUTHENTICATED-PORTFOLIO-FAILS-OPEN-TO-LOCAL"
  - "DSC:MARKET-OS-MUTATION-SUCCESS-REQUIRES-AFFECTED-ROW"
landmines:
  - >-
    FIXED by A1A (#6098): `templates/market_books.js::buildModel` no longer unions
    Watchlist symbols into Portfolio books and the pinning tests were replaced.
    Do not restore the union; population law is §11 of the A1A freeze.
  - >-
    `templates/watchlist.js::runEntry` currently mutates the Watchlist and a temporary
    ENTERED overlay; it is not a canonical Portfolio import. A1B owns the future
    canonical paste/import path and must not reuse this mutation as Portfolio authority.
  - >-
    FIXED by A1A closure (#6136): identity decides authority (_isLocalMode := !user);
    an authenticated cloud failure resolves degraded/error (last-good read-only or
    explicit unavailability), never the local book, and failed Portfolio writes say
    "Change not saved" — never the Watchlist's "changes kept locally" claim. There is
    still NO authenticated offline outbox; do not claim retention on write failure.
  - >-
    The Active Build Map is generated/advisory and can be stale relative to current
    main; regenerate and inspect live worktrees before every runtime dispatch.
  - >-
    Terminal PR #429 changes large-Portfolio quote demand; Terminal consumer work must
    re-census its disposition before editing PortfolioView or quote-demand paths.
  - >-
    A1A semantic-v2 restoration excludes only created_at and updated_at because they
    are server-generated metadata. Never broaden that exception to identity, owner,
    semantic fields, multiplicity, Watchlists, Macro-Terminal agreement, or the
    separately sealed ordered row-id sequence; the exception changes no product or
    database semantics for either timestamp.
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
  - Do not attempt to preserve created_at or updated_at during the bounded A1A restore; omit both and let production generate them.
  - Do not repeat the passed semantic-v2 temporary-row restoration probe; its exact cleanup receipt is durable in the latest handoff.
  - Do not repeat the passed final authenticated A1A production matrix unless new contradictory production evidence appears or Sol explicitly recommissions it.
  - Do not reopen Scene 9 as hidden A1A debt; it was prohibited by the later specific matrix authorities and Sol accepted A1A without it.
  - Do not treat merged PR #6125's pre-production-proof BUILT_NOT_PROVEN state as the current gate; preserve it as historical reconciliation evidence.
artifacts:
  - research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_A1A_COMMISSIONING_2026-08-20.md
  - agentos/handoffs/MARKET-OS-2026-08-20.md
  - agentos/handoffs/MARKET-OS-2026-08-21.md
  - agentos/handoffs/MARKET-OS-2026-08-22.md
  - agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-blocker.md
  - agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-v2-probe.md
  - agentos/handoffs/MARKET-OS-2026-08-23-a1a-final-authenticated-matrix.md
  - agentos/handoffs/MARKET-OS-2026-08-23-a1a-sol-acceptance.md
  - agentos/handoffs/MARKET-OS-2026-08-20-a1a-merge-reconciliation.md
  - agentos/decisions/DEC-MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED.md
next_action: >
  PRIMARY: commission exactly A1B Portfolio Fast Start Import after a fresh current-head,
  open-PR/worktree/path-collision, Active Build Map, and canonical mutation/identity
  census across Macro and protected Terminal. A1B must write reviewed paste/import rows
  to canonical portfolio_positions with stable identity, atomic/idempotent persistence,
  lost-response safety, and Macro-Terminal conformance; do not absorb A2-A6. PARALLEL:
  RCTX-1 remains bound to merged #6300 and its existing Fable DELIVERY_ONLY transport;
  reconcile only when real ACK/branch/PR/return evidence appears and do not auto-failover.
---

## Current state

The product thesis and experience/intelligence architecture are frozen. The first six
planning turns established one product with three lenses: Market, Security, and My
Market; one shared Decision Spine; separate public intelligence and private exposure;
and explicit fact, deterministic-state, forecast, and decision authority.

A1A is accepted in production. The canonical Portfolio population/state authority seam
is now a proven foundation for the next import wave: authenticated users do not fail open
to local Portfolio state; Watchlists and temporary baskets do not enter Portfolio count,
market membership, weighting, book or risk; weighting assumptions and abstention are
explicit; and Macro/Terminal agreement has been demonstrated across the frozen live
matrix. Fast Start Import itself is still NOT_BUILT and must arrive through A1B rather
than by relabeling the existing Watchlist/ENTERED paste path.

## Program-parent note

This workstream cites `terminal-user-services` because the existing semantic registry
owns the shared user-state and alert product boundary. Market OS does not transfer
identity, news, company-event, signal, risk, or forecast authority into that program;
those domain owners remain independent and are composed through governed contracts.
A later semantic-map amendment may introduce a dedicated flagship product program, but
that registry change is not required to continue the bounded Market OS sequence.
