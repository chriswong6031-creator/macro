# Outcome Learning — Executive Memory and CCL Reconciliation Amendment

**Date:** 2026-09-01
**Owner:** Fable COO (bounded repair authority; see Repair authority chain below)
**Operation:** `mastermind-outcome-learning-policy-calibration-20260830-sol-001`
**Repair authority chain:** Chairman transfer op `mastermind-agent-evaluation-fable-coo-end-to-end-20260901` → Slack ruling `SOL REQUEST_REPAIR / CONTINUE` ts `1788144551` (6 points) → GitHub review `5061735318` (blockers A–E, verdict `REQUEST_CHANGES` on exact head `29518b3cfad719226db0444ccb4d92a3626b07c9`).
**Status:** **BINDING ARCHITECTURE AMENDMENT / RECORDS ONLY.** This document creates no Executive Learning/Chairman Memory program, database, Agent OS record type, graph authority, RAG plane, leaderboard, lifecycle, queue, self-editing policy, OL-1/OL-2 START, canary, policy effect, or code. It repairs the same carrier, branch and PR the review evaluated; it does not fork or replace them.

## 1. Precedence and narrow supersession

This amendment binds the Outcome Learning program and is **controlling** over the 2026-08-30 design, implementation plan, and governance amendment where they conflict. All else in those three records — owner boundaries, evidence grades, time/correction semantics, privacy rules, no-rebuild laws, the two-decision canary gate (`DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE`), downstream proof requirements, and the final 10/10 completion ruler — remains controlling and unchanged.

This amendment closes GitHub review `5061735318` blockers A–E on exact head `29518b3cfad719226db0444ccb4d92a3626b07c9`. It is a narrow correction, not a redesign: the selected federated Outcome Compiler and reviewed policy-calibration architecture remain the sole organizational-learning carrier.

---

## §A Canonical ownership and CCL reconciliation (closes BLOCKER A / review points 1–2)

### A.1 Canonical owner

`organizational-learning` (this program) is the **canonical owner** of GENERIC organizational-learning and executive-experience methodology and contracts:

- expectation/outcome semantics;
- decision-quality-vs-luck adjudication;
- assumption/falsifier semantics;
- memory admission/application/poisoning/correction/replay law (§D);
- retrieval-discipline law (§F);
- self-model and memory-efficacy benchmark methodology (§G).

### A.2 CCL-A4 is a consumer, not a second owner

CCL-A4 (Chairman Cognition Loop strategic learning) is a **consumer/application** of the contracts owned above. It is not a second memory store, schema authority, retriever, graph, evaluator, or promotion plane. CCL may hold Chairman-cognition domain content (the substance of what the Chairman thinks about); its *learning semantics* — how a lesson is admitted, sealed, resolved, applied, corrected, retrieved, or benchmarked — come from `organizational-learning`.

### A.3 Sequencing correction (hindsight-contamination fix)

The originally reviewed CCL sequence (`CCL-A2 -> CCL-A3 live canary -> prediction/outcome review -> CCL-A4`) let the first CCL canary begin before any decision-time contract existed, which is hindsight-contaminated capture and is forbidden.

Corrected sequencing:

- A minimal sealed prospective expectation/assumption receipt (per §B/§C) **MUST exist before the first CCL-A3 effect**.
- CCL-A3 need not wait for randomized OL-5 (the handoff-quality canary is a separate, later, unrelated intervention).
- With only the minimal §B/§C receipt in place, CCL-A3's learning grade ceiling is `DESCRIPTIVE_ONLY` (decision-calibration learning only; no causal claim about CCL-A3's own effect is licensed by that receipt alone).

### A.4 Binding cross-program requirement

Before CCL-A3 START, the CCL program's canonical carrier must adopt the corresponding narrow correction: an ownership acknowledgment of A.1–A.2 above, plus the pre-effect sealed receipt requirement of A.3. This obligation is **owed on the CCL side**; this record only states and binds the requirement from the Outcome Learning side and does not itself edit any CCL/Mastermind carrier.

### A.5 CCL carrier migration record (verbatim, for audit continuity)

The review's binding reference to Mastermind PR #284 names a carrier that has since moved. Recorded verbatim as of this amendment's authoring:

- `CCL-A1` decision contract PR #284 — CLOSED → re-carried and MERGED as PR #309 (2026-09-01).
- `CCL-A2` PR #311 — OPEN [RELEASE].
- `CCL-A4-canary` PR #292 — OPEN/STACKED/DRAFT.

The review's "#284" requirement (A.4 above) therefore binds the CCL program's live/future carriers — currently #309/#311/#292 and their successor CCL-A3 START gate — not the closed PR number. A.4 does not change with further CCL PR renumbering; re-read the CCL program's canonical carrier at CCL-A3 START time rather than trusting this list to stay current.

---

## §B OL-2a minimal prospective-capture contract (sequencing; closes BLOCKER A.3 / review point 2)

Task 2 / Wave OL-2 (pure contracts and deterministic compiler) is split into two parts:

- **`OL-2a`** — the pure contract subset: schema, sealing, and validation for the extended `mastermind.decision_expectation_receipt.v2` receipt (§C), with **no compiler/study dependency**. `OL-2a` must be protected — implemented and available — before the first CCL-A3 effect (per §A.3).
- **OL-2 remainder** — the deterministic compiler (`compile_outcome_study`, `StudySpec`, evidence-grade admission, etc.) and everything else already specified for OL-2 — unchanged, and not required before CCL-A3.

This is a boundary split within the existing OL-2 wave, not a new wave number and not a reordering of any other wave. Governance §7's wave list gains an `OL-2a` sub-line under OL-2 (§7 revision below); the plan's Task 2 gains an explicit Task 2a boundary (update hook below). No other wave is renumbered.

---

## §C Receipt extension v1→v2 (closes BLOCKER B / review point 3)

`mastermind.decision_expectation_receipt.v1` semantics (design §7.1) are preserved **verbatim** as a strict subset. The extended schema is:

```text
mastermind.decision_expectation_receipt.v2
```

v2 adds these closed fields on top of the unchanged v1 fields:

- **`assumptions[]`** — explicit assumptions made at decision time:
  `{assumption_id (stable), role: LOAD_BEARING|CONTEXTUAL, statement, evidence_refs[], ex_ante_confidence (probability or null + null_reason), falsifier}`.

- **`assumption_resolutions[]`** — appended **post-outcome** by the outcome study; it **never mutates the sealed receipt** (supersession/link semantics identical to v1 §7.2 — a correction creates a new revision linked by `supersedes`, it never backdates or overwrites the sealed record):
  `{assumption_id, resolution: HELD|FALSIFIED|UNRESOLVED|NOT_TESTED|CONFOUNDED, evidence_refs[]}`.
  Resolution is never forced binary success/failure; all five states — `HELD`, `FALSIFIED`, `UNRESOLVED`, `NOT_TESTED`, `CONFOUNDED` — are first-class and may co-occur across an assumption set.

- **`memory_exposure`** — what durable memory the decision actually consulted:
  `{pre_memory_option_set_digest, final_option_set_digest, final_decision_digest, consulted[]: {record_ref (DEC/DSC/source-law), influence: MATERIALLY_CHANGED|CONSULTED_NO_CHANGE|REJECTED_INAPPLICABLE, why}, source_packet_digests[]}`.

No private chain of thought may enter any v2 field; the receipt grants no authority (unchanged from v1); every V1 durable learning artifact carrying a v2 receipt requires `PUBLIC_SAFE` classification per §E.

This closes design §7 without rewriting the frozen v1 JSON block — see the design.md update hook below, which adds only a pointer paragraph, not an edit to the v1 example.

**Study-side field mapping (review closure, 2026-09-01):** blocker B's study-side bullet asked for separate process-quality, forecast, realized-consequence, attribution/confounding, and regret/counterfactual fields on the compiled study. Process-quality, forecast, realized-consequence, and attribution/confounding separations are already satisfied by the unamended design — no new field is needed: design §9's decision-process-quality/forecast-calibration/realized-consequence separation law, design §8.1's sensitivity-analysis and known-unmeasured-confounders fields, and v1's `known_confounders` field already carry these. Regret/counterfactual quantities are the one bullet item not yet built; they are an explicitly **DEFERRED** optional study field for OL-4D, permitted only under the reviewed, explicit utility model that design §9 already mandates before any expected-utility, regret, or cost-benefit number may be computed ("the compiler may not invent hidden weights that collapse quality, speed, cost and risk into one score"). This is a deliberate deferral pending that utility-model review, not an omission from this amendment's scope.

---

## §D Memory admission, application, poisoning, correction, and replay law (closes BLOCKER C / review point 4)

- **Admission:** untrusted prose (Slack/email/web/worker/model) never becomes durable executive memory directly. It must pass canonical evidence/outcome adjudication and the existing DSC falsifiable + load-bearing gates before it can inform a future decision as memory.

- **Application:** a valid historical DEC/DSC is evidence, not current truth or procedure. Its scope, supersession, applicability, source state, and authority must be checked at retrieval/effect time, not assumed from its existence.

- **Frozen inequalities (verbatim, binding on every future memory consumer):**

  `REMEMBERED_ACTION != AUTHORIZED_ACTION`
  `REMEMBERED_SUCCESS != CURRENT_PROCEDURE`
  `REMEMBERED_TOOL_SEQUENCE != REPLAYABLE_EFFECT`

  A memory record showing that an action was once taken, that it once succeeded, or the exact steps once used never by itself authorizes taking that action again, never substitutes for checking current procedure, and never licenses replaying the same tool sequence for effect.

- **Poisoning and correction:** when a DSC/DEC premise is corrected or superseded, derived downstream lineage is flagged `MEMORY_PREMISE_INVALIDATED`. This flag is informational only — there is no automatic reversal and no automatic policy edit. A human/Sol-reviewed decision remains required to act on an invalidated-premise flag; the flag is supersession bookkeeping, not a rewrite of history.

- **Replay:** a historical replay (of a decision, a session, an action) contains only information available at the frozen cutoff of the record being replayed. Memory never authorizes or replays an effect on its own — replay is read-only reconstruction for review, never an execution path.

---

## §E PUBLIC_SAFE law (closes review point 6 / review §C tail)

V1 durable learning artifacts written to current public repositories (Macro, Mastermind) must be explicitly classified `PUBLIC_SAFE`. Restricted/unknown material, private human context, credentials, raw prompts/transcripts, and secret-bearing provider/account data **fail closed** — they are excluded from the artifact rather than entered into public Git history, even redacted. An artifact whose classification is unresolved is treated as not `PUBLIC_SAFE` and is withheld.

A future private physical partition (for material that can never be `PUBLIC_SAFE`) requires a separate authority/security ruling; it is not created by this amendment. Such a partition, if ever authorized, remains one logical Agent OS/CXI architecture — it does not become a second memory system with its own admission, correction, or retrieval law; §D and §F still govern it.

---

## §F Retrieval and negative-transfer law (closes BLOCKER D / review point 5)

Macro Context Index (CXI) remains the **only** retrieval plane. This amendment creates no memory RAG service and no graph authority.

Future retrieval law (binding on any later retrieval consumer, not built by this records-only amendment):

1. Major ambiguous decisions perform a memory-light first pass from current truth alone.
2. A second pass receives source-attributed precedents.
3. The delta between the two passes records what memory changed and what analogy was rejected.
4. An audit checks the delta for anchoring and negative transfer.

Retrieval must deliberately surface supportive analogues **and** failures, contradictions, superseded beliefs, rejected alternatives, and relevant self-calibration — not merely highest similarity. Omissions are named explicitly rather than silently dropped, and every surfaced item is cited under existing Agent OS/CXI law.

A derived relationship view (later, not built here) may expose entity/temporal/evidential/semantic edges, carrying one of three provenance classes: `CANONICAL_DECLARED`, `DETERMINISTIC_DERIVED`, or `MODEL_INFERRED`. `MODEL_INFERRED` edges have **zero authority** — they may be shown but never treated as ground truth. A dedicated graph engine or embeddings-based retrieval enters only after a measured benchmark win over the CXI baseline (per §G's benchmark discipline). GNN-based policy authority is explicitly out of scope.

---

## §G Executive self-model and memory-efficacy benchmark (closes BLOCKER E / review point 5 tail)

A later wave, **`OL-4E` — executive-memory efficacy benchmark**, is added to the sequence between OL-4D and OL-5A (governance §7 revision below; plan gets a stub task, update hook below).

OL-4E's eventual scope: an empirical, non-psychological self-model for the logical office, partitioned by decision class/domain/ambiguity/blast radius/topology/model-surface cohort where known. It exposes forecast calibration, time-to-evidence bias, intervention classes, rework classes, assumption-failure patterns, and topology outcomes, always with sample size/coverage/uncertainty attached. It is **never** a universal CEO/worker/model score.

Benchmark arms (minimum three):

- memory-light reasoning (no historical retrieval);
- naive memory injection (highest-similarity retrieval, no discipline);
- anti-anchored two-pass memory (the §F future retrieval law).

Measured dimensions: option diversity, correct precedent use, stale/superseded-memory refusal, premise awareness, negative transfer, poisoning resistance, calibration, Chairman intervention, rework, correctness, time/context cost, and cross-model portability. Memory is promoted for use only on a measured decision improvement across these dimensions, with no hidden quality regression on any of them — the same promotion discipline as the two-decision canary gate (`DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE`), applied to memory retrieval rather than handoff policy.

---

## Non-goals (verbatim force, from the repair ruling)

This amendment does not create: a new Executive Learning/Chairman Memory program, database, Agent OS record type, graph authority, RAG plane, leaderboard, lifecycle, queue, or self-editing policy. It does not start OL-1 or OL-2, arm a canary, cause a policy effect, or ship code. It makes no edits to the Mastermind repository, Mastermind PR #299, Mastermind PR #162, or any CCL carrier (PR #309, #311, #292, or their successors). The DSC file `agentos/discoveries/DSC-HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED.md` is untouched by this amendment and by this repair.

## Capability state

This amendment is `SPEC_ONLY / RECORDS_ONLY`, identical to the OL-0 architecture it amends (per governance §10's capability-state honesty rule). It changes what a later OL-1..OL-7 wave must build; it builds nothing itself.
