# Research Factory — Scheduled Automation Lane (program seed, for a future Fable session)

**Status:** NOT STARTED — deferred by ruling RF-16 of `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` (factory W0–W7 COMPLETE 2026-07-06; Batch A adjudicated in #1629).
**Prepared:** 2026-07-06 by the Fable session that built the factory.
**Trigger to start:** ≥2–3 more MANUAL batches adjudicated after Batch A (i.e., the loop is proven useful and its kill/paper rates are known from `data/research_factory/health.jsonl`) AND an operator decision that the manual challenger-invocation step is the bottleneck. Do not start this program because it seems natural — start it because the health ledger shows human-invoked throughput is the constraint.

## 1. What this program is

Move two LLM stages from operator/Fable-invoked to scheduled: (a) candidate extraction from selected prompt packs (external reports via `scripts/research_factory_report_pack.py`, oracle brainstorm packs), and (b) challenger batches for candidates that cleared numeric screens and sit in `screened` without a challenge file. Plus cost telemetry. Everything else — ingest, dedup, transitions, review queue, decisions, monitor — is already deterministic or human and does NOT change.

## 2. Binding constraints (inherited, not renegotiable here)

- LLM stages remain propose/challenge-only (constitution A0–A2; challenger stays ADVISORY — RF-7). Scheduling changes WHO invokes, never WHAT authority the output has.
- Deterministic scripts remain the only ledger writers; scheduled LLM output lands in an inbox and goes through `research_factory_ingest.py` / `--ingest-response` validation exactly as today. Malformed output = no transition, loud warning.
- Human gate stays synchronous and manual: nothing scheduled may enter `paper`/`deferred`/`rejected`/`scoped_build` (actor law in `engine/research_factory/state.py` enforces this — scheduled runs are `script` actors).
- **Identity: API service key, never personal Claude OAuth** (`SELF_IMPROVING_AI_SUITE.md` made this call; user OAuth is fragile in CI and unauditable). Key rides as a repo secret (self-hosted runners are FS-isolated — memory `self-hosted-runners-fs-isolated`).
- Arming-predicate doctrine (constitution A6 lane conventions): no env-flag switches; the lane arms via config.yml with a declared predicate (e.g. `research_factory_auto.enabled` + minimum manual-batch count + cost ceiling present), and every scheduled run logs a governance event (`research_factory_challenge`, `article: null` — already registered in `engine/neuralweb/governance.py`).
- Off the render path; its own workflow lane (NOT daily.yml engine job, NOT render.yml). Weekly cadence recommended over nightly — candidate inflow is slow and the 3/week cortex budget shows small-N is a feature.

## 3. Design sketch

1. `scripts/research_factory_auto_challenge.py`: enumerate `screened` candidates without challenge files (resolve state from transitions.jsonl — candidates.jsonl status is the ingest-time snapshot), cap at N per run (recommend 5), emit packets (existing `challenge_pack --candidate`), call the reviewer via the Anthropic API with `research/research_factory/CHALLENGER_PROMPT.md` + packet, validate via the existing `--ingest-response` path. Model: Opus tier per CLAUDE.md routing (challenger = review work). Retries bounded; on persistent failure, skip and flag — never block the lane.
2. `scripts/research_factory_auto_extract.py`: same shape for extraction packs; output goes to an inbox dir for the deterministic ingest. Extraction proposals count toward dedup/trial law exactly as manual ones.
3. **Cost telemetry ledger** `data/research_factory/llm_costs.jsonl` (git-tracked, small): per run — stage, model, input/output tokens, computed cost, candidates processed. Health builder gains a cost-per-surviving-candidate line; a monthly ceiling in config aborts the lane when crossed (loudly, with a governance event).
4. Kill switch = config.yml disarm (`enabled: false`), honored at run start.

## 4. Fable decision checklist

1. Cadence (weekly recommended) and per-run cap (5 recommended).
2. Monthly cost ceiling in dollars, and what happens at 80% (warn) vs 100% (disarm).
3. Which packs are auto-extraction-eligible (recommend: none at first — start with auto-challenge only; extraction keeps a human because it decides what enters the funnel at all).
4. Does the scheduled challenger get the identical prompt as manual runs, or a hardened variant (recommend identical — one prompt, one behavior, CODEOWNERS-protected once the codegen program lands).
5. Failure semantics: how many consecutive failed runs before auto-disarm + operator alert.

## 5. What to read first in a fresh session

`research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` (RF-7/RF-12/RF-16; §6 Deferred), `scripts/research_factory_challenge_pack.py` (the ingest-response contract you're wrapping), `data/research_factory/health.jsonl` (the evidence the trigger condition asks for), `research/research_factory/OPERATING_RUNBOOK.md` (what the manual loop does today), memory `research-factory-program`.
