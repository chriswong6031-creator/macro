---
key: RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT
claim: >
  A repository ruleset that blocks pushes to main (GH013 "Changes must be made
  through a pull request") kills every bot-publish lane while every BUILD
  instrument stays green: the engine builds boards correctly, its push retries
  exhaust (12/12) hours later, the run goes red on a step nobody watches, and
  data-freshness watchdogs attribute the staleness to a bake problem that does
  not exist. Rulesets are invisible to normal triage because the standing law
  says "main carries no branch protection" — true in the NORMAL state and
  falsifiable at any moment by an org admin (or automation) minting a ruleset.
  Detection signature: dashboard-bot commits/day collapsing (251 → 8 → 1 → 0
  across 08-13→08-17) while PR merges continue normally.
falsifier: >
  A GH013 push rejection on main while `gh api repos/{o}/{r}/rulesets` returns
  empty (would mean a second blocking mechanism this record does not name), or
  bot pushes succeeding while a push-blocking ruleset is active (bypass list
  broader than believed).
so_what: >
  On ANY mysterious push failure to main — especially "N attempts failed" from a
  retry loop that normally wins — run `gh api repos/{o}/{r}/rulesets` FIRST,
  before diagnosing the pipeline. Watch dashboard-bot commit cadence as the
  cheap canary. A deliberate freeze owes a DEC record + expiry plan (AGENTS.md
  §merge discipline, amended 2026-08-17); an undocumented one is an incident.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  Run 31913143619 engine log: "12 attempts failed … engine worktree could not be
  made byte-equivalent to accepted main; derived ledgers withheld"; ruleset
  ci-recovery-bootstrap-freeze-2026-08-15 (id 20878487, created 08-15 01:20Z,
  bypass OrganizationAdmin) confirmed deleted 08-17 ~23:40Z (GET /rulesets →
  []); commit-rate collapse measured by peer session (issue #5742 thread).
  research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md.
scope: [macro, terminal, mastermind]
confidence: verified
---

Credit: the ruleset root cause was isolated by the peer triage session
(prophet-picks-update worktree) while this session independently isolated the
queued-job hostage (DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP). The
two failures stacked: the freeze stopped publishes 08-15→17, the hostage kept
the nightly from even running on time, and the watchdog blind spots (fixed in
DEC:PROPHET-NIGHTLY-WEDGE-HARDENING) let both run for days.
