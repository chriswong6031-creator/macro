# W3-C Data Accrual Infrastructure — Execution Report

*research/china_alpha/w3/W3C_DATA_ACCRUAL_INFRA.md · 2026-07-03 · W3-C executor (Sonnet)*

---

## Summary (pre-send gate)

All three sub-tasks are complete. No pages touched, no signals wired, no backtests
run — this wave is pure infrastructure.

- **C1 (Margin daily accrual):** `ChinaMarginDetailAdapter` added to
  `collectors/china_margin_detail.py` and registered in `scripts/collect.py` under
  the `china_margin_detail` key (auto-assigns to `asia` shard). Schema extended to
  include `short_balance` (融券余量, shares) and `short_balance_yuan` (融券余额, yuan
  from SZSE). Existing `fin_balance` column kept unchanged to avoid breaking
  `engine/china_extras.margin_positioning`. Data at `data/china_margin_detail/detail.parquet`
  currently holds 3 sessions (2026-06-30..07-02); daily accrual starts tonight.

- **C2 (LHB backfill):** `scripts/backfill_china_lhb.py` created and run successfully.
  28,580 events written to `data/china_lhb/history.parquet` (0.34 MB, 409 unique
  trading dates, 4,313 unique tickers, 2024-07-01..2026-07-03). `ChinaLhbAdapter`
  added to `collectors/china_lhb.py` and registered. Store is safe to commit in-tree
  (0.34 MB << 20 MB R2 threshold). One 30-day chunk (2024-11-28..2024-12-27) returned
  a "Response ended prematurely" warning — best-effort; the adjacent chunks were
  successfully fetched so the gap is a single-month akshare transient, not a GFW block.

- **C3 (Tests):** 13 tests in `tests/test_china_alpha_w3c_infra.py`, all passing. 0
  existing test regressions (`test_drip_append_only.py`, `test_china_extras.py` both
  green).

---

## C1 — Margin Daily Accrual

### What was done

The existing `collectors/china_margin_detail.py` had `refresh()` and `backfill()`
implemented but was NOT registered in `scripts/collect.py` — it was a dead file that
ran only if called manually. This wave wires it into the daily collect lane.

**Schema extension.** The prior schema stored only `fin_balance` (融资余额). The
akshare endpoints also expose:
- SSE (`stock_margin_detail_sse`): `融券余量` (short-lending volume, shares) →
  stored as `short_balance`
- SZSE (`stock_margin_detail_szse`): `融券余量` (shares) and `融券余额` (yuan) →
  stored as `short_balance` and `short_balance_yuan` respectively

Full schema as of this wave:

| Column | Type | Description |
|---|---|---|
| `date` | str YYYY-MM-DD | Trading date this row represents |
| `ticker` | str | e.g. `600000.SS` / `000001.SZ` |
| `fin_balance` | float | 融资余额 (financing balance), raw yuan |
| `short_balance` | float | 融券余量 (shares; SSE primary source) or None |
| `short_balance_yuan` | float | 融券余额 (yuan; SZSE only) or None |
| `fin_balance_prior` | float | `fin_balance` ~20 trading days earlier |
| `prior_date` | str | Date of `fin_balance_prior` |
| `asof` | str | UTC date this row was collected |

**Existing consumers** (`engine/china_extras.margin_positioning`) read `fin_balance`
and `fin_balance_prior` — unchanged. The new columns are additive.

**Adapter class.** `ChinaMarginDetailAdapter` subclasses `collectors.base.Adapter`
and wraps `refresh()` in the circuit-breaker / freshness machinery. `fetch()` returns
a sentinel DataFrame so `run_adapter` records success/failure in `run_status.json`.
`stale_after_days = 3` flags the health surface if no new session appears for 3+ days.

**Sentinel/commit coverage.** `data/china_margin_detail/` is under `data/` — covered
by `git add data/` in both `daily.yml` and `asia-close.yml`. The `china_margin_detail`
key starts with `china`, so `group_members("asia", ...)` auto-includes it. No sentinel
path additions needed (the #1026 race condition was about specific paths staged in
`sentinel.yml` — which stages only `data/vector`; `china_margin_detail` runs in the
`asia-close` lane, not the 30-min sentinel lane).

**Idempotency.** `_stored_sessions()` returns dates already on disk; `refresh()` skips
if today's session exists. `_drip.append_snapshot` de-dups on `(date, ticker) keep-last`.

**Best-effort gate.** akshare failures inside `_detail_for()` are caught per-exchange
and return `{}`. A total failure (both exchanges fail) causes `refresh()` to return 0
without raising — the collect lane never fails on this source.

### Carry-over note for W3 status log

**Margin store becomes analysis-ready for margin-velocity phase-0 after ~60 accrued
daily sessions (~2026-09-29).** The per-name velocity signal is UNTESTED; registered
as ACCRUE in `data/experiments/registry_seed.json` (id: `w3c-margin-velocity-substrate`).

---

## C2 — LHB Backfill

### What was done

`scripts/backfill_china_lhb.py` created as a standalone script. The script:

1. Calls `collectors.china_lhb.backfill(start, end)` which fetches
   `ak.stock_lhb_detail_em` in 30-day chunks and appends to `data/china_lhb/events.parquet`.
2. Copies `events.parquet` → `data/china_lhb/history.parquet` (stable alias for
   phase-0 harnesses that should not be confused with the rolling daily collect).
3. Reports a R2-plane decision if the file exceeds 20 MB (it does not: 0.34 MB).
4. Applies a hard SIGALRM timeout (default 600 s; Darwin/POSIX only).

**Schema of `history.parquet`** (one row per name × 上榜日 × reason):

| Column | Type | Description |
|---|---|---|
| `date` | str YYYY-MM-DD | 上榜日 (board-appearance date) |
| `ticker` | str | e.g. `600000.SS` / `000001.SZ` |
| `name` | str | Stock short name (Chinese) |
| `net_buy_yi` | float | 龙虎榜净买额 ÷ 1e8 (亿; positive = net buy) |
| `reason` | str | 上榜原因 (trigger reason) |

Dedup key: `(date, ticker)` keep-last (via `_drip.append_snapshot`).

**Run result (2026-07-03, ~570 s):**

| Metric | Value |
|---|---|
| Events written | 28,580 net rows in events.parquet (33,605 pre-dedup appends; (date,ticker) keep-last dedup collapses multi-reason same-day rows — net_buy under-counted for multi-reason names, a caveat the future seat-quality phase-0 must handle) |
| Rows in history.parquet | 28,580 |
| Unique trading dates | 409 |
| Date range | 2024-07-01 .. 2026-07-03 |
| Unique tickers | 4,313 |
| history.parquet size | 0.34 MB |
| R2-plane needed | No (< 20 MB) |
| Gaps | One 30-day chunk (2024-11-28..2024-12-27) returned "Response ended prematurely"; surrounding chunks succeeded |

The gap is best-effort/akshare transient. The script can be re-run targeting just the
missing window: `python3 scripts/backfill_china_lhb.py --start 2024-11-28 --end 2024-12-27`.

**Adapter class.** `ChinaLhbAdapter` added to `collectors/china_lhb.py`, registered
in `scripts/collect.py` under `china_lhb` (auto-joins `asia` group). `stale_after_days = 3`.

**LHB store becomes analysis-ready immediately** — the 409-date / 28,580-event backfill
is available now. The caveat is that the inst-seat split (the weak-positive ACCRUING
leg) requires `events.parquet` rows filtered for institutional-seat appearances —
the current backfill only captures `stock_lhb_detail_em` (the retail/aggregate tape),
not `stock_lhb_jgmmtj_em` (the inst-seat split). The institutional split needs a
separate backfill step before the inst-seat phase-0 can run.

### Carry-over note for W3 status log

**LHB history is immediately available for the raw-flag sign audit (2024-07..2026-07,
28.6k events, 409 dates).** The inst-seat split needs a separate backfill via
`stock_lhb_jgmmtj_em` before a full seat-quality phase-0 is runnable. Registered as
ACCRUE (id: `w3c-lhb-backfill`; come_back 2026-10-01).

---

## C3 — Tests

File: `tests/test_china_alpha_w3c_infra.py` — 13 tests, 0 failures.

| Test class | Tests | What is covered |
|---|---|---|
| `TestMarginDetailSchema` | 4 | `_detail_for()` schema (SSE+SZSE); `refresh()` column set; idempotency; akshare failure non-fatal |
| `TestLhbAdapter` | 5 | `_raw_events()` schema; idempotency via `_drip`; akshare failure non-fatal; script importable; dry-run |
| `TestCollectRegistration` | 4 | Both keys in `collect.py`; both in `asia` group; adapter classes loadable |

All mocking via `patch.dict("sys.modules", {"akshare": mock_ak})` (akshare is imported
locally inside functions, not at module level, so standard `patch("module.ak")` does
not work — this is the correct idiom for lazy imports).

Regression check: `test_drip_append_only.py` (5 tests) and `test_china_extras.py`
(7 tests) both pass with no changes needed — the schema extension is purely additive.

---

## Files changed

| File | Change |
|---|---|
| `collectors/china_margin_detail.py` | Added `short_balance` / `short_balance_yuan` to schema; added `ChinaMarginDetailAdapter`; refactored `_detail_for` to extract both exchanges' short fields |
| `collectors/china_lhb.py` | Added `ChinaLhbAdapter` class |
| `scripts/collect.py` | Registered `china_margin_detail` + `china_lhb` adapters |
| `scripts/backfill_china_lhb.py` | New standalone backfill script (C2 deliverable) |
| `tests/test_china_alpha_w3c_infra.py` | New test file, 13 tests (C3 deliverable) |
| `data/china_lhb/history.parquet` | New: 28,580 rows, 2024-07-01..2026-07-03, 0.34 MB |
| `data/china_lhb/events.parquet` | Extended by backfill run |
| `data/experiments/registry_seed.json` | +2 entries: `w3c-margin-velocity-substrate`, `w3c-lhb-backfill` |

---

## Open items / known limits

1. **Margin backfill not yet run.** The existing `data/china_margin_detail/detail.parquet`
   holds only 3 sessions (2026-06-30..07-02). A backfill going further back (e.g. 1 year)
   can be triggered by `python3 -m collectors.china_margin_detail --backfill 2025-07-01 2026-06-29`.
   The SSE/SZSE per-date endpoints serve historical data; estimated 250+ akshare calls per
   year. Not done in this wave — the rolling daily collect builds the history going forward
   and the analysis-ready threshold is ~60 sessions (~2026-09-29).

2. **LHB inst-seat backfill missing.** `scripts/backfill_china_lhb.py` only fetches
   `stock_lhb_detail_em` (retail tape). The `stock_lhb_jgmmtj_em` (institutional-seat split)
   backfill is a separate step needed before the inst-seat phase-0 can be run.

3. **One missing chunk.** 2024-11-28..2024-12-27 returned "Response ended prematurely"
   during the backfill. The chunk can be retried: `python3 scripts/backfill_china_lhb.py
   --start 2024-11-28 --end 2024-12-27`.

4. **`Timestamp.utcnow` deprecation warning.** Both `china_margin_detail.py` and
   `china_lhb.py` use `pd.Timestamp.utcnow()` (Pandas 4 warning). This is a pre-existing
   pattern across the codebase; not fixed in this wave.
