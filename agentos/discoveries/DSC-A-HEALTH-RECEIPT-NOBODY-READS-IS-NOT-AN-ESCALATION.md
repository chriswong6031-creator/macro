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
  — an artifact nobody reads is not an alert either; (b) the receipt's own existence is
  the diagnosis, because `accrue()` returns `{"status": "no_key"}` and writes NO receipt
  when the key is absent — so a receipt carrying 401/403 PROVES the key is present and
  the vendor is rejecting it, distinguishing "expired/de-entitled at the vendor" from
  "secret missing from the runner", which the reason code alone conflates
  (a missing key sends `apiKey=None` and also returns 401).
falsifier: >
  `python3 -m scripts.audit_options_accrual` exiting 0 with `ok:true`, or
  `ls data/polygon_gex/chains/` showing a file newer than 2026-08-13, or a
  data/polygon_gex_health/*.json attempt whose `failure_reasons` is not dominated by
  `auth_or_entitlement_failure`. Any of these means the vendor credential was rotated
  and the lane recovered. The escalation half is falsified by
  tests/test_polygon_gex.py::test_zero_capture_emits_a_line_start_error_annotation
  failing, or by `grep -n '::error title=polygon-accrual-dark'
  scripts/build_polygon_gex.py` returning nothing.
so_what: >
  Do NOT re-audit board logic when a downstream book shows all-zero fires. Walk the
  chain first — site/flowleaders/leaders.json `stale:true` is a FAIL-CLOSED refusal, not
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
