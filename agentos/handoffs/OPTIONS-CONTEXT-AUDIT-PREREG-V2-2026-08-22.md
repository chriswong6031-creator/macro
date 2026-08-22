---
workstream: "WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2"
session: claude/w2c-v1-context-audit-decouple
model: local
ended_because: ci_handoff
prs: []
decisions:
  - "DEC:W2C-V1-CONTEXT-OWNER-DECOUPLED-FROM-OPTIONS-AUDIT"
discoveries:
  - "DSC:OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL"
mission: >
  Record the continuation workstream for Options Context Audit preregistration
  v2. Do not implement the redesign in the W2C recovery PR.
state_before: >
  Frozen v1 audit cannot lawfully admit more than 4,096 references. Production
  corpus is 3,897 episode rows and currently times out during O(N) construction
  before the hard refuse. August-13 adjudication forbids v1 stopgaps.
changed:
  - path: agentos/workstreams/WS-OPTIONS-CONTEXT-AUDIT-PREREG-V2.md
    what: Charter-only workstream; wave V2-PREREG-CHARTER remains todo.
verified:
  - claim: This session did not change engine/options_market_memory_context.py _MAX_REFERENCES.
    command: python3 -c "from engine.options_market_memory_context import _MAX_REFERENCES; assert _MAX_REFERENCES==4096"
    result: assertion passed
unverified:
  - claim: A future NYSE-bounded preregistration v2 can represent ~25k rows / 48 MiB.
    what_would_verify: Dedicated design packet and new preregistration bytes, not a v1 ceiling edit.
unresolved:
  - Preregistration v2 design and runtime are not started.
next_actions:
  - Write the v2 preregistration packet from OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md section 7.
  - Keep the independent audit unit loud until that successor exists.
do_not_redo:
  - Do not implement v2 inside a W2C timer-recovery PR.
  - Do not evict owners to fit 4,096 (DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION).
  - Do not swallow the audit exception or mark it healthy.
danger_areas:
  - The v1 engine is byte-pinned by sparse_selector_preregistration_receipt_v1.json.
  - Recoupling this owner into trusted context re-breaks W2C v1.
---

Charter only. Implementation is a later PR.
