---
key: GD1-EWY-IS-NOT-KOSPI-CASH
claim: >
  On 2026-08-18 the US-listed Korea ETF EWY closed -8.13% while Yahoo KOSPI
  (_KS11) for the Korea 2026-08-18 session closed -1.55%. Using EWY as the
  official Korea cash clock on that date is a wrong-clock join.
falsifier: >
  A vendor correction that revises either bar so the two same-session
  close-to-close returns agree within ordinary ETF tracking error (~1 pp),
  or an explicit documented corporate action that explains an 8-vs-1.5 gap.
so_what: >
  GD-1 / GD-2 regional contagion sentences must quote _KS11 (or a local
  000660.KS tape) for Korea cash and label EWY as a US-hours proxy. A
  "Korea -8% on 18 Aug" claim is not supported by the KOSPI bar.
kind: landmine
verified_at: 2026-08-19
verified_by: >
  data/yahoo/EWY.parquet 2026-08-18/17 close 170.05/185.10 = -8.13%;
  data/yahoo/_KS11.parquet 2026-08-18/14 close 6869.83/6977.94 = -1.55%
  (no 2026-08-17 KOSPI bar). 2026-08-19 KOSPI -4.75% on light volume.
scope:
  - macro
  - data/yahoo/EWY.parquet
  - data/yahoo/_KS11.parquet
  - WS:GREY-DEER-RISK-INTELLIGENCE
confidence: verified
---
