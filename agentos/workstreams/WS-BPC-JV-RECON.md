---
key: BPC-JV-RECON
title: BioPharmCatalyst JV snapshot reconstruction (independent primary sources)
objective: >
  Turn the authorized 2026-08-17 BPC snapshots into a complete spec for independently
  rebuilding every reconstructable dataset from Mastermind-owned primary sources.
  Done for RECON-0 = freeze merged after Sol review. Done for the program = RECON-1
  (Drugs@FDA approved-event reconstruction ledger) ships hermetic producer→evidence→
  fact→matcher→context consumer without touching the CT.gov soak or committing BPC rows.
status: awaiting_review
program: biocatalyst
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
waves:
  - id: RECON-0
    title: JV snapshot archaeology + source-system reconstruction freeze
    status: awaiting_ci
    pr: 5909
    next_action: Sol reviews PR #5909; on PASS, commission RECON-1 only. Do not merge-on-green.
  - id: RECON-1
    title: Drugs@FDA approved-event reconstruction ledger (hermetic)
    status: todo
    depends_on: [RECON-0]
    next_action: Do not start until Sol PASS on RECON-0; then execute freeze §11.
needs_ceo:
  question: >
    Approve RECON-1 (hermetic Drugs@FDA approved-event spine vs JV Historical FDA
    clean Approved rows; rights stay dark; soak untouched) as the first vertical,
    versus starting with device/CDRH or issuer-disclosed PDUFA NLP instead?
  options:
    - RECON-1 as specified in freeze §11 (recommended)
    - Device/CDRH pack first
    - Forward PDUFA 8-K NLP first
    - Hold all implementation
  recommendation: RECON-1 as specified in freeze §11
  by_when: 2026-08-22
owns_paths:
  - research/BPC_RECON_0_*
  - agentos/workstreams/WS-BPC-JV-RECON.md
  - agentos/handoffs/BPC-JV-RECON-*
landmines:
  - >-
    Do not modify the running CT.gov record-history canary (b2_history_canary /
    BIOCATALYST_HISTORY_ENABLED / four-NCT allowlist) or the soak window
    2026-08-12T02:00:00Z→2026-08-26T02:00:00Z.
  - >-
    Occupied checkouts may hold unauthorized scraped_*.json BPC artifacts — not
    evidence; do not census, commit, or cite them.
  - >-
    biopharmcatalyst_benchmark is historical clean-room policy; never silently
    rewrite it. JV seeds are a distinct source id.
  - >-
    Export-time Price/IV/OI/EM/mcap must never join onto historical event rows
    as pre-event features.
decisions:
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-OPENFDA-PRODUCER-IS-STUB"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
do_not_redo:
  - >-
    Do not re-hash the 2026-08-17 authorized dump; SHA256 values are in freeze §1
    and were re-verified 2026-08-18.
  - >-
    Do not re-count the Historical FDA 28.1% left-shift (4404/15700).
  - >-
    Do not propose stuffing PDUFA/device into evt_cik…_fy_action fiscal ids.
  - >-
    Do not treat collectors.biocatalyst.openfda_regulatory as implemented.
  - >-
    Do not treat Market Memory W1A as a historical PIT price source for past catalysts.
  - >-
    Do not duplicate SEC ingest inside biocatalyst (direct_duplicate_sec_ingest).
next_action: Sol review of PR #5909; on PASS, commission RECON-1 per freeze §11. Do not merge-on-green.
artifacts:
  - research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
  - config/biocatalyst_sources.yml
---

## Context

RECON-0 (2026-08-18) inventoried the authorized BPC dump (one xlsx / nine sheets plus
four CSVs), classified every column onto event-clock vs export-time vs editorial/model,
mapped each field to an existing Mastermind owner or to NONE, and froze exactly one
first vertical. Sibling soak worktrees own the live CT.gov path; this workstream owns
the reconstruction spec and the later hermetic Drugs@FDA matcher only.
