---
key: DEFENSE-PROCUREMENT-V3
title: Defense Procurement & Industrial Base Intelligence OS V3
objective: >
  Freeze a financial-alpha defense architecture, then implement it as bounded
  waves D0R through D20 over the existing Government Revenue substrate. Done for
  D0R = current-state truth, driver taxonomy, historical casebook method,
  source/rights/PIT registry, graph/contract freeze, golden universe, real-data
  experience architecture, and exact D1-D4 handoffs exist; no production mutation.
status: active
program: government-revenue-foresight
repos: [macro, terminal, mastermind]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md
  - research/DEFENSE_PROCUREMENT_D0R_FINANCIAL_ALPHA_RECONNAISSANCE_HANDOFF_2026-08-16.md
  - research/defense_intelligence/
  - engine/government_revenue/
  - app/government_revenue.py
  - scripts/build_government_revenue.py
  - scripts/build_government_revenue_candidates.py
  - templates/government_revenue.html.j2
  - templates/government-revenue-candidate-radar.js
  - templates/government-revenue-dossiers.js
waves:
  - id: D0R
    title: Financial-alpha reconnaissance and architecture freeze
    status: done
    pr: [5814, 5819]
    next_action: >
      D0R accepted on #5819. Do not reopen Gate 5 as a D0R architecture gap.
      Historical corpus remains mandatory before any alpha promotion.
  - id: D1
    title: Production truth and signed-in product rescue
    status: in_progress
    depends_on: [D0R]
    next_action: >
      GovRev stale-write fence, then a receipt-bound re-baseline, then
      rebase #5856 with receipt hardening. Do not start D2. Do not merge
      #5424. Do not treat Radar 48 as new alpha.
  - id: D2
    title: Defense Identity Atlas vertical slice
    status: todo
    depends_on: [D1]
  - id: D3
    title: Temporal event v3 and Change Tape
    status: todo
    depends_on: [D2]
  - id: D4
    title: Company financial truth bridge
    status: todo
    depends_on: [D3]
  - id: D5
    title: Program, mission, capability, and product graph
    status: todo
    depends_on: [D4]
landmines:
  - "Live page is government_revenue.html (underscore). government-revenue.html 404s."
  - "Access (site_full / 401 locked) is independent of epistemics (display/context_only). Do not conflate them."
  - "HEAD recipient graph is defense19-v1. #5424 defense20-v1 is still open and must not be treated as live."
  - "government-revenue-live can build-and-prove a projection and still fail to publish; prior live projection stays authoritative (run 32112383533, 2026-08-18)."
  - "Radar 48 is the coherent published queue, not 26 new awards. Ledger still has 56 lines with orphaned race identities."
  - "Session worktrees are sparse by default. Never write into omitted data/ — that truncates the committed artifact."
  - "DNR:LAW-REVIEWED-MANIFEST-CENSUS — a reviewed recipient graph cannot re-time itself."
  - "SPR is not a live issuer (Boeing close 2025-12-08; absent from Stock Identity universe)."
do_not_redo:
  - "Do not start original D0. V2/D0 remain historical records only."
  - "Do not implement collectors, schemas, UI, Neural Web, or Prophet members in D0R."
  - "Do not create a second SEC, transcript, estimate, price, options, theme, identity, tenant, Neural Web, or Prophet plane."
  - "Do not treat GovTribe/GovCon capture parity as the product north star."
  - "Do not grant rank, gate, size, entry, or execution authority."
  - "Do not treat SPR as a live golden ticker."
  - "Do not invent 60 VERIFIED_CASE primaries."
  - "Do not fold #5424 into D1. Do not start D2 in the D1 session."
  - "Do not assert Candidate Radar must equal historical 22. Prove cookie = bearer = UI for the live content_id."
  - "Do not hand-advance the candidate ledger. Do not change recipient mappings to make counts nicer."
  - "Do not merge #5856 until a healed/receipt-bound generation exists to rebase onto."
decisions:
  - DEC:D0R-RED-TEAM-ADJUDICATION-2026-08-17
discoveries:
  - DSC:GOVREV-COMPACT-TEASER-IS-THE-LIVE-DEFAULT
  - DSC:GOVREV-MAY-ACTION-AUGUST-KNOWN-AT
  - DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
  - DSC:GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200
  - DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS
  - DSC:CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES
next_action: >
  Fence government-revenue-live stale writes, then receipt-bound re-baseline,
  then rebase #5856. Do not start D2. Do not merge #5424.
---

## Context

V3 architecture and the D0R handoff merged in #5803 (`455284b7beae`). D0R
closed on #5819 (`0d10acdd`) and was accepted; Gate 5 stays honest-labeled
(6 VERIFIED_CASE + 61 RESEARCH_CANDIDATE) and is not alpha validation.
D1 entitled-desk rescue merged as #5836. D1 is not accepted: #5856 PIT-safe
agency is still open, and the 2026-08-18 collection/fold race left a published
generation that live rebuild 32112383533 built but did not publish. Recovery
generation currently served: bundle `grw2-df3a9860110d76a89dd9cc6b`, candidate
`grcq1-d7948adf2acbf728e9e48270`, Radar/cookie/bearer 48, mapping backlog 21,
graph `defense19-v1`. Canonical D1 contract:
`research/defense_intelligence/DEFENSE_D1_PRODUCTION_TRUTH_AND_PRODUCT_RESCUE_HANDOFF.md`.
Latest proof: `agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-18.md`.
