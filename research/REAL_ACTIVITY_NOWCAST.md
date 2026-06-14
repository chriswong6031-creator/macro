# High-Frequency Real-Activity Nowcast

**Status:** BUILT + verified (collectors live, wired to the conditions nowcast).
**Scope decision:** Tier 1 + Tier 2 of the Augur-Infinity-style real-activity board.
Collect + wire to the `engine/conditions.py` nowcast snapshot **only** — NOT into the
recession/drawdown SCORE (which feeds the macro-risk overlay) until separately validated.

## Motivation
The dashboard was deep on price / financial-conditions / survey data but thin on
**high-frequency hard real-activity**. The only labor reads were `PAYEMS` / `INDPRO`
— both monthly and revised. These additions give a real-time labor + income leg that
**leads the monthly, revised payrolls**, plus a quant news-sentiment series.

## Sources (all free / keyless)
| Series | Store | Source | Cadence | Notes |
|---|---|---|---|---|
| Initial claims | `fred/ICSA` | FRED | weekly | leading labor signal |
| Initial claims 4wk MA | `fred/IC4WSA` | FRED | weekly | the smoothed trend read |
| Continued claims | `fred/CCSA` | FRED | weekly | insured unemployment (confirms) |
| Indeed job postings | `fred/IHLIDXUS` | FRED (Indeed Hiring Lab) | ~weekly | labor **demand**; Feb-1-2020=100 |
| Indeed NEW postings | `fred/IHLIDXNEWUS` | FRED | ~weekly | the more-leading variant |
| Withheld income tax | `treasury/withheld_taxes` | Treasury DTS Table II | daily | wage/income FLOW ($mn); coverage from **2023-02** |
| News sentiment | `frbsf/news_sentiment` | SF Fed | daily | lexical economic sentiment, history from 1980 |

- **DTS endpoint:** `/v1/accounting/dts/deposits_withdrawals_operating_cash`,
  `transaction_type=Deposits`, `transaction_catg="Taxes - Withheld Individual/FICA"`.
  The unified deposits table only carries this category from **2023-02** onward — enough
  for a trailing-3m YoY. Self-backfills the first time it is collected.
- **SF Fed:** `news_sentiment_data.xlsx`, `Data` sheet `(date, News Sentiment)`.

## ⚠️ Licensing caveat — Indeed
The Indeed Hiring Lab series (`IHLIDXUS` / `IHLIDXNEWUS`) are **copyrighted**; FRED
states pre-approval is required to USE/redistribute them. Pulled here for **private
dashboard use only — do not publish**. They are deliberately excluded from the ALFRED
point-in-time vintage matrix (also because they re-revise their whole history on each
methodology change, like the NFCI family).

## Derived reads (`engine/conditions.py`)
- **Claims:** YoY of the 4wk-MA level (rising = cooling) + a 3y rolling z.
- **Indeed:** 3-month % change of the postings index (falling = demand softening).
- **Withheld taxes:** a FLOW — summed over a trailing ~3m of ACTUAL deposit days, then
  YoY of that sum (**never forward-filled**, which would double-count). Nominal.
- **News sentiment:** level + 1y rolling z; surfaced in `risk_appetite`, NOT folded into
  the `roro` composite (keeps that gauge stable until validated).
- **Synthesis:** a 3-vote `labor_nowcast.read` → "labor cooling" / "firm" / "mixed".

## Why nowcast-only (not scoring)
`recession_risk` and `drawdown_risk` feed the macro-risk overlay (`MRS` → sector heat +
per-stock ladder). House discipline (AQR-null / DSR; see `INSTITUTIONAL_GRADE_ROADMAP`)
is to validate before any new leg touches a scoring path. These legs are additive display
columns; a future, separately-validated step can fold claims into the recession composite
(the plumbing — config-gated weights — is the natural extension point).

## Verification
- 16 conditions/collector tests green (full suite 338 passed, 0 fail).
- Live fetch confirmed for all 7 series; live read (2026-06): claims 219k falling
  (−9.6% YoY), withheld income +3.4% YoY → "labor firm"; Indeed −3.3%/3m; news tone
  slightly pessimistic near its 1y mean.

## Skipped (Tier 3/4)
TSA throughput (free scrape, noisy) and OpenTable (dashboard scrape, YoY-only, citation)
were deferred. Augur "Timely Growth/Inflation" composites are proprietary (we already have
WEI+GDPNow and sticky/flex/median CPI equivalents); Redbook is paywalled; Box Office is
negligible macro signal.
