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
  temporary, so a reader can catch that target at `nlink == 2`. FIXED in PR #6186 - and the
  reachability guess in this line was WRONG, see the amendment below.
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

## Amendment 2026-08-21 (PR #6186) — the sibling window is closed, and its stated reachability was wrong

The `so_what` corollary (2) was right that `verify_private_evidence` read the evidence store
with no store lock, and right about the mechanism. PR #6186 closed it: the three readers
(`verify_private_evidence`, `verify_event_evidence`, `verify_capture_evidence`) now prove the
inode under `_private_store_lock`, with the loop functions holding it once for a whole sweep
via the same `_store_locked: bool = False` passthrough `_write_private_bytes` already used.

**But "Reachable when two concurrent appends carry byte-identical evidence" is REFUTED.**
Measured on darwin 2026-08-21: 300 rounds × 4 threads appending byte-identical evidence to one
private root, against the PRE-FIX engine, produced **1,200 appends and 0 failures** — and still
0 at 4 ms of artificial widening injected between `os.link` and the temporary's `unlink`. The
same result for 1,200 plain concurrent `append_event` calls.

Two structural reasons, both worth knowing before hunting this shape again:

1. **The whole link→unlink window is already inside `.store.lock`.** `_write_private_bytes`
   recurses into itself *inside* `with _private_store_lock(root)` when `_store_locked=False`,
   so the `finally: temporary.unlink()` runs under the lock too. Only a reader that skips the
   lock can observe `nlink == 2` — which is exactly what made this a reader-side defect, and
   also why no *writer* ever sees it.
2. **Every publisher writes evidence BEFORE its row becomes visible.** `append_event` and
   `append_capture_receipt` call `write_private_evidence` and only then `_append_canonical_row`.
   So any event a concurrent verifier can read from the ledger already has fully-published
   evidence, and a verifier reading the ledger can never be pointed at a digest mid-publish.

What remains genuinely exposed is the caller-held-receipt shape, not the ledger-read one:
`scripts/capture_options_nbbo_cohort.py:285` verifies a receipt the caller is holding rather
than one read back from the ledger, which is one concurrent actor away from the window.

**So the fix is defense-in-depth, not an active-flake repair** — unlike the `_append_canonical_row`
race this record was minted for, which had a real CI receipt. Do not go looking for a red
`options-nbbo-cohort` run to blame on this one; there isn't one.

Proof that the window is nonetheless real, and that the fix is what closes it: against the
GENUINE `_write_private_bytes` publisher with its `os.link` slowed (no hardlink stand-in), a
concurrent `verify_private_evidence` raises `producer evidence must be an owned private 0600
file` pre-fix and is clean post-fix. The standing experiment is
`tests/test_options_nbbo_cohort.py::test_evidence_verifiers_prove_the_inode_only_under_the_store_lock`.

Still unfixed, and deliberately out of #6186's scope: `_read_source_response` and
`read_observations` call `_validate_private_file` with no store lock. Both their writer
(`write_source_response`, :3348) and their reader (:3226) sit inside `_advance_locked` under
`.advance.lock`, so they are serialized and not concurrently reachable today — the exposure is
latent on that serialization holding, not on the lock they skip.

A trap for whoever writes the next test here: cleaning up a hardlink stand-in AFTER releasing
the store lock makes the test flaky rather than the code — the woken reader stats a target that
really is still at `nlink == 2` and fails honestly. Measured 4/25 (16%) before the cleanup was
moved inside the `with`; 25/25 after.
