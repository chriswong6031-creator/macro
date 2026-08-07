# US board ledger — column coverage map

**Artifact:** `retro_grades.parquet` — one row per `(as_of, lane, ticker, horizon)` for the
US Buy Board. Writer chain: `scripts/grade_us_board.py --nightly` (grades + spine columns)
→ `scripts/stamp_options_state.py` (options-state + tape-flow stamp columns). The v2 lane
(`retro_grades_v2.parquet`, SA-W5) is a parallel artifact with its own snapshot files.

**Why this file exists:** column population is a function of *when each column family
started* × *what its stores cover* — not of data quality. Every census that ignores this
rediscovers "dead" columns that are actually young, gated, or maturing. Measured
2026-08-04 (2,282 rows × 85 cols, `as_of` 2026-06-15 → 2026-07-21). Percentages will have
risen since; the start dates and mechanisms below are the durable part. Re-measure before
relying on any number here.

## Price-basis era — boundary 2026-08-06

Two eras live in this parquet, separated by the `price_basis` column. **Rows are never
re-graded across the boundary**, so the stamp is the only way to tell them apart.

| `price_basis` | Era | What it means |
|---|---|---|
| `unverified_pre_20260806` | 1 | Graded before the boundary. The name leg came from the RAW breadth close caches while the benchmark leg (SPY / sector ETF) came from the back-adjusted `data/yahoo`, so `excess_spy` and `excess_sector` could book a name's own dividend as underperformance. 2,277 rows at the boundary. |
| `adjusted` | 2 | Name and benchmark legs share the back-adjusted basis (`engine.price_ladder`). |
| `unadjusted` | 2 | The name has **no** adjusted counterpart in any store, so it is still priced from the raw cache — kept and disclosed rather than dropped. ~20.6% of freshly-graded rows (154 of 855 admitted tickers). Closing this needs a collector change, not a grader change. |

`price_source` names the exact store (`baskets_ohlcv` / `yahoo` / `data_stocks` /
`baskets_extras` / `closes_cache_UNADJUSTED`); it is null on era-1 rows because nothing
recorded it at the time.

**Era 1 is unverified, not presumed wrong.** Measured at the boundary, 2,277 of 2,287
shipped rows already agreed with the adjusted basis to <0.01pp — the caches happened to
have been re-based shortly before those rows were graded. Only 33 rows sat on a window
where the two bases genuinely differ, and on all 33 the stored value matches the adjusted
one.

**Why the rows were frozen instead of corrected.** The breadth caches are re-based *in
place*, so the same `(ticker, date)` reads differently on different days (`PNC`
2026-06-22: `234.71` on 2026-07-01, `232.85` on 2026-08-06). The merge used to be
keep-FRESH, which meant every run silently rewrote history: re-running the grader on
2026-08-06 would have moved **75 already-published rows, 19 of them materially** (worst
−1.94pp, `LPG` 2026-06-18 H5). Price-derived columns are now write-once
(`grade_us_board._FROZEN_PRICE_COLS`); annotations (regime stamp, archetype,
`board_tenure_days`, new spine columns) still accrue onto historical rows as before.

## Structural facts that bound every column

* **Grading lag:** a fire is graded only when its horizon matures. The shortest horizon is
  5 trading days and rows keep accruing per horizon, so max `as_of` trails the wall clock
  by ~2 trading weeks. This is not an outage.
* **Coverage starts are family-wide:** a column null before its family's start date is
  *unrecorded history*, not a defect. Legacy rows keep nulls (schema-union convention).
* **Store-gated columns can be null forever on old rows** even after their store matures:
  PIT gates count store rows `< as_of`, and `as_of` is frozen per row.

## Per-column coverage starts (measured 2026-08-04)

| First non-null | Family / columns | Populated | Mechanism bounding coverage |
|---|---|---|---|
| 2026-06-15 | Core grades: `ret`, `excess_spy`, `excess_sector`, `sector_etf`, `etf_ret`, `mae_close_excess_*` | ~100% | Ledger inception; price-resolvable names only |
| 2026-06-15 | `opt_opex_days` | 97.9% | Calendar-derived; excluded from the stamp retry gate |
| 2026-06-16 | W1.3 options state: `opt_gamma_regime`, `opt_wall_up/down`, `opt_iv30`, `opt_dist_to_flip_pct`, `opt_voi_flag`, `opt_front7_charm_share` | 10–12% | Needs chain/summary store coverage at `as_of`; stores begin mid-June and cover an options subset of board names (gitignored R2 stores — populated on the runner, not locally). `opt_front7_charm_share` history restored by the 2026-08-02 `--backfill-ovc` repair. `opt_voi_flag` and `opt_front7_charm_share` additionally go null on the first `as_of` after a chain-collection gap: both compare today's snapshot against YESTERDAY's open interest, and after a gap the prior snapshot is several sessions stale (GAP DISCIPLINE, `engine/options_stamp.py`) |
| 2026-06-18 | Board-payload wave 1: `entry_status`, `act_level`, `validation_status`, `vol_squeeze`, `dispersion_state` | 78.2% | Board schema gained the fields on 06-18 boards |
| 2026-06-23 | `align_tier` | 30.0% | Board schema addition; only some lanes carry it |
| 2026-06-30 | W-C options: `opt_skew`, `opt_skew_5d_chg`, `opt_ivspread_rel`, `opt_pin_risk`, `opt_wall_dist_up/down_pct`, `opt_doi_slope_5d`, `opt_vanna_relief` | 9.2–9.4% | W-C snapshot stores begin 2026-06-30 (skew/ivspread). `opt_doi_slope_5d` survives chain-collection gaps — it is fitted against session ordinals, so the slope stays a per-session rate — but nulls when its six snapshots span more than 11 sessions (GAP DISCIPLINE, `engine/options_stamp.py`) |
| 2026-06-30 | Confluence/alt-data confirmers: `news_burst`, `confluence_k`, `has_stop_guidance`, `smartmoney_add`, `sue_fresh`, `insider_cluster`, `altdata_conv_gte2`, `board_tenure_days` | 58.4% | W3 evidence-stack fields enter the board payload 06-30 |
| 2026-06-30 | Spine: `fwd_mfe_{5,10,21}`, `terminal_state_clean8_21`, `post_cushion_breach`, `signal_quality`, `tier_cascade` | 3–33% | W0.1 B-b; `fwd_mfe_h` populates only on that horizon's own rows, and only once matured |
| 2026-07-01 | PIT regime stamp: `vol_regime`, `quad_hard_label`, `fused_risk_label`, `risk_radar_state`, `regime_vector_degraded`, `vector_asof`, `staleness_hours` | 49.2% | `regime_vector.parquet` history begins 07-01; earlier `as_of` rows stay null (PIT) |
| 2026-07-02 | `donor_state`, `donor_sector` | 42.6% | G6a rotation context enters the board payload |
| 2026-07-06 | `hold_state`, `hold_days`, `hold_inv`, `hold_anchor_src`, `rate_pressure`, `gex_confirm_verdict` | 12–37% | W6-C HOLD tracker + GEX confirm enter the payload |
| 2026-07-10 | Tape-flow (P2.2): `opt_dte_quality`, `opt_flow_breadth_group` | ~2% | `data/tape_flow/daily/` store begins 2026-07-10 (see below) |

## Warming up — expected to be null today (do not report as dead)

* **`opt_net_signed_prem_5d_z`, `opt_crowding_flag` (0%):** both carry a 20-prior-observation
  PIT gate against the per-root tape-flow store. The store's first rows are 2026-07-10, and
  per-root accrual is **~weekly, not nightly**: the T2a lane budget-rotates a ~360-root
  universe (`scripts/build_tape_flow_daily --mode forward`, resume-from-last), and the step
  self-skips on runner hosts without the ThetaData Terminal (~2/5 nights). Measured
  2026-08-04: median 5 rows/root over 15 sessions. First non-null requires 20 store rows
  strictly before a fire's `as_of`: at measured cadence that is reached roughly 12 weeks
  after store inception (~Oct 2026 `as_of` dates, graded ~2 weeks later); at true nightly
  cadence it would be ~4 weeks. If these columns are still 0% well after the store's
  per-root depth crosses 20, *then* suspect the stamper. (SPY alone is backfilled to 2017
  via `--mode etf-history`; SPY is not a board name, so no ledger row benefits.)
* **`terminal_state_clean15_126` (0%):** 126-trading-day terminal window vs spine columns
  that began 2026-06-30 — first maturation lands ~early Jan 2027.
* **`fwd_mfe_21` (3.1%):** 21-day maturation lag on top of the 06-30 family start.

## Deferred by ruling — null by design

* **`opt_iv_rank_252` (0%):** explicitly deferred per ruling A9
  (`engine/options_stamp.py`) — it reads `data/thetadata_eod` greeks, which is mid-backfill
  with a known dedup defect (#1363). Wiring waits for the dedup repair + manifest-complete.
  `scripts/validate_options_entry.py` (S-IVR) already guards for it and self-documents the
  deferral. Do not retire; do not report as a defect.

## Retired / wired 2026-08-04 (this PR)

* **`species_id` — retired.** It was written as a literal `None` on every row
  ("multiple species bind this ledger; ambiguous" — no unique binding exists, so the column
  could never populate). The writer now drops it (including the legacy-carry path through
  the store merge); all known consumers read it via `.get()` and are unaffected.
* **`archetype` — wired.** It was read from the board-row payload, which never carried it
  (0% over 2,282 rows). Now resolved payload-first, else PIT lookup (greatest
  `asof_date ≤ as_of`) from `data/archetypes/history.parquet` (1,331 tickers) via
  `engine.neuralweb.context_api.archetype_asof`, with a fill-null-only backfill over
  existing rows in the nightly (FIX-6 precedent: PIT-honest retro-stamp). Coverage after
  the first nightly ≈ the store's ticker overlap with the board (~high; unclassified
  names stay null and are printed).

## Stamping conventions that shape coverage

* No-overwrite is **per column** for the tape-flow family (2026-08-04 fix): a computable
  column fills without freezing its still-null siblings; a row stays retryable while any
  tape-flow column is null. (Before the fix, the first non-null in the family committed
  all four and locked the rest at null forever — all 71 committed rows were frozen that
  way: 18 dte-only, 29 breadth-only, 24 both. They remain honest nulls since their PIT
  inputs cannot change, but future store repairs/backfills can now heal what they touch.)
* The options-state family retry gate excludes `opt_opex_days` and `opt_root_class`
  (always-computable columns get dedicated writes and never close the gate).
* Nightly coverage per column is printed by `scripts/stamp_options_state.py`; a stamp
  column that is 0% while its display twin populates trips the `_twin_silent_null_guard`
  ::warning (W-OVC class defect tripwire).

## Disclosed null eras — holes that must NOT be repaired by backfilling

`snapshots.jsonl` has **no rows for 2026-08-03..08-06**. That looks like an outage
someone should fix. The obvious fix — backfill the dates — is the **wrong action**, and
the machine-readable record of why is `disclosed_gaps.json`
(id `us-board-frozen-alpha-2026-08`).

**The board published every one of those days. It just ranked on frozen factors.** A GHA
cache regression had the `engine` job restoring `data/breadth/_closes_cache.parquet` from
a prefix-matched cache over the fresh panel `collect` had committed hours earlier, then
committing the stale copy back (`git add data/` + push_retry's `-X theirs`). Since the
board's ranking key **is** alpha — `build_stock_library.py:3850`,
`rank_setups(cand, as_of=alpha_asof, rank_by="alpha", ...)` — and alpha is stamped
`as_of = R.index.max()` off that panel (`engine/residual_alpha.py:277`), every board in
the window ordered its names by **2026-07-31 factors while pricing entry zones off current
data**. Measured: every `alpha.json` revision from 2026-07-31T20:35Z to 2026-08-06T16:36Z
carries one `as_of` value, while the buy lane moved 71 → 76 → 73 → 55 → 59 → 62. Different
boards, one stamp. The snapshotter keys on `as_of`, so it saw the same date nightly and
appended nothing.

**Why the hole rather than the rows.** Backfilling with corrected dates fixes the *dates*
and leaves the *rankings* wrong — Prophet would learn from orderings computed on six-day
stale factors at six-day newer prices. That is the corruption the exercise set out to
prevent. Operator adjudication 2026-08-07: record as a disclosed null era, no graded
entries, six days of learning signal forfeited so the substrate stays clean.

**This is enforced, not just documented.** `tests/test_grade_us_board.py` asserts the
window stays empty (`test_no_graded_rows_were_backfilled_into_a_disclosed_null_era`), so
filling it turns a test red instead of quietly widening a denominator. If a reconstruction
is ever wanted it needs a **new `board_definition` era stamp** — a re-ranked board is a
different admission rule from the one that actually published — plus a point-in-time
replay harness that does not exist today (`build_stock_library.py` has no argparse and no
as-of clamp; `as_of` is derived from whatever panel is on disk).

The cause is fixed (#4798) and verified in production: `data: daily collection 2026-08-07`
wrote `max_date=2026-08-06` (349×510), the first advance since 07-31. The guard against
recurrence is
`tests/test_daily_collect_commit_path.py::test_no_job_restores_a_stale_cache_over_data_it_will_commit`.

**The alarm was never the gap.** `build_stock_library._board_continuity_warning` printed
*"22 builds all claiming as_of=2026-07-31"* every night throughout, and is marked
`Display-only: never a gate`. Detection worked; escalation did not.
