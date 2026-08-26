---
workstream: "WS:PROPHET-US-AVAILABILITY"
session: "claude/prophet-us-live-silent-freeze-20260826 (worktree prophet-us-force-majeure-541e4d)"
model: fable
ended_because: complete
mission: >
  Sol commission PROPHET-US-LIVE-FORCE-MAJEURE-2026-08-26: determine why US
  Prophet Live stopped updating, restore the lane, reconstruct every
  point-in-time-provable lost session, permanently eliminate the silent-freeze
  class, obtain real production proof, and update durable records.
state_before: >
  Commission scoped the outage to two sessions (2026-08-24/25) from an observed
  "last good ~Aug 21", cause unknown, timer suspected dead. No US Prophet-Live
  repair carrier existed. scripts/check_vps_live_health.py graded eight lanes but
  not US prophet_live; /api/status exposed six live artifacts but not
  prophet_live.json; the evaluator returned 0 on every publication failure.
changed:
  - path: scripts/prophet_live_evaluator.py
    what: >
      Publication is now a CONTRACT. publication_required()/no_publish_set()
      resolve an explicit mode (--dry-run, --no-require-publish,
      PROPHET_LIVE_REQUIRE_PUBLISH, PROPHET_LIVE_NO_PUBLISH kill switch) and
      default to fail-closed. Missing R2 client / failed live PUT / failed event
      spool with events / failed served write on a host that owns a live plane
      exit 3; unexpected exception exits 1 (was 0). Served-write obligation is a
      CAPABILITY test (parent dir exists), never host-name guessing, so runners
      are not failed for a directory they do not own. Partial effects are named,
      never blind-retried.
  - path: app/main.py
    what: >
      checks.prophet_live added to /api/status and ALWAYS emitted, including when
      the artifact is absent. Absolute clocks (pass_ts, quote_asof) with derived
      pass_age_min/quote_age_min; mtime demoted to served_age_min and never the
      truth signal; pack_ok compares pack_as_of to last_completed_session;
      aggregate counts only (public unauthenticated endpoint). expected_now comes
      from engine.prophet_live.live_states so no second holiday calendar exists.
  - path: scripts/check_vps_live_health.py
    what: >
      Dead-man grades the US lane during an expected session: absent /
      unparseable / stale pass_ts (>15m) / stale quote clock (>25m) / wrong pack
      basis / global darkness / missing producer. Deliberately NOT ABSENT-OK —
      a missing prophet_live key during the session is itself a failure. New
      _abs_age_min() refuses naive-local drift and unusable stamps.
  - path: tests/test_prophet_live_silent_freeze.py
    what: NEW 22-test hostile matrix; mutation-verified against pristine modules.
  - path: tests/test_prophet_live_vps_lane.py
    what: >
      Three contract tests re-pinned to the new exit codes (artifact invariants
      unchanged). Drive-by heal: the public-live inventory guard now compares
      Caddy against config/site_access.yml instead of a literal 4-file list that
      had gone stale and was red on main.
  - path: .github/ci/legacy-jobs.yml, .github/workflows/ci.yml
    what: suite wired into prophet-live P0 plus its retrigger paths (no dark tests).
  - path: research/PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md
    what: NEW Wave-A forensic freeze + Wave-C feasibility adjudication.
verified:
  - claim: "The outage is 27 days and ~18 sessions, not the commissioned 2."
    command: >
      R2 head of live_flow/prophet_live.json -> LastModified 2026-07-30T17:20:56Z,
      meta.pass_ts 2026-07-30T17:20:53Z, status=dark, 355 B.
  - claim: "The timer never died; the producer ran and exited 0 throughout."
    command: >
      systemctl is-enabled/is-active macro-live-prophet.timer -> enabled/active;
      Result=success ExecMainStatus=0; Persistent=no.
  - claim: "Initiating fault is unseeded R2 credentials at the 2026-07-30 cutover."
    command: >
      journalctl -u macro-live-prophet.service: oldest entry 2026-07-30T18:03:09Z
      is already 'no R2 credentials'; last non-skipped prophet-live.yml run
      2026-07-30T17:20:08Z; every scheduled run since is 'skipped'.
  - claim: "Credentials now work; the lane can publish."
    command: >
      Authenticated PUT/GET/DELETE of live_flow/_diag/prophet_live_write_probe.json
      -> PUT_OK, READBACK_OK (88 B), PROBE_CLEANED.
  - claim: "Pre-incident code called the exact production state healthy."
    command: >
      Executed HEAD:scripts/check_vps_live_health.py against a payload with the
      artifact frozen 27 days, globally dark, no producer -> NO FAILURE. Same for
      a missing prophet_live key. HEAD evaluator main() with a raising run() -> 0.
  - claim: "No historical armed packs are retained."
    command: >
      get_bucket_versioning -> not enabled; list_object_versions -> NotImplemented;
      live_flow/prophet* holds exactly 3 objects.
  - claim: "598 lost ledger keys are visible in the journal across 7 sessions."
    command: >
      journalctl EVENT lines -> distinct (date,ticker,kind): 07-31=90, 08-07=15,
      08-11=162, 08-14=143, 08-20=71, 08-21=31, 08-25=86.
do_not_redo:
  - "Do NOT treat 'nightly Prophet is fresh' as evidence the live lane is fresh — they are separate planes and the nightly stayed healthy through all 27 days."
  - "Do NOT use event-spool absence as evidence no passes ran: zero spool objects exist alongside ~1,500 in-window passes."
  - "Do NOT reconstruct the 11 Class-D sessions (08-03/04/05/06/10/12/13/17/18/19/24). Their dark verdict was CORRECT for the pack they were handed; recovering them means minting a pack production never armed."
  - "Do NOT write journal-derived rows to forward.parquet. The log omits `entered` and `via`, and `entered` is what separates a genuine cross from a board member's first-pass reading."
  - "Do NOT re-probe R2 for historical armed packs. Versioning is off and ListObjectVersions is unimplemented; the bytes do not exist."
  - "Do NOT re-litigate the ci-authority/codex/merge-queue-pilot red — it fails by design on every main-based PR."
danger_areas:
  - "live/prophet_live.json has exactly two lawful writers (evaluator + close-pass mirror CAS). Nothing in this wave adds a third; keep it that way."
  - "Manual workflow_dispatch of prophet-live.yml BYPASSES the VPS_LIVE_PRIMARY gate. Never dispatch it while the VPS timer can still publish — that is two writers on one object."
  - "Persistent=false on macro-live-prophet.timer is load-bearing and now test-pinned; a reboot must not replay stale live moments."
  - "The pack builder's as_of is the tip of the loaded close series (build_prophet_live_pack.py:167). It is VISIBLE now (pack_ok) but NOT repaired — it will recur."
next_actions: >
  1) Merge PR #6464 on concluded-green (merge-on-green armed; the codex pilot X is
     red-by-design), deploy to /opt/macro, and hold the §9 production proof during
     a real NYSE session: two consecutive natural invocations, advancing pass_ts,
     session_et = current session, pack_as_of = last completed session, R2 + served
     objects advancing, entitled product fetch, nightly board unchanged.
  2) Return the §25 continuation packet to Sol carrying the two operator items:
     the unattributed 2026-08-26T07:43:28Z credential seeding, and D12 ownership.
  3) Wave C remains GATED, not refused: the §13 control substrate is solved (the
     journal), but historical pack fidelity is unproven and no pack bytes survive.
     Any Wave-C session must run the §10.5 gate — reconstruct pack at D-1 vintage,
     reject unless cohort size matches the journal's checked+unchecked for that
     session, replay live_states over a delay-respecting quote view, reject unless
     the (ticker,kind) set matches the journal exactly — and refuse rather than
     widen. Lawful scope is the 7 Class-R sessions / 598 keys ONLY.
unverified:
  - "PR #6464 is BUILT_NOT_PROVEN: merged/deployed production behaviour is not yet observed. CI green is NOT production proof."
  - "The §9 live proof (two consecutive natural in-window invocations advancing the served and R2 objects) has not been held — the next NYSE window opens 13:25Z 2026-08-26."
  - "The 15m pass_ts and 25m quote thresholds are reasoned from the 5-minute timer and the lane's own freshness gate, but have not yet been observed against a full real session."
  - "Whether a reconstructed armed pack can reproduce production's cohort for any Class-R session is UNTESTED; §10.5 is the gate, not a result."
unresolved:
  - "Who seeded /etc/macro-live.env at 2026-08-26T07:43:28Z. It happened ~3 minutes before this session's first VPS connection, from this operator machine, with no PR or Agent OS record. Needs operator acknowledgement."
  - "D12 ownership: the armed pack's as_of inherits the close-series tip (build_prophet_live_pack.py:167). Visible now via pack_ok; unrepaired and will recur."
  - "Whether Wave C/D should proceed at all given no historical pack bytes survive — a Sol call, since the §24.2 stop condition is live."
  - "The 2026-07-30 tail after 17:20:56Z (~13:21-16:15 ET) is a partial lost session not classified R or D."
---

# US Prophet Live force-majeure — Wave A/B closeout

## The one sentence that matters

US Prophet Live published nothing for 27 days and ~18 NYSE sessions while the
timer fired every five minutes, the state machine computed correct verdicts, and
every health surface reported success — because the 2026-07-30 cutover made the
VPS the primary writer without seeding its R2 credentials, and nothing in the
estate graded this lane.

## Why the commissioned window was wrong

The commission scoped two sessions from an observed "last good ~Aug 21". The
served artifact's own clock says `2026-07-30T17:20:56Z`. The Aug-21 observation
was not the freeze onset — it is roughly when someone happened to look. Grading
an outage from the date a human noticed is exactly the failure
`WS:PROPHET-US-AVAILABILITY` exists to end.

## Session classification (binding for any backfill)

- **Class R — infrastructure loss, backfill lawful:** 2026-07-31, 08-07, 08-11,
  08-14, 08-20, 08-21, 08-25. Correct pack, correct tape, correct verdicts; only
  the PUT was impossible. 598 distinct `(date, ticker, kind)` keys.
- **Class D — correctly dark, backfill REFUSED:** 2026-08-03/04/05/06/10/12/13/
  17/18/19/24. The armed pack carried a same-day, weekend, or lagging `as_of`
  (924 `stale_pack` passes), so `dark` was the right answer for the pack handed
  to the evaluator. Reconstructing them means minting a pack production never
  armed — data manufacture, not infrastructure reconstruction, and outside
  `DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT`.

## What is proven vs merely built

`PR #6464` is BUILT_NOT_PROVEN until it is merged, deployed to `/opt/macro`, and
a real in-window pass advances the served and R2 objects. CI green is not
production proof and must not be reported as such.

The restoration precondition IS proven: authenticated PUT/GET/DELETE against the
production bucket succeeded with the now-seeded credentials, and today's armed
pack (`as_of=2026-08-25`) is correctly stamped, so the lane is not exposed to D12
for this session.

## Open operator acts

1. The four R2 keys appeared in `/etc/macro-live.env` at mtime
   `2026-08-26T07:43:28Z`, about three minutes before this session first
   connected to the host. This session did not perform that change and it has no
   carrier or record. It is currently the most load-bearing production change in
   the incident and needs acknowledgement.
2. D12 (pack `as_of` inherits the close-series tip) needs an owner. This wave
   makes it visible; it does not repair it.
