---
key: BPC-JV-RECON
title: BioPharmCatalyst JV snapshot reconstruction (independent primary sources)
objective: >
  Turn the authorized 2026-08-17 BPC snapshots into a reconstruction spec, then
  later onboard the licensed corpus and independently rebuild reconstructable
  families from Mastermind-owned primary sources. RECON-0 is done: freeze
  architecture accepted by Sol and PR #5909 merged 2026-08-19T19:51:49Z as
  9711c60d3067f1908a7822008ffd7a8b23171854.
  Done for the program = (1) licensed snapshot corpus onboarded and useful,
  (2) independent producers can continuously regenerate the targeted data
  families, (3) owner-plane projections wired to website/machine consumers,
  (4) research can use the data under PIT rules. RECON-1 hermetic Drugs@FDA ZIP
  replay is not program completion.
status: active
program: biocatalyst
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
waves:
  - id: RECON-0
    title: JV snapshot archaeology + source-system reconstruction freeze
    status: done
    pr: 5909
    next_action: >
      Done. #5909 merged 2026-08-19T19:51:49Z as 9711c60d3067. Do not start
      SNAPSHOT-ONBOARD from that PR; commissioning is a separate Sol act.
  - id: SNAPSHOT-ONBOARD
    title: Licensed snapshot corpus onboarding — bounded Historical Event History vertical
    status: in_progress
    pr: 6389
    depends_on: [RECON-0]
    next_action: >
      SNAPSHOT-ONBOARD A is commissioned by Macro issue #6374 and implemented in
      HOLD-FOR-SOL PR #6389. Sol reviews the exact held head.
      Only an explicit Sol release may merge it, publish the private R2 snapshot,
      deploy the public projection, and begin real entitled production acceptance.
      This bounded vertical grants no CONTINUOUS-RECON, source-registry, cohort,
      cadence, or successor-wave authority.
  - id: CONTINUOUS-RECON
    title: Continuous source reconstruction
    status: todo
    depends_on: [RECON-0]
    next_action: >
      Remains todo; #5909 is merged but grants no start authority. Independent
      producers, consumer wiring, PIT research; Drugs@FDA matcher is a
      calibration component, not this wave's proof. Runtime source registration
      stays post-soak successor-registry gated.
  - id: RECON-1
    title: Drugs@FDA hermetic matcher (recast — calibration component, not program-done)
    status: dropped
    depends_on: [RECON-0]
    next_action: Recast into CONTINUOUS-RECON. Do not start from this PR. CI ZIP replay is not production proof.
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
    The active launch SLO manifest is soak_scheduled and hash-binds
    predecessor config/biocatalyst_sources.yml. Do not insert
    biopharmcatalyst_jv_snapshot into that live registry, re-hash the
    manifest, or add machine-enforced JV source-registry tests during soak
    (DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK).
  - >-
    DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK is a local-environment
    statement only. Do not promote it into a global lost/unrecovered claim.
decisions:
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
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
    The Chairman identified the nine-sheet W4 workbook as the canonical/latest
    complete export for SNAPSHOT-ONBOARD A. W2/W3 are archaeology only and W1 is
    not required. Parenthetical upload collision suffixes are not version or
    capture chronology. Do not reopen a W1–W4 admission dependency in this wave.
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
    Do not expand SNAPSHOT-ONBOARD A into CONTINUOUS-RECON, RECON-1, live
    device/CDRH collection, PDUFA NLP, or any continuous BPC ingestion.
  - >-
    Do not mutate the soak-bound predecessor source registry or add
    machine-enforced JV source-registry tests during the active soak. Runtime
    registration waits for the post-soak successor registry / successor
    launch-manifest transition.
next_action: >
  Sol reviews the exact HOLD-FOR-SOL head of PR #6389 for commissioned
  SNAPSHOT-ONBOARD A.
  Only explicit Sol approval releases the same lane to merge, publish the
  private R2 snapshot, deploy its pointer-bound public projection, and run real
  entitled production acceptance. Runtime biopharmcatalyst_jv_snapshot registry
  insertion, CONTINUOUS-RECON, cohort/cadence expansion, and successor waves are
  not commissioned.
artifacts:
  - research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
  - research/BIOCATALYST_SNAPSHOT_ONBOARD_A_CORPUS_AND_CONTRACT_FREEZE_2026-08-24.md
  - agentos/handoffs/BPC-JV-RECON-2026-08-24-SNAPSHOT-ONBOARD-A.md
---

## Context

RECON-0 is Sol-accepted architecture, merged 2026-08-19 (PR #5909, squash
`9711c60d3067f1908a7822008ffd7a8b23171854`). Canonical identity
`biopharmcatalyst_jv_snapshot` is frozen; the live source registry remains
untouched. Macro issue #6374 separately commissioned SNAPSHOT-ONBOARD A: the
Chairman-authorized W4 nine-sheet workbook plus four CSVs become a finite,
private R2 snapshot and a pointer-bound public Historical Event History
projection. That implementation is in a HOLD-FOR-SOL delivery lane and is not
merged, deployed, or production accepted. CONTINUOUS-RECON remains todo and
uncommissioned; matcher-only RECON-1 stays dropped.
