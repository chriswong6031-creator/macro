---
key: PROPHET-INDEX-PUBLIC-R2-TWIN
claim: >
  The full US Prophet plan book is anonymously world-readable: the public R2
  dev host (whose base URL ships in every page's head via
  templates/data_base.js:12) serves prophet/index.json at HTTP 200 —
  2,163,748 bytes, 262 plans with per-row entry, entry_zone, targets,
  invalidation, trigger, thesis and _priority_score — while the site origin
  401s the same path behind the regwall. The estate's own law already treats
  premium payloads as R2-forbidden (premiumdata/us_stocks.json and
  factordata/us_standouts.json are 404 on the same host); prophet/index.json
  is the anomaly. The P-MP1-SHELL migration (#6076) moved the page's paid
  boundary ONTO this artifact, so the server-side split it implements is
  bypassable in one unauthenticated GET. The leak predates the shell — the
  object has been published every nightly by scripts/build_prophet.py
  (R2_INDEX_KEY, :125).
falsifier: >
  An anonymous GET of
  https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json
  returning 401/403/404, or returning a redacted body without the per-plan
  actionable fields, retires the leak half. A ruling that /prophet/ is
  deliberately non-paid would retire the boundary half (and would need the
  origin regwall on the same path explained).
so_what: >
  ESCALATED to Sol + operator (Day-4 report). Remedy sketch, all server-side
  (no browser impact): (1) scripts/build_prophet.py publishes a REDACTED
  public stub (asof/counts/schema/ids only) for the plumbing that reads the
  public URL — scripts/prophet_rescue.py:131 (the stdlib-only watchdog; it
  needs staleness metadata, not plan rows) and scripts/build_prophet_marks.py
  (has a local-checkout fallback) — while the FULL index stays origin-gated
  (site/prophet/index.json behind the regwall, exactly like premiumdata);
  (2) the Terminal reads the full index via its own SERVER-side
  /api/flow route (charting-app terminal/app/api/flow/route.ts maps
  prophet_idx -> prophet/index.json — a Next.js server route that can carry
  credentials or fetch the gated origin); (3) delete the public object and
  verify 404. Cross-repo (charting-app) + Prophet-engine + rescue-watchdog
  surfaces — do NOT hotfix unilaterally; the rescue lane must never break.
  Until remediation lands, no §8b review may certify the plan-book boundary
  as unreachable (the #6076 certification records this withholding
  explicitly).
kind: constraint
confidence: verified
verified_at: 2026-08-20
verified_by: "curl -sS https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json (200, 2163748B, plans 262, fields incl. entry/targets/invalidation/thesis) vs the same path on www.mastermind-x.com (401); premiumdata/us_stocks.json + factordata/us_standouts.json 404 on the R2 host; producer scripts/build_prophet.py:125; base URL templates/data_base.js:12; readers scripts/prophet_rescue.py:131, scripts/build_prophet_marks.py:89-92, charting-app terminal/app/api/flow/route.ts:108"
scope:
  - "macro"
  - "terminal"
related:
  - "WS:PROPHET-US-V4-RECOVERY"
  - "WS:PROPHET-US-AVAILABILITY"
---

Found by the independent §8b reviewer during the P-MP1-SHELL certification
(Day-4, 2026-08-20). The #5840 ranked-board split and the premiumdata idiom
prove the estate already knows and enforces the "premium payloads stay off
public R2" law; this object slipped past it because the R2 publication
predates the artifact becoming a paid boundary. The certification for #6076
carries the load-bearing sentence: "no merge may cite this review as evidence
that the withheld plan rows are unreachable."
