---
key: BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE
question: >
  Should PDUFA, device, conference, and IPO catalyst events reuse fiscal
  event_workspace.v1 identifiers (evt_cik…_{year}fy_action), or compose with
  company_event.v1 without inheriting the earnings workspace keys? Is
  ticker + date + drug/device canonical event identity?
answer: >
  Accepted. Compose with company_identity.v1 and company_event.v1
  lifecycle / publication clocks (observed_at, source_available_at). Do not
  reuse fiscal event_workspace.v1 ids or earnings payload keys for catalysts.
  Canonical events must prefer source-native IDs (NCT, Drugs@FDA ApplNo, CDRH
  510(k)/PMA, SEC accession, Nasdaq IPO deal id) and the existing owner event
  plane. ticker + date + drug/device is jv_reconciliation_match_key, never
  canonical event identity. A later PR may extend EVENT_TYPES and generalize
  canonical_event_id under Sol review.
rationale: >
  canonical_event_id requires a fiscal period (events.py EVENT_TYPES and
  _EVENT_ID_RE). event_workspace.v1 is an earnings payload (fiscal_period,
  facts/deltas/guidance/claims) with live universe AAPL FY2026 Q3 only and
  claim_citations_pending must stay True. Stuffing a PDUFA date into
  evt_…_fy_action would either lie about fiscal period or fork a silent second
  semantics onto the same id function. Sharing identity and lifecycle is the
  composition the operator asked for; sharing the earnings id is not. Using the
  JV triple as a canonical id would mint Mastermind events from a snapshot
  join key. Sol accepted this ruling on 2026-08-19 (PR #5909).
alternatives:
  - option: Reuse evt_cik{10}_{year}fy_action for all non-earnings catalysts
    why_not: >
      The id parser returns a FiscalPeriod. PDUFA/device/conference dates are not
      fiscal periods. Colliding with corporate_action earnings-year events is
      guaranteed.
  - option: Treat ticker + date + drug/device as canonical event identity
    why_not: >
      That triple is a reconciliation key against the JV snapshot. Canonical
      events must prefer source-native IDs and the owner event plane. Minting
      evt_… from the triple would bake a licensed-snapshot join into identity.
  - option: Invent a parallel catalyst_event.v1 bus now
    why_not: >
      Duplicate owner plane. The freeze's composition rule is to extend the
      existing event type table later, not to stand up a second bus in RECON-0.
  - option: Put catalysts inside event_workspace.v1
    why_not: >
      Workspace keys are earnings-shaped. claim_citations_pending, prophet_flags,
      and the AAPL-only live universe would all be inherited incorrectly.
evidence:
  - "engine/company_intelligence/events.py:93-102 EVENT_TYPES and _EVENT_ID_RE"
  - "engine/company_intelligence/event_workspace.py claim_citations_pending must be derived bool"
  - "engine/company_intelligence/contracts.py event_map claim_citations_pending is not True fails"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §7"
  - "PR #5909 Sol REQUEST CHANGES 2026-08-19 jv_reconciliation_match_key"
  - "PR #5909 Sol FINAL ACCEPTANCE 2026-08-19"
affects:
  - "WS:BPC-JV-RECON"
  - "WS:EARNINGS-INTELLIGENCE-OS"
  - "biocatalyst"
  - "engine/company_intelligence/events.py"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

The operator required composition with event_workspace.v1 rather than a second
event system. The load-bearing read is that the *workspace* is earnings-specific
while the *event envelope* (identity, lifecycle, publication clocks) is the
shareable layer. Composition happens at the envelope, not at the fiscal id.
The JV triple is a matcher key only. This record is Sol-accepted architecture
(`decided_by: ceo-sol`).

## What would reopen this

A later PR that actually extends EVENT_TYPES with catalyst tokens and a
non-fiscal id function, reviewed as its own decision. That extension is allowed;
reusing fy_action without it is not, and promoting jv_reconciliation_match_key
to canonical identity is not.
