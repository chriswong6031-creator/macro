---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/defense-d1-product-rescue
model: local
ended_because: ci_handoff
prs: []
decisions:
  - DEC:D0R-RED-TEAM-ADJUDICATION-2026-08-17
discoveries:
  - DSC:GOVREV-COMPACT-TEASER-IS-THE-LIVE-DEFAULT
  - DSC:GOVREV-MAY-ACTION-AUGUST-KNOWN-AT
  - DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
  - DSC:GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200

mission: >
  D1 production truth and signed-in product rescue of government_revenue.html
  for an already-entitled site_full user. No D2, no #5424, no collectors,
  no Prophet/Neural Web authority expansion.

state_before: >
  D0R accepted on #5819 (0d10acdd). Main had advanced past that checkpoint.
  Entitled production already had cookie workspace 500 and bearer candidates 22,
  but Radar treated pre-MDXAuth 401 as membership lock, filmstrip said Members
  only, agency filters leaked objects/Python reprs, compact-loading banner could
  remain after a complete hydrate, and Budget/SAM zeros read as empty-valid.

changed:
  - path: templates/government-revenue-candidate-radar.js
    what: >
      Rehydrate on mdx-auth; 401 before auth-ready stays loading; cookie
      candidates.json is a valid entitled fallback; 401 after settle is locked.
  - path: templates/government-revenue-dossiers.js
    what: >
      Budget 503/404/contract maps to projection_missing; 401 before settle
      stays loading; reload on mdx-auth.
  - path: templates/government_revenue.html.j2
    what: >
      Banner hides when the workspace is already complete; filmstrip cannot
      say Members only on a complete entitled tape; agency names are coerced;
      Budget/SAM empty states print PROJECTION_MISSING / SOURCE_UNAVAILABLE;
      Radar unavailable offers retry, not plans.html.
  - path: site/government-revenue-candidate-radar.js
    what: Paired plain-copy of the Radar factory.
  - path: site/government-revenue-dossiers.js
    what: Paired plain-copy of the Budget factory.
  - path: tests/test_government_revenue_ui.py
    what: Late-auth, cookie hydrate, complete-banner, agency names, typed failures.
  - path: tests/test_government_revenue_dossier_ui.py
    what: Budget 503 is projection_missing.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: D0R done; D1 in_progress; #5424 still excluded.

verified:
  - claim: D1 UI/auth tests pass, including late MDXAuth reload and cookie queue hydrate.
    command: >
      .venv python -m pytest tests/test_government_revenue_ui.py
      tests/test_government_revenue_dossier_ui.py
      tests/test_government_revenue_api_auth.py -q
    result: 99 passed
  - claim: Anonymous /api/government-revenue/* still 401 without bearer.
    command: pytest tests/test_government_revenue_api_auth.py -q
    result: passed; no entitlement expansion
  - claim: Radar 401 before auth-ready is loading, not locked; 401 after settle is locked.
    command: pytest tests/test_government_revenue_ui.py::test_candidate_radar_reports_an_unentitled_lane_as_locked
    result: passed
  - claim: Complete workspace hides the compact-loading banner and will not mark IRDM Members only.
    command: pytest tests/test_government_revenue_ui.py::test_d1_complete_workspace_hides_compact_loading_banner tests/test_government_revenue_ui.py::test_d1_entitled_complete_workspace_does_not_mark_filmstrip_members_only
    result: passed
  - claim: Agency object and Python-repr strings become human names or Unspecified agency.
    command: pytest tests/test_government_revenue_ui.py::test_d1_agency_filters_are_human_names_not_python_dicts
    result: passed
  - claim: Budget graph 503 is PROJECTION_MISSING; opportunities freshness unavailable is SOURCE_UNAVAILABLE.
    command: pytest tests/test_government_revenue_dossier_ui.py::test_budget_graph_absence_is_projection_missing_not_empty_valid tests/test_government_revenue_ui.py::test_d1_opportunities_and_budget_render_typed_failure_states
    result: passed

unverified:
  - claim: Entitled production Radar shows 22 rows including grc1-025ab7cfdb7f9735f0e1e575 and no membership CTA.
    what_would_verify: Signed-in browser on https://www.mastermind-x.com/government_revenue.html after merge+VPS pull+render, plus bearer /api/government-revenue/candidates content_id
  - claim: Entitled Change Tape shows 500 events with the compact-loading banner hidden.
    what_would_verify: Same session cookie GET government-revenue-data/workspace.json events.length===total and banner[hidden]
  - claim: Live graph id remains defense19-v1 and #5424 was not merged.
    what_would_verify: gh pr view 5424 --json state; live candidate issuer_resolution_ref.graph_id

unresolved:
  - Authenticated production/browser proof after merge and render.
  - D2 Atlas remains unauthorized until operator review of D1 live proof.
  - "#5424 defense20-v1 still open/draft; outside this program."

next_actions:
  - After merge, wait for VPS pull (JS pairs) and render.yml (inline j2 runtime).
  - Sign in through the normal UI and prove Changes 500, Radar 22, typed Budget/SAM failures, no Members only on IRDM.
  - Return the live content ids and typed failure states for review. Do not start D2.

do_not_redo:
  - Do not rediscover the underscore vs hyphen URL or anonymous latest.json 401.
  - Do not treat defense20-v1 / "#5424" as the live graph.
  - Do not start SAM/P-1/FMS/GAO collectors inside D1.
  - Do not raise the 500 workspace cap.
  - Do not compute a frontend materiality ratio from $18.4M.
  - Do not infer late discovery from action_date vs known_at; keep is_late_discovery.
  - Do not treat entitled API 200 as Radar-live without the overlay actually gone.
  - Do not assume cookie JSON 200 implies /api/government-revenue 200 without a bearer.

danger_areas:
  - Writing into omitted sparse data/ truncates committed artifacts.
  - Committing cookies, Authorization headers, emails, or /tmp Chrome profiles.
  - Language-switch boot(false) must not clobber a locked banner with loading.
  - Radar 401 before MDXAuth ready is a race, not membership.
  - Paired JS files go live on VPS pull; the j2 inline runtime needs render.yml.
---

D1 implementation is on `claude/defense-d1-product-rescue`. Live production proof is still unverified until merge, VPS pull, and render.yml bake `government_revenue.html`. Do not start D2. Do not fold #5424.
