# Half-A K-chain and calibration-gate docket — eight rows that no engineering may open

**Date:** 2026-09-06 · **Lane:** F04 ontology/transmission (+F05 event-impact spillover)
**Packet:** B-A-F04-K1 (wave A-spare, Meta-CEO B) · **Kind:** records only
**Source ledger:** `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
**Decision record:** `agentos/decisions/DEC-HALF-A-K-CHAIN-GATED-ROWS-ARE-DOCKETED-NOT-BUILT-2026-09-06.md`

## What this says, in plain words

Eight rows of the Half-A closure ledger are waiting on someone else. Nothing here has been
built, and this document builds nothing. For each row it records one thing: which gate is
shut, who or what can open it, the highest claim that row is ever allowed to make, and the
one small thing we would ship on the day it opens. If you came here to find out whether a
row is done, the answer for all eight is: no, and here is exactly what it is waiting for.

This records the STATE of each gate, not its OUTCOME. If a gate opens tomorrow this page is
still correct — the row's own "Opener" line names the event that would open it.

## MO-PAID-016 — TXI hop context composed with GMI edges into a rendered causal explanation

- **Disposition:** DOCKETED
- **Gate:** `K3-D`
- **Opener:** Sol acceptance of the K3-D economic-propagation commission. PR #6514 is OPEN
  HOLD-FOR-SOL (F00B crosswalk line 165), while WS-ALPHA-INTELLIGENCE-INTEGRATION.md:205
  records K3-D as still NOT_BUILT and requiring its own commission. Either an acceptance of
  #6514 or a separately commissioned K3-D wave opens this row. This packet schedules neither.
- **Authority ceiling (verbatim from ledger):** `research_display_only; no calibrated causal certainty`
- **First bounded slice when it opens:** One read-only research-tier view that composes a
  single TXI hop chain with the GMI edges for the same theme node and renders a shock ->
  theme -> cross-asset explanation, every claim carried by a K1 EvidenceBlock. Display only:
  no calibrated causal certainty, no rank, gate, size or trade semantics.
- **Ledger evidence:** row `MO-PAID-016` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=UPGRADE_EXISTING_OWNER, capability_state_c2=PARTIAL, real_consumer=NONE product-tier (internal: intelligence_workspace adapters)

The TXI producer is `engine/transmission_chains.py:109`
(`class ChainSchemaError(ValueError)`), which reds CI at load when a chain YAML violates the
TXI-R1 schema. The GMI edge side keeps a keep-first `(edge_id, belief_time)` correction
behavior — `engine/theme_graph/store.py:114-117` — and its current view is the max-belief_time
row per edge_id (`store.py:1-8`). No product-tier consumer exists for this join today.

## MO-PAID-018 — Causal Impact workflow consumer (F05)

- **Disposition:** DOCKETED
- **Gate:** `K3-D`
- **Opener:** Sol acceptance of the K3-D economic-propagation commission. PR #6514 is OPEN
  HOLD-FOR-SOL (F00B crosswalk line 165), while WS-ALPHA-INTELLIGENCE-INTEGRATION.md:205
  records K3-D as still NOT_BUILT and requiring its own commission. Either an acceptance of
  #6514 or a separately commissioned K3-D wave opens this row. This packet schedules neither.
- **Authority ceiling (verbatim from ledger):** `research_only; LLMs summarize cited records only`
- **First bounded slice when it opens:** One Causal Impact workflow consumer that emits only
  claims backed by an accepted K3-D or Eval-OS model, each claim carrying its K1 EvidenceRef.
  Any language model in that path summarizes cited records and originates no signal, score or
  escalation.
- **Ledger evidence:** row `MO-PAID-018` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=UPGRADE_EXISTING_OWNER, capability_state_c2=SPEC_ONLY, real_consumer=NONE

capability_state_c2 = SPEC_ONLY on this row; producer NONE, consumer NONE. The gate and
opener are identical to MO-PAID-016 because both wait on the same K3-D economic-propagation
acceptance named at WS-ALPHA-INTELLIGENCE-INTEGRATION.md:205.

## MO-PAID-024 — competitor arbitrage scanner

- **Disposition:** DOCKETED
- **Gate:** `K2-C + K3-D + K5`
- **Opener:** Sol acceptance of the K2-C institutional adapter pilot (#6533 is MERGED but NOT
  Sol-accepted, F00B crosswalk line 166; post-merge repair is the explicit adjudication
  point), then Sol acceptance of K3-D, then a separately commissioned K5 plus Eval-OS
  calibrated promotion.
- **Authority ceiling (verbatim from ledger):** `research_only; competitor direction/confidence/expected-impact/priced% semantics NOT inheritable absent calibrated promotion proof (Sol amendment)`
- **First bounded slice when it opens:** Nothing is scoped until lawful K5 promotion. At that
  point the first slice is one research-only context panel over the existing dislocation
  evidence scoping, with no direction, confidence, expected-impact or priced-percentage field
  and no arbitrage authority of any kind.
- **Ledger evidence:** row `MO-PAID-024` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=CONTEXT_ONLY, capability_state_c2=NOT_BUILT, real_consumer=NONE

The ledger names `engine/dislocation.py` as adjacent. `engine/dislocation.py:143
def evidence_scope(trigger_keys, dd_pct=None) -> dict` is a pure evidence-coverage helper
returning `coverage in covered|partial|uncovered|none` — it is not an arbitrage scanner and
inherits no scanner authority.

## MO-PAID-033 — ranked-implications surface (F05)

- **Disposition:** DOCKETED
- **Gate:** `K2-C + K3-D + K5`
- **Opener:** Sol acceptance of the K2-C adapter pilot (#6533 merged, not Sol-accepted)
  followed by K3-D acceptance; the calibrated fields additionally require a separately
  commissioned K5 plus Eval-OS promotion (WS-ALPHA-INTELLIGENCE-INTEGRATION.md:213, 234-236).
- **Authority ceiling (verbatim from ledger):** `research_priority_only; competitor calibrated fields excluded absent promotion`
- **First bounded slice when it opens:** One implications surface whose ordering is plain
  research-priority only, sequenced behind the acceptances above, with every calibrated field
  absent and its absence stated on the surface in plain words.
- **Ledger evidence:** row `MO-PAID-033` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=UPGRADE_EXISTING_OWNER, capability_state_c2=NOT_BUILT, real_consumer=NONE

`WS-ALPHA-INTELLIGENCE-INTEGRATION.md:213` records K5 as `status: todo`, `depends_on: [k2,
k3]`, and `:234-236` forbids starting K5 until both K2 and K3 are complete.

## MO-PAID-042 — K5-derived opportunity projection onto the Live Entry Radar

- **Disposition:** DOCKETED
- **Gate:** `K5`
- **Opener:** A separately commissioned K5 OpportunityCase / Prophet-integration wave.
  WS-ALPHA-INTELLIGENCE-INTEGRATION.md:213 records K5 as todo, depends_on [k2, k3], and
  :234-236 forbids starting it until BOTH K2 and K3 are complete.
- **Authority ceiling (verbatim from ledger):** `research_priority_only; competitor direction/confidence/expected-impact/priced% semantics NOT inheritable absent calibrated promotion proof (Sol amendment)`
- **First bounded slice when it opens:** Project one K5-derived opportunity field onto the
  existing frozen Radar record and render it in one reading consumer. This slice needs a
  second, independent unblock: the Radar spool has no reader today.
- **Ledger evidence:** row `MO-PAID-042` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=PROJECTION_ONLY, capability_state_c2=PARTIAL, real_consumer=NONE rendered (LER spool_dir=null per DSC:LER-W5-PROSPECTIVE-CONSUMER-DISCONNECTED)

This row has two independent blockers, not one. The producer WS-LIVE-ENTRY-RADAR is frozen
at #6599 (F00B crosswalk line 170), and there is no rendered consumer — `spool_dir` is null,
`observed_spool_events=0`, `state=WAITING_FOR_LIVE_SOURCE` per
`DSC:LER-W5-PROSPECTIVE-CONSUMER-DISCONNECTED`. K5 opening does not by itself open this row.

## MO-PAID-043 — gap monitor comparing TXI hop coverage against GMI edge state

- **Disposition:** DOCKETED
- **Gate:** `D2C→W3C fold`
- **Opener:** Execution of the D2C -> D2E -> W3B -> W3C fold sequence. The ledger records
  that sequence as ruled NOT executed while D2C is unplaced (no receiver, ACK, watcher or
  START); PR #6522 GMI Theme Graph finish-and-fold is OPEN (F00B crosswalk line 160). The
  W3C question is answered, not open.
- **Authority ceiling (verbatim from ledger):** `research_display_only; no gate/rank authority`
- **First bounded slice when it opens:** One read-only gap-monitor view comparing TXI hop
  coverage against the GMI edge state at the current max-belief_time view, citing both stores
  by name. Display only: no gate or rank authority.
- **Ledger evidence:** row `MO-PAID-043` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=UPGRADE_EXISTING_OWNER, capability_state_c2=PARTIAL, real_consumer=NONE (gap-monitor consumer absent)

The GMI edge store keeps an append-only, keep-first correction behavior on
`(edge_id, belief_time)` — `engine/theme_graph/store.py:114-117` — with the current view
defined as the max-belief_time row per edge_id.

## MO-PAID-044 — second-order screener chaining an accepted K3-D signal

- **Disposition:** DOCKETED
- **Gate:** `K3-D + K5`
- **Opener:** Sol acceptance of the K3-D economic-propagation commission (PR #6514 OPEN
  HOLD-FOR-SOL, F00B crosswalk line 165; WS-ALPHA-INTELLIGENCE-INTEGRATION.md:205 records
  K3-D as NOT_BUILT), then a separately commissioned K5.
- **Authority ceiling (verbatim from ledger):** `research_only`
- **First bounded slice when it opens:** One second-order screener that chains TXI and
  theme-graph context through an accepted K3-D signal, creating no new grader, ranker or
  fourth store.
- **Ledger evidence:** row `MO-PAID-044` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=UPGRADE_EXISTING_OWNER, capability_state_c2=NOT_BUILT, real_consumer=NONE

The TXI producer is `engine/transmission_chains.py:109`
(`class ChainSchemaError(ValueError)`); the theme-graph side is
`engine/theme_graph/identity.py:1-16` (ticker-epoch identity law, `company_node_id` at
`:129`, `theme_node_id` at `:141`).

## MO-DELTA-006 — ranked-catalyst Opportunity Map

- **Disposition:** DOCKETED
- **Gate:** `K5`
- **Opener:** For the calibrated half: a separately commissioned K5 plus Eval-OS calibrated
  promotion. The plain uncalibrated half has no gate — it was ruled lawful now by the Sol
  PROGRAM-CEO C2 docket ruling (#6748 comment 5504596085) and is simply not scheduled by this
  packet.
- **Authority ceiling (verbatim from ledger):** `research_priority_only; authority semantics REJECTED_BY_DESIGN absent calibrated promotion proof`
- **First bounded slice when it opens:** A plain uncalibrated research-priority ordering
  shown as a projection: a list ordered by one stated non-calibrated rule, with every
  calibrated field absent and its absence disclosed in plain words on the surface.
- **Split:** LAWFUL-NOW-BUT-UNCALIBRATED
- **Ledger evidence:** row `MO-DELTA-006` of `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  — granular_disposition=PROJECTION_ONLY, capability_state_c2=NOT_BUILT, real_consumer=NONE

The calibrated fields — direction, confidence, expected-impact, gate, and size — each stay
REJECTED_BY_DESIGN behind K5 plus Eval-OS calibrated promotion. This packet records the
permission and does not exercise it — no calibrated field is scheduled.

## What we do not know — nulls, printed

- Zero of the eight rows is closed. None is built, promoted, or capability-closed.
- We do not know WHEN any gate opens. This page records state on 2026-09-06, not a schedule.
- The commission for this packet named PR #6498 as a K2-C binding. Nothing in this checkout
  corroborates #6498 — it appears in no research document, ledger row, or workstream record.
  It is therefore recorded here as unverified and is cited by no row. The K2-C binding this
  docket uses is #6533 (F00B crosswalk line 166).
- MO-PAID-043's fold sequence is recorded as NOT executed. That is a ruled answer, not a
  measurement taken today, and it changes if D2C is placed.
- MO-PAID-042 has two independent blockers, not one. K5 opening leaves the second standing.

## Ledger reconciliation — deliberately deferred

This docket writes no disposition column into
`MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`. That CSV is a shared write
surface and PRs #6924 and #6925 both edit it; a third concurrent writer would conflict on
merge order. The disposition write lands in one reconciliation commit after #6924 and #6925
merge. Until then this file is the authority on these eight rows' dispositions.

## Standing limits this docket does not move

- No row here carries trading authority, and none acquires any by being docketed.
- No language model originates a signal, score, or escalation in any slice named above.
- No new nav header, no third page-header family, no new graph, store, grader, or ranker.
- Identity resolution stays with Stock Identity, Data OS, and Supabase auth.
- Evidence in every future slice uses the K1 EvidenceRef / EvidenceBlock / EvidenceRecipe
  vocabulary; corrections are typed states.
- No proprietary Market Ontology code, text, data, or asset is copied into this repo.
