---
key: SHARED-CLONE-PACK-STORM-STALLS-THE-FLEET
type: discovery
status: active
workstream: MARKET-OS
summary: >
  The one object store behind every session worktree (Macro Dashboard/.git, a blobless
  partial clone) had accumulated 71,232 pack files (85 GB) because every promisor fetch adds a
  pack and nothing consolidates them; at that count every object lookup scans 71k indexes, so
  `git status` took minutes, the Stop guard timed out, WorktreeCreate hooks were cancelled and
  three workflow build stages lost their worktrees on 2026-09-06. `git multi-pack-index write`
  (5 min, additive) restored sub-second git.
evidence:
  - "ls .git/objects/pack/*.pack | wc -l -> 71232; du -sh .git/objects -> 85G (Macro Dashboard/.git, 2026-09-06 07:1xZ)"
  - "ship_loop_guard Stop hook: Command git status --porcelain=v1 --untracked-files=all timed out after 260 seconds (twice, 2026-09-06 07:3x-07:5xZ); a one-file git add hung 40 minutes; load average 21-32 with 76 concurrent git processes; df -h showed 151 GiB free (not ENOSPC)"
  - "workflow failures: WorktreeCreate hook failed: python3 .claude/hooks/worktree_create_sparse.py: Hook cancelled (runs wf_df9c46ea-243, wf_f1b05540-853 x3, wf_aaaf6f7a-545 x2)"
  - "git multi-pack-index write --no-progress: 5:05 wall clock, 126,744,148-byte index; afterwards git log --oneline -2 = 0.096 s; load average 13.7 (scratchpad midx_write.log)"
falsifier: >
  If git commands stay slow after the multi-pack-index exists and the pack count is small
  (hundreds), the cause is something else (lock contention, network fetches on the promisor
  clone, or genuine ENOSPC); and if the pack count stays flat across a day of fleet activity,
  the "every fetch adds a pack" mechanism is wrong.
so_what: >
  When git crawls or a Stop-hook guard reports a git timeout, check the pack count BEFORE
  blaming the hook, the harness, or load. A multi-pack-index write is the safe first remedy
  (no repack, no temp-space risk on a host that has hit ENOSPC twice). The structural fix is
  scheduled maintenance on the shared clone — `git maintenance run --task incremental-repack`
  or a launchd job — which is an operator/DEC decision, not something a session should run
  ad hoc under a live fleet. Until then expect the count to climb again (~1 pack per fetch).
related:
  - "DSC:TERMINAL-REQUIRED-CHECK-HAS-NO-MASTER-PROOF"
  - "WS:MARKET-OS"
---

On 2026-09-06 the shared clone's 71,232 pack files made every git command take minutes and
stalled hooks and builders fleet-wide; a 5-minute `git multi-pack-index write` fixed it. Check
the pack count first next time; propose scheduled incremental-repack as the durable fix.
