---
key: MAS48-CEO-INGRESS-V1-ACCEPTED-ARCHITECTURE
question: >
  What exact architecture and implementation law now govern the first Personal-Pro
  Sol writeback path, and which earlier Slack-bridge assumptions are superseded?
answer: >
  Mastermind PR #91, merged as e61e48904302d0aae53baeab0e2681ee3fbec97d,
  remains the accepted parent product/system architecture for MAS-48. Mastermind
  PR #96, merged as 5f9016f2db45acf60d4344656d85dfc496b87252,
  is the accepted repository-canonical implementation law for MAS-75 / PR-A.
  Personal-Pro Sol reads Executive state through the existing read-only MCP,
  carries its observed Mastermind/Macro grounding in a bounded Slack request,
  and the future Slack transport reaches a dedicated CeoIngress AF_UNIX listener
  in the same ExecutiveControlService process/runtime. CeoIngress exposes only
  closed v1 submit and Slack-namespace status schemas, derives privileged fields
  inside trusted Executive code, and terminates at the existing
  ceo_intent.submit_intent sink. Executive SQLite remains the sole lifecycle
  authority. CEO admission readiness is distinct from worker execution readiness,
  so one QUEUED Job may be admitted while generic service state remains
  AWAITING_CANARY and Codex execution remains unavailable. No generic Slack
  lifecycle store, seat inbox, Wake dependency, broad Operator socket access,
  canonical Slack-metadata persistence, cancellable mutation timeout, or second
  readiness store is authorized by V1.
rationale: >
  The accepted design solves the Chairman's actual constraint: choose the Personal
  Pro seat for reasoning quality without requiring that same ChatGPT plan to own a
  production custom-MCP write entitlement, and without making CEO communication
  hostage to the separate Codex workspace/auth blocker. Reusing the canonical
  CEO-intent Job/Event sink preserves one lifecycle authority. A dedicated ingress
  socket reduces the network-facing principal's blast radius, while separate
  admission readiness preserves the existing worker canary gate honestly rather
  than manufacturing execution readiness. Existing-intent-first reconciliation,
  effect-unknown recovery through deterministic status, startup refusal fencing,
  ingress-handler shutdown drain, and opaque dependency errors close the final
  implementation races without adding a second durable control plane.
alternatives:
  - option: Add the Slack principal to the existing Operator socket/group and command-allowlist it
    why_not: >
      The existing socket terminates in a broad generic dispatcher. Accepted law
      requires structural transport separation: the Slack principal never joins
      _mastermind_ops and never reaches the Operator dispatcher.
  - option: Persist Slack lifecycle, dedupe, grounding, retry, or seat-inbox state in a new database
    why_not: >
      Executive SQLite already owns Job/Event idempotency and lifecycle truth.
      Deterministic Slack intent identity plus canonical status provide recovery
      without duplicating lifecycle authority.
  - option: Wait for Codex worker readiness before allowing CEO admission
    why_not: >
      Conflates communication/admission with execution and leaves the Pro-Sol
      writeback outcome blocked by an unrelated provider entitlement problem.
  - option: Time out and cancel a started sync CEO-intent mutation
    why_not: >
      Cancelling an awaiting asyncio coroutine cannot safely cancel the underlying
      SQLite mutation thread. A timeout could therefore be followed by a real
      commit and would falsely claim cancellation. Transport timeout/disconnect is
      effect-unknown and must reconcile through deterministic status.
  - option: Reuse ordinary external-text sanitization for model-facing provider/backend errors
    why_not: >
      The repository sanitizer intentionally preserves filesystem paths and URLs.
      CeoIngress therefore emits fixed opaque dependency-failure messages rather
      than forwarding sanitized exception text.
  - option: Reinterpret the Executive running marker as listener readiness
    why_not: >
      Current service law creates that marker while acquiring the single service
      lock before Runtime/listener startup. It remains instance/lock ownership;
      a new process-local startup latch, not another durable marker, fences ingress
      readiness.
evidence:
  - "Mastermind PR #91 merged e61e48904302d0aae53baeab0e2681ee3fbec97d — five-record MAS-48 parent architecture freeze"
  - "Mastermind PR #96 merged 5f9016f2db45acf60d4344656d85dfc496b87252 — repository-canonical PR-A implementation law"
  - "Mastermind #96 final reviewed head 69ac38a0d4438f7aa7e1c6f7deec76595cafb55e — hosted CI run 260 SUCCESS"
  - "Mastermind #96 CI receipt — discovered=272 excluded=0 running=272; source compile and shell validation PASS"
  - "Mastermind #96 changed-file census — exactly three research records; zero runtime/config/test/workflow files"
  - "MAS-75 builder branch fast-forwarded without force to 5f9016f2db45acf60d4344656d85dfc496b87252 and verified identical to current master"
  - "Macro PR #6071 merged 58da4615788e219634a6d8defc09d1e5c80f62d5 — Linear/Slack operating law"
  - "Linear MAS-29/30/31 — Backlog dependency holds behind MAS-48/MAS-29 sequencing"
  - "Slack #agent-dispatch — MAS-75 commission is a durable handoff only; no connected Fable principal exists"
affects:
  - WS:AGENT-OS
  - MAS-9
  - MAS-48
  - MAS-75
  - MAS-29
  - MAS-30
  - MAS-31
  - agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md
  - research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Authority and supersession scope

This decision does **not** reverse `DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`.
Its layer law remains controlling: Slack is transport/acknowledgement, not runtime or
canonical state. This decision supersedes only implementation details in earlier records
where they conflict with the later accepted Mastermind architecture/law.

Technical precedence for the first PR-A implementation is:

1. Chairman/Sol product outcome and merged Mastermind PR #91 parent architecture;
2. merged Mastermind PR #96 records for PR-A mechanics:
   - `EXECUTIVE_OS_PRO_SOL_SLACK_PR_A_LIFECYCLE_CORRECTION_2026-08-20.md` (R2) — highest for service-lock/running-marker/startup-readiness;
   - `EXECUTIVE_OS_PRO_SOL_SLACK_PR_A_SECURITY_CORRECTION_2026-08-20.md` (R1) — highest for refusal-only startup fencing and model-facing dependency-error opacity;
   - `EXECUTIVE_OS_PRO_SOL_SLACK_PR_A_IMPLEMENTATION_ADJUDICATION_2026-08-20.md` — remaining PR-A mechanics;
3. current Mastermind source contracts (`ceo_intent`, `executive_service`, Executive MCP);
4. Macro #6071 layer law and Linear portfolio projection.

Linear comments are coordination archaeology after #96; they are not higher technical authority than the merged repository records.

## Binding V1 facts

- production Slack later uses a dedicated `CeoIngress` AF_UNIX socket into the same
  Executive process/runtime, never the broad Operator socket;
- the ingress has no generic command field/dispatcher and exactly two closed schemas:
  `mastermind.executive_ceo_ingress_submit.v1` and
  `mastermind.executive_ceo_ingress_status.v1`;
- status is read-only and accepts only deterministic `slack-<32hex>` CEO-intent ids;
- Slack v1 id derivation uses domain
  `mastermind.executive_slack.operation_key.v1\x00` plus normalized operation key only;
- every new submit carries non-authoritative `observed_grounding`, which must equal
  independently observed trusted grounding and survive a pre-commit re-read;
- accepted canonical intent state wins on replay before current grounding is consulted;
  an uncommitted stale request is never silently re-grounded;
- exact command-id lookup distinguishes true `not_found` from malformed durable evidence;
- a started canonical sync mutation is not wrapped in a server timeout claiming cancellation;
  disconnect/transport timeout means effect-unknown and requires status reconciliation;
- CeoIngress handlers are drained before the single Executive service lock/marker is
  released when canonical admission has started;
- dual-listener startup uses a process-local refusal latch so a sequential listener start
  cannot expose a half-ready business path;
- the existing Executive running marker remains pre-listener instance/lock ownership,
  not readiness; no second durable readiness marker/store is introduced in PR-A;
- provider/backend/internal dependency failures use fixed opaque ingress messages rather
  than forwarded exception text that could disclose paths/URLs/secrets;
- Socket Mode protocol ACK is distinct from the later user-visible Executive ACK;
- V1 does not widen canonical CEO-intent provenance merely to persist Slack metadata;
- CEO ingress may be separately armed in `AWAITING_CANARY` without setting generic
  service state `READY` or touching worker/provider execution;
- dynamic `QUARANTINED` or unknown unsafe service state blocks ingress;
- request acceptance ends at one QUEUED Job/JOB_CREATED with `dispatched=false`.

## Agent OS workstream clarification

`WS:AGENT-OS` appears in this decision's `affects` set and in the companion handoff because
that existing workstream owns **Agent OS memory maintenance**. It does **not** assign
`MAS-75` or a future CEO intent an Executive runtime `workstream: WS:AGENT-OS` provenance
value. MAS-75 currently has no canonical Executive OS Agent OS workstream mapping, and PR-A
must not invent one merely because its architecture memory is maintained here.

## Current implementation gate

`MAS-75` / PR-A is the only authorized implementation wave. Its sole branch is:

`chatgpt1/mas-75-pr-a-dedicated-ceo-ingress-shared-request-law`

Exact builder base after #96 acceptance:

`5f9016f2db45acf60d4344656d85dfc496b87252`

The branch was fast-forwarded without force and verified identical to current Mastermind
`master` (`ahead=0`, `behind=0`, zero changed files). No implementation commit or PR existed
at that acceptance point, and no connected Fable/Linear/Slack principal had claimed it.
Therefore MAS-75 correctly remains `Todo` until an external principal-builder session
actually claims the branch.

PR-A is hermetic: shared v1 high-level request law, dedicated two-schema local ingress,
trusted grounding/replay, admission-vs-execution readiness separation, timeout/effect-
unknown recovery, shutdown drain, opaque errors, canonical Job/readback proof, and tests.

PR-A does not include Slack SDK/networking, launchd/install/principal provisioning, Wake,
Codex auth repair, worker execution, a new durable store, or production arming. PR-B and
PR-C remain uncommissioned until Sol adversarially accepts the preceding slice.

Records-only Phase 1F-C PRs #94/#95 freeze future strict
`mastermind.ceo_intent.v2` / schema-v4 work; MAS-75 remains v1-only and must stop for
semantic reconciliation if a Phase 1F-C runtime implementation lands in overlapping
authority files before PR-A merges.
