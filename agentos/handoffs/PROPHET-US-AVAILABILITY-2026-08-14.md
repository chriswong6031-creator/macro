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
  - path: scripts/prophet_rescue.py (1214) + tests/test_prophet_rescue.py (73 tests) + .github/workflows/prophet-rescue.yml
    what: "Responder lane: pure decide() core, DST-stable deadline ladder, four mutation-pinned dispatch-safety invariants, two-pass reads (3 healthy / 5 alarm, AST-pinned), issue-receipt attempt ledger, verdict-set alert dedup, hourly ubuntu workflow. Opus-built, red-teamed (six required amendments all landed), 187 green across the dark-guards battery."
  - path: scripts/prophet_rescue_launchd.py + install_prophet_rescue_launchd.sh + prophet_rescue.launchd.plist
    what: "Host twin on the canonical GC-installer pattern (re-extracts from origin/main; token via chmod-600 env file or gh auth token; --disk-path measures the runner volume). Operator-installed only."
  - path: .claude/hooks/gh_quota_guard.py + tests/test_gh_quota_guard.py
    what: "PROTECTED_LANES += prophet-rescue.yml, nightly-liveness.yml; first-ever shape-6 test coverage (104 tests)."
  - path: .github/ci/legacy-jobs.yml + .github/workflows/ci.yml
    what: "Suite registered in the existing unrun-dark-guards job (importlib path-literal family; no new job, 188 total); path triggers for both halves. Disjoint from PR #5487's hunks (~2100/~1336 vs ~6922/~3890) — verified merges clean."
  - path: AGENTS.md + CLAUDE.md
    what: "Recovery etiquette in both registers: rescue lane is the ONLY auto-redispatcher of daily.yml; read the prophet-outage issue before manual dispatch; never dispatch over a live run."

verified:
  - claim: "Outage root causes: 512KB workflow strand (08-11), rogue codex force-cancels ×6 (08-12), runner disk-full (08-13); GitHub platform not implicated"
    command: "gh run view 31671422158 --json jobs (disk-full annotation); gh run list --workflow daily.yml --limit 10; curl -s https://www.githubstatus.com/api/v2/incidents.json"
    result: "Zero Actions-component incidents Aug-11→14; 'No space left on device' on job 94481620700; 10-dispatch thrash timeline reconstructed"
  - claim: "A cancelled bake still delivered: 25 plans recorded_at=2026-08-12 on main"
    command: "git show origin/main:site/prophet/index.json | python3 -c '<recorded_at Counter census>'"
    result: "cohorts 08-10:25, 08-11:0, 08-12:25, 08-13:0; asof=2026-08-13 source_asof=2026-08-12"
  - claim: "Serve paths healthy — outage was production, not delivery"
    command: "curl -s https://www.mastermind-x.com/api/status; curl -s https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json"
    result: "VPS site.commit 13 min old at 02:14Z; R2 matches main (source_asof 08-12, 25× 08-12 plans)"
  - claim: "agentos records schema-clean"
    command: "python3 scripts/agentos.py validate"
    result: "0 errors (phantom-owns-path warnings resolve when builder files land)"

unverified:
  - claim: "The dispatch / issue-upsert / webhook write paths behave correctly against a REAL alarm (unit-tested with mocks; live dry-run exercised only the healthy/WAIT path)"
    what_would_verify: "First real outage, or a supervised drill: gh workflow run prophet-rescue.yml on a synthetic stale fixture (WS W2 fire-drill week)"
  - claim: "The prophet-outage label + issue flow works with the workflow's issues:write grant"
    what_would_verify: "First alarm wake creates label+issue; degraded path is annotated ::warning prophet-rescue-ledger-blind"

unresolved:
  - "Operator arbitration of codex session rollout-2026-08-11T04-10-51 (six receipted kills) — outstanding since 2026-08-12"
  - "No codex-side technical enforcement for production-lane cancels exists"
  - "healthcheck.py's divergent _sessions_stale calendar math vs lib/nyse_calendar — consolidation chip, separate lane"

next_actions:
  - "Finalize builder-evidence entries in this handoff + PR body; open PR; arm merge-on-green; scripts/ci_handoff.py"
  - "After merge: verify first scheduled prophet-rescue wake's run summary"
  - "Operator: run scripts/install_prophet_rescue_launchd.sh once on the Mac Studio (W1)"
  - "W2 fire-drill week per WS record"

do_not_redo:
  - "GitHub platform incident check for Aug 11–13 (done: zero Actions incidents — self-inflicted outage)."
  - "Aug-11 backfill feasibility (adjudicated REFUSED: no origination event, no bake-time board, bars uncollected that night; #5305 charter + #5289 contamination precedent). Reopen only on explicit operator override."
  - "Duplicate detection of #5487's run-created/run-concluded/source_asof arms."

danger_areas:
  - "The cancelling codex session (rollout-2026-08-11T04-10-51) was still active 08-13 16:00 local; nothing technical binds codex sessions — treat any new production-lane cancel as that unresolved arbitration, not a new mystery."
  - "Do not edit daily.yml/build_prophet.py in this lane — availability work must never add bake risk (first-run-bomb law)."
  - "PR #5487 owns .github/ci/legacy-jobs.yml, config/house_law_checks.yml, and dag-conformance ci.yml hunks — colliding hunks will conflict at the sweeper."

decisions: ["DEC:PROPHET-RESCUE-SEPARATE-FROM-LIVENESS"]
discoveries: ["DSC:PROPHET-ASOF-IS-WALL-CLOCK", "DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET"]
---

## Notes

If tonight's bake (31753425298) concluded without a recorded_at=2026-08-13 cohort,
read the intake receipt before any dispatch — NO_COHORT wedge signatures are code
bugs, not staleness, and a re-dispatch cannot fix them.

Session chain context: this session also monitored the in-flight 08-13 bake
(collect→engine healthy at handoff time) and left the Aug-11 gap explicitly disclosed
rather than backfilled — the honest-history call, per charter. The operator's two
standing actions (launchd install, codex arbitration) are the only unautomated pieces
of the never-again posture.
