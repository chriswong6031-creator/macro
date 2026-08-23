---
key: MAS28-PR-LINKAGE-VALIDATOR-V1-REPORT-ONLY
question: >
  Which author grammar, compatibility boundary and authority posture govern the
  MAS-28 PR-linkage validator V1 despite drift among MAS-6, the older MAS-28 issue
  body, current repository templates and incomplete MAS-67 native canaries?
answer: >
  The current Chairman MAS-28 commission freezes the canonical six-field V1 grammar
  and a deterministic exact-receipt compatibility epoch. MAS-28 is a zero-network,
  zero-mutation observer with separate classification and evidence-verdict axes;
  semantic findings remain report-only and cannot gate merge or mutate Linear.
rationale: >
  The Chairman commission is the newest accepted source and explicitly reconciles the
  older enum family. Treating the old templates as canonical would perpetuate known
  drift, while accepting every historical spelling would make the declaration fuzzy.
  Exact per-repository cutover merge/blob receipts let the pure core distinguish lawful
  pre-cutover aliases from post-cutover defects without clocks or live network access.
  Separating PR shape from evidence support preserves honest partial state while MAS-67
  closing/non-closing canaries and admin readbacks remain incomplete. Report-only shadow
  follows Charter P3/P8 and the #6119 completion amendment; enforcement requires a new
  post-calibration decision.
alternatives:
  - option: Keep the old MAS-28 issue and template literals as canonical V1
    why_not: >
      They are older than the controlling Chairman commission, disagree with current
      MAS-6 direction and omit deploy, architecture-candidate and records-only concepts.
  - option: Silently alias every observed historical spelling to a canonical class
    why_not: >
      It converts authoring ambiguity into false conformance and makes future template
      regressions invisible. Only four named aliases are lawful before exact cutover.
  - option: Query GitHub and Linear from the validator to fill missing observations
    why_not: >
      It couples deterministic analysis to mutable credentials/network state, duplicates
      native/projector authority and prevents reproducible calibration.
  - option: Make REFUSE_METADATA a required merge check immediately
    why_not: >
      Native A/B behavior and real-corpus error rates are not calibrated. Charter P8 and
      the commission require report-only shadow evidence before any separate gate request.
evidence:
  - "Chairman document: MAS-28 — Autonomous Sol End-to-End Commission & V1 Architecture Freeze, updated 2026-08-23"
  - "research/MASTERMIND_PR_LINKAGE_VALIDATOR_V1_ARCHITECTURE_FREEZE_2026-08-23.md"
  - "Macro PR #6119 / merge c7ffb20af0764b1afafd10c97034f9a29724a494 — native completion-law amendment"
  - "Macro PR #6135 / head 96fb7a35bb17fbcc7b462610bfbf59072ebbc218 — open stale-alias template carrier"
  - "Mastermind protected master db0bac5fe3f72348262d42c8bd26b836bda9f61d / docs/sol_skills tree 0a009d5314a4a3bbb1aac2f111b68644fc7a64d8"
  - "MAS-67 — relation-only and skip/ignore proven; closing/non-closing and admin readbacks incomplete"
affects:
  - WS:AGENT-OS
  - MAS-28
  - MAS-6
  - MAS-67
  - .github/pull_request_template.md
  - scripts/pr_linkage_validator.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

## Canonical consequence

Canonical author values are `creates_workstream`, `implementation`, `proof`, and
`proof-required`; `deploy`, `architecture_candidate`, and `records-only` are first-class.
`untracked_refused` is generated output, never an author mode. The four older template aliases
are visible migration inputs only under an exact repository cutover receipt.

The pure report schema is `mastermind.pr_linkage_report.v1`; the input is
`mastermind.pr_linkage_observation.v1`. A valid observation always yields a report and exits
successfully even when the evidence verdict is `REFUSE_METADATA`.

## Enforcement barrier

No V1 finding may become a required check, branch-protection rule, merge-controller decision,
PR mutation, Linear mutation or automatic repair under this decision. A future enforcement
proposal must cite accepted blinded calibration, real-path shadow receipts, observed operator
utility, measured partial rates, failure/rollback behavior and a new Chairman/Sol authority grant.
