---
workstream: "WS:EARNINGS-INTELLIGENCE-OS"
session: claude/earnings-e0-freeze-20260816
model: opus
ended_because: complete
mission: >
  Execute E0 only — capability ledger, lineage, ownership, golden universe,
  experience architecture, and frozen E1/E2 handoffs. Do not implement E1.
state_before: >
  PR #5797 held the V2 masterplan, E0 spec, DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE
  and DSC:EARNINGS-PROVENANCE-SUBSTRATE-OUTRAN-THE-PRODUCT. No E0 artifacts existed
  on origin/main.
changed:
  - path: research/earnings_intelligence/E0_CAPABILITY_LEDGER.md
    what: Exhaustive live/partial/spec/not-built ledger across all E0 families.
  - path: research/earnings_intelligence/E0_LINEAGE_AND_RUNTIME_MAP.md
    what: Traced LMND, AAPL, GOOGL/GOOG across Wire, CI, Terminal, Brain, Stage.
  - path: research/earnings_intelligence/E0_COMPETITOR_WORKFLOW_MATRIX.md
    what: Quartr / EarningsCall.ai / Jodie / Struct / EquityDesk jobs with COPY_JOB/ADAPT/DEFER/REJECT.
  - path: research/earnings_intelligence/E0_GOLDEN_UNIVERSE_AND_ACCEPTANCE_CASES.md
    what: Five companies, eight events, AI-infra golden wave, AAPL glance facts.
  - path: research/earnings_intelligence/E0_EXPERIENCE_ARCHITECTURE.md
    what: Ten surfaces, 1440/820/390, eight states, frozen E2 interactions.
  - path: research/earnings_intelligence/compositions/e0_real_data_specimen.html
    what: Real-data AAPL Q3 FY2026 specimen, not a product route.
  - path: research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md
    what: Identifiers, objects, payload, §4.1 production publication/read contract, file allow-lists, program ownership.
  - path: research/earnings_intelligence/E1_IMPLEMENTATION_HANDOFF.md
    what: E1 stops at payload + read_event_workspace; Brief+dossier is E1+E2.
  - path: research/earnings_intelligence/E2_IMPLEMENTATION_HANDOFF.md
    what: Exact E2 acceptance, blocked on E1; labeled as E1+E2 arc success.
  - path: agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md
    what: Workstream under existing program key earnings-intelligence.
  - path: agentos/decisions/DEC-EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP.md
    what: Keep earnings-intelligence; do not mint a second key in E0.
  - path: agentos/decisions/DEC-EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT.md
    what: Freeze event_workspaces nest + read_event_workspace as the real E1 consumer.
  - path: agentos/discoveries/DSC-EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER.md
    what: Live LMND/AAPL/GOOG plane split.
verified:
  - claim: Live Wire is a source-first transcript archive with 3361 admitted records.
    command: curl -sL https://www.mastermind-x.com/stocks/earnings/ | rg -n "admitted call records|0 model"
    result: "3361 admitted call records; 0 model calls in this publication (2026-08-16)"
  - claim: AAPL CI latest_event is FY2026 Q3 with claim_citations_pending and overlay summary.
    command: curl -sL https://www.mastermind-x.com/api/company-intelligence/AAPL
    result: "cie_98e318c37ec1a2a1f83c45e1, call_date 2026-07-30, claim_citations_pending true, summary lineage score_overlay"
  - claim: Expected AAPL Wire slug 404s.
    command: curl -sI https://www.mastermind-x.com/stocks/earnings/aapl-2026q3-call-record.html
    result: "HTTP 404 on 2026-08-16"
  - claim: LMND Wire Q2 is live with exact spans while CI latest is Q1.
    command: curl -sL https://www.mastermind-x.com/stocks/earnings/lmnd-2026q2-call-record.html; curl -sL https://www.mastermind-x.com/api/company-intelligence/LMND
    result: "Wire Q2 2026-07-29 byte table; CI latest_event FY2026 Q1 2026-04-29"
  - claim: GOOGL CI exists and GOOG CI does not.
    command: curl -sI https://www.mastermind-x.com/api/company-intelligence/GOOGL; curl -sI https://www.mastermind-x.com/api/company-intelligence/GOOG
    result: "GOOGL 200; GOOG 404"
  - claim: Calendar coverage is degraded despite a fresh newest stamp.
    command: python3 -c "import json; print(json.load(open('data/quality/earnings_freshness_audit.json'))['ok'], json.load(open('data/quality/earnings_freshness_audit.json'))['detail']['fresh_row_fraction'])"
    result: "ok False; fresh_row_fraction 0.1785 (as_of 2026-08-13)"
  - claim: AAPL FY2026 Q3 8-K Item 2.02 lives at accession 0000320193-26-000018 (not a date join).
    command: curl -sI https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm
    result: "SEC archives object for 0000320193-26-000018 (filing 2026-07-30); Exhibit 99.1 sibling a8-kex991q3202606272026.htm"
unverified:
  - claim: Terminal origin/master CI v1 lenses match the explore census (Brief/Topics/Sources live; Peers/Slides spec-only).
    what_would_verify: Fast-forward charting-app to origin/master and open /analysis?symbol=AAPL&page=intelligence at 1440.
  - claim: data/edgar/earnings_8k_dates.parquet already carries accession 0000320193-26-000018 for CIK 320193.
    what_would_verify: Query that parquet on a full checkout; join, do not re-scrape.
unresolved:
  - Expanding owns/does_not_own on earnings-intelligence requires a generated-map PR after E0.
  - Production freshness repair remains an independent lane; E0 did not touch it.
next_actions:
  - Merge the E0 artifact PR (docs/research only).
  - New session: implement E1 exactly as research/earnings_intelligence/E1_IMPLEMENTATION_HANDOFF.md.
  - Do not start E2 until E1 is live.
do_not_redo:
  - Rebuild Terminal transcripts, Stage, Group Reads, TIL, or a standalone app.
  - Treat Wire excerpts as the finished product.
  - Flip v1 claim_citations_pending to false.
  - Use synthetic corpus CIKs in production.
danger_areas:
  - Listing-keyed cie_ ids vs issuer-keyed canonical ids.
  - CI generated_at vs latest_event freshness.
  - Forced transcript-only public_wire completeness contract.
  - Prophet earnings_call_sent residual path (R0-C / DNR:HOLD-PSQ-TILT-CLOCK).
---

E0 is complete as a construction drawing. The next session sentence is safe:

> Implement E1 exactly as frozen; prove AAPL FY2026 Q3 from source documents through the canonical compact payload and one real consumer.
