---
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: warp/warp-955c8a92221b4f309db256c3faa58a73
model: codex
ended_because: blocked
mission: >
  Continue private-repository compute readiness by independently adjudicating
  M1 W2/TerraMaster evidence, preserving W4's capability boundary, recovering
  the M2 from a live disk-pressure breach, and rechecking the PC gate without
  changing CI routes, runner labels, repository visibility, or either held PR.
state_before: >
  Current main still described the M1 12-hour soak and TerraMaster identity as
  outstanding. The PC WSL management path was unreachable. PR #6286 remained
  the sole held ci.yml carrier. During the fresh host guard the M2 APFS container
  had only 19.4 GB unallocated, three Runner.Workers were observed, and the
  `mac-builder-5` `_work` tree measured 289 GiB.
changed:
  - path: agentos/discoveries/DSC-PERSISTENT-RUNNER-TEMP-PACKS-CAN-BREACH-THE-HOST-DISK-GUARD.md
    what: >
      Records the clean-checkout temporary-pack landmine and the exact bounded
      M2 recovery receipt so another session does not misdiagnose the pressure as
      tracked data, ordinary worktree size, or a reason to recruit M4 capacity.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Accepts the terminal M1 listener soak, records TerraMaster's scratch-only
      qualification and M2 recovery, and keeps W2/W4/private-cutover gates honest.
  - path: agentos/handoffs/RUNNER-FLEET-RESILIENCE-2026-08-24-m1-terra-m2-recovery.md
    what: >
      Provides the exact continuation boundary for M1 storage, PC Wave B/C,
      #6286/Sol, trusted-CI cutover and post-cutover telemetry.
verified:
  - claim: >
      The older M1 W2 listener soak is a terminal positive 12-hour receipt.
    command: >
      On host `m1`, inspect
      `/Users/chriswong/runner-recovery-receipts/20260821-w2w3/m1-soak-20260821T080442Z/soak.log`
      with `wc -l`, `shasum -a 256`, bounded head/tail reads, and counts of
      SAMPLE_INDEX, SERVICE, RUNNER_DISK_GUARD, PID_SET, identity mismatches,
      lightweight/full verdicts, ENOSPC text and SOAK_MONITOR_COMPLETE.
    result: >
      SHA-256 b5baf6044615328e8fed16319234d71738cb7f0542cd42b9f6d8f620dd925293;
      73 samples from 2026-08-21T08:07:28Z through 20:07:56Z; 219 exact service
      and guard observations; three distinct expected listener PIDs in all 73
      samples; zero identity mismatch; lightweight allowed in all 219 guard
      rows; full work allowed in zero; zero ENOSPC; terminal completion present;
      monitor exited.
  - claim: >
      The newer Aug-24 W2 monitor is incomplete and supplies no competing
      terminal authority.
    command: >
      On host `m1`, inspect
      `/Users/chriswong/runner-guard/receipts/W2_M1_12H_SOAK_20260824T091217Z.jsonl`,
      its line count/tail, process table and open writers.
    result: >
      Header plus 16 clean samples through 2026-08-24T12:57:16Z; no terminal
      line, no monitor process and no open writer. It was not restarted because
      the independent Aug-21 receipt already satisfies the terminal listener
      soak.
  - claim: >
      TerraMaster is currently identifiable and qualified only as disposable,
      non-secret scratch.
    command: >
      `diskutil info /Volumes/Mastermind`; shallow census and size check of
      `/Volumes/Mastermind/Mastermind/scratch/runner-fleet`.
    result: >
      External 4 TB solid-state APFS volume; UUID
      7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A; SMART verified; PCI-Express;
      ownership disabled; unencrypted; approximately 3.9 TB free. The reversible
      M1 recovery set occupies about 69 GiB. It is not authorized for secrets,
      runner roots or canonical state.
  - claim: >
      M1 storage remains below the full-work floor and W4 remains unadmitted.
    command: >
      On host `m1`, `df -h /`, process census and launchd service census.
    result: >
      Approximately 110 GiB free; the latest guard sample reported
      118,800,756,736 free bytes, 75.97% used, lightweight allowed and full work
      refused. Three guarded listeners remain present; no generic macstudio or
      other W4 production label/route was added.
  - claim: >
      The PC native recovery gate has not changed.
    command: >
      One bounded non-interactive SSH probe with password and keyboard-interactive
      authentication disabled to `winpc-wsl`, plus Computer Use app census for an
      existing Windows/Remote Desktop session.
    result: >
      SSH to 100.121.5.60:22 timed out with exit 255. No existing Windows App or
      Remote Desktop control session was available on this Mac. No second restart,
      network mutation, canary dispatch, listener change or production route change
      occurred.
  - claim: >
      The M2 disk-pressure breach came from Git-classified temporary pack garbage
      in a clean exact-main persistent runner checkout and was recovered without
      touching active work.
    command: >
      Drain `actions-runner-2` and `actions-runner-3`; inspect exact checkout head,
      tracked status, `_work` sizes, `git count-objects -vH`, exact file stat and
      open handles; remove only the validated 27 regular `tmp_pack_*` paths;
      re-run Git status/object census, APFS census and runner disk guard; restart
      the two drained services after acceptance.
    result: >
      `mac-builder-5` was clean at current main
      a5485cd5e5585912d87fc36fc98c34ba1f3fea64. Its `.git` held 27 closed garbage
      files totaling 279,435,292,497 bytes. Post-removal Git reports zero garbage,
      `.git` fell from 283 GiB to 23 GiB, APFS rose from 19.4 GB to 303.6 GB
      unallocated, the checkout stayed clean at exact main, the disk guard returned
      full_work_allowed=true, and both drained listeners restarted successfully.
  - claim: >
      Held authority and hardware boundaries were preserved.
    command: >
      Fresh `gh pr view` receipts before the shared API quota was exhausted;
      repository diff and service/route census.
    result: >
      PR #6286 stayed OPEN/DRAFT at
      7fe2a5604f4938161b2630f6f6c15d8d436a3822 with no label or auto-merge; held
      records PR #6367 stayed OPEN/DRAFT at
      986fc6279005935d6d964d7229b1a9309a3df25f with no label or auto-merge. No
      workflow, runner label/group, visibility, M4, or production CI route changed.
unverified:
  - claim: >
      The precise workflow interruption or fetch command that created each of the
      27 temporary pack files.
    what_would_verify: >
      A recurrence with creation timestamps and exact runner/job/fetch logs, or a
      retained pre-deletion filesystem timestamp manifest correlated to concluded
      jobs. The bounded recovery proves the garbage class and pressure effect, not
      the producer.
  - claim: >
      M1 has completed checksum/metadata parity for the whole fixed inactive clone
      set and safely recovered at least 200 GiB free.
    what_would_verify: >
      Resume the existing hardlink-preserving copy only in a fresh all-idle M2
      window; exact `rsync -aHcni --delete` parity; recover only verified inactive
      explicit source paths; then re-run the M1 disk guard.
  - claim: >
      PC Wave B/C can sustain one exact-tree CI slot and then three CI slots plus
      one independent render slot.
    what_would_verify: >
      Native Windows WSL wake followed by the bounded runbook acceptance sequence
      with exact-tree parity, contamination isolation, cache-negative refusal,
      resource telemetry and render-reservation proof.
  - claim: >
      The final private-ready hosted projection has meaningful headroom below the
      50,000-minute allowance.
    what_would_verify: >
      Sol acceptance of #6286 and PC capacity; main-defined trusted-CI cutover;
      representative natural post-cutover enhanced-billing and queue/resource
      telemetry; a Sol-accepted acceptance packet.
unresolved:
  - >
    A native Windows operator must run
    `wsl.exe -d Ubuntu-24.04 --exec /bin/true` or open Ubuntu-24.04 once. Until
    that happens, PC DNS/cache/listener and canary work remains fail-closed.
  - >
    M1 source recovery remains reversible and partial. Do not resume while the M2
    has Runner.Workers or unrelated heavy Git/pytest activity; do not delete any
    source path before full fixed-set checksum and metadata parity.
  - >
    PR #6286 remains the sole ci.yml carrier under Sol's hold. PR #6367 is a stale
    held records packet and is evidence only; neither hold authorizes mutation or
    a replacement carrier.
  - >
    GitHub's shared REST quota was exhausted after the bounded current-state read.
    Do not replace it with jobs-API fan-out or weaken merge/authority proof.
next_actions:
  - >
    After the native Windows WSL wake, re-pin current main, prove DNS/HTTPS/broker/
    Tailscale/mount/resource health, advance the root-owned cache, disable but do
    not delete legacy pc-render-2/3/4, prove unique pc-render-1 reservation, then
    execute one-slot/two-tree and three-CI-plus-one-render acceptance. No production
    route change in that packet.
  - >
    Resume the existing M1 fixed-set recovery only on a fresh all-idle M2 guard;
    finish hardlink-preserving parity and recover only verified inactive source
    paths until the M1 guard reports at least 200 GiB free and below 85% used.
  - >
    Keep W4 held. After W2 storage acceptance, commission at most one
    capability-specific M1 lane; generic macstudio remains forbidden.
  - >
    Wait for an explicit Sol accept/reject/release on #6286. Only after that and
    PC capacity acceptance may a new carrier add the main-defined bounded trusted
    executor and route expensive same-repository packs through it.
  - >
    After natural production cutover observations, re-measure hosted billing,
    queue pickup/completion, cancellation amplification and PC/M1/M2 resources.
    Return the Sol private-cutover packet and stop before visibility mutation.
do_not_redo:
  - >
    Do not restart another M1 listener soak; the Aug-21 terminal receipt is the
    accepted listener-continuity proof. Storage readiness remains a separate gate.
  - >
    Do not blanket-delete runner checkouts or run Git maintenance while a listener
    is live. The M2 recovery removed only Git-classified, closed temporary-pack
    garbage after drain and exact-main proof.
  - >
    Do not create another runner GC/lifecycle plane. Recurrence prevention belongs
    in the existing `ops/runner-host` admission/cleanup substrate after the producer
    is measured.
  - >
    Do not fork, rebuild, ready, arm, merge or replace #6286, and do not mutate the
    stale held #6367 packet without Sol release.
  - >
    Do not use generic macstudio on M1, move protected hosted control/untrusted jobs
    to persistent home runners, recruit M4 hardware, or change repository visibility.
danger_areas:
  - >
    `parked` does not prevent GitHub assignment. A listener must be drained/stopped
    before inspecting or removing its checkout state.
  - >
    `git status` can be clean while `.git/objects/pack` contains hundreds of GiB of
    unreferenced temporary packs. Working-tree size and object-store garbage are
    different measurements.
  - >
    M2 free-space recovery does not make M1 full-work safe. The M1 guard remains the
    host-specific production boundary.
  - >
    TerraMaster ownership is disabled and the volume is unencrypted. Scratch
    qualification is not authority for credentials, durable data or runner roots.
discoveries:
  - "DSC:PERSISTENT-RUNNER-TEMP-PACKS-CAN-BREACH-THE-HOST-DISK-GUARD"
  - "DSC:PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER"
---

## State

The M1 listener soak and TerraMaster scratch identity are now proven. W2 remains
in progress only because M1 storage is below the full-work floor. The M2 emergency
is healed and its drained listeners were restored, but temporary-pack recurrence
prevention still needs a measured producer before implementation. PC capacity,
#6286 acceptance, trusted-CI cutover, natural telemetry and Sol's final packet
remain incomplete.

No production CI route, runner label/group, repository visibility or M4 state was
changed.
