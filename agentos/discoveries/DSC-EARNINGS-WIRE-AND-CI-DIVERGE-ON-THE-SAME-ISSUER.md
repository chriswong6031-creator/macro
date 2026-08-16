---
key: EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER
claim: >
  On 2026-08-16 the public Earnings Wire and Company Intelligence latest_event
  are not the same event for the same ticker: LMND Wire is Q2 FY2026
  (2026-07-29) with exact span receipts while CI latest_event is Q1 FY2026
  (2026-04-29); AAPL CI has FY2026 Q3 (2026-07-30, cie_98e318c37ec1a2a1f83c45e1)
  while the expected Wire slug aapl-2026q3-call-record.html 404s; GOOGL CI is
  200 and GOOG CI is 404.
falsifier: >
  Fetch https://www.mastermind-x.com/stocks/earnings/lmnd-2026q2-call-record.html
  and GET /api/company-intelligence/LMND and show they share fiscal period and
  a joinable event id; fetch aapl-2026q3-call-record.html as 200 with the same
  cie_ as the AAPL CI latest_event; GET /api/company-intelligence/GOOG as 200
  aliased to the GOOGL issuer event.
so_what: >
  E1 must join Wire evidence and CI context through canonical issuer event ids.
  A CI generated_at of today does not mean latest_event is the live call.
  Dual-class listings cannot be assumed to exist as CI objects.
kind: runtime
verified_at: 2026-08-16
verified_by: >
  WebFetch live Wire index (3361 records), lmnd-2026q2-call-record.html,
  iex-2026q2-call-record.html, aapl-2026q3-call-record.html 404,
  GET /api/company-intelligence/AAPL|LMND|GOOGL 200 and GOOG 404 on 2026-08-16.
scope:
  - macro
  - terminal
  - earnings-intelligence
  - templates/earnings_wire/**
  - engine/company_intelligence/**
  - app/company_intelligence.py
confidence: verified
---

## Boundary

This does not say the Wire or CI builders are idle. It says they do not share
an event identity or a freshness clock, so E1 cannot treat either plane as
proof the other is current.
