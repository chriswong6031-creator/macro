---
workstream: WS:PROPHET-US-AVAILABILITY
session: claude/prophet-us-live-force-majeure-20260826
model: fable
ended_because: complete
mission: >
  Second, independent session on the same Sol force-majeure commission as #6464.
  After that PR merged mid-session, this wave was reduced to the residual gaps it
  did not close, plus the red it left on main.
state_before: >
  #6464 merged 2026-08-26T09:36:58Z, closing the evaluator exit contract, the
  /api/status projection and the dead-man grader. It left the initiating fault
  undefended in deploy, left three of the four blind instruments unaddressed, and
  left tests/test_vps_live_orchestration.py RED on main.
changed:
  - path: app/deploy/live-setup.sh
    what: >
      Idempotently seeds R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY /
      R2_BUCKET into /etc/macro-live.env from the already-provisioned
      /etc/macro-api.env. THE INITIATING FAULT'S DURABLE FIX — #6464 hardened the
      detection but not the provisioning, so a host rebuild reproduced the incident
      exactly. Logs a count, and key NAMES only on a gap, never a value.
  - path: scripts/freshness_sentinel.py
    what: >
      Grades /live/prophet_live.json on a 10-minute meta.pass_ts budget, gated on the
      NYSE window. This is the only lane that meets the commission's "≤2 monitoring
      cadences": macro-sentinel.timer is a real 15-minute systemd timer, whereas the
      GitHub heartbeat #6464 relies on measurably delivers every 26-105 min.
  - path: scripts/close_pass_mirror.py
    what: >
      run() no longer discards annotate_live_strip's result. Outcomes classified
      material (absent / unparseable / publish_served failed) vs benign
      (already-annotated / dry-run / CAS skip); only material ones are loud. The
      read-then-re-read-last CAS ordering is byte-for-byte unchanged.
  - path: scripts/build_prophet_live_pack.py
    what: >
      A failed or credential-less --publish returns 1. daily.yml's `if [ "$rc" -ne 0 ]`
      warning was unreachable dead code; the nightly board stays protected by that
      step's `set +e` / `exit 0`.
  - path: tests/test_vps_live_orchestration.py
    what: >
      HEALS MAIN. #6464 added the prophet_live grader requirement without giving this
      file's _healthy_vps_status() a healthy entry, so four tests asserted "no
      failures" against a payload the new grader correctly failed. Fixture completed,
      clocks stamped relative to a named instant so they cannot rot into a scheduled red.
  - path: tests/test_close_pass_lane.py
    what: "Mirror outcome tests; heals inventory copy 2 of 3 (see do_not_redo)."
  - path: tests/test_entry_radar_w4_lane.py
    what: "Heals inventory copy 3 of 3."
  - path: tests/test_freshness_sentinel.py
    what: "Sentinel grading tests incl. fresh-mtime-over-ancient-pass_ts."
verified:
  - claim: "main was RED on four tests in tests/test_vps_live_orchestration.py after #6464."
    command: "git worktree add --detach <tmp> origin/main && cd <tmp> && python3 -m pytest tests/test_vps_live_orchestration.py -q"
    result: "4 failed, 64 passed at pristine origin/main. After the fixture heal: 68 passed."
  - claim: "#6464 did not close the initiating fault, the sentinel gap, or the mirror gap."
    command: "git show origin/main:app/deploy/live-setup.sh | grep -c R2_ENDPOINT; git show origin/main:scripts/freshness_sentinel.py | grep -c PROPHET_LIVE_MAX_AGE"
    result: "0 and 0. #6464's file list contains neither live-setup.sh nor freshness_sentinel.py nor close_pass_mirror.py."
  - claim: "#6464 healed only one of the three copies of the reviewed public-/live/ inventory."
    command: "for f in test_prophet_live_vps_lane test_close_pass_lane test_entry_radar_w4_lane; do git show origin/main:tests/$f.py | grep -c intraday_quotes.json; done"
    result: "1, 0, 0 — the other two were still red."
  - claim: "All affected suites pass on the reconciled branch."
    command: "python3 -m pytest tests/test_vps_live_orchestration.py tests/test_freshness_sentinel.py tests/test_close_pass_lane.py tests/test_entry_radar_w4_lane.py tests/test_prophet_live_vps_lane.py tests/test_prophet_live_pack.py tests/test_prophet_live_evaluator.py tests/test_prophet_live_silent_freeze.py tests/test_check_script_import_pinning.py tests/test_deploy_update_self_heal.py tests/test_gh_annotation_line_start.py -q"
    result: "837 passed. agentos validate: 0 errors."
  - claim: "The host restoration works: the service builds an R2 client and the pipeline runs clean."
    command: "ssh root@146.190.142.17 'set -a; . /etc/macro-live.env; python -m scripts.prophet_live_evaluator --dry-run --now 2026-08-26T14:00:00Z'"
    result: "exit=0, NO `no R2 credentials` warning, session_et=2026-08-26, pack_as_of=2026-08-25."
unverified:
  - claim: "The restored lane publishes a non-dark artifact during a live NYSE session."
    what_would_verify: "Two consecutive natural macro-live-prophet.service invocations after 13:28Z, with served + R2 pass_ts advancing off the 2026-07-30T17:20:53Z baseline."
unresolved:
  - "Waves C/D (PIT replay + backfill) remain returned to Sol on EVIDENCE, not permission — zero prophet_live event objects have ever existed, so §13's mandatory known-good control cannot be constructed and §22 forbids effect without it."
  - "Two sessions were commissioned on the same packet and did not discover each other until a merge conflict. Neither packet named the other."
next_actions:
  - "Verify the first live publishing pass at/after 13:28Z with the staged /tmp/verify_live.py harness."
  - "Decide with Sol whether the lane simply begins accruing evidence from the first genuine session forward."
do_not_redo:
  - "Do NOT re-derive the root cause or re-open the exit-contract / status-projection / dead-man work — #6464 owns all three and its design is BETTER than the duplicate attempt: publication_required() defaults to True (opt-out), so it is armed in production, and check_vps_live_health.py stays stdlib-only per its own docstring instead of importing engine code."
  - "Do NOT add Environment=PROPHET_LIVE_REQUIRE_PUBLISH=1 to macro-live-prophet.service. It is redundant: main's evaluator already treats a real pass as owing publication unless explicitly opted out."
  - "Do NOT make check_vps_live_health.py import engine.prophet_live. It is deliberately stdlib-only so GitHub-hosted monitoring and an operator shell can run it bare; doing so also trips tests/test_check_script_import_pinning.py, which forbids call-time sys.path mutation in the guard family because a bare `python3 scripts/<name>.py` could then resolve a repo import against a FOREIGN tree."
  - "Do NOT heal only one copy of the reviewed public-/live/ inventory. There are THREE (test_prophet_live_vps_lane, test_close_pass_lane, test_entry_radar_w4_lane); a pack is one check, so partial heals deadlock. #6105 made /live/flow_pulse.json and /live/intraday_quotes.json public on purpose — this is bookkeeping, not a leak."
danger_areas:
  - "live/prophet_live.json has exactly TWO writers — the evaluator and close_pass_mirror's CAS annotate. Never add a third."
  - "macro-live-prophet.timer must keep Persistent=false."
  - "live-setup.sh must never log an R2 value; it logs a count, and key NAMES only on a gap."
  - "CI path scoping hid three red inventory tests on main for six days, and hid #6464's fresh red until a conflicting PR ran the pack. A suite that only runs when its lane is touched is not evidence that lane is healthy."
discoveries:
  - "DSC:LIVE-LANE-LIVENESS-IS-THE-ARTIFACT-CLOCK"
  - "DSC:ADJACENT-ARTIFACT-MONITORING-GREENLIGHTS-A-DEAD-LANE"
prs: [6470]
---

## Why this is a second handoff for the same day and workstream

Two sessions were commissioned on the same Sol force-majeure packet and ran
concurrently without either knowing. #6464 merged at 09:36:58Z, mid-flight here. Both
reached the same root cause independently — the 2026-07-30 cutover that made the VPS
primary without seeding its R2 credentials.

Rather than force a duplicate through a five-file conflict — which house law warns
silently reverts the better fix that landed behind you — this branch was reset to
origin/main and rebuilt as additive-only. Where the two designs overlapped, #6464's
was kept, including in the two places it is straightforwardly better (documented under
`do_not_redo`).

What remains here is the part of the incident #6464 did not close: the initiating
fault's durable fix in deploy, the two blind instruments beyond the two it addressed,
the latency lane that can actually meet the commission's cadence bound, and the red it
left on main.
