---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2d-discovery
model: codex
ended_because: ci_handoff
mission: >
  Qualify the natural-run discovery falsifier, implement one bounded official
  Latest Filings plus daily-index reconciliation plane, and stop in a draft
  HOLD-FOR-SOL PR without merging, dispatching daily, or starting W3/W4.
state_before: >
  W2A and W2B were proven live and natural run 32786919396 drained inherited
  LIVE debt to zero. W2 remained in progress because discovery expected a
  future/not-yet-built SEC daily index and the Capital Structure job crossed
  its warning. W2C and W2D were separately authorized; W2D could be researched
  and built but not merged before W2C adjudication.
changed:
  - path: engine/capital_structure/sec_discovery_clock.py
    what: >
      Add one America/New_York filing-day clock with separate real-time filing
      and conservative next-day daily-index readiness expectations.
  - path: collectors/sec_capital_structure.py
    what: >
      Add bounded exhaustive Latest Filings Atom traversal, role-aware accession
      dedupe, fail-closed source-movement detection, provisional discovery, and
      daily-index in-place reconciliation through the existing ledger/queue.
  - path: engine/capital_structure/ingestion_health.py
    what: >
      Separate same-day observation health from daily-index reconciliation
      health while retaining legacy receipt interpretation.
  - path: contracts/capital_structure_retrieval_queue_receipt.schema.json
    what: Bind generated receipts to the W2D discovery-clock policy.
  - path: contracts/capital_structure_ingestion_health.schema.json
    what: Admit explicit real-time filing and Latest Filings health watermarks.
  - path: tests/
    what: >
      Add hostile clock, traversal, outage, reconciliation, identity, and
      no-duplicate-event coverage; keep daily-index-only W1 fixtures isolated
      from live network calls.
  - path: research/CAPITAL_STRUCTURE_W2D_SEC_DISCOVERY_QUALIFICATION_2026-08-25.md
    what: Record official source law, canaries, architecture, bounds, and gates.
  - path: agentos/decisions/DEC-CS-V2-W2D-DUAL-DISCOVERY-CLOCK.md
    what: Record the chosen one-ledger dual-clock discovery law and alternatives.
  - path: agentos/discoveries/DSC-CS-V2-W2D-DAILY-INDEX-READINESS.md
    what: Preserve the measured readiness classification and traversal finding.
verified:
  - claim: The original daily-index failure is a readiness/clock defect, not proven SEC downtime.
    command: >
      Inspect run 32786919396 generation a6ff3b6b47db index coverage at
      2026-08-25T00:04:02Z; run exact production-header read-only canaries for
      form.20260824.idx, form.20260825.idx, and QTR3 index.json after publication.
    result: >
      August 24 later returned 200 with Last-Modified 22:01:43 ET and SHA-256
      40b557e6e6782c79084c6d7256d81dff8a498ebf8040d9b65f05cdcaeea7f649;
      August 25 was absent from the listing and returned XML AccessDenied before
      its nightly build. The original probe was August 24 at 20:04 ET.
  - claim: One Latest Filings page cannot prove exhaustive market-wide same-day discovery.
    command: >
      Traverse 30 Atom pages at count=100 with production identity and 0.12s pacing,
      deduping canonical accession and recording filing/update boundaries.
    result: >
      All 30 pages were full; 3,000 listing rows represented 2,031 unique
      accessions; page 29 still contained boundary-day entries and no trustworthy
      next/total metadata was present.
  - claim: Hostile W2D clock, collector, health, contract, identity, and closed-bundle fixtures pass.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest -q over
      tests/test_capital_structure_sec_discovery_clock.py,
      tests/test_sec_capital_structure.py,
      tests/test_capital_structure_ingestion_health.py,
      tests/test_capital_structure_contracts.py,
      tests/test_daily_capital_structure_job.py,
      tests/test_capital_structure_source_identity.py,
      tests/test_capital_structure_source_manifest.py,
      tests/test_capital_structure_evidence_identity.py, and
      tests/test_capital_structure_closed_bundle.py.
    result: >
      Focused constituent runs passed: clock/collector 67, health 32,
      contracts/daily 53, source identity/manifest 22, evidence identity 32,
      and closed bundle 9. Only known temporary pytest cleanup warnings appeared.
  - claim: Overlay-to-daily reconciliation creates no duplicate evidence or event.
    command: >
      Run test_latest_filings_then_daily_reconciliation_keeps_one_evidence_and_event.
    result: >
      One discovery accession was corrected in place; the source-ledger bytes
      stayed byte-identical, retrieval attempts remained one, evidence IDs were
      unique, compiler output contained one event, and compile failures were zero.
unverified:
  - claim: W2D exact-head hosted CI, fences, and active authority have concluded green.
    what_would_verify: >
      Push the final immutable branch head, open the draft HOLD-FOR-SOL PR, and
      wait for every binding hosted check on that SHA to conclude.
  - claim: W2D is accepted, merged, or proven live.
    what_would_verify: >
      Sol must accept and release the held head after W2C adjudication; then the
      first natural scheduled chain containing both merges must prove the new
      health contract in production.
unresolved:
  - "W2C remains a separate held Sol-adjudication carrier and must be adjudicated before W2D merge."
  - "W2 remains in progress; zero inherited debt alone did not prove healthy discovery or sustainable runtime."
  - "W3 and W4 remain held and unstarted."
next_actions:
  - Park the exact W2D head in one draft `[HOLD-FOR-SOL]` PR with no auto-merge or merge-on-green label.
  - Obtain exact-head hosted CI, fences, active authority, and final current-main collision receipts.
  - Return the immutable W2C and W2D packets to Sol; do not merge either carrier here.
  - After Sol accepts and releases both in order, observe only the first natural scheduled chain containing both.
do_not_redo:
  - Reclassify every SEC 403 as rate limiting or every 403 as readiness without object-time evidence.
  - Replace bounded traversal with a one-page Latest Filings sample.
  - Treat Latest Filings metadata as retained filing evidence.
  - Add another queue, store, job, cadence, timeout, carrier, or authority plane.
  - Change the 500/20/20 envelope, scheduler semantics, W1 identities, #5792, append-only fence, or prophet authority.
  - Dispatch or rerun daily.yml, merge before Sol release, or start W3/W4.
danger_areas:
  - "Equal update timestamps can span Atom pages; the boundary comparison must retain equals and stop only after a strictly older entry."
  - "A short/empty page or crossed durable watermark proves traversal; the fixed page cap alone never does."
  - "A complete prior-day daily index cannot make the horizon current when the expected same-day Latest Filings observation is missing."
decisions:
  - DEC:CS-V2-W2D-DUAL-DISCOVERY-CLOCK
discoveries:
  - DSC:CS-V2-W2D-DAILY-INDEX-READINESS
---

This is a held build/qualification handoff, not release, deployment, or natural
production proof. W2 stays open and W3/W4 stay held.
