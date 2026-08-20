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
  - "Mastermind PR #91 / Linear MAS-48 — records-only architecture merge transiently projected the still-unproven program as Done"
  - "Mastermind PR #96 / Linear MAS-75 — records-only implementation-law merge projected the zero-code implementation issue as Done until Sol repaired it"
  - "https://linear.app/docs/github — native branch-ID auto-link, closing/non-closing/relation linkage, and skip/ignore suppression semantics"
  - "research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md — native linkage correction"
  - "agentos/discoveries/DSC-LINEAR-BRANCH-AUTOLINK-CAN-FALSE-COMPLETE.md — live regression evidence"
affects:
  - WS:AGENT-OS
  - project-active-build-control
  - MAS-67
  - research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md
  - research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md
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

A stronger correction is now required for **the Linear object linked to the PR itself**. The
2026-08-20 MAS-48/#91 and MAS-75/#96 incidents proved that a records-only architecture PR can
also falsely complete the very delivery/program issue it references when native branch-ID
linking and merge-status automation are allowed to infer semantics from Git identity alone.

Therefore:

- GitHub merge is execution/evidence truth; Linear `Done` is semantic deliverable completion.
- They coincide only when the relationship explicitly says this PR completes this Linear object
  **and** the PR actually satisfies that object's acceptance/stop condition.
- Architecture, source-law, research, proof, and other contributing PRs must use non-closing or
  relation-only linkage to delivery/program issues; they never inherit merge-to-Done merely
  because they mention the issue.
- A delivery issue ID in a branch name is a native Linear automation input, not neutral metadata.
  Use it only when that branch's merge is legitimately allowed to drive that issue's lifecycle.
- If a non-closing/reference PR unavoidably uses a branch that already contains the delivery
  issue ID, use Linear's documented `skip <ISSUE>` / `ignore <ISSUE>` suppression so later pushes
  or merge cannot silently re-link it.

The exact native relationship and authoring rules are frozen in
`research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md`. This is a
correction to projection mechanics, not a new authority store and not a reason to disable the
useful native Linear↔GitHub integration.
