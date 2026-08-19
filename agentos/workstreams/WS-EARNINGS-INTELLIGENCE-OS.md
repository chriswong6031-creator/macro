---
key: EARNINGS-INTELLIGENCE-OS
title: Earnings Intelligence OS — E0 freeze through E2 golden workspace
objective: >
  Finish the Company Event / Earnings Intelligence product over the existing
  provenance substrate. Done for this workstream's first arc means E0 artifacts
  are merged, E1 binds AAPL FY2026 Q3 into event_workspace.v1, and E2 renders
  that payload in the existing Terminal workspace and dossier glance.
status: active
program: earnings-intelligence
repos: [macro, terminal]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: specified
next_action: >
  Implement E2-D only: render the live AAPL FY2026 Q3 event_workspace.v1
  (generation f709a0a6ec514282d5769e7d, event_id evt_cik0000320193_2026q3_results)
  in the existing Macro dossier Company Intelligence glance with the same
  stance and event id as Terminal Brief. Do not reopen E2-T1. Do not re-read
  the v1 score overlay. Do not start E3+.
owns_paths:
  - research/earnings_intelligence/**
  - research/EARNINGS_INTELLIGENCE_E0_FREEZE_ARCHAEOLOGY_AND_EXPERIENCE_HANDOFF_2026-08-16.md
  - research/EARNINGS_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md
  - engine/earnings_narrative/**
  - engine/company_intelligence/**
  - templates/earnings_wire/**
decisions:
  - "DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE"
  - "DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP"
  - "DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT"
discoveries:
  - "DSC:EARNINGS-PROVENANCE-SUBSTRATE-OUTRAN-THE-PRODUCT"
  - "DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER"
  - "DSC:E1-READER-IS-NOT-THE-PRODUCTION-OBJECT"
  - "DSC:EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED"
  - "DSC:CN-POST-EVENT-TAPES-SHARE-NO-EVENT-ID"
do_not_redo:
  - Rebuild Terminal transcripts, Stage, Group Reads, TIL, or a standalone earnings app.
  - Treat Earnings Wire excerpt archive as the finished intelligence product.
  - Listing-key dual-class events (GOOG/GOOGL) as two issuers.
  - Treat a production-shaped reader test as proof the R2 object exists.
  - Publish E1 test fixtures as production event_workspace truth.
  - Parse EDGAR `-index-headers.html` without html.unescape.
  - Re-read the closed v1 score overlay for the E2 glance.
  - Broaden E2 into E3+, slides, Q&A ML, or a second publisher.
  - Reopen Terminal E2-T1 product, Results taxonomy, receipt copy, or #420 CSS ownership.
landmines:
  - v1 CI requires claim_citations_pending == true; do not flip the v1 invariant.
  - public_wire completeness is forced transcript-only; changing it is a contract change.
  - Calendar freshness can look green on the newest stamp while coverage is 17.9%.
  - LMND Wire Q2 vs CI Q1 proves "generated_at today" is not "latest event current".
waves:
  - id: E0
    title: Freeze archaeology, ownership, golden universe, experience, E1/E2 contracts
    status: done
    next_action: Frozen; do not reopen unless the contract itself is superseded.
  - id: E1
    title: Canonical truth convergence for AAPL FY2026 Q3
    status: done
    depends_on: [E0]
    pr: 5817
    next_action: Implementation accepted; production object is E1P, not a second E1.
  - id: E1P
    title: Production activation of the AAPL FY2026 Q3 event_workspace nest
    status: done
    depends_on: [E1]
    pr: 5841
    next_action: Live on generation f709a0a6ec514282d5769e7d; E2 is unblocked.
  - id: E2
    title: Golden Event Workspace in existing Terminal + dossier
    status: in_progress
    depends_on: [E1P]
    next_action: E2-T1 is live on Terminal #418 / abf87195c7ea; remaining slice is E2-D dossier glance.
  - id: E2-D
    title: Macro dossier glance from the live AAPL FY2026 Q3 workspace
    status: todo
    depends_on: [E2]
    next_action: >
      Render event_workspace.v1 generation f709a0a6ec514282d5769e7d on the
      existing Macro dossier Company Intelligence block. Same event_id as
      Terminal Brief. Do not re-read v1 overlay. Do not reopen E2-T1.
---

E0 is research/design only. E1/E2 are the first vertical slice. Later waves E3–E15 live in the V2 masterplan and are out of this workstream's immediate next_action.
