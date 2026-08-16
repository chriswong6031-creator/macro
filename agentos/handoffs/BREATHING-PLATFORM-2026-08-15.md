---
workstream: "WS:BREATHING-PLATFORM"
session: claude/breathing-platform-revival (worktree breathing-platform-revival-fc7825)
model: fable
ended_because: complete
mission: >
  Chairman directive 2026-08-15: revive the Breathing Platform, fix the two
  measured product defects of the evening Prophet board (86% coverage hole,
  hours-late GitHub-cron clock), ship independently rollbackable PRs, run all
  lawful weekend acceptance, leave live-session acceptance explicitly open.
state_before: >
  W-L0/W-L1 fully merged (#4978 #4982 #5088 #5089 #5148 #5154 #5217 #5220
  #5222 #5223 #5495); lane first green 2026-08-13. Friday 2026-08-14 real
  outcome: 22 cards from 253/1,763 evaluated, published ~19:20 ET. No
  breathing-platform Agent OS workstream existed.
changed:
  - path: agentos/workstreams/WS-BREATHING-PLATFORM.md
    what: canonical workstream created (program prophet-us), waves W-L0..W-ACCEPT
  - path: agentos/decisions/DEC-BREATHING-HOST-NATIVE-CLOSE-CLOCK.md
    what: architecture ruling — Mac launchd primary clock, Massive close source, GH backstop
  - path: agentos/discoveries/DSC-MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE.md
    what: measured close-semantics discovery (snapshot day.c == grouped, freezes at 16:00 ET)
  - path: engine/close_pass/massive_close.py
    what: (#5746, via opus builder) grouped/snapshot close adapter, corp-action guard, case-exact matching
  - path: scripts/close_pass_publish.py
    what: (#5746) in-memory Massive fill for no_todays_bar names, fail-closed guard-down, provenance meta
  - path: scripts/measure_massive_close_parity.py
    what: (#5746) parity battery + Monday-live measurement tool
  - path: scripts/close_pass_host_runner.py
    what: (#5760, armed) launchd primary-clock runner — lane worktree, wait-for-close, receipts
  - path: ops/launchd/com.macro.closepass.plist
    what: (#5760, armed) 13:00 PT weekday schedule + installer scripts/install_closepass_launchd.sh
  - path: .github/workflows/close-pass.yml
    what: (#5746+#5760) MASSIVE_API_KEY env; demotion to fail-open backstop with keyless stand-down
  - path: scripts/freshness_sentinel.py
    what: (#5761, armed, via opus builder) latency decomposition + stale-armed-pack watchdog
  - path: scripts/close_pass_slo_report.py
    what: (#5761, armed) per-session acceptance-record table for W-ACCEPT
  - path: research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-15.md
    what: session handoff (mid-flight #5758 version superseded in place by close version)
verified:
  - claim: The new path fixes coverage on real Friday data (253→1,684 evaluated, 73 cards)
    command: in-process collect("2026-08-14")+build_payload in the PR-A worktree with the host .env key
    result: 'REPLAY BOARD: evaluated 1684, admitted 73, close_source {"store": 0, "massive": 1684}, close_finalized true, skipped {corp_action_today: 58, no_todays_bar: 19, delisted: 2}'
  - claim: Store-vs-Massive close parity holds on the real store
    command: python3 scripts/measure_massive_close_parity.py --session 2026-08-13 (in PR-A worktree)
    result: 1,741/1,741 within $0.005, max abs diff $0.000117
  - claim: A real browser mounts the 73-card replay board on a static page frozen at N−1, and refuses the expired copy
    command: python3 -m http.server via .claude/launch.json site-static; Browser pane DOM+network reads
    result: expired state fetched 200 → provisionalGridMounted false; fresh-stamped state → mounted true, provCards 73, nightly grid hidden, mobile 375px overflowX false
  - claim: The suites are green on the COMBINED A+B tree
    command: python -m pytest tests/test_close_pass_lane.py -q (post-rebase in PR-B worktree)
    result: 110 passed (plus 43 massive_close, 48 host_runner, 123 sentinel/slo in their trees)
  - claim: The sweeper ignores the new pilot authority check by name
    command: read scripts/merge_on_green.py:838-848 on main
    result: ci-authority/codex/merge-queue-pilot excluded as an invalidation receipt
unverified:
  - claim: The launchd primary fires and publishes by ~16:10 ET on a live session
    what_would_verify: Monday 2026-08-17 16:00 ET firing + scripts/close_pass_slo_report.py
  - claim: Snapshot day.c settles to the official close within minutes of a LIVE bell
    what_would_verify: Monday 16:01-16:20 ET polls vs next-day grouped (DSC falsifier command)
  - claim: "#5760 and #5761 merged"
    what_would_verify: gh pr view 5760/5761 --json state (armed at session close, checks running)
unresolved:
  - "16:15 ET product SLO vs measured ~7-8 min single-threaded collect: first live sessions decide whether W-L2 parallelization is required for the SLO or only for comfort."
  - "Arming-budget coverage (88/3,046 armed, probe_cap_cross 2,764) — W-L2."
next_actions:
  - "Verify #5760/#5761 merged; rebase from lane worktrees agent-a32af4cc3baeb108d / agent-a6a3be5eb79bcc32f if a re-run goes DIRTY"
  - "After #5760: bash scripts/install_closepass_launchd.sh from fresh main; launchctl print gui/$UID/com.macro.closepass; dry-run kickstart with --now 2026-08-14T20:26:00Z; confirm run receipt"
  - "After #5761: verify sentinel armed-pack surface on the VPS within ~33 min; run close_pass_slo_report.py --sessions 3"
  - "Monday 2026-08-17: W-ACCEPT session 1 of 3 — grade close→candidate→visible; GH lane must stand down"
do_not_redo:
  - "Do not rebuild the close observation on Yahoo — Massive grouped/snapshot is primary (DEC), Yahoo heal remains index-group store fallback only"
  - "Do not craft replay/rescue artifacts as bare {board_state:...} shells — the client refuses them; annotate the real evaluator doc like close_pass_mirror"
  - "Do not upper-case vendor tickers before joins (DSC:MASSIVE-TICKER-CASE-IS-IDENTITY); census of remaining sites is chipped (task_6fb8d4c3)"
  - "Do not add a VPS board-compute tier or a websocket — DEC alternatives close both until W-L2 evidence"
danger_areas:
  - "close-pass.yml carries THREE lanes' reasoning in comments (schedule, ledger law, backstop) — edit surgically, tests pin the shape"
  - "Two writers on live/prophet_live.json via CAS — never add a third"
  - "The lane worktree .claude/worktrees/closepass-host-lane is created by raw git (FULL checkout, data/ included) — the sparse hook does not govern it; GC is held off by its lock"
prs: [5743, 5746, 5758, 5760, 5761]
decisions: ["DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK"]
discoveries: ["DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE", "DSC:MASSIVE-TICKER-CASE-IS-IDENTITY"]
---

## Session shape (for the stranger)

One Fable orchestrator; three Opus builders + one Opus red-team spawned in
parallel worktrees. The account's 5-hour window capped mid-build and killed all
three agents; the orchestrator absorbed their work serially — finished PR-B's
last deliverable, shipped PR-C's completed-but-unpushed commit, completed the
red-team checklist itself — and ran the browser replay end-to-end. Cost of the
detour: ~2 hours. Nothing was rebuilt from scratch; the loss-proof mid-flight
handoff (#5758) is superseded by the close version of the same file.
