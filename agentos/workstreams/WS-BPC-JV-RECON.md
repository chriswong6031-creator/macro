---
key: BPC-JV-RECON
title: BioPharmCatalyst JV snapshot reconstruction (independent primary sources)
objective: >
  Turn the authorized 2026-08-17 BPC snapshots into a reconstruction spec, then
  later onboard the licensed corpus and independently rebuild reconstructable
  families from Mastermind-owned primary sources. Done for RECON-0 = freeze
  merged after Sol acceptance of architecture plus the corpus-state correction.
  Done for the program = (1) licensed snapshot corpus onboarded and useful,
  (2) independent producers can continuously regenerate the targeted data
  families, (3) owner-plane projections wired to website/machine consumers,
  (4) research can use the data under PIT rules. RECON-1 hermetic Drugs@FDA ZIP
  replay is not program completion.
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
    next_action: Sol reviews the corpus-state correction on PR #5909; do not merge-on-green; do not start implementation.
  - id: SNAPSHOT-ONBOARD
    title: Licensed snapshot corpus onboarding
    status: todo
    depends_on: [RECON-0]
    next_action: >
      Do not start from PR #5909. After Sol PASS, when W1–W4 bytes are in the
      implementation environment, census each workbook (SHA-256 → ordered sheet
      set → dimensions → content hashes → pair class
      ADDITIVE_SHEET_EXPORT_IDENTICAL_COMMON_CONTENT |
      COMMON_SHEET_CONTENT_CHANGED | DISTINCT_CAPTURE | UNRESOLVED). Do not
      invent predecessor SHA-256 from File Library metadata. Preserve unique
      predecessor rows if found.
  - id: CONTINUOUS-RECON
    title: Continuous source reconstruction
    status: todo
    depends_on: [RECON-0]
    next_action: Do not start from PR #5909. Independent producers, consumer wiring, PIT research; Drugs@FDA matcher is a calibration component, not this wave's proof.
  - id: RECON-1
    title: Drugs@FDA hermetic matcher (recast — calibration component, not program-done)
    status: dropped
    depends_on: [RECON-0]
    next_action: Recast into CONTINUOUS-RECON. Do not start from this PR. CI ZIP replay is not production proof.
needs_ceo:
  question: >
    Accept the remaining corpus-state correction on PR #5909 — local operator
    state is W4 bytes only; global corpus state is W1/W2/W3/W4 exist in the
    Chairman's File Library; relationship is
    UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS; W1→W4 are not four temporal
    vintages unless a later census proves time-varying common-sheet content?
    Architecture (rights, completion law, two-track roadmap, poison rules,
    reconciliation key, source-owner map, authority) is already accepted.
  options:
    - Accept freeze with this corpus-state correction (recommended)
    - Request further corpus-state wording
    - Hold
  recommendation: Accept freeze with this corpus-state correction (recommended)
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
    rewrite it. JV snapshots are a distinct source id with finite-snapshot
    rights, not a continuous BPC feed.
  - >-
    Export-time Price/IV/OI/EM/mcap must never join onto historical event rows
    as pre-event features. They may be used as capture-time observations from
    their actual capture timestamp onward.
  - >-
    production_ingest_allowed is the continuous-producer gate. Do not flip it
    true to "allow snapshot import."
  - >-
    DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK is a local-environment
    statement only. Do not promote it into a global lost/unrecovered claim.
decisions:
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-OPENFDA-PRODUCER-IS-STUB"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
  - "DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK"
do_not_redo:
  - >-
    Do not re-hash the locally verified W4 workbook and four CSVs; SHA256
    values are in freeze §1.
  - >-
    Do not re-count the Historical FDA 28.1% left-shift (4404/15700).
  - >-
    Do not call W4 a proven superset of W1–W3, and do not call W1–W3 lost.
    Relationship is UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS. The open
    question is whether W4 is a superset of W1–W3 with identical common-sheet
    content.
  - >-
    Do not treat W1→W4 as four temporal vintages or as evidence of BPC row
    revisions unless a later census proves time-varying common-sheet content.
  - >-
    Do not invent predecessor SHA-256 values from File Library metadata.
  - >-
    Do not propose stuffing PDUFA/device into evt_cik…_fy_action fiscal ids,
    or using ticker+date+drug as canonical event identity.
  - >-
    Do not treat collectors.biocatalyst.openfda_regulatory as implemented.
  - >-
    Do not treat Market Memory W1A as a historical PIT price source for past catalysts.
  - >-
    Do not duplicate SEC ingest inside biocatalyst (direct_duplicate_sec_ingest).
  - >-
    Do not describe CI ZIP replay as production proof.
  - >-
    Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH,
    PDUFA NLP, or snapshot ingestion from PR #5909.
next_action: >
  Sol review of the corpus-state correction on PR #5909. Do not start
  SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or
  snapshot ingestion. Do not merge-on-green.
artifacts:
  - research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
  - config/biocatalyst_sources.yml
---

## Context

RECON-0 inventoried the authorized BPC dump. Sol accepted the archaeology,
poison list, owner-plane census, Historical FDA left-shift, options/W1A ruling,
event-plane composition direction, source-reconstruction map, rights
architecture, completion law, two-track roadmap, and authority boundaries.
Sol's remaining correction (2026-08-19): local operator absence of W1–W3 bytes
must not be promoted into a global unrecovered claim. All four Excel captures
exist in the Chairman's File Library. Relationship remains
`UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`. Sibling soak worktrees own the
live CT.gov path. This workstream does not start SNAPSHOT-ONBOARD or
CONTINUOUS-RECON from #5909.
