> ARCHIVED 2026-07-06. This Codex handoff was adjudicated by Fable with an operator amendment the same day.
> Where this doc and research/FABLE_SUCCESSION_OPERATING_SYSTEM.md conflict, the Operating System doc wins.
> Key amendments: Opus IS a decision authority (Tier 0/1), the nondelegable list became Tier-2 (operator + adversarial panel, never parked forever), and a short invariants list stays never-approvable.

# Fable Succession Bench and Adjudication Pack Handoff

Prepared: 2026-07-07
Author: Codex
Status: research and freeze-spec only; do not build from this doc.
Audience: Fable, operator, Opus reviewers, Sonnet builders.

## Executive Decision

Neural Web has many mechanisms for building, reviewing, and logging work. It still has a brittle terminal dependency:

```text
High-leverage adjudication often means "ask Fable."
```

That is fine today and dangerous tomorrow. The repo needs a post-Fable adjudication bench: a packet format, delegation rubric, nondelegable list, and example verdict corpus that lets Opus + operator handle ordinary rulings while blocking decisions that should not be delegated.

This is not a proposal for autonomous approval. It is a way to prevent two bad outcomes:

1. work stalls forever because it says "needs Fable";
2. work overreaches because a future model pretends to be Fable.

## What This Doc Does For Fable

This handoff pre-builds the decision scaffolding:

- the existing human-gate laws,
- nondelegable decision classes,
- delegation matrix,
- adjudication packet schema,
- golden example list,
- first packets to backfill,
- Fable freeze questions.

Fable's job should be to edit and ratify the rubric, not reconstruct it from repo archaeology.

## Evidence Base

| Surface | Evidence |
|---|---|
| `CLAUDE.md` | Explicit role law: Fable plans/adjudicates/merges, Opus reviews, Sonnet builds. |
| `.claude/hooks/model_routing_guard.py` | Fable is not supposed to be spent on fan-outs. |
| `engine/neuralweb/constitution.py` | Article and authority ladder law. |
| `engine/research_factory/state.py` | Human-gate states require human actors; script actors cannot enter terminal judgment states. |
| `scripts/research_factory_decide.py` | Only path into `paper`, `deferred`, `rejected`, and `scoped_build`. |
| `research/research_factory/CHALLENGER_PROMPT.md` | Challenger output is advisory, not a transition authority. |
| `research/RF_CORTEX_BATCH_FOR_FABLE.md` | Even after Research Factory shipped, Cortex Batch B still needed Fable rulings. |
| `config/reflexes.yml` | Some activations require explicit Fable activation after evidence floors. |
| `engine/neuralweb/mastermind_context.py` | Mastermind context authority booleans are all false. |
| PR #1731 | Research Factory Batch B hardening still required Fable-style rulings. |

## Existing Human-Gate Law

Research Factory already encodes a partial model:

```yaml
script_actors:
  - script
  - codex
  - sonnet
human_actors:
  - fable
  - operator
human_gate_targets:
  - paper
  - deferred
  - rejected
  - scoped_build
  - retired
```

That is strong, but narrow. It governs Research Factory states, not all Neural Web architecture decisions.

The succession bench generalizes that idea across the repo.

## Core Principle

Separate:

```text
review competence
decision authority
implementation ownership
```

Opus can find a statistics defect. Sonnet can implement a frozen spec. The operator can decide a scoped review outcome. None of those automatically authorizes a new lobe, FDR family, public/private boundary, or scored-path behavior change.

## Delegation Matrix

### Sonnet Can Decide

Only inside a frozen spec:

- fixture shape,
- formatting,
- naming that does not alter public contract,
- fail-open mechanics,
- local helper decomposition,
- test scaffolding,
- doc/table cleanup,
- implementation details that do not touch authority, privacy, FDR, or owner boundaries.

### Opus Can Recommend

Opus can produce review findings and verdict recommendations:

- statistics defects,
- leakage or lookahead concerns,
- FDR/trial-budget defects,
- house-law violations,
- build feasibility risks,
- duplicate/case-law matches,
- privacy hazards,
- ambiguous ownership.

Opus recommendation is not a transition by itself.

### Operator Can Decide

Operator can decide when the packet is complete and no nondelegable boundary changes:

- `paper`,
- `defer`,
- `reject`,
- `scoped_build`,
- `retire`,
- "send to Opus review",
- "return for missing evidence",
- "merge doc-only clarification".

### Block / Nondelegable Without A Frozen Successor Rule

Recommended nondelegable list:

- new lobe charter,
- exception to the two-lobe cap,
- authority promotion above A2,
- any scored-path behavior change,
- any FDR family creation or split,
- qledger grading semantics,
- held-book/fill schema,
- public/private boundary changes,
- public write endpoint,
- Mastermind trading authority changes,
- cortex budget increase,
- LLM-originated score/rank/gate,
- Article 1/2/3 changes,
- trial-budget laundering,
- deletion of negative/null history.

## Adjudication Packet Schema

Doc-only freeze target:

```text
research/FABLE_SUCCESSION_OPERATING_SYSTEM.md
config/adjudication_rubrics.yml
data/neuralweb/adjudication_queue.json
research/adjudication_examples/*.md
scripts/build_adjudication_packet.py
scripts/check_adjudication_packet.py
```

Do not build these from this handoff; this is the contract.

Suggested packet:

```yaml
schema: neuralweb.adjudication_packet.v1
packet_id: adj-2026-07-07-example
created_at: ISO-UTC
created_by: codex|sonnet|operator|script
request:
  title: short title
  requested_decision: paper|defer|reject|scoped_build|charter|authority_change|privacy_change
  source_doc: research/...
  source_pr: 1234
scope:
  owner_program: neural-web
  proposed_classification: lobe|rail|wave|study|context|no_build
  touched_artifacts:
    - data/neuralweb/example.json
  touched_paths:
    - engine/neuralweb/example.py
case_law:
  ruling_hits:
    - RUL-C1
    - RUL-C9
  duplicate_risk: low|medium|high
  deferred_or_killed_hits: []
authority:
  current_ceiling: A1_explain
  requested_ceiling: A1_explain
  article2_surfaces_touched: []
  nondelegable: false
privacy:
  privacy_class: public_research|public_context|host_private|mastermind_private
  public_paths_touched: []
  private_fields: []
statistics:
  fdr_family: null
  trial_budget_change: false
  evidence_floor_met: false
  outcome_data_seen: false
clocks:
  come_back_on: null
  due_status: not_clocked|accruing|due|overdue
build_collision:
  open_prs_touching_paths: []
  owner_conflicts: []
review:
  required_lenses:
    - house_law
    - statistics
    - build_feasibility
  opus_findings: []
allowed_outcomes:
  - paper
  - defer
  - reject
blocked_outcomes:
  - authority_promotion
  - new_lobe_charter
operator_decision:
  decision: null
  actor_ref: null
  rationale: null
```

## Required Review Lenses

Every consequential packet should declare its lenses:

| Lens | Questions |
|---|---|
| Case law | Has this been ruled on, killed, deferred, or scoped elsewhere? |
| Authority | Does it affect Article-2, A3/A4/A5/A6, or LLM authority? |
| Privacy | Can any field leak held-book, fill, private note, path, key, or account behavior? |
| Statistics | Is there a frozen family, declared budget, no lookahead, and printed null branch? |
| Build feasibility | Are paths, writers, dependencies, and test surfaces realistic? |
| Collision | Is an active PR already building this? |
| Ownership | Which program owns it? Is it crossing QI/Mastermind/Oracle/Neural Web boundaries? |
| Ops budget | Does it add render/nightly time or off-path compute? |

## Golden Examples To Backfill

These are the examples Fable should freeze as training cases for future packets.

| Example | Why It Matters |
|---|---|
| Research Factory Batch A A15 paper + duplicate kills (#1629) | Shows paper vs rejected decisions and challenger role. |
| Three-Lobes zero-charter adjudication (#1673) | Shows how attractive lobe ideas decompose into rails/waves/studies. |
| Final-3 reshape/kill/defer rulings (#1695) | Shows partial adoption, killed overreach, and deferred same-tape conditioning. |
| R-ORTH rail-not-lobe ruling (#1739/#1748/#1768) | Shows taxonomy discipline. |
| Research Factory Cortex Batch B (#1731) | Shows why factory infrastructure still needs Fable-style judgment. |
| Factor dark scaffold activation floor (#1598 family) | Shows explicit activation after event floors. |
| Mastermind bridge dark-ship/context-only (#1567/#1680) | Shows cross-repo context with no authority. |
| Cycle Pattern truth/null status (#1773) | Shows nulls and statuses as active memory. |
| L6-P0 macro transmission pass/failed axes (#1693) | Shows "pass reopens charter question" without auto-chartering. |
| Operator exposure / grading (#1702/#1669) | Shows operator-action evidence accrual without promotion. |

## First 10 Packets To Generate

If this bench existed today, generate these first:

1. Held-book/fill feedback reverse bridge.
2. Ruling graph v1 seed.
3. Active build collision map.
4. Global evidence clock.
5. Private/public boundary audit.
6. Macro context rail #1635, because it is wide and still open.
7. Options signed tape #1763, because it touches data entitlement and future flow claims.
8. Entry-stack decline geometry #1777/#1778 follow-up, because it moved during this pass.
9. Research Factory LLM auth hardening follow-up, because #1731 noted operational LLM auth issues.
10. Post-Fable "new lobe charter" request template, to make the cap non-accidental.

## Fable Freeze Decisions

Fable should decide:

1. Is operator allowed to replace Fable for ordinary `paper/defer/reject/scoped_build` decisions?
2. Which decision classes are nondelegable?
3. Can Opus ever author final decisions, or only findings?
4. What fields make an adjudication packet complete?
5. What is the minimum evidence for a packet that touches authority?
6. What is the minimum evidence for a packet that touches private data?
7. What packet failures are hard blockers?
8. Which golden examples are canonical?
9. What should happen when an item is nondelegable after Fable is gone: park forever, operator override, or external review?

## Non-Goals

- No autonomous approval.
- No "model confidence" based decision.
- No LLM changing gates.
- No codegen lane.
- No behavior change.
- No bypass of Research Factory state law.
- No replacement of Fable's current rulings.

## Likely Objections And Answers

### "This will slow everything down."

The current alternative is slower: every major decision burns Fable-style reasoning ad hoc. The packet makes evidence reusable.

### "The operator can already decide."

Yes. The packet protects the operator from hidden authority/FDR/privacy implications and makes decisions auditable.

### "Opus can judge this."

Opus can review, but review is not authority. Keep that distinction.

### "Some decisions will remain blocked."

Correct. That is safer than laundering a nondelegable Fable decision into an ordinary build task.

## V1 Success Test

A future session says:

```text
Promote cycle-pattern turn hazard into a board rank conditioner.
```

The packet should return:

```text
Nondelegable: authority promotion / Article-2 ranked-output path.
Required case law: CPI truth schema, cycle-pattern authority guard, constitution A2/A3.
Allowed outcomes today: defer, request Opus stats review, or define shadow metric.
Blocked outcome: direct board-rank conditioning.
```

That is the succession bench doing its job.
