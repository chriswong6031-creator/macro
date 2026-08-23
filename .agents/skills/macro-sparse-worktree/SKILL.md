---
name: macro-sparse-worktree
description: Mint or reuse a sparse Macro session worktree at the start of every Warp/Oz session. Trigger when starting work in macro-main, Macro Dashboard, a Warp agent conversation, Oz local agent, or any new session in this repository. Also trigger for "sparse worktree", "session worktree", "worktree hook", or before editing Macro files from a Warp session that is still in the operator local root.
---

# Macro sparse session worktree (Warp)

Warp has no SessionStart or WorktreeCreate hook. Claude, Codex, Cursor, and Grok already thin new session trees via `scripts/worktree_sparse.py`. Warp sessions must run the same mint themselves.

## Do this first, before any other file edit

Run from the current workspace:

```sh
python3 "$(git rev-parse --show-toplevel 2>/dev/null || echo /Users/chriswong/Documents/Cluade/macro-main)/.warp/hooks/session_start_sparse.py"
```

Then:

1. Read the line `WORKSPACE=<path>`.
2. If that path is a directory and is not already your cwd, `cd` into it and do all project work there.
3. Never sparsify `/Users/chriswong/Documents/Cluade/macro-main` or `/Users/chriswong/Documents/Cluade/Macro Dashboard`.
4. Never write `.session-worktree` into a git checkout.

The hook:

- no-ops unless the donor is GitHub `mastermindx-market-intelligence/macro`
- converts only a linked worktree under a session root (`.warp/worktrees/` and siblings)
- otherwise mints a sparse tree under `<donor>/.warp/worktrees/<name>/` with `git worktree add --no-checkout`
- omits `data/`, `site/`, `mockups/`, `verify_shots/` from `config/sparse_worktree.json`
- preserves an existing sparse selection such as `add site`

## Opt in when you need a heavy tree

```sh
python3 scripts/worktree_sparse.py status
python3 scripts/worktree_sparse.py add site
python3 scripts/worktree_sparse.py full
```

Do not run the full test suite in a sparse tree. Do not `git add -A` an unexpected `data/` or `site/` diff.
