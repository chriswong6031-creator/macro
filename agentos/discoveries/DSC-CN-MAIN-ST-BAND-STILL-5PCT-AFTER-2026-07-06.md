---
key: CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06
claim: >
  The repo still applies a ±5% SSE/SZSE main-board risk-warning (ST/*ST) band
  with no era switch at 2026-07-06 — config/cn_limit_rules.yml carries the st
  rows as limit_up/limit_down 0.05 with valid_to null, and
  engine/china_microstructure.py's main-board width returns 0.05 for ST
  unconditionally — while the 2026 official SSE/SZSE rule revisions the R6
  program cites require ±10% from 2026-07-06, so every derived main-board
  risk-warning event label, breadth count, failed-seal, and ladder count from
  2026-07-06 onward is rule-stale and quarantined.
falsifier: >
  grep config/cn_limit_rules.yml for SSE/SZSE main-board st rows carrying an
  era boundary at 2026-07-06 with limit_up 0.10, and confirm
  engine/china_microstructure.py returns 0.10 for main-board ST sessions on or
  after that date; if both hold (P0-ST landed), this discovery is obsolete.
so_what: >
  Do not cite, grade, or train on post-2026-07-06 main-board risk-warning
  event labels from the microstructure tape or zt-pool-derived stores until
  wave P0-ST lands the effective-dated rule with an official-source receipt
  and a correction-receipted bounded replay. P0-ST is the program's P0 and the
  first runtime wave after R6-0. The official ±10% interpretation itself still
  owes its primary-source receipt inside P0-ST — this record pins the repo-side
  staleness, not the rule text.
kind: landmine
verified_at: 2026-08-19
verified_by: "grep config/cn_limit_rules.yml (sse/szse main st rows: 0.05, valid_to null); engine/china_microstructure.py:159 'return 0.05 if is_st else 0.10'"
scope:
  - macro
  - config/cn_limit_rules.yml
  - engine/china_microstructure.py
  - data/china_zt_pool/
confidence: verified
---

Coincidence worth knowing: engine/china_microstructure.py's
ST_STORE_COVERAGE_DATE is also 2026-07-06 (first date st_history covers) — the
same date the official band changed. A session grepping for the date will hit
the coverage constant first; it is not the rule-era switch, which does not
exist yet. Repair scope and acceptance live in
research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §P0-ST.
