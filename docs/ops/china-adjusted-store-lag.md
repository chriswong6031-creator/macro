# china_stocks adjusted store lag — diagnosis and fix (CN-SYS W5a)

**Symptom (observed 2026-07-08):** `data/china_stocks/` (dividend-adjusted OHLC,
1598 parquets) was 5 days stale at last-date 2026-07-02, while `data/china_stocks_raw/`
(nominal/unadjusted, 1587 parquets) was current at 2026-07-07. Since every live China
engine (`china_standout_track`, `china_alpha`, `build_china_library`, etc.) reads the
adjusted store, this staleness poisoned all per-name signal computation for 5 trading days.

## Root cause

Two GHA mechanisms — git commits and the `actions/cache@v4` store — diverged:

1. `asia-close.yml` restored `data/china_stocks/` from the `china-stocks-ohlc-` cache prefix
   **before** running `collect --group asia`. The cache content could be up to one day older
   than the committed git data if a prior asia-close push raced with daily.yml.

2. `daily.yml` (runs at 02:00 UTC, before asia-close at 08:30 UTC) has TWO restore steps for
   `data/china_stocks`, both from the same `china-stocks-ohlc-` prefix. After restoring
   potentially-stale cached data, `daily.yml` runs `git add data/` and commits whatever is
   in the working directory — including the cache-restored stale parquets, even if the
   current HEAD already has fresher data committed by a prior asia-close run.

3. `run_status.json` showed `china_stocks: status=ok, last_date=2026-07-07` because the
   status is written by the adapter in-process during the collect step. But the collected
   data was NEVER committed to git on 2026-07-07 because the "data: daily collection
   2026-07-07" commit (SHA 38dc031b11) staged the stale cache data and overwrote the
   fresh asia-close data that had been committed the same day (b93be50903).

**Confirmed:** `git show b93be50903:data/china_stocks/000001.SZ.parquet` → last=2026-07-07
(correct). `git show 38dc031b11:data/china_stocks/000001.SZ.parquet` → last=2026-07-02
(daily regression). The daily.yml commit retrograded 1587 of 1598 parquets.

## Fix applied (CN-SYS W5a, 2026-07-08)

**`asia-close.yml`**: Removed `restore-keys: china-stocks-ohlc-` from the
`data/china_stocks` cache step. The primary key `china-stocks-ohlc-${{ github.run_id }}`
always misses (unique per-run), so no restore occurs. The `actions/cache@v4` step still
SAVES the post-collect fresh parquets under the new key at job end, so `daily.yml`'s
engine-job cache-restore gets fresh data. The asia-close collect step itself does not
need the prior run's cache — the git checkout already has all committed parquets and
`store.upsert` merges fresh yfinance data directly.

**Note**: `daily.yml`'s two `data/china_stocks` cache-restore steps remain and continue
to use `restore-keys: china-stocks-ohlc-`. Since asia-close now saves fresh data under
a unique key (and runs before the NEXT day's daily.yml), the daily engine job restores
today's fresh asia-close data, which matches what's in git. The regression loop is broken.

## What to watch

- If asia-close fails to reach the cache-save step (job timeout or earlier failure),
  daily.yml will restore yesterday's cache. This is acceptable for the engine job (it
  reads the same data the prior run computed), but the committed git data will be fresh
  from asia-close's data-commit step (which runs before the build step).

- The `git show <sha>:data/china_stocks/<TICKER>.parquet` diagnostic is the ground
  truth. The `run_status.json` `last_date` is in-process state and may not match the
  committed git content if the push loop failed.

- If the regression recurs, look at `git log --oneline -- data/china_stocks/000001.SZ.parquet`
  and compare the last dates in successive commits. A "data: daily collection" commit
  that regresses the date means daily.yml committed stale cache data.

## Architecture note

All 1599 `data/china_stocks/` parquets and 1587 `data/china_stocks_raw/` parquets are
committed to git (not cache-only). The comment in `daily.yml` saying "only the ~12-name
seed is committed" is outdated — the full universe has been committed since the W6-CN
backfill. This means the cache is only needed for `daily.yml`'s ENGINE job (a separate
GHA job with a fresh checkout that reads the per-name OHLC for US-listed China signal
computation). The collect job in `asia-close.yml` and `daily.yml` both get the full
universe from the git checkout.
