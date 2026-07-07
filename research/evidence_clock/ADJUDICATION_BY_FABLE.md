# Global Evidence Clock — Adjudication by Fable

**Date:** 2026-07-06
**Status:** RATIFIED — build authorized (v1 display-only)
**Reference:** `research/evidence_clock/00_CODEX_HANDOFF.md`

---

## Data Snapshot Verification

Before ratifying the build, the data underlying the Codex handoff was independently re-verified
against the live repo state:

| Source | Handoff claim | Verified count |
|---|---|---|
| `data/experiments/registry_seed.json` | 137 entries, 128 with `come_back_on` | **137 / 128** confirmed |
| `data/trial_ledger.jsonl` | 975 trial lines | **976 rows** (975 trials + file structure; immaterial) |
| `data/qledger/claims.jsonl` | 9,069 claims / 2,815 grades / 1.6% falsifier coverage | **9,069 / 1.6%** confirmed |
| `data/neuralweb/governance.jsonl` | 19 rows (handoff said 20) | **19 rows** — one-day drift, immaterial |
| `data/rule_experiments/registry.jsonl` | 19 rows | **19 rows** confirmed |
| `data/neuralweb/research_queue.json` | Missing while referenced | **Confirmed missing** — `engine/neuralweb/research_queue.py` and `scripts/research_factory_ingest.py` both reference it |

RF-9 scope confirmed via `research/research_factory/OPERATING_RUNBOOK.md` ("factory-originated
clocks only"). A read-only aggregator that surfaces RF-9 conformance findings is legal; the
aggregator reads `come_back_on` from the experiments seed and never keeps a parallel store.

---

## Rulings

### EC-R1 (Sources — what the v1 clock aggregates)

**Included sources:**

1. Experiments registry (one row per entry with `come_back_on`; plus one rollup blocked row for the 9 entries missing it — RF-9 nonconformance)
2. Research factory (queue: human_review row when candidates pending; RF-9 conformance: blocked rows for candidates with no experiments-seed entry)
3. qledger — rollups only: one row per desk (n_open, n_past_check_by) and one global falsifier-floor blocked row. Per-claim rows are excluded; 9,069 per-claim rows would destroy the queue's navigational purpose.
4. Trial ledger — family rollups (top 15 by trial count, remainder as one "other" row)
5. Freshness: `data/neuralweb/health.json` when present (reuses already-computed lobe staleness; never recomputes 211 synapse SLAs); `data/neuralweb/mastermind_context.json` (as_of + freshness chips)
6. Governance: `data/neuralweb/governance.jsonl` + probation files — rows only when `lapses_at` non-null
7. Cortex machine registry: `data/neuralweb/machine_registry.jsonl` — rows for `status==registered` entries
8. Rule experiments: `data/rule_experiments/registry.jsonl` — rows per exp_id whose latest status is `registered` (never executed)
9. Cycle pattern: `data/cycle_pattern/truths.jsonl` — rows per truth with `next_review_due`
10. Species: `data/species/registry.json` — rows when `gating.come_back_on` non-null
11. Declared clocks: `config/evidence_clock.yml` `declared_clocks` (masterplan come-backs without a ledger home)
12. Expected artifacts: `data/neuralweb/research_queue.json` — missing → `missing` state row

**Excluded from v1:**

- Per-claim qledger rows (flood risk, no navigational value)
- Per-artifact freshness sweep of all 211 synapses (reuse health.json instead)
- Long-hold per-ticker `entry_clock`/`thesis_clock` (display context, would flood; revisit v2)

### EC-R2 (Vocabulary — the 9-state enum)

The Codex 9-state vocabulary is adopted verbatim:

`accruing | due | overdue | stale | missing | blocked | promotion_eligible | human_review | not_ready`

States are assigned by a deterministic function. `date_state` records the pre-demotion state
for audit. LLMs are never in the assignment loop.

### EC-R3 (Precedence — state demotion order)

Codex precedence order adopted: **governance > RF transition > qledger maturity > trial budget >
freshness > experiments > display clocks.** Date-due never survives a higher-precedence blocker.
All demotions carry a `blocking_reason`. Concretely implemented:

- Experiments row whose subject matches an RF candidate in `awaiting_data`/`blocked` → state `blocked`
- Any row whose `evidence_refs` artifact is stale per `health.json` → readiness note added ("stale_input: \<path\>"); state is NOT changed for freshness alone

### EC-R4 (Writes — exactly one output artifact)

v1 writes exactly ONE artifact: `data/neuralweb/evidence_clock.json`. Packet stubs are inline
on due/overdue rows (capped at the top 10 by sort order). No separate packet files — revisit
in v2 if operators request them. The reviews ledger (`data/neuralweb/evidence_clock_reviews.jsonl`)
is operator-written; the builder reads it but never writes it.

### EC-R5 (Privacy — surfaces)

`data/neuralweb/evidence_clock.json` does NOT get a `site/` copy. The site ships publicly via
GitHub Pages; this artifact contains operational detail that should stay behind the authed admin
console. Surfaces: authed admin console + counts-only block in the daily brief. Public redaction
layer revisited in v2.

### EC-R6 (Decision-ready — evidence floors)

`due` = date arrived AND evidence_refs exist on disk AND declared floors met. Unmet floors demote
to `not_ready` with a printed `blocking_reason`. Unknown floors are honest (`readiness.floor="undeclared"`)
and leave the row as `due` — never fabricated to demote. Floor demotion is EC-R6.

### EC-R7 (Stale display — first-class warning)

`stale` is a first-class warning state. It never hides a row and never blocks other rows. Every
stale/missing row carries a `regenerate_cmd` resolved from `config/synapse.yml` `producer` when
the artifact maps to a registered synapse.

### EC-R8 (Operator ack — attention snooze)

Append-only `data/neuralweb/evidence_clock_reviews.jsonl`: rows `{clock_id, reviewed_on, note,
outcome}`. An acknowledgment within `snooze_days` (7d default) sets `acknowledged=true` and
excludes the row from `top_due`/`morning_line` due-count. It is an attention snooze, never a
state mutation. Real state changes must flow through the source system (e.g., RF decide updating
`come_back_on`).

---

## Improvements Over the Codex Handoff

- **Synapse producer reuse:** `regenerate_cmd` is resolved from `config/synapse.yml producer`
  field when the artifact is registered, eliminating a manual maintenance surface.
- **Rollup law formalized:** any source with >50 rows is never emitted per-item; rollups are
  the only legal representation.
- **RF-9 conformance surfaced as a byproduct:** experiments without `come_back_on` emit a
  blocked rollup row; this gives the clock a self-auditing property for factory hygiene.
- **`morning_line` in summary:** the literal V1 success test from the handoff is implemented
  as a template-filled summary field.
- **Deterministic / fail-soft / no-LLM:** all three are enforced by construction. Any single-source
  failure emits a `gaps` note and continues; builder always exits 0.
- **`declared_clocks` stopgap with migration note:** the config clearly labels this as a temporary
  home for masterplan come-backs; RF-9 entry in the experiments seed is the preferred home.

---

## Non-Goals (verbatim from the Codex handoff)

- Does not promote any experiment, candidate, or claim
- Does not retire or change the status of any source record
- Does not originate any signal, score, or rank
- Does not replace or duplicate any source system
- Does not run any LLM
- Does not write to any source ledger (`governance.jsonl`, `claims.jsonl`, `registry_seed.json`, etc.)

---

## File Manifest (this PR)

| File | Purpose |
|---|---|
| `research/evidence_clock/00_CODEX_HANDOFF.md` | Verbatim Fable handoff document |
| `research/evidence_clock/ADJUDICATION_BY_FABLE.md` | This file — rulings and ratification |
| `config/evidence_clock.yml` | Source configuration, declared clocks, grace/snooze params |
| `engine/neuralweb/evidence_clock.py` | Core logic: adapters, state machine, precedence, rollups |
| `scripts/build_evidence_clock.py` | CLI wrapper: atomic write, fail-soft, always exit 0 |
| `scripts/check_evidence_clock.py` | CI-grade checker with `--selftest` |
| `docs/EVIDENCE_CLOCK_AUTOPILOT.md` | Operator guide |
| `config/synapse.yml` | Registered `evidence-clock` and `evidence-clock-reviews` |
| `docs/SIGNAL_BUS.md` | Regenerated from synapse.yml (byte-identical with generator) |
| `.github/workflows/daily.yml` | Added `build_evidence_clock` step in engine job |
| `config/dag.yml` | Declared `build_evidence_clock` step |
| `tests/test_evidence_clock.py` | pytest suite covering 8 test groups |
| `tests/fixtures/evidence_clock/` | Small fixtures for deterministic tests |
| `data/neuralweb/evidence_clock.json` | First generated artifact (committed as derived view) |
