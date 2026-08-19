---
key: CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES
question: >
  How should V2 evidence identity become lawful under
  DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY without rewriting history, without
  hashing parser interpretation, and without colliding with
  validate_manifest_ledger's one-id-one-body detector?
answer: >
  Forward-only dual-read. Do not rewrite historical manifest_id strings.
  Do not weaken manifest_id_for — it keeps hashing the full body minus
  manifest_id and remains the interpretation-revision receipt. Mint a derived
  evidence_id over immutable source occurrence plus retained bytes only:
  key_format, source_system, submission_accession, occurrence
  (submission, or parent_content_sha256 + byte_start + byte_end), and
  content_sha256. Exclude retrieval clocks, file-number interpretation,
  ticker/aliases, parser state/version, normalized issuer mapping, document
  role, document_version, storage namespace, and source_id. Interpretation
  correction appends a new manifest revision of the same evidence_id.
  Distinct source occurrences cannot collapse. Canonical first_known_at
  freezes at first Git publication of that evidence_id and never moves
  backward because a delayed observation carried an earlier local timestamp.
  Reuse retrieval_attempts as the observation plane; do not mint a second
  observation artifact. Drop the unconditional durable
  "1 evidence + 2 observations" W1 gate.
supersedes:
  - DEC:CS-V2-IDENTITY-DUAL-READ
rationale: >
  Hashing a declared subset of the manifest body while leaving clocks and
  parser fields on the same row produces the same manifest_id with two
  bodies, which validate_manifest_ledger already hard-aborts as divergent
  global manifest_id. The proposed W0 subset still contained interpretation
  (file_number, document_role, document_version). DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY
  says identity hashes are not weakened so that inputs stop moving; a new
  derived evidence_id is the lawful dual-read. Same bytes in two accessions
  must stay distinct (live POS AM digest shared across six accessions).
  Same accession two SGML occurrences must stay distinct. Same occurrence
  two clocks must not remint. Once a PIT boundary is on origin/main, a
  competing local timestamp cannot rewrite it; withheld generations were
  not canonically known.
alternatives:
  - option: Hash a content-binding subset as v2 manifest_id (superseded DEC)
    why_not: Same id plus different remaining body trips the ledger detector;
      the listed subset still included parser interpretation.
  - option: Hash only content_sha256
    why_not: Collapses distinct filings that reuse a prospectus body
      (measured 11 rows / 3 digest groups on the 1972-row freeze ledger).
  - option: Include file_number, ticker, issuer mapping, or document_role
    why_not: Parser improvement remints evidence. Role is a policy function.
  - option: New observation JSONL beside retrieval_attempts
    why_not: Existing attempt rows already record outcome, digest, and
      pre-fetch clock. Additive fields close the child-document and
      post-readback-clock gaps without a second lifecycle plane.
  - option: Keep "concurrent merge = 1 evidence + 2 durable observations"
    why_not: Durable 1+2 over overlapping CS jobs publishes a mixed
      generation. Whole-generation withhold plus idempotent evidence_id
      is the fence law.
evidence:
  - "engine/capital_structure/source_identity.py:136-141 manifest_id_for hashes body minus manifest_id"
  - "engine/capital_structure/source_identity.py:154-170 validate_manifest_ledger divergent global manifest_id"
  - "contracts/capital_structure_source_manifest.schema.json:72-76 retrieval clocks required"
  - "collectors/sec_capital_structure.py:169-173 _ATTEMPT_COLUMNS"
  - "collectors/sec_capital_structure.py:424-462 file_number observation encodings"
  - "collectors/sec_capital_structure.py:553-580 document_role is policy"
  - "DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY"
  - "Sol AMEND review of PR #5901 2026-08-18"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md §8"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "engine/capital_structure/source_identity.py"
  - "collectors/sec_capital_structure.py"
  - "data/capital_structure/source_manifest.jsonl"
  - "data/capital_structure/retrieval_attempts.parquet"
confidence: medium
reversibility: costly
decided_by: cursor-grok-4.6
decided_at: 2026-08-18
review_by: 2026-08-25
---

Architecture proposal for Sol/Chairman. Proposed by the Cursor Grok 4.6 W0
session. Not a Fable decision. Do not implement in this PR.

## Dual-read

- v1 rows keep validating under current `manifest_id_for`.
- `evidence_id` is computable from a v1 or v2 row's own bytes (legacy child
  rows without parent offsets use `legacy:{source_id}` until an authorized
  R2 re-derive, not W1 rewrite).
- No historical `manifest_id` string is rewritten.

## `evidence_id` preimage

`evidence:cs:` + sha256(canonical_json({key_format, source_system,
submission_accession, occurrence, content_sha256})).

Occurrence is `"submission"` for the complete submission, else
`{parent_content_sha256, byte_start, byte_end}` from the frozen
`<DOCUMENT>...</DOCUMENT>` inner-span rule. Changing that scanner requires
`key_format: 2`.

Bytes stay in the key so in-place SEC replacement mints a new evidence
identity linked by `correction_of`, never a silent rewrite.

## Clocks (four distinct things)

| Concept | Field | Rule |
|---|---|---|
| Evidence identity | `evidence_id` | No clock in the preimage |
| Per-attempt retrieval time | `retrieval_attempts.attempted_at` | Pre-fetch; never an availability claim |
| Verified-retention availability | `retained_available_at` on a successful attempt | Post-readback; per observation |
| Canonical first-known time | `first_known_at(evidence_id)` | Frozen at first Git publication of that evidence; never moves backward |

A delayed/competing observation with an earlier local timestamp is not a
reason to rewrite a published PIT boundary. A withheld generation was not
canonically known.

## Observation plane

Start from `_ATTEMPT_COLUMNS`. W1 may add `observed_evidence_ids` and
`retained_available_at` so successful re-observation of child documents is
representable. Do not create a second observation artifact unless those
additions prove insufficient.

## Hostile fixtures W1 must pin

1. Same SEC document, two clocks → same `evidence_id`; first_known frozen.
2. Same bytes, two accessions → distinct `evidence_id`.
3. Same bytes, two SGML sequences in one accession → distinct `evidence_id`.
4. Same occurrence, corrected file-number/issuer/parser → same `evidence_id`,
   new `manifest_id` revision.
5. Complete submission plus child documents → distinct ids; children carry
   parent coordinates.
6. Legacy v1 manifests still validate; `evidence_id` is a read-side projection.
7. Multiple valid v1 ids for the same occurrence collapse to one `evidence_id`
   on read; do not delete the v1 rows.

## W1 publication gate (replaces 1+2 durable observations)

In-process keep-first may still prove one `evidence_id` from two mints.
Durable overlapping CS jobs must leave **one coherent generation** on main
(`DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE`): no duplicate economic
event, no stale generation clobber. Mandatory proof is not two durable
attempt rows if publishing them would mix generations.
