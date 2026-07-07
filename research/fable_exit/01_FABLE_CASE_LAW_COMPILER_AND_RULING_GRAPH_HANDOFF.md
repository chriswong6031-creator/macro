# Fable Case-Law Compiler and Ruling Graph Handoff

Prepared: 2026-07-07
Author: Codex
Status: research and freeze-spec only; do not treat this as an implementation PR.
Audience: Fable first, then Claude/Sonnet/Opus implementers.

## Executive Decision

The Neural Web no longer lacks ideas. It now lacks a compact, executable memory of Fable's decisions.

The repo has a large body of law across research docs, PR descriptions, code comments, CI guards, and data contracts. My local census found:

- 825 `RUL-*` mentions across 63 files.
- 98 `RF-*` Research Factory law references across 9 files.
- 211 artifacts in `config/synapse.yml`, with 34 under `neural-web`.
- 17 open GitHub PRs during this pass, while `origin/main` advanced twice.

This means a future model can easily write a persuasive but illegal or duplicate plan. The immediate build should not be another lobe. It should be a curated `ruling_graph` that lets every future research packet ask:

```text
Has Fable already ruled on this idea?
Who owns it?
Was it killed, deferred, scoped, or adopted as residue?
What would legally reopen it?
What actions are forbidden before that reopen condition fires?
```

## What This Doc Does For Fable

This handoff pre-chews the expensive part:

- a doctrine taxonomy,
- seed ruling families to extract,
- a proposed schema,
- precedence and supersession rules,
- conflict-check logic,
- the likely objections Fable should resolve now.

Fable should not need to reread 60+ files to decide whether the compiler is worth freezing.

## Evidence Base

Primary local surfaces checked:

| Surface | What It Proves |
|---|---|
| `CLAUDE.md` | Fable plans/adjudicates/merges; Opus reviews; Sonnet builds. This is a role law, not just taste. |
| `engine/neuralweb/constitution.py` | Article 1 origination ban, Article 2 perimeter, Article 3 authority floor, A0-A7 ladder. |
| `engine/neuralweb/governance.py` | Authority transitions are already append-only events, but not broad case law. |
| `docs/SIGNAL_BUS.md` / `config/synapse.yml` | Artifact registry and consumer map; 211 artifacts, 34 neural-web, 202 git, 6 gitignored-local, 3 R2. |
| `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` | Two-lobe cap and rails/tier-1 law. |
| `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md` | Good Codex proposals were decomposed into existing waves; zero new lobes. |
| `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md` | Duplicate/stale/forbidden plans were reshaped into legal final-3 waves. |
| `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` | Candidate-state, actor, clock, trial accounting, and projection laws. |
| `research/NW_MASTERMIND_BRIDGE_PROGRAM.md` | Context-only, public-safe Neural Web -> Mastermind bridge law. |
| `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md` | Factor integration rulings and explicit activation floor examples. |
| `scripts/check_validated_claims.py`, `scripts/check_research_factory_authority.py`, `scripts/check_cycle_pattern_authority.py` | Some doctrine is already executable, but only in isolated guards. |

GitHub PR evidence:

- #1545: Neural Web rails/tier-1 program.
- #1571 and follow-ons: Research Factory W0-W7.
- #1629: Research Factory Batch A adjudication pattern.
- #1673: three-lobes adjudication, zero-charter outcome.
- #1695: Final-3 adjudication and masterplan.
- #1731: Research Factory Batch B / Cortex hardening.
- #1773: Cycle Pattern lobe and hazard UI.
- #1776: curated Synapse Map.
- #1777: entry-stack decline geometry merged during this pass.

## Problem Statement

The current state is law-rich but retrieval-poor.

Fable rulings are spread across:

- `RUL-*` paragraphs in research docs,
- PR bodies and merge histories,
- `RF-*` clauses,
- `config/synapse.yml` notes,
- code docstrings,
- authority guard scripts,
- `data/neuralweb/governance.jsonl`,
- experiments registry clocks,
- review queue artifacts.

This causes four expensive failure modes:

1. Duplicate ideas are re-proposed as new charters.
2. Killed ideas return without citing their kill reason.
3. Deferred ideas return before their clock/data condition has matured.
4. Authority/privacy/FDR boundary changes get treated as ordinary implementation details.

## Doctrine Taxonomy

The compiler should not start as a free-text search index. It should encode Fable's operating distinctions.

### Classification

Use these as the first status/classification vocabulary:

| Class | Meaning | Example |
|---|---|---|
| `constitution` | Article / authority ladder law. | A7 origination banned. |
| `lobe` | Owns objective, labels, falsifiers, authority path, FDR family. | L1 Short-Side, L3 Dispersion. |
| `rail` | Shared substrate with no objective function of its own. | R1 replay governor, R-ORTH covariance spine. |
| `wave` | Build slice inside an existing program. | Claim-accountability audit bridge. |
| `study` | Measurement or preregistered analysis only. | L6-P0 macro transmission phase-0. |
| `context` | Display/advisory artifact with no scored behavior. | `mastermind_context.v1`. |
| `no_build` | Legal conclusion: do not build as proposed. | Realized Decision Passport. |
| `duplicate` | Already exists or belongs to another owner. | Claim reliability as a new lobe. |
| `deferred` | Real idea, wrong time; must wait for clock/data/cap. | Dispersion feature store before DISP-GATE readout. |
| `killed` | Do not revive without a new factual basis. | Standalone `exit_regret_v2.py` governor bypass. |
| `blocked` | Cannot proceed until missing data/contract exists. | Held-book feedback before Mastermind contract. |
| `residue_adopted` | Proposal rejected as framed, but a smaller residue ships. | Claim reliability audit and bridge. |

### Scope Fences

Every row needs a scope fence. Examples:

- "No new lobe charter; ships only as rail/study/wave."
- "Display-only; no ranked-output consumer."
- "Context-only; all authority booleans false."
- "QI owns qledger semantics."
- "Mastermind owns held-book/fills."
- "No new FDR island; use flat pooled family."
- "No same-tape conditioning until prior gate prints."

### Authority Ceiling

Suggested vocabulary:

```yaml
authority_ceiling:
  - A0_observe
  - A1_explain
  - A2_attend
  - A3_de_escalate
  - A4_quarantine
  - A5_govern_tiers
  - A6_tune
  - A7_banned
```

Every row that touches behavior should carry both the ceiling and the source of that ceiling.

## Seed Ruling Table For Fable

This is the first extraction set I would ask Fable to confirm. The wording below is deliberately compact; the source docs remain canonical.

| Seed ID | Source | Pre-Summarized Ruling |
|---|---|---|
| CONST-A1 | `engine/neuralweb/constitution.py` | Neural Web may not originate a signal, trade, escalation, or claim. A7 is permanently refused. |
| CONST-A2 | `engine/neuralweb/constitution.py`, `config/synapse.yml` | Money-path and ranked-output surfaces are Article-2 surfaces; display/context artifacts cannot influence them without an earned authority path. |
| CONST-A3 | `engine/neuralweb/constitution.py` | Authority grants need sample floors, Wilson lower-bound lift, and freshness; silence or stale evidence lapses authority. |
| ROUTE-1 | `CLAUDE.md` | Fable adjudicates and merges; Opus reviews; Sonnet builds. Fan-outs must not spend Fable. |
| RUL-P1 | `NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` | Exactly two lobes were chartered in that program: L1 Short-Side and L3 Dispersion. Other work must route as rail, study, or existing-program wave. |
| RUL-P10 | `NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` | Data-path ownership matters: choose git, gitignored-local, or R2 intentionally; do not let nightly blanket staging decide. |
| RUL-C1 | `NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md` | Three proposed "new lobes" produced zero new charters; cap stays consumed. |
| RUL-C2 | same | `claim_reliability` is the legal bridge key; do not clobber the existing `reliability` lobe key. |
| RUL-C3 | same | QI owns qledger grading semantics. Legal work is read-only coverage/accountability diagnostics and bridge integration. |
| RUL-C4 | same | Macro transmission is a phase-0 measurement, never a fused macro hostility score, and operates at sector/basket/board grain. |
| RUL-C5 | same | Narrative/price contradiction arbitration is a come-back experiment, not a new grader. |
| RUL-C6 | same | Qledger story-decay waits for grade maturation; no parallel apparatus. |
| RUL-C8 | same | Bandwidth law must be stated honestly; extending a renderer is still render work even if seconds-scale. |
| RUL-C9 | same | New artifacts require synapse registration, Signal Bus regeneration, and declared commit path. |
| RUL-C10 | same | LLMs may cite measured context; they may not score, escalate, originate, or adjust measured values. |
| RUL-C11 | same | `macro_tx` is a flat pooled FDR family for macro-conditioning studies; sub-islands are forbidden. |
| RUL-F3.1 | `NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md` | Final-3 work ships without new lobe charters because the lobe cap remains consumed. |
| RUL-F3.2 | same | Exit/trim metrics attach to fire-tape counterfactuals, not held positions. |
| RUL-F3.3 | same | Label features must be pre-outcome only; outcome-derived labels are blocked. |
| RUL-F3.4 | same | Standalone `exit_regret_v2.py` is killed; legal increments ride existing replay/trim/net derivations. |
| RUL-F3.5 | same | TRIM-GRID is descriptive-only and contamination-stamped; later promotion requires fresh OOS evidence. |
| RUL-F3.6 | same | DISP-GATE prints feasibility/exclusion first; thin-cohort defer is a valid outcome. |
| RUL-F3.7 | same | Display-only guarantees need tests before dispersion enrichment grows. |
| RUL-F3.8 | same | Dispersion feature store, selection-trust model, and conditioning matrix are deferred until unblock conditions fire. |
| RUL-F3.9 | same | NET-REPLAY is a derivation over already-seen cells; gross/net side by side; no new verdict language. |
| RUL-F3.10 | same | Tax work is scenario-rate analysis, not an advice engine or tax-lot system. |
| RUL-F3.11 | same | Realized Decision Passport is killed; existing passport/provenance surfaces carry that role for now. |
| RUL-F3.12 | same | ThetaData tape calibration is Mac-side ops tooling, never render-path. |
| RF-2 | `RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` | Factory persists orchestration state only; authoritative domain registries are projected at read time. |
| RF-4 | same | Factory state machine has exactly defined states; `awaiting_data` and `deferred` are first-class and clocked. |
| RF-5 | same | Human-gate states require Fable/operator; script actors cannot enter terminal judgment states. |
| RF-6 | same | Trial accounting is explicit; RF families, cortex-shared, oracle-screen, and read-only modes differ. |
| RF-8 | same | Factory ledgers are append-only and nightly-forward where appropriate. |
| RF-9 | same | No bespoke clocks; paper/deferred/awaiting-data candidates go through experiments registry seed. |
| RF-10 | same | Kills need evidence and requeue logic when underpowered or regime-suspect. |
| RF-11 | same | Factory data is display-only and guarded from Article-2 surfaces. |
| BRIDGE-1 | `NW_MASTERMIND_BRIDGE_PROGRAM.md` | Neural Web -> Mastermind bridge is context-only, public-safe, all authority booleans false. |
| BRIDGE-2 | same | Candidate context is bounded; `book_context` is counts/contradictions only, not held-book/fill data. |
| FACTOR-NW6 | `factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md` | A3 factor de-escalation needs at least 25 episode-clustered events across three months plus explicit Fable activation. |
| RORTH-1 | `pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md` | Orthogonality work is a rail/accounting spine, not a new lobe or alpha source. |
| CPI-TRUTH | `config/cycle_pattern/truth_schema.md` | Truth status is the authority gate; null and retired truths cannot feed positive consumers. |

Fable should edit this seed set rather than start from a blank page.

## Proposed Artifact Contract

Doc-only freeze target:

```text
config/ruling_graph.yml
data/neuralweb/ruling_graph.jsonl
site/neuralwebdata/ruling_graph.json
docs/NEURAL_WEB_CASE_LAW.md
scripts/build_ruling_graph.py
scripts/check_ruling_conflicts.py
```

Do not build these from this handoff. The point of this doc is to let Fable freeze the contract.

### Row Schema V1

```yaml
schema: neuralweb.ruling.v1
ruling_id: RUL-F3.8
short_name: dispersion_upgrades_deferred
source_doc: research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md
source_lines: "52-53"
source_pr: 1695
source_commit: null
precedence_rank: 40
topic:
  primary: dispersion feature store and selection-trust conditioning
  aliases:
    - lobe-conditioning matrix
    - dispersion selection trust
status: deferred
classification: rail_wave
owner_program: nw-final3
authority_ceiling: A1_explain
privacy_class: public_research
scope_fence: >
  Do not build feature store, residual selection-trust model, or conditioning matrix
  before DISP-GATE-1 readout and a later charter.
fdr_family: replay
declared_budget: null
derived_from_surface: disp_gate_1
contamination_compensation: fresh_oos_required_for_later_promotion
forbidden_actions:
  - score
  - size
  - gate
  - rank
  - condition_entry
unblock_condition: DISP-GATE-1 printed and L3 charter extension approved.
come_back_on: null
supersedes: []
superseded_by: []
nondelegable: true
delegation_note: Fable/operator must approve any charter reopening.
review_lenses:
  - duplication
  - statistics
  - authority
  - build_scope
evidence_refs:
  - research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md
```

### Precedence Rules

Fable should freeze precedence now. Recommended order:

1. Constitution / CLAUDE standing law.
2. Fable masterplan or adjudication doc.
3. Ratified PR body / merge description.
4. Synapse/config law.
5. Code guard/docstring.
6. Data row or status log.
7. Codex/Fable-exit research packet.

When two rows conflict, the lower-precedence row must cite `superseded_by`.

### Conflict Checker Behavior

Start warn-only. Hard-fail only narrow, high-risk omissions:

| Trigger | Suggested Severity |
|---|---|
| New research doc proposes an idea with high match to `killed` ruling and does not cite it. | WARN initially; HARD after two clean weeks. |
| Any public/private boundary change without citing a ruling row. | HARD. |
| New FDR family not in `ruling_graph` or `TrialLedger` family set. | HARD. |
| New lobe charter while cap is consumed and no Fable/operator override row. | HARD. |
| `validated`-style promotion language without evidence artifact. | Existing guard, keep HARD where already enforced. |
| New held-book/fill/position field under public Macro paths. | HARD. |
| Deferred item before `come_back_on` or `unblock_condition`. | WARN, unless authority changes. |

## Integrations

### Research Factory

Every challenger packet should include:

- top 5 ruling hits,
- active clocks,
- owner-program collision,
- whether the idea is duplicate/deferred/killed,
- legal reopen condition.

This should happen before Opus review, so Opus reviews the real novelty rather than discovering duplicate law.

### Cortex / Ask-The-Brain

Give read-only tools:

- `read_ruling_graph(topic)`
- `list_active_clocks(owner_program)`
- `explain_ruling(ruling_id)`

The tools must return citations and never create rulings.

### PR Templates

Add a Neural Web section:

```yaml
ruling_graph_checked: true
ruling_ids_cited:
  - RUL-C9
  - RF-6
new_fdr_family: false
authority_boundary_changed: false
privacy_boundary_changed: false
```

### Admin Panel

Minimal panel:

- active clocks due soon,
- killed ideas,
- deferred ideas with unblock,
- owner-program map,
- latest supersessions,
- uncited conflict warnings.

## Likely Fable Objections And Answers

### "This could become false certainty."

Correct. The graph must cite source docs/PRs and support supersession. No row is source-less. No LLM-authored ruling rows.

### "Hard-failing conflicts will block good work."

Start warn-only except authority, privacy, FDR, and lobe-charter changes. The first job is retrieval and friction, not bureaucracy.

### "This is metadata busywork."

The same-day Final-3 adjudication estimated most of the plan was duplicate, stale, or forbidden. The user is also running multiple active Claude sessions. Case law retrieval now saves more time than another memo.

### "What about partial adoption?"

Use `residue_adopted` plus `forbidden_actions`. A proposal can be rejected as a lobe but adopted as a bridge, audit, or display row.

### "Who can write rulings after Fable?"

This is a succession question. My recommended answer:

- Fable seed rows are canonical.
- Future rows can be proposed by Opus/operator packets.
- Human operator can accept rows that do not alter authority/privacy/FDR/lobe status.
- Nondelegable rows stay blocked unless a replacement adjudication procedure is frozen.

## Fable Freeze Decisions

Fable should rule on these, in order:

1. Is `ruling_graph.yml` the curated source of truth, or should rows live in data JSONL first?
2. What is the status vocabulary?
3. What is the source precedence order?
4. Which classes become hard-fail in CI from day one?
5. Can operator-authored post-Fable rulings exist? If yes, under which nondelegable exclusions?
6. Which 75-100 seed rulings are mandatory for v1?
7. Should public `site/neuralwebdata/ruling_graph.json` expose all rows, or only safe public summaries?

## V1 Success Test

A future request such as "build a claim reliability lobe" should produce:

```text
Hit: RUL-C1, RUL-C2, RUL-C3, RUL-C10
Disposition: no new lobe; legal residue is read-only claim-accountability audit and bridge.
Owner: QI for grading semantics; Neural Web for accountability display.
Forbidden: learned source weights, qledger semantic edits, LLM scoring.
Reopen: >=500 graded labels for QI reliability ontology, plus Fable/operator charter.
```

That is the workload reduction. Fable should decide whether that answer is correct, not spend tokens finding it from scratch.
