---
key: M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED
claim: >
  The B1 M1 publisher runtime is HOST-LOCAL to the M1 (`Mac13,1`, Tailscale
  `m1` / 100.117.58.62) and has never existed on the M2 commissioning Mac.
  On 2026-08-25 `/Users/chriswong/flow-ops-wt` was found fully intact on the M1
  at exactly the pin the Day-6 record named — detached
  `a5f79c83fe0b26e3fbd798ffc4630fc957d09a60` (#2760, 2026-07-17) — carrying 395
  tracked modifications and 20 untracked paths. The STABLE identity invariant is
  the `git status --porcelain` sha256 `560e8e92...` — the SET of dirty paths is
  what the pin is. The `git diff HEAD` sha256 `5ba54da6...` is a POINT-IN-TIME
  forensic capture only and is EXPECTED to drift, because `flow-ops-wt` is a
  live tree whose data artifacts are rewritten by the production lanes it
  serves. Its detached dirty pin is DELIBERATE, not damage: PR #6363's
  architecture separates a *current, disposable launcher* (a clean governed
  clone at `~/macro-publisher-runtime`) from a *deliberately pinned engine*
  (`flow-ops-wt`, supplied to the lane only as `PYTHONPATH` + `WorkingDirectory`
  + `.env`). The same shape was already applied to the Prophet marks lane on
  2026-08-23 via `~/prophet-marks-runtime` at `e15b6907`.
falsifier: >
  On the M1, show `/Users/chriswong/flow-ops-wt` absent, or at a HEAD other than
  `a5f79c83fe0b26e3fbd798ffc4630fc957d09a60`, or with a
  `git status --porcelain` digest other than
  `560e8e929c5b768230680966e43001daae7d44a90137c1710627ed0c28e62834`; or show
  that the merged `ops/launchd/run_*.sh` at `deb53e6f` resolve `$REPO` to
  something other than `/Users/chriswong/flow-ops-wt`, which would mean the pin
  is incidental rather than load-bearing. The `git diff HEAD` digest is
  deliberately NOT part of this falsifier: it is a capture-time value, and a
  changed diff digest on its own falsifies nothing here.
so_what: >
  Never infer B1 M1 runtime loss from an absent path on the machine a session
  happens to be running on — probe the M1 over Tailscale first. Never "advance",
  reset, clean, or reconstruct `flow-ops-wt` to make it look canonical: the
  merged publisher contract REQUIRES the old pinned engine to stay exactly as it
  is, so normalizing it would silently destroy the governed runtime that #6363
  was written to preserve. Commissioning #6363 is purely additive — clone the
  launcher runtime, swap two plists — and needs no change to `flow-ops-wt` at
  all.
kind: landmine
scope:
  - macro
  - "ops/launchd/**"
  - "scripts/macro_machine_git.py"
confidence: verified
verified_at: 2026-08-25
verified_by: >
  `ssh m1` read-only forensic capture: `hostname`, `sysctl -n hw.model`,
  `stat -f 'dev=%d inode=%i'`, `git rev-parse HEAD`, `git symbolic-ref -q HEAD`
  (detached), `git log -1`, `git config --get remote.origin.url`,
  `git status --porcelain` counts + sha256, `git diff HEAD` sha256, full
  untracked inventory, and `grep -rl flow-ops-wt ~/Library/LaunchAgents/`.
  Re-run of the identical capture IMMEDIATELY AFTER the #6363 install returned
  byte-identical values for BOTH digests, which proves the install itself did
  not mutate the runtime during that capture interval. That is an interval
  claim, not a permanence claim. Later the same day the `git diff HEAD` digest
  moved to `b2b14cd8...` from a single benign production write to
  `data/thetadata_eod/_manifest.json` (14:30:15 PDT) — zero engine code changed,
  and the `git status --porcelain` digest was unmoved.
related:
  - "DEC:B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION"
  - "DEC:B1-MACRO-PRIVATE-CUTOVER"
  - "WS:PROPHET-US-V4-RECOVERY"
  - "WS:RUNNER-FLEET-RESILIENCE"
---

The 2026-08-24 post-merge comment on PR #6363 reported these paths absent and
concluded `EXTERNAL_CAPABILITY_BLOCKED: governed M1 engine checkout
/Users/chriswong/flow-ops-wt and its unrecoverable dirty pin state are
unavailable`. That comment names its own scope in its first clause — "On the
commissioning Mac" — which was the M2. The M1 was never probed. Every path it
listed as absent (`flow-ops-wt`, `prophet-marks-runtime`) was present and
healthy on the M1 the next day; the three it listed that genuinely did not exist
(`macro-publisher-runtime`, `indexgex-push-repo-private`,
`witness-push-repo-private`) are the artifacts the install itself creates.
