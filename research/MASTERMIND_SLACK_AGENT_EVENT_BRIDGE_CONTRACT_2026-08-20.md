# Mastermind-X Slack Agent Event Bridge Contract

**Status:** architecture contract / MVP boundary · 2026-08-20  
**Authority:** records only; does not itself start or dispatch work  
**Owning boundary:** transport belongs in the Mastermind execution/control plane, not Agent OS  
**Linear rollout:** `MAS-9`  

## 0. Purpose

Slack is Mastermind-X's **human-visible communication and event transport plane**. It lets Chairman/Sol seats, orchestration lanes, workers, and operators exchange bounded dispatches, acknowledgements, progress, results, and cross-program intelligence without treating a chat transcript as durable organizational truth.

The missing capability is not “send a Slack message.” It is the bridge that makes a Slack event durable, routable, attributable to a canonical workstream, visible to the target runtime when that runtime can actually consume it, and reconciled back into Agent OS/GitHub/Linear.

## 1. Non-negotiable boundary

**Slack delivery is not agent runtime delivery.**

A Slack message can arrive at an employee account while a ChatGPT/Claude/Fable browser session remains completely unaware of it. Therefore these are distinct facts:

- message posted;
- bridge received event;
- event validated/routed;
- target seat inbox contains event;
- runtime/session actually received event;
- target agent ACKed mission;
- work ran;
- result returned;
- canonical state changed.

No shortcut may collapse those states.

## 2. Channel topology

The initial control-plane topology is intentionally small:

| Channel | Purpose |
|---|---|
| `#ceo-control-room` | Chairman/Sol executive decisions, escalations, cross-program status |
| `#agent-dispatch` | structured dispatch → ACK → progress → result threads |
| `#build-events` | GitHub/CI/production-validation event feed; low discussion |
| `#company-intelligence` | significant discoveries crossing program boundaries |

Do not create one Slack channel per Agent OS workstream by default. Threads carry bounded execution conversations; Agent OS carries durable state.

## 3. Durable seat vs temporary role

Authentication identity and session role are separate.

A durable seat such as `chatgpt-1`, `chatgpt-2`, or `chatgpt-3` may run different roles over time (`ceo-sol`, reviewer, researcher, etc.). The event bridge resolves Slack identity to a durable seat first, then evaluates the role/authority requested by the dispatch.

Slack sender identity is provenance, **not authority**. Mastermind's authority map decides whether that seat/role may issue the requested action.

## 4. Dispatch envelope

Every accepted dispatch mints one immutable `mastermind.dispatch.v1` envelope:

```json
{
  "schema": "mastermind.dispatch.v1",
  "event_id": "evt_<uuid>",
  "dedupe_key": "sha256:<canonical-envelope>",
  "created_at": "ISO-8601 UTC",
  "source": {
    "kind": "slack",
    "workspace_id": "T...",
    "channel_id": "C...",
    "thread_ts": "...",
    "message_ts": "...",
    "sender_slack_user_id": "U...",
    "sender_seat": "<durable-seat>"
  },
  "routing": {
    "workstream": "WS:<KEY>",
    "linear_issue": "MAS-123|null",
    "target_role": "ceo-sol|coo-fable|researcher|builder|reviewer|operator",
    "target_seat": "<optional durable seat>",
    "runtime": "chatgpt|claude|grok|codex|local|operator|unknown"
  },
  "mission": "bounded executable instruction",
  "authority": "research|build|review|operator|decision",
  "priority": "urgent|high|normal|low",
  "acceptance": ["observable completion conditions"],
  "do_not": ["explicit scope fences"],
  "artifacts": ["canonical repo paths / PRs / Linear references"],
  "expires_at": "optional ISO-8601 UTC"
}
```

For substantive project work, `workstream` is mandatory and must resolve against Agent OS. An unknown/missing `WS:<KEY>` fails into a typed unrouted queue; the bridge never invents work identity.

A genuinely tiny maintenance action may use an explicit typed maintenance exception, but the exception is not a generic loophole.

## 5. Transport lifecycle

Transport state is separate from workstream state:

`RECEIVED → VALIDATED → ROUTED → QUEUED → RUNTIME_VISIBLE → ACKED → RUNNING → RESULT | FAILED | EXPIRED`

Definitions:

- **RECEIVED** — Slack event reached the bridge.
- **VALIDATED** — envelope is parseable, authorized, safe, and references valid identities.
- **ROUTED** — target workstream/role/seat resolution succeeded.
- **QUEUED** — immutable event is durable; no model/session is assumed to have seen it.
- **RUNTIME_VISIBLE** — target runtime bootstrap/adapter proves the exact envelope was presented.
- **ACKED** — target explicitly accepts mission + authority boundary.
- **RUNNING** — target reports active execution.
- **RESULT** — target returns completion/block/handoff transport result.
- **FAILED / EXPIRED** — typed terminal transport state.

`RESULT` is **not** automatically Agent OS `done` or Linear `Done`.

## 6. Runtime delivery modes

### 6.1 Runtime with a real launch/resume adapter

The dispatcher may call the approved runtime adapter with:

- the immutable dispatch envelope;
- compiled current Agent OS context for the workstream;
- the current Linear/GitHub references needed for the mission.

Only the adapter's actual delivery receipt advances the event to `RUNTIME_VISIBLE`.

### 6.2 Browser-hosted runtime with no launch/resume capability

Persist the dispatch in the target seat's durable inbox. At the next eligible session bootstrap:

1. resolve durable seat identity;
2. read oldest eligible non-expired pending dispatches before unrelated new work;
3. compile current Agent OS context for `WS:<KEY>`;
4. present the immutable dispatch envelope;
5. write a bootstrap delivery receipt (`RUNTIME_VISIBLE`);
6. require explicit ACK before `RUNNING`.

This is the MVP assumption for browser ChatGPT/Claude/Fable until a real adapter exists. Do not pretend a Slack notification woke the session.

## 7. Slack thread protocol

One dispatch = one event lineage = one Slack thread.

First line of lifecycle replies is machine parseable:

```text
ACK | event=<event_id> | seat=<seat> | ws=WS:<KEY> | linear=MAS-123 | state=accepted
```

```text
PROGRESS | event=<event_id> | state=<short-state> | pr=<repo#n|none> | next=<one-action>
```

```text
RESULT | event=<event_id> | outcome=<complete|blocked|handoff> | pr=<repo#n|none> | handoff=<canonical-path|none> | next=<one-action|none>
```

Free-form explanation may follow. Related child missions get their own event and may cite `parent_event_id`; unrelated missions never share one event thread.

## 8. Canonicalization after RESULT

A Slack claim is testimony, not proof.

1. Target agent/operator writes the required Agent OS handoff/DEC/record delta.
2. GitHub carries code/research/CI evidence.
3. Agent OS validation/generation establishes durable orchestration state.
4. Linear projector updates portfolio/gates.
5. Slack thread receives the canonical references.

If Slack, Linear, GitHub, and Agent OS disagree, emit a reconciliation warning and keep the disagreement visible.

## 9. Dedupe, edits, and supersession

Slack retries are expected. Canonicalize the immutable machine envelope and compute `dedupe_key`; replay with the same key is idempotent.

A materially changed mission after dispatch creates a **new event** with `supersedes_event_id`. Never mutate an ACKed mission in place.

## 10. Security and rights

Never put these in Slack dispatch bodies or the bridge event store:

- credentials/tokens;
- customer secrets;
- raw restricted-vendor payloads;
- private source data the target seat lacks rights to read.

Transport canonical references, hashes, IDs, rights-safe summaries, and redacted receipts instead.

Fail closed on:

- unknown sender/seat;
- unknown workstream;
- authority mismatch;
- expired dispatch;
- malformed scope;
- disallowed data class.

## 11. Relationship to Agent OS invariant I1

`WS:AGENT-OS` owns the organizational **knowledge plane**, not the dispatcher. Its own landmine states that work-start/dispatch authority belongs in Mastermind `control_plane/` or the existing execution hook layer.

Therefore:

- this contract may be cited by Agent OS;
- dispatch event storage/runtime adapters do **not** live under `agentos/` as an execution engine;
- Agent OS remains the work identity + decision/handoff source the dispatcher consumes.

This is the same boundary `DEC:AGENTOS-NO-TASK-STORE` already ratifies for a future task/job store: pre-PR autonomous assignment belongs in the Executive OS dispatcher, not Agent OS.

## 12. MVP implementation boundary

First implementation is deliberately fail-closed and boring:

1. ingest only structured dispatch messages from `#agent-dispatch`;
2. resolve Slack sender → durable seat;
3. validate `WS:<KEY>`;
4. persist immutable event + lifecycle transitions;
5. expose per-seat pending inbox;
6. deliver at next-session bootstrap for runtimes without launch/resume;
7. support ACK / PROGRESS / RESULT replies to the original Slack thread;
8. emit reconciliation metrics: unrouted events, unacked age, duplicates, expired events, RESULT events with no subsequent canonical state delta.

Automatic browser-session wake/resume is a **later adapter capability**, not an MVP assumption.

## 13. Acceptance tests

The bridge is not accepted until tests independently prove:

- Slack message delivery alone does not count as `RUNTIME_VISIBLE`;
- unknown `WS:` fails closed;
- duplicate Slack delivery creates one mission;
- the exact immutable envelope reaches the intended seat at bootstrap;
- ACK/RESULT remain attached to the original event/thread;
- `RESULT` cannot mark Agent OS/Linear done without canonical proof;
- secret/restricted payload classes are refused;
- an authority mismatch does not execute even when the Slack sender is a valid employee seat.

That is the bridge: Slack carries the event; Mastermind routes it; the runtime explicitly receives and ACKs it; Agent OS/GitHub carry durable truth and proof.
