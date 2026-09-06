---
key: COMMERCIAL-ACTIVATION-OWNS-JOURNEY-NOT-TRUTH-PLANES
question: >
  Should one new workstream own the visitor-to-retention commercial journey, and does
  owning the journey permit it to own authentication, billing, entitlements, Watchlists,
  Portfolio, analytics storage, email, or Market OS?
answer: >
  Create WS:COMMERCIAL-ACTIVATION as an integration and acceptance owner only. It owns
  journey transitions, transition contracts, instrumentation completeness, activation
  computation, contextual upgrade orchestration, cohort/retention learning, and
  end-to-end proof. Every underlying truth plane keeps its existing owner: Supabase auth,
  Stripe customer/payment authority, user_entitlements, Account Identity, canonical
  watchlists/watchlist_symbols and portfolio_positions, Market OS product truth, the
  existing /api/collect + analytics_events plane, app.mailer, and the commercial-path
  sentinel transport.
rationale: >
  The 2026-09-03 PROJECT_SOL census proved no current workstream spans
  visitor-to-retention: WS:ACCOUNT-IDENTITY-HARDENING owns identity, WS:MARKET-OS owns
  the product surface, WS:COMMERCIAL-PATH-ALERTING owns operational alarms, and the
  analytics sink has storage but no vocabulary owner. Forcing the journey into any of
  them stretches their charters; creating a new owner WITH truth-plane authority would
  duplicate systems that already exist and reopen settled ownership. A bounded
  integration owner closes the product gap without minting a second auth, billing,
  event, state, mail, or product plane.
alternatives:
  - option: Extend WS:MARKET-OS to own the commercial journey
    why_not: >
      Market OS owns user-facing product truth, not cross-company growth
      instrumentation, billing interpretation, or funnel acceptance; the stretch would
      make one workstream both truth plane and its own auditor.
  - option: Create a full-stack growth workstream that also owns analytics storage and signup
    why_not: >
      That mints a second analytics plane and a second identity/billing interpreter —
      exactly the duplication the no-rebuild census rejected; the existing planes are
      PROVEN_LIVE or BUILT_NOT_PROVEN, not absent.
  - option: Leave the journey ownerless and fix surfaces ad hoc
    why_not: >
      The owner gap is the proven root cause of the current incoherence (Plan/Billing in
      free signup, unjoinable event vocabularies, no activation definition); ad hoc
      fixes cannot produce one measured journey.
evidence:
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §2.2-§2.3 (owner census and absence proof)
  - agentos/workstreams/WS-ACCOUNT-IDENTITY-HARDENING.md, WS-MARKET-OS.md, WS-COMMERCIAL-PATH-ALERTING.md (adjacent owners, none spanning the journey)
  - "gh api repos/mastermindx-market-intelligence/macro/contents/agentos/workstreams — no commercial-activation record existed before this carrier (2026-09-04)"
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - "WS:MARKET-OS"
  - "WS:ACCOUNT-IDENTITY-HARDENING"
  - "WS:COMMERCIAL-PATH-ALERTING"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant of end-to-end authority to session
claude/mmx-commercial-activation-03fe73 on 2026-09-04, acting on PROJECT_SOL packet
MMX-SOL-COMMERCIAL-ACTIVATION-20260903-001. The workstream may compose and accept across
planes; it may never write around an authority. If a journey requirement seems to need a
truth-plane change, the change is commissioned to that plane's owner, not absorbed here.
