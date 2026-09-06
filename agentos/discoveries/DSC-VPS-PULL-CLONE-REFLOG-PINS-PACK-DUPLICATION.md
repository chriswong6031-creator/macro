---
key: VPS-PULL-CLONE-REFLOG-PINS-PACK-DUPLICATION
claim: >
  The production VPS (146.190.142.17) pull clone at /opt/macro hit 100% root disk usage
  because a --depth 1 fetch every 3 minutes with gc.auto=0 never consolidates packs and
  the default 30-day gc.reflogExpireUnreachable window pins ~2M reflog-reachable objects,
  so only an explicit `reflog expire --expire-unreachable=now` before `repack -ad` (not a
  plain `git gc`) shrinks the store; remediation took root usage from 100% to ~51% used.
kind: landmine
verified_at: 2026-09-06
verified_by: >
  df -h /, git config gc.auto, git rev-parse --is-shallow-repository, git count-objects
  -vH, git rev-list --objects --all | wc -l, and git rev-list --objects --all --reflog
  | wc -l run against /opt/macro on the VPS 2026-09-06 (VPS_DISK_RECLAIM_PLAN_2026-09-06.md).
scope:
  - macro
  - "VPS /opt/macro (146.190.142.17 production pull clone)"
  - WS:MARKET-OS
confidence: verified
type: discovery
status: active
workstream: MARKET-OS
summary: >
  The production VPS (146.190.142.17) pull clone at `/opt/macro` ran its root filesystem
  from 100% used (756 MiB free) to a live-fill emergency because `/usr/local/bin/macro-update`
  runs `git -C /opt/macro fetch --depth 1 -q origin main` every 3 minutes with `gc.auto=0`
  and no consolidation: every tip-moving fetch writes a brand-new pack, nothing ever merges
  them, and the default 30-day `gc.reflogExpireUnreachable` keeps ~2M reflog-reachable
  objects alive so a plain `git gc`/repack cannot shrink the store — only an explicit
  `reflog expire --expire-unreachable=now` before `repack -ad` does. Remediated 2026-09-06:
  root went from 100% used to ~51% used (38 GiB free); repack -ad packed objects down to
  87,544 (from 3,115,777 in-pack) at 2.99 GiB. The daily recurrence-prevention cron line was
  proposed but NOT applied (needs ratification), so the box is expected to refill at
  roughly 1.35 GiB/day absent that fix.
evidence:
  - "df -h / before remediation: 'Filesystem Size Used Avail Use% Mounted on; /dev/vda1 77G 76G 756M 100% /' (VPS_DISK_RECLAIM_PLAN_2026-09-06.md #1)"
  - "git rev-parse --is-shallow-repository -> true; wc -l .git/shallow -> 9020 (9,020 accumulated shallow-boundary commits, sort -u = 9020, all distinct)"
  - "objects reachable from refs only (git rev-list --objects --all) = 87,544; objects reachable including reflogs (--all --reflog) = 2,030,464; objects actually in packs (git count-objects -vH) = 3,115,777 -> measured 35.6x duplication against what the served tree needs"
  - "git config gc.auto = 0 (explicitly disabled in /opt/macro/.git/config); 135 pack files present, dated 2026-08-25 to 2026-09-06 (13 days), refill rate excluding repack debris ~=1.35 GiB/day with 756 MiB free -> refill in ~12-18 hours"
  - ".git/gc.log (mtime 2026-08-28 05:10): 'fatal: failed to run repack' -- a past repack attempt ran out of space mid-write; three of the 135 packs (4.55 GiB / 6.05 GiB / 5.92 GiB, dated 2026-08-25/08-26/09-01) are prior repack OUTPUTS whose predecessor packs were never deleted -- 16.5 GiB (48% of the 34 GiB) was partial-repack debris, not fresh fetch packs"
  - "reflog holds 6,225 entries on HEAD/refs/heads/main and 6,203 on origin/main, spanning 2026-07-29 -> 2026-09-06 -- exactly the ~30-day gc.reflogExpireUnreachable default plus change, the fingerprint of a past gc that trimmed to 30 days and stopped"
  - "Remediation (META_CEO_B_NOTES.md 2026-09-06 16:40Z): 'VPS: root 100% -> 51% (38 GiB free). Cause = reflog-pinned 35x pack duplication ... Did: SAFE-NOW cache cleanup, reflog expire, archived /opt/terminal/_tctest (4.9 GiB, 2026-07-07 hand copy) ... then removed it, repack -ad (in-pack 87,544, size-pack 2.99 GiB, prune ok).'"
  - "Recurrence cron line proposed to the Chairman, NOT applied: '23 6 * * * flock -w 1800 /var/lock/macro-update.lock bash -c \"git -C /opt/macro reflog expire --expire=now --expire-unreachable=now --all && git -C /opt/macro -c pack.threads=1 -c pack.windowMemory=256m repack -adq --window=10 --depth=50 && git -C /opt/macro prune --expire=now\"' (META_CEO_B_NOTES.md 16:40Z)"
  - "This is a DIFFERENT clone from DSC:SHARED-CLONE-PACK-STORM-STALLS-THE-FLEET (that record is the Mac Studio session-worktree clone at 'Macro Dashboard/.git', fixed with a multi-pack-index write; this record is the VPS's separate /opt/macro shallow pull clone, fixed with reflog-expire + full repack because multi-pack-index does not reclaim disk on this clone)"
falsifier: >
  If the pack count and disk usage at /opt/macro stay flat over several days WITHOUT the
  recurrence cron applied, the "every 3-minute fetch adds a pack, gc.auto=0 prevents
  consolidation" mechanism is wrong. If a plain `git gc` (no explicit
  `reflog expire --expire-unreachable=now`) is later observed to shrink the store to the
  refs-only object count, the "30-day reflogExpireUnreachable blocks gc" claim is wrong. If
  `git multi-pack-index write` is later observed to reduce `du -sh .git/objects` on this
  clone, the "MIDX does not reclaim disk, only in-place repack does" claim is wrong.
so_what: >
  Before touching this VPS clone again: check `git count-objects -vH` (in-pack) against
  `git rev-list --objects --all | wc -l` (refs-only) before assuming a `git gc` or a
  multi-pack-index write will free space on a bytes-exhausted host -- neither does here.
  The safe sequence when free space is thin is SAFE-NOW cleanup (journal/apt/crash) first,
  then an owner-approved one-off deletion (e.g. an untouched hand-made copy) to buy repack
  headroom, THEN `reflog expire --expire-unreachable=now --all` followed by
  `repack -adq --window=10 --depth=50` under the host's existing update lock -- never a
  bare `repack -ad` first, which can fail mid-write on a near-full disk (as it did on
  2026-08-28) and leave debris packs that make the problem worse. The daily cron fix is
  proposed, not applied; until an operator/Chairman ratifies it, expect this host to refill
  at ~1.35 GiB/day and re-approach exhaustion within weeks.
related:
  - "DSC:SHARED-CLONE-PACK-STORM-STALLS-THE-FLEET"
  - "WS:MARKET-OS"
---

On 2026-09-06 the VPS pull clone at `/opt/macro` hit 100% root disk usage because a
`--depth 1` fetch every 3 minutes plus `gc.auto=0` never consolidates packs, and the
default 30-day reflog-expiry window keeps ~2M reflog-reachable objects alive so a plain
`git gc` cannot shrink the store. Remediation (reflog expire --expire-unreachable=now,
then repack -ad, then prune) took root usage from 100% to ~51% (38 GiB free), packing
87,544 refs-reachable objects into a 2.99 GiB pack. The recurrence-prevention daily cron
line is written but not yet applied -- it needs ratification before the fix is durable.
