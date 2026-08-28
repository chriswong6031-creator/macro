---
key: CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE
question: >
  Given Git remains the compiled-generation selector, how should overlapping
  Capital Structure jobs publish so origin/main never drops source-ledger
  evidence, without file-level merge, merge=union, or a second publication
  plane?
answer: >
  Keep Git as the canonical compiled-generation selector for
  data/capital_structure/** and site/capital-structure-data. R2 remains the
  evidence store. No new publication control plane. Do not content-aware-merge
  source_manifest.jsonl at push time — a manifest merged after compile would
  no longer match that run's events, terms, projection, or health. W1 extends
  the existing append-only push-fence (DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE)
  with a capital-structure family. On proof that origin/main contains
  source-ledger evidence this candidate generation would drop, withhold the
  entire coherent CS generation (withhold_paths), not one file. R2 evidence
  survives and is re-derived from fresh canonical state on a later run.
  Call the fence from the capital_structure job push loop, not the collect
  job (collect unstages data/capital_structure). Identity
  DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES must make that re-derive reuse
  evidence_id.
supersedes:
  - DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR
rationale: >
  Sol accepted the Git-selector boundary and rejected the W0 proposal of a
  CS-owned push-time content-aware merge of source_manifest.jsonl. Capital
  Structure is an all-or-nothing compiled generation. The company already
  shipped the family-withhold fence for government-revenue; the registry is
  additive. Collect's fence cannot see CS artifacts because that job unstages
  them. -X theirs remains on the CS push today and can wholesale-replace the
  JSONL. merge=union is still declined on a prefix-hash ledger.
  Re-merge at push time produces a mixed generation, which
  DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE already declined.
alternatives:
  - option: CS-owned content-aware merge of source_manifest.jsonl at push
    why_not: Merges one file after compile; events/terms/projection/health
      would no longer match that run's manifest.
  - option: merge=union on the JSONL
    why_not: Hash-bound prefix ledger; same class declined for govrev
      candidate_ledger.jsonl.
  - option: New publication control plane or R2 as selector
    why_not: House law; Git-selector boundary is accepted.
  - option: Rely on collect-job push_append_only_fence alone
    why_not: daily.yml unstages data/capital_structure before collect push;
      CS commit and -X theirs happen later in the capital_structure job.
evidence:
  - "DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE"
  - "config/append_only_artifacts.json government-revenue family only on origin/main"
  - ".github/workflows/daily.yml:649 collect unstages data/capital_structure"
  - ".github/workflows/daily.yml:761,787 fence in collect push only"
  - ".github/workflows/daily.yml:1303 CS stages data/capital_structure site/capital-structure-data"
  - ".github/workflows/daily.yml:1332 CS push git pull --rebase --autostash -X theirs, no fence"
  - "Sol AMEND review of PR #5901 2026-08-18"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "config/append_only_artifacts.json"
  - ".github/workflows/daily.yml"
  - "scripts/ci/push_retry.sh"
  - "data/capital_structure/"
confidence: medium
reversibility: costly
decided_by: cursor-grok-4.6
decided_at: 2026-08-18
review_by: 2026-08-25
---

Architecture proposal for Sol/Chairman. Proposed by the Cursor Grok 4.6 W0
session. Restates the accepted Git-selector boundary from the superseded
record; replaces only the push-time file merge. Not a Fable decision. Do not
implement in this PR.

## W1 fence enrollment (spec only)

Additive family in `config/append_only_artifacts.json`:

- key: `capital-structure`
- members at minimum: `data/capital_structure/source_manifest.jsonl`
  (`jsonl_prefix`). If W1 also publishes `retrieval_attempts.parquet` under
  this generation, enroll it as `parquet_rows` with identity `["attempt_id"]`.
- withhold_paths: `data/capital_structure`, `site/capital-structure-data`
  (the coherent compiled generation `daily.yml` already stages together).
- Wire `push_append_only_fence origin/main` in the **capital_structure**
  job retry loop after fetch and before `-X theirs`, the same shape collect
  already uses for government-revenue.

A family this run did not touch stays invisible to the fence. Infrastructure
faults fail open; proven row-drop withholds fail closed
(`DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE`).

## What withholding means

Main keeps the previous coherent CS generation. This run's extra retained
bytes remain in R2. The next CS job re-derives against fresh canonical
state and, with lawful `evidence_id`, does not remint economics.
