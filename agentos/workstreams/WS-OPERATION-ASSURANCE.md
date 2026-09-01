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
  - {id: A2, title: "Canonical owner/source compilation via separately-accepted bounded gather seam", status: in_progress, next_action: "Author the A2 seam design record (records-only Mastermind PR, F0 pattern): freeze target operation, seam contract per Steward-reconciliation spec §5-§8, collision review vs CCL-A2 branches; Sol accepts before implementation"}
  - {id: A3, title: "Correction-safe current applicability + evidence-preserving summary", status: todo, depends_on: [A2]}
  - {id: A4, title: "Control Room experience over real data", status: todo, depends_on: [A3]}
  - {id: A5, title: "Report-only real canary + calibration", status: todo, depends_on: [A4]}
  - {id: A6, title: "Runtime conformance shadow path", status: todo, depends_on: [A2]}
  - {id: A7, title: "Admission integration, calibrated default-off promotion", status: todo, depends_on: [A5, A6]}
  - {id: A8, title: "Production installation, rollback drill, runbook, learning loop", status: todo, depends_on: [A7]}
next_action: >
  Author and land the A2 gather/source-compiler seam design record (records-only Mastermind PR)
  and freeze the first real target operation; request Sol acceptance on the fable-002 carrier
  before any A2 implementation.
do_not_redo:
  - "Do not re-diagnose the false-green Slack RESULT sequence on the parent carrier (F0/A1/A2 'PROTECTED' claims dated pre-2026-09-01): Sol's canonical correction overrode them and R0 re-landed F0 for real; GitHub is truth."
  - "repair_scope is RULED out of the F0/A1 wire (removed, pinned by exact-tuple tests at Mastermind tests/test_operation_assurance_a1_repair_wave.py); do not re-freeze it without superseding the ruling."
  - "Do not build a gather layer inside the pure A1 checker or a second Steward/federated reader — Steward-reconciliation spec §5-§8 forbids it; the seam must be separately accepted."
  - "PROPER_COMPLETION overlapping-terminal ownership is INTERSECTION (fail-closed principal ruling, reviewer-probed in 3 directions); do not revert to union."
landmines:
  - "Mastermind master requires up-to-date branches and allows squash-merge ONLY; reconcile via history-preserving server-side merge (merges API), never rebase/force-push."
  - "Mastermind master moves roughly hourly; fast-follow the merge after CI greens or the up-to-date gate refuses again."
  - "Several OLS-F0 'contract' tests are document-parity greps over spec prose, not engine coverage — green there does not prove the engine (this is exactly how the unbounded fairness product shipped its first draft)."
---

# Operation Assurance (OLS)

Program spec: Mastermind-side protected records (entry: `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`
§CONTROLLING notice, wire finalization first) plus the Chairman-ratified Fable principal packet
(operation `mastermind-operation-assurance-full-production-20260901-fable-002`, carrier
`C0BSBM78V1N/1788258733.684159`; predecessor fable-001 terminal/accepted after Wave R0).

Protected so far (canonical, read back): OLS-F0 architecture/source law at Mastermind master merge
`f0ea48479a32728ecc3a3c8f1c36088e21a1a115` (22 records/tests; SPEC_ONLY/RECORDS_ONLY/PRODUCTION_INERT);
OLS-A1 deterministic engine at master merge `c6af57d1ce96ed3f5ca8237099f4a5ecfa01d3cf`
(BUILT_NOT_PROVEN/REPORT_ONLY/PRODUCTION_INERT; 202 A1 tests; adversarial verdict RELEASE_SAFE
after a four-finding repair round).

No dedicated program key exists yet for the Executive-OS/organizational-assurance domain in
`config/mastermind_programs.yml`; `cross-repo-contract-governance` is the closest genuine fit
(OLS makes cross-owner authority/progress seams explicit and checkable). Minting a dedicated key
is the registry owner's call, not this workstream's.
