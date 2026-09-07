---
key: TERMINAL-BASE-RED-IS-HEALED-ONCE-NOT-PER-PR-2026-09-06
question: >
  All 16 open mastermind-terminal PRs are red on the same required check, "Terminal typecheck
  + tests" (the responsive Playwright suite; Terminal issue #485 documents 2 failed / 4 flaky
  and retry-to-green). Is that red each PR's defect, and how does half B release them?
answer: >
  The red is base-inherited: 16 of 16 sibling heads fail the same job name and ci.yml never
  runs on master pushes, so no PR can prove itself green against the current base. It is
  healed ONCE by one PR off origin/master that gives every failing spec an evidence-backed
  disposition (deterministic fix when small and obviously correct; otherwise test.fixme
  quarantine listed in terminal/e2e/QUARANTINE.md with run ids, owner PR/issue and re-enable
  condition, printed by CI as a ::warning line), with retries unchanged and no whole-suite
  skip. The 16 PRs are taken over, rebased and Opus-reviewed now (no_ship), and shipped only
  after the heal is merged; the R1 fixes (#496, #497, #501) un-quarantine the specs they
  repair; #509 (fail CI on retry-only passes) is sequenced last.
rationale: >
  Fleet law already treats a red shared by >=2 independent sibling heads as main's, not the
  PR's; sixteen is conclusive. Healing per-PR would mean sixteen partial heals of one check,
  which the pack-heal law says can never all go green. Quarantine with evidence keeps the
  check honest (coverage loss is printed, owned and time-bound) while unblocking the whole
  half; raising retries would hide the defect instead.
alternatives:
  - option: "Merge the 16 PRs past the red with --admin as 'known base red'."
    why_not: "Never --admin past a real red (fleet law); it would also leave the suite unproven on every merge."
  - option: "Wait for Sol's R1 program (#496/#497/#501) to make the suite deterministic."
    why_not: "Those PRs are themselves blocked by the same red and have been open for a week."
  - option: "Skip the responsive suite in CI."
    why_not: "Silent coverage loss; the suite is the only browser proof the Terminal has."
evidence:
  - "Workflow census wf_ed55ef80-a18 (2026-09-06): 16/16 open PRs red on 'Terminal typecheck + tests'; every PR's content unlanded (git cherry all '+')"
  - "gh run list -R mastermindx-market-intelligence/mastermind-terminal --branch master: only merge-on-green/CodeQL runs on master; ci.yml has pull_request + workflow_dispatch triggers only"
  - "Terminal issue #485 body: '556 passed / 260 skipped / 2 failed / 4 flaky'; 'passed only after seven flaky retries'"
  - "CLAUDE.md §Healing a red pack; §Shared workspace (pre-merge base-side attribution)"
affects:
  - "WS:MARKET-OS"
  - "charting-app .github/workflows/ci.yml, terminal/e2e/**"
  - "all 16 open mastermind-terminal PRs"
confidence: high
reversibility: easy
decided_by: "session 7cd4fae1-1ed9-41c2-adb4-1e5c6b0fbc5b (Meta-CEO B, Claude3, under the Chairman override of 2026-09-05)"
decided_at: 2026-09-06
---

Heal branch: claude/mo-b-w0-terminal-ci-heal-485 (workflow wf_a8f99863-cd9). Release streams
run with no_ship and are resumed with ship_nonce after the heal merges.
