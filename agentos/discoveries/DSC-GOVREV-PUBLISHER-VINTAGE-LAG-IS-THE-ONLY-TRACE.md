---
key: GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE
claim: >
  The government-revenue candidate publisher can BUILD a projection that
  admits new candidates and then silently DISCARD it, and the only durable
  trace is that candidate_projection_status.recipient_graph_id stays a
  reviewed-graph vintage behind recipient_entity_graph.graph_id.  Measured on
  run 32258132159 (push, head eb81e91ef90b, 2026-08-19T13:26:50Z): step 9
  "build Government Revenue projection" SUCCEEDED -- the two first-seen BWXT
  candidates were admitted and appended -- step 10 "prove the candidate
  projection before publishing it" FAILED under GOVREV_CANDIDATE_PROOF_FATAL=1,
  and step 11 "commit complete evidence projection" was SKIPPED, so the
  freshly-issued ledger died with the runner workspace.  Two further
  properties keep the lane from self-healing: a heal that touches only
  tests/** does NOT re-arm the publisher (tests/** is absent from the lane's
  push path filter, so merging PR 5997 fired no push run), and a scheduled run
  outside 00xx-01xx UTC quiet-skips the SAM collect, leaving
  status=missing/partial=true and publish=no.  So a wall of green scheduled
  runs is NOT evidence that anything was published, and an emitted-but-unissued
  candidate is a publication-scheduling fact, never a review verdict about the
  row.
falsifier: >
  A publisher that wrote a receipt (or a GitHub annotation) on proof-gate
  abort would make the discarded projection visible directly, collapsing this
  finding to an ordinary failure report; an alarm comparing
  candidate_projection_status.recipient_graph_id against the committed
  recipient_entity_graph.graph_id would surface the lag without anyone
  hand-diffing two artifacts; and a lane whose push path filter included the
  proof suite would re-arm on a test-only heal, so the lag would close on the
  heal's own merge.
so_what: >
  Found while implementing an "explicit reviewed non-issuance record" for two
  unissued BWXT candidates (grc1-2431cef9fbca1f209edb0f45,
  grc1-81a1a8df4bdb97de3b1cdfa8, source award
  CONT_AWD_89233123CNA000308_8900).  Writing that record would have asserted a
  durable review verdict over a transitional scheduling lag and permanently
  holed the one gate that catches the 2026-08-10 unaccounted-candidate
  incident class -- the manifests are immutable sha-bound chains that are
  never retired, so two candidate_ids subtracted from the unaccounted set stay
  subtracted after they issue.  The vintage lag is machine-readable and
  already committed, so it is the honest bound instead: the transitional
  excuse in tests/test_government_revenue_candidates.py is now conjoined with
  "the publisher's own receipt still names an older graph vintage", which
  dies for every row at once when the publisher catches up and needs no
  curation.  Corollary for future sessions: never diagnose an unissued
  candidate from the ledger alone -- read status.recipient_graph_id first,
  and check whether the last PUSH-event run of government-revenue-live.yml
  reached its commit step.
kind: constraint
scope:
  - .github/workflows/government-revenue-live.yml
  - data/government_revenue/candidate_projection_status.json
  - tests/test_government_revenue_candidates.py
  - scripts/build_government_revenue_candidates.py
verified_at: 2026-08-19
verified_by: "gh run view 32258132159 --json jobs: step 9 build=success, step 10 prove=failure, step 11 commit=skipped; committed status.recipient_graph_id='recipient-graph:reviewed:2026-08-08:defense19-v1' vs graph.graph_id='recipient-graph:reviewed:2026-08-19:defense21-v1'; live rebuild partition emitted 64 / ledger 62 / quarantined 8 / queue 54, unaccounted == exactly the two BWXT ids"
confidence: verified
---
