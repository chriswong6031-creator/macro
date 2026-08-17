---
key: GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
claim: >
  An entitled site_full session unlocks Caddy cookie JSON
  (government-revenue-data/workspace.json 200, 500 events) while the same
  browser's cookie-only fetches to /api/government-revenue/* remain 401
  missing bearer token; attaching MDXAuth.client() access token makes those
  APIs 200.
falsifier: >
  From a signed-in government_revenue.html session, fetch
  /api/government-revenue/workspace with credentials same-origin and no
  Authorization header and receive 200, or fetch
  government-revenue-data/workspace.json without any session cookies and
  receive 200 with events.length=500.
so_what: >
  Candidate Radar (bearer queue) and Change Tape (cookie workspace) can
  disagree after sign-in. D1 must rehydrate radar on session, not assume
  cookie 200 implies API 200.
kind: runtime
verified_at: 2026-08-16
verified_by: >
  Chrome for Testing CDP 2026-08-17T04:41-04:45Z; sanitized
  research/defense_intelligence/evidence/d0r-entitled-api-census.json
scope: [macro]
confidence: verified
---

Cookie JSON and FastAPI bearer are separate entitled planes on production Government Revenue.
