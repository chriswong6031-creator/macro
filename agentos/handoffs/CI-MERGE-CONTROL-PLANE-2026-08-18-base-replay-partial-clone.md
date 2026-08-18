---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude-base-replay-partial-clone-hydration
model: opus
ended_because: complete
mission: >
  The CI semantic base-replay could not check out ANY base SHA, so every
  main-inherited red on the fleet was reported `classification=unknown` and
  ship_loop_guard.py charged it to the PR under the INTERNAL block ladder
  (10 consecutive / 15 total) instead of the external one (2 / 3). Find the
  real cause, fix classification (never make `unknown` permissive), and make
  the next occurrence diagnosable from the report alone.
state_before: >
  Reported from PR #5853's guard output: two packs (3 and 6), two separate
  `ci-base-replay-*` temp clones, two different base SHAs — one of them
  minutes old after a fresh rebase — all failing identically with
  `Command '[... 'checkout', '--detach', '--force', <base>]' returned non-zero
  exit status 1`. No stderr anywhere in the record, so every downstream
  consumer saw a command line and an exit code. Main was independently red
  (ci-pack-5, ci-pack-6, ci-gate on run 32110254994), which the broken
  classifier could not attribute.
changed:
  - path: scripts/run_ci_pack.py
    what: >
      `_hydrate_exact_base_objects` + `_missing_tree_objects` +
      `_promisor_remote`, called from `_ensure_exact_commit` — a commit whose
      blobs cannot be read is not acquired. `_git_run_bounded` gains `env` and
      `stdin_text`. The checkout drops `capture_output=False`, and
      `_describe_failure` makes `_bounded_detail` carry a failed child's own
      stderr instead of only its exit status.
  - path: tests/test_ci_pack_semantic.py
    what: >
      Three fixtures: the partial-clone replay regression (with its own
      vacuity guard), the no-promisor no-op, and the stderr-in-detail pin.
  - path: agentos/discoveries/DSC-ALTERNATES-SHARE-OBJECTS-NOT-THE-PROMISOR.md
    what: the landmine record, with both sub-facts that make the repair non-obvious.
verified:
  - claim: >
      the defect reproduces against a real `blob:none` clone, and the new test
      fails without the fix with the SAME CalledProcessError the guard reported
    command: >
      remove the `_hydrate_exact_base_objects` call from `_ensure_exact_commit`,
      then python3 -m pytest tests/test_ci_pack_semantic.py -q -k partial_clone
    result: >
      1 failed — `Command '['git','--git-dir',...,'checkout','--detach',
      '--force','af923c3e...']' returned non-zero exit status 1`; restored, 1 passed.
  - claim: raw git stderr names the real cause once captured
    command: hand-built replay clone against a blob:none fixture, capture_output=True
    result: >
      "error: unable to read sha1 file of a.txt (d423074c)" + two more,
      then "error: invalid object 100644 f38345ce for 'sub/b.txt'", exit 1.
  - claim: >
      `git rev-list --objects --missing=print` cannot detect partial-clone
      omissions, so it is NOT a usable detector
    command: git rev-list --objects --missing=print <base> in the blob:none fixture
    result: 0 reported missing against 3 genuinely missing blobs.
  - claim: git's lazy fetch is one round trip PER OBJECT
    command: GIT_TRACE=1 git cat-file --batch-check < 3 missing OIDs
    result: >
      3 x "trace: built-in: git fetch origin --no-tags --no-write-fetch-head
      --recurse-submodules=no --filter=blob:none --stdin"; the bulk --stdin
      form hydrates all three in ONE.
  - claim: the replay now yields the BASE tree's content, not merely the base ref
    command: PACK._exact_base_worktree(work, base) over the blob:none fixture
    result: >
      HEAD == base, changed.txt == "base", untouched.txt == "shared",
      `git status --porcelain` empty.
  - claim: hydration is affordable on the live tree
    command: _missing_tree_objects / _hydrate_exact_base_objects against origin/main
    result: 8.9s cold, 3.7s warm over 69,251 blobs, against a 15-min replay budget.
  - claim: no regression in the owning suites
    command: python3 -m pytest tests/test_ci_pack_semantic.py tests/test_ci_pack.py tests/test_ci_semantic_proof.py -q
    result: 162 passed in 438s.
unverified:
  - claim: the classifier resolves a real main-inherited red on a live PR head
    what_would_verify: >
      after merge, a PR whose pack reds are inherited should report a
      `classification` other than `unknown` with a `tested_tree_sha` at the
      base. This session could not observe it: the fix must be ON main for a
      pack to run it, and main was independently red throughout.
unresolved:
  - >
    Main's own reds (ci-pack-5, ci-pack-6, ci-gate) are NOT this lane's and are
    owned elsewhere: #5874 (main-red-repair, Prophet Board-read keys), #5875 /
    #5877 (stock-identity B rescale banded on uniformity, not level). This PR
    touches scripts/**, so it is authority-changing and cannot lean on a
    base-inherited red — it needs main itself green. That is the only thing
    between it and the merge.
next_actions:
  - >
    After merge, read one real PR's base_replay record: `outcome` should not be
    "unavailable", and a genuine failure should now carry git's stderr in
    `detail` rather than an exit status alone.
  - >
    If a replay ever reports "exact-base hydration left N object(s)
    unresolved", that is the loud form of this bug and names the residual OIDs
    plus the fetch stderr. Treat it as a promisor/credential problem on the
    runner checkout, not as a base-SHA problem.
do_not_redo:
  - >
    Do NOT make `classification=unknown` permissive to unpin the fleet. It
    would let a genuinely PR-owned red merge. The fix is to make
    classification work.
  - >
    Do NOT give the replay repository a promisor remote or copy the runner's
    `http.<url>.extraheader` into it. The replay borrows an odb precisely so it
    has no network configuration and no capability — a base manifest's ordinary
    `git fetch origin main` must not be able to reach live main, and the child
    env allowlist exists to keep Actions/OIDC tokens out. Hydrate in the head
    checkout, which already holds both.
  - >
    Do NOT use `git rev-list --objects --missing=print` as the detector, and do
    NOT drop `GIT_NO_LAZY_FETCH=1` from the `cat-file` probe — without it the
    probe silently becomes the slow per-object fix and reports nothing missing.
  - >
    Do NOT convert the replay back to a linked worktree to dodge this. The
    isolation is deliberate and documented in `_exact_base_worktree`.
danger_areas:
  - >
    Any test of partial-clone behaviour needs a bare origin with
    `uploadpack.allowFilter=true`. Without it the server answers "filtering not
    recognized by server, ignoring" and hands back a COMPLETE clone — the test
    passes and pins nothing. The new regression asserts the missing-blob
    precondition for exactly this reason; do not weaken that assertion.
  - >
    `_bounded_detail` now carries child stderr into published semantic
    evidence. It stays bounded by SEMANTIC_DETAIL_MAX_BYTES and one-lined, but
    anything newly written to a failing command's stderr is now more visible.
  - >
    scripts/** is authority-changing: this PR needs main ITSELF green, not
    merely a base-inherited excuse.
---

Cold-stranger note: the surprise is not the fix, it is the detector. The natural
first move — `git rev-list --objects --missing=print <base>` — reports ZERO
missing objects on a tree with genuinely missing blobs, because a blob a partial
clone omitted is an *expected* absence. Anyone who starts there will conclude the
odb is fine and go looking at the base SHA, which is exactly the wrong end; the
SHA resolves perfectly (`rev-parse` and `log` both succeed) and only the working
tree materialization fails. Start instead from git's own stderr — captured, it
says `unable to read sha1 file of <path>` and names the blob.
