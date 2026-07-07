# Ruling Graph Adjudication and Freeze — by Fable

Date: 2026-07-06
Adjudicates: `research/fable_exit/01_FABLE_CASE_LAW_COMPILER_AND_RULING_GRAPH_HANDOFF.md` (Codex, 2026-07-07)
Status: FROZEN contract. Implementation may begin. Rows in `config/ruling_graph.yml` citing this doc are canonical.

> **In plain English:** the repo has hundreds of Fable rulings scattered across 60+ docs, PR bodies,
> and code guards. Future models keep re-proposing ideas that were already killed, deferred, or built.
> This program compiles the rulings into one queryable registry (`config/ruling_graph.yml`) with a CI
> checker that warns when a new research doc re-proposes killed/deferred law without citing it.
> Every row must carry a verbatim quote from its source doc, so invented law cannot merge.

## Verdict on the Codex handoff

ADOPT WITH AMENDMENTS. The problem statement is correct (law-rich, retrieval-poor; four failure
modes: duplicates, un-cited kill revivals, premature deferral returns, silent boundary changes).
The seed table is largely accurate and is superseded by the full extraction pass recorded in this
program. The schema and checker are adopted with the amendments below. The doc's own instruction —
"do not build from this handoff; Fable freezes the contract first" — is honored: this document is
the freeze.

## Freeze rulings (RUL-CL-1 .. RUL-CL-14)

### RUL-CL-1 — Canonical source of truth
`config/ruling_graph.yml` is the single canonical store of case-law rows; `site/neuralwebdata/ruling_graph.json` and `docs/NEURAL_WEB_CASE_LAW.md` are deterministic build products of it, and no `data/` JSONL ledger exists in v1.
Rationale: git history is the event log; a forward ledger would create a nightly-advancer
obligation (house ledger law) with no consumer. Supersession is expressed in-row
(`supersedes`/`superseded_by`), and the YAML is the review surface Fable/operator actually edit.

### RUL-CL-2 — Two-axis vocabulary
Codex's single 12-class list conflates disposition with object kind; the frozen vocabulary is two axes: `status` ∈ {active_law, adopted, residue_adopted, deferred, killed, no_build, duplicate, blocked, superseded} and `object_kind` ∈ {constitution, process, lobe, rail, wave, study, context, data_contract, signal_family}.
A killed *lobe proposal* and a killed *script* are different objects with the same disposition;
one axis cannot carry both.

### RUL-CL-3 — Globally unique, namespaced ruling IDs
Bare in-doc labels collide across programs (RUL-7 exists in entry-stack and elsewhere; RUL-27..34 overlap nontech numbering), so graph `ruling_id`s are globally unique — already-unique house labels (RUL-F3.8, DT-R14, LH-R11, RF-6, RUL-ORTH-8) are kept verbatim, and colliding plain-numbered labels get a program prefix (ESX-RUL-7, NW-RUL-3) with the bare label preserved in `aliases`.

### RUL-CL-4 — Verbatim source quotes, not line numbers
Every row MUST carry `source_quote`, a verbatim contiguous excerpt (40–400 chars) from `source_doc`, and CI verifies byte-presence of every quote in its source; `source_lines` is dropped from the schema.
Line numbers rot on edit; quotes are self-verifying. This is the anti-false-certainty guarantee:
a row whose quote cannot be found does not merge, therefore LLM-invented law cannot merge.
This mechanically enforces "no LLM-authored ruling rows" — LLMs transcribe, never originate.

### RUL-CL-5 — Precedence order (adopted verbatim from Codex)
Precedence: (1) Constitution / CLAUDE standing law, (2) Fable masterplan or adjudication doc, (3) ratified PR body, (4) synapse/config law, (5) code guard/docstring, (6) data row or status log, (7) Codex/Fable-exit research packet; on conflict the lower-precedence row must cite `superseded_by`.

### RUL-CL-6 — Conflict checker severities, v1
The v1 checker hard-fails on exactly two crisp classes — (a) a new `fdr_family` token not present in the graph's known-families set, and (b) held-book/fill/position tokens appearing under public `site/` paths — and everything else (killed-idea re-proposal without citation, deferred-before-clock, lobe-charter language, quote drift, expired clocks) is WARN in v1.
Codex proposed hard-fail for lobe charters and privacy changes broadly; lobe charters have no
machine-readable registry yet, so a HARD gate would be a vibes gate. WARN until the graph itself
becomes that registry (two clean weeks per Codex's own ratchet), then escalate by amendment.

### RUL-CL-7 — Deterministic matching only
Re-proposal detection is a deterministic, diff-aware substring scan of each row's curated `match_terms` against changed research/config files, requiring the ruling_id string to appear in the changed file to clear; no LLM matching runs in CI.

### RUL-CL-8 — No bespoke clocks (RF-9 applied to the graph itself)
A row with `come_back_on` must carry `experiment_ref` pointing at an experiments-registry id when a matching registry entry exists; the checker WARNs on clocked rows with no ref.
The registry (`data/experiments/registry_seed.json`) is the house clock spine; the graph must not
become a second, drifting clock store.

### RUL-CL-9 — Public exposure
`site/neuralwebdata/ruling_graph.json` carries only rows with `privacy_class: public_research`, and the build hard-fails if a public row contains a denylisted token (competitor/source names and held-book vocabulary); rows from personality-source adjudications default to `privacy_class: internal_only`.

### RUL-CL-10 — No PR template in v1
The Codex-proposed PR-template YAML section is DROPPED: no PR template exists in this repo and `gh pr create` (the only PR path agents use) does not apply templates non-interactively, so the CI checker carries the enforcement instead.

### RUL-CL-11 — v1 scope fence
v1 ships exactly: the curated YAML, `scripts/build_ruling_graph.py`, `scripts/check_ruling_conflicts.py`, `tests/test_ruling_graph.py`, the generated `docs/NEURAL_WEB_CASE_LAW.md` + site JSON, synapse registration, and the CI job; the admin panel tab, cortex read-only tools (`read_ruling_graph` et al.), and the Research Factory packet hook are registered come-back waves, not v1.
Rationale: RUL-C8 bandwidth honesty. The retrieval value is in the graph + friction; the
integrations are additive and must not delay the spine.

### RUL-CL-12 — The graph's own authority
The ruling graph is itself `object_kind: context`, `authority_ceiling: A1_EXPLAIN`, display-only, all authority booleans false; it may never gate, rank, score, or block a build by itself — its CI checker enforces *citation*, not *permission*, and only Fable/operator change law.

### RUL-CL-13 — Succession (adopted from Codex with one tightening)
Fable seed rows are canonical; post-Fable rows may be *proposed* by any actor but *accepted* only by the operator, and rows touching authority, privacy, FDR families, lobe charters, or reviving a `killed` row are nondelegable — they stay blocked absent a frozen replacement adjudication procedure.
Tightening: Codex allowed "Opus/operator packets" to propose — fine — but acceptance is
operator-only in all cases, not just nondelegable ones, because CI cannot distinguish an Opus
packet from any other LLM edit.

### RUL-CL-14 — Seed set for v1
v1 seeds are the full verified extraction from the 23 canonical sources listed below (constitution, CLAUDE.md, the NW masterplan + rails + all seven NW adjudications, Research Factory, bridge, factor, R-ORTH, DannyTrades, live-activation, gap-map, OVC, entry-stack masterplan + amendment 3, cycle-pattern truth schema, quant-synthesis, long-hold, cycle-pattern masterplan), curated by Fable to rows with standing or cross-program force; program-internal micro-verdicts ride later waves.
Every seed row was machine-quote-verified and Opus-audited for faithfulness before curation;
the Codex seed table served as the recall checklist.

## Answers to the seven freeze questions

1. **YAML or JSONL first?** YAML curated in `config/` (RUL-CL-1).
2. **Status vocabulary?** Two axes (RUL-CL-2).
3. **Precedence?** Codex order adopted (RUL-CL-5).
4. **Day-one hard-fails?** New FDR family token; held-book vocabulary under `site/` (RUL-CL-6).
5. **Post-Fable rulings?** Propose: anyone. Accept: operator only. Nondelegable classes blocked (RUL-CL-13).
6. **Mandatory seeds?** Verified extraction from 23 sources, Fable-curated (RUL-CL-14).
7. **Public exposure?** `public_research` rows only, token-denylisted (RUL-CL-9).

## Come-back waves (not v1)

- **W2 — Research Factory packet hook**: challenger packets carry top-5 ruling hits before Opus review.
- **W3 — Cortex read-only tools**: `read_ruling_graph(topic)`, `list_active_clocks(owner_program)`, `explain_ruling(ruling_id)`; citations mandatory, creation impossible.
- **W4 — Admin Observatory card**: clocks due, kills, deferrals with unblock, supersessions, uncited-conflict warnings.
- **W5 — Severity ratchet**: killed-idea re-proposal WARN→HARD after two clean weeks (per Codex), plus lobe-charter HARD once the graph is the charter registry.
- **Backfill waves**: remaining adjudication docs (oracle constitution + rulings, setup-species, china programs, mastermind control plane, options masterplans, healthcare dispersion, nontech bottom, short-side/dispersion charters, signal-lab frontier series).

## Relationship to the other seven fable_exit handoffs

This adjudication covers handoff 01 only. Handoffs 02–08 in Codex's worktree remain UNADJUDICATED
and carry no force; several (04 ownership map, 06 evidence-clock autopilot, 07 unified guard suite)
would become consumers or extensions of this graph and should be adjudicated against it.
