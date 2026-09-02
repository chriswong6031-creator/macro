---
key: SELFHOSTED-RUNNER-PATH-IS-A-CONFIGURE-TIME-SNAPSHOT
claim: >
  A self-hosted GitHub Actions runner's job PATH is a one-time snapshot of the
  interactive shell that ran config.sh, captured into the runner directory's
  .path file by env.sh — not a live read of the host's current PATH. On the Mac
  Studio the four live runners therefore carry materially different PATHs:
  actions-runner, -2 and -4 (registered Jul 13/15) begin with
  ~/.local/bin:...:/opt/homebrew/bin:..., while actions-runner-3 (re-registered
  2026-08-14 after a repair) has NO /opt/homebrew/bin entry at all — its jobs
  cannot resolve Homebrew node/npm/git/python3 unless a workflow step supplies
  them. Same physical host, four effective environments, selected by runner
  lottery.
falsifier: >
  A job on mac-builder-3 (actions.runner.mastermindx-market-intelligence-macro.
  mac-builder-3) whose `echo $PATH` in a plain run step shows /opt/homebrew/bin
  without any workflow-level PATH export or setup-* action in that job — that
  would show the runner re-derives PATH live rather than serving the .path
  snapshot.
so_what: >
  When a workflow behaves differently "sometimes" on the self-hosted pool,
  compare the runner NAME in the two run logs before bisecting the diff: a
  Homebrew-tool-not-found or wrong-python failure that only appears on one
  runner is the .path snapshot divergence, not a code regression. Any repair
  that re-registers a runner re-captures PATH from whatever shell performed the
  repair — re-registration is an environment mutation and should be followed by
  diffing the new .path against a sibling runner's. This is a motivating
  exemplar for the Reproducible Worker Environments program
  (research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md §3 I3).
kind: landmine
verified_at: 2026-09-01
verified_by: >
  Read-only census in session e0901edc: cat of ~/actions-runner*/.path (runner,
  -2, -4 contain /opt/homebrew/bin; grep -c homebrew ~/actions-runner-3/.path
  returns 0), ~/actions-runner/env.sh (snapshot mechanism), launchctl list
  showing the four live runner services, and .runner/.credentials mtimes of
  2026-08-14 on actions-runner-3 matching the sibling backup directory
  actions-runner-3-repair-backup-20260814T2300Z.
scope:
  - macro
  - self-hosted runner fleet (Mac Studio actions-runner*/)
confidence: verified
---
