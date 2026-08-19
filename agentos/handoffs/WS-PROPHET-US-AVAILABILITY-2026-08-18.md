---
workstream: "WS:PROPHET-US-AVAILABILITY"
session: "claude/prophet-pit-replay (worktree angry-varahamihira-6a3544)"
model: fable
ended_because: complete
mission: >
  Build the general point-in-time replay harness commissioned by
  DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT: reconstruct a named
  market session's Prophet board (US/CN/HK/CA/Intl) from PIT stores,
  parameterized by (market, session date), entering rows into the forward
  ledger unmarked, with a dry-run replay of one lost session as the PR proof.
state_before: >
  Policy permitted backfills by default but no tool could execute one:
  scripts/backfill_prophet_outage.py pinned to 2026-08-09,
  backfill_prophet_outage_20260811.py to 2026-08-11, build_stock_library.py
  with no as-of capability. Sessions US 2026-08-14 and CN/HK 2026-08-17 lost
  to the ruleset freeze + run-supersede (research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md)
  with no recovery path.
changed:
  - path: scripts/prophet_pit_replay.py
    what: >
      NEW general harness (~2,950 lines): market registry (us/cn/hk resolved;
      ca/intl DECLARED-UNRESOLVED fail-closed), vintage resolution
      (rev-list --first-parent --before bake slot), vintage worktree management,
      append-only price overlay + fence (lifted generalized from the 08-11
      script), alpha prestep (US), mandatory control-fidelity pass, origination
      + collision/chronology machinery (US), vintage-lane ledger delta capture,
      pending-entry writer, receipts, disclosed-gap guard, session validation,
      dead-proxy env pins + pinned-store byte assertions, sparse-tree execute
      refusal, CLI with dry-run default / --execute / --verify-collisions /
      --resolve-only.
  - path: scripts/grade_us_board.py
    what: absorb_pending_replays() in the --nightly path (shared _append_snapshot_row extraction).
  - path: engine/china_standout_track.py
    what: absorb_pending_replay() through the live append/dedupe; _merge_and_write date-sorted.
  - path: engine/board_ledger.py
    what: same absorb shape for the HK board-order ledger, HK-gated.
  - path: scripts/build_hk_pick_lab.py
    what: absorb_pending_replay() via pick_lab.ledger.append_fires with schema/market/staleness validation.
  - path: scripts/check_surface_freshness.py
    what: board-newest-as_of now max over all snapshot lines (was reverse-scan-first — order-dependent), per-line torn-line tolerance.
  - path: scripts/build_track_record_page.py
    what: _compute_board_series sorted by as_of (second order-dependent reader).
  - path: tests/test_prophet_pit_replay.py, tests/test_pit_replay_absorb.py, tests/test_pit_replay_absorb_asia.py, tests/test_check_surface_freshness.py
    what: ~280 new tests across harness primitives, absorb idempotence, gap guard, vintage resolution, order safety.
  - path: research/PROPHET_PIT_REPLAY_HARNESS_V1.md
    what: design of record (frozen spec, §0 gates, §2b named residuals).
  - path: research/PROPHET_PIT_REPLAY_DRYRUN_US_2026_08_14.md (+ _receipt.json)
    what: the PR proof artifact (dry-run of the lost US session).
  - path: research/PROPHET_LEDGER_SCHEMA.md
    what: dated addendum pointing at the DEC and the harness.
verified:
  - claim: Control fidelity — the harness reproduces the vintage's own committed 2026-08-13 board
    command: python3 -m scripts.prophet_pit_replay --market us --session 2026-08-14 --vintage-worktree <w> --work-dir <w2> --aux-panel-source <lane>/data/russell_breadth
    result: jaccard 1.0 exact-order pre-fix-wave; 0.9855 (68/69, sole miss EU from the moving aux panel) on final code; floor 0.85
  - claim: The reconstructed 2026-08-14 board is deterministic
    command: three independent harness runs (before/after the review-fix wave)
    result: identical sha256 3e2468999561…, as_of=2026-08-14, us_prophet_v2, 70 buy rows every time
  - claim: Lookahead excluded by construction over the whole declared surface
    command: fence_no_bar_after inside the run (receipt fence block)
    result: 5,305 files scanned, 0 violations, 0 unscannable, max date 2026-08-14
  - claim: Full regression sweep green
    command: python3 -m pytest tests/test_prophet_pit_replay.py tests/test_pit_replay_absorb.py tests/test_pit_replay_absorb_asia.py tests/test_prophet_outage_backfill_20260811.py tests/test_prophet_outage_backfill.py tests/test_grade_us_board.py tests/test_check_surface_freshness.py tests/test_china_standout_track.py tests/test_board_ledger.py tests/test_pick_lab_ledger.py tests/test_pick_lab_hk_runner.py tests/test_gh_annotation_line_start.py -q
    result: 590 passed, 0 failed
  - claim: Registry resolves the three immediate candidates and refuses the right things
    command: five --resolve-only invocations (us 08-14, cn 08-17, hk 08-17, us 08-16, us 08-04)
    result: first three rc=0 with correct vintage SHAs (54af649d / f6eefa29 ×2); Sunday refuses on the NYSE calendar; 08-04 refuses citing us-board-frozen-alpha-2026-08
  - claim: Opus adversarial review ran and every finding was closed
    command: reviewer packet (13 findings — 1 ship-blocker, 5 must-fix, 7 notes) then fix wave + re-sweep
    result: all 13 implemented; the reviewer's reproduction cases now covered by tests
unverified:
  - claim: CN/HK control-pass fidelity clears the 0.85 floor
    what_would_verify: a cn/hk dry-run (the gitignored breadth close caches are absent from this host's lane checkouts, so the universes will build narrower — the control pass will price exactly that; --allow-low-fidelity records a waiver if the operator accepts)
  - claim: The absorb hooks behave on a REAL nightly
    what_would_verify: first nightly after an executed replay (pending file absorbed, deleted, ledger row present once)
do_not_redo:
  - "Do not add an --asof flag to build_stock_library — the harness truncates the STORE, not the reader; a read-time clamp is only as good as its coverage of a 6,500-line builder (charter §5.2 lesson, preserved)."
  - "Do not gate the CN drip collectors in current lane code as a replay defense — the vintage tree runs OLD code; only harness-side controls (dead proxy + pinned-store assertions) bind (DSC:VINTAGE-REPLAY-RUNS-THE-OLD-CODE)."
  - "Do not mark replayed rows (origination_mode or any flag) — the operator explicitly declined; DEC records the accepted cost."
danger_areas:
  - "site/factordata/* is never written by the harness; reconstructed boards stay unpublished."
  - "data/prophet/ledger.jsonl, board.parquet, snapshots.jsonl, hk_board.parquet: absorb-only via each lane's own pass — never direct writes."
  - "The aux --aux-panel-source panels are a moving external input; the control fidelity number inherits their drift (measured: 1.0 → 0.9855 across a few hours)."
unresolved:
  - "CN/HK control fidelity on this host without the gitignored breadth close caches (aux sources absent from the lane checkouts here — control will price it; may need --allow-low-fidelity adjudication or a host that carries the caches)"
  - "HK 2026-08-17 store-tail availability (CN confirmed on main; HK stores not yet re-checked post asia-close 08-18)"
next_actions:
  - "Execute US 2026-08-14: --execute in a fresh FULL worktree; PR carries plans + pending entry + harness receipt; run --verify-collisions immediately before merge; merge in a clear engine window; verify the next nightly absorbs + advances."
  - "Execute CN 2026-08-17 and HK 2026-08-17 the same way after re-verifying store tails and aux cache availability."
  - "Complete CA/Intl registry entries (bake lane, price-surface census, control validation) before any CA/Intl replay."
---

Cold-stranger note: read `research/PROPHET_PIT_REPLAY_HARNESS_V1.md` first —
§0 gates and §2b residuals are the contract; the dry-run proof doc shows what a
healthy run looks like. The harness is operator/session-run only (no schedule).
