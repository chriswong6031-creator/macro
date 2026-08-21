---
key: RENAME-IS-ATOMIC-FOR-THE-NAME-NOT-THE-INODE
claim: >
  `os.replace()` is atomic for the NAME only: a concurrent `lstat()` of the rename TARGET
  can observe the inode with `st_nlink == 0` while the rename is in flight, so any
  strict-ownership guard that asserts `st_nlink == 1` on a file another thread or process
  may be replacing is a latent flake, not a tamper detector. Measured 2026-08-21 on darwin:
  one writer looping create-temp-0600 -> `os.replace` against three observer threads
  produced 671 `nlink == 0` sightings in 6 seconds, with `mode`, `uid` and `S_ISREG` never
  once wrong. That is the whole of macro's `options-nbbo-cohort` flake: `_append_canonical_row`
  proved the ledger BEFORE taking `.events.lock`, so a sibling `append_event` mid-`_atomic_rewrite`
  made the guard raise `private event ledger must be owned 0600` about a ledger that was
  never anything but 0600. The obvious reading of that message - "the writer chmods after
  creating, so widen-then-narrow leaks a window" - is WRONG here and will send a session
  to rewrite a writer that is already correct: the temp file is created
  `O_CREAT|O_EXCL, 0o600` in one syscall and never chmod-ed. The defect is on the READER.
falsifier: >
  Run a writer thread doing `os.open(tmp, O_CREAT|O_EXCL, 0o600)` + `os.replace(tmp, target)`
  in a loop against observer threads calling `target.lstat()`; if no observer ever sees
  `st_nlink != 1`, this is refuted for that platform and filesystem.
  `tests/test_options_nbbo_cohort.py::test_event_append_proves_the_ledger_only_under_the_writer_lock`
  is the standing experiment - it hardlinks the ledger to stand in for the rename window and
  asserts the appending thread parks on the lock instead of stat-ing through it.
so_what: >
  Put the inode proof INSIDE the same lock that serializes the writers, never before it -
  moving the check is the fix, and rewriting the writer is wasted work. Two corollaries.
  (1) A guard message names the PREDICATE SET it failed, not which predicate failed:
  `mode/uid/isreg/nlink` all raise one string here, and only `nlink` was ever wrong - do not
  trust the message's noun when triaging. (2) The same shape lives elsewhere in this module
  and is unfixed: `verify_private_evidence` reads an evidence file with no store lock while
  `_write_private_bytes` publishes by `os.link(temporary, target)` and only then unlinks the
  temporary, so a reader can catch that target at `nlink == 2`. Reachable when two concurrent
  appends carry byte-identical evidence.
kind: landmine
verified_at: 2026-08-21
verified_by: >
  PR #6181. Symptom receipt: run 32461103221 attempt 1, job ci-pack-9 -> legacy job
  `options-nbbo-cohort`, `tests/test_options_nbbo_cohort.py:1853`; attempt 2 (a plain rerun,
  no code change) passed, which is what identifies it as a race rather than a break.
  Mechanism receipt: 671/6s `nlink == 0` sightings from the writer/observer harness above.
  A second, independent race in the same function - the check-then-create at
  `_private_file` (`if create and not resolved.exists(): os.open(..., O_EXCL)`) - surfaced
  at 4 failures / 480 concurrent-append iterations as `FileExistsError` on `.events.lock`;
  0 failures / 1200 iterations after both fixes.
  scripts/capture_options_nbbo_cohort.py `_private_file`, `_private_path`,
  `_append_canonical_row`, `_atomic_rewrite`.
scope: [macro, scripts/capture_options_nbbo_cohort.py, engine/options_nbbo_cohort.py]
confidence: verified
---

## Detail

The private-ledger design is sound and is the reason the trap is well hidden. Every writer
stages into a fresh `O_CREAT|O_EXCL, 0o600` temp file, fsyncs it, renames it over the ledger,
and fsyncs the parent directory — there is no moment at which a wider-than-0600 ledger exists
on disk, and the guard that asserts otherwise is right to be strict. So a report of
"must be owned 0600" reads as a real permissions defect, and the natural fix — create the
temp file at its final mode instead of chmod-ing it afterwards — is already what the code does.

What is not atomic is the *metadata* a concurrent reader sees. POSIX guarantees that a
`rename()` never leaves the target name absent or dangling; it says nothing about the link
count an interleaved `stat()` observes on either inode while the directory entry is being
re-pointed. The replaced inode's count is dropped as part of the same operation, and a reader
that resolves the name in that instant gets a `struct stat` describing an inode on its way out.
`nlink == 0` is not corruption and not a filesystem bug — it is a snapshot of a
legitimately transient state.

That makes the failure umask-independent and load-dependent, which is why it presents as a
hosted-runner-only flake: the window is a few microseconds wide, and only a machine that
actually preempts the reader inside it will ever see it. Scope-inferred runs on main do not
execute this legacy job at all, so main looked green throughout.

The reader was outside the lock for an understandable reason: `_append_canonical_row` needed
the ledger's *resolved* path to derive its sibling lock file, and resolving happened to be
bundled with proving. Splitting `_private_path` (path-level proof: absolute, non-symlink, not
inside the repository) from `_private_file` (inode-level proof plus creation) lets the lock
path be derived before the lock and the inode be proven after it, with no ordering weakened —
a ledger path that is relative, symlinked, or repo-internal is still rejected before anything
is created on disk.

The second race in the same function is the classic one and worth stating plainly because the
correct idiom is shorter than the wrong one: `if not path.exists(): os.open(path, O_EXCL)` is
never right. `O_CREAT|O_EXCL` already answers "did I create it, or did someone else" in a
single syscall; the `exists()` pre-check only adds a window in which both callers decide they
are the creator and one of them dies. Catching `FileExistsError` and falling through to the
validation that was going to run anyway is both safer and less code.
