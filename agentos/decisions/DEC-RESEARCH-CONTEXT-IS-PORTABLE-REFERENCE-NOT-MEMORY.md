---
key: RESEARCH-CONTEXT-IS-PORTABLE-REFERENCE-NOT-MEMORY
question: >
  How should Mastermind preserve an investor's active investigation across Search,
  company/event workspaces, charts and Ask Mastermind without creating another memory,
  evidence, identity or user-state control plane?
answer: >
  Portable Research Context is a bounded reference bundle over canonical owner objects.
  It may carry canonical issuer/security/event references, query/filter/result references,
  pinned evidence receipts, an explicit comparison-set reference, historical cutoff and
  selected analytical-lens references. It does not copy source bodies or become truth.
  The first implementation should be ephemeral/session/navigation state. Any later saved
  persistence must reuse or reconcile the existing terminal-user-services user-state
  authority; this decision authorizes no research_context database.
rationale: >
  Terminal already proves useful workspace-local selection: company/event context,
  receipt selection and event-change reset. Fiscal reconnaissance showed that independent
  workspaces often discard analytical context even while company sibling tabs preserve it.
  The useful delta is therefore controlled reference continuity, not another memory
  system. References also preserve entitlement and correction boundaries: the destination
  re-resolves identity, source availability, rights and corrections instead of inheriting
  unrestricted copied content.
alternatives:
  - option: Persist a universal research_workspace object immediately
    why_not: No owner census has proven a new store is needed; Market OS already sits under an existing user-state boundary.
  - option: Serialize the whole UI state between routes
    why_not: Scroll, zoom, accordion and other local presentation state create an unbounded brittle contract and can carry stale selections.
  - option: Let Neural Web or Brain memory own navigation context
    why_not: Research navigation state is not machine memory/truth, and doing so creates a second user-state semantic role inside Neural Web.
  - option: Carry source text/bodies inside the context bundle
    why_not: It duplicates evidence, breaks correction/rights boundaries and can leak content across entitlements.
evidence:
  - "research/market_os/FISCAL_RESEARCH_OS_ARCHITECTURE_DELTA_2026-08-22.md"
  - "mastermind-terminal/docs/COMPANY_INTELLIGENCE_WORKSPACE.md at observed master 449439c690e93ba968185499af4041c2f512b659"
  - "Mastermind Fiscal recon PR #121 route_and_context_map.md at 758741b9b89d9ee641729a81af691ad608de4720"
  - "WS:MARKET-OS program-parent note: terminal-user-services owns shared user-state/alert product boundary while domain truth remains independent"
affects:
  - WS:MARKET-OS
  - terminal-user-services
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-22
---

The cross-surface identity is canonical-reference first, never ticker-string first. An ambiguous
or mismatched listing is a refusal, not a silent convenience mapping.

Pinned evidence keeps the original reference and selected cutoff when later corrected. A destination
surface re-checks entitlement and current correction state. Unsupported context fields are explicitly
dropped/refused rather than silently changing the meaning of the remaining investigation.
