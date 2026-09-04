# Global Liquidity Data Census — W-LIQ.1

**Date:** 2026-08-22

**Commission:** Mastermind issue #118, under architecture #117 and orchestration #123

**Repository:** Macro (`mastermindx-market-intelligence/macro`)

**Boundary:** inventory and state producer only; no UI, shock registry, transmission curve, repricing gap, alert, trade, or allocation authority.

## Verdict

Macro already owns enough data to produce a conservative three-central-bank
monetary state and a separate USD-funding impulse without adding a collector.
It does **not** own enough comparable, release-stamped global credit data to
publish an honest `credit_impulse_global` scalar. The v1 contract therefore
publishes that field as explicit `null` with its reason and exposes US and China
credit directions separately as context.

The canonical W-LIQ.1 monetary basket is Fed + ECB + BoJ balance-sheet assets,
USD-converted from existing FRED/Yahoo stores. The canonical funding basket is
the broad trade-weighted dollar + 10-year real yield + HY OAS. The existing US
WALCL−RRP−TGA classifier remains the source of truth for US liquidity quality;
this producer consumes it and does not re-derive or replace it.

## Existing ownership and fitness

| Family | Canonical repository asset | Coverage in the 2026-08-22 checkout | Timing / revision finding | W-LIQ.1 disposition |
|---|---|---:|---|---|
| Fed total assets | `data/fred/WALCL.parquet` | 2002-12-18 → 2026-08-19, weekly | Wednesday observation, conservative +1 business-day availability; low revision risk | **Use** in monetary state |
| ECB total assets | `data/fred/ECBASSETSW.parquet` | 1999-01-01 → 2026-08-14, weekly | Conservative +2 business-day availability; repository has no full vintage history | **Use**, medium revision-risk disclosure |
| BoJ total assets | `data/fred/JPNASSETS.parquet` | 1998-04-01 → 2026-07-01, monthly | FRED label is the first of the month but the statistic is end-of-period; month-end anchor +2 business days is load-bearing | **Use** only after corrected month-end anchoring |
| Fed/ECB/BoJ FX | `data/yahoo/EURUSD_X.parquet`, `USDJPY_X.parquet` through 2026-08-21 | Daily | Last close on or before the economic reference date | **Use** for USD conversion |
| Existing CB aggregate | `engine/global_liquidity.py` | Current snapshot logic | Useful display context, but treats the BoJ provider label as its economic date and therefore makes monthly as-of/FX alignment too early | Reuse sources, **not** its date kernel |
| US broad money | `data/fred/M2SL.parquet` plus `data/fred_vintage/vintages.parquet` | 1959 → 2026-06; initial-release archive from 1996-12 | Monthly, initial releases available for the archived interval | Retain as research/context; not mixed with CB assets in v1 |
| China broad money | `data/china_macro/money_supply.parquet` | 2008 → 2026-07 | EastMoney period dates; no release timestamp or vintage lineage | **Exclude** from causal state |
| Discontinued international M2 | `data/fred/EZ_m2.parquet`, `JP_m2.parquet`, `KR_m2.parquet`, `GB_m2.parquet` | Mostly stop in 2017; GB stops 2023-11 | Explicitly removed/discontinued in config | **Do not revive** |
| US bank credit | `data/fred/BUSLOANS.parquet` and FRED vintage archive | 1947 → 2026-07; initial-release archive from 1996-12 | Monthly; not economically comparable to China TSF | Separate current context only |
| China credit | `data/china_credit/tsf.parquet` | 2015 → 2026-07 | Direct PBoC; explicit conservative `availability_date`, with canonical level/acceleration transforms in `engine.canon` | Separate PIT context only |
| BIS credit / DSR / credit gap | existing BIS parquets | Quarterly through 2025Q4 | Structural/final data; repository does not record vintage/release timestamps | **Exclude** from causal global scalar |
| Fed net liquidity / Treasury plumbing | `data/macro/fed_net_liquidity.parquet`, `data/regime/latest.json.liquidity_quality` | Daily composite through 2026-08-21 | Canonical WALCL−RRP−TGA quantity and composition; already handles RRP exhaustion/mechanical moves | **Consume unchanged** as US quality |
| Broad dollar | `data/fred/DTWEXBGS.parquet` | 2006-01-02 → 2026-08-14, daily business | Conservative +1 business day, low revision risk | **Use** in funding basket, inverse sign |
| 10Y real yield | `data/fred/DFII10.parquet` | 2003-01-02 → 2026-08-20, daily | Conservative +1 business day, low revision risk | **Use** in funding basket, inverse sign |
| HY OAS | `data/fred/BAMLH0A0HYM2.parquet` | 1996-12-31 → 2026-08-20, daily | Repo append-only history preserves observations beyond the provider rolling window | **Use** in funding basket, inverse sign |
| NFCI / ANFCI | existing FRED parquets | 1971 → 2026-08-14, weekly | Full histories revise on release; absent from the FRED vintage archive | **Exclude** from causal state |
| HK / CN funding | HKMA aggregate balance/HIBOR, SHIBOR, CNH futures | Daily, varying starts | Useful jurisdiction context, not a homogeneous global funding factor | Leave for a later specified extension |
| BoE / SNB / PBoC total assets | no adequate canonical total-assets feed | — | Existing BoE SONIA and Swiss rate/FX stores are funding context, not balance sheets; no clean keyless PBoC total-assets series | Explicitly omitted |

## Full source-by-source census receipt

“Not frozen” below is an adverse finding: the repository has a current series
but not enough release/vintage evidence to claim a causal lag. It is not silently
treated as same-day. “Publication” describes the pre-W-LIQ.1 state; no source had
a standalone GLT/R2 artifact before this commission.

| Source / canonical owner | Provider | Frequency; earliest usable / latest | Release and freshness semantics | PIT / revision grade | Existing publication / v1 decision |
|---|---|---|---|---|---|
| `data/fred/WALCL.parquet` (`collectors.fred`, Fed assets) | Federal Reserve Board via FRED | weekly; 2002-12-18 / 2026-08-19 | Wed reference, +1BD, stale >10 calendar days | lag-aligned, low revision risk | Existing CB display + regime inputs; **v1 monetary** |
| `data/fred/WRESBAL.parquet` (reserve balances) | Federal Reserve Board via FRED | weekly; 2002-12-18 / 2026-08-19 | Wed reference, +1BD if causally reused | lag-aligned, low revision risk | Existing macro input, no separate GLT/R2; census context only because WALCL already represents the Fed balance-sheet leg |
| `data/fred/RRPONTSYD.parquet` and deeper `data/nyfed/rrp.parquet` | New York Fed / FRED | daily; 2003-02-07 (NY Fed operation store 2013-04-02) / 2026-08-21 | daily facility observation; canonical quality plane owns current lag/staleness | append-only repo history, low revision risk | Existing net-liquidity/regime/site consumers; **reuse only through US quality** |
| `data/treasury/tga.parquet` and `data/macro/fed_net_liquidity.parquet` | U.S. Treasury Fiscal Data + canonical Macro composer | daily; 2005-10-03 / 2026-08-20 (composite through 2026-08-21) | collector date; exact upstream intraday release not frozen; composite meta names each component tip and 10BD guard | no full vintage store; current composition is canonical | `data/regime/latest.json.liquidity_quality`; **consume unchanged** |
| `data/fred/ECBASSETSW.parquet` (`collectors.fred`) | ECB via FRED | weekly; 1999-01-01 / 2026-08-14 | +2BD, stale >12 days | lag-aligned but full vintage absent; medium risk | Existing CB display, no GLT/R2; **v1 monetary** |
| `data/fred/JPNASSETS.parquet` (`collectors.fred`) | BoJ via FRED | monthly EOP; 1998-04-01 / 2026-07-01 provider label | relabel to month-end, +2BD, stale >45 days | lag-aligned but full vintage absent; medium risk | Existing CB display has early-label landmine; **v1 monetary with corrected clock** |
| `data/china_pboc/fx_reserves.parquet` | PBoC official macro release | monthly; 2008-01 / 2026-07 | period date; release timestamp not stored | not vintage-safe; revision/clock risk medium-high | Existing China context; **not a PBoC balance-sheet substitute** |
| `data/china_omo/operations.parquet` | PBoC public OMO bulletins | event/daily; current archive | bulletin observation clocks, event-specific | first-seen event tape, but not total assets | Existing China context; outside v1 scalar |
| no adequate BoE total-assets store; `data/fred/IUDSOIA.parquet` is SONIA | Bank of England via FRED | daily SONIA; 1997-01-02 / 2026-08-19 | market/reference rate, not a balance sheet | low revision for the rate; wrong construct | Existing rates context; **BoE balance sheet missing** |
| no adequate SNB total-assets store; `IR3TIB01CHM156N` + `DEXSZUS` are rate/FX | OECD/FRED and Federal Reserve FX | monthly rate from 1999-07; daily FX from 1971 | observation dates, not balance-sheet release | rate/FX histories only | Existing FX/rates context; **SNB balance sheet missing** |
| `data/fred/M2SL.parquet` + `data/fred_vintage/vintages.parquet` | Federal Reserve Board / ALFRED | monthly; 1959-01 / 2026-06; initial releases from 1996-12 | exact initial-release archive where present | PIT-capable on archived interval | Existing regime/BTC broad-money context; kept separate from CB-assets v1 |
| `data/china_macro/money_supply.parquet` | EastMoney aggregation of official China macro data | monthly; 2008-01 / 2026-07 | period date only; release/first-known absent | not PIT safe; revision risk unbounded | Existing China/BTC context; **excluded from causal state** |
| `EZ_m2`, `JP_m2`, `KR_m2`, `GB_m2` legacy FRED parquets | former FRED/OECD feeds | monthly; mostly end 2017, GB ends 2023-11 | discontinued/stale by years | unsuitable | Explicit config removals; **do not revive** |
| `data/fred/BUSLOANS.parquet` + FRED vintage archive | Federal Reserve Board / ALFRED | monthly; 1947-01 / 2026-07; initial releases from 1996-12 | monthly release; initial-release rows usable where archived | PIT-capable only on archived interval | Existing macro context; separate US credit direction, not global scalar |
| `data/china_credit/tsf.parquet` (`collectors.china_credit`) | PBoC direct | monthly; 2015-01 / 2026-07 | explicit conservative `availability_date` (month M usable day 16 of M+1) | PIT-aligned at stored first availability; later revision risk remains | Existing China credit engines/site; canonical transforms reused for separate context |
| `data/bis/{us,cn}_gap.parquet`, `{us,cn}_dsr.parquet` | BIS | quarterly; gaps US 1957Q4/CN 1995Q4, DSR 1999Q1; all latest 2025Q4 | repository records period end, not original release/vintage timestamp | final/structural history; not PIT safe | Existing structural context; **excluded from causal global credit** |
| `data/fred/BAMLH0A0HYM2.parquet` | ICE BofA via FRED + repo archive | daily; 1996-12-31 / 2026-08-20 | +1BD, stale >7 days | append-only preserved history; low revision risk | Existing regime/credit consumers; **v1 USD funding** |
| `data/fred/BAMLC0A0CM.parquet` | ICE BofA via FRED | daily store only 2023-04-24 / 2026-08-20 | +1BD if reused | low revision but upstream rolling window left shallow repo history | Existing IG context; excluded from v1 composite because deep comparison is not homogeneous |
| `data/fred/NFCI.parquet`, `ANFCI.parquet` | Chicago Fed via FRED | weekly; 1971-01-08 / 2026-08-14 | weekly; existing research applies one-week lag | full history revises each release; absent from vintage archive | Existing conditions/regime context; **excluded from causal state** |
| `data/fred/DTWEXBGS.parquet` | Federal Reserve Board via FRED | daily business; 2006-01-02 / 2026-08-14 | +1BD, stale >10 days | lag-aligned, low revision risk | Existing FX/macro consumers; **v1 USD funding, inverse 13-week log change** |
| nominal curves (`DGS2/5/10/20/30`, `T10Y2Y`) and `DFII10` | U.S. Treasury / Federal Reserve via FRED | daily; `DFII10` 2003-01-02 / 2026-08-20 | +1BD, stale >7 days for v1 real-yield leg | low revision risk | Existing rates/transmission surfaces; **DFII10 only in v1 funding**, nominal curve stays context |
| `data/yahoo/CNH_F.parquet`, `CNH_X.parquet`, `data/fred/DEXCHUS.parquet` | Yahoo / Federal Reserve | daily; futures 2013-02-11 / 2026-08-21, spot cache only 20 rows in current checkout | market-close clocks; CNH spot cache is shallow | market history, not a cross-currency funding vintage | Existing FX/HK chips; context only, no v1 global scalar |
| `data/hkma/interbank_liquidity.parquet` | HKMA | daily; 2002-01-02 / 2026-08-21 | observation-date series; collector owns freshness | no revision archive; market/official operational history | Existing HK page/context; jurisdiction diagnostic only |
| `data/china_funding/shibor.parquet` | ChinaMoney/Jin10 public payloads | daily; 2015-05-08 / 2026-08-21 | fixing-date series; collector owns freshness | no vintage archive, typically non-revised fixing | Existing China funding context; jurisdiction diagnostic only |
| World Bank reserve parquets | World Bank | annual/quarterly depending country | slow structural releases; repo lacks first-known clock | final/revised structural data | Existing macro context; not a timely CB-state leg |

No adequate cross-currency-basis swap store was found. CNH futures/spot basis,
HIBOR−SOFR, and HKMA aggregate balance are useful local funding diagnostics but
must not be renamed into a covered global basis basket.

## Existing logic that remains canonical

1. `engine/global_liquidity.py` owns the existing display-tier Fed/ECB/BoJ
   balance-sheet panel. W-LIQ.1 shares its source stores but adds a causal
   availability kernel and does not replace the display module.
2. `engine/btc_signals.py::global_liquidity` owns the existing US+China broad
   money read. It is a different economic construct and remains separate.
3. `engine.regime.liquidity_quality` and
   `data/regime/latest.json.liquidity_quality` own the US quantity-versus-quality
   classifier. W-LIQ.1 embeds the current canonical object without changing its
   label or thresholds.
4. `engine.canon.credit_impulse_level` and `credit_impulse_accel` own China TSF
   transforms. W-LIQ.1 uses them only for separate context after applying the
   stored `availability_date`.

## Point-in-time classes

The producer distinguishes four claims instead of calling every dated series
“PIT”:

- `release_lag_aligned_non_revised`: observation is made usable only after a
  conservative release lag and the stored history is treated as non-revising.
- `release_lag_aligned_revision_unknown`: the availability date is conservative,
  but the repository cannot reconstruct all later revisions. ECB and BoJ carry
  this limitation.
- `explicit_conservative_availability_date`: the collector stores an explicit
  usable date, as China TSF does.
- excluded: a series whose vintage or publication timing is inadequate for the
  causal state. China M2 and NFCI/ANFCI are not silently promoted from context.

Availability alignment and vintage reconstruction are different guarantees. A
lag prevents using a print before release; it does not undo a later revision.

## Durable BoJ date finding

`JPNASSETS` is an end-of-period monthly statistic whose repository index is the
first day of its month. Treating `2026-07-01` as the economic observation date
uses July’s end value and its FX conversion roughly one month too early. W-LIQ.1
anchors it to `2026-07-31`, samples USD/JPY on or before that date, and makes it
available after two business days (`2026-08-04`). This is separately recorded as
`DSC:BOJ-ASSETS-REQUIRE-MONTH-END-ANCHOR`.

## Current-source receipt

At the generated contract as of 2026-08-21:

- monetary coverage is 3/3: Fed reference 2026-08-19, ECB 2026-08-14, BoJ
  economic reference 2026-07-31;
- USD-funding coverage is 3/3: broad dollar reference 2026-08-14, real yield
  and HY OAS 2026-08-20;
- canonical US liquidity quality reads `contracting`, with the move classified
  as mechanical and the RRP buffer exhausted;
- `credit_impulse_global` is null by design, not zero and not neutral.

The machine-readable source IDs, reference dates, availability dates, ages,
staleness thresholds, PIT classes, and revision-risk grades are included under
`freshness.components` in the sample contract. Each component also carries a
canonical history/component hash. The aggregate sample source snapshot is
identified by `meta.source_snapshot_hash`; `generated_at` is not part of that
hash, so an exact retry remains the same source snapshot.

The repo has no exact record of first-known GLT payloads for the visually
identified 2023–2026 episodes because the producer did not yet exist. Weekly
backfill dates are causal measurement dates, not an episode chronology. The
history receipt therefore freezes an empty chronology and forbids inference.

## Files produced by the commission

- Producer manifest: `config/global_liquidity_transmission_v1.yml`
- Causal kernel: `engine/global_liquidity_transmission.py`
- Builder: `scripts/build_global_liquidity_transmission.py`
- Historical state: `data/global_liquidity_transmission/state_history.parquet`
- History receipt: `data/global_liquidity_transmission/state_history_meta.json`
- Frozen factor comparison: `data/global_liquidity_transmission/factor_comparison_btc_4w.json`
- State-only sample contract: `site/liquiditydata/global_liquidity_transmission.json`
