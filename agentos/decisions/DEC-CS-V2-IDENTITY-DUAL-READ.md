---
key: CS-V2-IDENTITY-DUAL-READ
question: >
  `manifest_id_for` hashes the full source-manifest body, including required
  retrieval clocks, so unchanged SEC bytes can mint a new manifest_id on
  re-retention. Historical IDs already sit under PIT receipts. How should V2
  become lawful under DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY without rewriting
  history or using git merge=union?
answer: >
  Forward-only dual-read. v1 rows keep validating under the current full-body
  hash. v2 hashes a declared content-binding subset and excludes retrieval and
  run clocks. first_seen_at freezes on first retention; later retrieves append
  an observation. Same content_sha256 + accession + document role is one
  evidence identity (keep-first). Do not rewrite historical manifest_id strings.
  Do not merge=union the JSONL. Content-aware merge lives in merge_manifest_ledgers
  and in CS-owned push conflict handling for this file only.
rationale: >
  Evidence bytes are already content-addressed and stable
  (storage.object_key = capital_structure/sec/sha256/{aa}/{sha256}). The DNR
  violation is the retention identity, not the object store. Sequential remints
  are masked by _eligible_complete_accessions; concurrent collect (measured
  possible; et_gate mutex rejected) is not. event_id hashes manifest_ids, so
  remints contaminate the spine. Govrev already declined merge=union on a
  prefix-hash JSONL for the same reason. Rewriting IDs would invalidate PIT
  receipts. Dual-read is the only compatibility path that is both lawful and
  non-destructive. Live-tail must not scale retrieval until this lands.
alternatives:
  - option: Rewrite all historical manifest_ids to the new hash
    why_not: Breaks existing PIT receipts, BioCatalyst read_ids, and any
      downstream fact_id that committed to the old string.
  - option: Leave identity unchanged and start live-tail first
    why_not: Live-tail increases re-observation and races; artifact count would
      measure cadence. The audit selected identity as the prerequisite.
  - option: Add merge=union on source_manifest.jsonl
    why_not: Union on a hash-bound ledger duplicates rows and breaks
      prefix_sha256 / source_ledger_receipt the same class as
      DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS.
  - option: Hash only content_sha256 and drop manifests
    why_not: One accession has many documents; role and byte_length are
      content-binding. The manifest row is the receipt, not the bytes.
evidence:
  - "engine/capital_structure/source_identity.py:136-141 manifest_id_for hashes body minus manifest_id"
  - "contracts/capital_structure_source_manifest.schema.json:72-78 retrieval.retrieved_at and first_seen_at required"
  - "collectors/sec_capital_structure.py:1728-1737 both clocks set to retained_at wall clock"
  - "collectors/sec_capital_structure.py:1287-1313 _eligible_complete_accessions queue skip"
  - "engine/capital_structure/event_spine.py:469-471 event_id hashes body including manifest_ids"
  - "DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY"
  - "DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md §8"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "engine/capital_structure/source_identity.py"
  - "collectors/sec_capital_structure.py"
  - "data/capital_structure/source_manifest.jsonl"
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-08-25
---

Architecture ruling only. Wave 1 implements it after Sol/Chairman accept W0.
Do not patch identity in the masterplan PR.
