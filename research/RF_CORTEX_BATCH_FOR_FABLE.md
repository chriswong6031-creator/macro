# Research Factory — Cortex Batch (Batch B) (program seed, for a future Fable session)

**Status:** NOT STARTED — deferred because `data/neuralweb/machine_registry.jsonl` has ZERO registrations to date (verified 2026-07-06; the file does not exist). The factory's cortex adapter is BUILT and merged (`engine/research_factory/adapter_cortex.py`, #1581) and is absent-file-safe — there is simply nothing to wrap yet.
**Prepared:** 2026-07-06 by the Fable session that built the factory (charter: `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`, W0–W7 COMPLETE).
**Trigger to start:** machine_registry has ≥1 hypothesis with an evaluator verdict (`passed` / `insufficient-n` trending, or anything Fable wants challenged). Watch: cortex just received provider-failover honesty fixes (#1625), so registrations may begin; the weekly budget is 3 (hard, server-side, ISO week Mon–Sun in `engine/neuralweb/metabolism.py`).

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
