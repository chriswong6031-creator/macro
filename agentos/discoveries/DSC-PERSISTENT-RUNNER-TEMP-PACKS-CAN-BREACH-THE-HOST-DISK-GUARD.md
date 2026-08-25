---
key: PERSISTENT-RUNNER-TEMP-PACKS-CAN-BREACH-THE-HOST-DISK-GUARD
claim: >
  A clean persistent Actions checkout can consume hundreds of GiB through
  unreferenced `.git/objects/pack/tmp_pack_*` files even when its working tree
  and remote-tracking head are exact. On 2026-08-24 the drained M2
  `mac-builder-5` checkout was clean at current `origin/main` but held 27 files
  that `git count-objects -vH` classified as 260.24 GiB of garbage, leaving the
  2 TB APFS container only 19.4 GB free.
falsifier: >
  Re-run `git count-objects -vH` in the exact drained checkout and show that the
  named `tmp_pack_*` files are referenced packfiles or are not the reported
  garbage, or show that removing only those closed temporary files does not
  recover the corresponding APFS capacity while preserving a clean exact-main
  checkout.
so_what: >
  Do not judge a persistent runner checkout by `git status` or working-tree size
  alone. After an interrupted or failed large fetch, drain the listener, prove
  zero Workers and zero open handles, inspect `git count-objects -vH`, and remove
  only files Git classifies as pack-directory garbage. Feed recurrence prevention
  into the existing runner admission/cleanup lifecycle; do not add a second GC
  daemon or run blanket `git gc` while a listener is live.
kind: landmine
verified_at: 2026-08-24
verified_by: >
  Drained `/Users/chriswong/actions-runner-2`; `git status --short --branch
  --untracked-files=no`; `git rev-parse HEAD`; `git rev-parse
  refs/remotes/origin/main`; `git count-objects -vH`; exact `stat` and `lsof`
  census of 27 `.git/objects/pack/tmp_pack_*` files; exact-path removal of
  279435292497 bytes; post-removal `git count-objects -vH`, `git status`,
  `du -sh .git`, `diskutil apfs list`, and
  `ops/runner-host/m1/runner_disk_guard.py --mode full`.
scope: [macro, "ops/runner-host/**"]
confidence: verified
---

## Recovery receipt

Before recovery, the runner checkout was 288 GiB and its `.git` directory was
283 GiB. The checkout was on branch `main`; both `HEAD` and
`refs/remotes/origin/main` were
`a5485cd5e5585912d87fc36fc98c34ba1f3fea64`; tracked status was clean. Git
reported 95 referenced packs (14.09 GiB), 158,542 loose objects (8.96 GiB), and
27 garbage files (260.24 GiB). None of the 27 files had an open handle.

The listener was stopped before removal and restarted only after verification.
Removal targeted the 27 resolved regular files under the exact pack directory;
it did not touch referenced `.pack`/`.idx` files, the working tree, another
runner root, the retained PR #6286 oracle, or a foreign process. Afterwards Git
reported `garbage: 0`, the checkout remained clean at the same head, `.git`
measured 23 GiB, and APFS reported 303.6 GB unallocated at 84.8% used. The
existing disk guard returned `full_work_allowed=true` with 303,625,261,056 free
bytes and 30,962,601,984 work bytes.

This receipt proves the bounded recovery, not the exact producer of every
temporary pack. A future recurrence investigation must correlate pack creation
times with the runner's fetch/cancellation history before changing checkout or
maintenance semantics.
