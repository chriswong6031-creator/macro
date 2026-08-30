---
key: SHARED-GITHUB-REST-BUDGET-MAKES-PER-SESSION-WATCHERS-A-FLEET-OUTAGE
claim: >
  Macro CI sessions using the same authenticated GitHub user consume one shared
  5,000-request core REST allowance. Long-running `gh run watch` loops and
  repeated `gh run view` censuses across independent reasoning sessions can
  exhaust that allowance, strand every session's GitHub control visibility and
  amplify token waste even though GitHub Actions itself continues running.
falsifier: >
  Run `gh api rate_limit --jq .resources.core` concurrently from separate
  Codex/Claude/Fable sessions using the same authenticated account and show
  independent `remaining` counters, or show that the 2026-08-27 HTTP 403 and
  `/rate_limit` receipt came from a GitHub Actions scheduler outage rather than
  an exhausted shared core bucket for user 292968551.
so_what: >
  Do not attach continuous per-session CLI watchers to CI. One owning session
  may take a bounded snapshot when a materially new event is expected; longer
  waits must use a sparse scheduled continuation or GitHub's own server-side
  status/notification surfaces. On quota exhaustion, stop all REST polling until
  the published reset time, preserve active runs, and never cancel/rerun merely
  to regain visibility. This is an operating rule inside the existing GitHub
  scheduler and Agent OS workstream, not a new queue or watcher database.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  On PR #6556 the sole local watcher for CI run 33079426385 exited at
  2026-08-27T14:22:41Z with HTTP 403 `API rate limit exceeded for user ID
  292968551`. One bounded `gh api rate_limit --jq .resources` receipt immediately
  afterwards reported core limit 5000, used 5000, remaining 0, reset 1787842510
  (2026-08-27T14:55:10Z), while GraphQL retained 4897/5000 and runner
  registration retained 10000/10000. A signed-in browser read showed the Actions
  run continued server-side after CLI visibility failed and later reached its own
  independent 30-minute job timeout.
scope: [macro, github-actions, "#6351", agent-sessions]
confidence: verified
---

## Incident receipt

The watcher used `gh run watch 33079426385 --exit-status --interval 30` and was
the only watcher owned by the #6351 coordinator. It contributed repeated REST
reads for roughly 25 minutes but could not by itself account for all 5,000 core
requests; multiple active sessions were already checking CI through the same
account. The correct attribution is shared polling amplification, not one job or
one model session acting alone.

The 403 stopped only client-side observation. It did not cancel the workflow,
change runner registration, consume M1/M4 capacity, mutate a PR head or alter
repository visibility. The active run remained visible through the signed-in
GitHub page and reached its separately configured timeout. All coordinating
sessions were told to stop `gh run watch`, repeated `gh run view` and periodic
core-API polling until reset.

## Durable operating law

CI ownership still belongs to one canonical carrier and GitHub Actions remains
the scheduler. The acceptance controller should react to terminal or materially
new receipts, not simulate a scheduler by continuously polling. A scheduled
continuation may perform one bounded census, record a new receipt, and end again;
unchanged state is not a reason to spend another reasoning turn or another burst
of API calls.
