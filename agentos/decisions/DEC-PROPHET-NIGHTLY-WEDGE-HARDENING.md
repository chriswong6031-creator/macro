---
key: PROPHET-NIGHTLY-WEDGE-HARDENING
question: >
  After the 2026-08-14→17 outage (ruleset push-freeze + orphaned theta-m1 label
  turning collect_tail into a nightly concurrency hostage + every watchdog
  structurally quiet), what is the durable fix set — and which superficially
  attractive fixes are rejected?
answer: >
  Four changes: (1) collect_tail runs-on moves theta-m1 → macstudio (the
  probe-only/keep-last-real laws make store-less execution the designed degraded
  mode; re-pin when runner-policy's m1-theta canary graduates); (2)
  check_nightly_liveness gains IN_FLIGHT_MAX_AGE=14h (an in-flight run older
  than that is a WEDGED breach, not INDETERMINATE) and STALE_GRACE=10h (past
  boundary+grace with a read run list and nothing fresh alive, 1-behind
  breaches — closes the weekend hole), plus a third daily look at 20:00Z; (3)
  prophet_rescue §0.4a is amended: a PROVEN wedge (run ≥6h old, zero jobs in
  progress, every live job queued ≥3h, every input fail-closed via one
  alarm-path jobs read) no longer blocks dispatch — budget and floor still
  bind, nothing is ever stopped; (4) CLAUDE.md/AGENTS.md annotate the
  "no branch protection" law as externally violable with rulesets as the first
  push-failure diagnostic. Interim infra (runners API, receipted on issue
  #5742): theta-m1 restored onto mac-builder-3 (kept). A companion macstudio
  add to mac-builder-4 was REVERTED-AND-HARMFUL within the hour — mac-builder-4
  is the merge-control runner and merge-on-green's non-cone sparse checkout
  shares its work dir, so the first recovery dispatch's engine died at pip
  install in the thin tree (job 95550650855, 2.5 min); build labels and
  merge-control must not mix (postmortem follow-up 7).
rationale: >
  The hostage class must die at the root (an unschedulable job should be
  impossible, hence the unpin), the detectors must convert "eternally alive" and
  "weekend 1-behind" into pages (they were the two shapes that stayed quiet for
  four days), and the responder must be able to act through a hostage it can
  prove (its designed escape was "an operator look is owed", which took two
  days to arrive). Every threshold is far above healthy behavior: serial worst
  case through daily.yml's caps is ~13h vs the 14h age cap; a healthy Friday
  bake lands hours before boundary+10h; ordinary macstudio contention resolved
  in ~1h vs the 3h queue floor. A wrong WEDGED call costs a budgeted
  double-bake — the failure mode daily.yml's concurrency comment declares
  acceptable; a wrong ALIVE call cost four days.
alternatives: >
  (a) cancel-in-progress:true on the per-cron groups — REJECTED: a same-slot
  refire 24h later would guillotine a slow-but-alive bake; contradicts the
  documented double-run-never-zero-run law. (b) A wall-clock debris stand-down
  in et_gate — REJECTED: tests/test_daily_et_gate.py's delay-tolerance vector
  (a firing queued 5h must still proceed) encodes the same law; a late real
  firing may be the night's only bake. (c) Label-restore alone without the
  unpin — REJECTED as the fix (kept as the interim): API-only state,
  undocumented, silently re-driftable. (d) Letting sessions cancel hostage
  runs — REJECTED: §0.4c and gh_quota_guard shape 6 stay absolute; a kill is
  invisible to every staleness instrument.
evidence: >
  research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md;
  DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP;
  DSC:RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT; selftest + 142 lockstep
  tests green (tests/test_prophet_rescue.py, tests/test_nightly_liveness.py,
  tests/test_daily_et_gate.py, tests/test_workflow_file_size.py,
  tests/test_dag_conformance.py, tests/test_nightly_timings.py).
affects: [WS:PROPHET-US-AVAILABILITY, ".github/workflows/daily.yml", ".github/workflows/nightly-liveness.yml", "scripts/check_nightly_liveness.py", "scripts/prophet_rescue.py"]
confidence: high
reversibility: easy
decided_by: fable-prophet-outage-triage-fix-session
decided_at: 2026-08-17
---

The wedge thresholds (6h/3h/14h/10h) are calibrated to the 08-16/17 receipts
and the timings ledger, not to taste — see the constants' own comments. The
detection matrix (which instrument was quiet and why) lives in the postmortem.
