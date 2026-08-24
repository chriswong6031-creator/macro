---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2b-natural-proof-closeout
model: codex
ended_because: complete
mission: >
  Receipt the first natural post-#6287 W2B collector -> Capital Structure chain,
  mark W2B proven live without falsely closing W2, and stop without starting W3
  or W4.
state_before: >
  Sol released exact PR #6287 head f50ba6cf76f0, which squash-merged as
  0a23f1ffcedc at 2026-08-23T06:56:37Z. W2B was BUILT_NOT_PROVEN pending the
  first natural scheduled chain containing that merge. W2 remained in progress
  with 857 inherited unserved LIVE filings.
changed:
  - path: agentos/discoveries/DSC-CS-V2-W2B-NATURAL-CHAIN-PROVEN-LIVE.md
    what: >
      Record the exact natural-run ancestry, reservations, spill, class/lane
      service, runtime, horizon, projection, W1, #5792, fence, twin, and
      authority receipts with falsifier and future operating consequence.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: >
      Mark W2B done and proven live while keeping W2 in progress, the remaining
      337 LIVE debt visible, and W3/W4 held behind W2.
  - path: agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-24-w2b-natural-proof.md
    what: Close this proof wave with reproducible commands and exact receipts.
verified:
  - claim: The first qualifying natural chain ran W2B code and both required jobs succeeded.
    command: >
      gh run view 32671784885 --json event,headSha,createdAt,status,conclusion,jobs;
      git merge-base --is-ancestor 0a23f1ffcedc7d8a3838b05ef137742eb1d809a1
      c5cd5dbca25dd676c25cdfcd4f2f7a1812022f44
    result: >
      Scheduled run created 2026-08-23T22:49:57Z. Collect job 97273624140
      succeeded 22:50:04Z -> 01:15:57Z. Capital Structure job 97292842139
      succeeded 01:15:59Z -> 02:21:31Z. The merge is an ancestor. No daily was
      dispatched, cancelled, or rerun. Unrelated downstream jobs may continue
      independently of these terminal-success jobs.
  - claim: Exact reservations, spill, class and lane outcomes satisfy W2B law.
    command: >
      git show 8a3628f1c2bb:data/capital_structure/retrieval_queue_receipt.json;
      git show 8a3628f1c2bb:data/capital_structure/ingestion_run.json; pandas
      current-run group-by of retrieval_attempts.parquet
    result: >
      Reserved 500/20/20 under derived cap 540. RECOVERY pending 0 and spilled
      all 20 slots to LIVE, so final quotas and selections were LIVE 520,
      RECOVERY 0, HISTORICAL 20. All 540 attempts stored; no retrieval, parser,
      or storage deferral. Current-run arrivals 0, overflow 0. LIVE pending ->
      selected -> unserved was 857 -> 520 -> 337, so inherited debt fell by
      exactly 520 from the prior 857. RECOVERY was unpopulated. HISTORICAL was
      17,797 -> 20 -> 17,777 and retained protected service.
  - claim: Every class/lane selection and retrieval outcome is accounted for.
    command: >
      jq work_classes/lanes on retrieval_queue_receipt.json and pandas group-by
      work_class,retrieval_lane on 540 attempts at or after
      2026-08-23T23:54:22.425342Z
    result: >
      Overall lane pending -> selected -> unselected: registration
      1,360 -> 50 -> 1,310; state 1,553 -> 47 -> 1,506; prospectus
      3,715 -> 185 -> 3,530; reg_a 628 -> 16 -> 612; current report
      9,042 -> 186 -> 8,856; periodic 2,068 -> 44 -> 2,024; proxy
      288 -> 12 -> 276. LIVE selected/retrieved by those lanes was
      46/45/182/14/182/40/11. HISTORICAL selected/retrieved was
      4/2/3/2/4/4/1. Total pending/selected/unserved was
      18,654/540/18,114; parked remained 404.
  - claim: SEC behavior and both existing runtime envelopes stayed healthy.
    command: >
      pandas audit of current retrieval_attempts rows; inspect completed collect
      log and timing row 9b35a3839c6e; inspect Capital Structure timing row
      12c6ac010a73
    result: >
      Current attempts were 540 unique sources, all state=stored with no error,
      error_class, HTTP status, SEC 404, SEC 429, or retry. The 404 census count
      of three is historical and produced no current attempt. The dedicated
      r2_capital_structure write probe still returned storage AccessDenied and
      used the unchanged r2_research fallback; storage_deferred stayed zero.
      Collector wall was 144.7m/240m (60.3%), below the unchanged 204m warning
      and 240m hard lines; sec_capital_structure was 2,256.0s = 37.6m.
      Downstream wall was 65.3m/90m (72.5%). No carrier tripwire fired.
  - claim: Watermarks, gaps, horizon reasons, and compilation are canonical and honest.
    command: >
      jq horizon/counters/source watermarks from 8a3628f1c2bb health.json and
      compile_failures/counts from telemetry.json
    result: >
      Latest discovered, eligible-retained, compiled, completed, and expected
      SEC index dates were all 2026-08-21; expected status complete; discovery
      -> retained and retained -> compiled completed-session gaps were both 0.
      Horizon degraded_capacity had the sole reason
      live_tail_unserved_after_selection. Compilation failures were 0;
      compiler counts were 2,137 events, 32 edges, 1,535 review items, and
      6,890 source manifests. Health verdict was ok.
  - claim: Projection is exactly generation-bound and its canonical/public twins are identical.
    command: >
      jq source_receipt/coverage on projection.json; compare compiler telemetry
      hashes; git rev-parse and shasum -a 256 on projection.json and
      site/capital-structure-data/latest.json at 8a3628f1c2bb
    result: >
      Compiler generation generation:cs:51a3af1ad01ef167ed251b43 and its three
      artifact hashes bind exactly into projection generation
      projection:cs:355740fc6b12ae3dc52ddb87. Projection freshness was stale
      under inherited debt while generation freshness was fresh at 1.075887h.
      Both twins were 9,458,281 bytes, Git blob
      74f44633b19d2baeec8064b0ece7d012b35dee6c, and SHA-256
      aff5c87dce93ececc2d0ecd18adf7ce73a9de241fe26a65c377df6ec07599ec4.
  - claim: W1 identity, closed bundles, append-only publication, #5792, capacity, and authority remained stable.
    command: >
      Python source_manifest audit of 73d9810fe3f9 vs 8a3628f1c2bb; Capital
      Structure job append-only fence receipt; AST-strip source hash of
      ingestion_health.decide_verdict at 26dc696c3ae6, 7ea3dc5b421d,
      0a23f1ffcedc, and 8a3628f1c2bb; git show/grep W2B constants; jq authority
    result: >
      Ledger grew 5,350 -> 6,890 by 540 complete submissions and 1,000 children
      as a byte-identical append. All 5,350 prior occurrence-plus-bytes keys
      retained evidence_id. All 1,000 new children were parent-SHA/byte-range
      coordinate-bound; zero new legacy occurrence or evidence IDs. All 2,137
      current accession bundles closed; zero failures. source-ledger
      immutable_prefix=true; append-only fence reported capital-structure ok for
      both members and the push succeeded on attempt 1. decide_verdict stayed
      byte-identical at SHA-256
      74cd0a97e34a13308d1f4c291c7f300ed950c1056c7e549a0c4bc2d562e342ca.
      PACE_SECONDS=0.12; reservations remain 500/20/20 and MAX_FILINGS_PER_RUN
      is their derived 540 sum. prophet_authority=false in ingestion, queue,
      health, telemetry, and projection.
  - claim: The natural generation is durable on canonical main.
    command: git merge-base --is-ancestor 8a3628f1c2bb origin/main
    result: >
      Generation 8a3628f1c2bb and its later timing commits are ancestors of
      origin/main at the proof closeout base 16cc28b074af.
unverified:
  - claim: W2 has reached the canonical closure gate.
    what_would_verify: >
      A later natural scheduled chain must report healthy discovery,
      horizon.state=current, and live_tail_unserved_after_selection=0.
unresolved:
  - "Inherited LIVE debt remains 337; this is the sole degraded-capacity reason."
  - "The dedicated r2_capital_structure store still rejects writes; fallback retained all current work in r2_research."
  - "Company Facts remains default-off/unprovisioned and is outside W2B."
  - "W3 and W4 remain unstarted and held behind W2."
next_actions:
  - Merge only this narrow Agent OS closeout after its own exact-head checks conclude.
  - Continue observing normal scheduled chains; never dispatch, rerun, or create W2C merely to drain debt.
  - Close W2 only at a natural current horizon with healthy discovery and zero unserved LIVE, unless Sol rerules.
  - Return to Sol for W3/W4 sequencing after W2 closes; do not start either here.
do_not_redo:
  - Dispatch or rerun daily.yml to re-prove W2B or accelerate the inherited debt drain.
  - Change the 500/20/20 envelope, carrier, source, queue, job, cadence, timeout, scheduler, identity, horizon, projection, fence, or authority law.
  - Count the historic 404 census or dedicated-store 403 as a current SEC rate-limit response.
  - Treat fresh compiler-generation age as a current information horizon.
  - Mark W2 done while 337 LIVE filings remain unserved.
  - Start W3 or W4.
danger_areas:
  - "degraded_capacity is allowed solely because inherited LIVE debt remains; it is not a failed W2B proof."
  - "RECOVERY was empty, so its protected-service condition was not falsified; its exact 20-slot spill is the relevant receipt."
  - "The overall daily workflow can continue independently of the two required terminal-success jobs; do not interfere with unrelated work."
prs: [6287]
decisions:
  - DEC:CS-V2-W2B-500-LIVE-ENVELOPE
discoveries:
  - DSC:CS-V2-W2B-NATURAL-CHAIN-PROVEN-LIVE
---

W2B is done and production-proven. W2 remains in progress until natural
scheduled work drains the remaining 337 LIVE filings and the canonical horizon
becomes current. No W2C, W3, or W4 work is authorized by this receipt.
