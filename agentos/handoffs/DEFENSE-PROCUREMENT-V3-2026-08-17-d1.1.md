---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/defense-d1-1-agency-semantic
model: local
ended_because: ci_handoff
prs: []
decisions:
  - DEC:D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
discoveries:
  - DSC:GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT

mission: >
  D1.1 Agency Semantic Recovery: every Change/Award row with authoritative
  awarding-agency evidence must show a truthful human label on the Change Tape
  and agency facet. Only genuinely missing agency may render Unspecified agency.
  No D2, no #5424, no collectors, no Prophet/Neural Web authority.

state_before: >
  D1 PR #5836 was live. Change Tape 500 / Radar 22 / Budget PROJECTION_MISSING /
  Opportunities SOURCE_UNAVAILABLE were preserved, but agencyName() discarded
  mixed Python-repr strings (`: None` plus a real toptier name) and action
  events such as P00032 shipped agency {name:null, subagency:null} despite
  DISA/DoD on the award snapshot.

changed:
  - path: engine/government_revenue/award_events.py
    what: >
      canonicalize_agency() parses nested USAspending objects and legacy
      Python/JSON literals into the v2 agency object; action events inherit
      the latest snapshot agency for the same award_identity when they omit
      awarding_agency; funding_agency is not copied.
  - path: engine/government_revenue/workspace.py
    what: >
      Facet helper uses the frozen label order; copied award events are
      re-canonicalized so already-projected Python-repr name fields heal at
      rebuild without a collector rewrite.
  - path: scripts/build_government_revenue.py
    what: Compact first-paint now keeps name and subagency as well as department_*.
  - path: templates/government_revenue.html.j2
    what: >
      agencyName() presents department_name → subagency_name → office_name →
      name; leftover `{` strings stay Unspecified; queue can show subagency
      as a separate span; inspector prefers department_name then subagency_name.
  - path: tests/test_government_revenue_award_events.py
    what: Semantic cases A/B/C plus P00032 clocks, IRDM, and $18,416,666.66 increment.
  - path: tests/test_government_revenue_workspace.py
    what: Workspace rebuild parses a legacy serialized name into DoD/DISA facets.
  - path: tests/test_government_revenue_ui.py
    what: Structured department, subagency fallback, P00032, NASA, and genuine Unspecified.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: D1 done; D1.1 in progress; D2 still unauthorized.
  - path: agentos/discoveries/DSC-GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT.md
    what: Live 478-empty / 22-repr split and P00032 parquet evidence.
  - path: agentos/decisions/DEC-D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT.md
    what: Projector canonicalize + snapshot inherit; no collector hash rewrite.

verified:
  - claim: Structured department_name, subagency fallback, legacy USAspending literal, and genuine null project to the expected labels.
    command: >
      .venv python -m pytest tests/test_government_revenue_award_events.py
      tests/test_government_revenue_workspace.py::test_workspace_parses_legacy_serialized_agency_into_human_facet -q
    result: 41 passed including P00032 DISA/DoD inherit, NASA second agency, null unspecified
  - claim: P00032 stays IRDM, late discovery, $18,416,666.66 federal_action_obligation, and does not copy Air Force funding into awarding agency.
    command: pytest tests/test_government_revenue_award_events.py::test_d11_p00032_recovers_award_snapshot_agency_without_changing_clocks_or_amount
    result: passed
  - claim: Change Tape UI shows Department of Defense, NASA, Defense Logistics Agency, and Unspecified agency with no Python repr leak.
    command: pytest tests/test_government_revenue_ui.py::test_d11_agency_labels_preserve_source_semantics tests/test_government_revenue_ui.py::test_d1_agency_filters_are_human_names_not_python_dicts tests/test_government_revenue_ui.py::test_d1_opportunities_and_budget_render_typed_failure_states
    result: passed; TEMPLATE still contains PROJECTION_MISSING and SOURCE_UNAVAILABLE

unverified:
  - claim: Entitled production Change Tape shows at least two real human agency names and P00032 as Department of Defense / DISA.
    what_would_verify: >
      site_full session on https://www.mastermind-x.com/government_revenue.html
      after merge plus government-revenue-live rebuild of workspace.json
  - claim: Candidate Radar remains 22 and Budget/Opportunities remain typed failures.
    what_would_verify: Same entitled session; bearer candidates total=22; budget 503; SAM SOURCE_UNAVAILABLE

unresolved:
  - Production workspace.json still has the pre-D1.1 agency shapes until government-revenue-live rebuilds it from parquet.
  - D2 Identity Atlas remains unauthorized.

next_actions:
  - Merge the D1.1 PR on concluded green checks and arm merge-on-green as backstop.
  - Watch government-revenue-live rebuild workspace.json; do not cancel the lane.
  - Entitled production proof of agency labels, P00032, Unspecified, 500/22, typed Budget/SAM.
  - Stop. Do not start D2.

do_not_redo:
  - Do not start D2 / Identity Atlas in this session.
  - Do not merge #5424.
  - Do not rewrite collector awarding_agency hashes to flatten nested objects.
  - Do not eval() or parse arbitrary Python in the browser.
  - Do not infer agency from ticker, NAICS, PSC, or description.
  - Do not merge funding_agency into awarding agency.
  - Do not raise the 500-event cap or change candidate eligibility.

danger_areas:
  - Collector event_state_sha256 is load-bearing; canonicalizing only at write time fabricates revisions.
  - Session worktrees omit data/; never git add a truncated data/ or site/ diff.
  - Compact #gov-data is a 2-row teaser; entitled truth is cookie workspace.json after rebuild.
  - Live URL is government_revenue.html (underscore).
---

D1.1 heals the public agency object. It does not collect new sources and does
not authorize Atlas.
