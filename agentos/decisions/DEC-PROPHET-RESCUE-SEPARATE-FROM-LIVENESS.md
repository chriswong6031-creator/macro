---
key: PROPHET-RESCUE-SEPARATE-FROM-LIVENESS
question: >
  After the 2026-08-11/13 Prophet US outage, how should automated recovery be
  architected relative to detection — one organ or two, running where, with what
  authority?
answer: >
  Two organs, three survival domains. Detection = PR #5487's nightly-liveness (red
  check, zero side effects, blind→INDETERMINATE). Response = scripts/prophet_rescue.py
  + prophet-rescue.yml (GitHub-hosted ubuntu): artifact-truth staleness verdicts
  (source_asof + recorded_at cohort vs lib/nyse_calendar), bounded self-heal
  (re-dispatch daily.yml only; never while a run is queued/in_progress; auto-budget 2
  per night; zero cancel authority; API-dark → alert not dispatch), plus issue/webhook
  alerting and serve-split + zero-origination coverage detection. Survival = a
  host-local launchd twin (operator-installed, canonical GC-installer pattern) for
  GitHub-scheduler death, and both watchdog workflows added to the cancel-deny hook's
  PROTECTED_LANES.
rationale: >
  The outage had three independent kill classes (workflow-size cron strand, rogue
  fleet force-cancels, runner disk-full), and each surviving instrument shared fate
  with what it watched. A detector that also dispatches couples "cry-wolf gets muted"
  reporting discipline with recovery authority — #5487 chose INDETERMINATE-when-blind,
  which is correct for a check but fatal for a responder, so the responder is a
  separate organ with fail-toward-alert semantics. Re-dispatching the whole nightly
  (rather than a partial prophet-only lane) keeps the nightly the sole ledger advancer.
  Bounded budget + never-over-live-run prevents both dispatch storms and the measured
  2026-08-09 livelock class. Making force-cancels self-defeating (re-armed ≤1h,
  receipted in a public issue) addresses the one kill class no hook can technically
  fence (codex sessions honor no Claude hooks).
alternatives:
  - option: Extend #5487's check into a detect-and-respond organ
    why_not: >
      Couples reporting discipline with dispatch authority; collides with an armed
      in-flight PR (its ci.yml/legacy-jobs/house_law_checks hunks); and a red CHECK
      must stay side-effect-free to remain trustworthy in CI contexts.
  - option: Run recovery on the self-hosted Mac Studio pool
    why_not: >
      Fate-sharing — the pool's own death (disk-full 2026-08-13 14:29Z) is one of the
      failure classes being fenced. heartbeat.yml already demonstrates the blindness.
  - option: A prophet-only rescue bake lane (collect+prophet subset workflow)
    why_not: >
      Violates "nightly is the sole advancer of forward ledgers"; a second origination
      path is a contamination + double-advance risk for hours of saved latency.
  - option: Auto-backfill missed sessions after the fact
    why_not: >
      The backfill charter (#5305) authorizes replaying a real refused-origination
      event only; a night that never ran has no bake-time board — reconstruction is
      the contaminated-input class #5289 refused. 2026-08-11 stays a disclosed gap
      absent an explicit operator override.
  - option: Rely on GitHub-side protections against cancels
    why_not: >
      No GitHub permission granularity exists below actions:write for run
      cancellation; any fleet actor with the shared token can cancel. Only
      re-arm + receipts + operator arbitration address it.
evidence:
  - "research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md §1 incident table (receipted)"
  - "PR #5487 body — detection design, blind→INDETERMINATE rationale"
  - "gh run view 31649984834 / 31671422158 — delivery-vs-conclusion decoupling (DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET)"
  - "githubstatus.com incidents Aug-11→14: zero Actions incidents — outage self-inflicted"
  - ".claude/hooks/gh_quota_guard.py PROTECTED_LANES (#5488) — Claude-only binding, codex gap"
affects: [WS:PROPHET-US-AVAILABILITY, "scripts/prophet_rescue.py", ".github/workflows/prophet-rescue.yml"]
confidence: high
reversibility: easy
decided_by: fable-main-loop-availability-session
decided_at: 2026-08-14
---
