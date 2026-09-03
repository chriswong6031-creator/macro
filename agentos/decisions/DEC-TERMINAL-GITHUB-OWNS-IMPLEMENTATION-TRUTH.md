---
key: TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH
question: Which system owns normal Mastermind Terminal implementation source and accepted release evidence?
answer: >
  GitHub owns Terminal implementation and evidence truth. Normal production releases must consume
  one explicit full commit accepted on the protected default branch, and the production host may
  own only declared runtime data, generated artifacts, configuration, secrets and other reviewed
  host-local state. A VPS edit is never silently authoritative; any emergency host edit must stop
  normal deployment and create an immediate GitHub reconciliation carrier.
rationale: >
  Multiple sessions and deploy paths can safely converge only on one immutable implementation
  identity. Treating the VPS or an arbitrary workstation checkout as source authority makes a
  healthy deployment capable of overwriting unknown work, makes rollback identity ambiguous, and
  forces every fresh operator into SSH archaeology. GitHub already carries review, exact history,
  required CI and accepted commits; the host is the correct owner for mutable runtime state but not
  ordinary source. Exact-SHA deployment plus source/drift receipts preserves both truths without a
  second deployment database or lifecycle.
alternatives:
  - option: Keep the VPS as canonical implementation source and reconcile box to Git before deploy.
    why_not: >
      This permits hidden production-only implementation, makes reproducibility depend on forensic
      reverse synchronization, and contradicts the project law that GitHub owns implementation and
      evidence truth.
  - option: Keep both the server-pull builder and arbitrary workstation build/rsync as equal deploy authorities.
    why_not: >
      Two authorities can ship different bytes for the same branch state, bypass one another's
      preflight and rollback contract, and leave no single answer for what production should run.
  - option: Add a standalone deployment database and scheduler as canonical release truth.
    why_not: >
      GitHub commit history plus runtime receipts are sufficient. A new database/scheduler would
      duplicate Executive OS and the existing deploy/merge control planes without unlocking a user
      or machine capability.
evidence:
  - "Chairman commission and Terminal issue #483 freeze GitHub default-branch implementation authority and exact-SHA deployment."
  - "Terminal `DEPLOY.md` and `ops/terminal-build.sh` already describe/build from the GitHub checkout, while the repository description and `scripts/deploy_terminal.sh` retained contradictory VPS/local-source law."
  - "Accepted Wave-0 production census recorded `/opt/terminal/terminal` as the serving plain copy, `/opt/terminal/.gitsrc` as the pristine canonical checkout, deployed SHA b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea, and zero unexplained implementation drift."
  - "Terminal PR #484 implements a fail-closed accepted-SHA versus live-source audit without adding a deployment lifecycle."
affects:
  - "WS:TERMINAL-GITHUB-CANONICALIZATION"
  - terminal-charting
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-29
---

## Consequences

1. The default branch and its exact accepted commit are the only normal implementation source.
2. Production deploy tooling must fail before destructive convergence when accepted identity or
   live source classification is unknown.
3. Runtime data, caches, dependencies, generated builds, environment files and secrets remain
   host-owned only through explicit reviewed boundaries; they are not evidence that the host owns
   application source.
4. A deployment receipt must distinguish attempted SHA, actually deployed SHA, health result and
   rollback result. A matching marker alone does not prove served bytes.
5. The existing merge-on-green controller remains the one fallback merge controller and is hardened
   in place; no second merge bot or release database is created.
6. Repository privacy is a later access/deploy/rollback decision, not a prerequisite for source
   authority and not something CI success proves.

## Emergency exception

A production-only emergency edit may be used solely to restore service when the normal path cannot.
It must be treated as an explicit divergence incident, must not be followed by a normal deploy that
would erase it, and must immediately produce one durable GitHub reconciliation carrier containing
the exact delta, reason, operator, production receipt and retirement path. The exception does not
make the host canonical and does not create a parallel hotfix branch family.
