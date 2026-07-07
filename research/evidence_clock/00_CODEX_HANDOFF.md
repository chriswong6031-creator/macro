# Global Evidence Clock Autopilot Handoff

Prepared: 2026-07-07
Author: Codex
Status: research and freeze-spec only; do not build from this doc.
Audience: Fable, operator, Research Factory, admin/HQ implementers.

## Executive Decision

The repo has many clocks. It does not have one review clock.

Examples:

- qledger `check_by`,
- Research Factory `come_back_on`,
- experiments registry `come_back_on`,
- synapse freshness SLAs,
- governance authority lapses,
- trial-ledger FDR batches,
- long-hold clocks,
- cortex due hypotheses,
- cycle-pattern review dates,
- Mastermind context freshness.

Each is locally reasonable. Together they create an operator/Fable burden: someone must remember what becomes decisionable this week.

The Global Evidence Clock should not promote, reject, or mutate anything. It should say:

```text
What is due?
What is stale?
What is still underpowered?
What exact evidence packet should be reviewed next?
```

## What This Doc Does For Fable

This handoff:

- inventories clock sources,
- reports a current data snapshot,
- proposes a unifying schema,
- defines allowed non-mutating behavior,
- gives sample queue rows,
- lists Fable freeze decisions.

## Current Clock Evidence

Local structured snapshot from this checkout:

| Source | Current Finding |
|---|---|
| `data/experiments/registry_seed.json` | 137 rows; 128 rows with `come_back_on`; statuses include 77 accruing, 16 registered, 10 proven, 5 collecting, 4 closed_no_go. |
| `data/research_factory/review/queue.json` | Present, 0 candidates, `authority: display_only`. |
| `data/neuralweb/research_queue.json` | Missing in this checkout, despite code/charters referencing it. |
| `data/trial_ledger.jsonl` | 975 lines; multiple families and declared budgets. |
| `data/neuralweb/governance.jsonl` | 20 lines; authority/article/research-factory governance events. |
| `data/neuralweb/mastermind_context.json` | Present, `as_of: 2026-07-02`; generated 2026-07-06; context-only; size under cap. |
| `data/governance/claim_accountability.json` | 9,069 claims, 2,815 grades, about 1.6% falsifier coverage. |
| `data/reflexivity/n_eff_history.json` | One history row; note says substrate for a later verdict window. |
| `data/rule_experiments/registry.jsonl` | 20 lines; rule experiment states and reports. |

This is enough to justify a clock unifier.

## Existing Clock Sources

### QLedger

Owns claim maturity via `check_by`, horizon, grade state, and falsifiers.

Clock issue:

- claim maturity is not surfaced as a unified "review due" queue;
- many claims lack falsifiers, so maturity does not always mean decision-ready.

### Research Factory

Owns candidate lifecycle, including `paper`, `deferred`, `awaiting_data`, `promote_eligible`, and human-gate states.

Clock issue:

- RF-9 says no bespoke clocks; candidates should route through experiments registry;
- current review queue can be empty even while many external clocks exist.

### Experiments Registry

`data/experiments/registry_seed.json` is the richest current clock inventory.

Clock issue:

- it is broad and useful, but not normalized into Fable-ready review packets;
- it mixes track records, studies, data collections, validations, and parked research.

### Trial Ledger

Owns multiple-testing memory and declared budgets.

Clock issue:

- budget maturity is family-local;
- there is no dashboard that says which family has enough evidence to review.

### Synapse / Signal Bus

Owns freshness and consumer topology.

Clock issue:

- freshness is an artifact clock, not a decision clock;
- stale context artifacts can silently reduce review value unless promoted into a due/stale queue.

### Governance

Owns authority events and lapses.

Clock issue:

- governance history is append-only but not summarized into upcoming lapse/review items.

### Long-Hold Clocks

`entry_clock` and `thesis_clock` annotate per-ticker state.

Clock issue:

- useful display context, not a global Fable queue.

## Proposed Artifact Contract

Doc-only freeze target:

```text
config/evidence_clock.yml
data/neuralweb/evidence_clock.json
site/neuralwebdata/evidence_clock.json
docs/EVIDENCE_CLOCK_AUTOPILOT.md
scripts/build_evidence_clock.py
scripts/check_evidence_clock.py
```

Do not build these from this handoff.

## Schema V1

```yaml
schema: neuralweb.evidence_clock.v1
clock_id: experiments:index-leadership
source_system: experiments|qledger|research_factory|trial_ledger|synapse|governance|long_hold|cortex|mastermind_context
subject_id: index-leadership
subject_type: track_record|claim|candidate|artifact|family|authority|thesis
owner_program: engine-fix
clock_type: check_by|come_back_on|freshness_sla|fdr_batch_due|lapse_at|human_review_due|thesis_clock|paper_decay
due_at: "2026-07-29"
as_of: "2026-07-07"
age_hours: null
sla_hours: null
state: accruing|due|overdue|stale|missing|blocked|promotion_eligible|human_review|not_ready
readiness:
  n: 37
  min_n: 40
  horizons_matured:
    - 5d
  falsifier_status: thin
  trial_family: null
  budget_used: null
  blocking_reason: "needs n_matured>=40"
allowed_actions:
  - inspect
  - print_gap
forbidden_actions:
  - promote
  - mutate_source_state
  - score
authority: display_only
evidence_refs:
  - data/experiments/registry_seed.json
packet_ref: null
```

## State Vocabulary

| State | Meaning |
|---|---|
| `accruing` | Clock exists, not decision-ready. |
| `due` | Clock date has arrived and minimum packet can be built. |
| `overdue` | Due date passed without packet/review. |
| `stale` | Artifact freshness SLA breached. |
| `missing` | Expected artifact absent. |
| `blocked` | Cannot progress without data/labels/grader. |
| `promotion_eligible` | Source system says it may be reviewed; no auto-promotion. |
| `human_review` | Needs operator/Opus/Fable-equivalent packet. |
| `not_ready` | Date may have arrived, but evidence floor not met. |

## Allowed V1 Behavior

The autopilot may:

- aggregate clocks,
- sort due/overdue/stale items,
- generate review packet stubs,
- print missing evidence,
- route attention,
- show exact commands to regenerate source artifacts.

It may not:

- mutate RF state,
- promote,
- retire,
- change trial budgets,
- edit qledger claims,
- alter synapse,
- write authority events,
- rank stocks,
- size positions,
- call Mastermind.

## Sample Queue Rows

### Experiments Row

```yaml
clock_id: experiments:hub-track-record
source_system: experiments
subject_id: hub-track-record
clock_type: come_back_on
due_at: 2026-07-20
state: accruing
readiness:
  blocking_reason: "durable 5d/10d verdict not yet mature"
allowed_actions:
  - inspect
  - print_gap
```

### Research Factory Paper Candidate

```yaml
clock_id: rf:A15_WASHOUT_OPP_OUT_2NODE
source_system: research_factory
subject_id: rf-20260706-adopt-a15_washout_opp_out_2node
clock_type: paper_decay
state: accruing
allowed_actions:
  - inspect
  - route_human_review_when_due
authority: display_only
```

### Synapse Freshness

```yaml
clock_id: synapse:neuralweb-mastermind-context
source_system: synapse
subject_id: data/neuralweb/mastermind_context.json
clock_type: freshness_sla
as_of: 2026-07-02
state: stale_or_aging
allowed_actions:
  - print_gap
  - regenerate_packet
forbidden_actions:
  - infer_current_context
```

### Claim Accountability

```yaml
clock_id: claim_accountability:falsifier_coverage
source_system: qledger
subject_id: global_claims
clock_type: evidence_floor
state: blocked
readiness:
  n_claims: 9069
  n_with_falsifier: 146
  blocking_reason: "falsifier coverage about 1.6%; not a promotion-grade substrate"
allowed_actions:
  - print_gap
```

### Cortex FDR Batch

```yaml
clock_id: cortex:fdr_batch_2026_10
source_system: cortex
subject_id: cortex_kernel_batch
clock_type: fdr_batch_due
due_at: 2026-10-01
state: accruing
allowed_actions:
  - inspect_when_due
forbidden_actions:
  - auto_promote
```

## Precedence Rules

When clocks disagree, recommended precedence:

1. Governance/ruling graph.
2. Research Factory transition state.
3. QLedger maturity / claim state.
4. Trial Ledger budget state.
5. Synapse freshness.
6. Experiments registry.
7. Display clocks.

Example: if experiments says a row is due but qledger says falsifier coverage is absent, state becomes `not_ready` or `blocked`, not `due`.

## Review Packet Integration

Each due item should produce an adjudication packet stub:

```yaml
packet_id: adj-from-clock-...
clock_id: experiments:...
reason_due: come_back_on elapsed
source_evidence:
  - path
missing_evidence:
  - path_or_floor
allowed_decisions:
  - inspect
  - defer
  - reject
  - paper
blocked_decisions:
  - promote
  - authority_change
```

## Fable Freeze Decisions

Fable should decide:

1. What clock sources are in v1?
2. What is the state vocabulary?
3. Which source wins on conflict?
4. Can the autopilot write only `data/neuralweb/evidence_clock.json`, or also packet stubs?
5. Which clocks are private and must not appear in public site output?
6. What makes a due item decision-ready vs merely date-due?
7. How should stale artifacts be displayed: warning, blocked, or absent?
8. Can operator mark a clock "reviewed" without mutating the source system?

## Non-Goals

- No promotion.
- No retirement.
- No mutation of source ledgers.
- No new signal.
- No new lobe.
- No FDR decision.
- No qledger edit.
- No Mastermind action.

## Likely Objections And Answers

### "This duplicates Research Factory monitor."

RF monitor owns RF state. Global Evidence Clock watches all systems and routes attention.

### "This duplicates the admin Experiments tab."

Experiments registry is one source. The clock unifier also reads qledger, synapse, governance, trial ledger, cortex, and private future clocks.

### "This creates authority drift."

Only if it mutates. V1 must be read-only and display-only.

### "The clock will be noisy."

Correct. That is why state vocabulary needs `not_ready`, `blocked`, and `print_gap`, not only `due`.

## V1 Success Test

On any morning, the operator can ask:

```text
What needs Fable-style review today?
```

The system returns:

```text
3 due, 12 accruing, 2 stale, 5 blocked.
No authority promotions.
Top due item: X, evidence packet path Y, missing evidence Z, allowed decisions A/B/C.
```

That replaces memory and scrolling with a review queue.
