# Mastermind-X Slack Transport + Executive Ingress Contract

**Status:** architecture contract / sequencing boundary · 2026-08-20  
**Authority:** records only; does not itself start or dispatch work  
**Owning boundary:** transport integrates with Mastermind execution/control authority; Agent OS remains the knowledge plane  
**Linear program:** `MAS-9`  
**First vertical:** `MAS-48`  

## 0. Purpose

Slack is Mastermind-X's **human-visible communication and write transport**. It can carry bounded requests, acknowledgements, progress references, results and cross-program intelligence among Chairman/Sol seats, orchestration lanes, workers and operators.

Slack is not a lifecycle database, task store, source of workstream truth, or proof that an AI runtime saw a message.

The immediate implementation problem is deliberately narrower than a generic agent bus: prove that a Personal-Pro Sol session can submit one bounded CEO request through `#ceo-control-room` into the **existing Executive OS**, receive a deterministic Slack acknowledgement, and read the same canonical intent/Job back through the existing read-only MCP. Generic `#agent-dispatch` routing follows only after that proof and a fresh architecture review.

## 1. Authority order

When systems overlap, use this ownership order:

1. **Mastermind Executive OS** — canonical Job/Attempt/Worker/Event lifecycle and CEO-intent admission.
2. **Agent OS / Mastermind organizational knowledge** — durable workstream identity, decisions, discoveries, handoffs, authority walls and proof requirements.
3. **GitHub** — exact implementation/evidence truth.
4. **Linear** — selective portfolio projection.
5. **Slack** — transport, human visibility and transport acknowledgement.

Slack must never gain authority merely because it is convenient to write to.

## 2. No-duplicate-state law

Current Executive OS archaeology is binding for this contract:

- Executive SQLite already owns Job/Attempt/Worker/Event lifecycle state;
- `events.command_id` already provides canonical idempotency for Executive mutations;
- `control_plane/ceo_intent.py` already admits one bounded CEO intent into one queued Job plus `JOB_CREATED`;
- `control_plane/executive_service.py` is the production mutation boundary;
- `executive_inbox.py` is intentionally a recomputed projection, not a mutable inbox database;
- Wake is currently **HOLD / NOT_ACCEPTED / NOT_ARMED** and is not an accepted foundation.

Therefore this program does **not** pre-authorize:

- a Slack lifecycle database;
- a second event/command dedupe table;
- a durable Slack seat-inbox database;
- a parallel Slack task/job store;
- direct Slack-daemon access to Executive SQLite;
- an Agent OS execution queue.

If later generic dispatch requires a fact not representable by existing canonical authority, a new architecture ruling must prove that gap before persistence is added.

## 3. Truth distinctions

The following facts are different:

1. Slack message posted.
2. Transport adapter received/validated the message.
3. Canonical receiving system accepted or refused the request.
4. Runtime/session actually became aware of the work.
5. Agent explicitly acknowledged the mission/authority boundary.
6. Work began.
7. A result was returned.
8. Canonical work/proof state changed.

These distinctions are semantic laws, **not a requirement to create a separate persisted Slack state machine**.

For the CEO-intent V1, the accepted canonical Executive Job/Event plus bounded Slack transport provenance and the Slack thread ACK provide the durable receipt. The ACK explicitly reports `dispatched=false`; no runtime-delivery claim is made.

## 4. Channel topology and sequencing

The shared workspace topology remains useful:

| Channel | Purpose | Implementation status |
|---|---|---|
| `#ceo-control-room` | Chairman/Sol executive requests, decisions and escalations | **First writeback vertical: MAS-48** |
| `#agent-dispatch` | future structured agent/seat dispatch threads | **Architecture hold pending MAS-48 + Wake review** |
| `#build-events` | GitHub/CI/production-validation event feed | observational/event use |
| `#company-intelligence` | discoveries crossing program boundaries | communication/research use |

Do not create one channel per Agent OS workstream by default. Threads are transport conversations; Agent OS carries durable organizational state.

## 5. Durable seat vs temporary role

Authentication identity and session role are separate.

A durable seat such as `chatgpt-1`, `chatgpt-2`, or `chatgpt-3` may run CEO Sol, reviewer, researcher or another role over time. Slack user identity establishes transport provenance only. It does **not** establish Executive authority, Agent OS ownership, or permission to execute.

The trusted receiving system derives and adjudicates authority using its canonical rules.

## 6. First vertical — Pro Sol CEO request

### 6.1 Observable journey

The V1 path is:

```text
ChatGPT Personal Pro — Sol
        |
        | approved Slack write action
        v
#ceo-control-room
        |
        | dedicated least-privilege Slack transport
        v
ExecutiveControlService
        |
        | high-level submit-ceo-request admission
        v
existing ceo_intent.submit_intent(...)
        |
        v
Executive SQLite
one canonical Job + JOB_CREATED
        |
        +----------------------+
        |                      |
        v                      v
Slack thread ACK        read-only Executive MCP
                         ceo_intent_status / executive_job
```

Submission is **not dispatch**. The accepted Job remains queued under normal Executive OS law unless another authorized subsystem later dispatches it.

### 6.2 Slack wire discriminator

The first line is exactly:

```text
EXECOS/CEO_REQUEST_V1
```

The remainder is exactly one JSON object. Its business fields may be no wider than the existing model-safe Executive/MCP request vocabulary:

Required:

- `operation_key`
- `objective`
- `department`
- `priority`
- `execution_profile`

Optional:

- `workstream`
- `allowed_write_paths`
- `validation`
- `attempt_limit`

The Slack sender may not provide actor, raw authority lists, grounding SHA, raw validation argv, worktree, branch, Job ID, canonical intent ID, runtime database path, service-control fields, credentials or tokens.

Unknown keys fail closed. No YAML or prose repair. Whole message ceiling is 4,500 UTF-8 bytes in V1.

### 6.3 Trusted derivation

Do not copy Executive/MCP policy logic into the Slack package.

A transport-neutral first-party admission layer under `control_plane/` should normalize the high-level request and derive privileged fields. The Executive control process then invokes the existing CEO-intent seam.

The network-facing Slack process must use a dedicated least-privilege local principal and be command-scoped to the one high-level admission command. It must be denied raw `submit-ceo-intent`, dispatch, shutdown, backup, service control and future commands by default.

## 7. Idempotency, correction and provenance

### 7.1 Idempotency

Do not add a Slack dedupe database.

The Slack integration derives its stable canonical operation identity and relies on existing Executive admission/idempotency law. Replayed delivery of the same normalized operation creates/reconciles one canonical Job. Reuse of the same operation key with changed normalized payload fails closed rather than producing a second Job.

### 7.2 Edits

A Slack message edit does not mutate an accepted CEO intent. Changed work uses a new operation key.

### 7.3 Transport provenance

Bounded transport provenance may be attached to the existing canonical `JOB_CREATED` CEO-intent provenance if backwards-compatible. Allowed provenance is identifiers/evidence such as workspace, channel, message/thread, sender and Slack event IDs.

Transport provenance:

- confers no authority;
- is outside model-authored intent fingerprint material;
- contains no token, credential, email/display-name requirement or full message-body copy;
- is not a second event store.

## 8. Slack acknowledgement law

The CEO V1 ACK is a receipt for canonical admission, not execution.

It may contain bounded references such as:

```text
ACK | operation=<operation_key> | intent=<intent_id> | job=<job_id> | accepted=true | duplicate=false | dispatched=false
```

If canonical state committed but Slack ACK fails, do not roll back or blindly resubmit. Reconcile the canonical intent/Job first, then retry the acknowledgement only.

A timeout never proves failure or success of a modifying request without canonical reconciliation.

## 9. Generic `#agent-dispatch` is a later program

The long-term agent-communication vision remains valid, but its persistence/routing design is **not frozen by this document**.

`MAS-29/30/31` must wait for:

1. MAS-48 production proof;
2. the then-current Wake adjudication;
3. an archaeology pass over existing Executive events, Jobs, attempts, worker/session state and inbox projections.

The redesign must answer:

- which generic dispatch facts are already canonical Job/Event facts;
- whether pending browser-session work can be derived as a projection instead of stored in a new seat inbox;
- whether any accepted Wake mechanism is relevant without conflating inbound Slack requests and outbound source-anchored wake obligations;
- how `WS:<KEY>` organizational provenance remains distinct from runtime/session-target routing namespaces;
- how `RUNTIME_VISIBLE`, `ACKED`, `RUNNING` and `RESULT` claims are independently tied to real runtime evidence.

No new mutable Slack dispatch store or durable seat-inbox database may be implemented merely because earlier drafts named one.

## 10. Browser-hosted runtime law

ChatGPT/Claude/Fable browser sessions cannot be assumed to wake because a Slack account received a message.

Until a real supported launch/resume adapter or accepted canonical bootstrap mechanism exists:

- do not claim automatic asynchronous delivery;
- do not advance a runtime-visible/acknowledged state from Slack receipt;
- do not create a durable seat inbox by default;
- prefer a read-only/recomputed pending-work projection from accepted canonical Executive state when that becomes implementable;
- require actual runtime/bootstrap evidence before claiming the session saw the mission.

## 11. Slack thread protocol for later execution states

A useful thread format may still exist, but every state token must refer to canonical evidence rather than become its own authority. Examples:

```text
PROGRESS | job=<canonical-job-or-work-ref> | pr=<repo#n|none> | next=<bounded-next-action>
```

```text
RESULT | job=<canonical-job-or-work-ref> | outcome=<complete|blocked|handoff> | pr=<repo#n|none> | handoff=<canonical-path|none>
```

A Slack `RESULT` is testimony until the canonical owning systems agree. It cannot by itself close an Executive Job, Agent OS workstream/wave, Linear issue, production-proof gate or PR.

## 12. Canonicalization after work

For substantive work:

1. Executive OS owns canonical execution lifecycle where applicable.
2. Target worker/session writes required Agent OS handoff/decision/workstream deltas.
3. GitHub carries implementation/research/CI receipts.
4. Production proof is recorded on the real path where required.
5. Linear projects the resulting current portfolio/gates.
6. Slack receives references/acknowledgement for human visibility.

If Slack, Linear, GitHub, Executive OS and Agent OS disagree, keep the disagreement visible and repair the projection/transport representation rather than rewriting canonical truth for cosmetic consistency.

## 13. Security and rights

Never put credentials/tokens, customer secrets, raw restricted-vendor payloads or private source material into Slack transport bodies when the receiving principal is not authorized for them.

The V1 transport fails closed on at least:

- wrong workspace/channel;
- untrusted sender;
- unsupported subtype/self-loop;
- malformed discriminator/JSON;
- oversize payload;
- unknown keys;
- operation-key conflict;
- invalid high-level request;
- authority refusal;
- command/peer denial;
- backend unavailable/refused/timeout;
- acknowledgement failure after canonical commit.

Slack source identity is provenance, never privilege.

## 14. Relationship to Agent OS invariant I1

`WS:AGENT-OS` owns organizational knowledge only. It does not start work.

This contract may be cited by Agent OS, but runtime admission, Job/Event state and execution remain in Mastermind Executive OS / existing execution control. This preserves both invariant I1 and `DEC:AGENTOS-NO-TASK-STORE`.

## 15. Implementation sequence

### MAS-48 / PR-A — shared CEO-request law + command-scoped local admission

Prove a hermetic Slack-like local peer can submit one high-level CEO request over AF_UNIX into the existing Executive OS and is structurally unable to invoke other control commands. No Slack SDK/network/install.

### MAS-48 / PR-B — Slack Socket Mode adapter

Add the isolated least-privilege Slack transport, strict parser, source filters, reconnect/backoff and deterministic ACK. No production credential/install mutation in this PR.

### MAS-48 / PR-C — production principal/install + one harmless canary

One real Personal-Pro Sol `research_only` request in `#ceo-control-room` creates/reconciles one canonical Job, receives an ACK and is visible through read-only MCP. No generic bus and no worker execution.

### MAS-29/30/31 — re-architecture after proof

Do not start from the superseded durable-event-store/seat-inbox design. Commission only after MAS-48 returns and current Wake/Executive archaeology is reconciled.

## 16. Acceptance tests

The first vertical is accepted only when evidence independently proves:

- duplicate Slack delivery produces one canonical Job;
- changed payload under the same operation key is refused;
- the Slack principal is denied every control command except the approved high-level admission command;
- raw authority/worktree/branch/argv/credential fields cannot be authored from Slack;
- existing MCP schema/derived behavior remains unchanged;
- no new lifecycle database/table/store exists;
- wrong workspace/channel/sender/subtype/oversize payload fails closed;
- bot acknowledgement cannot recurse;
- ACK failure cannot lose or duplicate committed canonical state;
- Slack message/thread -> canonical intent -> Job/JOB_CREATED -> Slack ACK -> MCP readback are tied to one operation;
- `WAKE_USED=false` and `dispatched=false` for the V1 proof;
- Slack receipt alone never counts as runtime visibility, execution or completion.

That is the architecture: Slack carries approved transport; the canonical receiving system owns durable state; Agent OS carries organizational memory; GitHub carries implementation proof; Linear projects the portfolio. No second lifecycle plane is created.
