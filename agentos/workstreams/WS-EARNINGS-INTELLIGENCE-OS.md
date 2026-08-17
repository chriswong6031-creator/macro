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
  Heal the HTML-escaped SGML parser, redispatch company-intelligence.yml on
  main, prove GET event_workspaces/manifest.json is 200 and
  read_event_workspace returns available:true on all four AAPL aliases, then
  stop. Do not start E2.
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
do_not_redo:
  - Rebuild Terminal transcripts, Stage, Group Reads, TIL, or a standalone earnings app.
  - Treat Earnings Wire excerpt archive as the finished intelligence product.
  - Listing-key dual-class events (GOOG/GOOGL) as two issuers.
  - Treat a production-shaped reader test as proof the R2 object exists.
  - Publish E1 test fixtures as production event_workspace truth.
  - Start E2 before GET company_intelligence/event_workspaces/manifest.json is 200.
  - Parse EDGAR `-index-headers.html` without html.unescape.
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
    status: in_progress
    depends_on: [E1]
    next_action: Unescape EDGAR index-headers.html, redispatch company-intelligence.yml, prove the public reader.
  - id: E2
    title: Golden Event Workspace in existing Terminal + dossier
    status: todo
    depends_on: [E1P]
    next_action: Execute research/earnings_intelligence/E2_IMPLEMENTATION_HANDOFF.md only after E1P live proof.
---

E0 is research/design only. E1/E2 are the first vertical slice. Later waves E3–E15 live in the V2 masterplan and are out of this workstream's immediate next_action.
