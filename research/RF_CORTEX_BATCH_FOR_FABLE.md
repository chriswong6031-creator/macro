# Research Factory — Cortex Batch (Batch B) (program seed, for a future Fable session)

**Status:** ARMED — 2026-07-06 Fable session: census complete, seams re-verified, conformance hardening shipped, rulings recorded (see §6). Trigger unchanged.
**Prepared:** 2026-07-06 by the Fable session that built the factory (charter: `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`, W0–W7 COMPLETE).
**Trigger to start:** machine_registry has ≥1 hypothesis with an evaluator verdict (`passed` / `insufficient-n` trending, or anything Fable wants challenged). Watch: cortex deliberation is failing at turn 0 with "Connection error." — ops action required before registrations can begin; see §6 for root-cause and fix. The weekly budget is 3 (hard, server-side, ISO week Mon–Sun in `engine/neuralweb/metabolism.py`).
**Come-back:** 2026-08-03 — if `data/neuralweb/machine_registry.jsonl` is still absent by then, the ops action needs escalation.

## 1. What this batch is

Batch B from the source study (`research/AGENTIC_RESEARCH_FACTORY_FOR_FABLE.md` §11): wrap graded cortex hypotheses with challenge packets + factory human review. Mostly OPERATING existing machinery — expected build is small (possibly a cortex-specific lens paragraph in the challenger prompt; everything else exists).

Success criteria (from the study, still binding): **no change to the cortex budget; no promotion; better visibility** into what the cortex actually proposes.

## 2. Binding seams (all verified in the 2026-07-06 census — re-verify file:line before relying)

- `metabolism.register_hypothesis()` is the SOLE registrar and budget chokepoint. The factory NEVER writes machine_registry.jsonl, never calls stake_hypothesis, never re-registers. A factory candidate with `source='cortex'` must carry the metabolism-issued id as `spec_ref` and a registration timestamp ≥ metabolism's server-side `registered_at` (charter RF-13).
- `claim_shape` is copied VERBATIM from the metabolism row — one of {lead_lag, conditional_regime, entry_quality, sector_conditional}; it routes `scripts/evaluate_cortex_hypotheses.py` PATH A (qledger forward-return) vs PATH B (walk-forward stop-out). The factory taxonomy field is `candidate_type='cortex_hypothesis'` (RF-3 — do not confuse the two; this was a blocker-class correction to the source study).
- Trial accounting: NO new family. Metabolism already logs `log_declared_budget(1, family='cortex')` per registration; the factory reads `TrialLedger().effective_n('cortex')` (RF-6). An `rf.cortex.*` family would double-count — this is a named trap in the charter.
- Three-layer self-grading exclusion: any `spine_query` referencing `cortex_attention` is blocked at registration, grading, and ranking. The adapter re-checks before attaching firings evidence (`_SELF_LEDGER_EXCLUSIONS` in evaluate_cortex_hypotheses; `metabolism._validate_hypothesis`; `research_queue._has_self_ref`).
- One-night cross-job lag: the cortex job commits AFTER the engine job; anything the factory reads in the engine lane is the PRIOR night's registry. Accepted and documented (adapter docstring).
- `engine/neuralweb/research_queue.py` output (`data/neuralweb/research_queue.json`) is a legitimate ingest source already wired (`research_factory_ingest.py --research-queue` ingests `high_ev_build_now`; `--nominate <id>` for other bins). Come-back-due rows come via `metabolism.load_due()` (status='registered' AND come_back ≤ today; come_back = registered_at + horizon_d + 7).

## 3. Batch procedure when triggered

1. Confirm registry rows + verdicts: read machine_registry.jsonl and the evaluator outputs.
2. Ingest: `--research-queue` (+ `--nominate`) — candidates arrive as pointer candidates (`spec_ref` = metabolism id, `trial_accounting.mode='cortex_shared'`).
3. `scripts/research_factory_run.py --execute` — the cortex adapter projects registry status (metabolism vocabulary → factory states) and attaches the graded verdict as the screen artifact.
4. Challenge packets for `passed`/interesting rows (`challenge_pack --candidate`); spawn reviewer agents per the runbook; `--ingest-response`.
5. Review queue → Fable decisions via `research_factory_decide.py`. `paper` for a cortex candidate means: factory-level display accrual with an experiments-seed clock — the metabolism come_back clock keeps running independently (two clocks by design here: metabolism owns evaluation cadence, the seed owns operator attention; the charter's RF-9 single-clock law refers to factory-originated clocks).
6. Whether a passed cortex hypothesis becomes a scoped build is a Fable ruling recorded via `--decision scoped_build --program-doc research/<NEW>_BY_FABLE.md`.

## 4. Fable decision checklist

1. Challenge every registered hypothesis, or only evaluator-`passed` rows? (Study says passed/interesting; recommend that.)
2. Does the challenger prompt need a cortex lens (metabolism gate mechanics, self-reference risks, PATH A/B ruler correctness)? Recommend a short added section, CODEOWNERS-tracked once that exists.
3. Cortex budget stays 3/week — reaffirm (raising it before the funnel has kill-rate evidence was rejected in the study AND the charter).

## 5. What to read first in a fresh session

Charter RF-2/RF-3/RF-6/RF-13; `engine/research_factory/adapter_cortex.py`; `engine/neuralweb/metabolism.py` (registration/budget/come_back); `scripts/evaluate_cortex_hypotheses.py` (verdicts); `research/research_factory/OPERATING_RUNBOOK.md`; memory `research-factory-program` and `neural-web-program`.

---

## 6. Program log — ARMED 2026-07-06

**Status change.** NOT STARTED → ARMED (2026-07-06, Fable session). A full census of every binding seam in §2 was run, conformance hardening was built and shipped, and all Fable rulings were recorded (R1–R6 below). The trigger is unchanged: first `machine_registry.jsonl` registrations with evaluator verdicts.

**Root-cause of zero registrations.** Diagnosed from CI logs, run 28772063146 and predecessors. The cortex LLM tool loop is fully wired — `stake_hypothesis` is exposed and instructed in the system prompt — but every live deliberation has failed at turn 0. Timeline: 2026-07-01→07-03 calls reached Anthropic and returned HTTP 401 "Invalid bearer token". The `CLAUDE_CODE_OAUTH_TOKEN` secret was updated 2026-07-04 at 22:57Z. Since that update, every cortex call fails instantly with SDK "Connection error." — consistent with a corrupted secret value (internal line-wrap or non-ASCII character making an illegal HTTP header), not a network block. GitHub egress from the runner works in the same jobs. `ANTHROPIC_API_KEY` is not set at all in the repo, so there is no failover provider.

OPS ACTION (operator): re-set `CLAUDE_CODE_OAUTH_TOKEN` cleanly — single line, no wrapping — e.g. `gh secret set CLAUDE_CODE_OAUTH_TOKEN` with a carefully-piped value. Consider also setting `ANTHROPIC_API_KEY` as a failover. In-repo hardening shipped in this session: token sanitization in `engine/llm_auth.py` `build_providers()` (whitespace-collapse + printable-ASCII validation with warnings) and a fix in `cortex.py` run_status stamping so degraded runs keep the staleness/retry gate open. The prior silent-failure path saved `last_run_state.json` on degraded runs, defeating the #1722 retry logic; the stale state file was deleted.

**Seam corrections found by the census.** Four §2 claims did not hold and were fixed or recorded:

1. RF-13 timestamp check (`spec_ref` registration timestamp ≥ `registered_at`) was docstring-only — now enforced as a warn-and-flag in `engine/research_factory/adapter_cortex.py`.
2. Ingest did NOT auto-set `candidate_type='cortex_hypothesis'`. It defaulted to `external_idea`, which would have taken the `rf_family` accounting path and double-counted the shared cortex trial family. Fixed: adapter now auto-types incoming cortex rows as `cortex_hypothesis` with `trial_accounting.mode='cortex_shared'` and requires a `spec_ref`.
3. No status projection map existed. Raw metabolism vocabulary was passed through; factory states are a different vocabulary. Fixed: a mapping was added per RF-2 (`registered`→`screened`, `insufficient-n`→`awaiting_data`, `failed`→`numeric_rejected`, `passed`→`screened`). Note `screened` means challenge-eligible; the projection never promotes.
4. DOC CORRECTION: §2's claim that the factory reads `TrialLedger().effective_n('cortex')` was aspirational — nothing in Batch B mechanics actually needs it. Recorded as a doc correction; no build (ruling R5).

**Fable rulings:**
- R1: Challenge only evaluator-passed rows plus any Fable-nominated rows. Skip `registered`/`insufficient-n` rows with no verdict.
- R2: Cortex lens added as `research/research_factory/CHALLENGER_PROMPT.md` Lens 6 (this session). CODEOWNERS tracking deferred to W-CODEGEN per charter RF-16.
- R3: Cortex budget stays 3/week — reaffirmed. No raise before the funnel has kill-rate evidence.
- R4: Ingest auto-typing required and shipped pre-trigger.
- R5: `TrialLedger().effective_n('cortex')` reference in §2 is a doc correction; no build needed for Batch B mechanics.
- R6: Trigger-unblock hardening shipped (llm_auth sanitization + cortex.py staleness fix). Ops action flagged separately.

**Visibility.** No new watch infrastructure is needed. `engine/experiments_registry.py` already auto-injects `machine_registry.jsonl` rows into the admin Experiments tab (`hook='cortex_evaluator'`) with `ready=True` and an alert on `passed`/`gate_open` verdicts. The trigger will surface itself in the operator's existing alert surface once registrations begin.

**Come-back: 2026-08-03.** If `data/neuralweb/machine_registry.jsonl` is still absent by then, the cortex pipeline is still broken and the ops action needs escalation. If rows exist, proceed with §3 as written.
