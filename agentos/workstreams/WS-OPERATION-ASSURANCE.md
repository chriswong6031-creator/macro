---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Mastermind Operation Assurance (OLS) — liveness/soundness checker to full production
objective: >
  A Program CEO or machine admission consumer can submit a proposed or running operation,
  receive a deterministic source-attributed liveness/soundness assessment with the shortest
  actionable counterexample or valid-wait explanation, see it in the existing Control Room,
  and observe a real report-only canary changing an operational decision — without a second
  lifecycle, source, authority, retry, status, or observability plane.
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat), Sol retains architecture + release acceptance
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: R0, title: "Recover canonical truth; protect OLS-F0 architecture/source law (PR 279)", status: done, pr: 279}
  - {id: A1, title: "Pure deterministic assurance engine + immutable report + report-only CLI (PR 324)", status: done, pr: 324}
  - {id: A2, title: "Canonical Agent OS source compilation through the protected Executive Steward", status: in_progress, pr: [339, 362], next_action: "Sol must review the exact current PR 362 head against protected A2 design 339, B1-B4 repairs, current-base CI and this exact corrected Agent OS revision; if clean, release A2, otherwise commission only the smallest same-carrier repair. The attempted fable-004 placement ended pre-START with effect NONE and is not an active receiver."}
  - {id: A3, title: "Correction-safe current applicability + evidence-preserving summary", status: todo, depends_on: [A2], next_action: "After A2 protection, derive current applicability and an evidence-preserving summary without mutating any historical report."}
  - {id: A4, title: "Control Room experience over real data", status: todo, depends_on: [A3], next_action: "After A3, project the report-only assurance result into the existing Control Room with real data, degraded states and browser proof."}
  - {id: A5, title: "Report-only real canary + calibration", status: todo, depends_on: [A4], next_action: "After A4, run a supervised report-only canary and calibrate false positives, false negatives and decision usefulness without admission effects."}
  - {id: A6, title: "Runtime conformance shadow path", status: todo, depends_on: [A2], next_action: "After A2 protection, compare authored-model expectations with existing runtime evidence through a read-only conformance shadow; do not create runtime truth."}
  - {id: A7, title: "Admission integration, calibrated default-off promotion", status: todo, depends_on: [A5, A6], next_action: "After accepted A5 and A6 evidence, implement a separately reviewed default-off admission projection; no verdict may grant authority or originate retry."}
  - {id: A8, title: "Production installation, rollback drill, runbook, learning loop", status: todo, depends_on: [A7], next_action: "After A7 acceptance, install the bounded production path, prove rollback and cleanup, publish the runbook, and establish the correction-safe learning loop."}
next_action: >
  Complete exact-head CEO review of Mastermind PR #362. Require current protected master ancestry,
  the exact OLS-A2 source/compiler/CLI/fixture/test path family, terminal hosted proof, no unresolved
  review thread, and a real compilation of this exact protected Macro revision through owner-native
  bytes -> protected Executive Steward -> pure compiler -> protected A1 checker/report. The prior
  fable-004 child `mastermind-operation-assurance-a2-source-compiler-20260902-fable-004` is terminal
  pre-START with effect NONE after its canonical packet was absent; it is not a continuation target.
  If PR #362 is clean, release A2 as BUILT_NOT_PROVEN / REPORT_ONLY / PRODUCTION_INERT. Otherwise
  commission only the smallest repair on that existing branch. Do not start A3+.
do_not_redo:
  - "Do not re-diagnose the false-green Slack RESULT sequence on the parent carrier: R0 and A1 were re-landed for real; GitHub is implementation/evidence truth."
  - "repair_scope is ruled out of the F0/A1 wire and pinned by exact-tuple tests; do not reintroduce it."
  - "Do not build a gather layer inside the pure A1 checker or a second Steward/federated reader; A2 must reuse the protected Executive Steward."
  - "PROPER_COMPLETION overlapping-terminal ownership is INTERSECTION; do not revert to union."
  - "Do not present PR #362's synthetic corrected fixture or an unprotected Macro branch as the required real positive source proof."
  - "Do not infer CURRENT_SOURCE_ATTESTED, whole-operation completeness, finite-model proof or REPORT_ONLY_PROCEED from Agent-OS-only evidence."
  - "Do not reuse terminal fable-003 or fable-004 dialogue state as authority for a repair or next wave."
landmines:
  - "Mastermind master requires up-to-date branches and allows squash merge only; reconcile by history-preserving merge, never rebase/reset/force."
  - "Several OLS-F0 contract tests are document-parity greps; green prose parity is not engine or production proof."
  - "This corrected workstream revision is owner-native organizational evidence only. It does not author Executive lifecycle, runtime, Wake, Capacity, GitHub or action-target facts."
  - "A2 remains SOUND_OVERAPPROXIMATION with source applicability capped by actual receipts; unsupported properties and absent owners remain load-bearing model gaps."
  - "A later correction creates a new pinned model/report or supersession projection; it never mutates an immutable historical report."
---

# Operation Assurance (OLS)

Program architecture is protected in Mastermind. OLS-F0 landed through PR #279 at
`f0ea48479a32728ecc3a3c8f1c36088e21a1a115`. OLS-A1 landed through PR #324 at
`c6af57d1ce96ed3f5ca8237099f4a5ecfa01d3cf`. The bounded A2 source-seam design landed through PR
#339 at `ae483cc5f101d369f368f217bb767c91fc9e0150` and requires this composition:

```text
owner-native Agent OS bytes + revision/cutoff receipts
-> invocation-local source facts
-> protected mastermind.executive_steward.result.v1 composition
-> pure SOUND_OVERAPPROXIMATION model compiler
-> protected A1 checker
-> immutable report-only output
```

Mastermind PR #362 is the sole current A2 implementation source carrier. The branch has incorporated
Sol's closed-wire, checkout/revision-binding, workstream-status agreement and full-tuple source-alias
repairs plus the canonical BSC-E1 fence correction. It still requires exact-current-head review,
current-base proof and a real run against this protected record before release. Its capability ceiling
remains `BUILT_NOT_PROVEN / OFFLINE_SOURCE_COMPILER / REPORT_ONLY / PRODUCTION_INERT`.

The fable-003 design dialogue is terminal. The separately attempted fable-004 implementation child
was stopped pre-START with `effect=NONE` because its required canonical issue was absent and its
receiver did not match the targeted prior session. Neither terminal dialogue is an active source
writer or continuation authority. Existing PR #362 source is preserved as known Git evidence and is
reviewed in place rather than duplicated or retried.

This revision is the real owner-native positive source candidate required by the protected design.
Every nonterminal wave now has an explicit dependency-bounded continuation or current next action,
so the positive compile can distinguish implementation behavior from an avoidable organizational
no-completion defect. Once protected on Macro main, PR #362 must gather this exact commit's bytes
under its full immutable revision and return model/report/source-byte receipts. That proof remains
Agent-OS-scoped: it does not establish current Executive runtime completeness, production
applicability, admission authority, or permission to proceed.

A3 through A8 remain held. No Control Room experience, canary, runtime conformance, admission
integration, enforcement, production installation or learning-loop completion is created by this
records correction.