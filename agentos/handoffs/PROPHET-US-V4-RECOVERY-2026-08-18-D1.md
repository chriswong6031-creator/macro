---
workstream: WS:PROPHET-US-V4-RECOVERY
session: claude/prophet-v4-d1-census
model: fable
ended_because: complete
mission: >
  V4-D1: deterministic theme-source, taxonomy, identity and coverage census at pin
  5c1d82b928 — make the thematic estate explicit enough that D2/W3B build without
  rediscovery, forced mappings, or a second graph. Zero runtime/rank/ThemeState
  authority.
state_before: >
  Post-0B record said D1 was the next authorized wave. The thematic estate was
  fragmented across ten source families with unknown coverage, unknown identity
  grain, and unmeasured PIT truth; ThemeState feasibility was unassessed; Citrini
  and Theia states were remembered rather than settled.
changed:
  - path: research/prophet_v4/D1_THEME_SOURCE_AND_IDENTITY_CENSUS_2026-08-18.md
    what: master census — headline truths, cohorts, adjudicated taxonomy roles,
      coverage/identity/PIT/rights findings, owner-surface reconciliation, external
      taxonomy verdicts, adjudicated ThemeState feasibility, gap summary
  - path: research/prophet_v4/d1/
    what: >
      8 matrix artifacts + D1_field_mapping.md + the committed build/ harness (source_family_matrix 20 rows; taxonomy_grain_matrix;
      coverage_matrix C0-C6; identity_join_audit; pit_freshness_matrix;
      theme_state_feasibility; mapping_gap_ledger 28 rows; real_data_exemplars;
      all with pin/reproduce/cohort-stamp envelopes, null_reason discipline)
  - path: research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md
    what: spawn-grade D2 handoff (gates inline; executes inside/with GMI)
  - path: research/prophet_v4/D1_D3_W3B_MERGE_ORDER_RECOMMENDATION.md
    what: recommendation — GMI W3B builds theme_state/v1 after d2; d3 = consumption
      contract; neuralweb thematic_state lineage reconciliation owed; path fences
  - path: research/prophet_v4/D1_D5_READINESS_RULING.md
    what: D5_CONTRACT_READY_AFTER_D1 + theme family ACCRUING until d3, with riders
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: d1 done; d2/d3/d5 rows updated with rulings; next_action = three Sol
      adjudications; A-lane unchanged (acceptance-by-adoption)
  - path: research/prophet_v4/CAPABILITY_LEDGER.md
    what: rows 22/23 updated with census truth; new row 47 (D1)
  - path: research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md
    what: appended section-4 item 13 (census-grounded ruling pointers)
verified:
  - claim: execution pin fresh at session start; data/ and site/ materialized before any absence claim
    command: git fetch + git log -1 origin/main; python3 scripts/worktree_sparse.py add data / add site
    result: 5c1d82b928 (2026-08-18T02:22:18Z); worktree-sparse materialized data, site
  - claim: all 9 d1 artifacts parse and carry null reasons
    command: python3 json.load over research/prophet_v4/d1/*.json; check_null_reasons.py walker
    result: all parse; walker 0 flags (builder receipts)
  - claim: cohort denominators closed and stamped
    command: builder coverage harness (reproduce commands embedded in coverage_matrix.json)
    result: C0=3227@2026-08-07; C1=1508@2026-08-12-STALE; C2=192@08-13; C3=831@08-13; C4=UNKNOWN(reason); C5=71@08-14; C6=2368
  - claim: graph company plane is ticker-string-keyed
    command: builder identity audit over data/theme_graph/nodes.parquet external_ids
    result: every company node's external_ids is exactly one symbol-to-ticker pair; hostile chains recorded
  - claim: no repo file outside the D1 deliverable set changed
    command: git status --porcelain during build
    result: only research/prophet_v4/ additions + the record updates above
unverified:
  - claim: OHLCV price-series PIT class (performance-family input)
    what_would_verify: D2 confirmation over data/baskets/ohlcv/ (outside D1 core list)
  - claim: Company Theme Exposure R2 artifact existence
    what_would_verify: network read of the R2 bucket (out of D1 scope)
unresolved:
  - "5 RIGHTS_DECISION_REQUIRED items routed (census section 7): Finviz derived-display tier; Citrini definitions commit (operator delivery); Theia license option; Kensho procurement; structural GICS classification (review H4 — 99% third-party rows, no registry entry)."
  - "Two live graph data defects (GOLD reused-ticker member, IBIT ETF-as-company) recorded as gap rows — D2 corrects through graph lineage, not D1."
  - "Act-Now board (site/basketdata/action_board.json) located but not field-mapped — flagged for the ThemeState builder."
  - "probation/proposals.jsonl schema unopened — D2 gate 2 opens it."
next_actions:
  - "Merge the D1 PR (this session owns it to merge)."
  - "Route to Sol: commission d2 with GMI (handoff ready); ratify the D3/W3B merge order; optionally commission the d5 contract lane in parallel."
  - "A-lane unchanged: await the Availability return for Sol acceptance (#5742); do not spawn A1."
do_not_redo:
  - "Do not redo source archaeology — the census + d1/ artifacts are the record; re-verify only LIVE items (served freshness, #5742)."
  - "Do not fuzzy-map THS/Finviz/basket labels to canonical themes — probation + adjudication only (W3A ruling; D2 gate 2)."
  - "Do not fabricate the exposure-weights plane — NO SOURCE exists; CTE is a membership projection, not weights."
  - "Do not treat the neuralweb thematic_state lineage, the subsector-rotation surface, or the Act-Now board as ThemeState — owner surfaces; formulas are prior art only."
  - "Do not read the top-level accel/z_accel of subsector_rotation.json as the velocity primitive — different formula, same name; the turn-engine z-fields are the prior art."
danger_areas:
  - "C1 is STALE (2026-08-12, scan-only) because the availability outage stalled the candidate store — any coverage claim citing C1 must carry the stamp."
  - "The 11 us_sector_* pseudo-baskets are STRUCTURAL — counting them as thematic membership zeroes the C6 gap and inflates coverage."
  - "Rights: Finviz/THS are internal-only for new emissions; a public ThemeState on them is unlawful until the routed decision resolves."
prs: [5859]
---

## Cold-stranger summary

D1 measured the thematic estate instead of assuming it: 73% of the classification
union has structural-only coverage; the graph joins by ticker strings; the crosswalk
and THS planes have no PIT history; a ThemeState-shaped predecessor already runs in
neuralweb; Citrini is operator-held; Theia stays a procurement option. The repair
path is frozen: d2 (identity + probation breadth, inside GMI) → W3B builds
theme_state/v1 (reconciling the neuralweb lineage) → d3 consumes; d5's contract lane
may run in parallel with the theme family pinned ACCRUING. Start at the master
census; every number has a reproduce command in `research/prophet_v4/d1/`.
