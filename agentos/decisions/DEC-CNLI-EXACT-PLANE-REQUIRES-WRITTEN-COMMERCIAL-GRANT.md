---
key: CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT
question: >
  Does CN-Limit DEP-EXACT require a coding-visible written TuShare commercial grant,
  authorization receipt, trust allowlist, grant-document SHA, or equivalent runtime
  license-document proof?
answer: >
  NO. NULL / SUPERSEDED by Chairman decision
  DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE on 2026-08-21.
  The former written-grant + cryptographically pinned receipt requirement was a
  CEO/Codex-generated architecture error and has no authority. TuShare compliance has
  already been verified internally and privately. Coding sessions and runtime code must
  not request, upload, inspect, persist, hash, quote, or gate on the private agreement or
  supporting evidence. The confidential agreement is outside the coding estate because
  its details cannot be disclosed to coding sessions or third parties under NDA/privacy
  constraints.
rationale: >
  Supersession preserves a resolvable historical decision key while making the old answer
  impossible to treat as active authority. Engineering owns technical correctness,
  access/quota observations, canary, completeness, PIT and backfill readiness; it does not
  own re-verification of private licensing evidence already resolved by the Chairman.
alternatives:
  - option: Restore the former written-grant/allowlist gate
    why_not: >
      Forbidden unless a later explicit Chairman/compliance-owner decision supersedes
      DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE.
evidence:
  - "Chairman operator override 2026-08-21."
affects:
  - WS:CN-LIMIT-ALPHA
  - collectors/china_tushare_spine.py
confidence: high
reversibility: one_way
superseded_by: DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE
decided_by: chairman-operator
decided_at: 2026-08-21
---

## Historical-status tombstone

The pre-override content of this file is historical only. It must not be used to block
TuShare collection, DEP-EXACT, a canary, a range campaign, derived research, or product
work; it must not be quoted to request private licensing documents from the Chairman.
Current authority is `DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`.
