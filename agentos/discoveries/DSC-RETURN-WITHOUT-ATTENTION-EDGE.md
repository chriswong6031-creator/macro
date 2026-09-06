---
key: RETURN-WITHOUT-ATTENTION-EDGE
claim: >
  A native worker can currently emit a company-level BLOCKED, DECISION_REQUEST or RESULT return and
  end its reasoning turn without proving that the exact current runtime has any armed continuation
  path back from Sol. This makes a semantically correct return operationally orphanable until the
  Chairman notices the missing attention edge. Return projection and continuation registration must
  become one governed outcome; a successful return without a delivery/wake/resume path is not a
  clean handoff.
falsifier: >
  Under real concurrent Codex/worker sessions, every actionable worker return either atomically
  establishes the accepted canonical continuation path to the exact current RuntimeBinding/current
  Attempt/Worker or emits a typed continuation-unavailable/degraded defect before the turn can be
  considered cleanly returned. Sol can reply without Chairman intervention and the exact original
  runtime receives/resumes from that edge; terminal STOP closes the bridge. No passive Slack/Linear
  scan, arbitrary replacement tab, or silent orphan is required.
so_what: >
  Do not rely on a worker remembering to create a watcher after it has already returned. Treat a
  temporary native watcher only as containment while the existing Agent Dialogue/WP-TW/Wake,
  RuntimeBinding/Operator Continuity and autonomous-delegation owners implement atomic return plus
  attention/delivery. If no current bounded wave owns the Sol-to-worker delivery half, record that
  as an explicit gap rather than inventing a watcher/session registry.
kind: runtime
verified_at: 2026-08-29
verified_by: >
  Live Codex task 01a04c44-7988-7da1-a05e-9ed43da374c0 and #agent-dispatch parent
  1787986955.050419: worker posted DECISION_REQUEST at 1787987543.919809 without an armed return
  path; Chairman intervention prompted later creation of sol-session-collision-binding-watch.
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - slack:#agent-dispatch
confidence: verified
---

## Evidence

The `CODEX_SESSION_COLLISION_REPAIR` native Codex task correctly returned
`DECISION_REQUEST ... RUNTIME_BINDING_RECONCILIATION_REQUIRED` with repository effect state `NONE`.
The return transferred turn ownership to Sol, but the task did not establish an attention path before
ending its turn. The Chairman then had to ask how the session would know when Sol replied. Only after
that prompt did the native task create and verify a direct exact-task watcher.

The defect is not that the eventual temporary watcher is invalid containment. The defect is that
**return and continuation setup were separable behaviors whose omission required Chairman detection**.

## Permanent acceptance law

- actionable worker return and continuation registration are one governed outcome;
- return cannot be considered clean when the exact current runtime has no delivery/wake/resume path;
- failure to establish that path must itself become a typed company-visible degraded/blocking return;
- no passive Slack, Linear or GitHub-comment scanning is required from the provider session;
- Sol continuation resolves through the exact current RuntimeBinding/current Attempt/Worker and
  canonical dialogue context;
- pre-effect authority is reread after resumption so stale cached instructions cannot mutate;
- temporary host-native watchers own no lifecycle, retry, completion or next-wave authority and are
  disarmed after terminal STOP;
- no new watcher registry, session database, inbox, scheduler or retry control plane is introduced.

## Current owners

Reconcile inside existing Agent Dialogue V2/WP-TW/Wake, RuntimeBinding/Operator Continuity,
Executive Attempt/Worker/fence authority, Agent Relay, and the autonomous-delegation AD-DLG/AD-RET
worker-continuation decomposition. If the exact Sol-to-worker native-session resume mechanism has no
current bounded implementation owner, preserve that as an explicit implementation gap.
