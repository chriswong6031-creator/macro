---
key: LINEAR-IS-PORTFOLIO-PROJECTION-NOT-CANONICAL
question: >
  Should Mastermind-X use Linear as a new canonical work/task database, or as a
  bird's-eye projection of the existing Agent OS + GitHub work model?
answer: >
  Use Linear as a selective one-way portfolio projection. Agent OS remains canonical
  for workstream identity, dependencies, decisions, discoveries, handoffs, next actions
  and proof/authority gates; GitHub remains the execution/evidence plane. Linear projects
  materially live workstreams, current deliverables and executive/operator/production gates.
rationale: >
  The organization already has a durable work-identity model: Agent OS workstreams with
  inline waves, plus PRs as execution objects. DEC:AGENTOS-NO-TASK-STORE explicitly rejects
  a second task registry inside the knowledge plane. Making Linear authoritative as well
  would create two mutable dependency/state graphs and force every session to reconcile
  which copy wins. The actual unmet need is product-level compression: the Chairman and
  Sol need to see current programs, gates and progress without reading dozens of records
  or reconstructing PR meaning. A one-way projection solves that job while preserving
  Agent OS's context compiler and GitHub's exact execution receipts.
alternatives:
  - option: Make Linear the canonical task/workstream system and migrate Agent OS state into it
    why_not: >
      Duplicates or displaces the existing knowledge plane, breaks read-local Agent OS context,
      and creates a second mutable dependency/decision store whose drift is harder to detect than
      the current file-backed truth.
  - option: Mirror every Agent OS wave, DEC, DSC, handoff and historical PR into Linear
    why_not: >
      Produces a numerically complete but operationally noisy duplicate corpus. Linear's value is
      executive compression; high-cardinality evidence and organizational memory already have
      canonical homes.
  - option: Leave Linear unused and rely on Agent OS/GitHub alone
    why_not: >
      Preserves the current human burden: product progress remains fragmented across workstream
      records, PRs and sessions with no strong bird's-eye portfolio surface.
evidence:
  - "agentos/decisions/DEC-AGENTOS-NO-TASK-STORE.md — Chairman-ratified workstream waves + PR execution law"
  - "research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md §1 — workstream is the durable unit of work identity"
  - "research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md — durable cold-stranger state lives in Agent OS, not chat"
  - "research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md — entity/state/projection contract"
affects:
  - WS:AGENT-OS
  - project-active-build-control
  - research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Operational consequence

The canonical join is:

`WS:<KEY> → Linear Project → current MAS issue → GitHub PR → proof/acceptance → Agent OS transition`.

Linear may display a stale or conflicting state; when it does, repair the projection. Never
rewrite Agent OS merely to make the Linear dashboard green.

## Completion is not merge

A merged PR may close an implementation issue while a separate production/CEO/operator gate
stays open. If Agent OS says `BUILT_NOT_PROVEN`, prospective accrual, human rights approval,
operator configuration, or CEO acceptance remains owed, Linear must keep that fact visible.
