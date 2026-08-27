---
workstream: WS:CHAIRMAN-CONTROL-ROOM
session: sol/worker-presence-dialogue-20260827
model: sol
ended_because: ci_handoff
mission: >
  Record the Chairman-approved Worker Presence & Dialogue / stateless turn-watcher architecture after
  its protected Mastermind merge, preserve existing ASD-A2/A3 ownership, and leave the exact WP-1
  implementation carrier recoverable without creating another dialogue workstream, lifecycle, queue,
  session registry, watcher registry or Slack-owned authority plane.
state_before: >
  Agent OS already owned active-session dialogue under WS:CHAIRMAN-CONTROL-ROOM: ASD A0/A1 was the
  accepted DEVELOPMENT_UNARMED core, ASD-A2 production Agent Relay and ASD-A3 real dialogue remained
  separately gated, and the workstream explicitly prohibited a second dialogue workstream/control
  plane. Separately, the Chairman approved extending that architecture so governed Codex/Worker
  identities can use one Agent Relay/company-dialogue path and validated watcher-enabled turns may
  later become source facts for existing Wake Fabric. Before this handoff, that new source law lived
  only in Mastermind and this Agent OS workstream did not record its merge/dependency boundary.
changed:
  - path: mastermind:docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md
    what: >
      Protected Mastermind PR #177 merged the one-Slack-app / derived worker-identity architecture:
      Executive OS stays Job/Attempt/Worker authority; Agent Relay/ASD stays one dialogue plane;
      existing ExecutionCapabilityRegistry/McpServerGrant stays the MCP capability-policy owner;
      workers later receive bounded company-dialogue tools rather than generic Slack authority.
  - path: mastermind:docs/superpowers/specs/2026-08-27-worker-presence-dialogue-turn-watcher-amendment.md
    what: >
      Narrows only the Wake-source boundary: raw Slack never originates work/authority, while a fully
      validated immutable-commission-bound turn under exact watch_mode=turn_watch_v1 may later project
      deterministic AgentDialogueAttention for the existing Wake Fabric. Historical V1 threads remain
      inert; no watcher/cursor/inbox/session/provider registry is authorized.
  - path: mastermind:docs/superpowers/plans/2026-08-27-worker-presence-dialogue-wp1-agent-relay-v2.md
    what: >
      Freezes WP-1 as the sole first implementation dependency: V2 parent/message identity,
      operation_key/watch_mode, typed actor/applicability, normal storeless V2 engine and ordinary
      request/response service dispatch only. Zero turn classification, Wake or observer behavior.
  - path: mastermind:docs/superpowers/plans/2026-08-27-worker-presence-dialogue-wp2-company-mcp.md
    what: >
      Freezes the later six-tool company-dialogue MCP facade and trusted-binding boundary. It remains
      held until WP-1 acceptance and may not introduce a shared token, fake production endpoint or
      second MCP capability registry.
  - path: mastermind:docs/superpowers/plans/2026-08-27-worker-presence-dialogue-wptw1-turn-classifier.md
    what: >
      Freezes the later pure turn classifier/AgentDialogueAttention projection to exactly
      turn_watcher.py plus one test file, with zero Slack/service/Wake/provider/persistence side effects.
  - path: mastermind:research/WORKER_PRESENCE_DIALOGUE_WP1_COMMISSION_2026-08-27.md
    what: >
      Releases one bounded HOLD-FOR-SOL WP-1 implementation carrier as Mastermind PR #178 from exact
      protected #177 merge. Carrier existence is not Worker/runtime claim or execution evidence.
verified:
  - claim: Chairman-approved WP-0 source law is merged into protected Mastermind.
    command: >
      Review Mastermind PR #177 exact up-to-date head daa212443154b1d17d5d5ee8c58de008e830a793,
      exact changed-file census, CI/security checks, then squash merge with expected head.
    result: >
      Exact-head repository test SUCCESS; CodeQL SUCCESS; Python/JavaScript-TypeScript/Actions
      analyses SUCCESS; six WP records files only; merge af43f356f4f7f34cb3514d1d1099b50444af8487.
  - claim: WP-1 is the only released WP implementation carrier after the architecture merge.
    command: >
      Re-pin protected Mastermind at af43f356f4f7f34cb3514d1d1099b50444af8487; search open WP PRs
      and WP-1 branches before carrier creation; create one branch/commission/PR from that exact SHA.
    result: >
      No competing WP-1 PR/branch existed; Mastermind PR #178 is DRAFT/HOLD-FOR-SOL on
      sol/worker-presence-dialogue-wp1-20260827 with commission head
      5e6628b9d469bc0d1e839a9d7423421815f9fad0. No runtime claim/execution proof exists from PR creation.
  - claim: WP ownership does not supersede current ASD-A2/A3 Agent OS gates.
    command: >
      Read current Macro main ca671bf404feb7d5212da9da3f6ad458efd331dd and
      WS:CHAIRMAN-CONTROL-ROOM after ASD-A2 revalidation records #6556.
    result: >
      ASD-A2 remains todo/separately gated behind native action-time confirmation and real production
      Relay canary; ASD-A3 remains after A2. Workstream still forbids another dialogue workstream and
      generic Wake/dispatch absorption.
unverified:
  - claim: WP-1 V2 dialogue implementation exists and passes its acceptance law.
    what_would_verify: >
      A real builder return on the single Mastermind #178 carrier with RED-before TDD evidence, exact
      WP-1 changed paths, V1 compatibility, focused/full hosted CI, CodeQL/security, adversarial review,
      mutation/no-rebuild receipts and Sol acceptance. PR existence alone is insufficient.
  - claim: Company-dialogue MCP is built.
    what_would_verify: >
      Only after accepted WP-1, a separately released WP-2 carrier implementing the frozen six-tool
      production-inert facade and existing MCP capability-policy compatibility.
  - claim: Dialogue turns automatically wake/resume the right Sol/Fable responsibility.
    what_would_verify: >
      Only after accepted WP-1, accepted WP-TW1 pure classifier, then separately gated WP-TW2
      Relay-observer/Wake composition reconciled against final Wake #174 and production Agent Relay law,
      followed by the real zero-Chairman-intermediate-action bilateral canary.
unresolved:
  - "WP architecture is SPEC_ONLY after #177; no runtime capability became live from the records merge."
  - "Mastermind #178 is a released implementation carrier, not proof any operator has claimed or begun it."
  - "WP-2 and WP-TW1 remain held until WP-1 is accepted; do not fan them out early by creating temporary duplicate V2 contracts."
  - "WP-TW2 remains further held behind WP-TW1 plus exact Wake #174 and production Agent Relay prerequisites."
  - "ASD-A2/A3 proceeds independently under its current Agent OS gate and must not be marked satisfied by WP implementation code."
next_actions:
  - "Primary: review the first genuine builder return on Mastermind #178 against the merged WP-1 plan; do not call the commission PR executing before evidence exists."
  - "On WP-1 Sol PASS/merge, re-pin protected Mastermind and collision-census again; only then release separate WP-2 and WP-TW1 carriers in parallel."
  - "Keep ASD-A2 revalidation/production canary on its existing independent carrier and authority boundary."
do_not_redo:
  - "Do not create WS:WORKER-PRESENCE, WS:ACTIVE-AGENT-COMMS or another dialogue/watcher workstream."
  - "Do not create another WP-0 architecture carrier; #177/af43f356f4f7f34cb3514d1d1099b50444af8487 is the accepted package."
  - "Do not create a second WP-1 branch/PR while #178 is open/ambiguous."
  - "Do not treat Slack display identity, provider/model/account, MCP server identity or PR authorship as Executive Worker identity/authority."
  - "Do not expose generic Slack MCP tools to workers, mint one Slack app/token per ephemeral worker, or use personal ChatGPT/Claude principals as generic Worker identities."
  - "Do not implement turn_watcher.py inside WP-1; WP-TW1 owns that file after WP-1 acceptance."
  - "Do not add Agent Relay background polling/Wake adapter in WP-1/WP-TW1; WP-TW2 owns that later gated composition."
  - "Do not use WP work to bypass ASD-A2 credentials/production proof, Wake #174, C1/B2/C2, CF2/HF1/PF1/MH1 or existing session-target law."
danger_areas:
  - "Slack transport can look like runtime execution; preserve transport vs Worker claim vs Wake target acknowledgement distinctions."
  - "The turn-watcher amendment permits validated dialogue to become a Wake source only; it does not make Slack a task/authority plane."
  - "WP-1 service.py is a future collision hotspot with WP-TW2; WP-TW2 must wait and re-pin after WP-1/ASD/Wake movement."
prs: [177, 178]
decisions:
  - DEC:CHAIRMAN-CONTROL-ROOM-ACTIVE-SESSION-DIALOGUE-F0-ACCEPTED
  - DEC:AUTONOMY-V1-DISPATCH-DIALOGUE-RUNTIME-SEPARATION
discoveries:
  - DSC:AGENT-DISPATCH-CURRENTLY-HAS-NO-WORKER-RECEIVER
---

# Return point

Start from protected Mastermind merge `af43f356f4f7f34cb3514d1d1099b50444af8487`, Mastermind
WP-1 carrier #178, current Macro `WS:CHAIRMAN-CONTROL-ROOM`, and current ASD-A2 revalidation truth.
WP-0 is source law only. The exact next WP action is a genuine builder return on #178 followed by
Sol review; WP-2 and WP-TW1 remain held. ASD-A2 remains independent and separately gated.