---
workstream: "WS:REPRODUCIBLE-WORKER-ENVIRONMENTS"
session: "claude/rwe (worktree reproducible-worker-environments-e139a1, Fable COO, session e0901edc)"
model: fable
ended_because: complete
mission: >
  Chairman direct delivery of operation
  mastermind-reproducible-worker-environments-20260830-sol-pro-001 (annex 05 of the
  seven-program Fable COO bundle) into the live Fable session of 2026-09-01, followed
  mid-program by an explicit Chairman override ("keep going, do not stop to ask me or
  CEO, take COO leadership until full completion"). The session ACKed on the Slack
  carrier (C0BSBM78V1N/1788258537.508239), executed waves A0 (census), D0 (bakeoff),
  P0 (pilot build + independent review chain + merge), CI0 (parity proof), and this
  closeout.
state_before: >
  No workstream, no carrier (op key and portfolio key both zero-result in Slack), no
  GitHub PR or branch for the program in macro or Mastermind, and the semantic registry
  had no reproducible-environments program. No coherent cross-host environment system
  existed: three distinct production Pythons in the estate, ~194 unpinned pip install
  lines in macro's legacy CI, persistent never-rebuilt runner venvs, divergent runner
  .path snapshots on one physical host, and two receipted drift incidents (I1 floating
  python pin, I2 Homebrew icu4c/node dyld breakage).
changed:
  - path: config/mastermind_programs.yml
    what: >
      Minted the reproducible-worker-environments program entry (registry gap resolved
      per the same procedure as executive-os on 2026-09-01; programs 61 -> 62).
  - path: docs/MASTERMIND_SYSTEM_MAP.md
    what: Regenerated via `python3 scripts/build_mastermind_system_map.py` (sole lawful path).
  - path: tests/test_mastermind_system_map.py
    what: Census pin advanced 61 -> 62 with a cause comment.
  - path: agentos/workstreams/WS-REPRODUCIBLE-WORKER-ENVIRONMENTS.md
    what: New workstream; A0/D0/P0/CI0 done, S0 blocked on Program 4, E0 todo.
  - path: agentos/decisions/DEC-RWE-PILOT-APPROACH-D.md
    what: The measured approach ruling (D selected; Devbox deferred; devenv/flake rejected).
  - path: research/REPRODUCIBLE_WORKER_ENVIRONMENTS_P0_CI0_RESULTS_2026-09-02.md
    what: P0/CI0 results, receipt parity table, adoption ruling, residuals.
verified:
  - claim: "Pilot merged on protected Mastermind master"
    command: "git -C /Users/chriswong/Documents/Cluade/Mastermind fetch origin && git merge-base --is-ancestor 722f15d531a1b05e06a346fa0c67d4d52142f4d0 origin/master && echo ok"
    result: "ok — PR #342 squash 722f15d531a1, mergedAt 2026-09-02T04:58:25Z, expected-head 72a403b9"
  - claim: "Independent adversarial review reached PASS at the reviewed exact head"
    command: "review packets in session e0901edc (opus reviewer): REQUEST_REPAIR at 29caa02a -> repairs add91c5d -> delta REQUEST_REPAIR(small) -> fixes 0a360b44 -> PASS re-probing all majors"
    result: "PASS with zero remaining findings; 63/63 unit tests at final head"
  - claim: "Full repository gate green in CI from the committed linux lock"
    command: "gh run view 33590301387 --repo mastermindx-market-intelligence/Mastermind (shadow); receipt artifact rwe-receipt-linux"
    result: "proof.gate = {exit: 0, discovered: 452, seconds: 1063.67}; vendored resolved_ref == pinned ref, match true"
  - claim: "Mac-side realize + receipt from the merged commit"
    command: "python3 scripts/rwe_env.py realize --dest <tmp> ; gate --env <tmp> --subset tests/test_executive_service.py (clone at 722f15d5)"
    result: "pip check ok; environment_id 45add2e16d4a1bfa; subset 35/35 exit 0; receipt secret-free (path classes only)"
  - claim: "Receipt parity mac vs CI is SEMANTIC_EQUIVALENT with explicit platform differences"
    command: "json compare of ci0-mac-receipt vs rwe-receipt-linux artifact (session scratchpad)"
    result: "same pyproject sha d5d346c4; 76 packages each; per-platform locks; interpreter divergence explicit (3.12.13/homebrew vs 3.12.14/toolcache) and folded into distinct environment_ids"
  - claim: "Bakeoff spike branch destroyed after capture"
    command: "gh api repos/mastermindx-market-intelligence/Mastermind/branches/claude/rwe-d0-bakeoff-spike-20260901"
    result: "404 (builder-verified); no PR ever existed for it"
unverified:
  - "The mac-side FULL gate under the pilot env (bounded subsets only ran locally; full-gate proof is CI-side — mac full gate requires materializing vendor/macro_src locally, documented in the runbook)"
  - "realize hash-mismatch refusal is enforced by pip's --require-hashes flags, not separately falsified with a tampered lock"
  - "Devbox candidate measurements are single-run (no variance sampling) and hosted-linux only"
do_not_redo:
  - "Do not re-run the D0 bakeoff to re-litigate approach selection without new bakeoff-grade measurements — DEC:RWE-PILOT-APPROACH-D governs; the spike branch is deleted by design"
  - "Do not install devenv/Devbox/Nix on any production Mac before supply-chain admission (RWE-S0 is BLOCKED on Program 4, which had no carrier as of 2026-09-02)"
  - "Do not make the rwe-shadow lane a required check or replace ci.yml's install path without the RWE-E0 value study"
  - "Do not 'fix' the two platform locks being currently identical in body — expected (pip-compile hashes all platforms) and disclosed in requirements/README.md"
danger_areas:
  - "check_pyproject_not_stale hard-refuses realize on ANY pyproject.toml byte change until both locks are regenerated — deliberate fail-closed sharpness; regeneration commands are in requirements/README.md"
  - "tests/test_web_sol_extension_reconstitution.py is a known rotating master-side Node flake; it redded one shadow run and one required-CI run during this program and passed on rerun both times — check the failing test name before blaming an RWE change"
  - "The receipt's forbidden-token guard is deliberately split-case: path tokens case-insensitive, bare tokens (incl HOME) case-sensitive so python_executable_class=homebrew cannot false-positive — do not 'simplify' it back to uniform case-insensitivity"
unresolved:
  - "RWE-S0 (env-manager admission) requires Program 4, which has no carrier yet"
  - "RWE-E0 value study needs real worker usage data before wider adoption"
  - "Mac-side full-gate run under the pilot env not yet exercised (needs local vendor materialization; CI proves the full path)"
next_actions:
  - "Run RWE-E0 once workers use the runbook path; then the wider-adoption decision (macro legacy-jobs.yml is the largest candidate surface)"
  - "Surface Program-4 sequencing to the portfolio principal before any Devbox promotion"
next_action: >
  RWE-E0 value study once real workers use the runbook path (then the wider-adoption
  decision, with macro legacy-jobs.yml as the largest candidate surface); RWE-S0
  stays blocked until the portfolio's Program 4 (supply-chain admission) exists —
  surface that sequencing to the portfolio principal before any Devbox promotion.
---

# RWE program closeout handoff (2026-09-02)

Full program narrative and receipts: carrier thread C0BSBM78V1N/1788258537.508239;
program docs under research/REPRODUCIBLE_WORKER_ENVIRONMENTS_*.md; pilot implementation
in Mastermind at 722f15d531a1 (scripts/rwe_env.py, requirements/gate-*.lock,
.github/workflows/rwe-shadow.yml, docs/RWE_RUNBOOK.md).
