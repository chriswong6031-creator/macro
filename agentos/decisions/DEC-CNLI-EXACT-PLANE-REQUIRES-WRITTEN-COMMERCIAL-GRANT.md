---
key: CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT
question: >
  Which authorization mechanism governs CN-Limit DEP-EXACT — the full-A
  authority-grade exact plane (daily × daily_basic × stk_limit × suspend_d ×
  stock_st bulk retention and its downstream eligibility substrate): the
  china_tushare_spine written-grant receipt gate
  (cn_tushare_written_authorization.v1 bound to a code-reviewed trust root),
  or the 2026-08-09 ruling-3 plain-provenance operator wiring order
  (research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md) that the shipped
  addon/minutes lanes use?
answer: >
  The written vendor/institutional grant + cryptographically pinned receipt
  path is BINDING for the exact plane. The ruling-3 plain-provenance
  alternative is REJECTED for full-A authority-grade collection. Closure of
  DEP-EXACT therefore requires: a private written grant from the vendor (or
  the granting institution), an authorization receipt conforming to
  cn_tushare_written_authorization.v1 whose grant_document_sha256 verifies
  against the stored grant, an independent trust-allowlist file, and a
  reviewed code change adding that allowlist's exact SHA-256 to
  CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256. Only after that:
  licensed live canary (plan, then bounded execute), canary review, a
  separately reviewed BULK_HISTORICAL_BACKFILL_READY flip, the range-shard
  campaign, and the sanitized completeness manifest.
rationale: >
  Current Tushare terms (doc 405, DSC:TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT)
  grant ordinary service for personal/non-commercial use, and
  company/institution use is separately classified. The 2026-08-09 operator
  wiring ruling is an access/wiring instruction — it says which token wiring
  to use, not what the vendor has licensed — so it cannot stand in for a
  vendor commercial grant on a plane whose rows will feed authority-grade,
  potentially commercial derived outputs. The later full-A spine contract's
  authorization gate was designed for exactly this case and stands as
  designed. IMPORTANT: this decision record does NOT itself satisfy the
  runtime authorization gate. The gate reads bytes, not rulings — an absent
  receipt, an absent allowlist, or an empty
  CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256 frozenset still refuses
  every network and store write, and both constants remain in their
  fail-closed foundation state after this DEC lands. A red execute run on the
  campaign lane before the grant exists is the gate working.
alternatives:
  - option: Ruling-3 plain-provenance operator order (the addon/minutes mechanism)
    why_not: >
      It is an access/wiring instruction issued by the operator, not a vendor
      commercial grant. Extending it to bulk multi-year retention and
      commercial derived outputs would launder an authority question into a
      wiring precedent and contradict the vendor's own personal/non-commercial
      service classification.
  - option: Session-side gate alignment (edit the frozenset / READY flag to match a claimed authorization)
    why_not: >
      Self-excuse by construction — the fleet shares one token, so any
      session-mintable marker proves nothing. The trust root is addable only
      via reviewed code change binding to real grant bytes.
  - option: Operator terms-accepted switch (a config flag or receipt without a verifiable grant document)
    why_not: >
      Explicitly rejected in load_authorization_grant's design: the receipt
      must bind to an independently stored written grant whose SHA-256
      matches; a switch without bytes is a fabricated receipt.
evidence:
  - "collectors/china_tushare_spine.py:102-113 (empty code-reviewed trust root; BULK_HISTORICAL_BACKFILL_READY=False), :136-143 (required/recorded scope booleans), :662-760 (load_authorization_grant fail-closed validation)"
  - "agentos/discoveries/DSC-TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT.md (doc 405 click-through is personal/non-commercial/view-only)"
  - "research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md §3 (closure priced at ¥0 cash + one 5-question vendor letter)"
  - "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md (ruling-3 — the rejected alternative's text)"
  - "agentos/handoffs/CN-LIMIT-ALPHA-2026-08-21.md (DEP-EXACT authority census; PR #6171 merged as be66a9cc3d435eccc4e22abb50f39228e3d8f7d2)"
  - "research/cn_limit/TUSHARE_VENDOR_LETTER_PACKET_2026-08-21.md (the executable vendor-letter + post-grant procedure this DEC commissions)"
affects:
  - WS:CN-LIMIT-ALPHA
  - collectors/china_tushare_spine.py
  - .github/workflows/tushare-spine-backfill.yml
  - research/cn_limit/TUSHARE_VENDOR_LETTER_PACKET_2026-08-21.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-21
---

## Authority consequence

This DEC selects the mechanism; it grants no runtime authority. Concretely:

- `CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256` stays `frozenset()` and
  `BULK_HISTORICAL_BACKFILL_READY` stays `False` until each is changed by its
  own separately reviewed code change, each gated on real evidence (grant
  bytes for the first; canary/throughput receipts for the second).
- No TuShare call, campaign dispatch, receipt minting, or DEP-ID-ELIG/I1A
  work is authorized by this record.
- DEP-EXACT's workstream state moves to `WAITING_FOR_WRITTEN_VENDOR_GRANT`:
  the single blocking artifact is the vendor's written answer to the
  five-question letter in
  `research/cn_limit/TUSHARE_VENDOR_LETTER_PACKET_2026-08-21.md`, which also
  pre-stages (without activating) the full post-grant procedure:
  private written grant → authorization receipt → independent allowlist →
  reviewed trust-root pin → licensed canary (plan → bounded execute) →
  canary review → separately reviewed READY flip → range campaign →
  completeness manifest.
- `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` is untouched by this decision.
