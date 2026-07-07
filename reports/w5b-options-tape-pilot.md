# W5-B Options Tape Signed Pilot — ThetaTerminal UP

**In plain English:** We pulled every options trade with its simultaneous bid/ask
quote from ThetaTerminal for 20 liquid names. Each trade was classified as buyer-
or seller-initiated using the simple quote rule (trade at/above ask = buy, at/below
bid = sell, in the middle = excluded). The data is stored per-name as signed
aggregate premium and delta-weighted volume for each trading day.

## Pre-registration

Pre-registered gates and amendments (written before first compute):
- **Signing rule:** simple quote rule (price >= ask → BUY, price <= bid → SELL,
  midpoint excluded). NOT Lee-Ready tick-test. Stated explicitly.
- **Delta source:** moneyness-bucket proxy (Amendment A2). No live delta store
  available. Column labeled `delta_proxy` to distinguish from model delta.
- **Amendment A1:** trade_quote accepts wildcard expiration per day (confirmed live).
  One-calendar-day per request, 6 concurrent underlyings.

## Coverage

- Underlyings targeted: 20
- Trading days targeted: 60
- Name-days completed: 1200 of 1200 (100.0%)
- Errors: 0
- Total wall-clock: 1373s (22.9 min)

### Per-underlying completed dates

| Underlying | Dates completed |
|-----------|----------------|
| SPY | 60 |
| QQQ | 60 |
| AAPL | 60 |
| MSFT | 60 |
| NVDA | 60 |
| TSLA | 60 |
| AMZN | 60 |
| META | 60 |
| GOOGL | 60 |
| AMD | 60 |
| GS | 60 |
| JPM | 60 |
| BAC | 60 |
| XOM | 60 |
| CVX | 60 |
| JNJ | 60 |
| UNH | 60 |
| WMT | 60 |
| HD | 60 |
| V | 60 |

## Throughput

- Average elapsed per name-day: 5.4s
- Median elapsed per name-day: 2.6s
- P95 elapsed per name-day: 18.3s
- Total raw trade rows processed: 267,281,438
- Average raw rows per name-day: 222,735

### Projected full-build wall-clock

**Measured actual:** 20 names x 60 days = 1373s (22.9 min). This is the ground truth.

- **20 names x 60 days pilot:** 22.9 min (measured, not projected)
- **Full backfill to 2012-06-01 (20 names x ~3500 trading days):**
  ~3500/60 x 22.9 min = 22.9 min x 58 = ~22 hours at measured throughput
- **Extension to 500 names (full pilot universe, 60 days):**
  500/20 x 22.9 min = ~10 hours
- **Extension to 500 names x full backfill:**
  500/20 x 22 hours = ~550 hours (~23 days serial)
  → Strategy: run incremental nightly, full backfill offline as a batch job

**Nightly incremental (1 new day, 20 names):** 22.9 min / 60 = ~0.38 min (23 sec) per day

> NOTE: SPY and QQQ dominate P95 (2M+ rows/day each, 25-70s each vs 1-12s for single-names).
> Separating ETFs from single-names into two concurrent pools would reduce the tail significantly.
> The actual 22.9 min vs 61 min projected reflects that P95 is a per-name metric, not per-batch.

## Data quality spot-check

**AAPL** (60 days):
  - Average exclusion rate: 42.0% (midpoint trades excluded)
  - Average midpoint rate: 41.5%
  - Net premium sample (last 3 days): [11618689.0, 18188176.0, 50927613.0]

**AMD** (60 days):
  - Average exclusion rate: 59.3% (midpoint trades excluded)
  - Average midpoint rate: 58.6%
  - Net premium sample (last 3 days): [18471464.0, -23540192.0, -21828787.0]

**MSFT** (60 days):
  - Average exclusion rate: 52.3% (midpoint trades excluded)
  - Average midpoint rate: 51.8%
  - Net premium sample (last 3 days): [-4219299.0, 46769001.0, 365862.0]


## PIT assumptions

- Spot price: sourced from `massive_stock_day/<UNDERLYING>.parquet` last close
  strictly at or before the trade date. This is PIT-safe: no look-ahead.
- Delta proxy: moneyness bucket as of the spot price at the time of signing.
  Because spot is EOD-prior (not intraday), there is a small intraday bias;
  stated, not hidden.
- OI timing (for future signal use): OPRA reports OI at 06:30 ET = EOD t-1.
  Any signal using OI must lag one day.

## Signing rule detail

```
Simple quote rule (NOT Lee-Ready tick-test):
  price >= ask          → BUY-SIDE  (trade at or above the offer)
  price <= bid          → SELL-SIDE (trade at or below the bid)
  bid < price < ask     → EXCLUDED  (midpoint; initiator ambiguous)
  bid=NaN or ask=NaN    → EXCLUDED  (missing NBBO)
  bid > ask (crossed)   → EXCLUDED  (crossed market; quote unreliable)
```

The Lee-Ready tick-test would classify midpoint trades using the
prior tick direction. We chose the simpler pure-quote rule because:
1. The lane spec explicitly instructs it.
2. Tick-test introduces path-dependence that is harder to audit.
3. Exclusion rate is measured and reported; if high, a future pass
   can add tick-test as an alternative classification.

## Output schema

```
data/options_tape_signed/<UNDERLYING>.parquet
Columns:
  underlying          str  — ticker symbol
  date               datetime64  — trading date
  buy_premium        float  — sum(price * size * 100) for BUY trades
  sell_premium       float  — sum(price * size * 100) for SELL trades
  net_premium        float  — buy_premium - sell_premium (signed flow)
  buy_delta_proxy    float  — sum(delta_proxy * size) for BUY trades
  sell_delta_proxy   float  — sum(delta_proxy * size) for SELL trades
  net_delta_proxy    float  — buy_delta_proxy - sell_delta_proxy
  buy_count          int    — number of BUY-classified trades
  sell_count         int    — number of SELL-classified trades
  excluded_count     int    — number of excluded (midpoint/missing) trades
  total_count        int    — total raw trades (buy + sell + excluded)
  exclusion_rate     float  — excluded_count / total_count
  mid_rate           float  — midpoint-only exclusion / total_count

data/options_tape_signed/_backfill_state.json
  Resumable state machine per-underlying: cursor, completed_dates, errors.
```

## Delta proxy bucketing (Amendment A2)

```
Moneyness = (spot - strike)/spot for calls, (strike - spot)/spot for puts
  ITM  |m|>0.20  → delta_proxy = 0.90
  ITM  |m|>0.10  → delta_proxy = 0.70
  NTM/ATM |m|≤0.10 → delta_proxy = 0.50
  OTM  |m|>0.10  → delta_proxy = 0.30
  OTM  |m|>0.20  → delta_proxy = 0.10
Source: massive_stock_day EOD close (PIT-safe).
Label in output: delta_proxy (NOT model delta).
```

## Nightly wiring note (for consolidation)

**Accrual cadence proposal:**

1. **Timing:** run at 21:00 ET (after ThetaTerminal post-market data update ~20:00 ET).
   Today's trade_quote data is available from the terminal within ~1h of market close.

2. **Incremental pull:** read `_backfill_state.json`; for each underlying, pull only
   dates after the cursor. Typical nightly load: 1 date x 20 names = 20 name-days.
   Estimated: ~23 sec/night (measured: 22.9 min / 60 dates, wall-clock for 20 concurrent names)

3. **Consolidation target:** `scripts/collect.py` nightly job.
   Add a `collect_options_tape` stage after existing theta stages.
   (This file does NOT edit collect.py — per House Rule 6.)

4. **Extension to 500 names:** add to `PILOT_UNDERLYINGS` list in this script,
   or pass via `--underlyings` flag (future). Concurrency ceiling = 6 connections.
   At 500 names, nightly incremental load: ~500/6 * avg_s = 7 min/night

5. **R2 storage (future):** at 500 names x 3500 trading days, the store will grow
   to ~10-50 GB compressed parquet. If this exceeds git budget, move to R2 bucket
   (pattern: `data/options_tape_signed/` → `r2://options-tape-signed/`), consistent
   with the existing R2 pattern for `massive_stock_day`.
