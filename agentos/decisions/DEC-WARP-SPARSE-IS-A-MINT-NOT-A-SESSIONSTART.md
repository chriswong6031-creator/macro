---
key: WARP-SPARSE-IS-A-MINT-NOT-A-SESSIONSTART
question: >
  Warp has no Claude/Codex/Cursor SessionStart or WorktreeCreate event. How should
  Macro adopt the same sparse session-worktree profile for Warp/Oz sessions
  without inventing a second sparse mechanism or sparsifying the operator local
  root?
answer: >
  Reuse scripts/worktree_sparse.py mint/auto. Ship .warp/hooks/session_start_sparse.py
  as the mint and .agents/skills/macro-sparse-worktree as the discovery path a Warp
  session must run before editing. Plant trees under .warp/worktrees/, never
  sparsify macro-main or Macro Dashboard, and never write .session-worktree into a
  git checkout.
rationale: >
  Codex and Cursor can call `auto` after their harness creates a linked worktree.
  Warp local sessions start in the folder the operator opened — usually the
  occupied primary or the designated local root, which is itself a linked
  worktree. A Codex-shaped `auto` there is a no-op by design (and must stay that
  way). Grok already solved the empty-temp case by minting with
  `git worktree add --no-checkout`. Warp is that case plus a real git cwd, so
  the mint is the same and the pointer file is not.
alternatives:
  - option: Add a fake .warp/hooks.json SessionStart like Codex
    why_not: >
      Warp docs and settings_schema.json have no SessionStart/worktree hook key.
      A file Warp never loads would look like fleet law and not run.
  - option: Key auto on is_linked_worktree alone
    why_not: >
      macro-main is a linked worktree of the occupied primary. That would sparsify
      the 3.8 GiB operator root on every Warp chat — the exact Cursor fail-safe.
  - option: Write .session-worktree into macro-main
    why_not: >
      That folder is a git checkout. The pointer would be untracked dirt and trip
      the ship-loop dirty gate.
evidence:
  - "docs.warp.dev settings_schema.json — no hook/worktree/session-start setting"
  - "scripts/worktree_sparse.py auto_profile — refuses non-session linked trees"
  - ".grok/hooks/session_start_sparse.py — mint + pointer for empty grok-temp dirs"
affects: [".warp/hooks/session_start_sparse.py", ".agents/skills/macro-sparse-worktree", "scripts/worktree_sparse.py", "config/worktree_gc.json", "CLAUDE.md", "AGENTS.md"]
confidence: high
reversibility: easy
decided_by: warp-oz-session
decided_at: 2026-08-22
---

## Grounds

Warp's documented surfaces for this job are project rules, skills, and optional
cloud-environment setup commands. Local interactive Warp/Oz sessions in this
repo do not get a harness lifecycle hook. The cheapest correct analog is the
already-shipped mint, discovered by a skill Warp already loads.

## What would reopen this

A documented Warp SessionStart or WorktreeCreate event that can run a checked-in
project command before the agent edits files. Then this mint becomes a fallback,
the same way Codex's SessionStart is a fallback to environment.toml.
