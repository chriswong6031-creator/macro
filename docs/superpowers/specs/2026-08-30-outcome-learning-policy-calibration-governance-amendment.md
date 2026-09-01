# Outcome Learning & Policy Calibration — Governance and Evidence Amendment

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO  
**Operation:** `mastermind-outcome-learning-policy-calibration-20260830-sol-001`  
**Protected procedure re-pin:** `mastermindx-market-intelligence/Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1 compatible.  
**Status:** **BINDING ARCHITECTURE AMENDMENT / RECORDS ONLY.** This document creates no experiment, assignment, Job, Attempt, Worker, event, route, policy effect, runtime mutation, or authority.

## 1. Precedence and narrow supersession

This amendment binds the Outcome Learning program and supersedes only the following parts of the original architecture and plan where they imply a different sequence:

- the relationship between the original design §§11.2, 11.4, 11.6 and bounded waves OL-5/OL-6;
- the original implementation-plan Task 5 and Task 6 sequence;
- any wording that could be read to permit randomized treatment before an explicit policy decision authorizes the canary;
- any wording that could be read to permit the baseline arm to dispatch a handoff that fails current mandatory handoff law;
- any wording that calls a synthetic fixture a real historical study.

All other owner boundaries, evidence grades, time/correction semantics, privacy rules, no-rebuild laws, downstream proof requirements, and the final 10/10 completion ruler remain controlling.

The durable ruling is also recorded as `DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE`.

## 2. Finding: a canary is already a policy intervention

Randomly assigning eligible operations between two handoff procedures changes organizational behavior even when the candidate is reversible and low risk. Therefore, running the canary is not merely measurement infrastructure. It requires an explicit authorization decision **before the first treated assignment**.

Independent review after observing the results remains necessary but is a different decision. One post-hoc promotion DEC cannot retroactively authorize the experiment that generated its evidence.

The accepted sequence is consequently a **two-decision gate**:

```text
instrumentation and no-effect shadow
-> prospective baseline/maturity evidence
-> independent pre-canary protocol review
-> PRE-CANARY AUTHORIZATION DEC
-> bounded randomized canary
-> terminal + delayed outcome compilation
-> independent post-canary study review
-> POST-CANARY POLICY DEC
-> owner-native rollout or rollback
-> production and delayed proof
```

No statistical artifact, compiler output, validator result, PR merge, or Sol prose substitutes for either DEC.

## 3. Gate A — pre-canary authorization DEC

Before OL-5 may alter which lawful handoff procedure an operation receives, an ordinary Agent OS decision must choose exactly one of:

- `AUTHORIZE_BOUNDED_CANARY`
- `HOLD_FOR_REPAIR`
- `REJECT_CANARY`

`AUTHORIZE_BOUNDED_CANARY` is valid only when the decision names and cites:

1. exact treatment and baseline definitions;
2. the shared mandatory legality/admission gate applied to both arms;
3. eligible and excluded operation classes;
4. randomization unit, blocks/strata, assignment probabilities, and sealing time;
5. estimand and intention-to-treat analysis;
6. primary outcome, secondary outcomes, delayed horizon, and metric versions;
7. minimum evidence or valid sequential boundary;
8. missingness, censoring, correction, noncompliance, and attrition handling;
9. severe-harm and ordinary guardrail stop thresholds;
10. privacy, aggregation, access, and retention boundaries;
11. rollback mechanism and the exact owner that can perform it;
12. maximum episode/time envelope and stop condition;
13. independent reviewer identity or responsibility and its accepted protocol verdict;
14. explicit statement that the canary grants no route, worker, merge, source-law, or automatic promotion authority.

Missing any required item means `HOLD_FOR_REPAIR`, not implicit authorization.

## 4. Gate B — post-canary policy DEC

After the predeclared terminal and delayed horizons mature, an independent reviewer must examine assignment integrity, treatment fidelity, inclusion/exclusion, missingness, correction lineage, estimator use, uncertainty, sensitivity, Goodhart risk, and every guardrail.

Only then may a second ordinary Agent OS decision choose:

- `PROMOTE_BOUNDED`
- `CONTINUE_CANARY`
- `HOLD`
- `ROLLBACK`
- `REJECT`

This second DEC is the only organizational policy-promotion ruling. The study recommendation remains advisory. `PROMOTE_BOUNDED` still requires an owner-native rollout, reversible production canary, production proof, and delayed consequence read in OL-7.

## 5. Both experimental arms must already be lawful

The baseline is **not** permission to send an incomplete or noncompliant handoff. Before randomization, every candidate episode must pass the same current canonical handoff legality and completeness admission, including all required authority, mission, scope, non-goals, proof, stop, return, pickup-ACK, separate-START, and dialogue-close obligations.

The two arms are:

- **Baseline:** a handoff that has already passed canonical admission and is executed through the current compliant manual procedure.
- **Candidate:** the same canonically admitted handoff plus the reviewed deterministic machine preflight and mission checksum.

The candidate preflight may detect a defect missed by the shared admission path and may stop dispatch with a typed reason. It may not waive a mandatory field, choose a worker, select another carrier, alter authority, or dispatch a malformed packet. The baseline arm may not bypass the shared admission gate merely to manufacture contrast.

Randomization occurs only after:

1. canonical legality/completeness admission;
2. study eligibility admission;
3. action-time source and policy snapshot;
4. assignment probability sealing.

This protects subjects and preserves a meaningful estimand: the incremental effect of the machine preflight on already-lawful handoffs, not the effect of compliance versus noncompliance.

## 6. No-effect shadow and pilot boundary

Before Gate A, OL-4 may perform instrumentation-only work that cannot change a worker-visible packet, recipient, carrier, START decision, execution path, or policy result.

Permitted pre-canary work includes:

- computing both hypothetical arms without exposing the candidate;
- validating event identity, duplicate handling, timestamps, metric definitions, owner refs, redaction, maturity, correction, and missingness;
- collecting prospective baseline episodes under the unchanged operating policy;
- compiling `DESCRIPTIVE_ONLY` or `NOT_IDENTIFIED` readiness studies;
- estimating baseline event rates, clustering, delayed maturity, attrition, and feasible evidence envelopes.

Any pilot that changes the worker-visible handoff or dispatch outcome is treatment and therefore remains behind Gate A. Instrumentation or pilot episodes used to repair measurement are excluded from the promotion estimand unless the preregistration explicitly and prospectively says otherwise.

## 7. Revised bounded-wave sequence

The program sequence is now:

### OL-0 — architecture and causal boundary

Records-only architecture, this amendment, the architecture DEC, causal-limit DSC, and execution plan. No runtime behavior.

### OL-1 — semantic registration

Register `organizational-learning` and create `WS:OUTCOME-LEARNING-POLICY-CALIBRATION` after current semantic-registry path ownership is reconciled. No compiler or runtime effect.

### OL-2 — pure contracts and deterministic compiler

Build immutable expectation/evidence/study contracts and deterministic fixture compilation. No live owner reads or policy effect.

#### OL-2a — minimal prospective-capture contract (2026-09-01, CCL reconciliation amendment §B)

Sub-line of OL-2, not a new wave number. The receipt-contract subset of OL-2 (schema, sealing, and validation for `mastermind.decision_expectation_receipt.v2`, no compiler/study dependency) must be protected before the first CCL-A3 effect. See the CCL reconciliation amendment §A.3–A.4 for the CCL-A3 gate this sub-wave exists to satisfy.

### OL-3 — owner evidence and real descriptive study

Build read-only owner adapters and compile one historical study from exact owner-native exports or committed receipts. The study remains `DESCRIPTIVE_ONLY` or `NOT_IDENTIFIED`.

### OL-4A — owner-native expectation capture

Record sealed ex-ante expectations in existing Executive/Agent OS owner paths. No exploration.

### OL-4B — no-effect shadow instrumentation

Compute hypothetical baseline/candidate arms and write/read only through the existing reviewed evidence/event plane, while proving zero worker-visible or policy effect.

### OL-4C — prospective baseline and maturity corpus

Collect real unchanged-policy episodes and delayed outcomes sufficient to evaluate measurement completeness, baseline rate, clustering, maturity, attrition, and canary feasibility.

### OL-4D — descriptive readiness study

Compile and independently review a readiness report. It may recommend a canary protocol; it cannot authorize one.

#### OL-4E — executive-memory efficacy benchmark (2026-09-01, CCL reconciliation amendment §G)

Sub-line inserted between OL-4D and OL-5A, not a renumbering of either. Empirical, non-psychological self-model for the logical office across at least three benchmark arms (memory-light reasoning, naive memory injection, anti-anchored two-pass memory); never a universal CEO/worker/model score. Memory is promoted for use only on measured decision improvement with no hidden quality regression.

### OL-5A — independent protocol review and pre-canary DEC

Review the exact protocol and issue Gate A. No treated assignment exists before `AUTHORIZE_BOUNDED_CANARY`.

### OL-5B — bounded controlled canary

Run only the authorized intervention, within the exact episode/time envelope, with action-time propensities, intention-to-treat analysis, stop rules, and rollback.

### OL-6 — independent outcome review, DSC, and post-canary DEC

Review matured evidence, preserve one falsifiable learned consequence as DSC, and issue Gate B.

### OL-7 — owner-native policy application and delayed production proof

Apply only an authorized bounded delta, prove the real path and rollback, and close only after delayed benefit and guardrail evidence mature.

Worker/model routing remains a later consumer behind separate prospective support and separate authority.

## 8. Real evidence versus test fixtures

OL-3 must distinguish these artifacts:

- **Synthetic fixture:** invented data used to test validation, determinism, missingness, correction, and causal-grade refusal. It is never called a real operating study.
- **Redacted immutable capture:** a bounded committed representation derived from cited owner-native exports/receipts, with exact source refs, cutoffs, hashes, redaction method, and correction generation. It may support a real descriptive study when rights and access rules permit.
- **Owner-native export/receipt:** the canonical or explicitly approved read-only evidence source.

A command reading `tests/fixtures/...` supports a real study only when the fixture is documented as a redacted immutable capture of exact owner evidence and its provenance is machine-verifiable. Otherwise the output is a test study only.

No raw unrestricted Slack transcript, private chain of thought, credentials, tokens, or secret-bearing account payload may be copied into a study fixture.

## 9. Dynamic owner and path reconciliation

PR numbers and historical counts in the original plan are audit anchors, not permanent gates. Every wave must re-read current default branches, current semantic counts, current open PRs, exact changed paths, current owner/source-law records, and actual successor carriers.

Do not chase unrelated render/data commits by habit. Do rebase or merge current source when a material owner, schema, generator, validator, or authority path changed. `EFFECT_UNKNOWN` blocks failover or duplicate submission.

The OL-1 expected changed-file count must be derived from its exact current plan and current owner reconciliation; stale prose saying “five files” cannot justify an extra path or hide a missing one.

## 10. Capability-state and completion honesty

Architecture-time claims that a substrate is `PROVEN_LIVE` are evidence anchors for that owner, not proof that its Outcome Learning adapter or end-to-end learning use is live. Each wave must separately classify:

- owner substrate availability;
- adapter implementation;
- adapter production proof;
- compiled-study correctness;
- policy authority;
- policy rollout and delayed effect.

OL-0 merge remains `SPEC_ONLY / RECORDS_ONLY`. OL-2 code can be at most `BUILT_NOT_PROVEN` until a real owner/evidence consumer is proven. A green canary implementation without mature randomized evidence is not policy learning. The program is complete only at the original 10/10 ruler.

## 11. No-rebuild and authority boundary

This amendment creates no new outcome store, experiment registry, identity plane, lifecycle, queue, watcher, retry plane, assignment authority, route authority, worker leaderboard, hidden utility score, or self-modifying law.

Executive OS remains lifecycle and execution-event owner. Agent OS remains durable decision/discovery/workstream owner. GitHub remains implementation and proof owner. Existing Dialogue/Wake, Provider Control, Router, Linear, Slack, Portfolio, Market, and Eval owners retain their boundaries.

The architecture may be changed again only through an explicit superseding decision that preserves current Chairman intent and owner law.