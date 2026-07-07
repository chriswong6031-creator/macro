# Research Factory Cortex Batch B — Infrastructure Judgment, LLM-Auth Boundary

**Source:** PR #1731 (conformance hardening + rulings + ARMED status). Primary doc: `research/RF_CORTEX_BATCH_FOR_FABLE.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

The Research Factory's Batch B involves wrapping graded cortex hypotheses with challenge packets and factory human review. Before Batch B could trigger, a census of all binding seams was run to verify the factory's cortex integration was correctly wired. Four seam failures were found; rulings R1–R6 were recorded. The question was also: how should the cortex-specific factory path be hardened against LLM-auth boundary violations and double-counting?

## What was decided (the holding)

- **R1:** Challenge only evaluator-passed rows plus Fable-nominated rows. Skip `registered`/`insufficient-n` rows with no verdict.
- **R2:** Cortex lens added to `research/research_factory/CHALLENGER_PROMPT.md` as Lens 6. CODEOWNERS tracking deferred to W-CODEGEN (separate program).
- **R3:** Cortex budget stays 3/week — reaffirmed. No raise before the funnel has kill-rate evidence (this matches the original factory charter's RF-3).
- **R4 (RF-13 timestamp check):** the seam claiming that `spec_ref` registration timestamp ≥ `registered_at` was enforced was docstring-only; now enforced as a warn-and-flag in `engine/research_factory/adapter_cortex.py`.
- **R5 (doc correction):** the claim that the factory reads `TrialLedger().effective_n('cortex')` was aspirational; no build needed — Batch B mechanics don't require it.
- **R6 (trigger-unblock hardening — read-only adapter, no registry write):** `engine/llm_auth.py` gains token sanitization in `build_providers()` (whitespace-collapse + printable-ASCII validation); cortex.py run_status stamping fixed so degraded runs keep the staleness/retry gate open. The prior silent-failure path saved `last_run_state.json` on degraded runs, defeating the retry logic.
- **Ingest auto-typing fixed:** the adapter now auto-types incoming cortex rows as `cortex_hypothesis` with `trial_accounting.mode='cortex_shared'` and requires a `spec_ref`. Without this fix, cortex candidates defaulted to `external_idea`, took the `rf_family` accounting path, and would double-count the shared cortex trial family (named trap, RF-6).
- **Status projection map added:** raw metabolism vocabulary is mapped to factory vocabulary (e.g., `registered→screened`, `passed→screened`); the projection never promotes.
- **Shared cortex trial family (`'cortex'`) strictly preserved:** the factory NEVER creates a new `rf.cortex.*` family; an `rf.cortex.*` family would double-count the metabolism-issued cortex budget. This is a named anti-pattern enforced by the adapter.
- **Self-reference exclusion (`_SELF_LEDGER_EXCLUSIONS`):** any `spine_query` referencing `cortex_attention` is blocked at registration, grading, and ranking — the three-layer self-grading exclusion is re-checked before attaching firings evidence.
- **One-night cross-job lag accepted:** cortex job commits AFTER the engine job; factory reads prior night's registry. Documented in the adapter docstring as an accepted limitation.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Enforce timestamp check (warn-and-flag) | infrastructure hardening | **T0** (ROUTINE) | Opus alone |
| Fix ingest auto-typing (double-count prevention) | bug fix with audit artifact | **T0** (ROUTINE) | Opus alone |
| Add status projection map | adapter-layer change | **T0** (ROUTINE) | Ops; no packet required |
| Affirm cortex budget stays 3/week | budget policy reaffirmation | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| LLM-auth hardening (token sanitization) | ops/security infrastructure | **T0** (ROUTINE) | Opus alone |
| Cortex lens in challenger prompt | display doc change | **T0** (ROUTINE) | Opus alone |

The budget reaffirmation (R3) is T1 because it touches ops-budget policy; all other decisions are T0 mechanical hardening.

## Lenses that did the work

- **Authority:** the LLM-auth boundary is the most critical lens here. The cortex adapter must never write `machine_registry.jsonl`, never call `stake_hypothesis`, never bypass the 3/week metabolism chokepoint (RF-13 cortex seam). These are Article-1-adjacent — the factory ceiling is A0–A2; cortex origination of a registration would violate that ceiling.
- **Statistics:** double-counting via `rf.cortex.*` family creation is the statistical anti-pattern. The shared `'cortex'` family in `TrialLedger` is the correct accounting; any factory-issued sub-family would inflate the declared budget and undercount effective multiplicity.
- **Build feasibility:** the census found that the cortex LLM loop was failing with HTTP 401 then "Connection error" — the root cause was a corrupted `CLAUDE_CODE_OAUTH_TOKEN` secret (likely internal line-wrap). The hardening shipped regardless of trigger timing; the ARMED status documents an ops action pending (operator must re-set the secret cleanly).
- **Ops budget:** Batch B is expected to be small (mostly OPERATING existing machinery); the cortex adapter projects registry status and attaches graded verdicts as screen artifacts. It evaluates nothing, scores nothing.

## Citable holding

Factory infrastructure for an LLM-adjacent pipeline requires mechanical enforcement (not docstring honor-system) at every boundary where double-counting, self-reference, or authority escalation could silently occur; a ARMED status with a named ops action is the correct output when mechanical hardening is complete but an external credential block prevents the trigger from firing.

## Ruling IDs

R1 (challenge scope), R2 (cortex lens), R3 (budget reaffirmation), R4 (timestamp enforcement), R5 (doc correction), R6 (trigger hardening); RF-3, RF-6, RF-13 (cortex seam)
