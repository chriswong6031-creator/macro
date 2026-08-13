---
key: PR-CI-ONLY-RUNS-AGAINST-MAIN-BASE
claim: >
  The only pull_request-triggered workflows in Macro (ci.yml and fences.yml) filter
  branches: [main], so a PR whose BASE is any other branch schedules zero ACTIONS
  check runs — the only check that can appear on it is the non-Actions, non-required,
  known-spurious "Workers Builds: macro" X — leaving its head unproven forever.
falsifier: >
  grep -n -A8 "pull_request:" .github/workflows/*.yml showing a pull_request trigger
  with a base filter beyond [main] (note: -A8, because comment lines sit between the
  trigger and its branches: line in ci.yml), or any non-main-base PR carrying a
  ci.yml/fences.yml check run.
so_what: >
  Never stack a PR on a non-main base in this repo. A stacked PR can never satisfy the
  merge-on-green sweeper (no concluded checks to read) and can never satisfy ci_handoff
  condition 4 (at least one non-spurious check started), so the session cannot even hand
  off — it pins until someone re-targets the PR to main or rebases the stack flat.
  Restructure dependent work as sequential PRs against main, landing in order.
kind: constraint
verified_at: 2026-08-13
verified_by: >
  grep over .github/workflows/*.yml, 2026-08-13: pull_request triggers exist only in
  ci.yml (branches: [main]) and fences.yml (branches: [main]); no other workflow
  declares one. Scope is GitHub Actions; the Workers Builds check is a Cloudflare
  integration outside these triggers (wrangler.toml notes it builds every push on
  main + PR branches and is not required).
scope: [macro]
confidence: verified
---

## Detail

The trap is quiet: GitHub happily opens the stacked PR, no Actions suite ever schedules,
and the only thing that can appear is the spurious Workers Builds X — which every
classifier here excludes by name. The absence only bites at the handoff/merge boundary,
where both the sweeper and the ship-loop classifier treat a head with no non-spurious
checks as unproven rather than clean — deliberately, per fleet law ("an absence of red
is not a pass", #4779).

Cross-repo contrast worth knowing: the Terminal repo (mastermind-terminal) gates its
master branch with required checks per its own AGENTS.md §Merge-on-green controller, so
stacked-PR behavior differs there; this record is about Macro, where main carries no
branch protection and Actions scheduling is entirely trigger-filter-driven.
