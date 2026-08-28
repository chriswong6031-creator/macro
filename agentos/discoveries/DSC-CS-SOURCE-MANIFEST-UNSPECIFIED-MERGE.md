---
key: CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE
claim: >
  data/capital_structure/source_manifest.jsonl is not listed in
  .gitattributes, so git merge is unspecified, while the capital_structure
  job publishes with git pull --rebase --autostash -X theirs origin main,
  which can wholesale-replace that JSONL when two CS or collect generations
  conflict, the same lost-update mechanism measured on government-revenue
  receipts.
falsifier: >
  Show a .gitattributes line for data/capital_structure/source_manifest.jsonl,
  or show the capital_structure job push calling push_append_only_fence
  before -X theirs with a capital-structure family in
  config/append_only_artifacts.json whose withhold_paths cover the coherent
  CS generation. Commands:
  rg capital_structure .gitattributes;
  rg -n "push_append_only_fence" .github/workflows/daily.yml;
  rg capital-structure config/append_only_artifacts.json.
so_what: >
  Do not add merge=union. Do not content-aware-merge source_manifest.jsonl at
  push time (Sol AMEND 2026-08-18: a post-compile file merge is not a coherent
  CS generation). Wave 1 extends DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE
  so a CS push that would drop main's source-ledger evidence withholds the
  whole family. R2 bytes survive for re-derive. See
  DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  rg capital_structure .gitattributes empty at 791148b2b7d5.
  .github/workflows/daily.yml CS push step uses
  git pull --rebase --autostash -X theirs origin main.
  Sibling: DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS.
scope:
  - macro
  - capital-structure-intelligence
  - data/capital_structure/source_manifest.jsonl
  - .github/workflows/daily.yml
confidence: verified
---

The lost-update mechanism remains. The W1 remedy is the existing
whole-generation append-only push fence, not a file-level merge.
DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE still forbids solving the race with
an et_gate mutex.
