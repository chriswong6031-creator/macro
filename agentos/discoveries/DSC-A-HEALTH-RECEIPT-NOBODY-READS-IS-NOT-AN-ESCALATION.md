---
key: A-HEALTH-RECEIPT-NOBODY-READS-IS-NOT-AN-ESCALATION
claim: >
  The polygon options accrual lane went dark on 2026-08-13 and stayed dark THIRTEEN days
  with perfect detection and zero alarm. Every night collectors/polygon_options.py
  classified all 5 probe symbols `auth_or_entitlement_failure`, fired its documented
  auth short-circuit, and scripts/build_polygon_gex.py filed a correct
  `nothing_captured`/`failed` health receipt with the full census — but the zero-capture
  branch only called `log.warning()`, and a logger can never become a GitHub annotation
  (the house log format prefixes the line, so "::error" lands mid-line and Actions drops
  it). The sibling universe-degraded branch 40 lines below already printed a real
  line-start `::warning`, so the LOUDER failure (vendor rejects every request) was the
  quieter one. The nightly kept committing `data: daily collection` every day, so every
  liveness instrument stayed green while the lane produced nothing. Two further traps:
  (a) `data/quality/options_accrual_audit.json` HAS carried `ok:false` +
  "CHAINS STALE" nightly since the outage began and is committed to the repo each night
  — an artifact nobody reads is not an alert either; (b) CORRECTED 2026-08-27 by the
  operator — this was never a credential outage. THETADATA is the canonical Mastermind
  options source (Chairman ruling 2026-08-22,
  DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA); Massive/Polygon is a STOCK-data source
  whose options entitlement 403'd on 2026-08-13/14, and the blocker asking for it back
  was RETIRED by that same ruling. THERE IS NO OPTIONS-ENTITLED KEY TO ROTATE. The key
  that looks "present and rejected" is the STOCK key — stock/news kept returning 200,
  which is why `accrue()` files receipts instead of returning its `no_key` status. So
  `auth_or_entitlement_failure` across the whole probe set is the EXPECTED steady state
  of a source that is dead by ruling, and the nightly annotation for that case is a
  `::notice`, not an `::error` — an error every night for a decided-dead lane is alarm
  fatigue and buries the real reds in this file.
falsifier: >
  A superseding Sol / WS:ADVANCED-DATA-OPTIONS decision that repoints the flow lane at
  the ThetaData spine or retires the boards would end this record's relevance; so would
  `ls data/polygon_gex/chains/` showing a file newer than 2026-08-13 (which would mean
  the retired estate came back, contradicting the 2026-08-22 ruling). The escalation half
  is falsified by the `_annotate_zero_capture` tests in tests/test_polygon_gex.py
  failing, or by `grep -n 'polygon-options-estate-retired\|polygon-accrual-dark'
  scripts/build_polygon_gex.py` returning nothing.
so_what: >
  FIRST: read the owning workstream and its DEC records before calling any dark lane an
  incident. This record exists because a session diagnosed a SETTLED, ADJUDICATED,
  RETIRED source condition as a fresh 13-day credential outage and shipped a "rotate the
  key" remediation — the ruling was already in agentos/decisions/ and in that session's
  own recalled memory. THETADATA is canonical for options; full options data is also
  available via Terminal. Then: do NOT re-audit board logic when a downstream book shows
  all-zero fires. Walk the chain — site/flowleaders/leaders.json `stale:true` is a FAIL-CLOSED refusal, not
  a bug, and `fire_a=0` on every row is its consequence (stale gates off the recurrence
  block, nulling A1_flow_recur and collapsing K_a). The 2026-08-26 experiments audit
  correctly flagged the artifact but its "possibly the two Leader Radar books / same
  08-12 date, check for a shared upstream" hypothesis is FALSIFIED: Leader Radar reads
  PRICES, site/leaderradar/radar.json is stale:false with price_through 2026-08-25, and
  its near_trigger rows sit at k_true=1 of n_avail=3 — genuinely unmet, not starved.
  Likewise the US pick-lab 4-session outage 08-03->08-06 is a DIFFERENT incident: there
  are no `data: daily collection` commits at all between 08-01 and 08-06 21:00, i.e. the
  whole nightly was dark, whereas the 08-13 freeze happened while the nightly ran
  normally every day. Do not write one fix for the two. Generally: when adding a
  fail-closed refusal, add the line-start annotation in the SAME change — detection
  without escalation buys nothing, and a health receipt, a committed `ok:false` audit
  artifact, and a green nightly can all coexist with a lane that has produced nothing
  for two weeks.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  data/polygon_gex_health/{2026-08-19,20,21,24,25}.json (all auth_or_entitlement_failure
  x5, 0 successes, nothing_captured); `git log origin/main --since=2026-08-13 --
  data/polygon_gex/` = empty; `git log origin/main --grep='data: daily collection'`
  daily through 08-26; scripts/build_polygon_gex.py:869-871 (no_key writes no receipt);
  scripts/build_flow_leaders.py:131-146,954; engine/pick_lab/candidates.py:846-935;
  site/leaderradar/radar.json (stale:false, price_through 2026-08-25);
  data/pick_lab/snapshots/2026-08.parquet (sessions 08-07..08-25, 08-03..08-06 absent)
scope:
  - mastermindx-market-intelligence/macro
  - collectors/polygon_options.py
  - scripts/build_polygon_gex.py
  - scripts/build_flow_leaders.py
  - scripts/audit_options_accrual.py
  - engine/pick_lab/candidates.py
confidence: verified
---

Related: [[DSC-A-SWALLOWED-AUTH-ERROR-PAINTS-A-LANE-GREEN]] — the same credential-class
failure painted green by a broad `except Exception`. That one hid the death of a WRITE
plane behind a per-item counter; this one hid it behind a correct, well-designed,
completely unread health receipt. Both cost ~13 days.
