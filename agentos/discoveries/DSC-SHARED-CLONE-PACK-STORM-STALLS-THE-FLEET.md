---
key: SHARED-CLONE-PACK-STORM-STALLS-THE-FLEET
claim: >
  The one object store behind every session worktree (Macro Dashboard/.git, a blobless
  partial clone) accumulates one pack file per promisor fetch with nothing consolidating
  them; at 71,232 packs (85 GB) every object lookup scanned every index, `git status` took
  minutes, the Stop guard timed out, WorktreeCreate hooks were cancelled and workflow build
  stages lost their worktrees, and `git multi-pack-index write` (5 min, additive) restored
  sub-second git.
falsifier: >
  If git commands stay slow after `git multi-pack-index write` while the pack count is small
  (hundreds), the cause is something else (lock contention, promisor network fetches, or real
  ENOSPC); and if `ls .git/objects/pack/*.pack | wc -l` stays flat across a day of fleet
  activity, the "every fetch adds a pack" mechanism is wrong.
so_what: >
  When git crawls or a Stop-hook guard reports a git timeout, check the pack count BEFORE
  blaming the hook, the harness, or load. A multi-pack-index write is the safe first remedy
  (no repack, no temp-space risk on a host that has hit ENOSPC twice). The structural fix is
  scheduled maintenance on the shared clone (`git maintenance run --task incremental-repack`
  or a launchd job), an operator/DEC decision, not something a session should run ad hoc
  under a live fleet. Until then expect the count to climb again (~1 pack per fetch).
kind: landmine
verified_at: 2026-09-06
verified_by: >
  Meta-CEO B session 7cd4fae1, 2026-09-06 07:1xZ: `ls .git/objects/pack/*.pack | wc -l` ->
  71232 and `du -sh .git/objects` -> 85G in Macro Dashboard/.git; ship_loop_guard Stop hook
  "git status --porcelain=v1 --untracked-files=all timed out after 260 seconds" (twice); load
  average 21-32 with 76 concurrent git processes and 151 GiB free; workflow failures
  "WorktreeCreate hook failed: Hook cancelled" (runs wf_df9c46ea-243, wf_f1b05540-853 x3,
  wf_aaaf6f7a-545 x2); `git multi-pack-index write --no-progress` took 5:05 wall clock and
  wrote a 126,744,148-byte index, after which `git log --oneline -2` took 0.096 s.
scope:
  - macro
  - macro:.git/objects/pack
  - macro:.claude/hooks/worktree_create_sparse.py
  - WS:MARKET-OS
confidence: verified
related:
  - "DSC:TERMINAL-REQUIRED-CHECK-HAS-NO-MASTER-PROOF"
  - "WS:MARKET-OS"
---

On 2026-09-06 the shared clone's 71,232 pack files made every git command take minutes and
stalled hooks and builders fleet-wide; a 5-minute `git multi-pack-index write` fixed it. Check
the pack count first next time; propose scheduled incremental-repack as the durable fix.
