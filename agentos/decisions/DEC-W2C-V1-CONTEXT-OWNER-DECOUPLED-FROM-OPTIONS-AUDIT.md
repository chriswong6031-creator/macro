---
key: W2C-V1-CONTEXT-OWNER-DECOUPLED-FROM-OPTIONS-AUDIT
question: >
  May W2C v1 owner replay authenticate trusted Market Memory context while the
  Options Context Audit is independently failing its frozen 4,096-reference v1
  contract, and what service boundary makes that true without masking the audit?
answer: >
  Yes. W2C v1 consumes the trusted macro-regime profile, not the Options audit
  receipt. Production `macro-market-memory-context.service` now publishes only
  trusted context. The Options Context Audit runs as
  `macro-market-memory-options-context-audit.service` after trusted context is
  available, without Requires/Wants/PartOf, and its failure stays loud. Do not
  implement Options Audit preregistration v2 in this recovery.
rationale: >
  Canonical August-13 adjudication predicted the 4,096 wall around August 20–21
  and ruled there is no lawful v1 stopgap. Production 2026-08-22 measured 3,897
  episode rows and spent the 90s CPU budget (180s wall × 50% quota) constructing
  the complete corpus, so the coupled oneshot died before W2C could reach
  w2c_reconcile_timer(). Trusted projection itself completes; the remaining CPU
  is the audit. Registration
  mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3
  names trusted_profile market_memory.trusted.macro_regime_canary.v1 and does
  not name the Options audit. scripts/audit_options_market_memory_context.py
  was already the durable CLI. Splitting service ownership to match artifact
  ownership restores v1 timer arming without a second trusted store.
alternatives:
  - option: Raise TimeoutStartSec or CPUQuota on the coupled context oneshot
    why_not: >
      Sol rejected a larger timeout. Even if O(N) work finished, v1 still cannot
      admit more than 4,096 references.
  - option: Widen `_MAX_REFERENCES` or the pinned receipt-store ceiling
    why_not: >
      The ceiling is byte-pinned by the sparse-selector preregistration. Lifting
      it is a preregistration act, not a buffer change.
  - option: Window, evict, or truncate episode owners
    why_not: DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION.
  - option: try/except around publish_live_audit inside the context oneshot
    why_not: >
      That hides the audit behind the trusted owner and can relabel an honest
      audit failure as trusted success, or the reverse.
  - option: Manually enable --now the v1 experience timer
    why_not: >
      That bypasses owner replay. Sol forbade manufacturing an opportunity or
      starting v1/v2 experience oneshots by hand.
evidence:
  - "VPS 2026-08-22T21:03Z: episodes.jsonl 3897 rows / 6064140 bytes; outcomes_h60.jsonl 3252 rows / 6580547 bytes"
  - "context oneshot 1608454 started 21:06:23Z, SIGTERM 21:09:23Z, 90.134s CPU, trusted HEAD unchanged"
  - "config/market_memory_spy_experience_registration.v1.json trusted_profile=market_memory.trusted.macro_regime_canary.v1"
  - "scripts/accrue_market_memory_spy_experience.py has no options_context / audit_options hits"
  - "research/options_estate/OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md"
affects:
  - "WS:MARKET-MEMORY-W2C"
  - "WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2"
  - app/deploy/macro-market-memory-context.service
  - app/deploy/macro-market-memory-options-context-audit.service
  - scripts/project_market_memory_context.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
---

Trusted context and the Options Context Audit are different owners. Keep them that way.
