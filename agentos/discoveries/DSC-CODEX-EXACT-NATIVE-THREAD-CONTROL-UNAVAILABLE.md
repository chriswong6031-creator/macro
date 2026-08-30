---
key: CODEX-EXACT-NATIVE-THREAD-CONTROL-UNAVAILABLE
claim: >
  The currently available Mac-Studio ChatGPT.app/Codex GUI/AX/OCR control surfaces cannot mechanically
  address and verify an exact Codex native task UUID before click/type. Process presence, task-owner
  locks, visible CTO/OCR labels, window order, front-window state and composer visibility are not exact
  reasoning-session identity. Current first-party Codex source now exposes a separate Unix-socket
  app-server control transport that may become an exact current-writer attach seam, but that seam is
  not yet proven against the Chairman's existing Desktop tasks.
falsifier: >
  The GUI/AX negative control is falsified only by an accepted host path that mechanically verifies the
  exact current writer before input without title/newest-tab/window-order selection. The newly identified
  Codex Unix control socket is a candidate, not yet falsifying evidence: a canary must tie socket inode/path,
  owner process generation and exact loaded thread to the canonical current RuntimeBinding, then reach
  MAS-229 TARGET_ACKNOWLEDGED without creating or replacing a writer.
so_what: >
  Do not build or commission title/OCR/newest-tab GUI foregrounding, arbitrary deep-link navigation,
  cold CLI resume or a new standalone App Server as the Mastermind continuity primitive. Prefer passive
  proof of the current owning Codex App Server through the supported Unix control transport when and only
  when the current Desktop/runtime owner actually exposes it. Missing/unbound control transport is a
  blocker, not authority to bootstrap/restart another writer.
kind: runtime
verified_at: 2026-08-29
verified_by: >
  Slack #agent-dispatch attention experiment autonomy-native-cto-attention-recovery-20260829-sol-001
  on C0BSBM78V1N/1788044952.704639; Grok Secretary RESULT 1788045667.435029; terminal Sol STOP
  1788045714.266989; Mastermind #212 durable discovery comment 5465473258; MAS-237 and MAS-229
  selective Linear projections; current first-party openai/codex app-server transport and daemon source
  at b8c86376a258e55efc8e5ecfbabc21c16c07d814; Mastermind Wake PR3 plan #249.
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - slack:#agent-dispatch
  - MAS-237
  - MAS-229
confidence: verified
---

## Evidence

The 2026-08-29 Codex continuity incident first showed that a valid Slack `DIRECT_TARGETED` handoff to
an exact historical native task ID did not cause an idle Codex reasoning session to consume the
operation. Manual human foregrounding caused ORION, SENTINEL and TRACE to immediately reconcile their
existing canonical carriers and emit real ACK/WATCH_ARMED/START, proving that delivery quality and
handoff content were not the missing state transition.

After a Mac-Studio crash/restart, the original FORGE task
`01a04bdf-7a7b-7f63-9abd-9a7c13e944c0` still had owner-lock/process evidence and surviving local
worktrees, but its already-STARTed MAS-237 and CI-Quiescence repair children could not be assigned a
known post-crash effect. Both were correctly parked `EFFECT_UNKNOWN / RUNTIME_BINDING_RECONCILIATION_REQUIRED`
rather than replayed or failed over.

Sol then commissioned one bounded exact-native attention experiment to the existing Grok/Cursor Mac
surface. At action time Grok revalidated:

- `/Applications/ChatGPT.app`, bundle `com.openai.codex`;
- the existing Codex helper process;
- the signed Peekaboo/native observation surface;
- the exact four intended native task UUIDs and their canonical Slack principal carriers.

The available AX/UI surface exposed only window chrome. Native task UUIDs were not AX identifiers.
Visible OCR labels (`CTO-ORION`, `CTO-SENTINEL`, `CTO-Trace`, `CTO FORGE`) did not prove which exact
native conversation owned the composer. Window position, front-window state and process PID were also
insufficient. The worker therefore made **zero click/type submissions**, returned
`BLOCKED EXACT_NATIVE_THREAD_CONTROL_UNAVAILABLE`, and Sol terminally STOPped the experiment.

This remains a useful negative control: a UI that can see a Codex window is not an exact-session
control surface.

## 2026-08-29 first-party control-transport correction

Fresh current-source archaeology against public `openai/codex` found a supported non-GUI seam that
was not part of the original negative experiment.

Current `codex app-server` documents these local transports:

```text
stdio                 default
unix://                supported local control transport
$CODEX_HOME/app-server-control/app-server-control.sock
codex app-server proxy -> one raw stream to that socket
```

The first-party documentation says the Unix socket is intended for local app-server control-plane
clients. The same App Server exposes `thread/loaded/list`, `thread/read`, `thread/resume`,
`turn/start`, and `turn/completed`.

The first-party app-server daemon also:

- passively probes the socket;
- tracks its own PID/backend and managed binary identity;
- refuses to restart/stop an app server found on the socket when that process is not daemon-managed;
- treats daemon bootstrap/start/restart as explicit lifecycle effects.

This changes the search space but **does not falsify the discovery yet**. The Chairman's current
Desktop/Codex tasks have not been proven to be hosted by that daemon/socket, and a default socket path
without owner/process-generation proof is not current-writer identity.

The accepted candidate falsifier is now:

```text
passive host probe
-> exact current CODEX_HOME
-> exact Unix socket inode/path
-> exact owning App Server process generation
-> initialized read-only control connection
-> thread/loaded/list proves bound native thread loaded in that process
-> RuntimeBinding proves same current writer
-> re-prove immediately before one persisted Wake provider submission
-> MAS-229 TARGET_ACKNOWLEDGED
```

If the socket is absent, belongs to another process generation, or cannot prove the exact bound
thread is loaded, the result remains `SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED`.
Do **not** invoke `codex remote-control start`, daemon bootstrap/restart, a fresh standalone
`codex app-server`, cold `codex resume`, or GUI fallback merely to make a control endpoint appear.
Those would create/replace a writer while the prior writer may still be live/effect-unknown.

## Consequence

Do not infer or implement any of the following as continuity truth:

- visible CTO/chat title => exact native task;
- newest/front tab => currently sanctioned worker;
- task-file/owner-lock presence => reasoning turn consumed the latest obligation;
- Slack delivery / `ACT NOW` => ACK or START;
- composer visibility => safe exact-thread input target;
- a new `codex resume` process => continuation of a started/effect-unknown original writer;
- a persisted thread readable from a fresh App Server => same current writer;
- default Unix socket path => current writer without inode/process/thread-loaded proof.

A future native control bridge is lawful only if it verifies the exact canonical current session
**and current writer endpoint** before input through the accepted RuntimeBinding/continuation owner.
GUI automation remains rejected; the Unix control transport remains `CANDIDATE / NOT_PROVEN_LIVE`.

## Repair path

Preserve the existing single-owner sequence rather than creating another registry or watcher plane:

1. `MAS-237` projects the one current writer to an ABA-safe RuntimeBinding from existing Executive /
   Operator Harness / provider-session truth, including enough runtime-only endpoint/process-generation
   evidence to distinguish the current writer from a cold-resumed duplicate.
2. A passive W3C host falsifier may adopt the first-party Unix control socket only if it proves that
   socket/process owns the exact bound loaded thread. It performs no bootstrap/restart/create effect.
3. Wake delivery targets that current binding/owner endpoint; delivery alone remains
   `DELIVERED_UNACKNOWLEDGED`.
4. `MAS-229` validates exact target consumption under the same accepted binding and persists the
   existing `TARGET_ACKNOWLEDGED` phase.
5. Existing source-resolution law follows with `SOURCE_RESOLVED`.
6. The production canary must prove a sleeping/current Codex target consumes the wake and returns the
   exact ACK without Chairman/manual tab hunting or a second writer.

Related procedural mitigation is protected Mastermind #248 / `0604158caca9e3b8a43ec57dd36ca4dadf05198b`:
watcher prompts are attention rather than surviving scope fences, Class-M reasoning wakes are
resource-bounded, carrier freshness is mandatory, and stopping one child source cannot kill an
independent aggregate CTO/principal watcher. That procedural protection does not substitute for
MAS-237/MAS-229 runtime proof.
