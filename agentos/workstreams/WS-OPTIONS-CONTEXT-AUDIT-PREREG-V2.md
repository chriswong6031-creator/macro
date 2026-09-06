---
key: OPTIONS-CONTEXT-AUDIT-PREREG-V2
title: Options Context Audit preregistration v2
objective: >
  Replace the frozen v1 Options Context Audit with a new preregistration whose
  future NYSE boundary can represent the live owner corpus (~25,000 rows /
  48 MiB previously reviewed). Keep the v1 4,096 refusal honest until that
  successor exists. Do not window, evict, or truncate episode owners.
status: active
program: options-intelligence
repos: [macro]
owner: coo-fable
class: adjudication
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - engine/options_market_memory_context.py
  - engine/options_market_memory_receipt_store.py
  - scripts/audit_options_market_memory_context.py
  - app/deploy/macro-market-memory-options-context-audit.service
  - app/deploy/macro-market-memory-options-context-audit.timer
waves:
  - id: V2-PREREG-CHARTER
    title: Charter the successor preregistration; do not implement it here
    status: todo
    next_action: >
      Open a dedicated preregistration-v2 design packet from
      research/options_estate/OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md
      section 7. Size the new bound to the previously reviewed ~25k-row /
      48 MiB owner capacity with a future NYSE boundary. Do not implement that
      redesign inside a W2C recovery PR.
next_action: >
  Execute the charter-only V2-PREREG-CHARTER child first. Freeze honest full-corpus
  capacity, algorithmic/resource/refusal bounds, clocks/nulls/corrections and an
  anti-vacuity implementation acceptance packet. Do not implement v2 in the charter
  child. Implementation requires a separately keyed later child after Sol accepts the
  preregistration. Do not widen `_MAX_REFERENCES`, edit v1 in place, or recouple this
  owner into trusted-context publication.
decisions:
  - "DEC:W2C-V1-CONTEXT-OWNER-DECOUPLED-FROM-OPTIONS-AUDIT"
discoveries:
  - "DSC:OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL"
do_not_redo:
  - Do not implement preregistration v2 inside a W2C timer-recovery PR.
  - Do not raise TimeoutStartSec or CPUQuota as a substitute for v2.
  - Do not widen `_MAX_REFERENCES` or the pinned receipt-store reference ceiling.
  - Do not window, evict, rotate, or truncate episode owners (DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION).
  - Do not swallow the audit exception or mark the audit healthy.
  - Do not create a shadow validator with a larger cap.
landmines:
  - The v1 engine is byte-pinned by sparse_selector_preregistration_receipt_v1.json.
  - Production construction is O(N) over the complete owner corpus and currently dies on TimeoutStartSec=180 / CPUQuota=50% before the deterministic 4,096 refusal.
  - Trusted Market Memory context is a different owner. Recoupling this audit into macro-market-memory-context.service re-breaks W2C v1 timer arming.
artifacts:
  - research/options_estate/OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md
  - research/options_estate/sparse_selector_preregistration_receipt_v1.json
---

Lawful repair is a new preregistration v2, not a timeout or ceiling patch on v1.
