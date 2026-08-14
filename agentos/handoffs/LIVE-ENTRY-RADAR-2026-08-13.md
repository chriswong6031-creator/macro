# Handoff — WS:LIVE-ENTRY-RADAR — 2026-08-13 (PR-0)

**Session:** PR-0 orchestration (Fable main loop + 5 research tracks + adversarial review).
**State at stop:** PR-0 open and armed `merge-on-green` (PR number in the workstream's W0 row
once assigned; branch `worktree-live-entry-radar-95b9ce`). W0 completes at merge.

## What exists now

- **The frozen contract:** `research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` — governing
  document for PR-1..PR-9. Frozen at merge; changes only via §18 append-only amendments.
  All eleven commissioned PR-0 deliverables are in it, each grounded in a track census.
- **Evidence appendices:** `research/live_entry_radar/TRACK_{A,B,C,D,E}_*.md` — receipts for
  every load-bearing claim. Track A additionally computed G0 fired-date tables for
  NVDA/NFLX/TSLA (§2.6) — the operator-facing G0-VIS confirmation artifact, mirrored in the
  PR body.
- **Records:** `DEC:LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE`, `DEC:LER-PROPHET-BOARD-IS-DESIGN-REFERENCE`,
  `DEC:LER-LIVE-LANE-VPS-5MIN-REST`, `DSC:TERMINAL-GREY-DOT-IDENTITY`, `WS:LIVE-ENTRY-RADAR`
  (waves W0–W9 = PR-0–PR-9).

## Verified claims (each names its receipt)

- Grey-dot identity: verified by Track A staging `origin/master:signal_layer/*` and running
  `early_dots(compute_signals(close), close)` over shared `data/stocks` parquets; emitter
  comment verbatim at `confluence_v2.py@origin/master:1174-1176`.
- Kill compliance: `DNR:KILL-WASHOUT-TURN` construction decoded from
  `ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:259,271-276`; contract §2 carries the
  four-part distinction + NC-2 kill-arm inheritance.
- Live plane: entitlements from the TP-0 probe table
  (`MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md:159-176`); WS-slot eviction from
  TP-0.5 (§12); Caddy gating verified live (401 on unlisted `/live/*.json`).
- `python3 scripts/agentos.py validate` exit 0 at commit time.

## do_not_redo

- Do NOT re-census the lobe producers, indicator implementations, live plane, or eval
  conventions — Tracks A–E are the record; extend them, don't re-derive.
- Do NOT re-litigate: parity strategy (artifact-consumption primary, locked-spec fallback,
  no shared lib), live architecture (VPS 5-min REST, no WebSocket), scoring doctrine, or
  the frozen §10 numbers — those are contract-frozen; changes go through §18 amendments.
- Do NOT read `charting-app`'s working checkout for G0 spec (month-stale, pre-#392 leak);
  spec reads pin `origin/master`. Do NOT seed any reimplementation from
  `Macro/research/signal_engine/confluence.py` (verified silent fork, no `known_ts`).

## danger_areas

- `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`,
  `engine/signal_quality.py`, `engine/prophet_*.py` — never touched by this program
  (contract §16 mechanical non-interference; sibling `WS:PROPHET-US-ENTRY-TIMING`).
- The Massive stocks WebSocket slot — unclaimed estate-wide; overflow EVICTS the oldest
  connection silently. Radar never opens it (`DEC:LER-LIVE-LANE-VPS-5MIN-REST`).
- Session worktrees are sparse (`DSC:SESSION-WORKTREES-ARE-SPARSE`) — data/, site/,
  mockups/ absent; existence checks via `git ls-files`/`git show`, never bare `ls`.
- The shared deep store read by Terminal showed last bar 2026-07-08 at census — PR-2 must
  verify production freshness and hard-gate on `feed_end` before trusting slices.
- Track D flag, unresolved: `data/prophet_live/forward.parquet` has zero rows ever
  committed to main — confirm whether that is expected early-accrual or a stalled pipeline
  before treating prophet-live's reconciler as a fully proven precedent for PR-5.

## next_action

1. **G0-VIS:** operator checks the fired-date tables in the PR body / Track A §2.6 and
   confirms or names a missing dot. Blocks only PR-2's parity freeze.
2. **W1 (PR-1):** probe universe + enlistment bus per contract §6 + Track C. Independent of
   G0-VIS; can start immediately after W0 merges. Build items called out in §6: wrapper
   classifier, hot_tape nomination tap, Supabase watchlist adapter (server-side read).
3. **W2 (PR-2):** detector framework + G0 artifact consumption + fixtures F1–F6 (needs
   G0-VIS closed before the parity freeze).
4. Each build session: fresh worktree off origin/main, read the contract + relevant track
   appendix first, spawn Opus `builder` per §Model routing, arm merge-on-green, ci_handoff.
