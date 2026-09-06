---
key: TERMINAL-REQUIRED-CHECK-HAS-NO-MASTER-PROOF
claim: >
  The Terminal required job "Terminal typecheck + tests" has no automatic master-branch
  proof because `.github/workflows/ci.yml` runs it only on `pull_request` and
  `workflow_dispatch`, not `push`.
falsifier: >
  `gh run list -R mastermindx-market-intelligence/mastermind-terminal --workflow ci.yml
  --branch master` showing a completed "Terminal typecheck + tests" run created by a
  master push without a workflow change, or `terminal:.github/workflows/ci.yml` gaining
  `push: branches: [master]`, would disprove this discovery.
so_what: >
  Future Terminal release sessions must attribute this required-check base red by the
  same job name on at least two independent sibling PR heads, heal the base once, and
  not run per-PR retry-to-green loops. A structural fix is proposed, not decided: add a
  master push trigger for the job or run a `workflow_dispatch` baseline on a master
  descendant.
kind: constraint
verified_at: 2026-09-06
verified_by: >
  Meta-CEO B verification packet, 2026-09-06: `gh run list -R
  mastermindx-market-intelligence/mastermind-terminal --branch master` showed only
  CodeQL and merge-on-green; the base commit's check-runs showed only `sweep`;
  `.github/workflows/ci.yml` job `terminal` runs typegen, tsc, npm test, and
  `npm run test:e2e:responsive` only on pull_request and workflow_dispatch; Terminal
  PR #511 and issue #485 carry the quarantine/heal evidence.
scope:
  - terminal
  - terminal:.github/workflows/ci.yml
  - terminal:terminal/e2e/**
  - WS:MARKET-OS
confidence: verified
---

## Details

Meta-CEO B verified on 2026-09-06 that the required CI job "Terminal typecheck +
tests" in `mastermindx-market-intelligence/mastermind-terminal` runs on
`ubuntu-latest` with concurrency cancel-in-progress and executes typegen, `tsc`,
`npm test`, and `npm run test:e2e:responsive`. The workflow triggers are
`pull_request` and `workflow_dispatch` only. There is no `push` trigger, so a
normal master push never creates a master run of that job.

That removes the macro-style proof path that asks for main's own newest run. A
base-inherited red cannot be proven from master's required-check history when
master has no such history. The lawful attribution evidence is either the same
job name red on at least two independent sibling PR heads, or a green run on a
master descendant created by `workflow_dispatch`.

The 2026-09-06 measurement was 16 of 16 open Terminal PRs red on that single job
name, with no PR landed since 2026-09-04. The deterministic red in master's
content was `terminal/e2e/drawing-system.spec.ts:992` for Path tool
double-click. The flaky contention set had already been addressed by merged
Terminal PRs #505 (workers=1, timeout 60s) and #506 (retries 2). Terminal issue
#485 tracks the remaining flakiness.

The accepted heal is one PR: Terminal #511, branch
`claude/mo-b-w0-terminal-ci-heal-485`. It quarantines the one deterministic test
with evidence, adds `terminal/e2e/QUARANTINE.md`, and prints a bare line-start
`::warning` disclosure in CI. Per-PR "fix the cause and re-run" was rejected
because a pack/job is one check and 16 partial heals would deadlock; see
`DEC:TERMINAL-BASE-RED-IS-HEALED-ONCE-NOT-PER-PR-2026-09-06`, `WS:MARKET-OS`,
and Macro `CLAUDE.md` "Healing a red pack".

Release handling was separate from the discovery: Meta-CEO B ran the Terminal
release streams with `no_ship` (takeover -> review -> fix, no Ready/merge) until
the heal merges, then ships with a `ship_nonce`.
