# Mastermind-X Linear Portfolio Projection Contract

**Status:** operating contract · 2026-08-20  
**Authority:** organizational architecture; records only  
**Owning context:** `WS:AGENT-OS`  
**Linear rollout:** `MAS-6` (forward GitHub ↔ Linear linkage)  

## 0. Purpose

Linear is Mastermind-X's **bird's-eye product and portfolio surface**. It answers questions that the canonical repository state is deliberately not optimized to answer at a glance:

- What product/intelligence programs are live?
- What is currently blocked, in review, or waiting on an executive/operator gate?
- Which build/research deliverables are active under each program?
- What changed recently, and where is the execution proof?

Linear does **not** replace Mastermind OS / Agent OS, Executive OS, GitHub, or the execution control planes.

## 1. Authority order

When surfaces disagree, use this order and surface the discrepancy rather than silently choosing the convenient answer:

1. **Mastermind OS / Agent OS** — canonical organizational orchestration truth: workstream identity, dependencies, decisions, discoveries, handoffs, next actions, authority walls, CEO/operator gates, and proof requirements.
2. **Mastermind Executive OS** — canonical Job/Attempt/Worker/Event lifecycle wherever Executive execution applies.
3. **GitHub** — exact implementation/evidence truth: branches, commits, pull requests, review state, CI, merges, and landed artifacts.
4. **Linear** — portfolio projection: projects, current deliverables, executive/operator gates, selective execution links, and status summaries.
5. **Slack** — communication/write transport and acknowledgement; never canonical program or execution state.

A generated Agent OS rollup is an index, not a substitute for the current canonical workstream record. If a generated view says a PR is awaiting CI but exact GitHub says it merged, record a reconciliation warning and read the current workstream before deciding what remains.

## 2. Entity mapping

### Agent OS workstream → Linear project

Every materially live `WS:<KEY>` gets one Linear project named with its stable workstream key:

`WS:<KEY> — <human title>`

The Linear project is the executive/product view of the workstream. It links to the canonical workstream record and summarizes the **current** outcome, next gate, and authority boundary.

Do not create a rival Linear project for every wave, PR, branch, or session.

### Agent OS wave / current deliverable → Linear issue

A `MAS-…` issue is warranted when the item is a currently actionable deliverable or gate that benefits from product-level visibility. Typical classes:

- active build/research wave;
- CEO/Sol decision or acceptance gate;
- operator-only production/environment action;
- production-proof receipt;
- held execution object that must not be mistaken for ordinary work;
- reconciliation of canonical state vs exact execution state.

Linear issues are **not** the canonical wave store. The wave still lives in Agent OS.

### GitHub PR → execution evidence

A tracked PR links to its current `MAS-…` issue and owning `WS:<KEY>`. The PR remains the implementation/evidence object; Linear shows its product meaning and current state.

### Executive Job → lifecycle evidence where applicable

When a work item is admitted into Mastermind Executive OS, Linear may link to or summarize that Job's canonical state. Linear does not replicate the Job/Attempt/Event lifecycle and must never infer a Job transition from a Slack message or Linear edit.

## 3. The no-duplicate-task-store law

`DEC:AGENTOS-NO-TASK-STORE` remains binding. Agent OS workstreams + inline waves + PRs already provide durable organizational work identity and execution decomposition; Executive OS owns runtime Job/Attempt/Worker/Event state where used. Therefore:

- do not bulk-import every historical PR into Linear;
- do not mirror every Agent OS decision/discovery/handoff as a Linear ticket;
- do not create a second dependency graph in Linear;
- do not use Linear issue comments as the organizational memory of why a decision was made;
- do not mirror Executive Job/Event lifecycle into mutable Linear state as a rival authority.

Linear is intentionally **selective**. Its value is compression and visibility, not duplicate completeness.

## 4. Forward commission contract

Every substantive tracked commission should carry this small stable header:

```text
WORKSTREAM: WS:<KEY>
LINEAR: MAS-123
ROLE: builder|researcher|reviewer|operator
MISSION: <one bounded outcome>
AUTHORITY: <what this worker may change/decide>
ACCEPTANCE: <observable proof conditions>
DO NOT: <scope fences / authority walls>
RETURN: <PR + Agent OS handoff/receipt requirements>
```

A builder must never be asked to reconstruct the portfolio hierarchy from a broad prompt.

## 5. Branch and PR join contract

Preferred branch shape for tracked work:

`<seat-or-worker>/mas-123-<short-slug>`

Tracked PRs carry near the top:

```text
Workstream: WS:<KEY>
Linear: MAS-123
Wave: <wave-id|maintenance>
Authority: <build|research|records|repair>
Completion: <merge-is-done|BUILT_NOT_PROVEN|needs-sol|needs-operator>
```

The metadata is a join key, not a replacement for the house proof format.

## 6. State semantics

### Linear project state

- **Backlog / planned** — accepted portfolio item, not executing.
- **In Progress** — at least one material current wave/gate is live.
- **Completed** — canonical workstream is done (or the portfolio slice has an explicitly bounded completed end-state).
- **Canceled** — canonical work was killed/canceled; preserve reason in Agent OS.

### Linear issue state

- **Todo/Backlog** — commissioned/planned, not executing.
- **In Progress** — active execution/operator/production-proof work.
- **In Review** — awaiting review, executive acceptance, operator ruling, or intentionally held proof object.
- **Done** — that Linear deliverable's acceptance condition is complete.

A merged PR does **not** imply workstream completion. If Agent OS says `BUILT_NOT_PROVEN`, `needs_ceo`, `needs_operator`, prospective accrual, or a production receipt is owed, the remaining gate stays visible.

Likewise, a Slack acknowledgement does not imply a Job is dispatched/running, and a Job result does not automatically satisfy an Agent OS or production-proof gate unless the canonical owner records that closure.

## 7. Explicit gate labels

Use labels to make authority visible without reading the whole issue:

- `Agent OS Projection` — item projected from canonical workstream state;
- `CEO Gate` — Chairman/Sol decision/acceptance is required;
- `Operator Action` — production/environment action belongs to a human/operator boundary;
- `Production Proof` — landed bytes are not enough; a real path receipt is owed;
- `Execution Hold` — merge/deploy/start is explicitly not authorized;
- `Unmapped Execution` — real GitHub work has no evidence-backed canonical workstream owner yet;
- `Maintenance Exception` — a specifically adjudicated bounded repair that does not warrant a new workstream and must stop at its named boundary.

`Unmapped Execution` is a defect to adjudicate, not permission to invent a generic catch-all workstream. `Maintenance Exception` is not a generic loophole.

## 8. Projector contract

The eventual Agent OS → Linear projector is **one-way and advisory**.

Inputs:

- current canonical Agent OS workstream records;
- exact GitHub implementation state;
- stable Agent OS keys and Linear IDs;
- optionally, read-only Executive OS status for explicitly linked Jobs.

Outputs:

- Linear project summary/state;
- current tracked wave/deliverable issues;
- structured CEO/operator/production gates;
- execution links and reconciliation warnings.

Hard rules:

1. Never auto-write Agent OS from a Linear edit.
2. Never mutate Executive OS from a Linear projection.
3. Never close a proof/authority gate because a PR merged.
4. Never advance an Executive Job because Slack/Linear says work started or completed.
5. Key on stable `WS:<KEY>` / `MAS-…` / explicit Job IDs, never title similarity alone.
6. Be idempotent.
7. Start with a dry-run/report-only diff before automated mutation.
8. Surface direct-record-vs-generated-view-vs-GitHub/Executive disagreements explicitly.

## 9. Forward PR linkage validator

The first enforcement hook is report-only:

1. inspect newly opened substantive PRs for `WS:<KEY>` + `MAS-…`;
2. resolve both identities;
3. validate optional wave ID when supplied;
4. emit `portfolio_linkage_missing` plus an exact repair when missing/unresolvable;
5. allow only an explicit typed `maintenance_exception` for genuinely tiny bounded maintenance;
6. measure false positives before any class becomes a hard gate.

This is portfolio hygiene, not a new merge authority.

## 10. Historical backfill law

Backfill **current meaning**, not repository archaeology.

Prioritize:

- materially live Agent OS workstreams;
- active/held high-value PRs;
- current CEO/operator/production gates;
- open execution whose owner is ambiguous.

Do not create tickets for thousands of already-settled PRs merely to make Linear numerically complete.

## 11. Slack / Executive OS sequencing note

The Slack program's first implementation vertical is `MAS-48`: Personal-Pro Sol → `#ceo-control-room` → existing Executive CEO-intent/Job authority → Slack ACK → MCP readback. `MAS-29/30/31` are architecture-held for post-MAS-48 redesign and must not implement the superseded new Slack lifecycle-store / durable seat-inbox design.

This sequencing is part of the Linear portfolio projection; the canonical implementation authority remains in the accepted Executive OS architecture and repository records.

## 12. Completion test

The Linear layer is healthy when a cold Sol/Fable session can:

1. open Linear and identify the live portfolio/gates;
2. enter a workstream project;
3. reach the canonical Agent OS record and current `MAS-…` deliverable;
4. reach exact GitHub proof and, when applicable, read-only Executive Job status in a few clicks;
5. see immediately when merge is not completion;
6. see orphan/unmapped execution instead of silently losing it;
7. distinguish transport acknowledgement from canonical execution state;
8. hand a bounded commission to another agent without forcing it to rediscover product structure.

That is the role Linear serves. It is a product/portfolio lens over canonical truth, not a replacement for it.
