# US Context Vector — point-in-time candidate store (+ its forward grades)

Two sibling stores, one record:

- `candidates/YYYY-MM.parquet` — one row per analyzed US universe name per night,
  **including names that never passed the raw signal gate**, WITH that night's itemized
  `us_prophet_v1` priority-score legs. This is what **REMEMBERS the score**. Producer:
  `engine/us_context_vector.py`, stamped from `scripts/build_stock_library.py` at the end
  of its nightly run. Roadmap:
  `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §2.
- `grades/YYYY-MM.parquet` — what those names then **did**: every stamped row graded at
  H=10 and H=21 sessions, excess vs SPY. Producer: `engine/us_prophet_grades.py`, run by
  `scripts/grade_us_prophet_candidates.py --nightly`. Masterplan:
  `research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §W7 (operator order
  2026-08-05).

Only the join of the two can say whether a score was right — that join is the miss-audit's
`priority_score_scorecard` block (`data/prophet_miss_audit/latest.json`).

## Read them with the store readers, never by globbing

```python
from engine import us_context_vector as ucv
from engine import us_prophet_grades as upg

frame = ucv.load_candidates()                      # whole store, one frame
q3    = ucv.load_candidates(months=["2026-07", "2026-08"])
ids   = ucv.load_candidates(columns=["stamp_date", "ticker"])   # parquet-level projection

grades = upg.load_grades()                         # every graded (row, horizon)
joined = upg.load_graded_frame(score_columns=["lane", "sector"])  # grades + the score
```

The monthly parts are a **storage** detail. `load_candidates` concatenates them in
chronological order and unifies columns across parts, returning exactly what a
single accreting file would have. Nothing outside the producer module should know
parts exist.

## Two coverage tiers, one store (roadmap §4.5, ratified 2026-08-05)

Every row carries `tier`:

| `tier` | what it is | who writes it | admission |
|---|---|---|---|
| `curated` | the graded population (S&P 1500 + Russell + curated extras) | `scripts/build_stock_library.py`, in the **engine** job | unchanged — this set IS the board's population |
| `scan` | liquidity-floored coverage over `data/massive_stock_day` | `scripts/run_us_scan_tier.py`, in the post-engine **us_scan_tier** job | **never admitted** — seen and counted only |

"See everything, admit selectively." The scan tier exists so an off-index runner
is at minimum SEEN and counted missed (the FNV/FSM/EXK/AG/SBSW receipts: those
five were in no frame the engine looked at).

The two writers are **ordered** (engine first; the scan job `needs: engine`) and
their ticker sets are **disjoint by construction** — the scan resolver removes
curated names before stamping. Keep-first on
`(stamp_date, ticker, board_definition)` is the second fence: `tier` is
deliberately NOT in the dedupe key, so a name that somehow reached both passes
survives exactly once, as its **curated** row — the one carrying board legs, lane
and near-miss. Had `tier` joined the key, both rows would be kept and every
cohort count would double-count that name.

Floor (displayed, built from the constants so it cannot drift from what runs):
still trading AND ≥200 bars AND close ≥ $3 AND *median* close×volume over 20
sessions ≥ $5M. Measured 2026-07-02: 20,476 in store → 12,434 still trading →
10,422 with ≥200 bars → 3,980 pass the floor → **2,252 scan tier** after removing
the 1,728 already curated. Coverage 1,838 → 4,090 names seen.

## Zero authority

Nothing reads either store for **scoring**. They change no lane, no rank, no score and no
gate, and the candidates store **originates nothing** — every column is read off a producer
that already ran that night (glass-box law; A7). Any column reaches decision authority only
through the roadmap §3 bounded-authority ladder, one axis at a time, each with its own
preregistration.

The candidates store now has readers: the forward grader (`engine/us_prophet_grades.py`,
identity columns only) and, through it, the miss-audit's scorecard. Both are read-only ops
telemetry with no threshold and no alarm; `tests/test_us_prophet_grades.py` greps every
`engine`/`scripts`/`app`/`admin`/`lib`/`collectors` module to pin that nothing else touches
the grade store at all.

## Integrity rules

| Rule | Mechanism |
|---|---|
| Nightly is the sole advancer | `ledger_lane.nightly_advance_enabled()` (`COLLECT_LANE=nightly`, `US_LANE` legacy alias) is the **first statement** of `append_candidates` — an intraday or render lane returns 0 without opening a file |
| PIT discipline | keep-first on `(stamp_date, ticker, board_definition)`; a rerun can never rewrite a night already stamped |
| No retroactive backfill | only same-night values are stamped; a column added later is null for prior nights and self-heals **forward only** |
| Schema union on append | a new column never discards old columns; a retired column is preserved for the nights that had it — across parts as well as within one |
| Monthly parts | a stamp opens and rewrites **only** its own `YYYY-MM` part; every earlier part is byte-identical forever after its month closes (pinned by `TestMonthlyPartitionedLayout`) |
| Fail-soft | every failure path logs and returns 0; research telemetry never breaks the nightly build |

## `grades/` — the forward record (§W7)

`grades/YYYY-MM/YYYY-MM-DD.parquet`. One row per **(candidate row, horizon)** across the
**H=10 / 21 / 42 / 63** session ladder: `stamp_date`, `ticker`, `board_definition`,
`horizon`, `graded_asof`, `entry_price`, `fill_date`, `mark_date`, `fwd_ret`, `bench`,
`bench_ret`, `excess_spy`, `fwd_mfe`, `fwd_mdd`, plus two conditioning columns:

| Column | Values | Why |
|---|---|---|
| `universe_tier` | `curated` · `scan` · null | curated names are board-admissible; scan names are seen and stamped over the widened universe and **never admitted** (roadmap §4.5). Two populations, **never pooled** — including the median a "hit" is measured against |
| `signal_class` (+ `signal_label`) | `basing` · `momentum` · `other` | a basing pick and a momentum pick are different bets. Operator ruling 2026-08-05: *"they take time to base… but our board only measures for 10 day results??"* Mapped from the board's **existing** cycle vocabulary (`engine/cycles.py::STATE_DISPLAY`) — nothing new is stamped. An unmapped label classes `other` with the label **preserved** |

Both columns are **resolved from the candidates store by name and then VALIDATED by value**;
a name match alone is never trusted. Neither has landed in that store yet (a sibling lane
owns writing them), so today every row carries a null cohort and `signal_class='other'` with
a null label — and the run prints a `::warning` naming exactly what is missing. The scorecard
reports that state as `unsplit` / unavailable rather than calling it `curated`.

### The chartered-horizon prereg (fixed BEFORE any long-horizon data matured)

| class | headline horizon | supporting |
|---|---|---|
| `basing` | **H=63** | H=21 |
| `momentum` | **H=10** | H=21 |
| `other` | H=10 | H=21 |

Every class is graded and reported at **every** horizon in the ladder, so nothing is hidden.
This map only fixes which horizon is each class's *headline* read — because "grade each class
at the horizon that flatters it, chosen after seeing the results" is precisely the sin it
exists to make impossible. It ships in the nightly artifact
(`priority_score_scorecard.chartered_horizon`) so it can be audited later. **PROPOSED pending
commissioner adjudication.**

The existing **H=10 headline record is untouched** (era law). The class-conditional view
accrues beside it as measurement; any future redefinition of the headline is its own dated
operator adjudication, once the long-horizon data exists.

| Rule | Mechanism |
|---|---|
| Nightly is the sole advancer | `ledger_lane.nightly_advance_enabled()` is the **first statement** of `append_grades`; mutation-checked in `TestNightlyLaneGate` (both halves — off-lane writes nothing AND on-lane does write, so deleting the gate cannot leave the test green) |
| One-grader law | a graded `(stamp_date, ticker, board_definition, horizon)` is **frozen**; a re-run on the same night appends nothing |
| Ruler reused, not forked | every number comes from `engine.grading.forward_metrics` — the same next-bar fill and positional session horizons `grade_us_board` and `grade_prophet_doors` use, pinned mark-for-mark against the latter |
| Policy-free | fixed-horizon marks only: no stops, exits, hold rules or sizing. The row is measured as an origination+ranking observation, not as a trade |
| Maturity, never short marks | an unmatured horizon is **absent** from the run and graded on a later night; it is never scored 0 |
| Null is not zero | a missing SPY cache nulls `excess_spy` and prints a `::warning`; absolute marks still grade |
| Month-grouped **daily** parts, keyed by the run | see below |

### Why the parts are keyed by `graded_asof`, and why day grain

Two separate decisions:

**Keyed by the run, not the stamp.** Grading is a monotone forward process, so the run's own
as-of date means a nightly touches exactly one part and every earlier part is frozen. Stamp
keying would reopen the previous month's part nightly for ~3 weeks while its rows matured.

**Day grain inside a month directory, not one monthly file.** A parquet cannot be appended in
place, so a single monthly file is *rewritten* nightly and git stores a whole new blob each
time. That was tolerable at 1,579 names × 2 horizons. It is not once the H=42/63 ladder
doubles the rows and the scan tier multiplies the names by ~6.5. Measured on real-shaped
months (random-noise floats, so these are upper bounds):

| Scale | rows/month | month-end | **day parts (shipped)** | one monthly file |
|---|---|---|---|---|
| curated only (~1,579) | 132,636 | 8.65 MB | **0.10 GB/yr** | 1.14 GB/yr (11x) |
| with scan tier (~10.3k) | 865,200 | 47.7 MB | **0.57 GB/yr** | 6.30 GB/yr (11x) |

On disk after one year: ~104 MB (curated) / ~573 MB (with scan). A new file per run costs
exactly the store's own size — there is no rewrite churn at all — and it makes "every earlier
part is byte-identical forever" absolute rather than merely usual. `load_grades()` and the
`months=` filter are unchanged; parts remain a storage detail.

Each row still carries `stamp_date` and `mark_date`, so a study joins by stamp month
regardless of which part the row physically lives in.

## Measured facts (2026-08-04, this Mac Studio, 1,540-name universe)

- **Shape:** 1,540 rows x 150 columns for one `stamp_date`.
- **Assembly cost: 0.0675 s/name**, linear, after the insider-panel memo landed with
  this store (see below). The gate is judged on the HOST universe, not the local one:

  | universe | projected assembly |
  |---|---|
  | 1,540 names (this checkout — no russell closes cache) | **1.73 min** |
  | **2,932 names (host)** | **3.30 min** |

  Per-block, over 1,540 names — `context_frame` dominates, everything else is ~2.8 s:

  | block | cost | n |
  |---|---|---|
  | `context_frame` (11 dims) | ~104 s | 1,540 |
  | `event_features` | 1.95 s | 1,540 |
  | `eightk_recency` | 0.27 s | 659 |
  | `turnover_percentiles` | 0.17 s | 1,536 |
  | `relay_features` | 0.15 s | 300 |
  | `basket_membership` / `theme_state` / `foresight_stage_map` / `regime_block` | <0.02 s each | 36 / 47 / 27 / 5 |

  **Before the memo it was 0.302 s/name** — 8.3 min locally and ~14.7 min extrapolated
  to the host, over the 10-minute budget. `context_api._insider_dim` re-read all 81
  files in `data/sec_insider/panel/` for *every* ticker (~235k parquet reads a night)
  and was ~80% of the entire Context Snapshot cost. It now loads the panel once per
  process (`_load_insider_panel`, mirroring the file's own `_si_cache` idiom), narrowed
  to the 4 columns the aggregate consumes: **103 MB resident, 4.5x faster, values
  pinned byte-identical** against a transcription of the pre-cache implementation
  (`tests/test_context_api.py::test_insider_cache_is_byte_identical_to_the_uncached_reference`).

- **Growth:** 462 KB for the first night; 99 KB/night marginal measured on repeated
  nights. Real nights vary more than the repeat test, so the true marginal sits between
  those bounds — call it **~25-115 MB of total file after one year (252 sessions)**.

### Why monthly parts (the git-history math)

The store is git-tracked, and a nightly rewrites whatever file it touches — so git
stores a **whole new blob** each night, and parquet deltas poorly. With one accreting
file the cost is quadratic in nights: `S x N(N+1)/2` with `N = 252`, i.e.
**3.2-14.7 GB of history in year one.**

Monthly parts bound that to one month at a time: `12 x S x 21(21+1)/2`, i.e.
**0.27-1.28 GB** — an ~11.5x reduction, and a closed month never churns again. The
layout was chosen while the store had zero rows precisely so it would never need a
migration.

The CN sibling (`data/china_prophet_rank/candidates.parquet`) still has the
single-file shape and the original exposure; layout is a per-market storage idiom, so
that is the CN lane's call, not a divergence in the shared schema.

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

## `pool_*` — the display-tier candidate-pool lanes (operator commission 2026-08-11)

Nine columns, producer `engine/us_candidate_lanes.py`, stamped from the same
`build_stock_library` run that writes every other column here. They record the **lossless
four-lane partition of tonight's cascade-eligible pool** — CN parity with
`china_board_rank._partition`, in US vocabulary.

Why they are here rather than in a new store: this store already stamps exactly that
grain (one row per analyzed name per night, keyed `(stamp_date, ticker,
board_definition)`, carrying `prophet_score`, `selection_era` and the artifact `lane`),
its schema-union append gives a new column forward-only self-healing for free, and the
nightly already commits it. A sibling store would have duplicated the key, the lane gate,
keep-first and the monthly-parts layout for nine columns.

| Column | What it is |
|---|---|
| `pool_definition` | the partition rule that produced the row (`us_candidate_pool_v1`) |
| `pool_lane` | `featured` · `more_actionable` · `late_or_unfillable` · `forming` |
| `pool_lane_reasons` | `\|`-joined, **order preserved** — headline first. Not `_ids`, which sorts |
| `pool_headline_reason` | the first reason |
| `pool_rank` | position in the board's own pre-cap blend order over the eligible set |
| `pool_display_rank` | position within the row's lane |
| `pool_in_buy_lane` | whether the name also reached the published `buy[]` |
| `pool_admission_class` | `patience` / `confirmation` / null, read through `prophet_bridge` |
| `pool_open_plan` | the name already holds an open plan (open plans persist across nights) |

**Null off the pool, by construction.** Only tonight's cascade-eligible names are in the
partition — 144 of a ~1,540-name curated universe on the 2026-08-07 board — so ~91% of
rows carry nulls here. That is this store's disclosure idiom ("not measured for this name
tonight"), not a gap. Scan-tier rows are never in the pool: a scan name is never admitted.

**`prophet_score` stays null for the ~63 off-board eligibles**, and that is deliberate,
not a debt. `us_board_rank.score_rows` builds its `edge` leg from `alpha_percentiles`
over the pool it is handed, so scoring the off-board names as their own pool mints a
SECOND RULER, and scoring them together with `buy[]` moves every published row's
percentile and therefore the board ORDER. `pool_rank` is the comparable trajectory key
instead: it is the board's own pre-cap order, defined for every eligible name.

**`originated` is deliberately absent** (carried-columns law — never leave schema that
lies). This store is stamped by `build_stock_library`, which runs BEFORE `build_prophet`
in `daily.yml` and does not run at all under `render.yml`, so origination is unknowable
at stamp time and retroactive backfill is forbidden here. Origination is build_prophet's
fact and lives in its artifact and ledger; join on `(stamp_date, ticker)`. What IS
knowable — an already-open plan — is stamped as `pool_open_plan`.

**Zero authority, fenced by a file boundary.** `engine/us_candidate_lanes.py` imports
from `us_board_rank` / `prophet_bridge`; nothing on the admission path imports it, and
`tests/test_us_candidate_lanes.py::TestNoAuthorityLeak` pins that as a static token
sweep, an import-closure walk and a behavioural invariance check on
`prophet_bridge.select_candidates`.

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
- **`stamp_date`** is the US stamp column; the CN sibling uses `date`. **Adjudicated
  2026-08-04: `stamp_date` wins** — it is self-documenting where `date` is ambiguous
  next to the event dates it sits beside in a joined frame. US stays as-is; the CN-side
  rename is filed as its own task for the CN lane. See
  `research/CONTEXT_VECTOR_SCHEMA_CONTRACT.md` §3.1.
