---
key: ADJACENT-ARTIFACT-MONITORING-GREENLIGHTS-A-DEAD-LANE
claim: >
  Three independent instruments reported the US Prophet Live lane healthy for 27
  days because each graded a NEIGHBOURING artifact rather than
  live/prophet_live.json itself: the external dead-man graded quotes, breadth and
  CN Prophet Live; the VPS freshness sentinel graded live/us_board_provisional.json;
  and /api/status exposed six other live artifacts but not this one.
falsifier: >
  At macro@2f5b4d97c680, grep scripts/check_vps_live_health.py, app/main.py and
  scripts/freshness_sentinel.py for any check keyed on the US `prophet_live`
  artifact that reads its `meta.pass_ts`. Finding one disproves this.
so_what: >
  When a product lane ships, its monitor must name the EXACT artifact the product
  consumes. A check on a sibling written by the same timer proves nothing —
  us_board_provisional.json stayed genuinely fresh throughout this outage because a
  different lane writes it, and the sentinel entry that mentions prophet_live does
  so only in prose about board_state. Adjacency is the failure mode: every one of
  these instruments was working correctly and answering a question nobody had asked
  about the lane that was dead. Before accepting "lane X is healthy", confirm the
  check dereferences X's own artifact path.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  scripts/check_vps_live_health.py:66-246 — evaluate() inlines every check and
  contains cn_prophet_live at :169-179 with no US prophet_live grader;
  app/main.py:599-609 — the /api/status artifact tuple omits prophet_live.json;
  scripts/freshness_sentinel.py:407-410 — the entry is
  id=us_board_provisional, path=/live/us_board_provisional.json. VPS listing showed
  us_board_provisional.json fresh (mtime 2026-08-25T21:57Z) while
  prophet_live.json was absent from the served directory entirely.
scope:
  - macro
  - scripts/check_vps_live_health.py
  - scripts/freshness_sentinel.py
  - app/main.py
  - WS:PROPHET-US-AVAILABILITY
confidence: verified
---

A fourth instrument failed the same way in the other direction:
scripts/close_pass_mirror.py:179 discards `annotate_live_strip`'s boolean, so the
mirror's 27-day inability to find its target — the absent served
prophet_live.json — produced no signal at all. Its own module comment predicted
this ("its False return is discarded by the caller, so a dark surface leaves this
artifact looking perfect") and the prediction stood unacted-on.
