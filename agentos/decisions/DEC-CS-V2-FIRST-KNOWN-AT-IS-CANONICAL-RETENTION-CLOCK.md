---
key: CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK
question: >
  What exact clock does source-manifest first_known_at store, given the W1
  schema called it "first Git-publication time" while the collector assigns
  the verified-retention timestamp?
answer: >
  first_known_at is the verified-retention clock of the first observation of
  this evidence_id whose generation later became canonical. The value is the
  post-readback retention timestamp (collector retrieved_at / attempt
  retained_available_at), copied onto the published row. Git publication is
  the freeze event: once that value is on origin/main it never moves
  backward. It is not the Git commit timestamp. Parser/state availability
  remains a separate correction clock and is not back-dated onto first_known_at.
  Historical PIT records are not rewritten.
rationale: >
  Calling the retained timestamp a Git publication timestamp is a semantic
  contradiction. The collector never observes git commit time. The identity
  DEC's freeze rule is still right: a competing local timestamp cannot move a
  published boundary backward, and a withheld generation was not canonically
  known. W1A documents the stored value as retention-clock-frozen-at-publication
  rather than enlarging W1 into a full clock model.
alternatives:
  - option: Store the Git commit/push timestamp as first_known_at
    why_not: The collector cannot know that clock at write time; rewriting
      after push would mutate published PIT records.
  - option: Keep the schema wording "first Git-publication time" and leave
      the collector assigning retrieved_at
    why_not: The contradiction is what W1A was asked to remove.
  - option: Rebuild historical first_known_at values onto a new clock
    why_not: Forward-only. Do not rewrite historical PIT records.
evidence:
  - "contracts/capital_structure_source_manifest.schema.json first_known_at description"
  - "collectors/sec_capital_structure.py _manifest_record assigns retrieved_at then published_first_known_at"
  - "engine/capital_structure/source_identity.py published_first_known_at"
  - "DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES clocks table"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "contracts/capital_structure_source_manifest.schema.json"
  - "collectors/sec_capital_structure.py"
  - "engine/capital_structure/source_identity.py"
confidence: high
reversibility: easy
decided_by: cursor-grok-4.6
decided_at: 2026-08-19
review_by: 2026-08-25
---

W1A clock clarification. Does not replace DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES.
The identity preimage remains clock-free. This record names the stored
`first_known_at` value and the freeze rule without collapsing the four clocks.
