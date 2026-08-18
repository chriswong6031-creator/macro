---
key: PROPHET-US-AVAILABILITY
title: Prophet US never-stale availability program
objective: >
  Prophet US picks are produced and served for every NYSE session with automated
  detection, bounded self-heal, and loud escalation when unhealable — no outage ever
  again discovered by an operator looking at the site. Done = a full market week where
  every staleness/kill injection in the drill list is caught by an instrument (not a
  human) and healed or escalated within its deadline.
status: active
program: prophet-us
p0: PROPHET_US_AVAILABILITY
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: specified
next_action: >
  W3 (2026-08-17 outage hardening) is the live wave: land its PR, verify all five
  boards fresh, then fold the wedge/hostage classes into the W2 fire-drill list.
  W1 operator items stand: launchd installer; plus the new W3 operator asks on
  issue #5742 (cancel debris run 32077948964 post-recovery; census-lane cadence
  ruling; M1 host revival owns the collect_tail re-pin).
owns_paths:
  - scripts/prophet_rescue.py
  - .github/workflows/prophet-rescue.yml
  - tests/test_prophet_rescue.py
  - scripts/prophet_rescue_launchd.py
  - scripts/install_prophet_rescue_launchd.sh
  - scripts/prophet_rescue.launchd.plist
waves:
  - id: W0
    title: Response + resilience layers (rescue lane, hook protection, launchd pack, laws)
    status: in_progress
    next_action: >
      Land the availability-hardening PR (branch claude/prophet-us-availability-hardening);
      complements PR #5487 nightly-liveness (detection) — zero file overlap by design.
  - id: W1
    title: Operator acts — install launchd backstop; arbitrate the cancelling codex session
    status: todo
    depends_on: [W0]
    next_action: >
      Operator runs scripts/install_prophet_rescue_launchd.sh once on the Mac Studio;
      arbitration of codex session rollout-2026-08-11T04-10-51 (six receipted
      production-run kills) remains outstanding since 2026-08-12.
  - id: W2
    title: Fire-drill verification week
    status: todo
    depends_on: [W0]
    next_action: >
      Inject each failure class in staging form (stale fixture, mock cancelled run) and
      verify catch+heal+receipt paths — now including W3's wedge/hostage class (a run
      held alive by an unschedulable queued job) and the ruleset push-freeze class;
      then declare the workstream's done-bar met or iterate.
  - id: W3
    title: 2026-08-17 outage response — hostage-class + freeze-class hardening
    status: in_progress
    depends_on: [W0]
    next_action: >
      Merge the hardening PR (collect_tail unpin, liveness age-cap + weekend grace +
      20:00Z look, rescue §0.4a wedge amendment, law annotations, postmortem), verify
      all five Prophet boards fresh live, and hand the debris-run cancel + census
      cadence + M1 re-pin asks to the operator (issue #5742).
landmines:
  - "A queued job on a runner label with no live runner holds its RUN alive ~24h and the run holds its per-cron concurrency group — the next night pends with zero jobs (DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP). Check job runs-on labels against the live pool before any other diagnosis."
  - "A push-blocking ruleset kills publishes while builds stay green; `gh api repos/{o}/{r}/rulesets` is the FIRST check on mysterious GH013s (DSC:RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT)."
  - "Rescue §0.4a is amended (DEC:PROPHET-NIGHTLY-WEDGE-HARDENING): a PROVEN wedge dispatches through; everything unproven still refuses. Do not 'simplify' the fail-closed inputs."
  - "Top-level index.json asof is wall-clock — sentinels must read source_asof + cohorts (DSC:PROPHET-ASOF-IS-WALL-CLOCK)."
  - "Run conclusions decouple from Prophet delivery in both directions (DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET)."
  - "Never dispatch over a queued/in_progress daily run; never exceed the 2/night auto-budget — livelock and dispatch-storm classes are both measured, not hypothetical."
  - "2026-08-11 has no origination event and no bake-time board; backfill refused absent operator override (DEC:PROPHET-RESCUE-SEPARATE-FROM-LIVENESS alternatives)."
  - "GitHub concurrency supersedes PENDING runs even when cancel-in-progress is false (DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING). daily.yml DST crons must keep distinct groups (DEC:DAILY-CRON-SLOT-CONCURRENCY-GROUPS)."
do_not_redo:
  - "Do not re-investigate GitHub platform incidents for Aug 11-13 2026 — githubstatus history checked, zero Actions incidents; the outage was self-inflicted (workflow-size strand, fleet force-cancels, runner disk-full)."
  - "Do not build a second detection check duplicating PR #5487's run-created/run-concluded/source_asof arms."
  - "Do not 'fix' a queued daily.yml cancel by flipping cancel-in-progress or by putting both DST crons back in one group — that is the 2026-08-14/15 kill (DEC:DAILY-CRON-SLOT-CONCURRENCY-GROUPS)."
---

## Context

Born from the 2026-08-11/13 outage: two NYSE sessions with no fresh picks, discovered
by the operator. Full incident record + architecture:
`research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md`. Detection sibling:
PR #5487 (nightly-liveness). Related but distinct workstream:
WS:PROPHET-US-ENTRY-TIMING (signal quality, not availability).
