# Breathing Platform — continuation handoff (2026-08-15, revival session, MID-FLIGHT)

**Commission:** Chairman directive 2026-08-15 — revive the program, ship the
product outcome (same-session board by ~16:05–16:15 ET, intraday freshness,
failure isolation, honest staleness). **Workstream:** `WS:BREATHING-PLATFORM`
(merged, #5743). **Rulings:** `DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK`,
`DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE` (both merged, #5743).

**WHY THIS DOC EXISTS MID-SESSION:** the account hit its 5-hour session limit at
~10:35Z Sat (resets 05:10 PT / 12:10Z). Three subagents were terminated early by
the API limit, two of them with substantial UNCOMMITTED work in their worktrees.
This doc is the loss-proof state. The commissioning session (this one) resumes
post-reset; if it cannot, a fresh session executes §NEXT verbatim.

---

## §0 Diagnosis (measured, done — do not redo)

Friday 2026-08-14 real product outcome: board published **~19:20 ET** (cron
drift 27–45 min + macstudio queue waits to 95 min) with **22 cards from 253 of
1,763 names evaluated** — `skipped {'no_todays_bar': 1508}` because the keyless
Yahoo heal covers the index group only. Coverage = source defect; latency =
clock defect. Everything else in W-L1 (renderer, receipt, mirror, reader-side
SLA sentinel) is merged and works; lane first green 2026-08-13 (#5495).

## §1 State of the five lanes

| Lane | State | Where |
|---|---|---|
| Session records (WS/DEC/DSC + launch.json) | **MERGED** #5743 (sweeper, 10:12:47Z) | main |
| **PR-A Massive close truth** | **OPEN #5746, COMPLETE, unarmed** — built+measured, 43+92 tests green, parity 1,741/1,741 ≤$0.005, simulated Fri coverage 253→**1,684** (58 corp-action darked; BYND verified in guard). Found+fixed vendor case-sensitivity trap (TPC/TpC); minted `DSC:MASSIVE-TICKER-CASE-IS-IDENTITY` | branch `claude/breathing-pr-a…` via worktree `agent-a2d375e7109169e63` |
| PR-A red-team | **DIED MID-PASS** (session limit), no verdict issued. My own review of collect() integration + guard internals: ship-quality (tz-safe append, only-forward, store-wins, fail-closed guard-down, 0-close refusal, ns sanity band) | rerun post-reset, then arm #5746 |
| **PR-B host clock** | **UNCOMMITTED, ~90% built** — runner + plist + installer done; died while extending `tests/test_close_pass_lane.py` (workflow demotion pins) | worktree `.claude/worktrees/agent-a32af4cc3baeb108d` (dirty — DO NOT GC) |
| **PR-C liveness ruler** | **UNCOMMITTED, mid-flight** — died resolving an additive conflict | worktree `.claude/worktrees/agent-a6a3be5eb79bcc32f` (dirty — DO NOT GC) |

PR-D was resolved by determination (no build): intraday plane exists (armed
pack + 5-min VPS evaluator); measured gap = arming coverage 91/1,761
(probe_cap_cross 1,535) → W-L2 with its own timing verification. PR-C adds the
stale-pack watchdog (armed pack was as_of 08-13 on Sat with nothing alarming).

Case-collision census chipped: task `task_6fb8d4c3` (massive_stock_day
filenames upper-case vendor tickers — same trap class, durable artifacts).

## §NEXT — exact resume order

1. **Resume builder-B and builder-C in their own worktrees** (SendMessage to the
   original agents if the session survives; else fresh Opus builders pointed AT
   those worktrees with "finish + push + PR" — the work is on disk, do not
   rebuild from scratch). B's remaining scope: finish lane-test pins, plutil
   -lint + bash -n, PR. C's remaining: resolve its additive conflict, tests, PR.
2. **Rerun the PR-A red-team** (opus reviewer, prompt in session transcript —
   9 numbered break-attempts incl. case-set asymmetry, 16:00Z boundary, concat
   dtype). On SHIP: `gh pr edit 5746 --add-label merge-on-green`, own to merge.
3. **After A+B merge: deploy the launchd primary** — run
   `bash scripts/install_closepass_launchd.sh` (installer ships in PR-B),
   verify `launchctl print gui/$UID/com.macro.closepass`, kickstart a
   `--dry-run --now 2026-08-14T20:26:00Z` pass, confirm the run receipt +
   R2 untouched (dry-run publishes nothing).
4. **Replay acceptance (§13)** — harness PROVEN mid-build this session:
   freeze `site/us_stocks.html` at `dfa3d2580482` (carries the 08-13 board);
   project the real R2 Friday board through
   `engine.close_pass.board.board_state()` into `site/live/prophet_live.json`
   (measured output: rel=ahead, 22 tickers, 22 cards, card_complete=True,
   valid_until=2026-08-15T06:00:00Z — REGENERATE fresh or the client will
   correctly refuse the expired stamp); serve via `.claude/launch.json`
   `site-static` (:8931); browser-verify the provisional grid mounts
   (`data-provboard="1"`) replacing the static N−1 grid; screenshot;
   **REVERT BOTH OVERRIDES** (`git checkout -- site/us_stocks.html && rm
   site/live/prophet_live.json`). Repeat post-merge with the PR-A path
   (`--now` replay through close_pass_publish itself for the full-coverage
   board). EN/ZH + mobile + dark per §13.
5. **Chaos battery** — most of §12 ships inside A/B tests; verify the remainder
   (duplicate-pass dedup, DST sibling, R2-failure warning path) via targeted
   pytest + one forced GH-backstop no-op run, then record results in the
   workstream.
6. **Return packet to Chairman** (§17 skeleton lives in this session's plan):
   before/after architecture, measured causes, PR/SHAs, deploy receipts,
   parity numbers, replay evidence, chaos matrix, **live acceptance =
   EXPLICITLY OPEN until Mon 2026-08-17+3 sessions** (Saturday commission — no
   fake RTH acceptance).
7. **Monday 16:00 ET** — watch the launchd primary fire; run
   `scripts/close_pass_slo_report.py` (PR-C) for close→candidate→visible;
   expect ~16:05–16:12 ET first board at ~95% coverage; GH lane should
   fast-exit as backstop.

## Standing constraints (unchanged)
No data/ writes from the lane (G0.2); no websocket (TP-1 owns the slot); no
VPS compute tier (DEC); store-bar-wins basis law; corp-action darking is
fail-closed; never weaken `_bsQualify`; merge on CONCLUDED checks only;
`merge-on-green` + stay.
