# Cycle Pattern Truth Registry — Nulls and Statuses as Active Memory

**Source:** PR #1773. Primary doc: `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

The Cycle Pattern Intelligence program needed a truth-registry layer: a durable memory of what the house knows (and does not know) about cycle patterns, distinct from the candidate lifecycle managed by the Research Factory. The question was how to structure `truths.jsonl` so that null results and failed candidates have the same standing as positive findings, and duplicates are actively blocked.

## What was decided (the holding)

- **15 seed truths committed:** the truth registry (`data/cycle_pattern/truths.jsonl`) is initialized with 15 seed entries drawn from existing ratified verdict docs (W4.2 keystone, W4.2 binding calibration, W4.6, W5.1, etc.). These represent the house's current evidence state — including nulls and deferrals — as of 2026-07-06.
- **Append-only versioned:** the truth registry is append-only. No truth entry is ever deleted. Superseded entries gain a `superseded_by` field pointing to the newer entry's id; the old entry remains readable as history. This is a direct instantiation of RUL-SUCC-4 invariant 3 (deletion of null history is never-approvable).
- **`promoted_null` blocks duplicates:** a truth entry with `status='promoted_null'` is semantically equivalent to a positive finding for the purpose of blocking future candidates. When the factory's dedup context includes `truths.jsonl`, a candidate whose mechanism overlaps a `promoted_null` entry is flagged as a duplicate — exactly as if the basin representative existed with a positive status. Nulls are first-class memory.
- **Anti-mining law carry-forward:** the same trial-budget and anti-forking-paths laws that govern the candidate pipeline apply to the truth layer. A null truth does not restart the budget clock for a restated version of the same question; the original trial budget is consumed.
- **Truth layer is downstream of human_review/paper decisions:** `truths.jsonl` is written only from human_review or paper state transitions and existing ratified verdict docs. It is NOT a competing pipeline with the factory's candidate lifecycle — the factory governs candidate states; the truth registry governs adjudicated knowledge (the output of that pipeline).
- **Accrual hardening shipped first (Phase 0 of CPI):** before any discovery code, the measurement pipeline (`scripts/build_measurement.py`) is wired into the nightly workflow. Unaccrued live forward logs are training data lost forever; Phase 0 fixes the accrual gap.
- **`promoted_null` semantics explicit:** in the factory, `numeric_rejected`/`rejected` are candidate states, not memory. In the truth layer, a null result is promoted to `promoted_null` status — permanent standing memory that blocks duplicate candidates via the dedup context.
- **Covariate-expansion first (Fable amendment):** the discovery program priority is covariate-expansion trials (FT-families: breadth, credit/curve, liquidity, cross-entity sync, Oracle rotation context, China policy stance, vintage-true macro) before lattice/motif mining. Mining existing columns harder mostly rediscovers already-known nulls.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Create truth registry (append-only, nulls first-class) | new artifact, new governance layer | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| 15 seed truths (ratified from existing verdicts) | doc-only migration of existing rulings | **T0** (ROUTINE) | Opus alone |
| `promoted_null` blocks duplicates (dedup rule) | new dedup rule within factory | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| Anti-mining law carry-forward to truth layer | program law extension | **T0** (ROUTINE) | Opus alone |
| Accrual hardening (nightly wiring of measurement) | ops wiring, no authority change | **T0** (ROUTINE) | Ops; no packet required |
| Covariate-expansion priority (Fable amendment) | program strategy amendment | **T1** (CONSEQUENTIAL) | Opus + completed packet |

Creating the truth registry as a new append-only artifact with dedup authority is T1. The seed truths are T0 (they migrate existing ratified verdicts with no new adjudication). The `promoted_null` dedup rule is T1 because it changes what counts as a duplicate in the factory pipeline — a consequential cross-system rule.

## Lenses that did the work

- **Case law:** the anti-mining law (trial budgets, printed candidate counts, null baselines, date-blocked holdouts, era splits, dead-stays-dead) already existed in the cycle intelligence program; this case extends it explicitly to the truth layer. A null truth does not reset the clock.
- **Statistics:** the distinction between `promoted_null` blocking duplicates and the factory's `numeric_rejected` state being a candidate terminal state (not memory) is the key statistical architecture choice. Without the `promoted_null` construct, the same null question could be re-registered indefinitely, each time claiming a fresh budget.
- **Authority:** truth entries carry `authority_status` (descriptive/display-only at birth; promotable only via a separate registered gate). The truth registry does not grant authority — it records the evidence state that authority decisions must read.
- **Ops budget:** accrual hardening (wiring `build_measurement.py` into nightly) has zero signal cost but permanently addresses the data leakage of un-stamped live log dates. Every unstamped day is training data lost forever.

## Citable holding

A truth registry that is append-only, version-stamped, and treats `promoted_null` status as equal in standing to a positive finding — actively blocking duplicate registration via the factory's dedup context — is the correct institutional architecture for preventing re-belief of buried nulls; deletion of negative or null history is a never-approvable invariant (RUL-SUCC-4).

## Ruling IDs

RUL-SUCC-4 (invariant 3: deletion of null history never-approvable); anti-mining law (CPI program); `promoted_null` dedup rule; accrual-hardening doctrine
