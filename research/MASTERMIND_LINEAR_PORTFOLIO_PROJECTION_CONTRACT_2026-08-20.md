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

Linear does **not** replace Mastermind OS / Agent OS, GitHub, or the execution control planes.

## 1. Authority order

When surfaces disagree, use this order and surface the discrepancy rather than silently choosing the convenient answer:

1. **Mastermind OS / Agent OS** — canonical orchestration truth: workstream identity, dependencies, decisions, discoveries, handoffs, next actions, authority walls, CEO/operator gates, and proof requirements.
2. **GitHub** — exact execution/evidence truth: branches, commits, pull requests, review state, CI, merges, and landed artifacts.
3. **Linear** — portfolio projection: projects, current deliverables, executive/operator gates, selective execution links, and status summaries.
4. **Slack** — communication/event transport; never canonical program state.

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

A tracked PR links to its current `MAS-…` issue and owning `WS:<KEY>`. The PR remains the execution object; Linear shows its product meaning and current state.

## 3. The no-duplicate-task-store law

`DEC:AGENTOS-NO-TASK-STORE` remains binding. Agent OS workstreams + inline waves + PRs already provide durable work identity and execution decomposition. Therefore:

- do not bulk-import every historical PR into Linear;
- do not mirror every Agent OS decision/discovery/handoff as a Linear ticket;
- do not create a second dependency graph in Linear;
- do not use Linear issue comments as the organizational memory of why a decision was made.

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

## 7. Explicit gate labels

Use labels to make authority visible without reading the whole issue:

- `Agent OS Projection` — item projected from canonical workstream state;
- `CEO Gate` — Chairman/Sol decision/acceptance is required;
- `Operator Action` — production/environment action belongs to a human/operator boundary;
- `Production Proof` — landed bytes are not enough; a real path receipt is owed;
- `Execution Hold` — merge/deploy/start is explicitly not authorized;
- `Unmapped Execution` — real GitHub work has no evidence-backed canonical workstream owner yet.

`Unmapped Execution` is a defect to adjudicate, not permission to invent a generic catch-all workstream.

## 8. Projector contract

The eventual Agent OS → Linear projector is **one-way and advisory**.

Inputs:

- current canonical Agent OS workstream records;
- exact GitHub execution state;
- stable Agent OS keys and Linear IDs.

Outputs:

- Linear project summary/state;
- current tracked wave/deliverable issues;
- structured CEO/operator/production gates;
- reconciliation warnings.

Hard rules:

1. Never auto-write Agent OS from a Linear edit.
2. Never close a proof/authority gate because a PR merged.
3. Key on stable `WS:<KEY>` / `MAS-…`, never title similarity alone.
4. Be idempotent.
5. Start with a dry-run/report-only diff before automated mutation.
6. Surface direct-record-vs-generated-view-vs-GitHub disagreements explicitly.

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

## 11. Completion test

The Linear layer is healthy when a cold Sol/Fable session can:

1. open Linear and identify the live portfolio/gates;
2. enter a workstream project;
3. reach the canonical Agent OS record and current `MAS-…` deliverable;
4. reach exact GitHub proof in a few clicks;
5. see immediately when merge is not completion;
6. see orphan/unmapped execution instead of silently losing it;
7. hand a bounded commission to another agent without forcing it to rediscover product structure.

That is the role Linear serves. It is a product/portfolio lens over canonical truth, not a replacement for it.
