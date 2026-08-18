---
key: ALTERNATES-SHARE-OBJECTS-NOT-THE-PROMISOR
claim: >
  `objects/info/alternates` shares an object database and NOTHING else - not
  `extensions.partialClone`, not the promisor remote - so a repository that borrows a
  `blob:none` checkout's odb can read commits and trees but cannot materialize a working
  tree: `git checkout --detach --force <sha>` dies `error: unable to read sha1 file of
  <path>` on exactly the blobs that differ from the lender's checked-out tree, while
  `git rev-parse` and `git log` succeed throughout. That is what broke run_ci_pack.py's
  exact-base replay fleet-wide on 2026-08-18: ci.yml gives every pack
  `filter: blob:none` + `fetch-depth: 1`, so no base SHA could be checked out, every
  main-inherited red came back `classification=unknown`, and ship_loop_guard.py charged
  it to the PR under the INTERNAL ladder (10 consecutive / 15 total) instead of the
  external one (2 / 3). Two sub-facts make the repair non-obvious. (1) `git rev-list
  --objects --missing=print` CANNOT detect the absences: a blob a partial clone omitted
  is an EXPECTED absence and is never printed - measured, a tree with three genuinely
  missing blobs reported ZERO missing. The working detector is `GIT_NO_LAZY_FETCH=1 git
  cat-file --batch-check` fed the tree's blob OIDs, which prints `<oid> missing` and
  fetches nothing. (2) git's own lazy fetch issues one `git fetch` PER OBJECT (traced:
  3 blobs -> 3 fetches); the bulk form git uses internally is `git fetch <remote>
  --no-tags --no-write-fetch-head --recurse-submodules=no --filter=blob:none --stdin`
  with OIDs on stdin - one round trip, and no execve arg-length hazard.
falsifier: >
  Build a bare origin with `uploadpack.allowFilter=true`, clone it
  `--filter=blob:none --depth=1` at head, `git fetch --no-tags --depth=1 origin <base>`,
  then run `PACK._exact_base_worktree(work, base)` with the hydration call removed from
  `_ensure_exact_commit`: if the checkout succeeds, alternates do carry promisor
  capability and this is wrong. `tests/test_ci_pack_semantic.py::
  test_base_replay_checks_out_a_base_sha_inside_a_partial_clone` is that experiment
  standing. Equally: if `git rev-list --objects --missing=print <base>` in that fixture
  ever prints the omitted blobs, sub-fact (1) is refuted.
so_what: >
  Hydrate in the checkout that OWNS the promisor remote and its credentials, then let
  the borrower use the odb - never give a borrowing repository network configuration,
  which would defeat the isolation alternates were chosen for (the replay borrows an odb
  precisely so a base manifest's `git fetch origin main` cannot reach live main). When a
  git operation fails in a borrowed-odb or partial-clone context, do NOT reason from the
  SHA: `rev-parse` succeeding proves nothing about blob availability. And never test
  partial-clone behaviour against a bare origin without `uploadpack.allowFilter` - the
  server answers "filtering not recognized by server, ignoring" and hands back a
  COMPLETE clone, so the test passes vacuously while pinning nothing.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  PR #5879. Reproduced against a real `blob:none` fixture: pre-fix
  `git --git-dir <replay>/repository.git --work-tree <replay>/worktree checkout --detach
  --force <base>` -> `error: unable to read sha1 file of a.txt (d423074c)` + two more,
  exit 1 - the same CalledProcessError shape the guard reported on PR #5853 for two
  packs against two different bases, one minutes old.
  scripts/run_ci_pack.py `_exact_base_worktree` (alternates write + checkout),
  `_hydrate_exact_base_objects`, `_missing_tree_objects`, `_promisor_remote`;
  .github/workflows/ci.yml (pack checkout: `filter: blob:none`, `fetch-depth: 1`).
  `--missing=print` blindness measured on the same fixture (0 reported vs 3 real);
  per-object fetch count measured with `GIT_TRACE=1 git cat-file --batch-check`
  (3 x `trace: built-in: git fetch ... --stdin`). Detector cost on the live 69,251-blob
  tree: 3.7-8.9s against a 15-minute replay budget.
scope: [macro, scripts/run_ci_pack.py, .github/workflows/ci.yml]
confidence: verified
---

## Detail

The replay's isolation design is correct and is the reason the trap exists. A linked
worktree would share refs and remote configuration with the head checkout, letting a
base manifest's ordinary `git fetch origin main` substitute whatever main points to
later — so `_exact_base_worktree` builds a private bare repository whose refs, config
and index are its own and whose only `origin` branch is `main` pinned at the exact
replay SHA. It shares just the immutable object database, through alternates.

Alternates are exactly that narrow. They are a path to an object store; they carry no
configuration. In a full clone that distinction never surfaces, because every object the
borrower could want is genuinely in the lender's store. In a partial clone it is the
whole story: the lender's store is deliberately incomplete, and the thing that makes it
*work* — `extensions.partialClone` plus a promisor remote to go fetch on demand — lives
in config the borrower never sees.

The blobs that go missing are not arbitrary. The runner's head checkout materialized
every blob at the PR merge ref, so what is absent at the base commit is precisely the
base version of each file the PR changed — usually a handful. A replay that fails on the
PR's own changed files, on every base including one minutes old, looks like a base-SHA
problem and is not.

The diagnosis was invisible for a second reason worth separating: `CalledProcessError`
stringifies to "returned non-zero exit status 1" and drops the child's stderr, so every
downstream consumer saw a command line and an exit code while git's one explanatory line
existed only in the raw runner log. `_bounded_detail` now carries stderr. A classifier
that degrades to `unknown` reads as "probably your fault" to everything downstream, so
it must at least be able to say why it gave up.
