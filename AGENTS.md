# Macro Dashboard — shared agent operating rules

This repository is operated by multiple Claude accounts and Codex sessions. Repository files are the durable, shared source of instructions; promises or “memory” recorded only inside one chat do not carry to another session.

## Required context at the start of every task

1. Read `CLAUDE.md` in full and follow it as the authoritative project guide.
2. Search the Claude project memory index at
   `~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/memory/MEMORY.md`
   and open the entries relevant to the task. For delivery work, always include
   `session-finish-full-git-chain`, `auto-finish-commit-push-pr`, and
   `go-live-deploy-mechanics`.
3. Treat `/Users/chriswong/Documents/Cluade/charting-app` as the connected Terminal
   repository. Authentication, subscriptions, data contracts, APIs, and deployment
   changes may require checking both repositories.

## Workspace and git

- The canonical project home is `/Users/chriswong/Documents/Cluade`.
- Never create project work in `~/.codex/worktrees`, `/private/tmp`, or another
  Codex-only location. Never use a `codex/` branch for these repositories.
- The primary checkout is shared and commonly dirty or detached. Do not change its
  files or git state. Fetch the remote default branch, then create a fresh worktree
  under this repository's `.claude/worktrees/<task>/` and use a `claude/<task>`
  branch.
- Macro branches start from fresh `origin/main`; Terminal branches start from fresh
  `origin/master`. Never reuse a squash-merged branch.
- Do not use the repo-global stash stack.

## Definition of done

For every substantive, verified change, complete the full delivery chain without
asking the operator to finish it:

1. commit;
2. push;
3. open a pull request;
4. check CI and resolve genuine failures;
5. same-day squash-merge and delete the remote branch;
6. deploy or wait for the repository's normal deploy lane, then verify the change
   on the real live URL.

Do not stop at a local commit or an open PR. The only holds are an explicit operator
request to hold, a genuine non-spurious failing check, or a real deployment blocker.
For Macro, the `Workers Builds: macro` red X is known-spurious. Template/source
changes must include their paired `site/` artifact when required, and “merged” is
not “live” until the VPS/render path and live marker are verified.

When an operating standard changes, update the repository's `AGENTS.md` and
`CLAUDE.md` together so both Codex and every Claude account inherit it.

### Shared render-lane safety

`render.yml` is one shared, coalescing deploy lane. A successful push render at
a merge SHA or any later main descendant covers the earlier merge because the
workflow unions every dirty scope since its last covering watermark. Monitor
that shared covering run; do not demand a dedicated successful run for every
merge SHA.

Never cancel or manually re-run an in-progress `render`, `engine-render`, or
`daily` solely to unblock a session. A long job inside its declared timeout is
not wedged evidence. Re-run only after the job has concluded unsuccessfully,
the cause has been identified or corrected, and one session owns the recovery.
Parallel sessions must reuse that recovery instead of launching retries of
their own.

The contract is actively enforced for Claude by the tracked `SessionStart` and
`Stop` hook in `.claude/hooks/ship_loop_guard.py`. It snapshots pre-existing dirty
files, then refuses a normal stop while session-created work is uncommitted,
unpushed, unmerged, waiting on the required render, or absent from production.
Codex must follow the same chain directly from this file. A genuine repeated
external blocker must be reported as `SHIP LOOP BLOCKED:` with concrete evidence;
ordinary local cleanup, authentication setup, and waiting are not blockers.
The CI gate is base-side-aware: a red on the merged head that provably pre-existed
on main (same check failing on ≥2 independent concurrent PR heads pre-merge, or a
green ci.yml run on a main descendant) is excluded by name rather than pinning the
session forever; the operator lever for a healed base is
`gh workflow run ci.yml --ref main` — one green dispatched run clears every pinned
merge at once. Unknown or lone-sibling evidence stays `ci_failed` (fail-closed).
