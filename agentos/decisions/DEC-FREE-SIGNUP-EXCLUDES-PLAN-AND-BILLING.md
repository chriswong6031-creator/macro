---
key: FREE-SIGNUP-EXCLUDES-PLAN-AND-BILLING
question: >
  Should Plan and Billing remain steps of the default account-creation wizard?
answer: >
  No. Signup mode contains Account and Preferences only. Plan and Billing exist solely in
  an explicit upgrade mode entered by deliberate user intent (opening Pricing) or by a
  contextual post-activation capability limit. Billing remains fully available at all
  times; it is never a step of free account creation.
rationale: >
  The current five-step Terminal wizard (Account, Preferences, Plan, Billing, Done)
  conflates registration with purchase: it makes the free account appear to require a
  billing decision, contradicts the value-first architecture (frozen law 3 and 4), and
  poisons the paid-intent signal — a paywall.encountered or plans.viewed emitted from a
  forced wizard step measures wizard completion, not upgrade intent. The capability
  ledger grades "current signup aligned with value-before-paid-ask" as BROKEN for
  exactly this reason.
alternatives:
  - option: Keep Plan/Billing steps but add a prominent skip
    why_not: >
      A skippable paid ask is still a paid ask during registration; it keeps the intent
      signal contaminated and keeps free signup measurably longer than two screens.
  - option: Remove billing surfaces from the product entirely until activation
    why_not: >
      Voluntary purchase intent is legitimate at any time (law 4 allows a user to open
      Pricing whenever they want); hiding Pricing would suppress real revenue and make
      deliberate upgrade intent unmeasurable.
evidence:
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §3 (capability ledger rows "Minimal two-screen free signup" NOT_BUILT / "signup aligned" BROKEN)
  - terminal/components/onboarding/OnboardingSheet.tsx (current five-step wizard implementation)
  - research/MASTERMIND_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md (upgrade-mode specification)
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - "WS:ACCOUNT-IDENTITY-HARDENING"
  - terminal/components/onboarding/**
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant to session claude/mmx-commercial-activation-03fe73 on
2026-09-04. Implementation is CA2 (Terminal journey parity) scope and must compose with
the settled Terminal carriers #444/#445/#435 — it does not start from this record.
