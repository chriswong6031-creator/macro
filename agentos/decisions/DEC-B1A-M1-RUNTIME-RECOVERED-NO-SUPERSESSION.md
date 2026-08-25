---
key: B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION
question: >
  Was the governed M1 publisher runtime `/Users/chriswong/flow-ops-wt` lost, and
  does B1-A therefore owe a replacement-pin migration that supersedes the Day-6
  cutover record? And does the 2026-08-24 PR #6363 comment asserting
  `EXTERNAL_CAPABILITY_BLOCKED` carry authority over that record?
answer: >
  NO on all three. The runtime was RECOVERED intact on the M1 on 2026-08-25 at
  exactly the pin the Day-6 record named — detached
  `a5f79c83fe0b26e3fbd798ffc4630fc957d09a60`, 395 tracked modifications, 20
  untracked paths. No state was lost, so Phase-2 replacement-pin supersession is
  NOT triggered and MUST NOT be performed: the merged #6363 contract depends on
  that exact pinned engine remaining untouched. DEC:B1-MACRO-PRIVATE-CUTOVER and
  the Day-6 handoff STAND UNAMENDED, including their finding that advancing the
  M1 pin is an operator convenience and NOT a visibility-flip blocker. The PR
  comment is not authority: it is a session's terminal note, its own first clause
  scopes it to "the commissioning Mac" (the M2), and no Sol or Agent-OS ruling
  after 2026-08-21 superseded Day-6 — the durable plane still carries the pin
  advance as a residual chore, never as a blocker.
rationale: >
  An absent path on one host is not evidence of loss when the runtime is
  host-local to another. The M1 was reachable the whole time over Tailscale and
  answered on first probe. Treating the comment as authority would have
  authorized exactly the destructive act the mission forbids — reconstructing a
  clean checkout at the old pathname, or "superseding" a live governed runtime
  with a replacement pin — which would have discarded 395 tracked modifications
  that the merged publisher lanes still consume as their engine.
alternatives:
  - option: Accept the PR comment and execute a Phase-2 replacement-pin migration
    why_not: >
      It would supersede a runtime that is not lost, destroy the pinned engine
      #6363 requires, and record a false provenance verdict in the durable plane.
      The mission explicitly forbids reinterpreting a PR comment as a Sol ruling.
  - option: Advance / clean / reset `flow-ops-wt` to current main while installing #6363
    why_not: >
      The merged lanes resolve `$REPO` to `flow-ops-wt` for PYTHONPATH, working
      directory and `.env` only. #6363 deliberately separates the disposable
      launcher from the pinned engine, so advancing the engine is out of scope,
      is an operator action per Day-6, and risks the prophet_marks staleness
      escalation that Day-6 scoped OUT of B1.
  - option: Leave #6363 uninstalled until an operator restores "the exact bytes"
    why_not: >
      There is nothing to restore. The bytes were never missing, and the install
      is purely additive (one clone, two plist swaps, both backed up).
evidence:
  - "M1 `Mac13,1` reachable at Tailscale 100.117.58.62; `/Users/chriswong/flow-ops-wt` present, detached at a5f79c83fe0b26e3fbd798ffc4630fc957d09a60 (#2760, 2026-07-17), 395 tracked modified + 20 untracked, status digest 560e8e929c5b768230680966e43001daae7d44a90137c1710627ed0c28e62834, diff digest 5ba54da65e39ca975d449431ead3771e2cda49534595bcdac40f453e487adeca"
  - "Day-6 handoff records the same pin ('pinned a5f79c83 (#2760-era, no auto-pull) … NOT a flip-blocker'), so the recovered HEAD independently corroborates the Day-6 record"
  - "The ~69 GiB TerraMaster M1 recovery set at /Volumes/Mastermind/Mastermind/scratch/runner-fleet/m1-recovery-20260824 is entirely chrome-code-sign-clones-inactive and contains zero flow-ops-wt material — it can neither establish nor restore the runtime's identity"
  - "No Agent-OS decision, workstream or handoff after 2026-08-21 supersedes DEC:B1-MACRO-PRIVATE-CUTOVER; WS:PROPHET-US-V4-RECOVERY still lists the pin advance as a residual chore"
  - "Post-install re-capture of the same digests returned byte-identical values, proving commissioning did not mutate the recovered runtime"
affects:
  - "ops/launchd/com.macro.indexgexhistory.plist"
  - "ops/launchd/com.macro.theme-options-witness.plist"
  - "scripts/macro_machine_git.py"
confidence: high
reversibility: easy
decided_by: fable
decided_at: 2026-08-25
related:
  - "DSC:M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED"
  - "DEC:B1-MACRO-PRIVATE-CUTOVER"
  - "WS:PROPHET-US-V4-RECOVERY"
---

Recorded by the B1-A session commissioned to recover the M1 runtime or ratify a
replacement pin. The recovery branch of that mandate was taken; the replacement
branch is closed as not-triggered. Should a future session find `flow-ops-wt`
genuinely gone, this record does NOT pre-authorize a replacement pin — it
requires the same evidentiary standard applied here, beginning with a direct M1
probe rather than an inference from the machine the session happens to occupy.
