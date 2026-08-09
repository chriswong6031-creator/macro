# X competitive intelligence — weekly report

Generated 2026-08-09T22:20:21Z by `engine/marketing/x_intel.py` (schema `marketing.x_intel_report/v1`).
969 original posts from 17 accounts inside a 90-day window (969 in the corpus all-time).

Every number here is arithmetic over observed counters — no model scored anything (LLM-never-scores law). A post with no view count is EXCLUDED from rate denominators (`n_no_views`), never folded in as a zero. A row under the n-floor of 12 is marked *(seeding)* and makes no ranking claim.

## By shape (our vocabulary)

| shape | n | no-views | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|---|
| `one_liner` | 525 | 1 | 48,186 | 164 | 0.00368 | 0.00027 |
| `stack` | 243 | 0 | 106,787 | 370 | 0.00533 | 0.00044 |
| `two_part` | 131 | 0 | 46,315 | 216 | 0.00578 | 0.00034 |
| `caption` | 51 | 0 | 62,623 | 381 | 0.00791 | 0.00057 |
| `list` | 19 | 0 | 255,114 | 1,857 | 0.00565 | 0.00047 |

## By register

| register | n | no-views | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|---|
| wire | 422 | 1 | 99,958 | 197 | 0.00279 | 0.00023 |
| aggregator | 282 | 0 | 89,504 | 646 | 0.00741 | 0.00068 |
| trader | 150 | 0 | 49,517 | 194 | 0.00490 | 0.00021 |
| commentary | 89 | 0 | 13,563 | 75 | 0.00533 | 0.00076 |
| macro_color | 26 | 0 | 26,628 | 86.5 | 0.00439 | 0.00052 |

## By account

| account | n | med views | med likes | med interaction/view | med repost/view |
|---|---|---|---|---|---|
| @FirstSquawk | 160 | 20,545 | 14 | 0.00106 | 0.00017 |
| @unusual_whales | 146 | 139,775 | 652 | 0.00552 | 0.00030 |
| @DeItaone | 116 | 142,920 | 381 | 0.00348 | 0.00025 |
| @Barchart | 105 | 72,040 | 605 | 0.00893 | 0.00088 |
| @KobeissiLetter | 99 | 292,767 | 2,590 | 0.00836 | 0.00075 |
| @StockMKTNewz | 39 | 33,292 | 118 | 0.00452 | 0.00022 |
| @wallstengine | 39 | 24,770 | 92 | 0.00421 | 0.00035 |
| @Mr_Derivatives | 38 | 43,425 | 194 | 0.00621 | 0.00028 |
| @bespokeinvest | 34 | 8,100 | 11.5 | 0.00190 | 0.00031 |
| @PeterLBrandt | 33 | 55,166 | 327 | 0.00635 | 0.00022 |
| @RyanDetrick | 30 | 14,588 | 160 | 0.01308 | 0.00096 |
| @traderstewie | 29 | 41,669 | 97 | 0.00303 | 0.00012 |
| @markminervini | 26 | 116,462 | 548 | 0.00456 | 0.00017 |
| @charliebilello | 25 | 32,786 | 227 | 0.00890 | 0.00101 |
| @alphatrends | 24 | 26,758 | 131 | 0.00563 | 0.00028 |
| @LizAnnSonders | 20 | 24,754 | 78.5 | 0.00400 | 0.00057 |
| @jam_croissant *(seeding)* | 6 | 43,768 | 262 | 0.00694 | 0.00043 |

## Shape distribution vs our quotas

| shape | corpus share |
|---|---|
| `caption` | 5.3% |
| `list` | 2.0% |
| `one_liner` | 54.2% |
| `stack` | 25.1% |
| `two_part` | 13.5% |

- `one_liner` — ours (min) 25.0% vs corpus 54.2%. corpus share of single-content-line posts vs our floor
- `two_part` — ours (max) 30.0% vs corpus 13.5%. corpus share of two-content-line posts vs our ceiling

## Precision + signature rates

| metric | rate |
|---|---|
| decimal strict rate | 5.6% |
| decimal any rate | 16.5% |
| bare int rate | 62.7% |
| has number rate | 67.0% |
| cashtag rate | 19.7% |
| starts cashtag rate | 3.5% |
| all caps lead rate | 43.6% |
| emoji rate | 15.5% |
| url rate | 38.1% |
| blank spacer rate | 36.8% |
| quote rate | 10.3% |

> strict decimal is the docket's \d+\.\d\d (4.75); any-decimal also catches the far more common single-decimal percent (4.7%). The gap between them IS the finding — see the docket's key finding #2.

## Week-over-week

Prior snapshot 2026-07-31 (295 posts).

| metric | was | now | delta |
|---|---|---|---|
| all caps lead rate | 38.6% | 43.6% | +0.0501 |
| bare int rate | 70.9% | 62.7% | -0.0810 |
| blank spacer rate | 42.7% | 36.8% | -0.0587 |
| cashtag rate | 25.8% | 19.7% | -0.0605 |
| decimal any rate | 15.2% | 16.5% | +0.0126 |
| decimal strict rate | 5.8% | 5.6% | -0.0019 |
| emoji rate | 16.3% | 15.5% | -0.0079 |
| has number rate | 74.9% | 67.0% | -0.0794 |
| quote rate | 13.2% | 10.3% | -0.0290 |
| starts cashtag rate | 5.1% | 3.5% | -0.0157 |
| url rate | 50.8% | 38.1% | -0.1277 |

| shape | was | now | delta |
|---|---|---|---|
| `caption` | 6.8% | 5.3% | -0.0152 |
| `list` | 1.7% | 2.0% | +0.0027 |
| `one_liner` | 43.4% | 54.2% | +0.1079 |
| `stack` | 28.1% | 25.1% | -0.0306 |
| `two_part` | 20.0% | 13.5% | -0.0648 |

