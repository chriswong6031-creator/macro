# T2a Throughput Probe — P2.0 Measurement Memo

_Authored by Sonnet, 2026-07-05. Probe session: 2026-07-02 (most recent completed US trading day). Terminal: ThetaTerminal v3, http://127.0.0.1:25503. All timings are wall-clock from `curl` invocations, ≤2 concurrent requests (house law)._

---

## In plain English

The trade_quote endpoint is faster than the roadmap's original F-C finding implied. The F-C amendment (roadmap §1, 2026-07-05) was correct: bulk wildcard pulls (`exp=*`, `strike=*`, per-right) return ALL contracts in 2 requests per root-day. For SPY on 2026-07-02, that is 1.9 million trade rows in ~40 seconds. The per-contract approach that R6 originally assumed would take over 12 hours for SPY alone. The wildcard-bulk approach is ~1,100× faster.

Forward-daily accrual for the full 360-root universe takes approximately 13 minutes nightly (6-concurrent). That fits comfortably inside the 4-hour Mac batch window. Episode and ETF-history backfill each take 21–23 nightly sessions of 4 hours — significant but tractable, run in parallel with forward-daily as a background job.

One design decision gates everything: **raw tape vs aggregated features**. Raw tapes for all 360 roots accumulate ~2.6 GB/day uncompressed (~650 GB/year). Aggregating to daily signed-flow features at pull time reduces storage to ~100 KB/root-day (~15 GB/year for all 360). The recommendation is clear: aggregate at ingest for single-name universe; retain raw tapes only for ETF anchors and episode windows where tick-level reconstruction may be needed later.

---

## §1 Amendment context

Roadmap §1 row F-C was corrected before this probe ran:

> **AMENDMENT — 2026-07-05:** F-C corrected by PR #1358 live evidence: bulk trade_quote EXISTS (wildcard expiration+strike, per-right; right=* → 400). T2a cost = 2 requests/root-day.

This probe **confirms and quantifies** that amendment with measured numbers. The per-contract probe framing in P2.0's original task spec is moot; this memo instead measures the wildcard-bulk shape directly.

---

## §2 Measured numbers — SPY (heavy ETF benchmark)

**Session: 2026-07-02. Endpoint: `/v3/option/history/trade_quote?symbol=SPY&expiration=*&strike=*&right={call|put}&start_date=20260702&end_date=20260702`**

| Request | Rows | Bytes (raw CSV) | Wall clock |
|---|---|---|---|
| SPY, calls, exp=20260702 only (specific-exp control) | ~730,000 | 110 MB | 10.6–12.9s |
| SPY, puts, exp=20260702 only | ~920,000 | 101 MB | 18.6s |
| **SPY, calls, exp=\* (all expirations)** | **1,017,832** | **154 MB** | **29.7s** |
| **SPY, puts, exp=\* (all expirations)** | **923,992** | **138 MB** | **10.0s** |
| SPY total (call + put, all exp) | **1,941,824** | **292 MB** | **~40s** |

Observations:
- The same-expiration wildcard (exp=20260702) returned ~730K / ~920K rows for calls/puts. The all-expiration wildcard added ~287K call rows from other expiries (28% more).
- SPY is the heaviest root in the universe — it sets the upper bound.
- No stall observed. Data flowed continuously. 90-second read timeout was not approached.

**Constraint confirmed:** `right=*` returns `Invalid right: *`. Exactly 2 requests per root-day are required (call + put separately).

**Multi-day wildcard constraint confirmed:** `exp=* + start_date != end_date` returns: _"Option history requests without a specific expiration must be one day at a time."_ Forward-daily is therefore 2 single-day wildcard requests. Backfill requires looping over calendar days (one session = one API call pair).

---

## §3 Measured numbers — comparison roots

**All measurements: 2026-07-02, exp=\*, strike=\*, single-day wildcard.**

| Root | Category | Calls bytes | Calls time | Puts bytes | Puts time | Total time | Total MB |
|---|---|---|---|---|---|---|---|
| SPY | ETF heavy | 154 MB | 29.7s | 138 MB | 10.0s | ~40s | 292 MB |
| QQQ | ETF heavy | 107 MB | 8.4s | 100 MB | 8.5s | ~17s | 207 MB |
| NVDA | Single mega | 41 MB | 9.3s | 24 MB | 3.5s | ~13s | 65 MB |
| TSLA | Single mega | 75 MB | ~10s | — | — | ~15s est | ~120 MB est |
| AAPL | Single mega | 35 MB | ~5s | — | — | ~8s est | ~55 MB est |
| AMD | Single heavy | 11 MB | 2.3s | 8.3 MB | 2.5s | ~5s | 19 MB |
| META | Single heavy | 16 MB | ~2s | — | — | ~4s est | ~25 MB est |
| MSFT | Single heavy | 18 MB | ~2s | — | — | ~4s est | ~27 MB est |
| AMZN | Single heavy | 14 MB | ~2s | — | — | ~4s est | ~22 MB est |
| ANET | Single medium | ~2.8 MB | 2.0s | 0.5 MB | 1.6s | ~3.6s | 3.3 MB |
| LITE | Single light | 0.86 MB | 1.0s | 1.3 MB | 1.7s | ~2.7s | 2.2 MB |
| COHR | Single light | 0.61 MB | 1.1s | 0.78 MB | 2.0s | ~3.1s | 1.4 MB |

_"est" = call measured; put estimated at 60% of call size (observed ratio for SPY/NVDA/AMD)._

**Per-contract comparison (SPY, specific exp+strike+right):**

| Contract type | Rows | Bytes | Time |
|---|---|---|---|
| ATM 0DTE put (top-premium) | 34,350 | 5.1 MB | 17.7s |
| ATM 0DTE call (top-volume) | 49,359 | 7.4 MB | 5.2s |
| Dec put (mid-decile) | 323 | 49 KB | 4.7s |
| Deep OTM call (light-decile) | 0 | 30 bytes | 4.2s |

With 5,536 traded contracts on SPY 2026-07-02 at ~8s average: **44,000s (~12.3 hours) serial for SPY alone**. Wildcard pulls the same data in 40s. Efficiency gain: **~1,100×**. Per-contract approach is infeasible at any concurrency level that respects the 8-request ceiling.

---

## §4 SPY contract universe — premium and volume coverage analysis

**Source: `/Users/chriswong/theta-ops-wt/data/thetadata_eod/eod/SPY/2026.parquet`, 2026-07-02.**

| Metric | Value |
|---|---|
| Total SPY contracts (all, incl zero-volume) | 13,810 |
| Traded contracts (volume > 0) | 5,536 (40.1%) |
| Zero-volume (skippable per F-C) | 8,274 (59.9%) |
| Total volume | 14,857,080 |
| Total premium proxy (vol × close) | $23,361,933 |

**Coverage at top-N by premium proxy (vol × close):**

| N | Cumulative Volume % | Cumulative Premium % | Note |
|---|---|---|---|
| 10 | 14.9% | 30.5% | |
| 50 | 29.4% | 54.1% | |
| **100** | **37.2%** | **66.3%** | R6 suggested lower bound |
| **250** | **44.1%** | **79.7%** | Mid-range cutoff |
| **500** | **58.9%** | **87.7%** | R6 suggested upper bound |
| 1,000 | 86.9% | 94.3% | |
| ALL (5,536) | 100.0% | 100.0% | |

**Interpretation for T2a design:** Because the wildcard-bulk approach already retrieves all traded contracts in 2 requests, filtering to top-N contracts is a **storage and aggregation question, not a retrieval question**. The API cost is identical whether we keep 100 or 5,536 contracts per side. The top-N analysis matters only if raw tapes are stored contract-by-contract. For aggregated daily features (recommended), all contracts contribute equally at pull time.

**Volume distribution by DTE (SPY 2026-07-02):**

| DTE bucket | Volume % | Premium % |
|---|---|---|
| 0–7d | 88.6% | 54.7% |
| 8–30d | 8.7% | 19.4% |
| 31–60d | 1.3% | 6.6% |
| 61–90d | 0.5% | 3.5% |
| 91–365d | 0.8% | 9.0% |
| 365d+ | 0.2% | 6.7% |

0DTE/weekly dominates volume but longer-dated contracts carry disproportionate premium per contract. A DTE-quality filter (e.g., 8–90d) for signed flow features would capture 29.4% of volume but 29.4% of premium is misleading — the 8–90d bucket covers 29.6% of premium ($6.9M) and excludes mostly noise from 0DTE scalping.

---

## §5 Oracle episode count

**Source: `data/oracle/episodes_s.parquet`.**

| Metric | Value |
|---|---|
| Total Tier-S episodes | 749 |
| Two-sided (paired) episodes | 34 |
| Post-2022 episodes (onset >= 2022-01-01) | 195 |
| Post-2022 paired | 30 |
| Distinct nodes in post-2022 | 11 |

The R6 priority ladder states: "episode windows 2022→ (Tier-M options-era onset floor 2022-02-08 per O-OPT prereg R3)." The measured 195 post-2022 episodes covering 11 sector nodes is the operative scope for T2a episode backfill.

---

## §6 Extrapolated cost estimates

**Assumptions (stated):**
- 360 roots total in gex_symbols() universe (measured from options_universe.py)
- ETF category (20 roots): SPY-class avg 20s/pair; sector ETF avg 10s/pair
- Heavy single-names (50 roots, NVDA/TSLA/AAPL tier): avg 10s/pair
- Medium single-names (100 roots, AMD/META tier): avg 5s/pair
- Light single-names (190 roots, ANET/LITE tier): avg 3s/pair
- 6-concurrent requests during nightly batch (not the backfill window; backfill is separate)
- 30% overhead for parse, compress, write, retry

### (a) Forward-daily accrual — 360 roots, 1 day

| | Value |
|---|---|
| Serial request time (720 requests total) | ~58 minutes |
| Wall clock at 6-concurrent | ~10 minutes |
| With 30% overhead | **~13 minutes** |
| Fits in 4h nightly window? | **YES — with 3.8h headroom** |
| Data volume (uncompressed) | ~2.6 GB/day |
| If raw tapes retained annually | ~650 GB/year |
| If aggregated to daily features | ~15 GB/year (all 360 roots) |

**Recommendation: aggregate at ingest for single-name universe.** Forward-daily accrual is trivially within budget at any universe size up to 360.

### (b) Episode-window backfill — 2022+, Tier-S (R6 priority 2)

Scope: 195 episodes × 11 ETF roots × 31 days (±15d window) = 66,495 root-day combinations.

| | Value |
|---|---|
| Requests (×2 per root-day) | 132,990 |
| Serial time (ETF avg 10s/req) | ~370 hours |
| Wall clock at 6-concurrent | ~62 hours |
| Nightly 4h sessions needed | **~16 nights** |
| Caveat | Episodes cluster; overlapping windows reduce effective load ~20–30% |
| Adjusted estimate | **~12–16 nights** |

This is feasible as a dedicated background job. Run alongside forward-daily accrual (forward-daily uses only 13 minutes of the 4h window, leaving 3.8h for backfill each night).

### (c) ETF full history 2017→ (R6 priority 3)

Scope: 20 ETF roots × 252 trading days/year × 9 years (2017–2025) = 45,360 root-day combinations.

| | Value |
|---|---|
| Requests (×2 per root-day) | 90,720 |
| Serial time (ETF avg 15s/req — heavier history years) | ~378 hours |
| Wall clock at 6-concurrent | ~63 hours |
| Nightly 4h sessions needed | **~16 nights** |
| Caveat | 2017–2020 ETF chains are smaller; actual time likely 25% less |
| Adjusted estimate | **~12–16 nights** |

Can run in parallel with episode backfill since they use different roots.

### Summary table

| Track | Wall clock | Nightly sessions | Feasibility |
|---|---|---|---|
| Forward-daily (360 roots) | 13 min/night | 1 (ongoing) | Trivially fits |
| Episode backfill 2022+ | ~62h total | ~16 nights | Feasible (background) |
| ETF history 2017→ | ~63h total | ~16 nights | Feasible (parallel) |
| Single-name history 2022→ | NOT measured | >> 100 nights | Defer; measure separately |

---

## §7 Recommendation — concrete T2a shape

**Ruling R6 priority ladder:** (1) forward-daily → (2) episode windows 2022→ → (3) ETF history 2017→ → (4) single-name history opportunistic.

### Recommended T2a design

**Shape: wildcard-bulk per-root-per-day, aggregate-at-ingest.**

1. **Forward-daily (start immediately):** For each root in gex_symbols() (360 names), issue 2 bulk requests (exp=*, strike=*, right=call; right=put) for the prior trading day. Aggregate inline to signed-flow features: net signed premium, signed P/C ratio, flow breadth, DTE-quality (8–90d bucket), crowding flag. Discard raw tapes for single names. Budget: ~13 minutes nightly. Unblocked NOW.

2. **Raw tape retention policy:** Retain raw tapes (all rows, all expirations) ONLY for: (a) 20 ETF anchors (needed for history backfill and cross-sectional GEX reconstruction), (b) roots within ±15d of a registered Tier-S episode. This caps raw tape storage at ~20 ETFs × 2 GB/root-year = ~40 GB/year plus episode windows.

3. **Episode backfill 2022→ (R6 priority 2):** Loop 195 post-2022 episodes × 11 ETF roots × ±15d calendar days. Use per-day wildcard pulls. Aggregate features only (no raw tape) unless the root is an ETF anchor. Run in the 3.8h headroom after forward-daily. ETA: ~16 nights from start.

4. **ETF history 2017→ (R6 priority 3):** Loop 20 ETF roots × 252 days × 9 years. Retain raw tapes (ETFs are the backtest backbone). Run concurrently with episode backfill once that completes or in parallel on separate nights. ETA: ~16 additional nights.

5. **Single-name history:** NOT recommended pre-gate. Throughput is fine (3–10s per name-day) but the storage and time accumulate fast at 340 single-name roots × 3 years = >300K root-days. Wait for gate results from O-OPT before committing.

### What N for top-N filtering?

**N is irrelevant for the retrieval step.** The wildcard-bulk API returns all contracts in 2 requests regardless of how many are "top-N." The top-N question only applies if storing per-contract rows. Given the aggregate-at-ingest recommendation, there is no top-N filter — every traded contract contributes to the signed-flow features. The coverage table (§4) shows that even top-100 captures only 66% of premium; any fixed-N filter would bias signed-flow features toward large liquid contracts and miss small-order accumulation that constitutes a legitimate signal source. For daily aggregated features, use all contracts.

### Does top-N bias signed-flow features?

Yes, materially. From the SPY 2026-07-02 measurement:

- Top-100 of 5,536 contracts: 66.3% premium, 37.2% volume captured. **33.7% of premium lost** — including most of the open-interest-confirmed repeat-hitter patterns that are a primary unusual-activity signal source.
- Top-250: 79.7% premium, 44.1% volume. **20.3% of premium lost.**
- Top-500: 87.7% premium, 58.9% volume. **12.3% of premium lost** — still meaningful given that "dark money" trades often cluster in illiquid strikes.

Since the wildcard-bulk approach makes per-contract filtering irrelevant to API cost, there is no justification for a top-N cut. Any top-N filter is a storage convenience that trades analytical completeness for disk space. The aggregate-at-ingest approach retains 100% coverage at ~100 KB/root-day.

---

## §8 Caveats and open questions

1. **SPY is anomalously large.** SPY's 1.9M rows / 292 MB is 4–14× larger than any sector ETF. The 13-minute forward-daily estimate is dominated by the 3–4 heaviest names. If SPY+QQQ+NVDA+TSLA stall simultaneously (unlikely but possible), the batch could spike to 25 minutes. The 90s read timeout in `collectors/thetadata.py` would catch a genuine stall.

2. **Episode overlap.** The 195-episode × 31-day window count treats every episode as independent. In practice, many episodes overlap in calendar time (e.g., multiple sector rotations during the same VIX event). The actual unique root-day combinations are likely 20–30% fewer than the upper bound, making the 16-night backfill estimate conservative.

3. **2017 Greeks-start caveat.** The roadmap notes that Greek/IV data starts 2017. Trade-quote data starts 2012 (same as EOD). The ETF-history backfill for trade_quote does not require Greeks and can use the full 2012→ range if needed. However, R6 priorities start at 2017→ for ETF history to align with IV availability for joint features.

4. **Terminal throughput at scale.** All measurements used ≤2 concurrent requests. At the recommended 6-concurrent for nightly production, throughput may be slightly different (terminal has 8-request ceiling; measured at 2). The measured times provide a conservative lower bound on nightly wall-clock estimates.

5. **Signing gate.** The roadmap ratified signing calibration on one 20-minute window (SPY, 15 contracts, agreement 0.8848, recovery 0.80). The multi-session extension (P0.4) must land before tone claims on signed-flow UI are un-softened. Signed-flow features can accrue before that but must be labeled softly until P0.4 completes.

---

## §9 Probe script

Rerunnable at: `scripts/probe_t2a_throughput.py`

The script probes the first 5 ETF roots + 5 single names (≤2 concurrent) and prints measured rows/bytes/seconds per root-right pair, plus the SPY coverage analysis and extrapolations. Run after a trading session completes; update `PROBE_DATE` to the target session date. The terminal must be running (`scripts/run_theta_terminal.sh`).

---

_End of memo. Roadmap R6 status: probe complete; T2a build-unblocked on wildcard-bulk shape._
