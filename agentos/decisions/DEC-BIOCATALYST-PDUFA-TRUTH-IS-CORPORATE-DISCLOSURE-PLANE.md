---
key: BIOCATALYST-PDUFA-TRUTH-IS-CORPORATE-DISCLOSURE-PLANE
question: >
  Which plane owns prospective PDUFA date truth, and by which route may
  BioCatalyst ever consume it — given that pdufa_date is a forbidden claim on
  Drugs@FDA (RECON-0 law), SEC ingest is unavailable_to_biocatalyst by source
  registry law, and the BPC JV snapshots carry capture-time PDUFA fields?
answer: >
  SOL RULING (P1-0R, 2026-08-20). Prospective PDUFA date truth is owned by
  the Corporate/Company Intelligence disclosure plane. The canonical future
  route is: issuer IR / SEC / issuer disclosure → Company Intelligence
  evidence/event plane → bounded BioCatalyst consumer port. BioCatalyst may
  not duplicate SEC/IR ingest. Drugs@FDA is retrospective regulatory
  application/action/outcome truth and may not be used to manufacture
  prospective PDUFA dates. Post-soak BPC JV data may serve only as correctly
  timestamped capture-time seed/reconciliation evidence, never retroactive
  PIT truth. No implementation is authorized by this record.
rationale: >
  Every lawful fact points the same direction: forward PDUFA dates are
  issuer-controlled disclosures (8-K/PR/IR), not registry or FDA-database
  facts. The RECON-0 freeze already marks pdufa_date a forbidden claim on
  Drugs@FDA because the database records applications and actions after the
  fact; the source registry already marks SEC ingest owned_by_corporate_plane
  / unavailable_to_biocatalyst; and DNR law already prohibits duplicate SEC
  ingest inside biocatalyst (direct_duplicate_sec_ingest). Freezing the
  ownership now prevents the two failure modes P1-0 identified: (a) a future
  BioCatalyst wave quietly minting its own issuer-disclosure scraper to
  unblock the PDUFA tenant, and (b) JV snapshot PDUFA fields being backjoined
  as if they were historical PIT truth (DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT
  establishes there is no historical PIT plane to fake it with). The bounded
  consumer port keeps the catalyst-event spine's second tenant honest: the
  PDUFA lane starts when the Company Intelligence evidence/event contract
  exists, not when someone finds a shortcut.
alternatives:
  - option: BioCatalyst builds its own issuer IR / SEC PDUFA ingest
    why_not: >
      Duplicates the corporate plane's ingest (standing DNR
      direct_duplicate_sec_ingest prohibition), fragments disclosure truth
      across planes, and violates the source registry's
      owned_by_corporate_plane assignment.
  - option: Derive prospective PDUFA from Drugs@FDA submission records
    why_not: >
      Drugs@FDA is retrospective application/action/outcome truth; inferring
      forward action dates from it manufactures a claim the source does not
      carry — exactly the forbidden-claim shape RECON-0 froze.
  - option: Promote post-soak BPC JV snapshot PDUFA fields to PIT truth
    why_not: >
      The snapshots are finite capture-time observations
      (DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN); treating capture-time
      values as known-at-event-time history fabricates PIT. Seed and
      reconciliation evidence from actual capture timestamps onward is the
      full lawful extent.
evidence:
  - "Sol P1-0R authority-closure directive, 2026-08-20 §3"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md — pdufa_date forbidden claim on Drugs@FDA; forward PDUFA = issuer-disclosure truth"
  - "config/biocatalyst_sources.yml:221-222 drugs_at_fda production_ingest_allowed false; :267-271 SEC owned_by_corporate_plane / unavailable_to_biocatalyst"
  - "research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md §11.3 (question as returned to Sol)"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
affects:
  - "biocatalyst"
  - "WS:BIOCATALYST-CORE-PRODUCT"
  - "WS:BPC-JV-RECON"
  - "engine/biocatalyst/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Grounds

This closes §11.3 of the P1-0 recharter. The Regulatory/PDUFA lane remains
the catalyst-event spine's designed second tenant; this record defines the
only door it may enter through. When the Company Intelligence evidence/event
plane exposes issuer-disclosure PDUFA events, BioCatalyst consumes them
through a bounded port with the disclosure plane's provenance intact — it
does not re-derive, re-scrape, or re-time them.

## What would reopen this

A Sol/Chairman ruling relocating disclosure-plane ownership itself, or a
rights/architecture change making the Company Intelligence plane permanently
unable to carry issuer-disclosure events (which would need a new adjudication,
not a BioCatalyst workaround).
