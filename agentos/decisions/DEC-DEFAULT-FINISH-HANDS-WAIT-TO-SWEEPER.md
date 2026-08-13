---
key: DEFAULT-FINISH-HANDS-WAIT-TO-SWEEPER
question: >
  Once a session's work is committed, pushed, and open as a pull request with CI running,
  does the session stay alive to watch CI and perform the merge — or terminate?
answer: >
  Terminate. The default finish is: `gh pr edit <n> --add-label merge-on-green`, then
  `python3 scripts/ci_handoff.py`, emit the `CI_HANDOFF=` receipt it prints, and stop.
  The merge-on-green sweeper (GitHub-hosted, off the self-hosted render pools; fired by
  workflow_run on every ci/fences/integration-baseline conclusion, with a cron recovery
  net the lane may not lean on) squash-merges once every check has CONCLUDED clean.
  After `CI_HANDOFF`, waiting, polling, rerunning, merging, observing the deployment,
  and continuing the next phase in the same session are forbidden — "worker done" is an
  earlier state than "system done", and the system chain (sweeper merge, render lane,
  VPS 3-minute pull) completes without a session watching it. Manual merge on
  concluded-green remains mechanically valid but is the exception: an explicit operator
  request to watch one through, or a wedge the sweeper provably cannot clear.
rationale: >
  A worker alive past its handoff re-asks, on the one shared 5,000/hr REST bucket, a
  question the sweeper already re-derives from GitHub's live state at every CI
  conclusion — and `ship_loop_guard.py` spends REST calls per Stop evaluation and FAILS
  CLOSED when rate-limited, so over-polling blocks the very Stop the polling was for.
  Before the sweeper, sessions were held as CI hostages for the 20–60 minute pack
  wall-clock, duplicating a wait the lane now runs the moment each proof run concludes.
  The hook and the CLI hold ONE classifier (`scripts/ci_handoff_contract.py`, loaded by
  file path from both), so the release decision cannot fork between them. An unproven
  head — no non-spurious check started — still blocks release, because an absence of red
  is not a pass (#4779) and the sweeper will refuse the same head for the same reason:
  releasing on it would orphan the work.
alternatives:
  - option: Session watches CI to conclusion and merges by hand (the pre-sweeper default)
    why_not: >
      Spends a live worker 20–60 minutes duplicating a sweep the lane fires itself at
      every CI conclusion, and under a red main the wait is unbounded — measured
      fleet-wide session pinning (2026-07-28 and #5037 2026-08-08 receipts in fleet law).
  - option: Arm GitHub native auto-merge as the wait
    why_not: "Merges immediately — no branch protection on main. See DEC:MERGE-ON-CONCLUDED-CHECKS-ONLY (#3889)."
  - option: Release the session on ANY armed PR, proven or not
    why_not: >
      A head with no non-spurious checks is unproven; the sweeper will never merge it, so
      release would orphan the work with nobody watching (#4779: absence of red ≠ pass).
evidence:
  - "Macro CLAUDE.md §CI handoff is terminal (STANDING — HIGHEST PRECEDENCE) and AGENTS.md same-titled section"
  - "scripts/ci_handoff.py + scripts/ci_handoff_contract.py — added 2026-08-12 (git log --diff-filter=A)"
  - ".github/workflows/merge-on-green.yml — added 2026-07-28 (git log --diff-filter=A)"
  - ".claude/hooks/ship_loop_guard.py — releases at the unmerged gate on an armed, proven, non-red PR"
affects: [".claude/hooks/ship_loop_guard.py", "scripts/ci_handoff.py", "scripts/ci_handoff_contract.py"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-12
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). The sweeper landed 2026-07-28; the terminal
handoff contract (`ci_handoff.py`, one shared classifier, "worker done ≠ system done")
landed 2026-08-12 and is dated accordingly. Attribution: fleet law authored into
`CLAUDE.md`/`AGENTS.md` as a standing highest-precedence section; no single operator
quote mints it, so the deciding seat is recorded as coo-fable rather than chairman.

## What would reopen this

The sweeper repeatedly failing a class of PR it should clear (see the disarming and
`merge-blocked` law in `CLAUDE.md` §Shared workspace + completion), or the REST-quota
economics changing (per-session tokens). Related: `DEC:MERGE-ON-CONCLUDED-CHECKS-ONLY`
(what "concluded" means), `DEC:GITHUB-QUOTA-IS-ONE-SHARED-BUCKET` (why polling is the
scarce resource).
