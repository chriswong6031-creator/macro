---
key: PUSH-TRIGGERED-FRESHNESS-PROOF-IS-SELF-LOCKING
claim: >
  integration-baseline.yml had no schedule trigger, so its green verdict could
  only be refreshed by a SOURCE push to main; because merges are what produce
  source pushes, any quiet main longer than merge_on_green's
  BASELINE_MAX_AGE_HOURS (6h) pauses every ordinary merge until the sweeper's
  own ensure_integration_baseline notices and dispatches — a self-locking
  circuit breaker whose only exit is a lagged self-rescue.
falsifier: >
  `gh run list --workflow integration-baseline.yml --limit 100 --json
  createdAt,conclusion` showing no green-to-green gap above 6h, or a sweep log
  reporting "baseline-blocked" for a reason other than "source main baseline is
  pending" while the newest green baseline is under 6h old.
so_what: >
  On a "nothing is merging" report, read the sweep log's circuit-breaker line
  BEFORE diagnosing PR checks: `integration-baseline is pending (newest
  concluded baseline is Nh old)` means main is fine and no PR is at fault, and
  the queue drains on its own within ~30 min. Do not heal packs, rebase PRs, or
  dispatch ci.yml in response to it. Any freshness-bounded proof refreshed only
  by the traffic it gates needs a clock trigger, not a faster detector.
kind: landmine
verified_at: 2026-08-19
verified_by: >
  Sweep run 32211895483 (2026-08-19T03:23Z): "integration-baseline is pending
  (newest concluded baseline is 6.5h old, past the 6h freshness bound
  (fda2cfee4cb8))" with all four armed PRs reported "source main baseline is
  pending; leaving it armed behind the circuit breaker", while the same log
  read "main proof: 18 clean name(s) at 71b3e926c407". Recurrence measured over
  the 99 completed runs from 2026-08-15T11:53Z to 2026-08-18T20:53Z: three
  green-to-green gaps crossed the bound (08-15 17:10->23:57Z 6.8h; 08-16
  20:43Z->08-17 02:43Z 6.0h; 08-18 20:53Z->08-19 03:22Z 6.5h), every one an
  overnight window. Self-rescue confirmed: ensure_integration_baseline
  dispatched 32211919276 at 03:22:43Z, green 03:35:52Z, breaker opened.
scope:
  - macro
  - .github/workflows/integration-baseline.yml
  - scripts/merge_on_green.py
confidence: verified
---

## The shape of the failure

`integration-baseline.yml` is the merge train's fast circuit breaker: it
publishes one cheap verdict after every source/control change on main, and
`merge_on_green` pauses ordinary merges while that verdict is pending or red.

Its freshness bound is not decoration. The path filter that triggers it is
explicitly *not* trusted to be complete — the workflow header names "a missed
path trigger, generated sibling drift, or a direct source/control-plane push"
as the class it exists to catch. So a green verdict expires: past
`BASELINE_MAX_AGE_HOURS` it stops counting.

The defect is that the only thing that could renew it was the same source-push
traffic the breaker gates:

```
no merges  ->  no source push to main  ->  proof ages past 6h
           ->  breaker pends  ->  no merges
```

Nothing inside that loop breaks it. What actually breaks it is
`ensure_integration_baseline` in `scripts/merge_on_green.py`, which dispatches
the workflow itself once it observes a stale green — a self-rescue bounded only
by the sweep interval, so the merge train stalls for up to ~30 min and the
sweep log reads exactly like a broken queue.

## Why the obvious cheaper fix is wrong

"Skip the age bound when main's SOURCE tree is unchanged since the last green
proof" removes the redundant re-proving and is tempting. It decides freshness
using the same path list that the bound exists to compensate for, so it
inherits precisely the blind spot the bound covers. A clock trigger cannot be
fooled by a path the filter forgot.

## Diagnostic

The sweep log answers this in one line, before any PR is opened:

```
integration-baseline is pending (newest concluded baseline is 6.5h old, ...)
PR #NNNN: source main baseline is pending; leaving it armed behind the circuit breaker.
main proof: 18 clean name(s) at 71b3e926c407, 3.2h old
```

`main proof: N clean name(s)` and `baseline is pending` together mean main is
green and the pause is the breaker's own staleness. No PR is at fault. Do not
heal packs, rebase branches, or dispatch `ci.yml --ref main` in response.
