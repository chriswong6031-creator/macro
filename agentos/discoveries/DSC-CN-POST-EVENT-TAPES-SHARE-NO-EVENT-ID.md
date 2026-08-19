---
key: CN-POST-EVENT-TAPES-SHARE-NO-EVENT-ID
claim: >
  China already collects the vintages of an A-share earnings event
  (disclosure booking with revisions, 业绩预告, 业绩快报, CNInfo
  announcement metadata including inquiry/reply kinds, 互动易 and
  上证e互动 Q&A with keep-LAST answer correction) but no module joins
  them under a canonical_event_id. The 快报 parquet has no engine
  consumer. Earnings OS event_workspace.v1 cannot mint those issuers
  because company_id is CIK-only.
falsifier: >
  A grep that finds a function constructing event_workspace.v1 or
  company_event.v1 for a non-CIK listing_id, OR an engine/scripts
  reader of data/china_preannounce/preliminary.parquet other than
  collectors/china_preannounce.py, OR a shared event_id column
  present on china_earnings + china_preannounce + china_filings +
  china_irm.
so_what: >
  A future session that needs China post-event reinterpretation must
  not mint china_corporate_event.v1 (#5822) or another collector. It
  routes an Earnings OS E-wave after E2 that adapts existing tapes
  onto event_workspace.v1 with a listing identity. Do not treat 快报
  as "not collected".
kind: architecture
verified_at: 2026-08-19
verified_by: >
  collectors/china_earnings.py:7-14;
  collectors/china_preannounce.py:4-13,30-31;
  engine/china_special_situations.py:550-552;
  collectors/china_filings.py:8-16,138-178;
  collectors/china_irm.py:35-41;
  collectors/china_einteraction.py:42-48;
  engine/company_intelligence/events.py:6-14,43-55;
  engine/company_intelligence/identity.py company_id_for_cik;
  research/earnings_intelligence/ grep of China/A-share = 0 hits
scope:
  - macro
  - earnings-intelligence
  - china-system
  - WS:EARNINGS-INTELLIGENCE-OS
  - research/alpha_intelligence/censuses/G0/**
confidence: verified
---

G0 census finding. The missing object is a join, not a scrape.
