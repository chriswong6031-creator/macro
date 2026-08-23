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
    status: in_progress
    depends_on: [M0]
    next_action: >
      Engineering closed and live 2026-08-21 across three Sol rounds: #6098
      (initial wave), #6109 (serving allowlist), #6136 (round-2 blockers +
      snapshot authority; 2633380f800a), #6160 (round-3 P0 auth-generation
      binding for every portfolio op + consumer request-generation guard, risk
      provenance {scope,gen} minted at the FX universe resolution with
      fail-closed consumer rejection, wl-auth AUTO_W latch clear, client-init
      terminality; merge 9ed19a144a28; two-commit PR, adversarially reviewed,
      every guard mutation-red-proven). The #6109 merge-over-hold incident is
      recorded (DEC:MERGE-AUTOMATION-MUST-ENFORCE-RECORDED-HOLDS) and enforced
      in automation (#6149, merge 8a1b93889061). Anonymous production matrix
      PASSED live (round-2 receipts in agentos/handoffs/MARKET-OS-2026-08-21.md;
      round-3 re-verification after render at merge sha). PD1 Terminal mutation
      authority repair #456 is merged/deployed at 3f85efeb19bd and its bounded
      authenticated one-sentinel create/update/failure-honesty/close/reopen/delete
      production reproof passed with exact receipts, Macro-Terminal canonical
      agreement, durable cleanup to the sealed 13-row multiset, and unchanged
      Watchlists (agentos/handoffs/MARKET-OS-2026-08-22.md). Remaining before
      status done: PR #6257 proved that the existing authenticated owner-scoped
      path preserves explicit row identity and semantic fields but production
      rewrites created_at and updated_at. Under
      DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS, those
      two server-generated fields alone are excluded from A1A restoration
      equality; the semantic-v2 row fingerprint plus a separate authoritative
      ordered-id seal remain exact. The mandatory one-row semantic-v2 production
      probe passed on 2026-08-22 under ordinary authenticated owner RLS: the same
      explicit row id, owner, and semantic fields restored exactly without either
      timestamp input; only created_at and updated_at changed as expected; Macro
      and Terminal reproduced the pre-delete order; and the probe was permanently
      deleted. Immediate and delayed cleanup both returned the sealed 13-row
      semantic-v2, ordered-id, duplicate-multiplicity, and independent Watchlist
      seals exactly. Remaining before status done: return this receipt to Sol and
      obtain fresh action-time authority before deleting any canonical row, then
      execute the remaining authenticated matrix and exact cleanup. Do not execute
      Scene 9 or begin A1B without separate authority, and do not mark A1A done
      before Sol accepts it.
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
  - "DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS"
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
    ENTERED overlay; it is not a canonical Portfolio import.
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
  - Do not delete a canonical Portfolio row before Sol grants fresh action-time authority for the remaining authenticated A1A matrix.
artifacts:
  - research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_A1A_COMMISSIONING_2026-08-20.md
  - agentos/handoffs/MARKET-OS-2026-08-20.md
  - agentos/handoffs/MARKET-OS-2026-08-21.md
  - agentos/handoffs/MARKET-OS-2026-08-22.md
  - agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-blocker.md
  - agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-v2-probe.md
next_action: >
  A1A engineering is merged and live (#6136, 2633380f800a). PD1 Terminal repair
  #456 is also merged/live at 3f85efeb19bd, and its bounded authenticated
  one-sentinel production reproof passed with durable cleanup and unchanged
  Watchlists. PR #6257 then proved the ordinary authenticated owner path preserves
  explicit identity and semantic fields while rewriting only created_at and updated_at.
  DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS is now
  production-proven by one controlled same-id temporary-row restoration under
  ordinary authenticated owner RLS. The probe is durably absent, and immediate plus
  delayed Macro-Terminal reads reproduce the sealed 13-row semantic-v2 multiset,
  authoritative ordered-id sequence, duplicate multiplicity, and both independent
  Watchlist baselines exactly. Return the privacy-safe receipt in
  agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-v2-probe.md to Sol and obtain
  fresh action-time destructive authority before any canonical evacuation. After
  authority, recapture the action-time seals and execute the remaining authenticated
  A1A matrix with exact cleanup. Scene 9 remains excluded, and A1B plus every later
  dependent wave remain blocked on Sol accepting A1A in production.
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
