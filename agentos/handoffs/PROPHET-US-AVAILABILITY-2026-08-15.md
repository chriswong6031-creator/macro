---
workstream: WS:PROPHET-US-AVAILABILITY
session: cursor/daily-cron-sibling-concurrency-cae8
model: local
ended_because: complete
prs: [5723]
decisions: [DEC:DAILY-CRON-SLOT-CONCURRENCY-GROUPS]
discoveries: [DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING]
mission: >
  Stop daily.yml's EST-guard cron from concurrency-superseding a queued EDT
  nightly, and stop watchdogs from reading a gate-skip success as "the nightly ran".

state_before: >
  2026-08-14/15 US nightly did not run. EDT run 31848262472 (cron-delayed to 22:52Z)
  sat queued and was cancelled superseded at ~23:45Z by EST-guard 31851452961.
  The survivor skipped every real job and concluded success. cancel-in-progress
  was already false. No prophet-outage issue was open at 02:20Z. Fusion PR-1a
  §13.0 live-accrual closure stayed OPEN (first post-#5604 curated stamp still owed).

changed:
  - path: .github/workflows/daily.yml
    what: >
      Per-cron concurrency groups keyed on github.event.schedule; run-name embeds
      the fired cron; cancel-in-progress stays false; et_gate and both crons unchanged.
  - path: scripts/prophet_rescue.py
    what: >
      Gate-skip classifier (run-name cron or <=3min span); any_success ignores
      skips; STALE fires at the strand deadline once nothing is in flight.
  - path: scripts/check_nightly_liveness.py
    what: >
      Same classifier; a gate-skip success is not baked, so the 08-14/15 shape
      pages NO SUCCESS rather than RAN GREEN BUT DID NOT ADVANCE.
  - path: tests/test_daily_et_gate.py
    what: Pins distinct groups for the two crons and watchdog cron lockstep.
  - path: tests/test_prophet_rescue.py
    what: Pins cancelled-real + surviving-noop at 02:40Z as STALE/dispatch.
  - path: tests/test_nightly_liveness.py
    what: Pins the same shape as NO SUCCESS, not DID NOT ADVANCE.

verified:
  - claim: EDT and EST cron expressions evaluate to different concurrency groups
    command: TZ=UTC python3 -m pytest tests/test_daily_et_gate.py -q --tb=short
    result: 12 passed (includes test_dst_cron_slots_do_not_share_a_concurrency_group)
  - claim: cancelled-real + gate-skip is not a bake in rescue or liveness
    command: TZ=UTC python3 -m pytest tests/test_prophet_rescue.py tests/test_nightly_liveness.py tests/test_workflow_file_size.py -q --tb=short
    result: 116 passed; nightly-liveness --selftest PASS; daily.yml 469532 bytes (under 487000)

unverified:
  - claim: GitHub still evaluates format() + event.schedule the same way the test interpreter does
    what_would_verify: First scheduled pair after merge — EDT and EST-guard runs show different concurrency groups in the Actions UI and the queued EDT run is not cancelled when the EST-guard fires
  - claim: Fusion PR-1a §13.0 live-accrual closure
    what_would_verify: First real post-#5604 daily.yml completion stamps a fresh curated date in data/us_prophet_rank/candidates. This PR does not close that.

unresolved:
  - "Prophet Conditional Fusion PR-1a §13.0 remains OPEN pending the first real nightly (agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-15.md). Do not close it from this lane."
  - "closing-bell.yml still uses one shared group for its DST pair; same pending-supersede shape is possible there. Out of scope for this isolated daily.yml fix."

next_actions:
  - "Merge this PR; do not re-dispatch a live daily.yml as part of the verify."
  - "On the next EDT evening, confirm the 22:30Z run is not cancelled when the 23:30Z no-op schedules."
  - "Leave Fusion §13.0 open until that real nightly lands a curated stamp."

do_not_redo:
  - "Do not put both daily.yml DST crons back in one concurrency group."
  - "Do not treat cancel-in-progress false as protection for a queued run."
  - "Do not cancel or re-dispatch a live daily.yml to prove this fix."
  - "Do not close Fusion §13.0 from a gate-skip success or from this PR."

danger_areas:
  - "daily.yml is near the 512KB silent-strand cliff (tests/test_workflow_file_size.py). Grow it only by replacing comments or extracting scripts."
  - "A gate outage now double-runs the two crons in parallel (distinct groups). Fail-open is intentional; rebase-retry is the race fence."
  - "run_started_at on a concurrency-queued skip equals created_at (31851452961 both 23:45:40Z). Do not classify skips by workflow wall-clock span."
---
