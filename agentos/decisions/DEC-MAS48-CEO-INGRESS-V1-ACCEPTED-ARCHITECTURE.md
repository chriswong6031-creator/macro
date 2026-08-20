---
key: MAS48-CEO-INGRESS-V1-ACCEPTED-ARCHITECTURE
question: >
  After Mastermind PR #91, what exact architecture governs the first Personal-Pro
  Sol writeback path, and which earlier Slack-bridge implementation assumptions
  are superseded?
answer: >
  Mastermind PR #91, merged as e61e48904302d0aae53baeab0e2681ee3fbec97d,
  is the accepted authority for MAS-48. Personal-Pro Sol reads Executive state
  through the existing read-only MCP, carries its observed Mastermind/Macro
  grounding in a bounded Slack request, and the Slack transport reaches a
  dedicated CeoIngress AF_UNIX listener in the same ExecutiveControlService
  process/runtime. CeoIngress exposes only closed v1 submit and Slack-namespace
  status schemas, derives privileged fields inside trusted Executive code, and
  terminates at the existing ceo_intent.submit_intent sink. Executive SQLite
  remains the sole lifecycle authority. CEO admission readiness is distinct from
  worker execution readiness, so one QUEUED Job may be admitted while generic
  service state remains AWAITING_CANARY and Codex execution remains unavailable.
  No generic Slack lifecycle store, seat inbox, Wake dependency, broad Operator
  socket access, or canonical Slack-metadata persistence is authorized by V1.
rationale: >
  The accepted design solves the Chairman's actual constraint: choose the Personal
  Pro seat for reasoning quality without requiring that same ChatGPT plan to own a
  production custom-MCP write entitlement, and without making CEO communication
  hostage to the separate Codex workspace/auth blocker. Reusing the canonical
  CEO-intent Job/Event sink preserves one lifecycle authority. A separate ingress
  socket reduces the network-facing principal's blast radius, while separate
  admission readiness preserves the existing worker canary gate honestly rather
  than manufacturing execution readiness. Slack protocol acknowledgement and
  Executive acceptance are separate facts; crash recovery uses bounded Slack
  history plus canonical intent idempotency rather than a new durable queue.
alternatives:
  - option: Add the Slack principal to the existing Operator socket/group and command-allowlist it
    why_not: >
      The existing socket terminates in a broad generic dispatcher. PR #91 instead
      requires structural transport separation: the Slack principal never joins
      _mastermind_ops and never reaches the Operator dispatcher.
  - option: Persist Slack lifecycle, dedupe, grounding or seat-inbox state in a new database
    why_not: >
      Executive SQLite already owns Job/Event idempotency and lifecycle truth.
      Duplicating those facts would violate the one-canonical-system law.
  - option: Wait for Codex worker readiness before allowing CEO admission
    why_not: >
      Conflates communication/admission with execution and leaves the Pro-Sol
      writeback outcome blocked by an unrelated provider entitlement problem.
  - option: Store Slack message/thread ids inside CEO-intent JOB_CREATED provenance in V1
    why_not: >
      The first production proof does not require widening the canonical v1
      provenance contract. Slack plus the proof packet retain transport evidence;
      a later durable cross-transport provenance requirement needs its own schema ruling.
evidence:
  - "Mastermind PR #91 merged e61e48904302d0aae53baeab0e2681ee3fbec97d — five-record MAS-48 architecture freeze"
  - "Mastermind PR #91 final exact-head CI run 252 — success before merge"
  - "Macro PR #6071 merged 58da4615788e219634a6d8defc09d1e5c80f62d5 — Linear/Slack operating law"
  - "Linear MAS-48 — accepted parent program; MAS-75 is the sole active PR-A commission"
  - "Linear MAS-29/30/31 — Backlog architecture holds pending MAS-48 proof"
  - "Slack #agent-dispatch — MAS-75 commission is a durable handoff only; no Fable Slack principal exists"
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
reversibility: medium
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Supersession scope

This decision does **not** reverse `DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`.
Its layer law remains controlling: Slack is transport/acknowledgement, not runtime or
canonical state. This decision supersedes only implementation details in earlier records
where they conflict with the later accepted Mastermind PR #91 architecture.

The following V1 facts are now binding:

- production Slack uses a dedicated `CeoIngress` AF_UNIX socket into the same Executive
  process/runtime, never the broad Operator socket;
- the ingress has no generic command field/dispatcher and exactly two closed schemas:
  `mastermind.executive_ceo_ingress_submit.v1` and
  `mastermind.executive_ceo_ingress_status.v1`;
- status is read-only and accepts only deterministic `slack-<32hex>` CEO-intent ids;
- Slack v1 id derivation uses domain
  `mastermind.executive_slack.operation_key.v1\x00` plus normalized operation key only;
- every new submit carries non-authoritative `observed_grounding`, which must equal
  independently observed trusted host grounding and survive a pre-commit re-read;
- accepted canonical intent state wins on replay; an uncommitted stale Slack request is
  never silently re-grounded;
- Socket Mode protocol ACK is distinct from the later user-visible Executive ACK;
- V1 does not widen canonical CEO-intent provenance merely to persist Slack metadata;
- CEO ingress may be separately armed in `AWAITING_CANARY` without setting generic
  service state `READY` or touching worker/provider execution;
- `QUARANTINED` or unknown unsafe service state blocks ingress;
- request acceptance ends at one QUEUED Job/JOB_CREATED with `dispatched=false`.

## Current implementation gate

`MAS-75` / PR-A is the only authorized implementation wave. It is hermetic: shared v1
high-level request law, trusted grounding seam, dedicated two-schema local ingress,
admission-vs-execution readiness separation, canonical Job/readback proof, and tests.

PR-A does not include Slack SDK/networking, launchd/install/principal provisioning, Wake,
Codex auth repair, worker execution, a new durable store, or production arming. PR-B and
PR-C remain uncommissioned until Sol adversarially accepts the preceding slice.

The MAS-75 branch of record was reconciled to current Mastermind `master`
`a49ac647fff64d034cc965cf54ac48968d6c15be`, after records-only Phase 1F-C PRs #94/#95.
Those records freeze future strict `mastermind.ceo_intent.v2` / schema-v4 work; MAS-75
must remain v1-only and stop for semantic reconciliation if that runtime implementation
lands in overlapping authority files before PR-A returns.
