# Multi-Country OHLC Data Source — Research, Recommendation & PoC

> **Status: RESEARCH + RECOMMENDATION for owner greenlight. The collector is NOT
> built.** This document picks the data source for a per-name CN/HK OHLC store and
> sketches the wiring. No store is written and `collect.py` is unchanged until the
> owner says go. Read [`CHARTER.md`](CHARTER.md) for what the signal engine is and
> how it is judged; this doc only feeds it a cleaner input.

---

## 1. TL;DR / Recommendation

**Use `yfinance` 1.4.1 as the PRIMARY source for BOTH A-shares and HK, and
`akshare` 1.18.64 as a keyless native-source SECONDARY for cross-check / one-time
backfill.** yfinance returns full daily OHLC **with real High and Low**, the
deepest history of the three (000001.SZ to 1991, 600519.SS to 2001, 0700.HK to
2004 — all confirmed by the PoC), and its **`.SS` / `.SZ` suffixes already match
`data/china/*.parquet`** so there is zero remapping. It is already the repo's
CI-proven standard puller (`yf.download` across ~15 scripts, including
`china_residual_alpha_deep.py` and `hk_residual_alpha_phase0.py` which already
pull CN/HK via yfinance). akshare is SECONDARY — not primary — because its `qfq`
adjust goes **negative** on high-dividend multi-baggers, its A-share volume is in
手 (lots of 100), and it carries Eastmoney captcha / IP-ban / thread-segfault risk
that already forces a CI-skip. **Tushare ¥500 is NOT recommended for OHLC:** it
buys no incremental data over free yfinance while adding a paid HK surcharge
(¥1,000/yr, NOT in the ¥500 tier), a `.SH→.SS` remap, a new token secret, and a
non-commercial ToS that blocks the SaaS pivot. Keep the Tushare ¥500 tier for the
CN **fundamentals** it already serves ([[china-intel-powerhouse]]), not for prices.

---

## 2. Comparison

| Dimension | **yfinance 1.4.1** (PRIMARY) | **akshare 1.18.64** (SECONDARY) | **Tushare ¥500** (not for OHLC) |
|---|---|---|---|
| A-share coverage | Yes — `.SS`/`.SZ` suffix, matches store. PoC: 600519.SS, 000001.SZ | Yes — bare 6-digit (`600519`), SH/SZ resolved internally | Yes — `pro.daily()`, but `.SH`/`.SZ` suffix (remap needed) |
| HK coverage | Yes — `.HK` suffix. PoC: 0700.HK. No tier gate | Yes — 5-digit zero-pad (`00700`). No tier gate | Yes — but `hk_daily` **not** in ¥500 tier (separate ¥1,000/yr) |
| OHLC has HIGH/LOW | **Yes** (O/H/L/C/V; `auto_adjust=False` adds Adj Close). PoC: high/low present all 3 | **Yes** (开盘/收盘/最高/最低/成交量) | Yes (open/high/low/close/vol on both `daily` & `hk_daily`) |
| History depth | **Deepest.** PoC: 000001.SZ→1991 (8,887), 600519.SS→2001 (6,109), 0700.HK→2004 (5,438) | Matches within a few %: 8,423 / 5,948 / 5,427 (start-date dependent) | To IPO date; HK earliest-date undocumented (verify per ticker) |
| Update cadence | EOD same day (T+0). PoC pulled through 2026-06-26 | EOD same day (T+0), ~18:00 CST | EOD same day (T+0); HK ~18:00 HKT |
| Cost | **Free, no key** | **Free, keyless** (MIT lib; Eastmoney scrape) | ¥500 owned + **¥1,000/yr** for HK; token required |
| Licensing / redistribution | Legally gray (Yahoo ToS); **derived-signals-only is the defensible posture** — data sourced via ICE Data Services | Ambiguous; Eastmoney unofficial scrape, "academic research only" — real takedown risk as PRIMARY | **Non-commercial personal-use only** — hard blocker for the paid SaaS |
| Reliability / CI | **MODERATE.** Already in CI. Risk = Yahoo-side 429 (unfixed by 1.4.x); needs chunk+sleep+retry+`repair=True` | **POOR for CI.** captcha/IP-ban/segfault → already CI-SKIPPED, SERIAL-only | Moderate; **not installed**, no token in env; would become another CI-skipped dep |

---

## 3. Recommendation rationale

**Why yfinance is PRIMARY.** Four reasons, all PoC-verified:
1. **It already gives the thing this whole project needs — real High/Low.** With
   `auto_adjust=False` the download returns `[Open, High, Low, Close, Volume,
   Adj Close]`; with `auto_adjust=True` it returns the five adjusted columns. Either
   way High and Low are present and split-consistent. This is the *real fix* for the
   close-only gap (see §5).
2. **Zero remapping.** `.SS`/`.SZ`/`.HK` are exactly the keys `data/china/*.parquet`
   already uses. No suffix translation, no code→exchange lookup table to maintain.
3. **Deepest history** of the three sources (PoC: 1991 / 2001 / 2004) — far more than
   the confluence engine needs.
4. **It is already the repo standard and already in CI.** Adopting it adds *no new
   dependency, no new secret, no new CI surface.*

**Why akshare is SECONDARY (cross-check / backfill), not PRIMARY.** Confirmed
verdict: `qfq`-negative + thread-segfault + captcha/IP-ban CI-skip together
disqualify it as primary. Concretely: (a) `adjust='qfq'` returns **negative** prices
on big multi-baggers (PoC: 600519 first close raw `35.55` vs qfq `-312.47`),
corrupting any range/ATR math; (b) A-share 成交量 is in 手 (PoC: 000001 vol
`1,236,482` 手 = `123,648,164` shares — a silent **×100** error if unconverted);
(c) Eastmoney injects captcha and IP-bans automated/overseas IPs and the adapters
**segfault under threads** (`collect.py`: "14 akshare adapters segfault under
threads"), so it is already CI-skipped and SERIAL-only. It remains valuable as an
independent second source (different backend, native exchange data) for backfill and
spot cross-checks — see the fallback design below — but it cannot be the nightly
backbone.

**Why NOT Tushare ¥500 for OHLC.** It buys **zero incremental data** over free
yfinance (same OHLC, same ~35y depth — the PoC already proves yfinance reaches 1991)
while adding cost and friction: HK `hk_daily` is **not** in the ¥500/5000-point tier
and costs a **separate ¥1,000/yr** (confirmed); a mandatory `.SH→.SS` remap on every
write; a `TUSHARE_TOKEN` secret that is not currently set; a new pip dep that is not
installed; and a **non-commercial personal-use ToS** that is a hard blocker for the
SaaS pivot. Keep the ¥500 tier doing what it already does well — CN fundamentals.

**Addressing the completeness-critic gaps.** These do not change the source choice
but the collector must handle them (carried into §4 as build requirements):
- **Splits / corporate actions.** yfinance `auto_adjust=True` adjusts High/Low, but
  the price-repair wiki only documents HK *close* fixes and states "only US market
  data appears perfect." Mitigation: pull with **`repair=True`** for all CN/HK, and
  the collector's QA step must spot-check High/Low (not just close) against the
  akshare `hfq` series on at least one known split event per market before trusting
  range-derived features.
- **Batch throughput (~110 CN + 24 HK = 134 names).** Single `yf.download()` call per
  chunk of ~50, `time.sleep(random.uniform(2,5))` between chunks, off-hours nightly.
  Wall-clock is small (~3 chunks); the real risk is Yahoo-side **429**, which 1.4.x
  does **not** fix. Therefore the collector MUST have **retry-with-backoff +
  idempotent per-ticker writes** so a partial failure re-runs cleanly (the critic's
  point 5 — without this, partial-write state is undefined).
- **Halts / suspensions / delistings.** A-shares can suspend for weeks; delisted/ST
  names may return zero rows silently from a batch call. The collector must: write
  per-ticker so one dead name can't poison the batch; **skip (not zero-fill)** a
  ticker that returns `< N` rows; and **leave gaps as gaps** (do not carry-forward) so
  MACD/RSI see a true calendar.
- **Staleness / point-in-time.** Incremental pulls can silently absorb a Yahoo
  revision of a historical bar, contaminating walk-forward re-runs
  ([[signal-engine-walk-forward-harness]]). Decision deferred to the owner (§6):
  append-only immutable bars vs. accept best-effort revisions.
- **Redundancy / fallback.** Concrete trigger (not just a label): when yfinance
  returns `< 0.5×` the prior stored row count for a ticker, or `0` rows, the collector
  falls back to an **akshare `hfq`** pull for that single name (×100 A-volume fix +
  positive-adjust applied). This makes "secondary" operational.

---

## 4. Wiring design (NOT built — sketch for greenlight)

> Everything below is a SKETCH. No file is created and `collect.py` is untouched
> until greenlight.

**New per-ticker stores** (mirroring `data/stocks/*.parquet`, which is the verified
target format):
- `data/china_stocks/<CODE>.SS|.SZ.parquet` — e.g. `600519.SS.parquet`,
  `000001.SZ.parquet`
- `data/hk_stocks/<CODE>.HK.parquet` — e.g. `0700.HK.parquet`

These dirs today hold ONLY a `latest.json` aggregate (110 CN / 24 HK); there is no
per-name history anywhere in the repo. The index stores (`data/china/*.parquet` =
30 indices/ETFs, close+volume only; `data/hk/*.parquet` = 9 indices) **must not be
overwritten** — the new per-name store is a distinct path.

**Exact schema (match `data/stocks/*.parquet`):**
- `pandas` `DatetimeIndex` named **`Date`**
- columns **exactly** `[close, high, low, volume]`, **all `float64`**
- **no `open` column** (the confluence engine ignores open; drop it on ingest)

**Normalization the collector must do:**
- **yfinance (primary):** `yf.download(<chunk>, period="max", auto_adjust=True,
  repair=True)`. Result is a MultiIndex (ticker in the column level) — slice per
  ticker, map `Close→close, High→high, Low→low, Volume→volume`, **drop Open**, cast
  `float64`. Suffix `.SS/.SZ/.HK` is already the parquet key — **no remap**. Volume is
  in shares for both CN and HK — no unit fix. (Critic point 10: the MultiIndex slice
  must be guarded for a ticker that returns an all-NaN column in a mixed batch.)
- **akshare (secondary/backfill only):** strip suffix before the call
  (`600519.SS→600519`, `0700.HK→00700` 5-digit zero-pad); rename 收盘/最高/最低/成交量;
  **A-share volume ×100** (手→shares); HK volume already in shares; use **`hfq`**
  (positive, split-consistent) NOT `qfq` (negative); re-add the suffix as the parquet
  key. Document that an akshare-sourced row uses `hfq` and is **not** mixed into a
  yfinance `auto_adjust` series for the same ticker.
- **Tushare (not used):** would need `.SH→.SS` remap and `pro_bar(adj='qfq')` — listed
  only to show the cost it avoids.

**Plug into the existing serial CN/HK flow.** `collect.py` already runs the akshare
CN/HK adapters **serial** (segfault-under-threads constraint). Add a new serial step
that loops the 110 CN + 24 HK universe from the existing `latest.json` snapshots,
chunks yfinance calls (~50, sleep 2–5s), writes per-ticker parquets idempotently with
retry-on-429, and only on `<N`-row / zero-row results invokes the akshare fallback.
Sequential nightly is consistent with both the akshare serial rule and yfinance's
reentrant-but-not-concurrent guidance.

**Downstream (unchanged contracts).** The new `[close, high, low, volume]` per-name
store is exactly what the confluence/buy-filter expects (it currently runs on
close-only CN/HK and reconstructs range — see §5). Once real High/Low exist, the
confluence/3D math reads them directly, and the §7 site contract
`site/signals/<TICKER>.json` (already present for CN names, e.g.
`site/signals/000001.SZ.json`) is fed from real range instead of reconstructed range.
**Do not change `SCHEMA.json` or the §7 contract** — only the upstream price quality
improves.

---

## 5. Proof-of-concept

Committed alongside this doc:
- [`multicountry_poc.py`](multicountry_poc.py) — read-only probe (writes no store)
- [`multicountry_poc_output.txt`](multicountry_poc_output.txt) — captured run

Confirmed results (run 2026-06-27, EOD through 2026-06-26):

```
yfinance (auto_adjust=False -> O/H/L/C/V + Adj Close; HIGH/LOW present):
  0700.HK    : 5438 rows, 2004-06-16 -> 2026-06-26   high/low=True
  600519.SS  : 6109 rows, 2001-08-27 -> 2026-06-26   high/low=True
  000001.SZ  : 8887 rows, 1991-01-02 -> 2026-06-26   high/low=True   (deepest)
  .SS/.SZ/.HK suffix MATCHES data/china store -> no remapping

akshare (Eastmoney; 开盘/收盘/最高/最低/成交量; HIGH/LOW present):
  A  600519 (Moutai SH)  qfq: 5948 rows, 2001-08-27 -> 2026-06-26   high/low=True
  A  000001 (Ping An SZ) qfq: 8423 rows, 1991-04-03 -> 2026-06-26   high/low=True
  HK 00700 (Tencent)     qfq: 5427 rows, 2004-06-16 -> 2026-06-26   high/low=True

GOTCHAS confirmed:
  - akshare A-share volume in 手: 000001 = 1,236,482 手  (x100 -> 123,648,164 shares)
  - akshare qfq NEGATIVE on multi-bagger: 600519 first close raw 35.55 vs qfq -312.47
    -> use hfq/raw for split-consistent positive series
```

**This is the REAL fix.** A separate session shipped a close-only **High/Low
RECONSTRUCTION** stopgap ([[ohlc-reconstruction]], `engine/ohlc_reconstruct.py`,
`RANGE_MULT=2.0`) because the existing CN/HK index stores carry close+volume only.
That stopgap synthesizes a plausible range to keep the engine running; it is **not**
real intraday range. The PoC shows real daily High/Low are available for free, for
every name, back 20–35 years. Adopting this source **replaces reconstruction with
real range** for CN/HK per-name signals — the reconstruction layer stays only as a
fallback for names with no per-ticker pull.

---

## 6. Open questions for the owner

1. **Tushare HK entitlement (uncertain in research).** Verified that `hk_daily` is
   NOT in the ¥500/5000-point tier and lists a separate ¥1,000/yr permission — but we
   did **not** verify the exact entitlement on *your* account. Since the recommendation
   is to NOT use Tushare for OHLC at all, this only matters if you want to override and
   make Tushare the licensed primary. Decision: confirm you are fine **not** paying the
   HK surcharge and keeping Tushare for fundamentals only?
2. **Licensing posture for the SaaS.** yfinance is legally gray; the defensible line is
   **publish derived signals only, never raw Yahoo OHLC**. Confirm the product serves
   signals/markers/scores (not downloadable bars). If/when revenue justifies it, swap
   in a licensed feed (ICE / LSEG / Polygon international) to erase ToS exposure — your
   call on the trigger.
3. **Point-in-time immutability.** Should the per-name store be **append-only with
   immutable historical bars** (protects walk-forward re-runs from silent Yahoo
   revisions), or accept best-effort revisions on each incremental pull? This is a
   one-time design choice with downstream consequences for the harness.
4. **429 failure policy.** Acceptable nightly-CI behavior on a Yahoo 429: (a)
   retry-with-backoff then **partial success + alert**, or (b) **hard-fail the run**?
   The collector design depends on this answer.
5. **akshare fallback aggressiveness.** Default proposed trigger is `<0.5×` prior row
   count or `0` rows → single-name akshare `hfq` pull. Tighten, loosen, or disable the
   automatic fallback?
6. **Universe scope & cadence.** Build the store for exactly the 110 CN + 24 HK in the
   current `latest.json` snapshots, or seed deeper history for a wider universe up front
   (cheaper to backfill once than to chase later)?
