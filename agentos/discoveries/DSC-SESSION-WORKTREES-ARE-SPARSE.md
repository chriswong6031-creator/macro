---
key: SESSION-WORKTREES-ARE-SPARSE
claim: >
  Session worktrees under Macro .claude/worktrees/ are created with git sparse-checkout
  enabled by default: site/, data/, and mockups/ are tracked in HEAD but absent from a
  default session tree.
falsifier: >
  git -C <fresh session worktree> config core.sparseCheckout returning empty/false, or
  site/ present on disk in a fresh default session worktree whose git ls-tree HEAD
  lists it.
so_what: >
  Before reading or writing site/, data/, or mockups/ — site tests, artifact builders,
  template-site pairing, design specimens — materialize the tree first
  (git sparse-checkout add <dir>) or request a full worktree. A builder that
  read-modify-writes a committed artifact against an omitted tree rebuilds from an
  empty base and silently SHRINKS it, so an unexpected site/ or data/ shrink diff is
  data loss, never an edit. Guards and tests that glob the omitted trees pass
  vacuously — a green site-suite in a sparse tree proves nothing.
kind: landmine
verified_at: 2026-08-13
verified_by: >
  In worktree agent-os-phase-1-adoption-326435 (created 2026-08-13 by the WorktreeCreate
  hook): git config core.sparseCheckout → true; git ls-tree --name-only HEAD lists
  site, data, mockups; ls shows none of the three on disk.
scope: [macro]
confidence: verified
---

## Detail

The sparse profile is applied by the account-level WorktreeCreate hook at worktree
creation (the repo itself carries no sparse config — `.claude/settings.json` has none),
so it is invisible in the repo tree and easy to rediscover the hard way. Detection must
read git (`git config core.sparseCheckout`, `git sparse-checkout list`), never
`is_dir()` on one path — partial cones make single-path checks lie in both directions.

Two failure shapes this produces, both observed classes rather than hypotheticals:
silent artifact truncation (the read-modify-write shape in `so_what`), and vacuously
green guards (a suite globbing `site/**` collects zero files and passes). The safe
sequence for any session touching the omitted trees is: materialize, verify the base
artifact is non-empty, then build.
