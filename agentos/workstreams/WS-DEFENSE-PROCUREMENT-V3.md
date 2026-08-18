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
    pr: [5836, 5885, 5882, 5856]
    depends_on: [D0R]
    next_action: >
      Sol D1 acceptance review. Desk rescue, stale-base fence, FATAL=1
      candidate proof, and PIT-safe agency labels are on main and served.
      Do not start D2. Do not merge #5424. Do not re-baseline.
      Do not treat Radar 48 as new alpha.
  - id: D1.1
    title: Agency semantic recovery
    status: done
    pr: [5856]
    depends_on: [D1]
    next_action: >
      D1.1F live-proven on #5856. P00032 renders Department of Defense /
      Defense Information Systems Agency from receipt-backed PIT evidence.
      Do not start D2. Do not merge #5424.
  - id: D2
    title: Defense Identity Atlas vertical slice
    status: todo
    depends_on: [D1.1]
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
  - "government-revenue-live can build-and-prove a projection and still fail to publish; prior live projection stays authoritative until commit complete evidence projection lands (run 32112383533 did not publish; run 32177051815 did)."
  - "Radar 48 is the coherent published queue, not 26 new awards. Ledger line_count is append-only audit and is not required to equal Radar."
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
  - "Do not fold #5424 into D1 or D1.1. Do not start D2 until Sol accepts D1."
  - "Do not rewrite collector awarding_agency hashes to flatten nested USAspending objects."
  - "Do not assert Candidate Radar must equal historical 22. Prove cookie = bearer = UI for the live content_id."
  - "Do not hand-advance the candidate ledger. Do not change recipient mappings to make counts nicer."
  - "Do not re-baseline. Do not revive an et_gate mutex."
decisions:
  - DEC:D0R-RED-TEAM-ADJUDICATION-2026-08-17
  - DEC:D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
  - DEC:D11F-PIT-SAFE-AGENCY-FALLBACK
  - DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE
  - DEC:GOVREV-CANDIDATE-PROOF-GATE-ARMED
  - DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD
  - DEC:GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY
discoveries:
  - DSC:GOVREV-COMPACT-TEASER-IS-THE-LIVE-DEFAULT
  - DSC:GOVREV-MAY-ACTION-AUGUST-KNOWN-AT
  - DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
  - DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS
  - DSC:CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES
  - DSC:GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200
  - DSC:GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT
next_action: >
  Sol D1 acceptance review. Do not start Atlas/D2. Do not merge #5424.
  Do not re-baseline.
---

## Context

V3 architecture and the D0R handoff merged in #5803 (`455284b7beae`). D0R
closed on #5819 (`0d10acdd`) and was accepted; Gate 5 stays honest-labeled
(6 VERIFIED_CASE + 61 RESEARCH_CANDIDATE) and is not alpha validation.
D1 entitled-desk rescue merged as #5836. D1 closure on main: #5885 append-only
stale-base fence (`694c081975bf`), #5882 `GOVREV_CANDIDATE_PROOF_FATAL=1`
(`120f77a7e8e4`), #5856 PIT-safe receipt-strict agency (`19b009fceca6`).
Live run 32177051815 on `19b009fceca6` built, proved, and published.
Production checkout `f3a62c71833` serves bundle `grw2-825a2706c83452624a62f682`,
candidate `grcq1-3d14df91367241b9392818ca`, Radar/cookie/bearer 48, mapping
backlog 21, graph `defense19-v1`. P00032 is DoD / DISA, obligation
18416666.66, effective 2026-05-12, known_at 2026-08-12, late discovery, IRDM.
Canonical D1 contract:
`research/defense_intelligence/DEFENSE_D1_PRODUCTION_TRUTH_AND_PRODUCT_RESCUE_HANDOFF.md`.
Latest proof: `agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-18-d1-closure.md`.
D1 is not accepted until Sol's review. D2 stays unauthorized.
