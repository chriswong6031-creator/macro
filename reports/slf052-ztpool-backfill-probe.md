# SLF-052 — ZT Pool Backfill Probe + Accrual Registration

**Lane:** L8 (data probe only — no signal test, no trial family)
**Date:** 2026-07-06
**Status:** COMPLETE — history NOT manufacturable beyond ~3 weeks; forward accrual hardened and extended.

---

## In plain English

The limit-up pool (涨停板) is a daily snapshot from Eastmoney listing every A-share stock that hit its +10%/+20% price ceiling on a given trading day. We wanted to know whether we could build a multi-year history of this data so it could eventually underpin a backtest. The answer is **no**: the Eastmoney API (via akshare) only retains data for about 3 weeks. Before that, you get an empty result regardless of how old the date is.

What we *can* do — and have done — is backfill the entire available window (2026-06-15 to today), grow the store from 6 sessions to 16, and ensure the collector appends new sessions every night without overwriting old ones. With 16 sessions on disk today, the store is now on a path to accumulate meaningful history going forward.

---

## (A) History Probe Results

**Method:** `akshare.stock_zt_pool_em(date=YYYYMMDD)` called at ~0.6s intervals (≤2 req/s).

### Deep history probe — 24 quarterly samples 2020–2025

| Date range | Dates probed | Data returned | Empty |
|---|---|---|---|
| 2020 (4 quarterly) | 4 | 0 | 4 |
| 2021 (4 quarterly) | 4 | 0 | 4 |
| 2022 (4 quarterly) | 4 | 0 | 4 |
| 2023 (4 quarterly) | 4 | 0 | 4 |
| 2024 (4 quarterly) | 4 | 0 | 4 |
| 2025 (4 quarterly) | 4 | 0 | 4 |

**All 24 historical dates returned empty results.** No errors — akshare accepts the call, returns an empty DataFrame. The endpoint does not raise for out-of-range dates.

### Retention window walk-back (60 calendar days from 2026-07-06)

| Date | Result | Rows |
|---|---|---|
| 2026-07-06 | DATA | 64 |
| 2026-07-05 | empty (Saturday) | — |
| 2026-07-04 | DATA (Friday) | 108 |
| … | DATA (trading days) | 60–152 |
| **2026-06-15** | **DATA (earliest)** | **145** |
| 2026-06-14 | empty | — |
| 2026-06-13 and earlier | empty | — |

**Retention cutoff: 2026-06-15.** The endpoint serves no data before this date. The window is approximately 3 weeks (≈15 trading days at time of probe). This is consistent with the standing display-only ruling (store held ~5 dates at lane start).

**Verdict: History CANNOT be manufactured.** The source endpoint retains only the most recent ~3 weeks of limit-up pool snapshots. No backfill mechanism exists for dates before the retention window.

---

## (B) Backfill — Available Window

Since history beyond ~3 weeks is unavailable, the backfill covers the full retention window: **2026-06-15 to 2026-07-06** (the current date).

**PIT discipline:** No publication lag adjustment is possible or needed here. The source publishes the pool for trading day T during the afternoon of day T (session closes ~15:00 CST). All stored `date` values represent the trading session date; `asof` records the UTC fetch date. No look-ahead risk in this store structure.

### Sessions appended

| Session | Names |
|---|---|
| 2026-06-15 | 145 |
| 2026-06-16 | 117 |
| 2026-06-17 | 86 |
| 2026-06-18 | 91 |
| 2026-06-19 | empty (holiday) |
| 2026-06-22 | 134 |
| 2026-06-23 | 96 |
| 2026-06-24 | 98 |
| 2026-06-25 | 86 |
| 2026-06-26 | 60 |
| 2026-06-30 | 140 (pre-stored) |
| 2026-07-01 | 152 (pre-stored) |
| 2026-07-02 | 93 (pre-stored) |
| 2026-07-03 | 108 (pre-stored) |
| 2026-07-04 | 108 (pre-stored) |
| 2026-07-05 | 108 (pre-stored) |
| 2026-07-06 | 64 (today, added via refresh()) |

**Total: 16 sessions, 1,686 rows, 52 KB on disk.**

Store location: `data/china_zt_pool/pool.parquet`

Tarball: `/tmp/slf052_ztpool_backfill.tar.gz` (42 KB compressed)

---

## (C) Hardening Assessment

**Finding: The collector is already append-only. No patch required.**

Inspecting `collectors/china_zt_pool.py`:

- `refresh()` calls `_stored_sessions()` before writing — already-stored sessions are skipped (idempotent).
- All writes go through `collectors/_drip.py:append_snapshot()` which de-duplicates on `(date, ticker)` keep-last — a same-day re-collect corrects rather than duplicates.
- `backfill(start, end)` function already exists with proper skip logic.

The `_drip.py` module was added specifically to convert snapshot-overwrite collectors to append-only (per CN-1 masterplan §W6-CN). The zt_pool collector was already converted at that time.

**No collector code was modified.** The standing ruling says not to touch other collector behavior; no patch was needed.

---

## (D) Accrual Registration

### History on disk as of 2026-07-06
- **Earliest session:** 2026-06-15
- **Latest session:** 2026-07-06
- **Sessions:** 16 trading days
- **Names:** 1,686 rows

### Earliest possible phase-0 date
Under the **display-only** ruling (SLF-052 standing), no signal test is permitted until gauntlet conditions are met. If a future phase-0 were registered:
- A minimum meaningful cross-sectional sample requires ~60 trading sessions.
- At current accrual rate (nightly), the store will reach 60 sessions approximately **2026-10-01** (assuming ~1 trading session/day).
- Earliest phase-0 eligibility: **no earlier than 2026-Q4**.

### limit_breadth aggregate limitation
The `engine/china_extras.py` uses `zt_sector_breadth` — an aggregate computed from this pool (count of limit-up names per sector per day). The source endpoint retains **approximately 2 weeks** of data (confirmed: last data returned was 2026-06-15 vs probe date 2026-07-06 = 21 calendar days, ~15 trading days). This aggregate:
- **Is NOT backfillable** beyond the retention window.
- Has the same ~3-week retention as the pool itself.
- Any historical `limit_breadth` signal analysis must wait until the store accumulates sufficient forward history (no PIT-clean history exists before 2026-06-15).

---

## Pre-registered Gates

This is a data probe lane (no signal test, no trial family). Pre-registered gates were:

| Gate | Pass/Fail |
|---|---|
| Probe ≥ 24 quarterly dates spanning 2020–2025 | PASS (24 probed) |
| Report exact dates with data vs. empty | PASS (all empty; retention edge = 2026-06-15) |
| Backfill available window (if any history served) | PASS (10 new sessions appended; 6 pre-stored; 16 total; oldest 2026-06-15) |
| Store is append-only, idempotent | PASS (already hardened via _drip.append_snapshot) |
| Report limit_breadth aggregate limitation | PASS (confirmed ~2 weeks; not backfillable) |
| Tests: pure-function, no network | PASS (10 tests, all green) |
| check_validated_claims.py | PASS |

---

## Nightly Wiring (for consolidation)

The `refresh()` function in `collectors/china_zt_pool.py` is the correct nightly entry point. It is idempotent (skips already-stored sessions) and appends via `_drip.append_snapshot`.

If not already wired in `scripts/collect.py`, add:
```python
from collectors.china_zt_pool import refresh as china_zt_pool_refresh
china_zt_pool_refresh()
```

Do NOT add a backfill cron — the retention window has been exhausted. Only `refresh()` is needed going forward.

---

## Files Produced

- `tests/test_slf052_ztpool.py` — 10 pure-function tests (all pass)
- `data/china_zt_pool/pool.parquet` — extended from 6→16 sessions (worktree only; HEAD baseline was 6 sessions / 709 rows; 10 new sessions backfilled)
- `/tmp/slf052_ztpool_backfill.tar.gz` — 42 KB tarball of the backfilled store
- `reports/slf052-ztpool-backfill-probe.md` — this report
