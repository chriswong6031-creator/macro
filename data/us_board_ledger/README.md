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
| 2026-06-16 | W1.3 options state: `opt_gamma_regime`, `opt_wall_up/down`, `opt_iv30`, `opt_dist_to_flip_pct`, `opt_voi_flag`, `opt_front7_charm_share` | 10–12% | Needs chain/summary store coverage at `as_of`; stores begin mid-June and cover an options subset of board names (gitignored R2 stores — populated on the runner, not locally). `opt_front7_charm_share` history restored by the 2026-08-02 `--backfill-ovc` repair |
| 2026-06-18 | Board-payload wave 1: `entry_status`, `act_level`, `validation_status`, `vol_squeeze`, `dispersion_state` | 78.2% | Board schema gained the fields on 06-18 boards |
| 2026-06-23 | `align_tier` | 30.0% | Board schema addition; only some lanes carry it |
| 2026-06-30 | W-C options: `opt_skew`, `opt_skew_5d_chg`, `opt_ivspread_rel`, `opt_pin_risk`, `opt_wall_dist_up/down_pct`, `opt_doi_slope_5d`, `opt_vanna_relief` | 9.2–9.4% | W-C snapshot stores begin 2026-06-30 (skew/ivspread) |
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
