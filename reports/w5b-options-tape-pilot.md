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
  500/20 x 22 hours = ~556 hours (~23 days serial)
  → Strategy: run incremental nightly, full backfill offline as a batch job

**Nightly incremental (1 new day, 20 names):** 22.9 min / 60 = ~0.38 min (23 sec) per day

> NOTE: SPY and QQQ dominate P95 (2M+ rows/day each, 25-70s each vs 1-12s for single-names).
> Separating ETFs from single-names into two concurrent pools would reduce the tail significantly.
> The actual 22.9 min vs 61 min P95-projected reflects that P95 is a per-name metric, not per-batch.

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

## Raw-trade classification spot-check

**Underlying: V (Visa), date: 2026-07-02**

Spot price (EOD prior close, PIT): $362.13  
Total raw rows pulled: 12,037  
Classification: buy=1,909 / sell=1,641 / excluded=8,487 (70.5% exclusion rate)

The 10-row sample below was captured live from ThetaTerminal during this build session
(2026-07-07) and written to `data/options_tape_signed/_sample_V_2026-07-02.json`
for reproducibility without a re-pull. The reviewer independently confirmed
buy_count=1,909 from a separate pull, matching the code output exactly.

```
 #  price    bid    ask  strike  right  size  side   delta_proxy  signed_m       classification reason
 0  32.00  30.20  32.00   330.0   CALL     1  BUY    0.50        +0.089 ITM     price(32.00)==ask(32.00) → BUY
 1  34.00  32.25  34.00   330.0   CALL     4  BUY    0.50        +0.089 ITM     price(34.00)==ask(34.00) → BUY
 2  34.10  33.05  34.10   330.0   CALL     1  BUY    0.50        +0.089 ITM     price(34.10)==ask(34.10) → BUY
 3   5.40   5.15   5.40   305.0    PUT     1  BUY    0.30        -0.158 OTM     price(5.40)==ask(5.40) → BUY
 4   3.45   3.45   3.65   330.0    PUT     4  SELL   0.30        -0.089 OTM     price(3.45)==bid(3.45) → SELL
 5   3.15   3.15   3.40   330.0    PUT     3  SELL   0.30        -0.089 OTM     price(3.15)==bid(3.15) → SELL
 6  12.10  12.10  12.35   385.0   CALL     2  SELL   0.30        -0.063 OTM     price(12.10)==bid(12.10) → SELL
 7   4.14   3.80   4.55   330.0    PUT     2  None   0.30        -0.089 OTM     3.80<4.14<4.55 → midpoint EXCLUDED
 8   4.10   3.80   4.45   330.0    PUT     4  None   0.30        -0.089 OTM     3.80<4.10<4.45 → midpoint EXCLUDED
 9   4.10   3.80   4.45   330.0    PUT     3  None   0.30        -0.089 OTM     3.80<4.10<4.45 → midpoint EXCLUDED
```

signed_m convention: calls = (spot-strike)/spot, puts = (strike-spot)/spot.
Rows 0-2 (CALL strike=330, spot=362.13): m=(362.13-330)/362.13=+0.089 → ITM → |m|≤0.10 → 0.50.
Row 3 (PUT strike=305): m=(305-362.13)/362.13=-0.158 → OTM, |m|=0.158, 0.10<|m|≤0.20 → 0.30.
Rows 4-9 (PUT strike=330): m=(330-362.13)/362.13=-0.089 → OTM, |m|=0.089≤0.20 → 0.30.
Note: slightly-OTM puts (|m|=0.089) land in the OTM branch (→0.30), not NTM/ATM (→0.50),
because the bucketing branches on sign(m), not purely on |m|. This is intentional and tested.

Signing rule verification (rows 0-9):
- Rows 0-3: price == ask → BUY (correct)
- Rows 4-6: price == bid → SELL (correct)
- Rows 7-9: bid < price < ask → EXCLUDED/midpoint (correct)

Source: `data/options_tape_signed/_sample_V_2026-07-02.json`

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
Columns (16 total, in order):
  underlying          str  — ticker symbol
  date               datetime64  — trading date
  raw_rows           int    — total rows returned by terminal before signing
  elapsed_s          float  — wall-clock seconds for fetch+sign (per name-day)
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
  Note: this file is NOT git-tracked (it lives under data/ which is gitignored
  for size reasons). On a fresh CI checkout the state file is absent; the build
  starts from scratch, pulling the full date range for any uncompleted underlyings.
  The nightly pipeline runs on the host machine (not a fresh checkout), so state
  persists across runs in practice.

data/options_tape_signed/_sample_<UNDERLYING>_<DATE>.json
  Classification spot-check: 10 representative signed rows (price, bid, ask,
  strike, right, size, side, delta_proxy) written at build time. See section below.
```

## Delta proxy bucketing (Amendment A2)

```
Moneyness convention (as implemented in _moneyness_delta_proxy):
  For calls: signed_m = (spot - strike) / spot   [positive = ITM call]
  For puts:  signed_m = (strike - spot) / spot   [positive = ITM put]

Bucketing branches on sign of signed_m (ITM = positive, OTM = negative):
  ITM branch (signed_m >= 0):
    deep ITM  |m| > 0.20           → delta_proxy = 0.90
    ITM       0.10 < |m| <= 0.20   → delta_proxy = 0.70
    NTM/ATM   |m| <= 0.10          → delta_proxy = 0.50
  OTM branch (signed_m < 0):
    OTM       |m| <= 0.20          → delta_proxy = 0.30  (NTM-OTM included)
    deep OTM  |m| > 0.20           → delta_proxy = 0.10

Notes:
- The 0.03 ATM boundary mentioned in Amendment A2 planning is NOT implemented;
  NTM and ATM are collapsed into a single bucket (|m|<=0.10) within the ITM branch.
- Slightly-OTM contracts (|m|<=0.10 OTM) receive delta_proxy=0.30, NOT 0.50 —
  because the OTM branch has no sub-ATM bucket. See spot-check row 4 (PUT
  strike=330, spot=362, m=-0.089 → OTM → 0.30) for a live example.

Source: massive_stock_day EOD close (PIT-safe).
Label in output: delta_proxy (NOT model delta).
```

**IMPORTANT — delta_proxy is unsigned (magnitude only).** Both calls and puts
receive a positive proxy value for the same moneyness bucket. A deep-ITM put
gets delta_proxy=0.90, not -0.90. Therefore `net_delta_proxy` is NOT a
directional put-vs-call flow indicator. It is a flow-size proxy (signed only by
BUY/SELL classification), weighted by moneyness magnitude. Consumers must not
interpret it as a delta-adjusted directional position.

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
   At 500 names, nightly incremental load: ~10 min/night

5. **R2 storage (future):** at 500 names x 3500 trading days, the store will grow
   to ~10-50 GB compressed parquet. If this exceeds git budget, move to R2 bucket
   (pattern: `data/options_tape_signed/` → `r2://options-tape-signed/`), consistent
   with the existing R2 pattern for `massive_stock_day`.
