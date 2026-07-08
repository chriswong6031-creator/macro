# F5-01 CN Block-Discount Sector Read-Through — Phase-0

**Family:** `f501_cn_block_sector_readthrough`  **Lane:** LG-CN-SUPPLY (reclaimed after d2_cn_holder_sale_calendar directional fail)
**Date:** 2026-07-07  **Status:** NULL

---

## In plain English

> When multiple large shareholders of companies within the same sector all accept
> below-market prices to offload their holdings on the same block-trade platform
> (大宗交易), it could signal that insiders are pessimistic about that sector's
> near-term prospects. This test asks: when two or more stocks in the same
> curated basket print deep discounts on block trades within a 10-session window,
> do the *other* stocks in that basket subsequently underperform the market?
> The hypothesis is 'yes — informed-holder pessimism spreads to peers'.
> A PASS means we see that sector-contagion effect in the data; a NULL means
> the evidence does not support the claim at the pre-registered bar.

---

## Pre-registered design

**Event:** ≥2 distinct names in the same sector-group printing deep-discount blocks
(avg_premium_pct ≤ −8%; V2 DEEP variant ≤ −15%) within a trailing 10-session window.
Event date = day the 2nd name qualifies. Availability = event_date + 1 trading day.

**Outcome:** Forward 21d and 63d equal-weight returns of NON-blocked peers
in the same group, excess vs CSI 300 ETF (510300.SS).

**Primary sector grouping:** data/baskets_china/membership.json (22 curated baskets).
**Robustness grouping:** SW-L1 (5/31 codes: Agriculture/Chemicals/Steel/Nonferrous/Electronics).

**V3 (unlock-driven) status: FORWARD-ACCRUAL ONLY — not gated this run.**
akshare `stock_restricted_release_detail_em` covers 2022-12-02→2024-12-02 only.
Historical broad unlock calendar is not available from probed endpoints.
V3 gates are frozen here; execution requires matured nightly unlock store.

---

## Data coverage

| Dimension | Count |
|-----------|-------|
| Block tape rows (2013-2026) | 165,025 |
| Block tape date range | 2013-01-04 → 2026-07-06 |
| Unique tickers in block tape | 5,116 |
| Basket tickers (incl removed) | 280 |
| Basket tickers in block tape | 122 (43.6%) |
| SW-L1 tickers in block tape | 1109 (5/31 codes) |
| Market proxy | CSI 300 ETF (510300.SS) |

**Per-basket coverage (tickers appearing in block tape at least once, 2013+):**

| Basket | Total members | In block tape |
|--------|---------------|---------------|
| cn_ai_compute | 17 | 10 |
| cn_appliances | 8 | 4 |
| cn_autos | 16 | 6 |
| cn_baijiu | 7 | 4 |
| cn_banks | 18 | 2 |
| cn_battery | 16 | 14 |
| cn_brokers | 15 | 5 |
| cn_coal | 10 | 1 |
| cn_consumer_elec | 15 | 14 |
| cn_defense | 13 | 6 |
| cn_food_bev | 10 | 4 |
| cn_gold | 6 | 2 |
| cn_insurers | 5 | 0 |
| cn_med_devices | 14 | 8 |
| cn_metals | 13 | 7 |
| cn_pharma_cxo | 14 | 4 |
| cn_rare_earth | 9 | 5 |
| cn_robotics | 11 | 7 |
| cn_semis | 22 | 5 |
| cn_soe_value | 16 | 0 |
| cn_software | 15 | 9 |
| cn_solar | 15 | 6 |

**SW-L1 coverage:** 5 of 31 codes served by Shenwan API (801010 Agriculture,
801030 Chemicals, 801040 Steel, 801050 Nonferrous Metals, 801080 Electronics).
Remaining 26 codes return HTML (not JSON) from Shenwan — upstream API gap
verified live 2026-07-07. SW grouping is a robustness check only.

---

## Cluster counts

| Variant | Group type | Cluster events | Unique event dates |
|---------|------------|---------------|-------------------|
| V1 (≤−8%) | basket | 8,253 | 2,833 |
| V1 (≤−8%) | SW-L1 | 14,338 | 3,253 |
| V2 (≤−15%) | basket | 8,160 | 2,830 |

**V1 basket clusters per year:**

```
  2013: 275
  2014: 315
  2015: 379
  2016: 454
  2017: 610
  2018: 379
  2019: 389
  2020: 927
  2021: 1081
  2022: 809
  2023: 942
  2024: 718
  2025: 586
  2026: 389
```

**V2 basket clusters per year:**

```
  2013: 275
  2014: 315
  2015: 372
  2016: 439
  2017: 607
  2018: 369
  2019: 389
  2020: 927
  2021: 1073
  2022: 787
  2023: 923
  2024: 717
  2025: 586
  2026: 381
```

**Top 5 most-event baskets (V1, 21d):**
```
group_name
cn_consumer_elec    1640
cn_battery          1372
cn_med_devices       732
cn_software          722
cn_ai_compute        641
```

---

## Results: gated cells

| Cell | N dates | Mean excess | t_HAC | p | BH q | Dir<0 | Gate |
|------|---------|------------|-------|---|------|-------|------|
| B-V1-21d | 2810 | 0.1012 | 13.794 | 0.0000 | 0.0000 | N | FAIL |
| B-V1-63d | 2768 | 0.1153 | 14.496 | 0.0000 | 0.0000 | N | FAIL |
| B-V2-21d | 2807 | 0.1017 | 13.810 | 0.0000 | 0.0000 | N | FAIL |
| B-V2-63d | 2765 | 0.1154 | 14.451 | 0.0000 | 0.0000 | N | FAIL |
| SW-V1-21d | 3230 | 0.1061 | 21.605 | 0.0000 | 0.0000 | N | FAIL |
| SW-V1-63d | 3188 | 0.1259 | 23.861 | 0.0000 | 0.0000 | N | FAIL |

*N dates = calendar-time collapsed observations (one per event date).
Stats law: NW HAC, lag = min(4, sqrt(N)). BH correction across 6 gated cells.*

---

## Gate summary

| Gate | Criterion | Result |
|------|-----------|--------|
| G1 | Direction<0 AND \|t_HAC\|≥2 AND BH q≤0.10 on B-V1-21d | FAIL |
| G2 | Split-half same-sign (pre/post 2020-01-01) | FAIL |
| G3 | LOCO: 2015-crash same-sign | FAIL |
| G3 | LOCO: 2018-bear same-sign | FAIL |
| G3 | LOCO: 2024-stimulus same-sign | FAIL |
| G4 | Read-through survives excl. most-clustered basket (cn_consumer_elec) | FAIL |

**VERDICT: NULL**

G4 details: excluded 'cn_consumer_elec' (1640 cluster events); remaining mean excess = 0.1093; N dates after = 2540.

---

## PIT laws and amendments

- **AM-1 (market proxy):** CSI 300 ETF (510300.SS) (CSI 300 ETF, covers 2012-05+)
- **AM-2 (minimum peers):** events with <2 non-blocked peers with valid price data excluded
- **AM-3 (session window):** 10 trailing block-tape sessions (not calendar days)
- **AM-4 (PIT basket membership):** basket 'added' date used; removed date excludes tickers
- **AM-5 (multi-basket tickers):** tickers in multiple baskets counted in each
- **AM-6 (overlap correction):** date-collapsed portfolios for both 21d and 63d cells
- **AM-7 (SW matching):** 6-digit prefix match between block tape tickers and SW constituents

Signal availability lag: event_date + 1 trading day (block data publishes T+0 evening / T+1).
Returns measured from close of (event_date + 1 td).

---

## V3 registration (forward-accrual only)

V3 (unlock-driven clusters: ≥1 blocked name with unlock within ±30 days) is registered
here with frozen gates. It is NOT gated in this run because:

- `stock_restricted_release_detail_em` (live probe 2026-07-07): covers 2022-12-02→2024-12-02 only
- `stock_restricted_release_summary_em` with start_date/end_date: raises TypeError (NoneType)
- `stock_restricted_release_queue_em`: per-stock only, not cross-sectional
- `stock_restricted_release_queue_sina`: per-stock, would require batch scrape of 5,000+ tickers

The nightly `china_unlocks` store (`data/china_unlocks/detail.parquet`) currently covers
2026-06 forward. V3 gates identical to V1/V2 (G1-G4) will be applied when the store
matures to ≥3 years (earliest executable: 2029-07 with current data). Per docket §F5-01,
V3 is the red-team preferred variant — V1/V2 are the available-now approximation.

---

## Null accounting

- V1 basket events with <2 peers (excluded per AM-2): 23 of 2833 unique event dates
- SW-L1 coverage limited to 5/31 codes — robustness cells are honest partial coverage
- V3 (unlock-driven variant) not gated — forward-accrual registered above
- Pre-2013 block tape excluded (< 15 names/day, insufficient cross-section)

---

*Report generated 2026-07-07. Numbers verified against harness output.*
