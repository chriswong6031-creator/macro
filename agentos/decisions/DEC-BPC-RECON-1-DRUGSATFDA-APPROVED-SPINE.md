---
key: BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE
question: >
  Which single first vertical should follow the RECON-0 freeze — Drugs@FDA
  approved-event reconstruction, device/CDRH, forward PDUFA NLP, IPO filter,
  or conference calendar?
answer: >
  RECON-1 = hermetic Drugs@FDA approved-event reconstruction ledger against JV
  Historical FDA clean Approved rows after unshift. Live ZIP ingest stays blocked.
  Soak untouched. No new model. No PDUFA dates from this collector.
rationale: >
  The Drugs@FDA collector is already fully implemented and dark
  (rights_state review_required_before_b4). regulatory.py already emits
  fda_regulatory_event.v1 / fda_application_dossier.v1 over an approved-product
  corpus. The JV Historical FDA CSV is the only snapshot where a primary FDA
  source can honestly reproduce a dated event (Approved + date) after repairing
  the 28.1% left-shift. Every alternative fails a different gate: PDUFA has no
  official calendar and pdufa_date is a forbidden collector claim; device has
  no producer and no applicant→issuer join; conference is net-new; IPO is
  already live (filter only, not a first vertical); earnings collides with
  WS:EARNINGS-INTELLIGENCE-OS.
alternatives:
  - option: Forward PDUFA 8-K NLP as first vertical
    why_not: >
      Source hole (teardown §12.3). Forbidden on Drugs@FDA. Would require a new
      corporate-plane consumer and an NLP stack. Wrong first proof.
  - option: Device/CDRH pack first
    why_not: >
      Producer does not exist; openFDA biocatalyst producer is a stub; device
      applicant→issuer identity is unbuilt. Larger than a reconstruction ledger.
  - option: IPO biopharma filter first
    why_not: >
      Highest existing coverage, but it does not prove the reconstruction-ledger
      pattern the JV dump exists to drive. Do it as backlog item 2, not the
      first vertical.
  - option: LoA/LoP model recreation
    why_not: >
      MODEL_RECREATED. Operator forbade a new model in RECON-0.
evidence:
  - "config/biocatalyst_sources.yml drugs_at_fda producer collectors.biocatalyst.drugs_at_fda, production_ingest_allowed false, prohibited_claims includes pdufa_date"
  - "engine/biocatalyst/regulatory.py fda_application_dossier.v1 coverage_note: not pending/PDUFA/IND/CRL completeness"
  - "collectors/biocatalyst/ has clinicaltrials_* and drugs_at_fda.py; no openfda_regulatory.py"
  - "research/BIOCATALYST_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md: there is no official complete forward PDUFA calendar"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §11"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "collectors/biocatalyst/drugs_at_fda.py"
  - "engine/biocatalyst/regulatory.py"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-08-22
---

## Grounds

RECON-0's job was to pick exactly one first vertical that is a real producer →
evidence → fact → consumer path. Drugs@FDA is the only path where the producer
and the contract already exist and the JV seed contains a matchable primary
fact. Sol review can still pick a different vertical; this decision is the
recommendation on the freeze, not a rights unlock.

## What would reopen this

Sol choosing device/CDRH or PDUFA NLP on the needs_ceo question, or a rights
review that still leaves Drugs@FDA dark *and* forbids even hermetic fixture
replay (not the current rights_state — replay is already how the collector is
tested).
