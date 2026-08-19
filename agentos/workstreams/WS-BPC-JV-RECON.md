---
key: BPC-JV-RECON
title: BioPharmCatalyst JV snapshot reconstruction (independent primary sources)
objective: >
  Turn the authorized 2026-08-17 BPC snapshots into a reconstruction spec, then
  later onboard the licensed corpus and independently rebuild reconstructable
  families from Mastermind-owned primary sources. Done for RECON-0 = freeze
  architecture accepted by Sol; complete pending merge of PR #5909.
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
    next_action: Architecture accepted; complete pending merge of PR #5909. Do not start SNAPSHOT-ONBOARD from this PR.
  - id: SNAPSHOT-ONBOARD
    title: Licensed snapshot corpus onboarding
    status: todo
    depends_on: [RECON-0]
    next_action: >
      Do not start from PR #5909. After #5909 merges, return to Sol for
      commissioning of the first bounded SNAPSHOT-ONBOARD vertical. When
      commissioned and W1–W4 bytes are in the implementation environment, census
      each workbook (SHA-256 → ordered sheet set → dimensions → content hashes →
      pair class ADDITIVE_SHEET_EXPORT_IDENTICAL_COMMON_CONTENT |
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
  - >-
    Do not mutate the soak-bound predecessor source registry or add
    machine-enforced JV source-registry tests during the active soak. Runtime
    registration waits for the post-soak successor registry / successor
    launch-manifest transition.
next_action: >
  After #5909 merges, return to Sol for commissioning of the first bounded
  SNAPSHOT-ONBOARD vertical. Do not begin it from this PR.
artifacts:
  - research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
---

## Context

RECON-0 is Sol-accepted architecture, soak-safe pending merge of PR #5909.
Canonical identity `biopharmcatalyst_jv_snapshot` is frozen; live registry
insertion is deferred until the post-soak successor source-registry /
successor launch-manifest transition. The program continues (`status: active`).
SNAPSHOT-ONBOARD and CONTINUOUS-RECON remain todo. The matcher-only RECON-1
wave stays dropped. Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON,
Drugs@FDA work, device/CDRH, PDUFA work, or any runtime implementation from
this PR. After merge, return to Sol to commission the first bounded
SNAPSHOT-ONBOARD vertical.
