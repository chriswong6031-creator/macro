# Dead-Name Price Spike — W1 PR-G Feasibility Memo

**Wave:** W1 PR-G  
**Status:** COMPLETE — feasibility verdict reached  
**Date:** 2026-07-06  
**Program:** Long-Hold Thesis Layer (`research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`)  
**Target file:** `data/edgar/dead_name_prices.parquet`  
**Probe results:** `research/long_hold/dead_name_probe_results.json`

---

## Context

`grading.py` already implements the full dead-name architecture (`resolve_series`, `terminal_state`, `load_dead_prices`). The file `data/edgar/dead_name_prices.parquet` is absent; current coverage is 15/1,083 names (1.39%). The OBJECTIVE.md §8 pre-registration notes that the honest OOS window for 252d labels collapses to ~3.5 months of 2021 fires; this memo investigates whether ThetaData v3 or Polygon can fill the price gap.

**Dead universe:** 1,083 names. Source: `data/edgar/_dead_name_coverage.json`. Era breakdown from `data/breadth/sp1500_pit_membership.parquet`:

| Era | Count | Notes |
|---|---|---|
| pre-2012 | 333 | Exited before 2012-01-01 |
| 2012 – 2021-07-05 | 332 | Exited before Polygon rolling anchor |
| post-2021-07-06 | **418** | Full Polygon REST coverage |

---

## Source 1: ThetaData v3

**Terminal:** running on `http://127.0.0.1:25503` (confirmed reachable).

**Probe method:** direct REST calls against the `/v3/stock/history/eod` endpoint with symbol=ATVI, start/end dates spanning delisting window.

**Finding:** The ThetaData terminal holds a **PROFESSIONAL options subscription** and a **FREE stock subscription**. The symbol list (`/v3/stock/list/symbols`) enumerates ~26,000 symbols including dead names (ATVI, TWTR, CERN, XLNX confirmed present). However, all attempts to fetch stock EOD history return:

```
"Requesting stock history requiring a VALUE subscription, but you only have a FREE 
subscription. Please consider upgrading!"
```

(Phrasing varies by date range: `VALUE` for close history, `STANDARD` for recent, `PROFESSIONAL` for pre-2012-06 range.)

**Conclusion:**

| Question | Answer |
|---|---|
| Does ThetaData serve delisted-name EOD? | Yes — if a stock subscription is held |
| Does our current account have a stock subscription? | No — FREE tier only |
| Can we use ThetaData for dead-name price recovery now? | **No** |
| Upgrade cost estimate | ~$60/mo (Standard) to $240+/mo (Professional + historical); separate from options subscription |

ThetaData is a future option if the stock subscription is purchased. The terminal already knows all the dead tickers. **Not usable under current budget.**

---

## Source 2: Polygon REST API (massive.com subscription)

**Subscription:** active paid US stocks REST entitlement (confirmed from `MASSIVE_API_KEY`).

**Rolling window:** The subscription enforces a rolling 5-year data entitlement. Confirmed boundary: **2021-07-06 is the first accessible day**. Requests for any date before 2021-07-05 return `NOT_AUTHORIZED`.

**Probe results (5 dead names):**

| Ticker | Delist Date | Polygon REST result | Date range served |
|---|---|---|---|
| ATVI | 2023-10-16 | OK, 573 bars | 2021-07-05 → 2023-10-11 |
| TWTR | 2022-10-27 | OK, 333 bars | 2021-07-05 → 2022-10-26 |
| CERN | 2022-06-07 | OK, 234 bars | 2021-07-05 → 2022-06-06 |
| XLNX | 2022-02-14 | OK, 155 bars | 2021-07-05 → 2022-02-11 |
| Y (Yellow Corp) | 2022-10-18 | OK, 326 bars | 2021-07-05 → 2022-10-17 |
| WFM (control — 2017 delist) | 2017-08-29 | NOT_AUTHORIZED | — |

**Reference/tickers endpoint:** enumerates delisted names with `active=false` and `delisted_utc` dates. Contains CIK, FIGI, exchange. Useful for building a complete dead-name index.

**Flat files (S3):** `us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`. Years 2003–2026 are listed in the bucket but files before 2021-07-06 return 403 Forbidden (same rolling entitlement applies). Post-anchor files are accessible (~200KB each, ~10,500 tickers per day). Format is **unadjusted** close. REST adjusted aggregates are preferred for dead-name price recovery (Polygon handles split/dividend adjustment at query time).

**Coverage estimate by era:**

| Era | Names | Polygon REST coverage | Notes |
|---|---|---|---|
| pre-2012 | 333 | **0%** | All pre-anchor; NOT_AUTHORIZED |
| 2012 – 2021-07-05 | 332 | **0%** | All pre-anchor; NOT_AUTHORIZED |
| post-2021-07-06 | **418** | **~95%+** | All names traded after anchor; REST serves adjusted EOD through delist date |

The post-anchor coverage rate is estimated at ~95% because a small fraction of tickers may have data quality gaps (de-facto OTC after delisting, name collisions with reuse). The 5 probe names all returned clean data.

---

## Source 3: Stooq (free fallback)

**URL pattern:** `https://stooq.com/q/d/l/?s={ticker}.us&i=d`

**From this Mac IP:** The IP is blocked. All `.us` symbol queries return an HTML "page does not exist" wrapper (HTTP 200 body, content = "The page you requested does not exist or has been moved"). The JS PoW challenge seen in earlier curl attempts was a transient; the consistent result is a 200 HTML block page.

**From CI IPs:** The existing `edgar_deadname_prices.py` collector documents this as "HTML-blocks some IPs, reachable from CI." This has not been re-verified in this probe session; it is stated in the code comment as observed behavior. If true from CI, Stooq provides:

- Deep history going back 10–20 years for many US equities including delisted acquisitions
- Unadjusted close (acceptable for sector-relative return computation at scale)
- No API key required
- Free, but fragile (IP blocking, potential page changes)
- Skewed toward acquisitions: names acquired at a premium have clean price history; bankruptcies where price → 0 are under-served

**Coverage estimate by era if CI-accessible:**

| Era | Names | Stooq coverage (estimated) | Notes |
|---|---|---|---|
| pre-2012 | 333 | 20–40% | Acquisition tickers survive; bankruptcies largely absent |
| 2012 – 2021-07-05 | 332 | 50–70% | Higher acquisition fraction; most large-cap acquisitions covered |
| post-2021-07-06 | 418 | 70–85% | Redundant with Polygon; Stooq used as fallback |

These estimates are based on the `edgar_deadname_prices.py` author's characterization ("skews to ACQUISITIONS") and general Stooq US coverage knowledge. The existing collector already implements Stooq as primary source and falls back to Polygon. **No new build work needed for Stooq; it runs if CI IP is unblocked.**

---

## Coverage Estimate vs 1,083-Name Universe, By Era

Using Polygon REST (post-2021-07-06) + Stooq from CI (pre-2021, estimated):

| Era | N | Polygon REST | + Stooq (if CI accessible) | Cumulative |
|---|---|---|---|---|
| post-2021-07-06 | 418 | ~400 (~95%) | — | **~400/418** |
| 2012 – 2021-07-05 | 332 | 0 | +165–230 (50–70%) | **~165–230/332** |
| pre-2012 | 333 | 0 | +67–133 (20–40%) | **~67–133/333** |
| **Total** | **1,083** | **~400** | **~632–763** | **~58–70%** |

Without Stooq (Polygon only): coverage = ~400/1,083 (**37%**), all in post-anchor era.

With Stooq from CI: coverage = ~632–763/1,083 (**58–70%**). The pre-2012 cohort remains the hardest; those names have thin Stooq coverage and are entirely outside the Polygon window.

---

## Build Cost Estimate

### Recommended approach: Polygon REST for post-anchor names

The `edgar_deadname_prices.py` collector already implements the Polygon path (`_polygon_daily`). The only gap is that it queries via `POLYGON_API_KEY` env variable; the active key is `MASSIVE_API_KEY`. The fix is a one-line env variable alias in the collector or a wrapper.

| Step | Work | Cost |
|---|---|---|
| Env alias: `POLYGON_API_KEY = MASSIVE_API_KEY` in CI env | 1 line | 5 min |
| Run `fetch_dead_prices(tickers=post_anchor_418, max_new=418)` | Existing collector | 418 REST calls |
| Wall time at 2 req/sec | ~3.5 minutes | n/a |
| Wall time at 5 req/sec | ~1.5 minutes | n/a |
| Data volume | ~25 MB JSON → parquet | ~3 MB parquet |

For the minimum needed for G1 honest-cohort (140 dead tickers in the honest OOS window):
- 140 REST calls, ~70 seconds at 2 req/sec
- Can be done as a pre-G1 targeted sub-run

### Pre-existing Stooq path (no new code)

The existing collector runs `Stooq → Polygon → yfinance` in order. If CI IP is unblocked, running the collector on the full 1,083-name universe in CI will accrue Stooq results for pre-anchor names automatically. Run time: ~7 minutes for 1,083 names at the 0.4s Stooq rate-limit sleep already in the code.

---

## Recommended Build Plan

**Phase 1 (unblocks G1 kill test, ~1 day work):**

1. In the nightly CI/workflow environment, set `POLYGON_API_KEY=$(MASSIVE_API_KEY)` (one-line secret alias in `factor_ops.yml` or the dead-name collect step).
2. Run the existing `collectors/edgar_deadname_prices.py:fetch_dead_prices(max_new=150)` from CI. This picks up the 418 post-anchor names via Polygon.
3. After 3 runs (~450 names each capped at 150), the full post-anchor cohort is covered.
4. The G1 label harness (`long_hold_label_panel.py`) can then resolve 252d labels for the honest OOS window (2021-07-06 → 2021-10-25) with zero survivorship gap for those 140 dead name fires.

**Phase 2 (pre-2021 coverage, longer runway):**

5. Verify Stooq accessibility from the self-hosted CI runner with a test probe (1 dead ticker, check for CSV response vs HTML block).
6. If accessible: run `fetch_dead_prices(max_new=500)` from CI over multiple nights (the collector is already resumable; `_dead_name_prices_seen.json` tracks completed tickers).
7. Target ~60% overall coverage. The bankruptcy tail (price → 0) is partially corrected by the existing `edgar_delisting` bankruptcy imputation path (already in `collectors/edgar_delisting.py`).

**No new collector code is needed.** The build plan uses only existing infrastructure; the gap is environment configuration (key alias) and execution scheduling.

---

## Honest Verdict: Does Dead-Name Coverage Unblock G1?

### The honest-OOS episode-cluster count (§6.3 floor)

The honest OOS window for 252d labels is 2021-07-06 → 2021-10-25 (~3.5 months). This window contains:

- **3,331 total fires** across 1,957 unique tickers
- **235 fires from dead names** (140 unique dead tickers)
- All 140 dead tickers fired AFTER the Polygon anchor → Polygon REST serves their full 252d price window (252d after 2021-10-25 = ~2022-10-25, well within Polygon coverage)

The episode-cluster n-floor (§6.3): n ≥ 25 independent clusters. With 1,957 unique tickers in the window, even at a 10% extraction rate through tactical-win + 252d-maturity + dedup, the estimated cluster count is ~330. **The n=25 floor clears easily from the live-name cohort alone, independent of dead names.**

Dead names are not the determinant of whether the floor clears. Their contribution is qualitative: they populate the `cheap_trap` and `tactical_only_fail` cells that pure survivor data systematically underpopulates.

### Survivorship bias impact without dead names

Without dead-name prices:
- The `cheap_trap` label is systematically underrepresented (names that fired and then declined to zero or were distressed delistings are invisible)
- The `compounder` label is over-represented (names that fired and then got acquired at a premium look like compounders)
- This biases the `missed_hold` vs `tactical_only` contrast TOWARD finding a signal (acquisition premiums look like quality)
- A false positive in G1 is the primary risk

With Polygon REST covering the post-anchor dead names (418 names, ~140 in the honest OOS window): this bias is substantially corrected for the OOS period. Pre-2021 bias remains in the fit-period exploration, but the OOS verdict is the binding one.

### Era-by-era verdict

| Era | Honest cohort status | With recommended build | Notes |
|---|---|---|---|
| pre-2012 | UNREACHABLE (no surviving price source at scale) | **No change** | Polygon blocked; Stooq coverage < 40%. Pre-2012 results remain `survivorship_biased=True` regardless. These are not in the OOS split. |
| 2012 – 2021-07-05 | UNREACHABLE for most names | **Partial recovery via Stooq from CI** (50–70% est.) | Fit-period data only. Results stamped UPPER BOUND. |
| post-2021-07-06 | Largely reachable with Polygon | **~95% coverage (~400/418 names)** | Covers the honest OOS window and post-anchor fit data. |

### Horizon-by-horizon verdict

| Horizon | Status after build |
|---|---|
| 126d | **Viable** — even without dead names, 126d maturity after 2021-07-06 fires is fully within any price source's range |
| 252d | **Viable for OOS** — Polygon covers 252d windows for all post-anchor dead name fires |
| 504d | **Caveat-stamped** — post-anchor only; 504d after 2021-07-06 = 2023-07 onwards; Polygon serves this but survivorship bias caveat required |
| 756d | **REFUSED** (per OBJECTIVE.md §3) — 756d gate requires ≥50% dead-name coverage of the full 1,083-name universe. With Polygon-only coverage at 37%, this gate CANNOT be met. With Stooq addition reaching ~60-70%, the gate CANNOT be met either (short of 50%). The 756d horizon remains refused. |

**756d gate calculation:** OBJECTIVE.md requires ≥50% dead-name coverage (≥542/1,083 names) before 756d results may be published. Polygon REST provides ~400/1,083 (37%); Polygon + Stooq provides ~632–763/1,083 (58–70%). The 756d gate is technically meetable IF Stooq from CI delivers the upper end of estimates. However, this is not confirmed without a live CI probe. Do not treat 756d as unblocked until coverage is measured on actual data.

### G1 kill test can proceed now (with one caveat)

The G1 kill test on the honest OOS cohort (252d horizon, 2021-07-06 → 2021-10-25 fires) is structurally runnable:

1. The live-name cohort provides enough episode-cluster n (n >> 25) with existing price stores.
2. Dead-name prices for the honest OOS window (~140 tickers) are available via Polygon REST with ~1 day of build work (environment key alias + one collector run).
3. Without dead-name prices, the test can still run but the `cheap_trap` cell is survivor-biased; if it returns a null, the null must be marked "coverage-sensitive" per OBJECTIVE.md §8. With dead-name prices, the null is clean.

**Recommendation:** run the Polygon collector pass (Phase 1, ~1 day) before running the G1 label harness. The build cost is low, the structural work already exists, and it eliminates the survivorship-deferral caveat from the OOS verdict.

---

## Deviations and Caveats

1. **Stooq IP block from Mac:** Not re-verified from CI. The existing collector comment states it works from CI; treat as likely but unconfirmed. Before running the pre-2021 Stooq pass, add a 1-ticker probe in the CI job to confirm accessibility.

2. **Stooq quality:** Unadjusted prices. For names with stock splits before delisting (uncommon but present), sector-relative returns will carry a small upward bias. At the scale of this analysis, this is acceptable but must be noted in the coverage stamp.

3. **Polygon adjusted flag:** The REST endpoint with `adjusted=true` handles pre-delist splits and dividends. This is confirmed for the probe names. The `_polygon_daily` function in `edgar_deadname_prices.py` already uses `adjusted=true`.

4. **Acquisition skew persists:** Even with dead-name prices, acquisition targets (price ran to deal price) are over-represented vs genuine bankruptcies. The existing `edgar_delisting` bankruptcy imputation (Ch.11 8-K Item 1.03 → imputed −100% terminal) partially corrects this. The residual bias must remain stamped on any pre-registration analysis.

5. **Rolling window is rolling:** The Polygon 5-year window moves forward each day. Today (2026-07-06) the anchor is 2021-07-06. In one year it will be 2022-07-06, losing the first year of post-anchor dead names from the REST window. **Build this data store now, not later.** Names that delisted in 2021-07-06 → 2022-07-05 (35 in the universe) will be unreachable via REST within 12 months.

---

## Summary

| Source | Era coverage | Status |
|---|---|---|
| ThetaData v3 | All eras (2012+) if subscribed | NOT USABLE — FREE stock subscription only; requires ~$60–240/mo upgrade |
| Polygon REST (`MASSIVE_API_KEY`) | post-2021-07-06 only | **PRIMARY SOURCE** — ~418 names (~95%); 140/140 needed for OOS window; 1–3 days build |
| Polygon flat files S3 | post-2021-07-06 (same window) | Redundant with REST; unadjusted; not recommended |
| Stooq (from CI) | pre-2021 (partial) | **SECONDARY SOURCE** — unverified from CI, ~50–70% if accessible; no new code needed |
| yfinance | ~0% delisted | NOT USABLE |

**For the G1 kill test (OOS 252d honest cohort):** Polygon REST + MASSIVE_API_KEY env alias unblocks the test in ~1 day. Pre-2012 and 2012–2021 eras remain survivorship-biased in the fit period but do not gate the OOS verdict.

**For the 756d gate:** Not cleared by Polygon alone (37% vs 50% threshold). May be cleared if Stooq CI coverage is confirmed at the upper estimate; not recommended to assume this until measured.
