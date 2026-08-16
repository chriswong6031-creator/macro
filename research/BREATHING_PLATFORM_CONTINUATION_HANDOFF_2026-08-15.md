# Breathing Platform — continuation handoff (2026-08-15 revival session, CLOSE)

**Commission:** Chairman directive 2026-08-15 — revive the program and ship the
product outcome. **Workstream:** `WS:BREATHING-PLATFORM` (program prophet-us).
**Rulings this session:** `DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK`,
`DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE`, `DSC:MASSIVE-TICKER-CASE-IS-IDENTITY`.
This FINAL version supersedes the mid-flight §NEXT (#5758) — that interrupt
(account 5-hour session cap killed three subagents) was absorbed in-session:
the main loop finished, reviewed, and shipped the dead builders' work itself.

## What shipped (all merged unless noted)

| PR | What | State |
|---|---|---|
| #5743 | WS + DEC + DSC records; replay launch config | MERGED |
| #5746 | **PR-A: Massive close truth** — grouped-daily primary / snapshot fallback with session-identity check, corp-action darking (fail-closed guard-down), case-exact vendor matching, store-bar-wins basis law, provenance meta, parity battery | MERGED |
| #5758 | Mid-flight loss-proof handoff | MERGED (superseded by this doc) |
| #5760 | **PR-B: host-native primary clock** — `com.macro.closepass` launchd 13:00 PT weekdays; runner (locked lane worktree, fetch/reset receipts, wait-for-close decision table, alarm, run receipts); close-pass.yml demoted to fail-open backstop with keyless stand-down | armed, checks running at close of session |
| #5761 | **PR-C: liveness ruler** — sentinel latency decomposition (close→candidate→visible with disclosed 1800s resolution), stale-armed-pack watchdog, `close_pass_slo_report.py` acceptance-record tool | armed, checks running at close of session |

## Measured facts the next session stands on

- **Production defect (before):** Fri 2026-08-14 board = 22 cards from 253/1,763
  evaluated (`no_todays_bar: 1508`), published ~19:20 ET (cron created +27 min,
  sibling queued 95 min).
- **Replay through the new path (after):** same session, real store + real
  Massive grouped closes → **1,684/1,763 evaluated (95.5%), 73 admitted, 73
  cards**, `close_source {store: 0, massive: 1684}`, `close_finalized: true`,
  58 corp-action darked (BYND 30:1 in-guard), 19 genuinely bar-less. Compute
  ≈7–8 min single-threaded on the Mac.
- **Parity:** 1,741/1,741 store-vs-Massive agreement within $0.005 (2026-08-13
  overlap; max diff $0.000117 = float32 store quantization). 15 same-session
  ex-dividend names still agreed to the cent.
- **Browser replay (§13), receipts-grade:** frozen N−1 (08-13) static page +
  planted runtime artifact through the REAL annotate shape (a bare
  `{"board_state": …}` shell does NOT paint — the client needs the evaluator
  document; the mirror's read-modify-write is the only production writer and
  the harness must mimic it). Expired Friday state: fetched 200 → REFUSED →
  static board intact (stale never masquerades). Fresh-stamped full-coverage
  state: **73 provisional cards mounted, nightly grid hidden**, bilingual card
  content (BIIB EN/ZH), desktop + mobile 375px with zero horizontal overflow.
  Deep-scroll pixel captures were black — the HIDDEN Browser pane stops
  compositing; `elementFromPoint` proved painted content at those coordinates.
  DOM/network receipts are the evidence of record.
- **Chaos battery in tests:** split-splice mutation (guard-broken half flips
  the real gate verdict), 10/50/100% coverage loss, provider timeout,
  guard-down zero-appends, stale-session snapshot refusal
  (`tests/test_close_pass_massive_close.py`, 43); runner lock/refuse/decision
  table/receipts/alarm (`tests/test_close_pass_host_runner.py`, 48); lane +
  workflow pins on the COMBINED A+B tree (`tests/test_close_pass_lane.py`,
  110).
- **Intraday determination (PR-D):** the plane exists (armed pack + 5-min VPS
  evaluator); tonight's pack: 88 armed of 3,046, `probe_cap_cross: 2764` —
  the W-L2 arming-budget number. PR-C's watchdog now alarms pack staleness.
- The merge control plane grew `ci-authority/*` contexts mid-session; the
  sweeper excludes `ci-authority/codex/merge-queue-pilot` BY NAME (an
  invalidation receipt, not a check — scripts/merge_on_green.py:838).

## Remaining to DONE (exact order)

1. **Land #5760 + #5761** (armed; sweeper merges on green — verify, don't
   assume; on a DIRTY re-run rebase from the lane worktrees
   `agent-a32af4cc3baeb108d` / `agent-a6a3be5eb79bcc32f`).
2. **Deploy the primary clock (after #5760 is on main):** from a fresh main
   checkout run `bash scripts/install_closepass_launchd.sh`, then
   `launchctl print gui/$UID/com.macro.closepass | head -5`, then a plumbing
   kickstart `python3 scripts/close_pass_host_runner.py --dry-run --now
   2026-08-14T20:26:00Z` (dry-run publishes nothing; proves lane worktree +
   venv + env + wait loop end-to-end). Confirm a run receipt lands under
   `~/Library/Application Support/macro-closepass/runs/`.
3. **PR-C live verification (after #5761 merges):** VPS pulls within ~3 min;
   next sentinel tick within 30 min. Verify the armed-pack surface appears in
   the sentinel report and `scripts/close_pass_slo_report.py --sessions 3`
   runs against the real state file.
4. **Monday 2026-08-17 live acceptance (W-ACCEPT, three sessions):** watch the
   16:00 ET launchd fire; expect board on R2 ~16:08–16:14 ET at ~95% coverage,
   mirror ≤5 min, browser ≤2 min poll → **user-visible ≤16:20 ET** (the 16:15
   SLO may need the W-L2 parallel collect — measure first, then decide);
   the GH 16:25 lane must stand down with its notice. Grade with
   `close_pass_slo_report.py`; record in the workstream per session.
5. **W-L2 next wave:** parallelize/raise the arming budget (2,764 probe-capped)
   and the collect() gate loop (~7–8 min single-threaded → ProcessPoolExecutor
   per the pack builder's pattern) — each behind its own before/after timing
   verification.

## Standing constraints (unchanged)
G0.2 no data/ writes from the lane; corp-action darking fail-closed;
store-bar-wins; no websocket (TP-1 owns the slot); no VPS board compute
(DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK); never weaken `_bsQualify`; merge on
CONCLUDED checks; the browser replay harness must write through the real
evaluator-document shape.
