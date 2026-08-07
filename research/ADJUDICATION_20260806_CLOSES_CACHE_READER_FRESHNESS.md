# Adjudication 2026-08-06 — per-column freshness across the `_closes_cache` readers

Status: ADJUDICATED + SHIPPED (2026-08-06). Closes chip (3) of
`research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md` §4 — "the ~19 other
breadth-cache readers (factor panels, sector map, chart data, …) that read frozen
columns with no freshness gate — same class, separate program".

Scope: consumers of `data/{breadth,smallcap_breadth,midcap_breadth,russell_breadth}/_closes_cache.parquet`.
The sibling #4643 fixed the **scan-admission** side (`build_stock_library.universe()`
demotion) and the **collector silence**. This fixes the **reader** side. Boundaries
from #4643 are honored: the caches stay union-forever (no pruning), no membership
edits, no `data/` writes, no price-basis mixing.

## §0. Verdict

**The dominant defect was not staleness — it was the MERGE.** All measurements below
are re-taken at the 2026-07-31 cache vintage in this worktree; the brief's line numbers
had drifted and three of its named readers turned out not to read the cache at all
(§4).

Because the caches are union-forever archives, a name that MIGRATES between index
tiers (S&P 500 ↔ 400 ↔ 600) keeps a column in the tier it LEFT — frozen on its exit
date — while the tier it JOINED carries a live column. Every consumer merged the tiers
with the same idiom (concat in a fixed tier order, then `~columns.duplicated()` /
`setdefault`), which keeps the FIRST occurrence. For a migrant that is the **dead**
column, and the live one — sitting in the very same merge — is discarded.

The panel already contained the right answer and the readers threw it away.

## §1. Receipts (re-measured 2026-08-06 @ cache tip 2026-07-31)

Frozen columns (>7 calendar days behind the panel tip): breadth 5, smallcap 24,
midcap 12 = **41**; russell's closes cache is runner-only (absent in a bare checkout).
In-constituents leaks are still just CWEN-A plus the never-populated FI/MMC, exactly
as #4643 found — the constituents AND-gate holds.

**Dead-picked-while-a-live-column-existed**, by the tier order each reader uses:

| tier order | readers | dead-picked |
|---|---|---|
| breadth, smallcap, midcap | `equity_factors._closes`, `manager_quality`, `manager_trades` | 6 — CAG CPB POOL SANM SMTC VIAV |
| breadth, midcap, smallcap | `build_impulse`, `build_pick_lab`, `build_dispersion_regime` | 7 — BLKB CAG CNXC COTY CPB GT POOL |
| breadth, smallcap, midcap, russell | `build_chart_data` | 6 (+5 truncated, below) |

Downstream, measured on the shipped artifacts:

- **`site/factordata/factors.json`** — 32 of the 41 frozen names are in the table.
  Frozen names reached the **displayed** leaderboards: `composite_display_top`
  (CNXC, 43d), `low_beta` leaders (BLKB, CNXC), `low_vol` leaders (GTLS),
  `composite_display_bottom` (VIAV, SANM). The low-vol/low-beta case is
  mechanism-backed, not merely stale: a frozen name's recent volatility is
  *unobserved*, so freezing selects a name **into** the calm-factor leaderboards.
- **`site/factordata/alpha.json`** — VIAV published as sector leader **#9 of 221**
  (alpha 2.08, total_mom 174.9, rs 97) off a column that stopped 23 days earlier;
  its live column stood 9.2% lower. `residual_alpha` imports the same `_closes`.
- **Price error from the `ffill` resurrection** (`px.ffill().iloc[-1]`), cross-checked
  against the fresh yahoo store: **FLEX +29.8%** (147.61 vs a true 113.75),
  VIAV +10.2%, POOL +7.2%, CPB −3.8%, CAG −3.7%. That price is `d["price"]` → mktcap
  → every value yield → composite rank.
- **`grade_us_board.py`** prices from this same panel
  (`tests/test_us_board_ledger_continuity.py` §1), so the merge defect reached grading.
- **`build_impulse`** — the dead column is NaN at the tip and the engine pairs panels
  positionally at `iloc[-1]`, so the name was dropped from scoring outright:
  **1478 → 1487** scored names. At this vintage all 9 score NEUTRAL/FADING and the
  capped display lanes are unchanged — a coverage hole, not a visible lane change today.
- **`build_chart_data`** — the most user-visible: **POOL and CPB rendered through
  2026-06-18**, 43 days short, and VIAV/SANM/SMTC through 07-08. Separately,
  BLKB/CNXC/COTY/GT/FLEX rendered as **36–51 bar stubs** because the live column starts
  on the migration date.

## §2. What shipped

`lib/closes_panel.py` — one shared merge, freshest column per ticker; tier order now
only breaks ties, so every non-migrant is byte-identical to before. Column **coverage
is invariant** (1540 in, 1540 out), so no admission lane loses its price source.

The naive repair (take the freshest column whole) traded one defect for another: the
new tier's column carries only 26–51 observations, so `vol`/`beta`
(`min_price_history_d` = 150) go NaN — all 9 rescued names would have lost those legs,
and VIAV's composite with them. So the history join is **measurement-gated**: a donor
column restores pre-migration history only where it is proven **bit-identical** to the
live column on their overlapping sessions (≥5 sessions, max relative difference ≤1e-6).
Columns equal on every shared session cannot introduce a discontinuity; a genuine
adjustment-basis difference fails the test and is never spliced (the #2120 seam class
the sibling adjudication forbids). At this vintage 8 of 9 stitch; **CPB alone fails**
(its two lanes differ by a constant 1.69%, a dividend-adjustment gap) and keeps the
whole live column — correct current price, shorter history, no invented rebase.
Verified no seam was introduced: every large 1-day move in a stitched series already
existed in the donor or live column alone, and junction-day moves are ordinary
(−1.4% to +5.0%).

`engine/equity_factors.py` — the freshness **gate** for feeds that are genuinely dead
(no live duplicate anywhere). `px.ffill().iloc[-1]` no longer resurrects them: stale
names are dropped from price-derived factors (mktcap, value yields, leadership) while
their fundamentals-only legs still publish — demote, never delete (R1). The trailing
leadership return is gated for the same reason and one step worse: both endpoints ffill
to the same close, fabricating an exact **0.0%** that would then be averaged into the
quintile spreads. Threshold is the canonical `engine.name_score_grader._MAX_BAR_LAG_DAYS`
(7 calendar days), **imported not restated**, self-relative to the panel's own tip.
An R2-style circuit breaker disarms the gate above 20% stale with a loud `::warning`
(a universe-wide freeze is a collector outage; blanking the page would itself be
fail-dark, CSP-R1), and every ambiguous case fails open. Live run: 21/1515 gated.

Routed to the shared merge: `equity_factors._closes` (and therefore `residual_alpha`
and the US board's grading panel), `build_impulse`, `build_pick_lab`,
`build_dispersion_regime`, `manager_quality`, `manager_trades`, `build_chart_data`.
All disclosure is line-start `::warning` via bare `print(..., flush=True)` — never a
logger call (repo annotation law).

## §3. Rulings

- **R1 (freshness beats tier order; ties keep tier order).** Tier priority is a
  NAMING/priority convention, not evidence about which price series is current. For the
  PRICE column, the freshest wins. Ties are unchanged, so this is a strict refinement.
- **R2 (join only what is proven identical).** History may be restored across tiers
  ONLY on a measured bit-identical overlap. "Probably the same series" is not a basis
  argument; a constant-ratio difference is exactly the seam defect. Where the test
  fails, take the whole live column and accept the shorter history — never rebase.
- **R3 (a dead feed carries no price authority, but keeps its row).** Demote, disclose,
  never delete — the R1 shape from the sibling adjudication, applied at the reader.
- **R4 (studies keep the archive intact).** Survivorship-aware consumers must NOT be
  gated; a departed name's frozen column is the data they exist to read (§4).

## §4. Left alone, per reader — with the reason

**(a) Self-clean at the tip.** A frozen column is NaN at the panel tip (verified: the
collector's `combine_first` carries the column forward, so post-freeze rows are NaN, not
repeated values). Any reader that takes `.iloc[-1]` and lets NaN drop out is already
honest. `engine/impulse.py`, `engine/dispersion.py`, `engine/momentum_display.py`,
`engine/ignition_radar.py`, `engine/ai_desk.py`, `engine/sp500_heatmap.py`,
`engine/special_situations.py`, `engine/special_sits_intel.py`,
`engine/breadth_split.py`, `engine/risk_radar_market_catalysts.py`. A sweep for the
resurrection patterns (`ffill`, per-column `dropna().iloc[-1]`) across every reader found
`equity_factors` to be the **only** module that resurrects a per-name column — that is
why the gate lives there and nowhere else. Several of these read `data/breadth/` alone,
so they have no duplicate-column exposure at all.

**`scripts/live_breadth_poller.py` / `engine/live_breadth.py`** — self-clean *by design*
and documented as such: members absent from the snapshot are excluded from denominators,
so a half-reported tier reports honest counts. A frozen column yields `prev_close = None`
and the name leaves both numerator and denominator. No change.

**(b) Survivorship-aware studies — the frozen column is the point.** Gating these would
delete exactly the history they exist to measure (R4, and the sibling's R4 "union-forever
is a FEATURE"): `scripts/backtest_strategies.py`, `scripts/backtest_special_situations.py`,
`scripts/backtest_event_priors.py`, `scripts/calibrate_bottom_radar.py`,
`scripts/exit_policy_study.py`, `scripts/replay_standout_pipeline.py`,
`scripts/prophet_postmortem.py`, `engine/prophet_miss_audit.py`,
`scripts/mature_shadow_book.py`, `scripts/mature_bottom_sensors_shadow.py`,
`scripts/census_rebalance_days.py`, `research/prophet_us_audit/*`. Their PIT/replay
semantics also mean a freshest-wins merge could change a historical cross-section, which
is a reason to leave them alone rather than a reason to route them.

**(c) Named in the brief but NOT readers of this cache** — re-measured, the brief was
wrong (its line numbers were from 2026-08-03 and had drifted):
`scripts/build_site.py:1129,1270,3158` reads `data/<grp>/breadth.parquet`, the aggregate
breadth series, not the wide close cache; `scripts/build_sector_map.py:498` and
`scripts/build_oracle_panel.py:138` read `constituents.parquet`;
`scripts/residual_alpha_fetch.py:34` reads `constituents.parquet` (the alpha panel's
prices come via `equity_factors._closes`, which IS fixed).
`scripts/fetch_basket_extras.py` reads a single group per basket with no cross-tier
merge. `engine/trajectory.py` documents that it deliberately does NOT fall back to this
cache. No change to any of these.

## §5. Accepted residuals

- **CPB keeps a 36-bar history** in the chart and loses its `low_vol` leg, because its
  two tier columns are on different adjustment bases and R2 forbids the splice. This is
  a correct current price with thin history, replacing a 43-day-stale price with full
  history — the honest trade. It self-heals as the smallcap column accrues.
  A follow-up worth chipping: `build_chart_data`'s ladder tries the yahoo store only
  AFTER the caches, so a short cache column wins over a long fresh yahoo series
  (`data/yahoo/CPB.parquet` runs to 2026-08-04). Reordering that ladder is a separate
  change with its own provenance implications and is NOT made here.
- **The 32 genuinely dead feeds are unchanged in kind** — they have no live duplicate
  anywhere, so this PR only stops them impersonating live prices. Reviving the symbols
  is the collector-side work already chipped by the sibling adjudication §4 (2)
  (retired-symbol renames per the #4622 KEY-MIGRATION protocol).
- **Self-relative blindness to a TOTAL freeze** is unchanged and deliberate: every gate
  here measures against the panel's own tip, so a whole-collector outage is invisible to
  it. `build_stock_library`'s wall-clock disclosure remains the backstop (sibling R1).
