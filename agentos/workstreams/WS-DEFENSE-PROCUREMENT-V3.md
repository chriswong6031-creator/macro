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
    status: done
    pr: [5836, 5885, 5882, 5856]
    depends_on: [D0R]
    next_action: >
      Done — Sol accepted D1 (D2 was authorized and executed on top of it).
      Radar 48 remains coverage truth, never new alpha.
  - id: D1.1
    title: Agency semantic recovery
    status: done
    pr: [5856]
    depends_on: [D1]
    next_action: >
      Done/accepted. D1.1F live-proven on #5856. P00032 renders Department of
      Defense / Defense Information Systems Agency from receipt-backed PIT
      evidence.
  - id: D2
    title: Defense Identity Atlas vertical slice
    status: done
    pr: [5932, 5997, 6004, 6008]
    depends_on: [D1.1]
    next_action: >
      Done — accepted after the D2P production close (2026-08-20 entitled-
      journey proof; see
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-20-d2p-production-close.md).
      The operational closure chain is FOUR PRs, not #5932 alone: #5932
      (defense21-v1 graph, digest 93171ba0e6f7…, + Identity Atlas
      artifact/product, two-round opus adversarial review), #5997
      (republish-proof heal: distinct-id census + ledger-issuance-frontier
      discriminator), #6004 (candidate-accounting closure: B2 non-issuance
      manifest refused on evidence; vintage-bound excuse self-retired), #6008
      (unissued candidates self-retire via nightly; B2 manifest unloadable).
      Five BWXT chains reviewed; MMACD85DT5D5 / PM7HBL2KDX46 / URJ3CAC3MSH8
      refused (see DEC:D2-BWXT-EXACT-ADMISSION-GE-STAYS-UNRESOLVED); GE and
      SPR stay not_asserted by design. Remaining mapping_needed pilots: GE.
      #5424 is superseded by defense21-v1 — do not merge, revive, or recut.
      Graph republish law: DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK.
      Reliability follow-up (NOT a D3 prerequisite): the publisher-vintage
      lag has no alarm — nothing notices a publisher that stops firing
      (DSC:GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE).
  - id: D3
    title: Temporal event v3 and Change Tape
    status: done
    pr: [6048, 6059]
    depends_on: [D2]
    next_action: >
      Done — Sol authorized 2026-08-20 and the bounded charter shipped the
      same day: typed rail failure_state (source_unavailable /
      projection_missing) emitted by the workspace read-model, dual-clock
      tape rows + Late-discovery chip, inspector Clocks block with the
      NAMED-NULL source-publication row, receipt-bound before/after +
      successor line from prior_source_identity, budget mode's eternal
      "loading" retired. Additive only — event contract stays v2
      (DEC:D3-TEMPORAL-V3-IS-ADDITIVE); frozen spec
      research/defense_intelligence/DEFENSE_D3_TEMPORAL_CONTRACT_AND_CHANGE_TAPE_SPEC.md.
      Opus adversarial review found a real blocker (the first cut destroyed
      the already-working module PROJECTION_MISSING verdict) — repaired same
      PR chain: the real module's HTTP-receipt status is authoritative, the
      typed fallback applies only when no module exists. #6059 fitted the
      page under a ratcheted 296 KiB raw-byte budget after the D3 markup
      left 65 bytes of headroom. All four D3 families production-proven
      (browser proof 2026-08-20). ACCEPTED by Sol 2026-08-20 (D4 authorized
      on the D3 close).
  - id: D4
    title: Company financial truth bridge
    status: done
    pr: [6123, 6173]
    depends_on: [D3]
    next_action: >
      Done — shipped and live 2026-08-20 (merge b5548ece927d) under Sol's
      IRDM-only charter. Owner preflight: case A on the v1 context plane
      (GET /api/company-intelligence/IRDM serves company_intelligence_
      context.v1 live; event_workspace.v1 stays AAPL-only; DEC:D4-COMPANY-
      RAIL-CONSUMES-CI-V1-CONTEXT). Bridge renders GOVERNMENT FACT (P00032,
      transaction receipt by content_sha256) / COMPANY TRUTH
      (earnings_history-lineage fields only, fail-closed typed unavailable)
      / COMPARISON fixed not_comparable with no ratio node / RESEARCH
      QUESTION. 27-test hostile suite on a committed P00032 fixture in the
      MERGE-BINDING gate:code job govrev-company-bridge. Opus review found
      the suite would have shipped dark (gate:data holding pen) and a
      wrong-receipt link — repaired pre-merge, probes pinned as tests.
      Page fence unchanged (baked 296,693 <= 303,104). Sol re-review
      2026-08-21: implementation substantially passes, FINAL ACCEPTANCE
      WITHHELD on two gates. Gate 1 (D4.1 provenance hardening) CLOSED
      2026-08-21: receiptUrl() fail-open `|| rows[0]` fallback removed —
      exact content_sha256 match or NO source link (PR #6173, merge
      8f10699e118b, live in prod checkout 6590e678c60, fail-closed bytes
      verified at the serving checkout); pinned by hostile tests R14a-R14d
      in the merge-binding gate:code suite plus a captured red/green
      mutation run; bake 296,729 <= 303,104, fence NOT ratcheted. Gate 2
      (D4P entitled happy-path production proof) BLOCKED: no entitled
      browser mechanism was available (Chrome extension: zero connected
      instances, checked repeatedly 2026-08-21; credential entry is
      prohibited to agents; government-revenue-data/workspace.json is
      auth-locked so there is no anonymous receipt-sha shortcut). Honest
      state per Sol's own protocol: D4.1 merged; D4 = BUILT_NOT_PROVEN;
      BLOCKED_ON_ENTITLED_PRODUCTION_PROOF. No fixture substitute was
      performed. Live owner packet at block time: schema
      company_intelligence_context.v1, available true, generated_at
      2026-08-21T06:53:16Z, latest_event cie_77ff210df9c064c3b2fe4aa1,
      FY2026 Q1 / call 2026-04-23, claim_citations_pending true. Anonymous
      negative controls re-proven post-D4.1 (module 401, workspace locked,
      page 200, bridge host hidden markup only). D5 unauthorized.
  - id: D5
    title: Program, mission, capability, and product graph
    status: todo
    depends_on: [D4]
landmines:
  - "Live page is government_revenue.html (underscore). government-revenue.html 404s."
  - "Access (site_full / 401 locked) is independent of epistemics (display/context_only). Do not conflate them."
  - "Reviewed recipient graph on HEAD is defense21-v1 as of #5932 (defense19 rows byte-preserved). #5424 defense20-v1 is CLOSED/superseded by defense21-v1 — do not merge, revive, or recut it (Sol, D4 charter 2026-08-20)."
  - "government-revenue-live can build-and-prove a projection and still fail to publish; prior live projection stays authoritative until commit complete evidence projection lands (run 32112383533 did not publish; run 32177051815 did)."
  - "Radar 48 is the coherent published queue, not 26 new awards. Ledger line_count is append-only audit and is not required to equal Radar."
  - "Session worktrees are sparse by default. Never write into omitted data/ — that truncates the committed artifact."
  - "DNR:LAW-REVIEWED-MANIFEST-CENSUS — a reviewed recipient graph cannot re-time itself."
  - "SPR is not a live issuer (Boeing close 2025-12-08; absent from Stock Identity universe)."
  - "government_revenue.html has a ratcheted RAW_HTML_BUDGET_BYTES fence (296 KiB since #6059). Template growth ships INLINE in the page — bake locally (scripts/build_government_revenue._write_site_projection) before merging template edits, or the shared render lane fails at the govrev step. D3's first cut left 65 bytes of headroom."
  - "The real createGovernmentRevenueBudget module EXISTS in government-revenue-dossiers.js (BSD grep hides it — use grep -a). Its HTTP-receipt status is authoritative; the typed freshness.budget fallback applies only when no module loaded."
do_not_redo:
  - "Do not start original D0. V2/D0 remain historical records only."
  - "Do not implement collectors, schemas, UI, Neural Web, or Prophet members in D0R."
  - "Do not create a second SEC, transcript, estimate, price, options, theme, identity, tenant, Neural Web, or Prophet plane."
  - "Do not treat GovTribe/GovCon capture parity as the product north star."
  - "Do not grant rank, gate, size, entry, or execution authority."
  - "Do not treat SPR as a live golden ticker."
  - "Do not invent 60 VERIFIED_CASE primaries."
  - "Do not merge, revive, or recut #5424 — superseded by defense21-v1 (#5932). Do not start D3 until Sol authorizes it."
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
  D4P entitled production proof, then Sol final D4 acceptance. D4.1
  provenance hardening is CLOSED (#6173, merge 8f10699e118b, live);
  D4 = BUILT_NOT_PROVEN / BLOCKED_ON_ENTITLED_PRODUCTION_PROOF — the
  remaining gate is a real entitled site_full browser session rendering
  government_revenue.html?mode=companies&item=company:IRDM with the
  SUCCESS company-packet state beside P00032 (receipt sha equivalence,
  1280/768/375, LMT negative, anon control) per Sol's 2026-08-21 D4
  closeout directive. Unblocks when an authorized entitled browser
  mechanism exists (e.g. operator connects the Claude Chrome extension in
  a signed-in Chrome); never via agent credential entry, never via a
  fixture substitute. D5 is unauthorized. #5424 is closed/superseded by
  defense21-v1. Publisher-vintage alarm and fixture-freezing the D2/D3
  law suites out of the unrun-government-revenue holding pen remain
  separate follow-ups — do not fold them into the D4 closeout.
---

## Context

V3 architecture and the D0R handoff merged in #5803 (`455284b7beae`). D0R
closed on #5819 (`0d10acdd`) and was accepted; Gate 5 stays honest-labeled
(6 VERIFIED_CASE + 61 RESEARCH_CANDIDATE) and is not alpha validation.
D1 entitled-desk rescue merged as #5836. D1 closure on main: #5885 append-only
stale-base fence (`694c081975bf`), #5882 `GOVREV_CANDIDATE_PROOF_FATAL=1`
(`120f77a7e8e4`), #5856 PIT-safe receipt-strict agency (`19b009fceca6`).
Live run 32177051815 on `19b009fceca6` built, proved, and published.
Canonical D1 contract:
`research/defense_intelligence/DEFENSE_D1_PRODUCTION_TRUTH_AND_PRODUCT_RESCUE_HANDOFF.md`.

D2 closed operationally on #5932 + #5997 + #6004 + #6008 and was
production-proven 2026-08-20 (D2P): production checkout `f69f224c972` serves
graph `recipient-graph:reviewed:2026-08-19:defense21-v1` (digest
`93171ba0e6f7286de02e0918ef85be7db80df3f6b7fd8eb3d47e7e8e4adfa843`), atlas
`gria1-4eeaa88c8cbabfaa800fc67d` (graph_status ready), bundle
`grw2-a0f56dbca09da2a4d0363ca1`, candidate queue
`grcq1-3ff9ecc9633f3d667840f43f` (62), mapping backlog 21; candidate
accounting 124 emitted lines / 70 distinct ids / 8 quarantined (2026-08-10
manifest) / 62 queued / 0 unaccounted. P00032 stays DoD / DISA, obligation
18416666.66, effective 2026-05-12, known_at 2026-08-12, late discovery, IRDM.
Proof record:
`agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-20-d2p-production-close.md`.
D3 stays unauthorized pending Sol review.
