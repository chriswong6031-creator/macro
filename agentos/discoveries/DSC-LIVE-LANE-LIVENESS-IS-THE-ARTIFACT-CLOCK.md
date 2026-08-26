---
key: LIVE-LANE-LIVENESS-IS-THE-ARTIFACT-CLOCK
claim: >
  A VPS live lane's process health — timer enabled and active, service exit 0,
  journal "Deactivated successfully" — is fully independent of whether the lane
  published anything. The Prophet Live evaluator ran 108 clean passes per day for
  27 days (2026-07-30 to 2026-08-26) while publishing nothing to R2 and writing no
  served copy at all.
falsifier: >
  Run `journalctl -u macro-live-prophet.service --since '2026-08-21'` on the VPS and
  find any in-window pass in that window with a nonzero exit or a failed Result; or
  fetch `live_flow/prophet_live.json` and find `meta.pass_ts` advanced past
  2026-07-30T17:20:53Z before 2026-08-26.
so_what: >
  Grade a live lane on the ARTIFACT's semantic clocks — `meta.pass_ts`,
  `meta.quote_asof`, `meta.pack_as_of` — recomputed at read time from absolute
  timestamps. Never accept exit code, `systemctl is-active`, journal success lines,
  or file mtime as liveness evidence. File EXISTENCE is not implied either: the
  credential-less branch at scripts/prophet_live_evaluator.py:441 deliberately
  writes no served copy, so the served file was absent for the whole outage while
  the unit reported healthy. A monitor that grades mtime is defeated by any writer
  that touches a file without advancing its semantics.
kind: runtime
verified_at: 2026-08-26
verified_by: >
  journalctl on 146.190.142.17 showed 108 `Deactivated successfully` per day and 84
  `no R2 credentials` warnings per day on 2026-08-20/21/24/25 identically;
  `systemctl is-enabled/is-active macro-live-prophet.timer` = enabled/active;
  authenticated R2 GET of live_flow/prophet_live.json returned
  meta.pass_ts=2026-07-30T17:20:53Z, status=dark, 0 states. Code anchor:
  scripts/prophet_live_evaluator.py:440-448 (`if s3 is None: ... return 0`).
scope:
  - macro
  - scripts/prophet_live_evaluator.py
  - scripts/check_vps_live_health.py
  - scripts/freshness_sentinel.py
  - app/deploy/macro-live-prophet.service
  - WS:PROPHET-US-AVAILABILITY
  - WS:BREATHING-PLATFORM
confidence: verified
---

The inverse also holds and is the trap's second half: a fresh file mtime with an
ancient `pass_ts` must read as stale. Any writer that rewrites a document — the
close-pass mirror's CAS annotate, a deploy-time copy — refreshes mtime without
advancing the pass clock.
