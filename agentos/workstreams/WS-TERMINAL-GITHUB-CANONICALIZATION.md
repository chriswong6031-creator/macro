---
key: TERMINAL-GITHUB-CANONICALIZATION
title: Terminal GitHub Canonicalization, Deployment and Repository Reliability
objective: >
  Make GitHub the canonical implementation and evidence truth for Mastermind Terminal,
  then make production reproducibly deployable from one explicit accepted commit with
  truthful deployed-SHA, drift, health, browser/data and rollback receipts. Done means
  no ordinary source originates on the VPS, one canonical deploy path is production-proven,
  repository authority and security are hardened without replacing the existing merge
  controller, and private-repository readiness is either executed or blocked by an exact gate.
status: active
program: terminal-charting
repos: [terminal, macro]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: W0
    title: Read-only production archaeology and source-delta recovery
    status: done
    next_action: >
      Preserve the accepted receipt as the production baseline; every later mutation must
      rerun the fail-closed preflight and must not reinterpret runtime data as Git source.
  - id: W1
    title: Fail-closed source audit capability
    status: built_not_proven
    pr: 484
    depends_on: [W0]
    next_action: >
      Preserve exact source-audit head 6164f6c1cae733b2b1657b0ae38de4aefdafb7e3 on PR #484.
      Do not release it while the repository's required Terminal browser authority remains
      nondeterministic under #485. After responsive reliability is accepted, refresh #484 through
      the normal protected path, obtain fresh exact-head checks and independent review, then Sol
      either accepts and merges that head or returns a bounded repair on the same carrier.
  - id: W2
    title: Exact accepted-SHA deploy, release receipt and rollback identity
    status: todo
    depends_on: [W1]
    next_action: >
      After W1 lands, derive the narrow production source-audit policy from W0, require one
      explicit full master SHA, preflight before destructive checkout/source convergence, stage
      the target without mutating live state, and record attempted, deployed and rollback
      identities without a new deployment database.
  - id: W3
    title: Repository authority, merge and security hardening
    status: partial
    depends_on: [W1]
    next_action: >
      Keep W3B PR #487 DRAFT/held until #485 makes the required browser authority reliable, then
      refresh it onto current master and obtain fresh exact-head checks/review. Keep W3M issue #488
      SPEC_ONLY/held for the same reason. Reconcile GitHub Estate Governor source law before any
      ruleset, CODEOWNERS, merge-method, security or dependency-setting mutation.
  - id: W4
    title: Production browser, real-data, drift and rollback proof
    status: todo
    depends_on: [W2, W3]
    next_action: >
      Deploy one accepted SHA through the canonical path, prove exact served identity,
      health and representative Macro-backed data at desktop/tablet/phone, run the lawful
      rollback drill with a durable receipt, and prove the drift sentinel fails loud.
  - id: W5
    title: Private-repository readiness and durable closeout
    status: todo
    depends_on: [W4]
    next_action: >
      Prove ChatGPT/Codex/operator access, deploy authentication, private-safe fetches and
      rollback; execute or explicitly hold the visibility decision, then reconcile Agent OS,
      Linear and GitHub #483 to the final evidence state.
decisions:
  - DEC:TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH
discoveries:
  - DSC:TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY
landmines:
  - >-
    The accepted W0 deployed-SHA/topology receipt is a point-in-time production observation, not
    proof that production remained unchanged forever. Re-prove current production identity before
    any W2/W4 mutation or final acceptance.
  - >-
    A clean Git checkout or matching `.deployment-id` is not served-build provenance.
    Build output, runtime-code convergence, service health, browser behavior and upstream
    data freshness remain separate evidence states.
  - >-
    `/opt/terminal/terminal` is a plain production copy with host-local `.env*`, mutable
    `public/data`, dependencies and generated builds. Never run blind reset/clean/delete
    semantics over it or classify broad directories as runtime merely to obtain CLEAN.
  - >-
    The current VPS builder historically installs the next copy of itself only after an
    application swap. Bootstrap and rollback identity must therefore be designed explicitly;
    a merged script is not necessarily the script that performed the first deploy.
  - >-
    The application health check historically precedes later runtime-code synchronization.
    Do not claim one atomic app+runtime release until later failure behavior and receipt
    semantics are implemented and proven.
  - >-
    `merge-on-green` is an existing trusted-default-branch fallback controller. Harden its
    self-modification, check-provenance, arming and native-bypass boundaries; do not replace
    it with a second merge bot, queue or evidence database.
  - >-
    The required `Terminal typecheck + tests` check is itself release authority. Its responsive
    Playwright failures may not be laundered into green with retries, sleeps, skips, force-clicks,
    global timeout inflation or unrelated PR scope widening. Reliability repairs stay on #485 and
    their existing bounded carriers.
  - >-
    GitHub settings shared across the estate remain coordinated with the GitHub Estate
    Governor. A Terminal-only ruleset standard may not silently conflict with Macro or
    Mastermind publisher/bypass requirements.
  - >-
    Repository visibility must not change before connected-tool/operator access, production
    deploy authentication, every private fetch path and rollback are proven end to end.
do_not_redo:
  - >-
    Do not reopen whether GitHub or the VPS owns normal implementation source. Chairman law
    and DEC:TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH settle GitHub as canonical; remaining
    work is safe migration and production proof.
  - >-
    Do not recreate a source-audit tool outside Terminal PR #484. Continue that exact carrier
    until accepted, rejected or superseded by a recorded Sol decision.
  - >-
    Do not recreate the responsive reliability work now owned by #485. #492 is already on master;
    #496 owns adaptive-toolbar actionability and #497 owns finite visual-ready render liveness.
    Continue those exact GitHub carriers rather than minting replacement PRs.
  - >-
    Do not move Macro producers, market data, caches, configuration or secrets into the
    Terminal repository to make source comparison easier.
  - >-
    Do not treat green CI, a merge, Slack delivery or a healthy HTTP 200 as equivalent to
    deployed-SHA, real-data, rollback or final production acceptance.
artifacts:
  - agentos/decisions/DEC-TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH.md
  - agentos/discoveries/DSC-TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY.md
  - agentos/handoffs/TERMINAL-GITHUB-CANONICALIZATION-2026-08-30.md
  - agentos/handoffs/TERMINAL-GITHUB-CANONICALIZATION-2026-09-01.md
next_action: >
  Consume natural exact-head CI for Terminal PR #496 head
  d19bb18a16ad0b76d8b4d57d65ecd3590ba1c747 / run 33485568892 without rerun-to-green.
  If the owned layout-integrity and W2-A toolbar journeys are first-attempt clean, require one
  independent exact-head review and Sol release ruling before merge. In parallel keep PR #497 at
  REQUEST_CHANGES until its real `indicator-snapshot` consumer records the generation-bound
  `mm:terminal-visual-ready-diagnostic` reason; do not alter render budgets/logic until that
  discriminator identifies the missing edge. Only after #485 makes the required Terminal check
  deterministic should #484 and #487 be refreshed/re-proven for release. W2 production mutation,
  repository-setting mutation and visibility change remain held.
---

## Context

The Chairman assigned Sol autonomous ownership of Terminal source, deployment and repository
reliability after the repository description and an alternate local-rsync deploy path still
projected the VPS as source authority. The accepted W0 archaeology found no unexplained
production-only implementation at that observation time, so the program moved from source recovery
into fail-closed source auditing, release reliability, exact-SHA deployment and native repository
hardening.

GitHub issue `mastermindx-market-intelligence/mastermind-terminal#483` is the canonical program
carrier. This record preserves durable organizational state only. Executive OS owns runtime
Job/Attempt/Worker/Event state; GitHub owns implementation/evidence; Slack remains transport.

## Current capability frontier — 2026-09-01

- **W0 / PROVEN_LIVE at observation:** read-only production archaeology proved the serving plain
  copy, pristine canonical checkout, accepted deployed SHA
  `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`, and zero unexplained implementation drift. A fresh
  production read is still required before any later mutation/final current-state claim.
- **Responsive release authority / PARTIAL:** PR #492 is merged on Terminal master as
  `86a75b68c273a592a41af5e322f95aab242b8297` and makes visual readiness phase/generation truthful.
  PR #496 remains DRAFT on the same three-path toolbar carrier; exact head
  `d19bb18a16ad0b76d8b4d57d65ecd3590ba1c747` removes the falsified fixed 2-second action sub-budget
  while preserving one aggregate test-bound deadline, with natural run `33485568892` pending at the
  latest durable update. PR #497 remains DRAFT at `66a89d4b1cd70fd7617e40ea86f0fb6fc0ac0db8`
  under Sol REQUEST_CHANGES because the owned `indicator-snapshot` journey still failed twice and
  the new typed render diagnostic was not visible to the real E2E consumer.
- **W1 / BUILT_NOT_PROVEN:** PR #484 remains open at
  `6164f6c1cae733b2b1657b0ae38de4aefdafb7e3`. Its fail-closed source-audit implementation is built,
  but release remains held behind a trustworthy fresh required Terminal check and current
  exact-head review/proof.
- **W2 / NOT_BUILT:** reviewed production policy, explicit accepted-SHA deployment, complete
  attempted/deployed/rollback receipt, canonical operator path and drift sentinel are not live.
- **W3 / PARTIAL:** PR #487 contains the bounded required-check App provenance/candidate-token
  repair at `f37f5de8c2de36ddea1a9954e7e7c0003a6a70f2` but is DRAFT/held by #485; issue #488 freezes
  GitHub-native low-churn dependency maintenance but remains SPEC_ONLY/held. Strong native ruleset,
  CODEOWNERS, no-generic-admin-bypass, secret/push scanning, code scanning and final merge-method
  posture are not production-proven.
- **W4 / NOT_BUILT:** no accepted-SHA release has yet been production-proven through the future
  canonical path with current responsive browser, real Macro-backed data, drift and rollback proof.
- **W5 / NOT_BUILT:** private-safe operator/deploy/rollback qualification and the final visibility
  decision are unresolved.

## Operating model

Sol remains accountable for architecture, carrier admission, review, merge, production acceptance
and durable truth. Bounded engineering/review waves route to the least-scarce capable worker after
architecture is frozen. Worker delivery, ACK, START, implementation, CI and final acceptance remain
distinct. No reliability or deployment carrier inherits authority merely because a prior session
went silent; started sticky operations must be explicitly reconciled before a fresh operation can
reuse the same GitHub artifact.
