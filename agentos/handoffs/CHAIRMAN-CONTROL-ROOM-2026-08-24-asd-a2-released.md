---
workstream: WS:CHAIRMAN-CONTROL-ROOM
session: sol/ccr-asd-a2-release-20260824
model: sol
ended_because: complete
mission: >
  Release ASD-A2 as one bounded production-proof wave while fencing the Chairman's currently active
  local Executive-automation setup from any overlapping Agent Relay host mutation. This record
  commissions the preflight and canary; it does not install an app, store a credential, start a
  service, send Slack traffic, arm Executive Runtime, or begin ASD-A3/A4.
state_before: >
  CCR-X1 is accepted and live-local. ASD A0/A1 is accepted as DEVELOPMENT_UNARMED in Mastermind
  PR #125 merge eb9910681a6db9f9675b25233c8865bb43325c32, while ASD-A2/A3/A4 remain unstarted.
  Separately, protected Mastermind has advanced through Executive automation G1-G4, including the
  bounded COO cycle, read-only App Server planner, governed Docs MCP and one read-only native helper.
  Those capabilities remain production-unarmed and require current-master host requalification and
  provider readiness. The Chairman reports local sessions are currently working on that automation
  setup, creating a same-host collision risk even though no A2 GitHub/Slack/Linear carrier existed.
changed:
  - path: Linear MAS-127
    what: >
      Created the selective portfolio projection `ASD-A2 — Production Agent Relay app + harmless
      active-session canary` as Todo, urgent and unassigned. It is explicitly
      `COMMISSIONED / PRE-FLIGHT GATED / NOT EXECUTING`; Linear does not prove execution.
  - path: agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-24-asd-a2-released.md
    what: >
      Freezes the A2 release, mandatory local collision preflight, exact authority boundaries,
      production proof law and stop condition so one local operator can execute without recovering
      this chat or creating a competing carrier.
verified:
  - claim: The current protected Sol procedure permits one bounded A2 commission but requires a collision fence before dispatch.
    command: >
      Read docs/sol_skills/INDEX.md, COMMISSION_WAVE.md and RECONCILE_STATE.md from protected
      Mastermind master 7136b30a63ac47bdfc0a44e4d5080e0cd345de42.
    result: >
      Skillpack mastermind.sol_skillpack.v1 v1.0.0 is compatible. Commission law requires current
      boundary recovery, complete handoff and a final collision check; unexpected/concurrent carriers
      must be reconciled rather than duplicated.
  - claim: A1 is the sole accepted development-unarmed Agent Relay substrate.
    command: >
      Read Mastermind PR #125 and current protected integrations/slack_agent_dialogue source law.
    result: >
      Accepted head 21361653a273b801b08caa7271daa68437f7b2fc merged as
      eb9910681a6db9f9675b25233c8865bb43325c32. It created strict, storeless A0/A1 dialogue
      contract/engine/service seams and explicitly left production app/token/service/message work
      to a separately released A2.
  - claim: No remote A2 carrier is currently in flight.
    command: >
      Search current Mastermind open PRs and branches for ASD/A2/Agent Relay/automation/control-room,
      search current Macro open PRs for CCR/ASD/Agent Relay, search public Slack for ASD-A2/Agent Relay,
      and search Linear for a prior A2 production-canary issue.
    result: >
      No A2 Mastermind PR/branch or Slack thread existed; no overlapping Macro CCR/ASD PR existed;
      Linear had MAS-125 A0/A1 but no A2 issue before MAS-127 was created.
  - claim: The Chairman's local automation work is materially adjacent at the host layer but not an A2 authority/code carrier.
    command: >
      Reconcile protected Mastermind PRs #141-#144 and
      research/MASTERMIND_AUTONOMOUS_EXECUTIVE_AGENT_CLI_CAPABILITY_FREEZE_2026-08-24.md.
    result: >
      G1-G4 are merged and production-unarmed. Their next host gate is current-master service/install
      requalification and provider readiness. They own Executive Job/Attempt/Worker/Event and worker
      execution composition, not Slack Agent Dialogue. Concurrent launchd/keychain/service mutation
      on the same Mac can nevertheless make production evidence ambiguous, so A2 must preflight first.
unverified:
  - claim: The current local Executive-automation sessions are disjoint from every Agent Relay host resource.
    what_would_verify: >
      One local A2-0 read-only census confirms no other session/carrier is modifying the Agent Relay
      app principal, credential reference, service label, AF_UNIX endpoint, install/config surface or
      integrations/slack_agent_dialogue paths. Local process presence alone is not work ownership;
      use exact worktree/branch/service identities where available.
  - claim: A dedicated least-privilege production Mastermind Agent Relay app and credential are ready.
    what_would_verify: >
      After A2-0 PASS, native action-time human confirmation provisions or selects the exact app and
      secret through the reviewed private secret boundary. A secret-owning verifier emits only
      allowlisted non-secret identity/scope/channel metadata; no credential bytes enter model-visible
      output, argv, environment, repository, transcript or receipt.
  - claim: ASD-A2 removes the Chairman from a real program decision loop.
    what_would_verify: >
      Not A2. After A2 is independently accepted, ASD-A3 must prove one already-active,
      already-commissioned real Sol-Fable project decision/result exchange with zero Chairman
      message-body relay.
unresolved:
  - "A2 host mutation is gated on the local A2-0 collision preflight because local Executive automation setup is active on the same Mac."
  - "Action-time native credential confirmation remains required after A2-0 PASS; this release is not secret authorization."
  - "Executive G1-G4 remains production-unarmed until its own host requalification/provider-readiness acceptance; A2 must neither arm nor modify it."
  - "P0B/Multilogin remains a separate credential/vendor/foreground problem and is outside A2."

next_actions:
  - "A2-0: on the Chairman Mac, read-only inventory Agent Relay service/socket/keychain-metadata/worktree identities. If any active local session owns an overlapping Agent Relay resource, STOP and reconcile that exact carrier; create no second A2 carrier."
  - "If A2-0 proves disjointness, obtain native action-time confirmation for the dedicated Agent Relay app credential and perform the smallest install/config/service step required by the accepted A1 implementation."
  - "Bind exactly one #agent-dispatch parent to this immutable commission reference, then run one harmless request -> Personal-Pro Sol ruling -> same-session readback plus duplicate/effect-unknown/restart/wrong-sender/stale/missing-history proofs."
  - "Return all redacted receipts to Sol and STOP. Do not start ASD-A3/A4."

do_not_redo:
  - "Do not rebuild A0/A1 or create another MAS-125/A2 implementation substrate."
  - "Do not create a Session OS, Slack inbox DB, cursor, queue, retry ledger, second lifecycle or generic Slack proxy."
  - "Do not arm or edit Executive COO autonomy, App Server, native helpers, Wake, CeoIngress, MAS-48 or P0B from A2."
  - "Do not infer execution from MAS-127, Slack delivery, a running local process or a browser/window title."
  - "Do not expose Slack/vendor/provider credentials through model-visible settings, DOM/DevTools, argv, environment, shell variables, temp files, logs or receipts."
  - "Do not send the real A2 parent or canary traffic before this records carrier is merged and A2-0 passes."

danger_areas:
  - "Same-host service/keychain work can collide even when Git paths and authorities are disjoint; ambiguous modification means STOP, not parallel retry."
  - "Agent Relay and Executive Relay must remain different principals/tokens/channel allowlists/local authorities."
  - "Slack delivery is transport evidence only; A2 acceptance requires the full send/read/reconciliation/restart/refusal proof matrix and zero canonical lifecycle mutation."
  - "The A2 app/service is for already-active, already-commissioned sessions only; no wake/resume or prompt injection is authorized."

prs: [125, 138, 141, 142, 143, 144, 6330]
decisions:
  - DEC:CHAIRMAN-CONTROL-ROOM-ACTIVE-SESSION-DIALOGUE-F0-ACCEPTED
  - DEC:CCR-BRIDGE-FIRST-CHAIRMAN-PRIORITY
  - DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED
discoveries:
  - DSC:ASD-MODEL-VISIBLE-SETTINGS-CAN-EXPOSE-LIVE-CREDENTIALS
---

# ASD-A2 operator commission

## Observable mission

After A2-0 proves the host lane is disjoint and native credential confirmation occurs, prove one
production `Mastermind Agent Relay` can transport an exact-thread, harmless
`MMX/AGENT_DIALOGUE_V1` request from an already-active commissioned Fable/worker session to
Personal-Pro Sol and one eligible Sol ruling back to that same session, including restart and
ambiguity/refusal proofs, while creating zero canonical Executive or organizational lifecycle state.

## Why it matters

X1 reduces session hunting, but the Chairman is still the normal human carrier for substantive
Sol↔Fable questions and rulings. A2 proves the real transport substrate required before A3 can test
that workflow on an actual program decision boundary.

## Authority and precedence

1. Current Chairman ASD-A2 release, 2026-08-24.
2. Protected Sol Skillpack at Mastermind `7136b30a63ac47bdfc0a44e4d5080e0cd345de42`.
3. Accepted ASD F0 architecture in Mastermind research.
4. Mastermind PR #125 / merge `eb9910681a6db9f9675b25233c8865bb43325c32`.
5. This exact merged Macro handoff commit/path/hash after this records carrier lands.
6. Current `WS:CHAIRMAN-CONTROL-ROOM`.
7. Executive automation freeze only for collision/separation; it grants no ASD authority.

A newer material source or overlapping Agent Relay carrier stops the wave for Sol reconciliation.

## Exact scope

Primary implementation already exists in Mastermind `integrations/slack_agent_dialogue/**`.
A2 may add only the smallest production install/config/service adapter and focused tests/docs truly
required to operate that accepted core. Local private configuration and credentials stay off Git.
Any code change must use one new, bounded Mastermind A2 carrier created only after A2-0 proves no
existing local/remote A2 carrier owns the same surface.

## Explicit non-goals

No A3 real-program canary, A4 CCR projection, generic dispatch, wake/resume, provider prompt
injection, Executive/CeoIngress/SOL_STATE mutation, P0B, Multilogin, new database/cursor/inbox/queue,
automatic GitHub failover, Agent OS/Linear runtime writes, or Chairman-seat/browser mutation.

## Complete journey

1. A2-0 reads only non-secret local identities and proves the Agent Relay host surface is not owned by another active setup session.
2. Native operator confirms the dedicated Agent Relay secret action; secret bytes remain outside model-visible surfaces.
3. Verify exact app/bot identity, least-privilege scopes and #agent-dispatch membership using a secret-owning verifier that emits only allowlisted metadata.
4. Install/start the smallest local Agent Relay service using the accepted A1 contract and private config.
5. Verify exactly one eligible top-level parent binds this workstream and immutable commission; zero/multiple/mismatch refuses.
6. Already-active harmless Fable/worker canary sends one `DECISION_REQUEST` with stable message key.
7. Personal-Pro Sol reads it natively and posts one eligible `RULING` referencing the exact request/current applicability.
8. The same active canary reads and validates the ruling.
9. Prove duplicate same-payload, changed-payload conflict, ACK-loss/effect-unknown, wrong sender, stale applicability, incomplete history, restart, missing token/config and edit/delete correction behavior.
10. Prove the entire transport caused zero Executive Job/Attempt/Worker/Event mutation and no Agent OS/Linear/GitHub lifecycle mutation.
11. Stop service if the accepted operational design calls for canary-only runtime; otherwise leave only the explicitly reviewed least-privilege local service state. Return receipts to Sol.

## Data / contract / time / null / correction

Use the merged A1 `MMX/AGENT_DIALOGUE_V1` and `MMX/AGENT_DIALOGUE_PARENT_V1` contracts byte-for-byte.
One thread binds one immutable commission. Message key is logical identity; Slack timestamp is
transport evidence. Same key+fingerprint reconciles; same key+changed fingerprint conflicts. A
post with unknown effect stays on the same Slack carrier and rereads bounded history. Only complete
true-not-found permits the one reviewed same-carrier retry. Incomplete history remains uncertain.
Edits/deletes never cancel consumed dialogue; corrections use a new key. Restart recovers from
bounded Slack history and creates no cursor DB. Unknown/null identity or scope facts refuse rather
than guess.

## Method

All framing, parsing, hashing, identity, sender eligibility, thread binding, idempotency,
reconciliation and authority guards are deterministic. Model-generated text may fill only the
already-bounded human summary/rationale fields. Model output has zero authority over identity,
eligibility, retries, lifecycle or scope.

## Failure states

Refuse/fail closed on local resource collision, wrong app/workspace/channel, missing/extra scope,
zero/multiple parents, commission/hash mismatch, stale applicability, wrong sender, bot/self loop,
changed payload under same key, incomplete history, Slack unavailable, missing config/token,
restart reconciliation failure, secret-shaped content, arbitrary URL/argv/path, unexpected
Executive/AgentOS/Linear/GitHub mutation or any need for a durable queue/cursor/inbox.

## Ordered implementation/proof sequence

1. Re-pin current protected Mastermind/Macro and recheck remote/local collisions.
2. Run A2-0 read-only local collision preflight. STOP on overlap.
3. Obtain native action-time credential confirmation.
4. Verify app identity/scopes/channel membership through the secret-owning metadata path.
5. Install/start only the bounded Agent Relay production surface.
6. Bind one exact commission parent.
7. Run harmless request/ruling/readback.
8. Run hostile duplicate/uncertainty/restart/refusal matrix.
9. Verify zero canonical lifecycle mutation and secret hygiene.
10. If code changed, run focused/full exact-head CI and independent review on one A2 carrier.
11. Return to Sol. Do not start A3/A4.

## Acceptance tests and production proof

A2 must return app identity/scopes/channel-membership receipt; service identity/socket/peer-policy
receipt; exact parent/commission receipt; request and ruling keys/fingerprints/Slack timestamps;
duplicate/effect-unknown/restart/wrong-sender/stale/incomplete-history/missing-config outcomes; proof
of no durable dialogue store; before/after Executive lifecycle census showing zero A2-created
Job/Attempt/Worker/Event; no runtime Agent OS/Linear/GitHub write; secret-shape scan; and any
code/CI/security receipts. No credential bytes, raw private payloads or provider-native secrets in
receipts.

## Stop condition

Stop after one harmless production A2 canary and hostile proof matrix. Capability becomes at most
`PROVEN_LIVE` for the bounded transport if Sol accepts the real receipts. A3/A4 remain unstarted.

## Required continuation return

Return exact protected Mastermind/Macro SHAs, this commission repo/commit/path/content SHA-256,
MAS-127, local collision-preflight result, app/service non-secret identities, whether any code carrier
was needed, exact final head/PR if so, test/CI/security receipts, redacted production proof matrix,
zero-lifecycle-mutation proof, discovered collisions, remaining gates, and explicit
`ASD-A3/A4 UNSTARTED`.

# Return point

This record releases A2 but intentionally leaves execution gated. Merge this records-only carrier
first. Then one local operator/session performs A2-0. If it collides with the existing Executive
automation setup, return the exact ownership identities to Sol and do nothing else. If disjoint,
request native action-time credential confirmation and proceed with the bounded A2 canary only.
