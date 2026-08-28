---
key: ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL
question: >
  Does Earnings Intelligence OS's ownership of "event, document, claim, and
  earnings product truth" (DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP) extend to
  China A-share issuers, or is a separate China corporate-event truth
  (china_corporate_event.v1) permitted? The ownership DEC is venue-silent;
  company_event.v1 identity is CIK-only today (engine/company_intelligence/
  identity.py:40,50-58), so no A-share issuer can currently mint an event; and
  CN-G0 (PR #5943) found China already holds the vintage tapes (业绩预告/业绩快报,
  CNInfo inquiry/reply, 互动易/上证e互动, sell-side tape, cn_special_sits) but no
  canonical_event_id join. CN-G0's GQ7 routed the question to the FABLE-00 seat.
answer: >
  Venue-neutral. Earnings OS owns issuer event truth for ALL venues; the CIK lock
  is an identity-plane implementation limit, never an ownership boundary. Do not
  mint china_corporate_event.v1 and do not stand up an independent G lane. CN
  issuer admission is ONE later Earnings-owner E-wave, sequenced after E2 ships
  unchanged, freezing a listing-identity adapter onto the existing
  company_event.v1 / EVENT_STATES contract, referencing (never re-collecting) the
  existing China collectors, and using Stock Identity for listing identity. The
  audited delta is three named sites — company_id_for_cik plus the two
  __post_init__ CIK coercions (identity.py:158; events.py:292) — the security
  layer is already MIC-neutral (identity.py:61-66).
rationale: >
  A venue-scoped second event store is exactly the "second Earnings store" the
  No-Rebuild law forbids, and the estate's correction-stable event identity
  ("never sees a call date, a document hash, or a revision number",
  events.py:11-14) is venue-agnostic by design. CN-G0's own receipts show the
  missing piece is a join key, not a store: every China tape already exists with
  honest vintages. Resolving the ownership DEC's venue silence toward one
  issuer-keyed truth store keeps post-event reinterpretation one product family
  across US and CN instead of two divergent contracts.
alternatives:
  - option: Mint china_corporate_event.v1 as a China-owned event contract
    why_not: >
      Second Earnings store (No-Rebuild law); forks EVENT_STATES semantics and
      every downstream consumer; CN-G0's own verdict argues against it.
  - option: Leave the venue question open until a China build forces it
    why_not: >
      The silence is precisely what lets a parallel lane mint a duplicate store
      in good faith — the China Alpha program is actively commissioning around
      this seam today (#5953). An explicit ruling is cheap now and expensive
      to retrofit after a second contract exists.
  - option: Rule Earnings ownership US-only and give China events to the China
      Alpha program
    why_not: >
      Splits one product truth by venue, duplicates the event lifecycle,
      contradicts the ownership DEC's unqualified grant, and makes the
      dual-listed/ADR case (one issuer, two venues) structurally incoherent.
evidence:
  - "Ownership grant, venue-silent: agentos/decisions/DEC-EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP.md:7-13"
  - "CIK lock sites: engine/company_intelligence/identity.py:40,50-58,158; engine/company_intelligence/events.py:292; MIC-neutral security layer identity.py:61-66"
  - "Correction-stable identity quote: engine/company_intelligence/events.py:11-14"
  - "CN tape receipts (14/14 audit-verified): research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md §3; PR #5943 censuses/CN-G0/"
  - "E2 todo/unblocked: agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md:68-72"
affects:
  - "research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md"
  - "agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md"
  - "agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md"
confidence: high
reversibility: easy
decided_by: FABLE-00 seat, wave c0g
decided_at: 2026-08-19
---

## Grounds

CN-G0's GQ7 explicitly routed the venue question to this seat, flagging its own
Earnings-ownership reading as inference rather than quotation. The seat resolves
the DEC's silence in the only direction compatible with the No-Rebuild law and
the correction-stable identity design. Nothing is built by this ruling: the
adapter wave stays sequenced behind E2 and belongs to the Earnings owner.

## What would reopen this

An Earnings-owner refusal to admit CN issuers at its wave boundary, or a Sol
ruling assigning China event truth elsewhere, returns the question here for
re-adjudication rather than authorizing a parallel store. A demonstrated
technical impossibility of issuer-neutral identity (Stock Identity unable to
bind A-share listings) would also reopen it — that is a falsifier, not a veto.
