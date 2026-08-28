---
key: CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06
claim: >
  RESOLVED (PR #6047, P0-ST wave): the repo formerly applied an unconditional
  ±5% SSE/SZSE main-board risk-warning (ST/*ST) band with no era switch at
  2026-07-06 — this record's original falsifier has now fired. The repair
  landed a MAIN_ST_BAND_WIDE_DATE = 2026-07-06 era switch in
  engine/china_microstructure.py::limit_width_for_date (0.05 before that date,
  0.10 on/after) plus the matching config/cn_limit_rules.yml interval split
  (sse_main/szse_main st rows closed at valid_to 2026-07-05, new 0.10 rows
  opened at valid_from 2026-07-06), backed by official SSE/SZSE primary-source
  receipts. Bounded replay receipt:
  research/cn_limit/P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.md (+ .json) —
  census found ZERO persisted limit_width==5.0 rows and a zero-delta two-arm
  replay for the sole affected main-board name (600079.SS). A real
  asia-close LIVE PRODUCTION proof is still pending as of this record's
  verification date — do not treat this as fully closed until that proof
  lands.
falsifier: >
  grep config/cn_limit_rules.yml for SSE/SZSE main-board st rows carrying an
  era boundary at 2026-07-06 with limit_up 0.10 (superseding a closed 0.05 row
  at valid_to 2026-07-05), and confirm
  engine/china_microstructure.py::limit_width_for_date returns 0.10 for
  main-board ST sessions on or after MAIN_ST_BAND_WIDE_DATE (2026-07-06); both
  now hold. A later regression of either would re-open this discovery.
so_what: >
  Post-2026-07-06 main-board risk-warning event labels from the microstructure
  tape may now be cited as ±10%-band-derived (the code-level repair is landed
  and receipted) — the earlier blanket "do not cite" instruction is LIFTED for
  code/registry purposes. Still do NOT describe this as a proven-live
  production fact until a real asia-close run has been observed to produce
  correct post-07-06 main-board ST widths (packet §P0-ST); check for that
  live-proof note in a later handoff before upgrading this from
  "repaired in code, receipted" to "proven live".
kind: landmine
verified_at: 2026-08-19
verified_by: "PR #6047; engine/china_microstructure.py MAIN_ST_BAND_WIDE_DATE + limit_width_for_date era-dated main-board cell; config/cn_limit_rules.yml sse_main/szse_main st row split at 2026-07-05/2026-07-06; research/cn_limit/P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.{md,json}"
scope:
  - macro
  - config/cn_limit_rules.yml
  - engine/china_microstructure.py
  - data/china_zt_pool/
confidence: verified
---

Coincidence worth knowing: engine/china_microstructure.py's
ST_STORE_COVERAGE_DATE is also 2026-07-06 (first date st_history covers) — the
same date the official band changed. A session grepping for the date may hit
the coverage constant first; it is a DIFFERENT constant from the rule-era
switch (MAIN_ST_BAND_WIDE_DATE) that this record's repair introduced — do not
conflate the two. Repair receipt and gaps:
research/cn_limit/P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.md. Repair scope and
acceptance were originally scoped in
research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §P0-ST.
