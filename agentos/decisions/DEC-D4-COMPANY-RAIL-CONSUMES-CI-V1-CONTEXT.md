---
key: D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT
question: >
  D4's owner preflight must classify the IRDM company rail: does a canonical
  Earnings/SEC owner packet or read API exist for IRDM today (case A —
  consume read-only), or only source evidence with no owner packet (case B —
  render unavailable), or nothing usable (case C)? And which owner surface,
  if any, may the GovRev dossier's company rail lawfully consume?
answer: >
  Case A on the v1 context plane, with the richer packet absent. The
  canonical owner's closed per-ticker read API — GET
  /api/company-intelligence/{ticker}, schema company_intelligence_context.v1
  — serves IRDM live (probed 2026-08-20: available:true, generated_at
  2026-08-20T06:52:58Z, latest_event cie_77ff210df9c064c3b2fe4aa1, FY2026 Q1,
  claim_citations_pending:true, authority context_only). D4's company rail
  consumes exactly that API read-only, displays only fields whose
  field_lineage is earnings_history/transcript (score_overlay-lineage fields
  excluded), and fails closed to an explicit "Company packet unavailable"
  state. event_workspace.v1 remains AAPL-only by construction (single
  hardcoded producer scripts/refresh_event_workspaces.py; sole issuer
  builder apple_issuer()); no IRDM event workspace exists and D4 does not
  create or simulate one. Comparison stays not_comparable with null
  denominator/ratio: the v1 context packet structurally asserts no
  issuer-attributed denominator, and the candidate's own materiality block
  records exact_issuer_attributed_denominator_not_available.
rationale: >
  Sol's D4 charter requires consuming the canonical owner rather than
  forking a company-financial store, and requires honest unavailability when
  no owner packet exists. The live probe shows the owner's bounded public
  wire already answers per-ticker for IRDM, and a production surface
  (site/assets/js/company-intelligence-dossier.js) already consumes the same
  endpoint per ticker, so reading it from the GovRev dossier is precedented
  consumption of an owner-governed contract, not a new truth plane. The E2
  arc's ban on re-reading the v1 score overlay is scoped to the E2-D
  earnings glance; D4 additionally excludes score_overlay-lineage fields
  entirely so the bridge never rests on the overlay. The Earnings Wire IRDM
  call-record page is source evidence on a separate pipeline
  (earnings.public_wire_routes/v1) and parsing it from GovRev would make
  GovRev an Earnings builder — refused (case B must not be made case A).
alternatives:
  - option: Classify B and render "Company packet unavailable" despite the live v1 API
    why_not: >
      Factually wrong — an owner-provided IRDM read API exists and answers
      today. Rendering unavailable would hide owner-asserted truth the
      charter explicitly wants beside the government fact.
  - option: Build or trigger an IRDM event_workspace.v1 generation for a richer packet
    why_not: >
      Widens D4 into the earnings owner's producer plane (explicitly
      forbidden: "Do not widen D4 to make case B become case A"); the
      producer is AAPL-only by design and belongs to WS:EARNINGS-INTELLIGENCE-OS.
  - option: Parse site/stocks/earnings/irdm-2026q1-call-record.html for company facts
    why_not: >
      Forbidden by the charter (no Earnings Wire HTML parsing); it would
      make GovRev a second earnings truth store and bypass the owner's
      contract, clocks, and correction discipline.
  - option: Copy the v1 payload into data/government_revenue/ as a build-time artifact
    why_not: >
      Duplicate company-financial dataset under GovRev — explicitly banned;
      it would also freeze the company rail against the owner's restatement
      clock instead of following it.
evidence:
  - "curl GET https://www.mastermind-x.com/api/company-intelligence/IRDM (2026-08-20) → 200, available:true, schema company_intelligence_context.v1, generated_at 2026-08-20T06:52:58Z, latest_event cie_77ff210df9c064c3b2fe4aa1, claim_citations_pending true"
  - "scripts/refresh_event_workspaces.py:1-6,354-365 — AAPL-only producer (apple_registry, FLAGSHIP_EVENT_ID guard)"
  - "engine/company_intelligence/event_workspace.py:137-158 — apple_issuer() is the only issuer builder; no IRDM registry"
  - "app/company_intelligence.py:304 — GET /api/company-intelligence/{ticker}; safe_ticker has no per-ticker allowlist"
  - "site/assets/js/company-intelligence-dossier.js:459 — existing production consumption of the same endpoint per ticker"
  - "data/government_revenue/candidate_queue.json IRDM candidate materiality: comparison_state not_comparable, reason_code exact_issuer_attributed_denominator_not_available, issuer_attributed_denominator null, materiality_ratio null"
  - "research/defense_intelligence/DEFENSE_D4_COMPANY_FINANCIAL_TRUTH_BRIDGE_SPEC.md §1 (frozen preflight record)"
affects:
  - "WS:DEFENSE-PROCUREMENT-V3"
  - government-revenue-foresight
  - templates/government-revenue-dossiers.js
  - templates/government_revenue.html.j2
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
---

## Comparison stays static-closed this wave (review amendment 2026-08-20)

The opus adversarial review caught the first cut fetching the ~434 KiB
candidates artifact per selection to decorate a verdict that is closed by
law. Ruling: the COMPARISON block renders fixed closed-state copy mirroring
the producer's recorded materiality
(exact_issuer_attributed_denominator_not_available); the bridge's only
network read is /api/company-intelligence/{ticker}. Dynamic comparison
state may only arrive together with an owner-reviewed denominator-admission
path in a future authorized wave.

## Auto-upgrade path (recorded, not built)

If the earnings owner later publishes an IRDM event_workspace.v1 generation,
event_workspaces/manifest.json gains an IRDM alias key; a later authorized
wave may upgrade the company rail to that packet. Until then the v1 context
API is the frozen consumption contract, and the comparison block can only
open through an owner-asserted, receipt-bound issuer-attributed denominator
whose basis is compatible with a federal obligation — which
company_intelligence_context.v1 structurally never carries, so D4 renders no
ratio on any input.
