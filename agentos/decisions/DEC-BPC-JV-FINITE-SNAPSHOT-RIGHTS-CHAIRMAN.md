---
key: BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN
question: >
  What may Mastermind do with the Chairman-supplied BioPharmCatalyst datasets,
  and what remains forbidden?
answer: >
  Chairman-confirmed. The supplied BPC datasets are authorized for Mastermind
  storage/use, website/product incorporation, repository incorporation, and
  research / pattern / signal-development programs. Mastermind does not receive
  continuing BPC API access. Continuous BPC API and authenticated BPC scraping
  remain prohibited. Export-time fields remain forbidden as historical pre-event
  features; they may be used as correctly time-stamped snapshot observations in
  research from their actual capture time onward. Research permission is not
  Prophet or trade authority. Keep a distinct biopharmcatalyst_jv_snapshot
  identity with finite-snapshot rights separate from continuous-feed rights.
  production_ingest_allowed stays false because that field is the continuous
  producer gate.
rationale: >
  Direct Chairman confirmation recorded in the 2026-08-19 Sol REQUEST CHANGES
  on PR #5909. The withdrawn matching-only / operator-held-never-git / public
  projection blocked / model research blocked reading misstated those rights.
  Encoding finite-snapshot capabilities as their own block, without flipping
  production_ingest_allowed, keeps the continuous-producer gate honest.
alternatives:
  - option: Matching-only operator-held seed; never git; public projection blocked
    why_not: >
      Chairman confirmed storage, product incorporation, repository
      incorporation, and research use. That reading is the rejected freeze.
  - option: Flip production_ingest_allowed true so snapshot import can run
    why_not: >
      That field already means a continuous live producer
      (scripts/biocatalyst_worker.py). Silently widening it would authorize a
      BPC API/scrape feed this partnership does not grant.
  - option: Treat research permission as Prophet / trade authority
    why_not: >
      Chairman authorized research and pattern/signal development, not a
      promotion of snapshot-derived facts to Prophet or trade authority.
      biocatalyst remains context_only.
evidence:
  - "Sol REQUEST CHANGES on PR #5909, 2026-08-19, recording Chairman confirmation of JV dataset rights"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §2 — finite-snapshot rights frozen; runtime registry insertion deferred"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "config/biocatalyst_sources.yml"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-19
---

## Grounds

Partnership design withholds a continuing BPC API. The supplied finite snapshots
are a licensed corpus, not a scrape target and not a clean-room-only matching
seed. Product and research use are in-rights; live BPC collection is not.

## What would reopen this

A later Chairman instruction that withdraws product/repo/research use, or that
grants continuing BPC API access. A Sol promotion of snapshot-derived facts to
Prophet authority would be a separate decision, not a reread of this one.
