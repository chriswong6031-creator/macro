---
key: CS-V2-W2B-NATURAL-CHAIN-PROVEN-LIVE
claim: >
  The first natural scheduled daily.yml collect whose checkout contains W2B
  merge 0a23f1ffcedc is run 32671784885 at event SHA c5cd5dbca25d. Collect job
  97273624140 and capital_structure job 97292842139 both succeeded and
  published generation 8a3628f1c2bb. The canonical 500/20/20 reservations
  selected LIVE_TAIL 520, RECOVERY 0, and HISTORICAL_BACKFILL 20 after the
  empty recovery reserve spilled 20 slots to live. Retrieval stored all
  520/0/20 selections with no current-run SEC 404, 429, retry, parser, or
  storage failure. The weekend run admitted zero current LIVE arrivals and
  therefore had zero arrival overflow; inherited LIVE debt decreased from 857
  to 337. HISTORICAL retained its protected 20 slots, while the RECOVERY
  service condition was not applicable because its pending class was empty.
  Collector wall time was 144.7 minutes of the unchanged 240-minute cap,
  sec_capital_structure attributable time was 37.6 minutes, and downstream
  Capital Structure wall time was 65.3 minutes of 90. The canonical horizon
  remained degraded_capacity solely for live_tail_unserved_after_selection.
  All five discovered, retained, compiled, completed, and expected watermarks
  were 2026-08-21 with zero completed-session gaps. Compiler generation
  generation:cs:51a3af1ad01ef167ed251b43 bound exactly into projection
  generation projection:cs:355740fc6b12ae3dc52ddb87; compiler-generation
  freshness was fresh while honest information freshness remained stale.
  Canonical/public twins were byte-identical. Compile failures, W1 identity
  remints, open bundles, fresh legacy child identities, append-only-fence
  failures, #5792 drift, and prophet authority were all zero/absent.
falsifier: >
  Show that c5cd5dbca25d is not a descendant of 0a23f1ffcedc, either named job
  did not conclude success, generation 8a3628f1c2bb is absent from canonical
  main, a current retrieval attempt was not stored, admitted arrivals were
  nonzero or overflow was nonzero, inherited LIVE unserved did not fall from
  857 to 337, the populated HISTORICAL class did not receive 20 slots, the
  empty RECOVERY reserve did not spill exactly 20 slots to LIVE, a runtime
  warning/hard tripwire fired, the horizon has a reason other than inherited
  LIVE debt, any completed-session gap is nonzero, projection does not bind the
  exact compiler generation and hashes, the twins differ, compile_failures is
  non-empty, a prior occurrence-plus-bytes key changed evidence_id, a new child
  uses a legacy or unbound occurrence, any current accession bundle is open,
  the append-only fence failed, ingestion_health.decide_verdict differs from
  the #5792 source hash, the global ceiling is not the sum 500+20+20, or any
  published authority block makes prophet_authority true.
so_what: >
  W2B is production-proven on the existing natural carrier and its 500/20/20
  envelope must not be reopened merely because inherited debt remains. Keep W2
  in progress and let the remaining 337 LIVE filings drain through normal
  scheduled chains only. Do not create W2C merely to wait. W2 closes only when
  a natural run reports horizon.state=current with healthy discovery and zero
  unserved LIVE work, unless Sol explicitly rerules. W3 and W4 remain held.
kind: runtime
verified_at: 2026-08-24
verified_by: >
  gh run/job API receipts for 32671784885, 97273624140, and 97292842139;
  git merge-base --is-ancestor 0a23f1ffcedc c5cd5dbca25d; git show and jq on
  8a3628f1c2bb retrieval_queue_receipt.json, ingestion_run.json, health.json,
  telemetry.json, and projection.json; pandas current-run audit of
  retrieval_attempts.parquet; data/ops/nightly_timings rows in commits
  9b35a3839c6e and 12c6ac010a73; Python source-manifest prefix, identity,
  coordinate, and closed-bundle audit against 73d9810fe3f9; SHA-256 and Git
  blob comparison of projection.json and latest.json; AST source hash of
  ingestion_health.decide_verdict across #5792, W2A, W2B, and this generation.
scope:
  - macro
  - capital-structure-intelligence
  - collectors/sec_capital_structure.py
  - engine/capital_structure/ingestion_health.py
  - data/capital_structure/
confidence: verified
---

This is a successful bounded-capacity production receipt and an intentionally
incomplete W2 receipt. The remaining 337 LIVE filings are inherited debt, not
arrival overflow, and keep the horizon honestly degraded until natural runs
drain them.
