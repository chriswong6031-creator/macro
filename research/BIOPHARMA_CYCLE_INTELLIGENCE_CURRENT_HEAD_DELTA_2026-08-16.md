# Biopharma Cycle Intelligence — Current-Head Delta and Architecture Reconciliation

**Status:** Binding current-state addendum for the architecture draft; no runtime authority  
**Date:** 2026-08-16 America/New_York / 2026-08-17 UTC repository activity  
**Original BCI architecture freeze:** `810d6ae0b4438072e9c52ae3f6a0520f5221d37b`  
**Reconciled current `main`:** `5d600641bc3513f69a37cfb8cac1f1d86238e896`  
**Masterplan:** `research/BIOPHARMA_CYCLE_INTELLIGENCE_OS_MASTERPLAN_2026-08-16.md`

---

# 0. Verdict

The repository movement does **not** change the central architecture ruling.
It strengthens it.

Keep specialist programs independent and federate them through explicit ports.
Do not pause the company and mega-merge BioCatalyst, Market Memory, FIF, Defense,
Earnings, Options, Capital Structure, Neural Web, Prophet, Terminal, and Portfolio.
Freeze only overlapping ownership and unbounded expansion.

The latest changes add one important reuse boundary:

> **BCI must now evaluate the merged Company Intelligence `event_workspace.v1`
> as the canonical user-facing event-investigation publication/read pattern.**

BCI still needs a domain-specific immutable market-episode packet for prospective
memory, outcomes, event studies, and Market Memory ingestion. It should not assume
that it also needs a second user-facing event-workspace system.

---

# 1. Changes after the original architecture freeze

## 1.1 BioCatalyst P0-C1 merged

PR `#5810` merged as:

```text
9d91bf877da428b96741c80c20f5a1c2a2b5ccc1
```

It now distinguishes:

- locked;
- valid empty;
- source outage;
- integrity block;
- normal hydration;
- dossier-local rendering faults.

Strict frontend validators remain intact. The merge did not change collectors,
source truth, Market Memory, Prophet, or backend contracts.

**Current ruling:** BioCatalyst P0-C1 implementation is no longer pending. The
remaining P0 acceptance is real entitled production-browser proof and any exact
follow-up failure it reveals. Do not resume broad BioCatalyst feature or alpha
work merely because P0-C1 merged.

## 1.2 Earnings production recovery merged

PR `#5791` merged as:

```text
53a7fd0821415f9eb259d34c02f9edfb74a7c6a4
```

The story-packet path now uses bounded newest-first catch-up and direct-parent
hourly verification rather than replaying the complete lineage on every run.
The public-wire path was adjusted for the repository's protected-main boundary.

**BCI implication:** preserve bounded projection and immutable lineage as a shared
operational pattern. Do not make one BCI refresh walk every historical episode or
rebuild the full corpus on each source change.

## 1.3 `event_workspace.v1` became real

PR `#5817` merged as current `main`:

```text
5d600641bc3513f69a37cfb8cac1f1d86238e896
```

It binds one real AAPL FY2026 Q3 event to:

- real issuer/CIK;
- real 8-K accession and Exhibit 99.1;
- a held transcript;
- canonical event aliases;
- a marker-last immutable sibling nest under
  `company_intelligence/event_workspaces/`;
- a verified Neural Web reader;
- correction replay with the same event identity and a new generation;
- context-only authority and all-false Prophet flags.

Canonical implementation anchors:

- `engine/company_intelligence/event_workspace.py`;
- `engine/company_intelligence/event_workspace_build.py`;
- `engine/company_intelligence/event_id_adapter.py`;
- `engine/neuralweb/company_intelligence_reader.py`;
- `tests/test_company_intelligence_event_workspace.py`.

**BCI implication:** BCI-0B must answer three different questions rather than
inventing one broad new contract:

1. Can `event_workspace.v1` be extended or composed for a biopharma user-facing
   investigation without making Company Intelligence own clinical truth?
2. What biopharma-specific fields must stay in a BCI context/episode packet and be
   linked into the workspace as a sibling domain block?
3. Which object is the product workspace, which is the prospective market episode,
   and which is the generic Market Memory retrieval packet?

The default recommendation is:

```text
BioCatalyst domain event/revision bytes
→ BCI immutable market episode + outcome sidecar
→ Company Intelligence event_workspace composition for user investigation
→ Market Memory index/retrieval over episode packets
→ Neural Web current context
```

This is a recommendation for BCI-0B/0C adjudication, not an implementation order.

## 1.4 Defense D0R merged

PR `#5814` merged as:

```text
810d6ae0b4438072e9c52ae3f6a0520f5221d37b
```

It records entitled Government Revenue production census and Defense architecture
packets B–H. Candidate Radar remains UI-locked and D1 was not started.

**BCI implication:** Defense remains independent. Its D0R findings can later inform
shared packet/expectation/Market Memory interfaces, but BCI neither blocks nor
absorbs D1.

## 1.5 FIF-1R remains in review

PR `#5809` remains open and mergeable. Current head at this reconciliation:

```text
457b4b4c08f962e8cd54dbaf9b7b805bd9846ed5
```

It freezes a hermetic `financial_intelligence_packet.v1` kernel with recursively
closed formula evidence, bitemporal query semantics, an independent synthetic
filing-package ledger, and Company Facts as a separate witness. It explicitly says:

- hold merge for re-review;
- do not start FIF-2.

**BCI implication:** BCI consumes FIF only after the packet is accepted and a real
production packet/service exists. It must not copy the test fixture, query kernel,
formula closure, metric registry, or filing semantics.

## 1.6 Market Memory has not earned broad continuation

The first-cause nested R2 path repair remains merged as `#5805` /
`e1ec8865ac92ccebd11f8208fe2c1e09a85c21e9`.

No later current-main commit in this reconciliation establishes:

- the final prospective W2C opportunity disposition;
- M0B completion;
- operational learned/hybrid retrieval;
- a production BCI episode adapter.

The Agent OS workstream on main still reports `awaiting_ci` and names trusted-regime
freshness as the later blocker. That durable state is stale relative to the merged
repair and must be reconciled by the Market Memory owner, not silently overwritten
by BCI.

**BCI implication:** continue treating Market Memory as the horizontal target
architecture while keeping BCI's first episode writer independently useful and
forward-compatible. Do not build a second general retriever.

## 1.7 Seasonality did not move

At this reconciliation:

- no new Seasonality PR is open or merged;
- `event_study.py` remains without a production builder;
- `model.py` / `calibration.py` remain without a forecast-producing builder;
- `prophet_bridge.py` remains without a production caller;
- `app/seasonality.py` still explicitly registers no API router;
- the checked-in program watch remains dated `2026-08-13` and retains its
  structurally unavailable workflow-order check.

The original recovery diagnosis therefore remains valid.

---

# 2. Amendments to the masterplan

Where this addendum and the first masterplan differ, this addendum wins for current
state and sequencing.

## Amendment A — current baseline

Use `5d600641bc3513f69a37cfb8cac1f1d86238e896` as the latest audited repository
head for BCI-0A reconciliation. Every later session still fetches current main.

## Amendment B — BioCatalyst concurrency

Replace “continue P0-C1” with:

> P0-C1 code is merged. Continue only the exact entitled production-browser
> acceptance and any first proven follow-up defect. Post-P0 market-response,
> asymmetry, analogue, Neural Web, and Prophet work remains routed into BCI.

## Amendment C — Defense concurrency

Replace “continue/close D0R” with:

> D0R is merged. D1 follows Defense's own acceptance and handoff. It is not a BCI
> dependency and is not absorbed into BCI.

## Amendment D — user-facing event workspace

Before creating `biopharma_cycle.event_workspace.*`, BCI-0B/0C must adjudicate
reuse of Company Intelligence `event_workspace.v1` and its marker-last verified
reader.

The likely separation is:

- BCI market episode: prospective research/memory object;
- BCI current context: compact machine/user projection;
- Company Intelligence event workspace: user-facing multi-source investigation;
- Market Memory: generic historical index/retrieval.

## Amendment E — BCI-0B required archaeology

BCI-0B must add these current-main anchors to its inventory:

- `engine/company_intelligence/event_workspace.py`;
- `engine/company_intelligence/event_workspace_build.py`;
- `engine/company_intelligence/event_id_adapter.py`;
- `engine/neuralweb/company_intelligence_reader.py`;
- the AAPL FY2026 Q3 real-event fixture and correction tests;
- the bounded earnings packet recovery pattern from PR #5791.

## Amendment F — no broad coding prompt

The latest repository movement increases, rather than reduces, the need for
BCI-0B. There are now more reusable owners and contracts to reconcile. Do not skip
archaeology and hand a worker the full BCI wave list.

## Amendment G — producer-first execution order

The original masterplan listed the prospective BCI market-episode packet before the
BioCatalyst-owned machine event projection. That order cannot support real production
proof: a decision-time episode needs a real producer-owned event/revision input.

The binding execution order is now:

```text
BCI-1  BioCatalyst-owned machine event projection
  ↓
BCI-2  prospective biopharma market episode + outcome sidecar
  ↓
BCI-3  commissioned event-study vertical
```

BCI-1 must be independently useful through a real immutable projection plus an
inspection/verifier consumer. BCI-2 must consume those exact bytes. Neither may use
the paid user API as a machine transport.

## Amendment H — contradiction authority precedes shared current context

BCI's legitimate context-only contradictions could otherwise change Portfolio
candidacy or shrink indirectly through generic `graph_conflicts` counts. Therefore:

- BCI-0D is not a late optional polish;
- BCI-4 shared current context depends on BCI-0D;
- before BCI-0D, BCI product/research may display local typed contradictions, but
  no decision-visible shared contradiction edge or aggregate may reach Portfolio;
- the fence must bind exact eligible action and promotion receipt, not merely an
  all-false authority block on the source packet.

The durable workstream is the binding wave/dependency record.

---

# 3. Concurrency state now

| Lane | Current ruling |
|---|---|
| BCI architecture | Continue architecture-only PR; no runtime work |
| BioCatalyst | P0-C1 merged; entitled production acceptance only |
| Market Memory | Preserve M0A prospective proof boundary; no broad V2 restart |
| FIF | Hold #5809 for FIF-1R re-review; no FIF-2 |
| Defense | D0R merged; D1 remains independent and separately authorized |
| Earnings | Production recovery and E1 workspace merged; continue its own program |
| Seasonality | Freeze broad expansion; inventory and rebase under BCI |
| Neural Web/Portfolio authority | BCI-0D must precede shared decision-visible BCI contradictions |
| Prophet | Continue its existing fusion program; BCI enters only as future F4 shadow evidence |

---

# 4. Exact next action

Review and merge the architecture-only BCI-0A draft after any Chairman amendments.
Then execute:

```text
research/BIOPHARMA_CYCLE_INTELLIGENCE_BCI_0B_ARCHAEOLOGY_HANDOFF_2026-08-16.md
```

BCI-0B must stop without runtime implementation.
