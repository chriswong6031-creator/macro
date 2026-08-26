# X competitive intelligence — weekly report

Generated 2026-08-23T22:12:06Z by `engine/marketing/x_intel.py` (schema `marketing.x_intel_report/v1`).
2029 original posts from 17 accounts inside a 90-day window (2029 in the corpus all-time).

Every number here is arithmetic over observed counters — no model scored anything (LLM-never-scores law). A post with no view count is EXCLUDED from rate denominators (`n_no_views`), never folded in as a zero. A row under the n-floor of 12 is marked *(seeding)* and makes no ranking claim.

## By shape (our vocabulary)

| shape | n | no-views | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|---|
| `one_liner` | 1161 | 1 | 51,785 | 179 | 0.00358 | 0.00027 |
| `stack` | 501 | 0 | 123,499 | 409 | 0.00510 | 0.00041 |
| `two_part` | 226 | 0 | 55,031 | 240 | 0.00568 | 0.00036 |
| `caption` | 102 | 0 | 50,666 | 366 | 0.00783 | 0.00051 |
| `list` | 39 | 0 | 174,122 | 625 | 0.00462 | 0.00044 |

## By register

| register | n | no-views | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|---|
| wire | 1005 | 1 | 97,348 | 187 | 0.00265 | 0.00022 |
| aggregator | 622 | 0 | 110,024 | 814 | 0.00790 | 0.00075 |
| trader | 224 | 0 | 48,110 | 176 | 0.00487 | 0.00021 |
| commentary | 129 | 0 | 13,429 | 49.5 | 0.00481 | 0.00053 |
| macro_color | 49 | 0 | 24,691 | 78 | 0.00372 | 0.00048 |

## By account

| account | n | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|
| @FirstSquawk | 379 | 18,762 | 14 | 0.00112 | 0.00017 |
| @unusual_whales | 362 | 127,497 | 534 | 0.00534 | 0.00029 |
| @Barchart | 265 | 64,899 | 605 | 0.00966 | 0.00102 |
| @DeItaone | 264 | 138,850 | 344 | 0.00313 | 0.00024 |
| @KobeissiLetter | 239 | 288,562 | 2,270 | 0.00793 | 0.00075 |
| @StockMKTNewz | 59 | 35,853 | 113 | 0.00379 | 0.00021 |
| @wallstengine | 59 | 27,458 | 101 | 0.00399 | 0.00035 |
| @Mr_Derivatives | 56 | 41,974 | 198 | 0.00633 | 0.00023 |
| @bespokeinvest | 52 | 8,380 | 11 | 0.00172 | 0.00024 |
| @PeterLBrandt | 49 | 54,994 | 267 | 0.00491 | 0.00023 |
| @alphatrends | 44 | 26,758 | 134 | 0.00579 | 0.00026 |
| @RyanDetrick | 43 | 14,873 | 105 | 0.00794 | 0.00044 |
| @traderstewie | 40 | 38,584 | 95 | 0.00302 | 0.00012 |
| @LizAnnSonders | 39 | 23,539 | 66 | 0.00357 | 0.00055 |
| @markminervini | 35 | 108,869 | 538 | 0.00430 | 0.00015 |
| @charliebilello | 34 | 36,852 | 288 | 0.00893 | 0.00102 |
| @jam_croissant *(seeding)* | 10 | 42,165 | 228 | 0.00594 | 0.00033 |

## Shape distribution vs our quotas

| shape | corpus share |
|---|---|
| `caption` | 5.0% |
| `list` | 1.9% |
| `one_liner` | 57.2% |
| `stack` | 24.7% |
| `two_part` | 11.1% |

- `one_liner` — ours (min) 25.0% vs corpus 57.2%. corpus share of single-content-line posts vs our floor
- `two_part` — ours (max) 30.0% vs corpus 11.1%. corpus share of two-content-line posts vs our ceiling

## Precision + signature rates

| metric | rate |
|---|---|
| decimal strict rate | 7.2% |
| decimal any rate | 17.7% |
| bare int rate | 63.4% |
| has number rate | 67.1% |
| cashtag rate | 19.2% |
| starts cashtag rate | 2.9% |
| all caps lead rate | 50.7% |
| emoji rate | 16.4% |
| url rate | 35.3% |
| blank spacer rate | 35.3% |
| quote rate | 8.3% |

> strict decimal is the docket's \d+\.\d\d (4.75); any-decimal also catches the far more common single-decimal percent (4.7%). The gap between them IS the finding — see the docket's key finding #2.

## Week-over-week

Prior snapshot 2026-08-09 (969 posts).

| metric | was | now | delta |
|---|---|---|---|
| all caps lead rate | 43.6% | 50.7% | +0.0702 |
| bare int rate | 62.7% | 63.4% | +0.0068 |
| blank spacer rate | 36.8% | 35.3% | -0.0155 |
| cashtag rate | 19.7% | 19.2% | -0.0049 |
| decimal any rate | 16.5% | 17.7% | +0.0118 |
| decimal strict rate | 5.6% | 7.2% | +0.0167 |
| emoji rate | 15.5% | 16.4% | +0.0088 |
| has number rate | 67.0% | 67.1% | +0.0010 |
| quote rate | 10.3% | 8.3% | -0.0204 |
| starts cashtag rate | 3.5% | 2.9% | -0.0060 |
| url rate | 38.1% | 35.3% | -0.0274 |

| shape | was | now | delta |
|---|---|---|---|
| `caption` | 5.3% | 5.0% | -0.0023 |
| `list` | 2.0% | 1.9% | -0.0004 |
| `one_liner` | 54.2% | 57.2% | +0.0304 |
| `stack` | 25.1% | 24.7% | -0.0039 |
| `two_part` | 13.5% | 11.1% | -0.0238 |

