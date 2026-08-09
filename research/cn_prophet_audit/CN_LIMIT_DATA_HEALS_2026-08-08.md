# CN LIMIT-MOVE — data-plane heals: limit_events history hole + zt_pool date semantics

**Program:** CN LIMIT-MOVE ALPHA, Wave 1 (L0 data lane). **Upstream:** the two defects
`research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.md` flagged and did not fix
(its DECISION SUMMARY §13, and the `china_zt_pool` cross-check basis behind its §2).

**Tier: display / audit.** These are STORES and their emitters. Nothing here ranks, sizes,
gates or promotes anything, and no number below is a signal. Two data defects were measured,
mechanised, fixed at the producer, and healed in the committed stores; a third (the 涨停板
vendor's unpersisted fields) is reconnaissance only — nothing new is collected by this PR.

---

## DECISION SUMMARY

1. **`limit_events.parquet` had a per-NAME scan hole, and it was ~9× larger than v0 could
   see.** v0 reported 34 names missing pre-2026-07 history, 14 of them absent entirely. The
   true figure was **314 names, 264 of them with no row whatsoever** — v0's cross-check
   intersects its panel with the tape's ticker set (`shared = panel ∩ ev`), so a name absent
   from the tape *entirely* was structurally invisible to it. Its 34/14 counted only names
   inside the intersection.
2. **Mechanism: the store grew, the history did not.** `limit_events` is built ONCE by
   `scripts/backfill_china_limit_tape.py` (last full run 2026-07-08) and thereafter only
   appended to over a ~20-session window by `scripts/build_china_microstructure.py`. The raw
   store went **1,592 → 1,842 names on 2026-08-05** (`git ls-tree` at both revisions). Those
   250 newcomers could only ever receive a 20-day tail — and nothing at all when they had no
   limit event inside it. 249 of the 314 holed names are exactly those newcomers.
3. **The `backfill` flag cannot express this and never could.** `aggregate_daily` stamps
   `backfill = True` on every row it produces, nightly rows included (`engine/china_micro
   structure.py`), and it is a per-MARKET-DAY column on a per-NAME defect. Reading `True`
   for all 3,751 market-days was not a lie about coverage; it was a column answering a
   different question.
4. **Healed by re-running the emitter's own one-shot backfill over the current universe** —
   not a reimplementation, and not a patch of the parquet. All four of that script's sanity
   gates pass. **Events 60,428 → 71,463 rows, 1,578 → 1,782 tickers; names lacking
   pre-2026-07 coverage 314 → 74.**
5. **The residual 74 is honest, not a smaller hole.** After a full-history re-detection, 60
   names have ZERO detectable limit events (41 STAR, 15 ChiNext, 4 main — the 20%-band
   cohort v0 measured at a 0.33% STAR limit-up rate) and 14 have a genuinely recent first
   event. The one main-board name among the old late-starters, `600536.SS`, moved from a
   2026-07 first event to **2011-11-03** — that one was a real hole and is now closed.
6. **`china_zt_pool.pool.parquet` was stamping the RUN date, not the trade date.** 11 of its
   47 dates were not CN trading sessions (2026-07-04/05, 07-11/12, 07-18/19, 07-25/26,
   08-01/02, 08-08 — every weekend since daily collection began), 818 of 3,920 rows.
7. **Each one was a byte-identical re-serve of the session before it.** Compared across all
   seven payload columns: 07-04 ≡ 07-05 ≡ 07-03, 07-11 ≡ 07-12 ≡ 07-10, …, 08-08 ≡ 08-07.
   Eastmoney's `getTopicZTPool` does not 404 on a non-session date — asked for any date at or
   after the last published session it **CLAMPS** and serves that session's pool. The
   collector walked back over raw calendar days, stopped at the first non-empty response, and
   stamped the date it had ASKED for. **47 "dates" were 36 sessions.**
8. **Healed: 3,920 → 3,102 rows, 47 → 36 dates, non-session dates 11 → 0**, zero duplicate
   `(date, ticker)`. Every surviving date is a session in the store's own calendar.
9. **`date` is the trade date; `asof` is the UTC day the row was scraped.** They are not the
   same clock and were never meant to be — `asof` is provenance. A stored session whose
   `asof` is far past its `date` was recovered late, not observed late (the 06-15…06-26 rows
   all carry `asof = 2026-07-06`: one range backfill).
10. **The vendor exposes 16 fields; we persist 6.** The single most valuable unpersisted one
    is **首次封板时间** (first seal time, HHMMSS) — the 打板 timing number. Second is
    **涨停统计** (`days/ct`, e.g. `5/4`), which is a genuinely different quantity from
    `连板数`: on 2026-08-07 通宇通讯 read `连板数=2` with `涨停统计=5/4` — 4 boards in 5
    sessions, only 2 of them consecutive. **涨停原因/题材 is NOT on this endpoint** and needs a
    different source. Ranked proposal in §REPORT C. Nothing is collected by this PR.

---

## HEAL A — `data/china_microstructure/limit_events.parquet`

### What was broken

| | |
|---|---|
| Store | `data/china_microstructure/limit_events.parquet` (+ `limit_tape.parquet`) |
| Producers | one-shot `scripts/backfill_china_limit_tape.py`; nightly `scripts/build_china_microstructure.py::build_increment` (in `asia-close.yml`, via `config/dag.yml` `cl_flowconf`) |
| Detector | `engine.china_microstructure._detect_limit_events` — imported by both, never reimplemented here |

`build_increment` computes `lookback_start = scan_date − 20 days` and passes it as
`start_date` for **every** ticker. That is correct for a name whose history is already in the
store and silently wrong for one whose is not. Nothing in either producer asks whether a
ticker has ever been scanned.

### The measurement (all figures from the committed stores at `830ff9321f4`)

| Lens | Before | After |
|---|---|---|
| raw store names | 1,842 | 1,842 |
| names with ≥1 event row | 1,578 | **1,782** |
| names with NO event row | **264** | **60** |
| names whose first event is ≥ 2026-07-01 | **50** | **14** |
| names lacking pre-2026-07 coverage | **314** | **74** |
| event rows | 60,428 | **71,463** |
| tape rows | 3,751 | 3,768 |
| v0's lens (`delta > 5` on strict `sealed_up`, intersection only) | 34 / 14 absent | 0 by construction — the gap names' history is now present |

Attribution of the 314: **249** are among the 250 files added to `data/china_stocks_raw`
after 2026-07-10 (`git ls-tree` at `73ed5207ba4` = 1,592 files vs 1,842 now, all added
2026-08-05); **65** pre-date the growth, of which 53 had no `sealed_up` at all and 12 had a
first event in 2026-07.

### What changed in the data

The tape was rebuilt on the same run, so its **universe grew with it**: `universe_n` rises by
a median of 186 names per market-day (max 251), and the aggregate counts move accordingly —
`sealed_up_close` 26,970 → 31,906, `limit_down_count` 11,125 → 13,315, 2015 `limit_up_count`
7,016 → 8,398. **This is a denominator change, not a discovery.** Every breadth percentage in
the tape is a percentage of the store's curated universe, which is now 1,842 names instead of
1,592; v0's BINDING CAVEAT (curated universe ≠ the ~5,400-name market) is unchanged and still
governs. The 17 new tape rows are market-days on which only a newcomer had an event.

Nightly-appended rows for dates after 2026-07-08 were recomputed from raw, so the rebuild
also retires the module's documented *lianban undercount* for those dates (a streak that
began before the 20-session window used to be reported as `lianban_count = 1`).

### The durable fix — `scripts/build_china_microstructure.py`

The smaller of the two options in the brief, and the one that closes rather than documents:
**the emitter learns to detect store-newcomers and scan their FULL history.** Making
`backfill` per-name honest would have changed a §5-frozen tape column to describe a hole
instead of closing it.

- `_known_event_tickers()` reads the events store's ticker set. A ticker absent from it has
  never been scanned; it is detected from `LIMIT_TAPE_START_DATE` instead of the window.
- The result is **split**: the window part feeds `aggregate_daily` exactly as before, the
  pre-window part goes to the events store ONLY. Re-aggregating 15 years of tape nightly is
  off-budget, and the tape's historical rows must keep the universe that produced them
  (`universe_n`). The annotation says so and names the remedy.
- An EMPTY known-set means the store is missing or unreadable — a cold start, which belongs
  to the one-shot backfill. It is explicitly NOT read as "1,842 newcomers".
- `NEWCOMER_SCAN_CAP = 250` bounds the per-run cost (measured: ~0.12 s/ticker full-history,
  so ~30 s worst case, and only ever right after a universe expansion). Names over the cap
  are counted and picked up by later runs.
- The hole is **disclosed, never silent**: a `::warning title=cn-limit-newcomer-backfill`
  annotation (bare `print(..., flush=True)` — a logger's prefixing format would stop GitHub
  parsing it), a `data_gaps` entry, and a queryable per-name `newcomer_backfill` block in
  `site/chinastatedata/microstructure.json`.

**Residual cost, stated:** the 60 names with no detectable event are re-scanned on every
nightly run (~7 s) because "has no rows" is the only newcomer signal that needs no new store.
Accepted rather than adding a coverage sidecar; if that cohort ever grows past a few hundred,
a per-name coverage store is the next move.

---

## HEAL B — `data/china_zt_pool/pool.parquet`

### Where the scraper lives and when it runs

**In this repo.** `collectors/china_zt_pool.py`, invoked from
`scripts/build_china_library.py` (the additive A-share CONTEXT drip block) which runs inside
`.github/workflows/asia-close.yml` — a 7-slot daily cron (06:00 / 06:40 / 07:20 / 08:30 /
09:30 / 10:30 / 11:15 UTC) whose `gate` job keeps one real run per day. It fires **every**
calendar day, weekends included, which is what produced the Saturday and Sunday rows. No
launchd job and no sister repo is involved.

### What `date` and `asof` actually mean

- **`date`** — now the **TRADE date** of the session the pool describes. It used to be the
  date the collector ASKED the vendor for, which on a non-session day is the run date.
- **`asof`** — the **UTC day the row was scraped**. Provenance only. It legitimately differs
  from `date` (a range backfill stamps one `asof` across many sessions: all 9 sessions of
  2026-06-15…06-26 carry `asof = 2026-07-06`).

### The mechanism

`ak.stock_zt_pool_em(date=…)` → `https://push2ex.eastmoney.com/getTopicZTPool`. The response
carries **no date field**. For a date at or after the last published session the endpoint
serves that session's pool rather than an empty frame; for a *past* holiday it returns empty
(2026-06-19, 端午, is correctly absent from the range backfill). So the old walk-back —
newest calendar day first, stop at the first non-empty response, stamp the requested date —
mislabels every weekend and every future-dated request, and only ever labels correctly by
coincidence on a weekday.

A second, quieter defect in the same walk-back: it stopped at the newest POPULATED date, and
if that date was already stored it returned 0 without looking further. Whenever the vendor was
late on the session day itself, that session was skipped **permanently**. Three such gaps are
in the store: **2026-06-29, 2026-07-09, 2026-07-22** (all real sessions in the tape calendar).

### The fix — `collectors/china_zt_pool.py`

1. **Session calendar from our own store.** `session_calendar()` unions the bar dates of 24
   deterministically strided names in `data/china_stocks_raw` — a date is a session iff at
   least one of them traded. No external calendar; ~24 small parquet reads; holidays included.
   Without the store it degrades to a weekday filter and logs that holidays can still slip.
2. **Resolve BEFORE fetching.** `candidate_sessions()` returns only real sessions inside the
   walk-back window, newest first, so a non-session date is never asked for and never stamped.
3. **Payload fingerprint.** If the pool returned for a session is identical (over ticker /
   连板数 / 封板资金 / 炸板次数 / 换手率) to a pool already stored under a DIFFERENT date, the
   vendor has clamped and the session is not stamped. Two consecutive sessions producing an
   identical pool is not a market event.
4. **Per-date REPLACE.** `_drip.append_snapshot(..., replace_dates=True)` — opt-in, default
   unchanged. The pool's per-date slice is a COMPLETE SET, so a re-collect must replace it
   wholesale; keep-last on `(date, ticker)` can correct a row but can never retire one that
   left the pool. Other dates are untouched, so the tape stays append-only ACROSS sessions.
   The per-name drips (margin_detail, LHB, …), whose rows arrive a few names at a time, keep
   the merge semantics — replacing their date would delete rows.
5. **The newest session is always re-collected** (older ones only when missing), so a partial
   intraday scrape is corrected by a later run the same day. Bounded by
   `MAX_SESSIONS_PER_RUN = 4`, and never more vendor calls than the old walk-back already made.
6. **Anchor moved to the UTC day**, the same clock `asof` uses. China is UTC+8 so its trade
   date is never behind UTC's; the old `date.today()` (runner-local, PDT) could be a day behind.

### The one-time store heal — `scripts/heal_cn_zt_pool_dates.py`

Same shape as the house's existing `scripts/heal_cn_beijing_tickers.py`: `--check` mode,
idempotent, invariant-guarded, aborts rather than guesses.

| | Before | After |
|---|---|---|
| rows | 3,920 | **3,102** |
| dates | 47 | **36** |
| non-session dates | **11** | **0** |
| weekend dates | 11 | 0 |
| duplicate `(date, ticker)` | 0 | 0 |
| sessions still missing (2026-06-15…08-07) | 3 | 3 |

**The mapping applied** (each source was byte-identical to its target across all seven payload
columns, so the merge is a pure drop of re-serves — a differing payload aborts the heal):

```
2026-07-04 → 2026-07-03    2026-07-18 → 2026-07-17    2026-08-01 → 2026-07-31
2026-07-05 → 2026-07-03    2026-07-19 → 2026-07-17    2026-08-02 → 2026-07-31
2026-07-11 → 2026-07-10    2026-07-25 → 2026-07-24    2026-08-08 → 2026-08-07
2026-07-12 → 2026-07-10    2026-07-26 → 2026-07-24
```

**Independent confirmation:** one live fetch of `stock_zt_pool_em(date='20260807')` returned
**74 rows** — exactly the row count the healed store holds for 2026-08-07, the count that was
also sitting under the "2026-08-08" label.

---

## REPORT C — vendor field inventory (reconnaissance; nothing collected here)

Source of truth: `akshare.stock_zt_pool_em` → `push2ex.eastmoney.com/getTopicZTPool`,
confirmed by one live fetch on 2026-08-08 (16 columns, 74 rows for session 2026-08-07).
**We persist 6 of the 16.** No new dependency is needed for any row marked *same call*.

### Available NOW from the call we already make

| Rank | Field | Cost | Why it should exist, for onset / continuation |
|---|---|---|---|
| **1** | **首次封板时间** `HHMMSS` | same call | The single most-watched 打板 timing number. A 09:25 seal (call auction) is a different animal from a 14:47 seal; time-to-seal is the natural onset-strength ordinate and the only intraday quantity in the whole feed. Sample 2026-08-07: `092500`, `092500`, `092502`. |
| **2** | **涨停统计** `days/ct` | same call | The 几天几板 ladder, and **genuinely different from `连板数`** — 通宇通讯 on 2026-08-07 read `连板数=2`, `涨停统计=5/4` (4 boards in 5 sessions). Non-consecutive ladders are a distinct 打板 regime that our store currently cannot express at all. Direct answer to the brief's 连板天数-vs-几天几板 question. |
| **3** | **最后封板时间** `HHMMSS` | same call | With `炸板次数` (already persisted) this completes the seal-stability profile: first seal → n breaks → final seal. A name that sealed at 09:25, broke twice and re-sealed at 14:50 is a *failed* strong board wearing a strong board's closing print. |
| **4** | **流通市值** (free float) | same call | Unlocks two ratios we cannot currently compute: **封成比 proxy** = 封板资金 / 流通市值 (how much of the float the seal wall actually represents — the number 龙虎 traders read, not the raw 亿), and **free-float turnover** = 成交额 / 流通市值. Also closes v0's printed NULL f2 (turnover ratio), which failed for exactly this reason: "no CN store carries per-date shares outstanding or free float". |
| 5 | **成交额** | same call | Numerator of the above; also a plain liquidity control. |
| 6 | 总市值 | same call | Weak on its own; float is the one that matters for 打板. |
| 7 | 最新价 / 涨跌幅 | same call | Redundant with `china_stocks_raw`; useful only as a cross-check that the pool and our OHLCV agree on the session. |

### Needs a DIFFERENT endpoint (same vendor family, same akshare package)

| Field | Endpoint | Note |
|---|---|---|
| 炸板 detail (the failed-seal population itself) | `stock_zt_pool_zbgc_em` → `getTopicZBPool` | Carries 首次封板时间, 炸板次数, 涨停价, 振幅, 涨速. Our current store only counts a survivor's breaks; **the names that broke and never re-sealed are absent entirely** — the natural control group for any onset study is missing. Highest-value *new* endpoint. |
| 昨日封板时间 / 昨日连板数 | `stock_zt_pool_previous_em` → `getYesterdayZTPool` | The next-session follow-through population, pre-joined by the vendor. |
| 跌停 pool (封单资金, 最后封板时间, 板上成交额, 开板次数, 连续跌停) | `stock_zt_pool_dtgc_em` → `getTopicDTPool` | The down-limit mirror. `板上成交额` (turnover transacted while pinned) has no up-side equivalent in the feed. |
| 强势股池 | `stock_zt_pool_strong_em` → `getTopicQSPool` | Near-limit / 涨速 names. Adjacent, lower value. |

### NOT available anywhere in this vendor family

**涨停原因 / 题材 (limit reason / theme tags)** — the field the program's theme-relay lane
wants most — is **not on any `getTopic*Pool` endpoint**, and `akshare` carries no 涨停原因 /
涨停揭秘 function at all (grepped: zero hits for 涨停原因, 涨停揭秘, 题材 across the package).
It is a 同花顺 (THS) product surface. The nearest thing this repo already holds is
`data/baskets_china_ths` concept membership plus `engine/china_narrative_tags.py` — a
*mapping*, not the vendor's per-day per-name reason string. Any theme-relay build must treat
"limit reason" as an unsourced field today and either source THS or reconstruct it from
concept membership + the sector field we already persist. **Do not assume it arrives with the
pool.**

**Historical depth beyond our 47 dates** is available: `stock_zt_pool_em` is per-date and the
existing `backfill(start, end)` path already proved it (9 sessions of 2026-06). How far back
the vendor serves is **UNTESTED** — see below.

---

## UNTESTED / ORE

Stated, not resolved. None of this blocks the heals above.

1. **How far back does `getTopicZTPool` serve?** One range backfill reached 2026-06-15. The
   endpoint is per-date, so multi-year 打板 history may simply be fetchable — which would turn
   the program's best collector from a 36-session tape into a real sample. Nobody has asked
   it. Probe cost is one request per date; the operator lever already exists:
   `python -m collectors.china_zt_pool --backfill 2024-01-01 2026-06-14`.
2. **The 3 known session gaps** (2026-06-29, 2026-07-09, 2026-07-22) are outside the fixed
   collector's 10-day walk-back and will not self-heal. `--backfill 2026-06-27 2026-07-23`
   recovers them if the vendor still serves those dates. Not run here: it is a network write
   to a committed store, and it belongs with the depth probe above, in one deliberate pass.
3. **Other CN drip stores may carry the same run-date defect and were NOT audited.** Every
   store in `collectors/_drip.py`'s family keys on a collector-chosen date:
   `china_lhb/{detail,events}.parquet`, `china_block_trades/detail.parquet`,
   `china_margin_detail/detail.parquet`, `china_comment`, `china_st`. The zt_pool defect came
   from a vendor that clamps rather than 404s; any sibling reading a "today" endpoint on a
   weekend is a candidate. A one-line check — *is every stored date a session in
   `limit_tape`?* — would sweep all of them. Explicitly out of this lane's scope.
4. **The 60 zero-event names are asserted, not independently corroborated.** They are zero
   under `_detect_limit_events` over their full raw history, and their board mix (41 STAR / 15
   ChiNext / 4 main) matches v0's measured STAR limit-up rate of 0.33%. A cross-check against
   `china_zt_pool` would be the outside evidence — but the pool holds 36 sessions and these
   names' events, if any, are years old. Not resolvable with the stores we hold.
5. **`universe_n` describes a 2026 curation applied to 15 years of history.** The tape's
   breadth denominators now include 250 names that entered the store on 2026-08-05, selected
   by whatever added them. This is the same survivorship property v0 documented, one notch
   larger. It is disclosed, not corrected.
6. **The tape/events consistency window.** Between one-shot backfill runs, a newcomer's
   history lives in `limit_events` while the tape's historical rows do not count it. That is
   deliberate (§HEAL A) and annotated, but a consumer joining the two across a pre-newcomer
   date will see events the aggregate does not. No current consumer does; worth a guard if one
   ever does.
7. **Pre-existing unrelated red:** `tests/test_earnings_w4_feed.py::TestBoardRowSchema::
   test_the_contract_registers_both_keys_as_may_be_absent` fails on this branch and on its
   base — `us_standouts.json` `schema_version` is `1.8.0`, the test pins `1.7.0`. Nothing in
   this lane touches `scripts/export_signal_contracts.py`. Flagged, not fixed.

---

## What ran

Fresh, on this branch, `TZ=UTC`:

- `python3 scripts/backfill_china_limit_tape.py` — all 4 sanity gates PASS, 71,463 events /
  3,768 tape rows, ~3 min.
- `python3 scripts/heal_cn_zt_pool_dates.py` then `--check` → `clean` (idempotent).
- `python3 -m pytest tests/test_china_zt_pool_dates.py tests/test_china_limit_events_coverage.py
  tests/test_drip_append_only.py tests/test_china_microstructure.py tests/test_slf052_ztpool.py
  tests/test_heal_cn_beijing_tickers.py tests/test_china_analyst_ticker.py
  tests/test_pick_lab_cn_runner.py tests/test_gh_annotation_line_start.py` → **204 passed**.
- The wider store-adjacent sweep (`test_china_alpha_w3c_infra`, `test_china_cycle_phase`,
  `test_china_participation`, `test_dead_name_delisting`, `test_dead_names`,
  `test_earnings_sweep_entrypoint`, `test_earnings_w4_feed`, `test_earnings_w5`,
  `test_foresight_ledger_lane_gates`, `test_ticker_pages`) → 472 passed, 1 skipped, 1 failed
  (the pre-existing schema_version red in ORE §7).
- **Both new suites were mutation-checked.** Reverting the session-calendar resolution, the
  per-date replace and the clamp fingerprint reds 6 of 12 zt_pool tests; reverting the
  newcomer detection reds 3 of 6 coverage tests. The tests can see the defects they pin.
- `python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0
  --pack-count 4 --validate-only` → 171 jobs validated after registering the new suites.
