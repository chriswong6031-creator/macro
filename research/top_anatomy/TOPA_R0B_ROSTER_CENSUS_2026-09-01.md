# TOPA R0b — Refreshed Roster / Exemplar Census (descriptive read, 2026-09-01)

Operation `topa-r0b-winner-health-restore-20260901-coo-001` · `WS:TOP-ANATOMY` ·
masterplan §8 R0 requirement. **Chronology status:** this is the §5.2 *descriptive/
operational* read — current tier membership and display states only. No confirmatory
out-of-time effect estimate was computed in producing it (`TOPA_OOT_PREREG.md` §7); the
forward ledger advanced **+0 rows** (off-lane no-op, nightly remains the sole advancer).

## Read provenance

- Store: `data/massive_stock_day` restored from R2 (bucket `mastermindx`) on 2026-09-01
  PDT — 21,460 objects restored, 20,934 per-ticker parquets on disk; the committed
  `_manifest.json` is deliberately not restored by `fetch_r2` (publish-side artifact), so
  this local read's `store_vintage` field is empty — a local-only quirk; the production
  checkout carries the committed manifest and stamps normally.
- Read: `scripts/build_top_maturation.py` full panel (20,934 source files), generated
  2026-09-02T00:26:24Z, `asof 2026-09-02`, **`data_last_day 2026-08-28`,
  `tape_lag_sessions 3`** (disclosed; store currency belongs to the Massive Stock Day
  owner plane — a read-side census consumes it, never repairs it).
- Universe: `universe_n 2617` eligible names on the last session; the §exclusion
  instrument filter removed **92 non-stock instruments** (ETP/ETN/fund tickers) from the
  board.
- Analog libraries: committed frozen exports (`data/top_anatomy/library*.parquet`,
  vintage 2026-08-11T01:08:16Z, window **2022-07-18 → 2026-07-02**) — frozen-tape
  training window; nothing post-boundary is inside any library.
- Artifact: `winner_health.v2`, **`null_state: false`**, all three tiers
  `readable: true` — the first truthfully non-null read since the ordering defect began
  (nightly artifacts carried `null_state: true` on 08-23/27/28/29).

## Roster census (per tier)

| tier | EXT days | episodes | candidates (recently EXT) | on board | healthy | watch | thinning | breaking | no_read |
|---|---|---|---|---|---|---|---|---|---|
| primary | 124,182 | 5,078 | 373 (209) | **223** | 55 | 102 | 7 | 59 | 0 |
| r63 | 112,685 | 5,934 | 396 (237) | **203** | 63 | 85 | 11 | 44 | 0 |
| atrz | 426,844 | 11,732 | 689 (373) | **387** | 128 | 162 | 26 | 71 | 0 |

(EXT-day/episode counts are whole-tape census scale under the frozen phase-0
constructions; the board is the current-session display roster.)

## Exemplars (as rendered, tier primary)

- **CADL** (Candel Therapeutics) — `extended_healthy`, 77 sessions in episode,
  r126 +153.8%, r21 +39.0%; tier-local analog memory: n=40 similar historical runs,
  27/40 topped within 63td, median further gain +48.4%, median drop from high −39.3%
  (track W). The board answers "what did runs like this one do" with honest analog
  counts, not a probability.
- **CRWD** (CrowdStrike) — `extended_healthy`, 62 sessions in episode, r126 +134.9%;
  analogs n=40, 18/40 topped within 63td, median further gain +32.2%, median drop
  −42.2%.

## Local-reproduction note (so nobody misreads these steps as production gaps)

This census ran in a sparse session worktree, which required materializing committed
inputs the sparse cone omits (`data/universe/membership.parquet`, the three breadth
`constituents.parquet` tables, the six `data/top_anatomy/library*/thresholds*` files) —
all committed on `origin/main` and present natively in any full checkout, including the
production runner's. The only production gap was the shard-restore ordering repaired by
PR #6723; the local chain `R2 store → top_maturation → winner_health.v2 (non-null) →
winner_health.html (2.3MB real board, names rendered)` is the pre-production replica of
tonight's expected nightly behavior.
