---
key: BILLING-UNKNOWN-AND-MALFORMED-SUCCESS-FAIL-CLOSED
question: >
  What may the product claim when payment or entitlement authority is unavailable,
  stale, or returns an incomplete/malformed success body?
answer: >
  Nothing beyond what the authority proves. Unknown entitlement renders as Unavailable,
  never as Free and never as paid. A same-owner last-good paid state may be displayed
  explicitly labeled stale but cannot newly unlock capability. A trial may be declared
  only with exact trialing status, non-empty subscription identity, and a valid
  authority-sourced trial end — no locally fabricated dates. A 2xx billing response
  whose body cannot be verified stays on the Billing surface with "completion could not
  be verified"; checkout.completed and trial.started events are prohibited in that
  state. All billing state and dates come only from payment authority; entitlement
  unlocks come only from verified entitlement authority.
rationale: >
  Money and access claims are user-trust boundaries: a fabricated trial date or an
  unlock from a stale cache is a lie the user can act on. HTTP success alone does not
  prove a subscription exists. Fail-closed keeps every failure recoverable (retry,
  portal) while fail-open manufactures unowed access or phantom purchases that no later
  reconciliation can honestly unwind. This is the cross-app law that Terminal D7
  (PR #435) and E-3/E-4 (PRs #444/#445) implement client-side.
alternatives:
  - option: Treat unknown entitlement as Free (fail-open to the cheapest tier)
    why_not: >
      Unverified != free: a paid user on a flaky connection would see their product
      degrade to Free and paid surfaces lock/flicker — punishing exactly the users who
      paid; unknown must render as unknown.
  - option: Trust client-observed checkout success and reconcile later via webhooks
    why_not: >
      Client-authoritative checkout events were explicitly rejected in the no-rebuild
      census; webhook reconciliation cannot un-tell a user they had a trial.
  - option: Cache entitlement indefinitely and unlock from cache
    why_not: >
      Stale display must never be gate authority; cancellation/past-due would keep
      unlocking until cache expiry.
evidence:
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §6.10 (authority matrix), §5.3 (malformed-2xx state law)
  - "Terminal PR #435 (claude/d5-billing-fail-closed, head d6eb13f24084cbf70f72580de04837f082f07182) — D7 fail-closed trial receipt"
  - "Terminal PRs #444/#445 — E-3 canonical entitlement store (unverified != free), E-4 freshness/invalidation"
  - research/MASTERMIND_SECURITY_AUTH_BILLING_AUDIT.md (webhook/portal spine this composes with)
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - "WS:ACCOUNT-IDENTITY-HARDENING"
  - terminal/components/onboarding/**
  - terminal/lib/useEntitlement.ts
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant to session claude/mmx-commercial-activation-03fe73 on
2026-09-04. Analytics may describe billing outcomes only from server authority events;
no client emitter may originate a billing success fact.
