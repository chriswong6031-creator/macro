# US Context Vector — point-in-time candidate store

`candidates.parquet` — one row per analyzed US universe name per night, **including
names that never passed the raw signal gate**. Producer:
`engine/us_context_vector.py`, stamped from `scripts/build_stock_library.py` at the
end of its nightly run. Roadmap: `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §2.

## Zero authority

Nothing reads this store for scoring. It changes no lane, no rank, no score and no
gate, and it **originates nothing** — every column is read off a producer that
already ran that night (glass-box law; A7). Any column here reaches decision
authority only through the roadmap §3 bounded-authority ladder, one axis at a time,
each with its own preregistration.

## Integrity rules

| Rule | Mechanism |
|---|---|
| Nightly is the sole advancer | `ledger_lane.nightly_advance_enabled()` (`COLLECT_LANE=nightly`, `US_LANE` legacy alias) is the **first statement** of `append_candidates` — an intraday or render lane returns 0 without opening a file |
| PIT discipline | keep-first on `(stamp_date, ticker, board_definition)`; a rerun can never rewrite a night already stamped |
| No retroactive backfill | only same-night values are stamped; a column added later is null for prior nights and self-heals **forward only** |
| Schema union on append | a new column never discards old columns; a retired column is preserved for the nights that had it |
| Fail-soft | every failure path logs and returns 0; research telemetry never breaks the nightly build |

## Measured facts (2026-08-04, this Mac Studio, 1,540-name universe)

- **Shape:** 1,540 rows x 150 columns for one `stamp_date`.
- **Assembly cost:** 500.8 s (8.3 min) total. Of that, **~2.8 s is everything except
  the Context Snapshot** — `neuralweb.context_api.context_frame` is essentially the
  entire budget at 0.302 s/name, linear.
- **Growth:** 462 KB for the first night; 99 KB/night marginal measured on repeated
  nights. Real nights vary more than the repeat test, so the true marginal sits
  between those bounds: **~25-115 MB of file after one year (252 sessions)**.

### Growth caveat (flagged, not solved)

The store is git-tracked and fully rewritten every night, so each nightly commit
stores a **whole new blob** — parquet is already compressed, so git deltas it
poorly. Projected git-history cost after one year is **3.2-14.7 GB**. The CN
sibling (`data/china_prophet_rank/`) has the same shape and the same exposure. If
that projection is unacceptable, the fix is date-partitioned files or an R2 offload
per the render-budget law — **not** attempted here (out of scope for the §2 build).

## Column groups and honest coverage

Coverage is uneven **by construction** and disclosed rather than imputed. A null
means "not measured for this name tonight", **never "false"** (#4485).

| Group | Cols | Populated (2026-07-31 dry run) | Source |
|---|---|---|---|
| identity / board | 27 | spine 100%; board-only fields ~3% | `signal_gate.gate()` verdict (full universe) |
| itemized score legs | 10 | **3.2%** | `us_board_rank.score_rows()` — the US builder runs it on the **buy lane only**, so legs are null off the board. Read off, never recomputed |
| theme | 13 | 20.5% (membership); foresight 8.6% | `data/baskets/membership.json` + `data/baskets/latest.json` + `config/theme_crosswalk.yml` |
| event | 7 | `days_to_report` 88%; `in_blackout` 100%; 8-K 38% | `earnings_blackout.assess` + `earnings_catalyst.board_row_fields` (full universe) |
| flow | 3 | `turnover_pctile_20d` 99.7% | volume caches, S-A idiom |
| regime | 5 | 100% (one value for every row of the night) | `data/regime/latest.json`, `data/macro_snapshots/latest.json` |
| risk | 2 | `ext_z` 94.5% | `extension.extension_signals` (full universe) |
| quality | 82 | mean 15.8% absent | `neuralweb.context_api.context_frame`, all 11 dims |

`context_dims` records, **per row**, which Context Snapshot dimensions were
assembled that night. The public API exposes no dimension-subset parameter, so all
11 are always computed; if that ever changes, the store itself shows it rather than
thinning silently.

## Named debts

1. **`turnover_pctile_60d` — DATA-BLOCKED, stamped null.** The volume caches carry
   only ~51 non-null sessions (backfilled 2026-05-19). The column self-heals with
   **no code change** once the cache deepens (~mid-Aug 2026).
2. **`stoch_ob` / `stoch_bear` / `macd_bear` — NOT SHIPPED.** These are computed as
   inline locals in `engine/confluence_tiers.py::cascade()` (lines 230-235) and
   discarded; only their OR-negation `not_topped` survives, and that is not on the
   `signal_gate` verdict either. Stamping them needs a 3-line additive change to a
   scored-gate module, which this PR's fence forbids. Deliberately **omitted** rather
   than shipped as three permanently-dead columns (carried-columns law, roadmap §2:
   never leave schema that lies). Schema union makes adding them later free.
3. **`sue_z`, `catalyst_class`, `gex_state`, `flow_attention_z`, `short_vol_ratio`,
   `psq_stage`, `day3_mark_class`** — named in the roadmap §2 sketch, not built here.
   No dead columns were reserved for them.

## Divergences from neighbouring implementations (deliberate, documented)

- **`turnover_pctile_20d`** ports the S-A research idiom (`rank(pct=True)` over the
  trailing 20 sessions). `prophet_doors._turnover` uses `(w <= last).mean()` over an
  adaptive `min(60, available)` window. The two differ on ties; they are separate
  fields with separate names, not a fork of one field.
- **`relay_position` / `relay_count_3d`** follow the **live production** definition in
  `prophet_doors._RecordedFeatures._relay` (per-ticker, strict `>` against the prior
  63-session max), not the research stand-in, which broadcasts one basket-day value
  to every co-breakout. Window constants are imported from `prophet_doors` so they
  cannot drift.
- **`stamp_date`** is the US stamp column; the CN sibling uses `date`. Reconciling the
  two is the first item for the joint cross-market contract
  (`research/CONTEXT_VECTOR_SCHEMA_CONTRACT.md`, joint-pending-CN-adjudication).
