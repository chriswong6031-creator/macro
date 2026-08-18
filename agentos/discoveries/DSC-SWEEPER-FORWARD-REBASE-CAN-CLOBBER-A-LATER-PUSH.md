---
key: SWEEPER-FORWARD-REBASE-CAN-CLOBBER-A-LATER-PUSH
claim: >
  The `merge-on-green` sweeper's forward-rebase can land a PR head that OMITS a commit the
  session pushed, and the omission is invisible from the PR page because the head still
  carries the session's own commit message. Measured 2026-08-18 on PR #5882: the session
  pushed `b8f7863914cb` (a second commit reverting one file and editing two others); the
  merged head was `c34faa64f448` — a SHA the session never created, parented directly on
  main commit `18d6159aa5b6`, carrying ONE commit with the session's ORIGINAL headline. The
  second commit is absent from that head's history, so BOTH halves of it were lost: the code
  revert AND the documentation edits that described the revert. The squash merge
  (`120f77a7e8e4`) therefore shipped the file content the session had deliberately removed.
falsifier: >
  Exhibit a merged head that contains every commit the session pushed —
  `git log --oneline <mergedHead> | grep <later commit subject>` returning a hit where this
  case returns 0 — or a sweep log showing the rebase was computed from the session's NEWEST
  head rather than an earlier snapshot. Or show `b8f7863914cb` is an ancestor of
  `c34faa64f448` (`git merge-base --is-ancestor` — here it is not).
so_what: >
  A pushed commit is NOT proof that its content merged. After any sweeper-assisted merge,
  verify the MERGED BYTES on origin/main, not your local branch and not the PR file list —
  `git show origin/main:<path>` for anything you changed late, and
  `git show --stat <mergeCommit>` to see which paths the merge actually carried. This
  session asserted "the arming was cut" on the strength of its own push and was wrong; the
  arming was live on main.
  Second, and the sharper hazard: because the dropped commit carried BOTH the code change
  and the doc change describing it, the merged tree stayed internally CONSISTENT — records
  and code both from the earlier commit — so no guard, test or reviewer could see anything
  amiss. Consistency is not evidence that what you intended shipped. A later commit that
  documents its own code change is exactly the shape whose loss is undetectable.
  Third, if the late commit MATTERS (a safety cut, a revert, a scope reduction), do not
  rely on the sweeper: re-read `headRefOid` after the sweep and before treating the merge as
  yours, and prefer landing a safety cut as its OWN pull request rather than as a follow-up
  commit on an armed one.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  PR #5882. Pushed head `b8f7863914cb` — `git show b8f7863914cb:.github/workflows/government-revenue-live.yml
  | grep -m1 GOVREV_CANDIDATE_PROOF_FATAL` -> `"0"`. Merged head per
  `gh pr view 5882 --json headRefOid,mergeCommit` -> head `c34faa64f448`, mergeCommit
  `120f77a7e8e4`. `git show c34faa64f448:<same path>` -> `"1"`.
  `git log --oneline c34faa64f448 | grep -c "cut the proof-gate flip"` -> 0.
  `git log --oneline -3 c34faa64f448` shows parent `18d6159aa5b6` (a main commit), i.e. one
  commit rebased directly onto a newer main. `git show --stat 120f77a7e8e4` lists
  `.github/workflows/government-revenue-live.yml | 38 ++-` among 7 files.
  Live confirmation: `git show origin/main:.github/workflows/government-revenue-live.yml |
  grep -m1 GOVREV_CANDIDATE_PROOF_FATAL` -> `"1"`.
scope:
  - macro
  - scripts/merge_on_green.py
  - .github/workflows/merge-on-green.yml
confidence: verified
---

## Detail

### Why this is worse than "the sweeper rewrites the head"

That the sweeper rewrites `headRefOid` is already recorded and is expected — it rebases an
armed PR forward so a base-inherited red can be re-classified. The new fact is that the
rewritten head can be missing a commit the session pushed, while still presenting the
session's own commit message. Nothing on the PR page says "your second commit is gone."

The most likely mechanism, stated as the hypothesis it is: the sweeper computed its
forward-rebase from a snapshot of the branch taken before the session's later push landed,
then force-updated the ref with the result — clobbering the newer commit. That is consistent
with the single-commit head parented straight onto a newer main, but this session did not
capture a sweep log, so the mechanism is inference; the OBSERVATION (pushed commit absent
from merged head) is measured.

### The consistency trap

The lost commit contained a code revert *and* the documentation of that revert. Losing both
left main coherent: `DEC:GOVREV-CANDIDATE-PROOF-GATE-ARMED` says "YES — arm it", the handoff
`changed[]` says "flipped from 0 to 1", and the workflow says `"1"`. Every one of those
agrees with every other. A reviewer, a test, and the agentos validator all see a clean tree.

So the usual defence — "the records would have caught it" — does not apply. Only comparing
the merged bytes against what you *intended* catches this, which is why the `so_what` above
is phrased as a byte check against `origin/main` rather than a records check.

### What was NOT wrong here

The shipped outcome is the one the DEC endorses and the session had verified (precondition
met, 92 passed across the three proof suites, no wiring mirror, and the gate only fires when
candidate artifacts changed AND the suites genuinely fail). The cut was made for merge
mechanics under a fleet-wide main red, not for safety. So this record is about a machinery
hazard and an epistemic lesson, not about a bad change reaching main.
