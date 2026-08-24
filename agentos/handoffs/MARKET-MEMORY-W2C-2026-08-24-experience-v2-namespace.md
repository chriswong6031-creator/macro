---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/w2c-m0d-experience-v2-namespace
model: local
ended_because: complete
prs: []
decisions: []
discoveries:
  - "DSC:W2C-M0D-EXPERIENCE-V2-TMPFS-OPTIONAL-V1-INACCESSIBLE"
mission: >
  Bounded experience-v2 systemd namespace repair so 04:32Z can reach ExecStart
  without weakening v1 isolation. Do not manufacture an opportunity. Do not
  open R2. Stop at AWAITING_NATURAL_TUESDAY_PROOF.
state_before: >
  Sunday 2026-08-23 04:32Z experience-v2 failed 226/NAMESPACE before Python.
  Monday 04:32Z repeated the same failure. source-spy-rest and technicals-v2
  timers fired. v2 store remained .v2_install_verified only. v1 control was
  restored independently.
changed:
  - path: app/deploy/macro-market-memory-experience-v2.service
    what: >
      Optional '-' on the three tmpfs-hidden v1 siblings (sources,
      technicals-v1, experience-v1). External credential/options denies stay
      mandatory. TemporaryFileSystem, binds, PrivateNetwork, and
      RestrictAddressFamilies unchanged.
  - path: tests/test_market_memory_m0d_v2.py
    what: Semantic regression that fails the old mandatory-tmpfs combination and passes the repair.
  - path: agentos/discoveries/DSC-W2C-M0D-EXPERIENCE-V2-TMPFS-OPTIONAL-V1-INACCESSIBLE.md
    what: Durable Sunday/Monday namespace finding and canary proof.
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: M0D next_action is natural Tuesday proof; M0D remains BUILT_NOT_PROVEN.
verified:
  - claim: Mandatory InaccessiblePaths for each tmpfs-hidden v1 sibling aborts setup 226/NAMESPACE without invoking the writer.
    command: disposable mm-ns-canary-a/b/c on ubuntu-s-mastermindx
    result: each ExecMainStatus=226; Python not started; real experience-v2 not started
  - claim: Optional prefix on all three siblings lets the sandbox reach ExecStart.
    command: mm-ns-canary-d ExecStart=/bin/true; later exact repaired-unit sandbox /bin/true
    result: Result=success ExecMainStatus=0
  - claim: Repaired-equivalent namespace keeps v1/credentials/network isolated and v2 I/O as designed.
    command: exact repaired-sandbox isolation canary
    result: >
      sources-spy-rest-v1 readable not writable; technicals-v2 readable not
      writable; experience-v2 writable; sources/technicals-v1/experience-v1
      inaccessible; spy-rest credentials inaccessible; AF_INET unavailable
  - claim: Existing M0D suite still green on this head.
    command: python3 -m pytest tests/test_market_memory_m0d_v2.py -q
    result: 106 passed
unverified:
  - claim: Tuesday 2026-08-25 04:32Z will admit session 2026-08-24.
    what_would_verify: Natural source seal, technicals-v2, and experience-v2 without manual starts.
unresolved:
  - M0D remains BUILT_NOT_PROVEN until the natural Tuesday chain authenticates.
  - Sunday source-spy-rest selected session 2026-08-22 then refused (no valid bar). Residue only; not repaired here.
  - R2 atomicity remains NOT STARTED / CLOSED to this wave.
next_actions:
  - Merge and deploy reviewed unit bytes via update.sh. Do not hand-edit /etc/systemd/system.
  - Do not start macro-market-memory-experience-v2.service.
  - Observe Tuesday 2026-08-25 04:00 / 04:07 / 04:32Z naturally.
do_not_redo:
  - Do not restore mandatory InaccessiblePaths for tmpfs-hidden v1 siblings.
  - Do not manufacture a v2 opportunity or convert v1 missed rows.
  - Do not start R2 because this repair merged.
danger_areas:
  - Optionalizing paths outside the tmpfs that still exist at setup would hide deploy drift.
  - Starting the real writer to "prove" the repair would contaminate the Tuesday gate.
---

# experience-v2 namespace repair — AWAITING_NATURAL_TUESDAY_PROOF

The Sunday smoke did not create a v2 opportunity. Python never started.
The blocker was systemd mount-namespace setup, not M0D science.

Repair matches the already-proven v1 experience unit: optional `-` only on
unbound siblings hidden by `TemporaryFileSystem=/var/lib/macro-market-memory:ro`.
Isolation is the empty tmpfs plus remaining mandatory external denies.
