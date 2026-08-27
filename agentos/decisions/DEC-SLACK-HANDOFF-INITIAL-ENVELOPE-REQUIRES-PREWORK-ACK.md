---
key: SLACK-HANDOFF-INITIAL-ENVELOPE-REQUIRES-PREWORK-ACK
question: >
  When a Sol/CEO Slack handoff to Claude or another already-active operator requires the receiver
  to acknowledge the exact operation before doing work, where must that prerequisite live and
  what must the receiver do before execution begins?
answer: >
  The initial Slack handoff message itself must be a self-contained admission envelope. If a
  pre-work ACK is required, the initial message must explicitly say BEFORE DOING ANY WORK to reply
  in the handoff thread with `ACK <operation_key>`, then read the entire existing thread for any
  additional Chairman/CEO instructions, and not begin execution until both steps are complete.
  Thread replies/comments may amend or steer an admitted handoff, but they must not carry a
  prerequisite the receiver needed in order to start safely. The Slack ACK proves only that the
  receiver explicitly acknowledged the handoff boundary; it does not by itself prove canonical
  runtime claim, execution, completion, or Executive lifecycle state.
rationale: >
  On 2026-08-27 the Chairman observed a live Claude session begin handling a Slack-origin job
  without having consumed the thread comment that required an ACK. Only after the Chairman pointed
  out the missing ACK did the Claude session state that it had treated another instruction as
  overriding the ACK requirement and then post the ACK. That failure shows that thread comments
  are not a reliable pre-execution admission surface for a Claude handoff. Putting the mandatory
  admission sequence in the initial envelope removes that ambiguity while preserving Slack as
  transport rather than lifecycle authority.
alternatives:
  - option: Put the ACK requirement only in a later thread comment
    why_not: >
      A Claude/session harness may receive the initial handoff without ingesting all existing thread
      replies before it starts operating, so the prerequisite can be missed until after execution
      has already begun.
  - option: Treat any Slack delivery as sufficient acknowledgement
    why_not: >
      Existing Slack/Autonomy law distinguishes transport delivery from runtime visibility,
      explicit agent acknowledgement and execution.
  - option: Create a new Slack-side admission state machine to enforce the ordering
    why_not: >
      That would duplicate canonical lifecycle/control authority. This ruling is an envelope and
      receiver-protocol rule only; Executive OS remains the sole Job/Attempt/Worker/Event owner.
evidence:
  - "Chairman live observation, 2026-08-27: Claude began handling the job before consuming the thread-level ACK prerequisite; after Chairman intervention Claude acknowledged the error and posted the ACK."
  - "agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md"
  - "agentos/decisions/DEC-AUTONOMY-V1-DISPATCH-DIALOGUE-RUNTIME-SEPARATION.md"
  - "agentos/discoveries/DSC-AGENT-DISPATCH-CURRENTLY-HAS-NO-WORKER-RECEIVER.md"
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - slack:#agent-dispatch
  - CEO-to-Claude manual Slack handoffs that require a pre-work ACK
confidence: high
reversibility: easy
decided_by: chairman-chris
decided_at: 2026-08-27
---

## Required initial-envelope sequence

For any applicable Slack handoff, the initial message must contain the equivalent of:

```text
BEFORE DOING ANY WORK:
1. Reply in this Slack thread with `ACK <operation_key>`.
2. Then read the entire existing thread for additional Chairman/CEO instructions or amendments.
3. Do not begin execution until both steps are complete.
```

The initial envelope must also include enough minimum mission identity to make the ACK meaningful,
including the exact operation key and the bounded mission/authority context required by the
current commission law.

## Thread-amendment law

After admission, thread replies may add clarification, steering, evidence, or a bounded amendment.
They must not be the sole carrier of a prerequisite that was necessary for safe admission. If an
amendment materially changes the logical operation rather than clarifying it, current operation-key,
carrier-binding and reconciliation law still applies.

## Truth distinction

This ruling does not collapse Slack transport into runtime state:

```text
initial handoff posted
!= receiver read it
!= receiver ACKED it
!= canonical Worker/session claim
!= RUNNING
!= RESULT
```

An ACK is useful protocol evidence, not a replacement lifecycle. Executive OS, Agent OS and GitHub
retain their existing canonical ownership boundaries.

## Relationship to existing law

This decision refines the manual handoff protocol under
`DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY` and
`DEC:AUTONOMY-V1-DISPATCH-DIALOGUE-RUNTIME-SEPARATION`; it does not supersede their authority
boundaries and does not unfreeze absent-recipient generic worker dispatch.
