---
key: AGENT-DISPATCH-CURRENTLY-HAS-NO-WORKER-RECEIVER
claim: >
  Current #agent-dispatch fan-out still has no PROVEN canonical production receiver path even though
  the live channel includes multiple Claude user principals plus Chairman and ChatGPT1/2/3. User,
  account and Slack-seat identity are not Worker/session identity. A 2026-09-02 exact-session canary
  made the gap explicit: an EXACT_SESSION_REQUIRED commission bound to Claude Fable native session
  52bfee89-f502-49c4-bc24-078d8110ede6 was delivered through the Claude account/seat but instantiated
  a different fresh native Claude session, which correctly returned RECEIVER_SESSION_MISMATCH with
  effect NONE. The exact bound session remained idle with dirty local A2 bytes and was not registered
  in the observed host session-messaging registry, so the landing session could not wake it. At least
  one historical Slack-origin operation key (K2-C) later produced real GitHub implementation/merge
  evidence with Claude Fable co-authorship, so an un-ACKed Slack handoff still cannot be assumed never
  executed; however neither later GitHub activity nor account-level Slack delivery proves exact
  session pickup.
falsifier: >
  Run `rg -n "A2_0_PASS|A2_HOST_COLLISION|Agent Relay|agent-dispatch|RECEIVER_SESSION_MISMATCH" agentos/ research/`
  and follow any exact operation/PR receipts it surfaces. This discovery is falsified when an accepted
  production path deterministically binds an eligible commissioned worker/COO native session to the
  exact commission and produces explicit target consumption/ACK, or Executive OS records the
  corresponding concrete Worker claim/Attempt and exact runtime binding. A Slack mention, account,
  seat, display name, newly spawned same-model session, delivery receipt or later PR is insufficient.
so_what: >
  Future Sol sessions must keep generic runnable #agent-dispatch fan-out held, must reconcile each
  Slack-origin operation individually against GitHub/Agent OS/Executive evidence, and must not infer
  either non-execution from missing Slack ACK or canonical dispatch from a later PR. For
  EXACT_SESSION_REQUIRED work, account/seat delivery to a different native session is
  RECEIVER_SESSION_MISMATCH, not pickup; preserve the exact owner/effect and do not spawn/substitute
  another session. Finish the existing Agent Relay/Wake, RuntimeBinding/session-materialization and
  exact Chat/session provisioning owners rather than adding another Slack router or watcher plane.
kind: runtime
verified_at: 2026-09-02
verified_by: >
  Slack #agent-dispatch exact-thread reads C0BSBM78V1N/1788341279.243119 and
  C0BSBM78V1N/1788341662.642409, including RECEIVER_SESSION_MISMATCH 1788342106.076589;
  Mastermind PR #383 exact-thread/child-assignment procedure repair; prior Macro K2-C merge #6533 and
  protected Autonomy operating law evidence retained below.
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - slack:#agent-dispatch
confidence: verified
---

## 2026-09-02 exact-session falsifier

The OLS-A2 incident supplied a direct experiment instead of another inference from missing ACKs.

The original Fable principal had native session identity
`52bfee89-f502-49c4-bc24-078d8110ede6` and owned unreconciled local A2 bytes on Mastermind PR #362.
After a worker-self-minted successor child was stopped, Sol created a fresh, explicit
`EXACT_SESSION_REQUIRED` child on Slack parent `C0BSBM78V1N/1788341662.642409`, binding only that
exact Fable native session.

The Slack/account delivery did **not** reach that session. It arrived as the spawn prompt of a
separate fresh native session `local_98578804-30fb-4cad-b8cf-ea363115ed02`. That landing session
returned `BLOCKED ... RECEIVER_SESSION_MISMATCH effect=NONE` under the correct parent thread and
reported, read-only:

- the bound Fable session had not consumed the commission;
- the bound Fable session still owned six dirty in-family A2 files;
- the landing session owned none of that state and performed zero source effect;
- the bound Fable session was not registered in the observed host session-messaging registry, so no
  cross-session wake could be issued from the landing session.

Sol therefore parked the child as `EXACT_SESSION_WAKE_UNAVAILABLE / DIRTY_OWNER_PRESERVED` rather
than rebinding the fresh session. This is the behavior the permanent runtime must eventually make
unnecessary.

The incident also exposed a separate transport-law defect: the prior worker had posted a self-minted
`PICKUP_ACK` as a new top-level `#agent-dispatch` message. Mastermind PR #383 tightens procedure so a
Slack reciprocal carrier is workspace + conversation/channel + exact thread-root timestamp; a
same-channel top-level post is not a reply on the assigned child.

## Earlier evidence retained

A live Slack census on 2026-08-27 showed `#agent-dispatch` (`C0BSBM78V1N`) contained ten user
principals: Chairman Chris, ChatGPT1/2/3 and six Claude-labelled user principals. No dedicated
production Mastermind Agent Relay bot was present in that census.

The exact ASD-A2 preflight pickup `asd-a2-host-preflight-20260827-sol-001`, addressed to Claude3,
had one thread reply, but that reply was only ChatGPT1's same-carrier ACK nudge. Claude3 supplied no
`ACK asd-a2-host-preflight-20260827-sol-001`, `A2_0_PASS`, or `A2_HOST_COLLISION`. Under that pickup
contract the operation remained `DELIVERY_ONLY`, not ACKED or executing.

Separately, Macro main contained K2-C merge #6533. Its merge commit explicitly recorded operation key
`alpha-k2c-institutional-adapter-20260826-sol-001` and Claude Fable co-authorship. That operation
originated in an earlier `#agent-dispatch` DELIVERY_ONLY handoff. Therefore the prior simple mental
model "Slack post with no ACK means the work definitely never executed" is false. Canonical owner
and GitHub evidence must be reconciled per operation.

What remains unproven is the system capability Autonomy requires: a deterministic receiver path that
binds dialogue transport to one exact already-active commissioned session, or a canonical Executive
Worker claim plus exact RuntimeBinding/materialization for a Job. Channel membership, account labels,
display names and later matching PRs do not establish that binding.

## Consequence

Do not infer any of the following from Slack alone:

- Fable/Claude/ChatGPT claimed a commission because its user principal is in the channel;
- an account/seat mention reached the exact native session named by the packet;
- a missing Slack ACK proves the operation never ran;
- Executive OS created or routed a Job;
- a later matching PR proves a canonical Slack runtime receiver;
- a Claude/ChatGPT user identity is an Executive Worker ID.

For investigation, distinguish evidence states conceptually without creating another lifecycle:

- transport only;
- transport landed in the wrong native session (`RECEIVER_SESSION_MISMATCH`);
- out-of-band/manual pickup evidenced by an exact later owner/GitHub result;
- accepted Agent Relay/Wake exact-session target consumption/readback;
- Executive Job/Attempt/Worker claim with current RuntimeBinding.

Only the latter two establish the receiver/runtime capabilities the autonomy program is building.

## Repair

`DEC:AUTONOMY-V1-DISPATCH-DIALOGUE-RUNTIME-SEPARATION` remains controlling:

1. do not bulk replay historical DELIVERY_ONLY posts;
2. reconcile each apparent return against exact operation key, PR/head/merge and owning durable
   records before deciding whether work remains owed;
3. for `EXACT_SESSION_REQUIRED`, treat account/seat delivery to another native session as
   `RECEIVER_SESSION_MISMATCH`, preserve the exact owner and dirty/effect state, and do not substitute
   the landing session;
4. keep Slack carrier identity exact to the commissioned parent thread; a top-level same-channel ACK
   does not move or create the carrier;
5. finish Agent Relay/Wake exact-session delivery and source resolution through their existing owners;
6. finish RuntimeBinding, durable action-target transfer and session materialization/provisioning so
   new work does not depend on a pre-existing tab/session noticing Slack;
7. Slack user principals remain transport identities, never Worker or native-session identity by name.
