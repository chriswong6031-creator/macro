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
    status: done
    depends_on: [A1A]
    next_action: >
      ACCEPTED IN PRODUCTION by Sol on 2026-08-26 under
      DEC:MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION. PR #6335 exact semantic head
      2bf5d335e5adf742486e0c2aca50b0765617da2d landed as squash
      dd66f934e35a4629281656e854c6cc028dbd66d7; the assets were deployed; the
      anonymous production vertical passed with exact cleanup; and authenticated
      operation market-os-a1b-auth-accept-20260826-sol-001 passed the real
      paste->review->canonical portfolio_positions write->authoritative Macro reread
      ->Terminal conformance->exact cleanup journey on a designated disposable TEST
      identity. Closeout PR #6508 landed as fcbafecaa2636a5bba103d704bdc1c0d4d47d117.
      A1B is PROVEN_LIVE / DONE. Do not repeat either production acceptance vertical
      absent contradictory evidence or explicit recommission. The transient same-page
      Portfolio mode-tab count lag is NONBLOCKING follow-up #6510 and does not reopen
      A1B. A2-A6 are now dependency-eligible but remain unstarted and separately gated.
  - id: A2-A6
    title: Persistent sizing assumptions, CSV import, My Market rail, universal add, and Watchlist workspace
    status: todo
    depends_on: [A1B]
    next_action: >
      A1B is now PROVEN_LIVE / DONE, so this bundle is dependency-eligible. Sol must
      still refresh current Macro/Terminal truth and commission one independently useful
      vertical at a time; no broad My Market rewrite and no inference that eligibility
      equals start. The separate #6510 mode-tab count-lag repair may proceed independently
      if its fresh owner/path collision census remains clean.
  - id: B1A
    title: security_state.v1 golden AAPL product vertical (contract + compiler + producer + dossier Decision Spine)
    status: done
    depends_on: [A1A]
    next_action: >
      PROVEN_LIVE 2026-08-26. Sol accepted the held DRAFT and PR #6371 merged as
      squash 10b54a12828b14af0e99541a83c8d0638e64145e on 2026-08-25T16:56:39Z;
      the capability moves BUILT_NOT_PROVEN -> PROVEN_LIVE on the natural
      post-merge nightly, run 32908543584, with no lane re-run. That run's
      aggregate conclusion is `cancelled` and carries no B1A meaning — the
      owning jobs concluded success (collect 22:57:10Z->01:48:42Z; engine
      03:27:14Z->06:23:13Z, with rebuild stock-search libraries, publish heavy
      per-ticker stores to R2, and verify R2 data plane freshness all SUCCESS),
      and the only cancelled jobs were capital_structure and standout_audit_us,
      neither of which owns a B1A stage. Two live post-merge objects were
      verified, both self-consistent under a re-implementation of
      engine.security_state._content_sha256 with firing positive and stability
      controls: production /stockdata/AAPL.json (mtime 2026-08-26T02:22:47Z,
      126176 bytes, file sha256 3958897edf087e2c585acdb45e5e4ec0140e61acc287b408f3fe89caed3351bc,
      generated_at 2026-08-26T01:01:51Z inside the run window, content_sha256
      34e417cac98d24073f146bf8949ce33304e02ff8041f041aa5aec80b4894dc6c), and the
      canonical R2 data-plane object the dossier renders (Last-Modified
      2026-08-26T07:53:04Z, generated_at 2026-08-26T07:07:49Z, content_sha256
      abf598ea915c694c14118b2839ca718e6a0db69e4760a1d499c6fe153afe4c40).
      Attribution correction carried in the handoff: both objects were compiled
      by engine-render runs (32912667077 and 32938845408) — render.yml:1229 and
      engine-render.yml:833 also build_site and publish stockdata to R2, so
      daily.yml is not the only lane that delivers the blob; the nightly's own
      owning steps concluded SUCCESS on the same code path. Both
      carry identity PROVEN via owner_backed_chain.v1 (9 legs, 9 equalities, 0
      refusals, SEC:US-XNAS-AAPL / ISS:US-XNAS-AAPL / CIK 0000320193), real
      State and Change, the K1 recipe erp_5687f42d... with an EvidenceBlock ref
      and an evidence_foundation.recipe_compilation_receipt.v1 denominator,
      coverage PARTIAL with required legs 2/2 and dominant_degradation PARTIAL,
      failed_gates [] with strongest_unresolved_fact reaction_not_joined,
      catalyst ESTIMATED_WINDOW 2026-09-12->2026-10-10 authoritative false,
      personal_impact NO_USER_CONTEXT with zero private Portfolio/Watchlist
      tokens, and zero authority widening (no can_* true anywhere). Browser
      receipt: https://www.mastermind-x.com/stocks/AAPL.html served byte-identical
      to disk at sha256 8154964e0ed4b886eb3d59e075d094496f052aa8d785e239d57639e5d2a8338f,
      rendered by 0eb6fa5061ee at 2026-08-26T08:03:48Z, its Evidence & receipts
      drilldown printing the R2 object's own content fingerprint
      abf598ea915c... — six cards and the drilldown at 1440/820/390 with zero
      horizontal overflow. Control: MSFT holds no security_state on disk or on
      the live page, and only 2 of 3014 stockdata files carry the key (AAPL.json
      plus the AAPL row of index.json). Both Sol expansion gates survive into
      production and remain OPEN as repairs, not as closed items: universe
      expansion beyond ("AAPL",) is still BLOCKED under
      NO_GENERAL_NAMESPACE_RENDERER pending the owner-routed
      ListingAlias→ListingKey renderer + K1 vocabulary triple, and
      CIK_LEG_UNOWNED_ACCESS still names the reader-surface repair (expose
      issuer_cik on lib.dataos.identity readers). Receipts:
      agentos/handoffs/MARKET-OS-2026-08-26-b1a-proven-live.md. B1B and B2 need
      their own Sol commission and were not started.
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
    depends_on: [B1B-B6]
    next_action: Use compact Security State and Change Event projections; no fused rank.
  - id: D1-D9
    title: Portfolio Brief v3, Risk Packet, Holdings Map, visible risk sections, and scenarios
    status: todo
    depends_on: [A2-A6, B1B-B6]
    next_action: Preserve the existing risk core and one Portfolio composer; current-context mode precedes forecast mode.
  - id: E1-E3
    title: My Market Overview, personalized change feed, alerts, and digest
    status: todo
    depends_on: [C1-C6, D1-D9]
    next_action: Use deterministic research-priority precedence and privacy-safe user joins.
  - id: F0-F5
    title: Forecast Packet, prospective ledgers, shadow evaluation, and earned promotion
    status: todo
    depends_on: [B1B-B6, D1-D9]
    next_action: No live forward claim before point-in-time replay, calibration, forward shadow, and explicit authority promotion.
decisions:
  - "DEC:MARKET-OS-B1A-IDENTITY-GATE-OWNER-BACKED-CHAIN"
  - "DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE"
  - "DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT"
  - "DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS"
  - "DEC:MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED"
  - "DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION"
  - "DEC:MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION"
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
  - >-
    A1B production acceptance found a transient same-page presentation lag: after an
    authenticated import the authoritative Portfolio body/table and Terminal showed the
    new canonical count while the small Portfolio mode-tab badge still showed the old
    count until a fresh reread. This is NONBLOCKING issue #6510, not a persistence or
    authority failure. Repair only the existing render/update seam; never create a
    second count/state store or Watchlist-derived fallback.
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
  - Do not repeat either passed A1B production acceptance vertical absent contradictory production evidence or explicit recommission.
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
  - agentos/handoffs/MARKET-OS-2026-08-23-a1b-implementation.md
  - agentos/handoffs/MARKET-OS-2026-08-24-a1b-sol-review-repair.md
  - agentos/handoffs/MARKET-OS-2026-08-26-a1b-merged-deployed.md
  - agentos/handoffs/MARKET-OS-2026-08-26-a1b-sol-acceptance.md
  - agentos/handoffs/MARKET-OS-2026-08-20-a1a-merge-reconciliation.md
  - agentos/decisions/DEC-MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED.md
  - agentos/decisions/DEC-MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION.md
next_action: >
  PRIMARY PRODUCT: A1B is PROVEN_LIVE / DONE. Before any A2-A6 implementation,
  Sol refreshes current Macro/Terminal truth and commissions one independently useful
  vertical; eligibility is not execution. MAINTENANCE: #6510 may proceed independently
  as a bounded Portfolio mode-tab count synchronization repair if fresh collision
  census remains clean. PARALLEL ORGANIZATIONAL WORK: the separate Market Ontology
  parity/fanout carrier remains independent and must preserve its own current authority,
  claim, and proof gates; do not infer that this workstream sync lands or dispatches it.
---

## Current state

The product thesis and experience/intelligence architecture are frozen. The first six
planning turns established one product with three lenses: Market, Security, and My
Market; one shared Decision Spine; separate public intelligence and private exposure;
and explicit fact, deterministic-state, forecast, and decision authority.

A1A is accepted in production. The canonical Portfolio population/state authority seam
is the proven foundation for the import wave: authenticated users do not fail open
to local Portfolio state; Watchlists and temporary baskets do not enter Portfolio count,
market membership, weighting, book or risk; weighting assumptions and abstention are
explicit; and Macro/Terminal agreement has been demonstrated across the frozen live
matrix. A1B is also accepted in production under
DEC:MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION. Its anonymous and authenticated fast-start
journeys both passed with exact cleanup; authenticated canonical persistence moved the
designated TEST identity from 13 to 16 positions, Macro and Terminal agreed, Watchlists
were unchanged, and immediate plus delayed cleanup restored 13 positions with no
temporary residue. A1B is PROVEN_LIVE / DONE. The transient same-page Portfolio mode-tab
count lag is tracked separately as nonblocking issue #6510 and does not reopen A1B.
A2-A6 are dependency-eligible but remain unstarted pending separate bounded commissions.

## Program-parent note

This workstream cites `terminal-user-services` because the existing semantic registry
owns the shared user-state and alert product boundary. Market OS does not transfer
identity, news, company-event, signal, risk, or forecast authority into that program;
those domain owners remain independent and are composed through governed contracts.
A later semantic-map amendment may introduce a dedicated flagship product program, but
that registry change is not required to continue the bounded Market OS sequence.
