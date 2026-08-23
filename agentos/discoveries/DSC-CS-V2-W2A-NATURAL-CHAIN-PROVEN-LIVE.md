---
key: CS-V2-W2A-NATURAL-CHAIN-PROVEN-LIVE
claim: >
  The first natural 22:30Z daily.yml collect whose checkout contains W2A merge
  7ea3dc5b421d is run 32603557988 at event SHA fa73271632a7. Collect job
  97105275976 and capital_structure job 97119200594 both succeeded and
  published generation 73d9810fe3f9. The fixed 160/20/20 reserves selected
  LIVE_TAIL 180, RECOVERY 0, HISTORICAL_BACKFILL 20 after the empty recovery
  reserve spilled 20 slots to live. Retrieval closed 180/0/19, with one
  historical registration 404 becoming the sole transient failure. The run
  saw 202 live arrivals against effective live capacity 180, left 857 live and
  17,797 historical filings unselected, and truthfully published
  degraded_capacity with reasons live_tail_arrival_overflow and
  live_tail_unserved_after_selection. Discovered, eligible-retained, and
  compiled watermarks all reached the completed 2026-08-21 SEC session with
  zero completed-session gaps. Projection information freshness therefore
  remained stale under the adverse capacity state while compiler-generation
  freshness was fresh. W1 identity, closed bundles, the whole-generation
  append-only fence, the #5792 zero-progress verdict, the 200-filing cap, and
  prophet_authority=false all remained intact.
falsifier: >
  Show that fa73271632a7 is not a descendant of 7ea3dc5b421d, either named job
  did not conclude success, generation 73d9810fe3f9 is absent from origin/main,
  the generation artifacts disagree with the class/horizon values above, a
  newly appended child uses legacy occurrence identity or lacks parent byte
  coordinates, a current accession is not a closed bundle, stable
  occurrence-plus-bytes reminted evidence_id, the append-only fence withheld or
  did not run, projection.json and latest.json differ, compile_failures is
  non-empty, MAX_FILINGS_PER_RUN differs from 200, the #5792 decide_verdict
  function changed in #6220, or any published authority block makes
  prophet_authority true.
so_what: >
  W2A is production-closed. Do not dispatch another daily or wait for another
  generation to prove it. Keep degraded_capacity visible: the bounded class
  split preserves fairness but cannot clear current live arrivals. Do not
  reinterpret a fresh compiler generation as a current information horizon.
  Pause; W3 and W4 require a separate authorized commission.
kind: runtime
verified_at: 2026-08-23
verified_by: >
  gh run/job API receipts for 32603557988, 97105275976, and 97119200594;
  git merge-base --is-ancestor 7ea3dc5b421d fa73271632a7; git show and jq on
  73d9810fe3f9 retrieval_queue_receipt.json, ingestion_run.json, health.json,
  telemetry.json, and projection.json; pandas read of retrieval_attempts.parquet;
  Python manifest prefix/identity/closed-bundle audit against parent 931e4c1e42ec;
  SHA-256 and Git-blob comparison of projection.json and latest.json; AST source
  hash of decide_verdict before and after #6220.
scope:
  - macro
  - capital-structure-intelligence
  - collectors/sec_capital_structure.py
  - engine/capital_structure/ingestion_health.py
  - data/capital_structure/
confidence: verified
---

This is an adverse-but-accepted production receipt: the generation is coherent
and current through the latest completed SEC session, but the run itself proves
that fixed capacity is below live arrivals. `degraded_capacity` is the correct
instrument state, not a failed W2A implementation and not a market verdict.
