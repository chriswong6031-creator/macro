---
key: GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200
claim: >
  After a site_full session that returns HTTP 200 for
  /api/government-revenue/candidates (total 22) and mapping-backlog (total 21)
  with the same content_id, the Candidate Radar tab still shows count 0 and a
  membership lock overlay with a View membership plans CTA.
falsifier: >
  On https://www.mastermind-x.com/government_revenue.html with the same
  /api/me tier=unlimited session, the Candidate Radar tab count equals the
  API total and the membership lock overlay is absent.
so_what: >
  Do not treat entitled API 200 as Radar-live. D1 rescue is rehydrate-on-auth
  (and stop membership copy on an already-entitled filmstrip), not a new
  candidate model.
kind: runtime
verified_at: 2026-08-16
verified_by: >
  Bearer census total=22 at 2026-08-17T04:45Z; screenshot
  research/defense_intelligence/evidence/d0r-entitled-desktop-candidates.png
scope: [macro]
confidence: verified
---

Entitled Candidate Radar is API-live and UI-locked.
