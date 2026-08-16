---
key: SYSTEMD-ONESHOTS-USE-TIMEOUTSTARTSEC
claim: >
  The live-plane and sibling oneshot units under app/deploy/ bound runtime with
  TimeoutStartSec (and Nice/CPU/Memory caps), not RuntimeMaxSec. A 2026-08-12
  grep of app/deploy/*.service for RuntimeMaxSec returns no matches.
falsifier: >
  rg -n RuntimeMaxSec app/deploy/*.service — any hit on a unit that existed
  before the MMX-001 backup lane disproves "no current unit uses it".
so_what: >
  New oneshot timers should copy TimeoutStartSec + resource caps from the
  nearest sibling (macro-sentinel.service) and add RuntimeMaxSec only when a
  plan explicitly requires it. Do not "fix" the other 18 units onto
  RuntimeMaxSec in the same PR as an unrelated lane.
kind: constraint
verified_at: 2026-08-15
verified_by: >
  rg RuntimeMaxSec app/deploy/*.service → no matches; rg TimeoutStartSec
  app/deploy/*.service → 16 units (sentinel 300, snapshot 420, bars 900, …)
scope: [macro, app/deploy]
confidence: verified
---

## Detail

`research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md` WS-1 says "RuntimeMaxSec set,
like all 18 current units". That sentence is wrong about the current tree: the
18 units use `TimeoutStartSec`. The backup lane therefore ships both
(`TimeoutStartSec=900` and `RuntimeMaxSec=900`) so it matches the idiom and
the written requirement.
