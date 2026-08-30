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
    status: awaiting_ci
    pr: 484
    depends_on: [W0]
    next_action: >
      Re-read exact Terminal PR #484 head 6164f6c1cae733b2b1657b0ae38de4aefdafb7e3,
      require all protected checks plus independent final review, then Sol either accepts
      and merges that exact head or returns bounded repairs on the same carrier.
  - id: W2
    title: Exact accepted-SHA deploy, release receipt and rollback identity
    status: todo
    depends_on: [W1]
    next_action: >
      From the accepted W0 topology, commit the narrow production source-audit policy,
      require one explicit full master SHA, preflight before destructive checkout/source
      convergence, make application and runtime outcome truthful, and record attempted,
      deployed and rollback identities without a new deployment database.
  - id: W3
    title: Repository authority, merge and security hardening
    status: todo
    depends_on: [W1]
    next_action: >
      Reconcile the parallel GitHub Estate Governor ruling, then apply only the compatible
      Terminal ruleset, CODEOWNERS, squash-only, workflow-permission, dependency and native
      security baseline while preserving the sound trusted-code merge-on-green controller.
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
    Do not move Macro producers, market data, caches, configuration or secrets into the
    Terminal repository to make source comparison easier.
  - >-
    Do not treat green CI, a merge, Slack delivery or a healthy HTTP 200 as equivalent to
    deployed-SHA, real-data, rollback or final production acceptance.
artifacts:
  - agentos/decisions/DEC-TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH.md
  - agentos/discoveries/DSC-TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY.md
  - agentos/handoffs/TERMINAL-GITHUB-CANONICALIZATION-2026-08-30.md
next_action: >
  Complete exact-head hosted validation and independent final review for Terminal PR #484.
  If accepted, merge that immutable head; then start W2 only from a fresh Terminal master,
  the accepted W0 topology and a new collision census.
---

## Context

The Chairman assigned Sol autonomous ownership of Terminal source, deployment and repository
reliability after the repository description and an alternate local-rsync deploy path still
projected the VPS as source authority. The product already had strong required CI and a
server-pull deploy design, but no trustworthy one-command answer for accepted SHA versus live
source, no durable full deployment/rollback receipt, and no completed private-repository gate.

GitHub issue `mastermindx-market-intelligence/mastermind-terminal#483` is the canonical program
carrier. This record preserves durable organizational state only. Executive OS owns runtime
Job/Attempt/Worker/Event state; GitHub owns implementation/evidence; Slack remains transport.

## Current capability frontier

- **W0 / PROVEN_LIVE:** the read-only production census established the actual service/source
  topology and found zero unexplained production-only implementation at its observation time.
- **W1 / BUILT_NOT_PROVEN:** PR #484 contains the fail-closed source audit. Its final stdout
  repair is green in the Python required job; the long Terminal check and independent exact-head
  review remain acceptance gates.
- **W2 / NOT_BUILT:** explicit accepted-SHA deployment, reviewed production policy, complete
  attempted/deployed/rollback receipt and truthful app/runtime failure semantics.
- **W3 / PARTIAL:** classic required checks and a careful merge-on-green controller exist;
  stronger shared ruleset/CODEOWNERS/security/dependency posture is not yet reconciled.
- **W4 / NOT_BUILT:** exact release through real production with responsive browser, real data,
  drift and rollback proof.
- **W5 / SPEC_ONLY:** private access/deploy/rollback qualification and final visibility decision.

## Operating model

Sol remains accountable for architecture, carrier admission, review, merge, production acceptance
and durable truth. Bounded engineering/review waves route to the least-scarce capable worker after
architecture is frozen. Every worker assignment still requires pickup ACK, exact-thread watcher,
separate START and continuation return; those transport receipts never become workstream liveness.
