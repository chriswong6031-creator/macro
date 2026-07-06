# Research Factory — Codegen Lane (program seed, for a future Fable session)

**Status:** NOT STARTED — deferred by ruling RF-16 of `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` (the Research Factory charter, W0–W7 COMPLETE 2026-07-06, PRs #1571/#1575/#1580/#1581/#1602/#1601/#1622/#1623/#1629).
**Prepared:** 2026-07-06 by the Fable session that built the factory.
**Blocker to lift before ANY build:** an OS/identity-level boundary between LLM-generated code and the evaluators. Until that exists, this program may not start. This is the single hardest precondition in the factory family — do not soften it.

## 1. What this program is

Let LLM-generated strategy/feature code enter the factory as candidates (`candidate_type='code_candidate'`), be executed safely, and flow through the same screened → challenged → human_review funnel as grammar candidates. Today the factory is deliberately DSL/spec-first: Oracle candidates are JSON grammar, alpha-grammar candidates are ASTs, and arbitrary codegen was rejected for v1 (charter §2 finding 6, RF-16).

## 2. Why it was deferred (read before scoping)

`research/SELF_IMPROVING_AI_SUITE.md` §0 states the actual threat precisely: the LLM/evaluator separation today is an **in-process Python allowlist — defeatable by any bug or prompt injection** — and the nightly GitHub Actions job runs with `contents:write` pushing to main. An agent that can write code that the nightly executes can, transitively, edit gates. The factory's authority guard (`scripts/check_research_factory_authority.py`) protects the Article-2 read perimeter, not the write path. Codegen without an identity boundary converts "LLM proposes" into "LLM ships."

## 3. Non-negotiable preconditions (each is a deliverable of THIS program, before any generation)

1. **Separate runner identity** for anything that executes or lands generated code: `contents:read`, PR-only (no push to main). GitHub App or machine user — Fable decides which (note: self-hosted runners have virtualized FS, no host creds; secrets ride as repo secrets — see memory `self-hosted-runners-fs-isolated`).
2. **Branch protection on main** requiring review for the protected paths below (verify current settings first; the repo today squash-merges same-day without required reviews).
3. **CODEOWNERS** (human/Fable-owned, enforced): `engine/validation.py`, `engine/trial_ledger.py`, `engine/promotion_gate.py`, `engine/oracle/compounds.py`, `engine/research_factory/**`, `scripts/check_*.py`, `.github/workflows/**`, `config/dag.yml`, `config/synapse.yml`, `research/research_factory/CHALLENGER_PROMPT.md` (challenger prompts are validators in prose).
4. **Sandboxed execution** for generated code: no network, pinned deps, CPU/memory/time limits, read-only data mounts, PIT-clipped datasets (the sandbox only ever sees data ≤ the candidate's info_cutoff — lookahead becomes physically impossible rather than lint-detected).
5. **Mechanical PIT linter** for generated code (forward-index access, `.shift(-`, future-dated joins) as a first-pass gate before any run — flag-and-block, reviewer sees the report.

## 4. Design sketch (after preconditions)

- Revive the `implemented` state for this lane only (charter RF-4 explicitly reserved it for codegen; the §4 state table needs an amendment ruling to add the row back — entry actor `script`, mandatory field: sandbox run artifact + PIT-linter report).
- Trial accounting law applies at GENERATION: every generated variant is a counted trial (`TrialLedger.log_grid` of the full generated set BEFORE any backtest, family `rf.codegen.<slug>` — the fan-out is the search width, not the survivors). The 2-respin cap (RF-15) applies per lineage.
- Challenger packet gains a code lens: diff-sized review, dependency audit, PIT-linter findings, and the counterfactual-perturbation probe run on the sandbox output (the factory's probes.py already has the permutation machinery).
- Everything remains display-only, A0–A2; `paper` at most. Promotion of a codegen candidate to anything scored is a separate program on top of this one.

## 5. Fable decision checklist (answer in the W0 ruling of this program)

1. Identity mechanism: GitHub App vs machine user vs separate repo with PR-sync?
2. Where does the sandbox run — Mac Studio container (resource contention with nightly?) or a rented isolated box?
3. Generation scope for v1: extensions to the Oracle grammar (new primitives proposed as code + spec) vs free pandas strategies? Recommend grammar-extensions-first — smaller attack surface, reuses the existing evaluators.
4. Volume cap (variants/day) and token budget.
5. Who reviews generated code before the sandbox even runs it — reviewer agent alone, or reviewer + human for the first N?
6. Does a codegen candidate's PR ever touch `engine/`/`scripts/`, or does generated code live quarantined under `data/research_factory/code_candidates/` (recommended: quarantined, imported only by the sandbox runner)?

## 6. What to read first in a fresh session

`research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` (whole charter; RF-4/RF-6/RF-7/RF-15/RF-16 bind this program), `research/SELF_IMPROVING_AI_SUITE.md` §0 and §5, `engine/research_factory/state.py` (the matrix you'll amend), `engine/trial_ledger.py` (generation-time counting), memory file `research-factory-program`.
