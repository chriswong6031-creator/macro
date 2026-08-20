---
key: LIVE-BREADTH-EARLY-CLOSE-STILL-UNMODELLED
claim: >
  PR #6084 made scripts/live_breadth_poller.py's session_tag()/within_rth() consult
  lib.nyse_calendar.is_session(), which closes the FULL-DAY NYSE closure hole (Good
  Friday, Thanksgiving, observed Independence Day etc. previously returned "rth" at
  10:00 ET by clock alone). It did NOT model EARLY CLOSES, and this is a deliberate,
  recorded scope boundary rather than an oversight. lib/nyse_calendar.py is a
  SESSION-EXISTENCE authority only: is_session(d) answers whether a trading day
  exists, and the module exposes no half-day / early-close table and no per-session
  close time. On the ~3 early-close days a year (typically 1 Jul (day before
  Independence Day when it falls midweek), the Friday after Thanksgiving, and
  Christmas Eve) the NYSE closes at 13:00 ET, so between 13:00 and 16:00 ET
  session_tag() reports "rth" when the tape is in fact shut.
  The blast radius is BOUNDED and does not reopen the 0/0 defect: the browser gate
  now requires `usable === true`, and after the real close the vendor snapshot stops
  advancing, so source_age_min grows past the 25-minute SLA within about half an
  hour and the surface falls back to the baked nightly board on its own. The residual
  exposure is therefore a ~25-30 minute window after 13:00 ET on ~3 days a year in
  which a genuine last-print snapshot is labelled "rth" instead of "post", plus
  scripts/check_vps_live_health.py's 14..20 UTC live window demanding freshness on
  those afternoons and going red on a legitimately closed market.
falsifier: >
  lib/nyse_calendar.py growing an early-close table plus an accessor (e.g.
  session_close_time(d) or is_early_close(d)). The moment a canonical shared helper
  exists, session_tag()/within_rth() and check_vps_live_health.py's window should
  consult it, and this discovery is superseded. Conversely, finding an existing
  early-close authority already in the repo would refute the premise that none
  exists — grep for "early close"/"half day"/"13:00" under lib/ and engine/ first.
so_what: >
  Do NOT reimplement an early-close table inside live_breadth_poller.py — that is
  the second-calendar mistake the full-day fix explicitly avoided, and a private
  table drifts from whatever the nightly lanes use. The right repair is to extend
  lib.nyse_calendar once and let every consumer read it. Until then, expect and do
  not "fix" a health red on the ~3 early-close afternoons, and treat an "rth" label
  between 13:00 and 16:00 ET on those dates as known-wrong metadata rather than
  evidence of a producer fault.
kind: constraint
verified_at: 2026-08-20
verified_by: >
  lib/nyse_calendar.py:11 states outright that early closes (13:00 ET) are NOT
  modeled; grep for early.?close/half.?day/13:00 across that module returns only
  that disclaimer line, and the module exposes no close-time or half-day accessor.
scope: [macro, lib/nyse_calendar.py, scripts/live_breadth_poller.py, scripts/check_vps_live_health.py]
confidence: verified
metadata:
  type: discovery
---

Related: [[LIVE-BREADTH-VPS-LANE-MUST-NOT-GIT-PUBLISH]]
