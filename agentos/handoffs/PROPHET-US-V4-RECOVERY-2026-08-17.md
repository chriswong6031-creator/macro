---
workstream: WS:PROPHET-US-V4-RECOVERY
session: claude/prophet-v4-0a-packet
model: fable
ended_because: complete
mission: >
  V4-0A: estate archaeology + architecture freeze for Prophet US V4 from fresh
  origin/main (fc0557bb0873), producing the 9-file orchestration packet, the Theia
  rights decision, and the V4-A1 spawn handoff — with zero production-code changes.
state_before: >
  Sol's masterplan pinned 16874921e638 (2026-08-17 snapshot); no research/prophet_v4/
  directory existed; no WS-PROPHET-US-V4-RECOVERY record; Theia rights question
  prepared (GMI W3A rights doc §5) but undecided; WS-GMI-THEME-GRAPH stale
  (status blocked, no W3A row) against merged #5718; Prophet production serving
  source_asof=2026-08-13 with issue #5742 open.
changed:
  - path: research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md
    what: committed canonical copy of Sol's masterplan (was Downloads-only)
  - path: research/prophet_v4/FABLE_HANDOFF_PROPHET_US_V4_0A_2026-08-17.md
    what: committed canonical copy of the 0A commissioning handoff
  - path: research/prophet_v4/CURRENT_STATE_2026-08-17.md
    what: six-lane archaeology synthesis — live outage state, publication architecture, data plane, gate chain, entry/intelligence/evaluation estates, four-way stage split, vocabulary disambiguation, live-defect register, Sol-snapshot deltas
  - path: research/prophet_v4/CAPABILITY_LEDGER.md
    what: 45-row capability ledger with closed state vocabulary, refreshing masterplan §3 at the execution pin
  - path: research/prophet_v4/ARCHITECTURE_FREEZE.md
    what: nine numbered frozen decisions (the tenth — wave deps/file ownership — lives in the wave-graph doc), six-plane ratification, the 25 laws inlined verbatim, schema-name freeze, no-rebuild boundaries, repin deltas incl. MP-1 reconciliation, §12.7 DNR confrontations
  - path: research/prophet_v4/ADVERSARIAL_REVIEW_2026-08-17.md
    what: both adversarial-review lanes (packet review + owner-map/DNR sweep) with every CRITICAL/HIGH/BLOCKER dispositioned in-PR
  - path: research/prophet_v4/CONTRACT_AND_OWNER_MAP.md
    what: canonical owner table (8 authorities), Prophet-internal migration estate, frozen contract names, consumer map
  - path: research/prophet_v4/SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md
    what: Theia ruling summary + theme-source rights + 16-family alt-data census with honest freshness/rights states
  - path: research/prophet_v4/EXPERIENCE_REFERENCE_COMPOSITIONS.md
    what: V4 experience compositions (lanes, header, card anatomy, All Candidates, alerts, acceptance surface) + MP-1 as the executed base
  - path: research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md
    what: 29-wave dependency graph, critical paths, lane concurrency rules, path ownership per wave
  - path: research/prophet_v4/V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md
    what: the exact next-wave spawn handoff with inline acceptance gates and live incident state
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: new workstream record — 29 waves, landmines, do_not_redo, sibling dependencies
  - path: agentos/decisions/DEC-PROPHET-V4-THEIA-SOURCE-RIGHTS.md
    what: new decision — default original-build ruling; licensed TIIC/TWI recorded as Chairman procurement option; no scraping
  - path: agentos/workstreams/WS-GMI-THEME-GRAPH.md
    what: staleness fix from merged evidence only — blocked→active, W3A wave row added (pr 5718), owns_paths added, transmission next_action updated to name the ThemeState merge-order ruling
  - path: tests/test_agentos_status.py
    what: >
      CI heal owed by the GMI status flip — three contract tests built fixtures by
      string-replacing the record's LITERAL "status: blocked" (a silent no-op once the
      status legitimately changed, turning fail-closed assertions green-blind) and one
      asserted the live record's blocked state as its blocked-parent case. Mutations are
      now status-agnostic (re.sub on the status line) and the blocked parent is
      SYNTHESIZED in the fixture copy. 41/41 pass on the branch; the same 3 failed
      before the fix and pass on origin/main (attribution receipt).
verified:
  - claim: fresh origin/main at execution is fc0557bb0873 (newer than Sol's 16874921e638)
    command: git fetch origin && git rev-parse origin/main
    result: fc0557bb0873f51db5ccbab4b043b26bbc9bb670, 2026-08-17T06:04:45-05:00
  - claim: all serving surfaces stuck at source_asof=2026-08-13; no checkpoint since 08-14T04:25:52Z
    command: curl of R2/Pages/VPS surfaces + git contents API (V4-0A production archaeology lane, 2026-08-17T11:44Z)
    result: byte-identical 1,384,976-byte index on git/R2/Pages; VPS index 401 but showcase.json Last-Modified Fri 14 Aug 04:27:02 GMT; newest cohort 2026-08-13
  - claim: issue #5742 open with zero comments; PR #5723 merged without recovering the session
    command: gh issue view 5742 --json state,title,closedAt; gh pr view 5723 --json state,mergedAt
    result: OPEN, closedAt null; #5723 MERGED 2026-08-15T08:01:59Z
  - claim: no hard production candidate cap; production passes n=None
    command: read engine/prophet_bridge.py:146,1147,4127 and .github/workflows/daily.yml:2280,2493
    result: N_CANDIDATES=12 is an overridden default; originate_plans calls select_candidates(standouts, n=None, ...)
  - claim: no Theia/TIIC adapter or ingestion code exists
    command: grep -riE "theia|tiic|theme[ _-]?watch[ _-]?ind" across py/yml/md/json/j2/js
    result: only research memos + commented-out config/theme_sources.yml:49-52 stub (rights_class unresolved)
  - claim: Radar W5 closed the morning of 0A
    command: read agentos/workstreams/WS-LIVE-ENTRY-RADAR.md + agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-17.md
    result: "#5825 squash 0394d6e16407 2026-08-17T10:08:44Z; panels A/B re-run with 0 control-match refusals"
  - claim: agentos records validate
    command: python3 scripts/agentos.py validate
    result: exit 0 (run at packet completion; re-run before merge)
  - claim: the ci-pack-0 red was caused by test-pinned GMI status literals, not the records themselves
    command: python3 -m pytest tests/test_agentos_status.py -q (on branch pre-fix, on origin/main, and on branch post-fix)
    result: pre-fix branch 3 failed/38 deselected; origin/main 3 passed; post-fix branch 41 passed
unverified:
  - claim: root cause of run 31977372592 engine-job failure
    what_would_verify: that run's engine job logs (V4-A1 gate 1)
  - claim: mechanics of the 08-16 Pages-newer-than-git violation (run 31913143619)
    what_would_verify: that run's job logs; A3 designs the fence regardless
  - claim: B-15..B-19 current dispositions after the #5370 heal
    what_would_verify: V4-B2's opening disposition matrix against live engine/us_early_turn.py
  - claim: MP-1 R3/R4 reference crops still current with the design authority
    what_would_verify: design-authority confirmation at B5 spawn
unresolved:
  - "LIVE OUTAGE: Prophet serving 2026-08-13 picks; Friday 08-14 session never captured; candidate store + legacy shadow + TURN WATCH lanes stalled. V4-A1 (handoff in packet) owns recovery; THIS session dispatched nothing per its non-goals."
  - "Anonymous full-board leak (tier caps DOM-only) — fix candidate flagged; at latest E2."
  - "WS-PROPHET-US-AVAILABILITY.md W0/next_action stale (says 'land the hardening PR' while the rescue lane is live) — left to V4-0B records wave; V4-A1 handoff carries true state inline."
next_actions:
  - "Merge the V4-0A packet PR (this session owns it to merge)."
  - "Spawn V4-A1 per research/prophet_v4/V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md — one bounded session, no auto-roll."
  - "Run V4-0B (AgentOS reconciliation, records only) for the remaining stale rows (availability W0, EIOS artifact-vs-record gap)."
  - "Before any D3/ThemeState work: append the GMI-vs-V4 merge-order ruling to WAVE_GRAPH_AND_MERGE_ORDER.md §4."
do_not_redo:
  - "Do not re-run the 0A archaeology sweeps — receipts are in CURRENT_STATE_2026-08-17.md; re-verify only the LIVE items (§1/§2) which move nightly."
  - "Do not re-litigate the Theia default ruling absent a license purchase (DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS, review_by 2026-10-01)."
  - "Do not spend a PR removing the bridge candidate cap — it is already absent from the live path."
  - "Do not start B-lane/D-lane implementation before A1 settles the reader — the masterplan's critical path is frozen in WAVE_GRAPH_AND_MERGE_ORDER.md."
danger_areas:
  - "Fusion PR-3B forbidden zone = WS-PROPHET-CONDITIONAL-FUSION owns_paths verbatim (8 paths). Widening it is the named failure mode of this program's commissioning."
  - "The four stage-derivation sites in dashboard.html.j2/us_board_rank.py — touching any one without B3's single contract recreates the drift."
  - "prophet_rescue budget semantics count attempts including runless POSTs; never dispatch over a queued/in-progress daily run."
  - "Never cancel production lanes (gh_quota_guard shape 6); a cancel is invisible to every staleness instrument."
prs: [5832]
decisions:
  - DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS
---

## Cold-stranger summary

Prophet US V4 is commissioned (Sol masterplan, committed in-packet). This 0A session
produced the complete orchestration packet in `research/prophet_v4/` — read
`CURRENT_STATE_2026-08-17.md` first (the estate as measured), then
`ARCHITECTURE_FREEZE.md` (nine numbered frozen decisions + §12.7 DNR gates), then
`WAVE_GRAPH_AND_MERGE_ORDER.md` (what runs when; §4 carries the nine merge-order
rulings for every sibling-owned path). The single most important live fact:
the availability outage is ACTIVE (served picks are 2026-08-13); the next session
executes `V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md` exactly. No production code changed
in 0A; the only AgentOS mutations besides the new records are the evidence-proven
GMI staleness fix.
