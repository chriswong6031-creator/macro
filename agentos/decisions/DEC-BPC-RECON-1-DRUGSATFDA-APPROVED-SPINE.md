---
key: BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE
question: >
  Is a hermetic Drugs@FDA matcher against JV Historical FDA Approved rows the
  program-completion vertical, and is CI replay of a pinned ZIP production proof?
answer: >
  Accepted. No. A hermetic Drugs@FDA matcher may remain a recommended
  calibration / reconstruction component inside continuous source reconstruction.
  It is not "done for the program." CI replay of a pinned ZIP is not production
  proof and must not be described as an independently useful completed production
  vertical. Program completion means (1) the licensed snapshot corpus is onboarded
  and useful, (2) independent source producers can continuously regenerate the
  targeted data families, (3) owner-plane projections are wired to website/machine
  consumers, and (4) research can use the data under PIT rules. A future
  real-input → real-consumer proof is specified in freeze §11. Do not start this
  matcher, device/CDRH, PDUFA NLP, or snapshot ingestion from PR #5909.
rationale: >
  The Drugs@FDA collector is already fully implemented and dark, so a hermetic
  matcher is a cheap calibration component. Treating that component as program
  completion, or treating the unit-test ZIP as production proof, was the freeze
  defect Sol rejected. Live ZIP ingest stays blocked until a separate rights
  advance. Soak untouched. No new model. No PDUFA dates from this collector.
  Sol accepted this ruling on 2026-08-19 (PR #5909).
alternatives:
  - option: Treat hermetic ZIP replay as the completed first production vertical
    why_not: >
      CI replay of a pinned fixture is calibration. It does not prove real source
      input reaching a real website or machine consumer.
  - option: Commission RECON-1 immediately after this freeze merges
    why_not: >
      Sol instructed STOP. Do not start RECON-1, device/CDRH, PDUFA NLP, or
      snapshot ingestion from this PR. The next concepts are licensed snapshot
      onboarding and continuous source reconstruction, not a matcher-only wave.
  - option: Forward PDUFA 8-K NLP or device/CDRH as this PR's implementation
    why_not: >
      Out of this PR. Architecture sequencing lives in freeze §10; it is not
      authorization to implement those waves here.
evidence:
  - "config/biocatalyst_sources.yml drugs_at_fda producer collectors.biocatalyst.drugs_at_fda, production_ingest_allowed false, prohibited_claims includes pdufa_date"
  - "engine/biocatalyst/regulatory.py fda_application_dossier.v1 coverage_note: not pending/PDUFA/IND/CRL completeness"
  - "collectors/biocatalyst/ has clinicaltrials_* and drugs_at_fda.py; no openfda_regulatory.py"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §10–§11"
  - "PR #5909 Sol REQUEST CHANGES 2026-08-19"
  - "PR #5909 Sol FINAL ACCEPTANCE 2026-08-19"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "collectors/biocatalyst/drugs_at_fda.py"
  - "engine/biocatalyst/regulatory.py"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

RECON-0's job is the reconstruction spec, not a production vertical. Drugs@FDA
remains the best calibration component because the producer and contract already
exist and the JV Historical FDA CSV contains a matchable Approved+date fact after
unshift. That does not make ZIP replay a live proof, and it does not complete
the program. This record is Sol-accepted architecture (`decided_by: ceo-sol`).

## What would reopen this

Sol rejecting the calibration-component demotion, advancing drugs_at_fda
rights_state for live ZIP ingest, or commissioning snapshot onboarding as the
next implementation PR (expected) rather than the matcher.
