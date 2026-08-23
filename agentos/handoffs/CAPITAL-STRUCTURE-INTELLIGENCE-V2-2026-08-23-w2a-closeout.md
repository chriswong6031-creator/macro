---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2a-closeout
model: codex
ended_because: complete
mission: >
  Receipt the first natural post-#6220 W2A collector -> Capital Structure chain,
  close W2A in Agent OS, and stop without starting W3 or W4.
state_before: >
  #6220 had independent Sol PASS, exact-head CI run 32556582284 concluded green,
  and merged as 7ea3dc5b421d. W2A remained in progress until a natural scheduled
  daily containing the merge proved the class scheduler, canonical horizon,
  projection binding, W1 invariants, and publication path in production.
changed:
  - path: agentos/discoveries/DSC-CS-V2-W2A-NATURAL-CHAIN-PROVEN-LIVE.md
    what: >
      Record the exact natural-run class, backlog, horizon, projection, W1,
      #5792, cap, fence, twin, and authority receipts with falsifier and future
      operating consequence.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: >
      Mark W2/W2A done and proven live, point to the closeout evidence, and keep
      W3/W4 explicitly unstarted pending separate authority.
  - path: agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-23-w2a-closeout.md
    what: Close the session with commands and exact production receipts.
verified:
  - claim: The first qualifying natural chain ran W2A code and both required jobs succeeded.
    command: >
      gh run view 32603557988; GitHub job logs for collect 97105275976 and
      capital_structure 97119200594; git merge-base --is-ancestor
      7ea3dc5b421d081a7b04d3cc670a89b915e320a9
      fa73271632a7cf5eb214e4e68bdfcb96c22422b0
    result: >
      Scheduled run created 2026-08-22T22:50:19Z. Collect checked out
      fa73271632a7 and succeeded 22:50:27Z -> 00:57:33Z. Capital Structure
      succeeded 00:59:47Z -> 02:05:02Z. The merge is an ancestor. No duplicate
      daily, cancellation, or rerun was issued.
  - claim: The exact class reservations, spill, lane service, outcomes, and remaining backlog are proven.
    command: >
      git show 73d9810fe3f9:data/capital_structure/retrieval_queue_receipt.json;
      git show 73d9810fe3f9:data/capital_structure/ingestion_run.json; pandas
      group-by of current-run rows in retrieval_attempts.parquet
    result: >
      Reserved 160/20/20. RECOVERY pending 0 and spilled all 20 slots to LIVE,
      so final quotas/selected were LIVE 180, RECOVERY 0, HISTORICAL 20.
      Retrieved 180/0/19; one historical registration attempt was transient
      404; parser/storage deferred were zero. Pending -> selected -> unselected
      by lane was registration 1416 -> 56 -> 1360, state 1579 -> 26 -> 1553,
      prospectus 3745 -> 30 -> 3715, reg_a 643 -> 15 -> 628,
      issuer_current_report 9072 -> 30 -> 9042, issuer_periodic 2097 -> 29 ->
      2068, issuer_proxy 302 -> 14 -> 288. Retrieved by those lanes was
      55/26/30/15/30/29/14 respectively; only registration had one retrieval
      failure. Current-run live arrivals were 202, effective capacity 180,
      overflow 22. Remaining unselected backlog was LIVE 857, RECOVERY 0,
      HISTORICAL 17,797 (18,654 total), with parked count now 404.
  - claim: Canonical horizon and projection binding publish the adverse capacity state honestly.
    command: >
      jq on 73d9810fe3f9 health.json, telemetry.json, and projection.json; compare
      SHA-256 and Git blob ids for projection.json and latest.json
    result: >
      Discovered, eligible-retained, compiled, completed, and expected SEC
      filing watermarks are all 2026-08-21; expected status complete; both
      completed-session gaps are 0. Horizon is degraded_capacity solely for
      live_tail_arrival_overflow and live_tail_unserved_after_selection.
      Compiler generation generation:cs:bbf9d624349f09c8d3d55b7b and as_of
      2026-08-23T01:00:04.261441Z bind exactly into projection source_receipt.
      Projection freshness is stale, generation_freshness is fresh with age
      1.06224h, compile_failures is empty, and the canonical/public twins share
      Git blob 64a17df6722a72ba6346a1987db0bc64b6f521d2 and SHA-256
      a0242a1f0180365bea10f8d66dbe05fb39439a47270fa6bb5491f35cd68a09c3.
  - claim: W1 identity/publication, #5792, the cap, and authority remained stable.
    command: >
      Python source_manifest audit of 931e4c1e42ec vs 73d9810fe3f9; capital job
      log append-only fence receipt; AST hash compare of decide_verdict at
      26dc696c3ae6, 7ea3dc5b421d, and 73d9810fe3f9; git grep
      MAX_FILINGS_PER_RUN; jq authority blocks
    result: >
      The ledger grew 4665 -> 5350 by 199 complete submissions and 486 children.
      All 486 children were coordinate-bound; zero new or stored legacy
      occurrence/evidence ids. All 1,597 current accession bundles closed with
      zero failures. All 4,665 prior occurrence-plus-bytes keys kept the same
      evidence_id. Source-ledger immutable_prefix=true; the push logged
      append-only-base-fence ok for both family members and published on attempt
      1. decide_verdict stayed byte-identical at SHA-256
      74cd0a97e34a13308d1f4c291c7f300ed950c1056c7e549a0c4bc2d562e342ca;
      health verdict was ok because durable verified evidence advanced.
      MAX_FILINGS_PER_RUN=200. prophet_authority=false in ingestion, health,
      telemetry, and projection.
  - claim: The natural generation is durable on canonical main.
    command: git merge-base --is-ancestor 73d9810fe3f9 origin/main
    result: Generation 73d9810fe3f9 is an ancestor of current origin/main.
unverified: []
unresolved:
  - "The 200 cap remains structurally below observed live arrivals; W2A exposes rather than solves that deficit."
  - "The dedicated r2_capital_structure store still rejects writes; this run safely retained in r2_research and storage_deferred stayed zero."
  - "Company Facts remains default-off/unprovisioned and is outside W2A."
  - "W3 and W4 are not started."
next_actions:
  - Pause after the closeout PR merges and its durable main bytes are verified.
  - Await a separately authorized W3 or W4 commission; do not infer it from W2A completion.
do_not_redo:
  - Dispatch another daily to re-prove W2A.
  - Change or reinterpret the 160/20/20 policy or the 200 cap without new evidence and review.
  - Present compiler-generation freshness as information-horizon freshness.
  - Reopen W1 identity, closed-bundle, append-only, or #5792 laws without new failure evidence.
  - Start W3 or W4 from this closeout.
danger_areas:
  - "degraded_capacity is an accepted instrument verdict and an honest adverse production result, not a failed W2A chain."
  - "The one historical 404 became parked; do not count it as recovered or hide it inside retrieved totals."
  - "The overall daily can conclude independently of these two terminal-success jobs; do not cancel healthy downstream work to force a workflow verdict."
prs: [6220, 6282]
decisions:
  - DEC:CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS
discoveries:
  - DSC:CS-V2-W2A-NATURAL-CHAIN-PROVEN-LIVE
---

W2A is done and production-proven. This closeout deliberately leaves W3 and W4
unstarted.
