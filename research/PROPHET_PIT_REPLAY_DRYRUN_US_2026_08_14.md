# PIT replay dry-run proof — US session 2026-08-14 (lost to the 08-15→17 freeze)

**This is the PR proof artifact for the general PIT replay harness**
(`scripts/prophet_pit_replay.py`, masterplan
`research/PROPHET_PIT_REPLAY_HARNESS_V1.md`, authority
`DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT`). Dry-run only: nothing
was written to the checkout; the receipt below is the run's own output
(trimmed copy committed as
`research/PROPHET_PIT_REPLAY_DRYRUN_US_2026_08_14_receipt.json`; per-file
overlay rows and the 2.0MB captured snapshot row are elided and sha256-pinned —
the full receipt reproduces from the command below).

## Command

```bash
python3 -m scripts.prophet_pit_replay --market us --session 2026-08-14 \
  --vintage-worktree <work>/vintage-us-2026-08-14 \
  --work-dir <work>/work \
  --aux-panel-source <lane-checkout>/data/russell_breadth
```

## What the run established

1. **Vintage resolution** — bake slot `2026-08-14T22:30:00Z` (18:30 ET);
   resolved vintage `54af649d5e1a` committed `22:23:34Z`, 6½ minutes before the
   slot, proven first-parent ancestor of `origin/main`. This is the tree the
   cancelled bake (run 31848262472, superseded while queued, zero jobs) would
   have checked out.
2. **Structural truncation + fence** — the vintage store ends 2026-08-13
   (the stranded collect never wrote 08-14); the overlay appended exactly the
   08-14 session per file from `origin/main` (3,595 files written, 8 unchanged;
   vintage rows keep vintage bytes). Fence: **5,305 price files scanned, 0
   violations, 0 unscannable**, max date found 2026-08-14. Dead-proxy env pins
   active (`HTTP(S)_PROXY=http://127.0.0.1:9`, `TZ=UTC`, `RENDER_NO_DRIP=1`).
3. **Control fidelity (mandatory)** — the same harness rebuilt the vintage's
   OWN committed 2026-08-13 board: **jaccard 0.9855** vs floor 0.85 (68/69
   names; sole miss `EU`, attributable to the continuously-refreshed
   lane-checkout aux panel — the gitignored Russell close cache is supplied
   from a moving external source, §2b(2) of the masterplan). An earlier pass of
   the same harness before the review-fix wave measured **jaccard 1.0,
   exact order match** against the same reference with an earlier aux-panel
   state — the declared US price surface is complete.
4. **Reconstruction** — synthetic board `as_of=2026-08-14`,
   `rank_by=us_prophet_v2`, 70 buy rows, sha256 `3e2468999561…` —
   **byte-identical across three independent harness runs** (before and after
   the review-fix wave), i.e. the reconstruction is deterministic and
   insensitive to the aux-panel drift that moved the control by one name.
5. **Origination funnel (engine gates untouched, all on their own terms)** —
   70 buys → 52 admitted → 39 duplicate-id blocked (ids enumerated, #5305
   machinery) → 3 reorigination-blocked → 10 eligible → **6 would mint**,
   2 collided (live wins — the 08-17/18 recovery had already re-originated
   those episodes), 4 chronology-refused, 1 still refused. Both reconciliation
   identities close (52==52, 13==13).

   Would-mint set (recorded_at=2026-08-14, UNMARKED per the DEC):
   `BWXT-BULL-20260813, GNW-BULL-20260810, LAC-BULL-20260810,
   LYV-BULL-20260810, SPOT-BULL-20260701, WMB-BULL-20260813`.
6. **US board-ledger snapshot capture** — the vintage tree's own
   `grade_us_board.snapshot_today()` produced the `as_of=2026-08-14` row
   (sha256-pinned in the receipt); in an execute run it would ride the pending
   file `data/us_board_ledger/pending_replay/2026-08-14.json` and be absorbed
   by the next nightly through the ordinary append + dedupe path.

## What this dry-run deliberately did NOT do

No plans written, no pending entries staged, no receipts under `data/`, no
board published — §0.11 of the masterplan: this PR ships tooling + proof only.
Executing US 2026-08-14 (and CN/HK 2026-08-17) is the post-merge follow-up
under the DEC default.
