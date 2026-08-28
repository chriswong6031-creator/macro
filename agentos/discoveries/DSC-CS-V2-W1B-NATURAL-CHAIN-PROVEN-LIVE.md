---
key: CS-V2-W1B-NATURAL-CHAIN-PROVEN-LIVE
claim: >
  The first natural scheduled daily.yml collect → capital_structure chain whose
  collect checkout contains W1B merge ec388d963190 is GitHub run 32426513915
  (22:30Z 2026-08-20, event SHA 50577f18c5fb). Collect job 96609474282 and
  capital_structure job 96637756516 both succeeded and published generation
  3ba28993b741. Newly written children used coordinate-bound occurrence
  identity; zero fresh legacy:{source_id}; every current accession was a closed
  bundle; compile_failures=0; latest.json matched projection.json;
  prophet_authority stayed false; the append-only fence ran and did not withhold.
falsifier: >
  Show that run 32426513915 collect job checked out a SHA that is not a
  descendant of ec388d963190, or that capital-structure nightly generation
  3ba28993b741 is missing from origin/main, or that after-ledger
  source_manifest.jsonl contains a new child with evidence_occurrence
  starting legacy:, or that telemetry.json compile_failures != 0, or that
  site/capital-structure-data/latest.json is not byte-identical to
  data/capital_structure/projection.json at that generation.
so_what: >
  W1B is production-closed. Do not wait for another nightly to prove W1. Do
  not dispatch a daily to re-prove it. Do not treat the cancelled overall
  workflow conclusion as a failed CS chain — collect and capital_structure
  jobs on that run succeeded. W2 is the next action and still unstarted.
kind: runtime
verified_at: 2026-08-21
verified_by: >
  gh run view 32426513915; git merge-base --is-ancestor ec388d963190 50577f18c5fb;
  git show 3ba28993b741:data/capital_structure/{ingestion_run,health,telemetry,projection}.json
  and source_manifest.jsonl; sha256 of projection.json vs site/capital-structure-data/latest.json.
scope:
  - macro
  - capital-structure-intelligence
  - collectors/sec_capital_structure.py
  - data/capital_structure/
confidence: verified
---

Overall workflow conclusion for run 32426513915 is `cancelled` because a later
job (`standout_audit_us`) cancelled. That does not retract the collect or
capital_structure successes or the published generation.
