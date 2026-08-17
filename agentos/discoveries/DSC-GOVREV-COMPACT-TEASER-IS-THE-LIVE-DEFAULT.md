---
key: GOVREV-COMPACT-TEASER-IS-THE-LIVE-DEFAULT
claim: >
  Production government_revenue.html is a locked compact teaser: #gov-data
  carries government_procurement_workspace.v2 bundle grw2-dd9d7af893a7f3c773909351
  with total 500 and events length 2; workspace.json and /api/government-revenue/*
  return 401 without a site_full session.
falsifier: >
  From an anonymous browser on https://www.mastermind-x.com/government_revenue.html,
  GET government-revenue-data/workspace.json returns 200 JSON with events.length
  equal to procurement_workspace.total, or the compact #gov-data events array
  length equals that total.
so_what: >
  Do not label Candidate Radar, the 500-event Change Tape, or paid APIs PROVEN_LIVE
  from a 200 HTML shell. Repeat the tab census only after a site_full session
  hydrates workspace.json. A visible count of 0 on Candidate Radar is not
  EMPTY_VALID while HEAD candidate_count is 22.
kind: runtime
verified_at: 2026-08-16
verified_by: >
  Cursor same-origin fetch 2026-08-17T01:54:45Z: workspace.json/latest.json/candidates.json
  HTTP 401 locked authentication_required; /api/government-revenue/{latest,candidates,workspace,events}
  HTTP 401 missing bearer token; #gov-data parse events=2 total=500 next_cursor=djI6Mg;
  screenshots research/defense_intelligence/evidence/d0r-unentitled-*.png
scope: [macro]
confidence: verified
---

Anonymous 200 on government_revenue.html is the compact shell, not the entitled desk.
