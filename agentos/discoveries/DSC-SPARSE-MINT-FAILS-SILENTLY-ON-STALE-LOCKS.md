---
key: SPARSE-MINT-FAILS-SILENTLY-ON-STALE-LOCKS
claim: >
  `scripts/worktree_sparse.py`'s `refuse_if_locked` treated every
  `index.lock`/`info/sparse-checkout.lock` found in a worktree's git-dir as
  live and always refused — with no staleness notion — and that refusal was
  swallowed upstream by the harness, which reported the worktree as created
  and let the session proceed on a FULL (~6.5 GiB) checkout instead of the
  ~0.4 GiB sparse profile. Census 2026-09-06: 97 of 267 `.claude/worktrees/`
  session trees were FULL; the locks measured had ages of 600 to 3,500
  minutes with no live holder.
falsifier: >
  Run `python3 scripts/worktree_gc.py --report` (or an equivalent census over
  `.claude/worktrees/*`) and check whether any FULL tree's git-dir carries an
  `index.lock`/`info/sparse-checkout.lock` older than 10 minutes with no
  process holding that worktree or git-dir as cwd or an open file (`lsof -a
  -d cwd +D <worktree>`; `lsof +D <gitdir>`) — if none of the FULL trees show
  that pattern, the stale-lock theory does not explain the census and this
  claim is falsified for that population.
so_what: >
  Do not treat a lock found in a worktree's git-dir as automatic proof of a
  live concurrent operation, and do not silently accept a hook/CLI "success"
  report as proof a worktree ended up sparse. `scripts/worktree_sparse.py`
  (`refuse_if_locked`, `lock_is_stale`, `gather_live_processes`,
  `verify_sparse_postcondition`, `status_json`) and
  `.claude/hooks/worktree_create_sparse.py` (`apply_sparse`,
  `_clear_stale_locks`, `_verify_sparse_postcondition`,
  `_warn_if_reused_worktree_looks_full`) now self-heal a confirmed-stale lock
  (age >= `STALE_LOCK_MIN_AGE_S` = 600s AND no live process holding the
  worktree/git-dir) with a bare line-starting `::warning`, and fail LOUD
  (non-zero exit, bare line-starting `::error`) on a live/young/unconfirmed
  lock or a post-apply state mismatch — never a silent full checkout. A
  future census script should call `python3 scripts/worktree_sparse.py status
  --json` per worktree (reports `stale_locks_removed` as a side effect) rather
  than re-deriving lock staleness from scratch.
kind: landmine
verified_at: 2026-09-06
verified_by: >
  Read scripts/worktree_sparse.py's `refuse_if_locked` (origin/main, pre-fix):
  it named every found lock in an `::error` and returned True unconditionally,
  with no age or liveness check anywhere in the module. Read
  .claude/hooks/worktree_create_sparse.py's `apply_sparse` (pre-fix): it ran
  `git sparse-checkout init`/`set` directly with no lock check at all, and the
  `dest.exists()` reuse branch (main(), pre-fix) returned success on ANY
  already-registered worktree with no verification of its sparse state.
  Numbers (97/267 FULL, ages 600-3,500 min) as reported by the commissioning
  session's Meta-CEO B census + in-place sparsify pass, 2026-09-06.
scope:
  - macro
  - scripts/worktree_sparse.py
  - .claude/hooks/worktree_create_sparse.py
  - tests/test_worktree_sparse.py
  - research/WORKTREE_GC_POLICY.md
confidence: verified
---

`refuse_if_locked` refusing on every lock, forever, sounds safe — but a
refusal nobody checks the exit code of is worse than no check at all: it
looks like protection while behaving like a silent no-op. Age plus a real
liveness probe (`lock_is_stale`, `gather_live_processes` — both pure/testable
with an injectable process list) turns "always refuse" into "refuse only
while it still matters," and a post-apply `verify_sparse_postcondition` check
closes the other half: a `git sparse-checkout set` exiting 0 is no longer
trusted as proof the working tree actually ended up in the requested shape.
