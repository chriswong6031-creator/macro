---
key: COMMERCIAL-ACTIVATION
title: Commercial Front Door, Activation, and Retention
objective: >
  Make the visitor-to-retention journey coherent, measurable, and trustworthy: genuine
  intelligence before registration; a personal act before a minimal free account;
  canonical state preserved through signup; measurable free and paid activation;
  contextual paid asks after value; authority-sourced billing; and a useful personalized
  return. Done means a real anonymous visitor can experience intelligence, save a
  personally meaningful state through free account creation, return to it, activate,
  upgrade at a measured value boundary, and retain — with every stage machine-readable
  from the existing analytics plane.
status: active
program: terminal-user-services
p0: MONETIZATION_AND_ONBOARDING
repos: [macro, terminal]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/commercial_activation/**
  - scripts/activation_funnel_report.py
  - tests/test_commercial_activation_event_spine.py
  - tests/test_activation_funnel_report.py
decisions:
  - "DEC:COMMERCIAL-ACTIVATION-OWNS-JOURNEY-NOT-TRUTH-PLANES"
  - "DEC:VALUE-AND-PERSONAL-ACT-PRECEDE-REGISTRATION"
  - "DEC:FREE-SIGNUP-EXCLUDES-PLAN-AND-BILLING"
  - "DEC:ANON-WATCHLIST-FOLDS-INTO-CANONICAL-WATCHLIST"
  - "DEC:ANALYTICS-EID-USES-EXISTING-EVENT-PRIMARY-KEY"
  - "DEC:BILLING-UNKNOWN-AND-MALFORMED-SUCCESS-FAIL-CLOSED"
  - "DEC:TERMINAL-D7-COMPOSES-AFTER-E3-E4-SAME-CARRIER"
discoveries:
  - "DSC:COMMERCIAL-ACTIVATION-OWNER-GAP-AND-COLLISION-CENSUS-20260903"
artifacts:
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md
  - research/commercial_activation/CLAUDE_ORCHESTRATOR_HANDOFF_V1_CA1A_EVENT_SPINE_20260903.md
landmines:
  - >
    This workstream owns NO truth plane: auth, Stripe/billing, user_entitlements,
    Watchlist/Portfolio stores, Market OS product truth, analytics storage/transport,
    mail, and sentinel transport all keep their existing owners. A journey requirement
    that needs a truth-plane change is commissioned to that plane's owner.
  - >
    Analytics can describe behavior but can never grant product, payment, market, or
    trade authority; commercial telemetry never ranks or originates trades.
  - >
    The Terminal required check "Terminal typecheck + tests" is red repo-wide (all PR
    branches, disjoint diffs); do not attribute it to #435/#444/#445 and do not weaken
    tests to pass it — it is owned by its own CI-health repair carrier.
waves:
  - id: R0
    title: Owner charter, architecture decisions, collision census, CA1A handoff (records only)
    status: in_progress
    next_action: Merge this records-only carrier; no runtime work starts from it.
  - id: CA1A
    title: Activation Event Spine V1 — registry-driven acceptance, eid idempotency, real producers, deterministic funnel report
    status: todo
    depends_on: [R0]
    next_action: >
      Execute on one Macro carrier (branch sol/commercial-activation-ca1a-event-spine-20260903)
      per research/commercial_activation/CLAUDE_ORCHESTRATOR_HANDOFF_V1_CA1A_EVENT_SPINE_20260903.md;
      at START repin macro main, rerun the owned-path collision census, and compose with
      the merged #6815 flowobs semantics. Production canary per §16 before any
      completion claim.
  - id: CA1B
    title: Anonymous Insight → Canonical Save — third-symbol invitation, minimal signup, owner-verified fold, My Market return
    status: todo
    depends_on: [CA1A]
    next_action: Commission only after the CA1A production canary passes; separate carrier.
  - id: CA2
    title: Terminal journey parity — minimal signup and canonical save on Terminal
    status: todo
    depends_on: [CA1B]
    next_action: >
      Requires settled Terminal carriers #444 → #445 → #435 (see
      DEC:TERMINAL-D7-COMPOSES-AFTER-E3-E4-SAME-CARRIER) and the repo-wide e2e CI repair.
  - id: CA3
    title: Free-activation projector and weekly CEO commercial report from real source events
    status: todo
    depends_on: [CA1B]
    next_action: Includes the preregistered 30-day cohort review of the third-symbol hypothesis.
  - id: CA4
    title: Contextual upgrade moments and paid-activation projector
    status: todo
    depends_on: [CA3]
    next_action: First two moments — advanced evidence/depth ceiling and AI quota ceiling.
  - id: CA5
    title: Since-you-were-last-here retention loop from canonical source changes
    status: todo
    depends_on: [CA3]
    next_action: Honest no-change/stale/partial/unavailable states are in scope from day one.
  - id: CA6
    title: Pricing and paywall experiments under preregistered statistical gates
    status: todo
    depends_on: [CA4, CA5]
    next_action: No experiment ships without a preregistered promotion gate.
next_action: >
  Merge the R0 records carrier, then execute CA1A on branch
  sol/commercial-activation-ca1a-event-spine-20260903 with a fresh START repin and
  collision census.
---

# WS:COMMERCIAL-ACTIVATION — Commercial Front Door, Activation, and Retention

The frozen product architecture (five laws), the complete journey/state vocabulary, the
data/identity/time/null/correction/provenance/authority contracts, the no-rebuild
boundaries, and the 30/60/90 capability sequence live in the frozen return:
`research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md`.

The five frozen laws, for fast orientation:

1. Value precedes registration.
2. A personal act precedes registration (v1 act: anonymous Watchlist save; third
   distinct symbol is the strongest initial prompt moment — a preregistered hypothesis).
3. Registration is free and minimal (Account + Preferences only; no Plan/Billing).
4. Paid asks follow activation or deliberate purchase intent.
5. Authority never leaks upward (billing from payment authority; unlocks from verified
   entitlement authority; analytics describes, never grants).

Authorization lineage: PROJECT_SOL packet MMX-SOL-COMMERCIAL-ACTIVATION-20260903-001
(status ARCHITECTURE_FROZEN_EXECUTION_NOT_ADMITTED) was ratified and granted end-to-end
execution authority by the Chairman directly to session
claude/mmx-commercial-activation-03fe73 on 2026-09-04. Executive OS runtime was
fixture/degraded at grant time, so runtime Job admission was substituted by the direct
Chairman grant; that substitution is recorded here and in the R0 handoff rather than
implied to have been an Executive Job.
