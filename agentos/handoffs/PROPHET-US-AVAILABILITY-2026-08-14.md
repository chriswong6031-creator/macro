---
workstream: WS:PROPHET-US-AVAILABILITY
session: claude/prophet-us-availability-hardening
model: fable
ended_because: ci_handoff

mission: >
  Root-cause the 2026-08-11/13 Prophet US outage from receipts, design a never-again
  availability architecture, and ship the response+resilience layers as one PR —
  complementing (never duplicating) PR #5487's detection lane.

state_before: >
  site/prophet/index.json source_asof frozen at 2026-08-10 through two NYSE sessions;
  operator discovered it by looking at the site. Recorded_at cohorts on main at session
  start: 08-10:25, 08-11:0, 08-12:25 (landed 03:28Z 08-13), 08-13:0. Tonight's bake
  31753425298 in flight (collect succeeded ~02:2xZ). PR #5487 (nightly-liveness
  detection) armed, packs pending. No Prophet-specific staleness detection, no
  self-heal, no host-side backstop existed; #5488 cancel-deny hook bound Claude
  sessions only.

changed:
  - path: research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md
    what: "Masterplan + runbook: receipted incident table, sensor-blindness analysis, three-layer architecture (detect=#5487+additive; respond=prophet_rescue; survive=launchd twin+PROTECTED_LANES), §0 acceptance gates, test matrix, recovery etiquette."
  - path: agentos/discoveries/DSC-PROPHET-ASOF-IS-WALL-CLOCK.md
    what: "Landmine: top-level asof/recorded_at are wall-clock publication stamps; freshness must key source_asof + recorded_at cohorts."
  - path: agentos/discoveries/DSC-CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET.md
    what: "Landmine: prophet_checkpoint commits mid-run; run conclusions decouple from Prophet delivery in both directions."
  - path: agentos/decisions/DEC-PROPHET-RESCUE-SEPARATE-FROM-LIVENESS.md
    what: "Architecture decision: response organ separate from detection, bounded self-heal semantics, five alternatives rejected with receipts."
  - path: agentos/workstreams/WS-PROPHET-US-AVAILABILITY.md
    what: "New workstream: W0 rescue lane (this PR), W1 operator acts (launchd install + codex arbitration), W2 fire-drill week."
  - path: scripts/prophet_rescue.py + .github/workflows/prophet-rescue.yml + tests/test_prophet_rescue.py + .claude/hooks/gh_quota_guard.py + launchd installer pack + AGENTS.md/CLAUDE.md deltas
    what: "BUILDER EVIDENCE PENDING — opus builder implementing per masterplan §0 gates; this entry is finalized with the verified file list before the PR opens."

verified:
  - claim: "Outage root causes: 512KB workflow strand (08-11), rogue codex force-cancels ×6 (08-12), runner disk-full (08-13); GitHub platform not implicated"
    by: "gh run list/view on 31543112462…31753425298; githubstatus.com incidents API Aug-11→14; job annotation 'No space left on device' on run 31671422158 job 94481620700"
  - claim: "A cancelled bake still delivered: 25 plans recorded_at=2026-08-12 on main"
    by: "git show origin/main:site/prophet/index.json | python3 recorded_at census (08-12: 25)"
  - claim: "Serve paths healthy — outage was production, not delivery"
    by: "curl https://www.mastermind-x.com/api/status (site.commit 13 min old); curl pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json (matches main)"
  - claim: "agentos records schema-clean"
    by: "python3 scripts/agentos.py validate → 0 errors"

do_not_redo:
  - "GitHub platform incident check for Aug 11–13 (done: zero Actions incidents — self-inflicted outage)."
  - "Aug-11 backfill feasibility (adjudicated REFUSED: no origination event, no bake-time board, bars uncollected that night; #5305 charter + #5289 contamination precedent). Reopen only on explicit operator override."
  - "Duplicate detection of #5487's run-created/run-concluded/source_asof arms."

danger_areas:
  - "The cancelling codex session (rollout-2026-08-11T04-10-51) was still active 08-13 16:00 local; nothing technical binds codex sessions — treat any new production-lane cancel as that unresolved arbitration, not a new mystery."
  - "Do not edit daily.yml/build_prophet.py in this lane — availability work must never add bake risk (first-run-bomb law)."
  - "PR #5487 owns .github/ci/legacy-jobs.yml, config/house_law_checks.yml, and dag-conformance ci.yml hunks — colliding hunks will conflict at the sweeper."

next_session_should: >
  If this PR is merged: verify the first scheduled prophet-rescue wake's run summary,
  then advance WS W1 (operator installs launchd; arbitration) and W2 (fire drills).
  If tonight's bake (31753425298) concluded without a recorded_at=2026-08-13 cohort,
  read the intake receipt before any dispatch — NO_COHORT wedge signatures are
  code bugs, not staleness, and a re-dispatch cannot fix them.
---

## Notes

Session chain context: this session also monitored the in-flight 08-13 bake
(collect→engine healthy at handoff time) and left the Aug-11 gap explicitly disclosed
rather than backfilled — the honest-history call, per charter. The operator's two
standing actions (launchd install, codex arbitration) are the only unautomated pieces
of the never-again posture.
