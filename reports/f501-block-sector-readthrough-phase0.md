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
| V1 (≤−8%) | basket | 2,920 | 1,773 |
| V1 (≤−8%) | SW-L1 | 12,045 | 3,229 |
| V2 (≤−15%) | basket | 594 | 472 |

**V1 basket clusters per year:**

```
  2013: 33
  2014: 52
  2015: 90
  2016: 161
  2017: 131
  2018: 113
  2019: 193
  2020: 381
  2021: 433
  2022: 278
  2023: 367
  2024: 293
  2025: 255
  2026: 140
```

**V2 basket clusters per year:**

```
  2019: 4
  2020: 10
  2021: 100
  2022: 111
  2023: 144
  2024: 145
  2025: 60
  2026: 20
```

**Top 5 most-event baskets (V1, 21d):**
```
group_name
cn_consumer_elec    609
cn_battery          582
cn_software         370
cn_med_devices      312
cn_ai_compute       291
```

---

## Results: gated cells (excess vs CSI 300 ETF, AM-1 market proxy)

| Cell | N dates | Mean excess | t_HAC | p | BH q | Dir<0 | Gate |
|------|---------|------------|-------|---|------|-------|------|
| B-V1-21d | 1754 | 0.0526 | 8.476 | 0.0000 | 0.0000 | N | FAIL |
| B-V1-63d | 1721 | 0.0710 | 8.727 | 0.0000 | 0.0000 | N | FAIL |
| B-V2-21d | 462 | 0.0147 | 1.544 | 0.1232 | 0.1232 | N | FAIL |
| B-V2-63d | 458 | 0.0437 | 2.720 | 0.0068 | 0.0081 | N | FAIL |
| SW-V1-21d | 3206 | 0.1117 | 21.182 | 0.0000 | 0.0000 | N | FAIL |
| SW-V1-63d | 3164 | 0.1332 | 23.514 | 0.0000 | 0.0000 | N | FAIL |

*N dates = calendar-time collapsed observations (one per event date).
Stats law: NW HAC, lag = min(4, sqrt(N)). BH correction across 6 gated cells.*

**Note on market proxy bias:** CSI 300 is cap-weighted large-cap; peer baskets are
equal-weight small/mid-cap. The positive excess above is substantially a benchmark-mismatch
artifact (persistent size drift). The own-group baseline below nets this out.

### Results: own-group unconditional baseline (spec OUTCOME baseline b)

Excess vs the unconditional equal-weight mean return of the same peer group
across ALL available dates (non-event and event). This baseline captures the
persistent size/composition drift that inflates the CSI-300-excess above.

| Cell | N dates | Mean vs own-group | t_HAC | p | Dir<0 |
|------|---------|------------------|-------|---|-------|
| B-V1-OG-21d | 1754 | 0.0364 | 5.084 | 0.0000 | — | N | FAIL |
| B-V1-OG-63d | 1721 | 0.0119 | 1.225 | 0.2206 | — | N | FAIL |
| B-V2-OG-21d | 462 | -0.0092 | -0.704 | 0.4819 | — | Y | FAIL |
| B-V2-OG-63d | 458 | -0.0400 | -1.929 | 0.0544 | — | Y | FAIL |
| SW-V1-OG-21d | 3206 | 0.0996 | 17.745 | 0.0000 | — | N | FAIL |
| SW-V1-OG-63d | 3164 | 0.0962 | 14.804 | 0.0000 | — | N | FAIL |

*OG = own-group unconditional baseline. BH correction not applied to informational rows;
gate verdict is G1 on CSI-300-excess cells (the primary pre-registered control).*

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

G4 details: excluded 'cn_consumer_elec' (609 cluster events); remaining mean excess = 0.0605; N dates after = 1504.

---

## PIT laws and amendments

- **AM-1 (market proxy):** CSI 300 ETF (510300.SS). NOTE: docstring said 'CN-A market EW'; amendment
  AM-1 filed before computing to use CSI 300 ETF (510300.SS) instead. CSI 300 is
  cap-weighted large-cap; see own-group baseline above for the size-drift-corrected view.
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

- V1 basket events with <2 peers (excluded per AM-2): 19 of 1773 unique event dates
- SW-L1 coverage limited to 5/31 codes — robustness cells are honest partial coverage
- V3 (unlock-driven variant) not gated — forward-accrual registered above
- Pre-2013 block tape excluded (< 15 names/day, insufficient cross-section)

---

*Report generated 2026-07-07. Numbers verified against harness output.*
