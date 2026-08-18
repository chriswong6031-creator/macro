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
  or show the CS push step no longer using -X theirs on rebase, or show a
  content-aware merge that runs before that rebase. Commands:
  rg capital_structure .gitattributes;
  rg -n "X theirs" .github/workflows/daily.yml.
so_what: >
  Do not add merge=union (the ledger is hash-bound; union was declined for
  govrev for the same reason). Wave 1 must own a content-aware merge for this
  file. A CS push that wins with -X theirs can drop the other generation's
  newly retained rows even when R2 still holds the bytes.
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

This is CS-owned conflict handling, not a global daily.yml concurrency rewrite.
DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE still forbids solving the race with
an et_gate mutex.
