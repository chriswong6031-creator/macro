# TSA Daily Throughput — Data Product (Lane A9)

**Status:** SHIPPED — backfill complete, parquet written, no trial family.

---

## In plain English

Every day the TSA publishes how many passengers passed through US airport security checkpoints the prior calendar day. This product scrapes that number from tsa.gov (2019 to present), stores it, and adds three context columns that make the raw count chart-ready without further computation: a 7-day rolling average to smooth day-of-week noise, year-over-year % change to show travel demand momentum, and a % vs same-weekday-in-2019 to show recovery from the COVID collapse.

The 2019 baseline is the natural pre-COVID reference point for travel demand; the TSA itself uses it on their own site.

---

## Data product details

| Item | Value |
|---|---|
| Source | https://www.tsa.gov/travel/passenger-volumes (no API key; public) |
| Store | `data/tsa/throughput.parquet` |
| Group / series | `tsa` / `throughput` |
| Date range (backfill) | 2019-01-01 — 2026-07-05 |
| Total rows | 2,743 |
| Update frequency | Daily (TSA publishes prior day each morning ET) |
| Parquet size | ~107 KB |

### Columns

| Column | Type | Description |
|---|---|---|
| `passengers` | int64 | Raw daily checkpoint count from TSA |
| `avg7d` | float64 | 7-day trailing rolling average (min_periods=1) |
| `yoy_pct` | float64 | % change vs same calendar date 1 year prior (±1 day fallback if missing) |
| `vs2019_pct` | float64 | % vs nearest same-weekday 2019 date (within ±3 days; nearest-date fallback) |

### Coverage summary

| Year | Days | yoy_pct coverage | vs2019_pct coverage (**) |
|---|---|---|---|
| 2019 | 365 | 0% (no prior year) | 0% (is the baseline) |
| 2020 | 366 | ~100% | 97% |
| 2021 | 365 | ~100% | 96% |
| 2022 | 365 | ~100% | 96% |
| 2023 | 365 | ~100% | 96% |
| 2024 | 366 | ~100% | 97% |
| 2025 | 365 | ~100% | 97% |
| 2026 | 186 (through Jul 5) | ~100% | 96% |

### Sample (most recent 5 days)

```
date         passengers     avg7d      yoy_pct   vs2019_pct
2026-07-01   2,654,017   2,734,886    +10.5%      +4.2%
2026-07-02   2,901,753   2,733,643    +6.7%       +23.6%  (*)
2026-07-03   2,572,397   2,686,184    -12.0%        NaN   (**)
2026-07-04   1,882,467   2,587,161    -13.0%        NaN   (**)
2026-07-05   2,914,375   2,584,833    +18.6%      +4.3%
```

(*) Holiday-adjacent caveat: Jul 2 vs2019 = +23.6%. The previous computation reported +38.9% because the ±3-day weekday search matched 2026-07-02 (Thursday) to 2019-07-04 (Thursday = Independence Day, an anomalously low travel day at ~2.1M vs the normal ~2.3M range). That match was a day-type artifact, not a demand signal. The corrected value uses the nearest non-holiday 2019 date (2019-07-02, Tuesday — not a weekday match, but no non-holiday same-weekday exists in the ±3-day window around Jul 4 2019). See Amendment A3 below.

(**) Jul 3 and Jul 4 2026 are US federal holidays (July 4 = Independence Day, falls on Saturday; observed = Friday July 3). vs2019_pct is NaN for all federal holiday dates on BOTH sides of the comparison. Holiday counts are anomalously low and a holiday-vs-non-holiday ratio is not a demand signal. The avg7d column smooths over these dates for trend display.

**Holiday-adjacent warning (applies to all years):** Any vs2019_pct value where the target date or the matched 2019 date is within ±3 days of a US federal holiday may be affected by day-type mismatch even after holiday exclusion. Specifically: if the ±3-day same-weekday search finds no valid non-holiday candidate, the fallback uses the nearest non-holiday 2019 date regardless of weekday. These fallback values are lower quality and should be read alongside avg7d rather than in isolation. YoY % is not affected by holiday exclusion (both sides are the same calendar date).

---

## PIT assumptions

- **Passengers column:** point-in-time; TSA publishes the prior calendar day's count the following morning. The collector's `last_date` gate ensures no row is re-fetched from a future date.
- **avg7d:** trailing 7-day rolling mean. No look-ahead; min_periods=1 means first 6 rows use partial windows (disclosed).
- **yoy_pct:** uses same calendar date exactly ±1 year. If that exact date is missing (e.g. leap day), tries ±1 calendar day. If 2020 Feb 29 vs 2019: 2019 has no Feb 29, so ±1-day fallback hits Feb 28. This is disclosed and unavoidable with calendar-date YoY.
- **vs2019_pct:** searches ±3 days for a 2019 date with the same weekday, EXCLUDING US federal holidays from both the target date and the 2019 candidate set (Amendment A3). Falls back to nearest non-holiday date within ±7 days regardless of weekday if no same-weekday non-holiday match exists. Holiday dates return NaN. Leap years (2020, 2024) have Feb 29 mapped to Feb 28 2019 as the approx anchor.

### Pre-registered amendments

- **Amendment A1:** rows where the `Numbers` cell is blank or non-numeric are dropped rather than coerced to NaN. TSA occasionally publishes pages with placeholder rows for not-yet-available dates. Dropping is safer than storing NaN for a date that will later be filled.
- **Amendment A2 (leap-day mapping):** Timestamp.replace(year=2019) raises ValueError for Feb 29 in leap years. Fallback: replace day=28 first, then apply ±3-day weekday search. Disclosed in docstring.
- **Amendment A3 (holiday exclusion for vs2019_pct):** US federal holidays (all 11 official holidays plus their observed substitute dates per OPM rules) are excluded from BOTH the target date and the 2019 candidate set in _vs2019_pct. A holiday-vs-non-holiday match produces a spurious recovery figure that is purely a day-type artifact (demonstrated: 2026-07-02 vs 2019-07-04 yielded +38.9% when the correct figure after exclusion is +23.6%). Holiday dates return NaN. The self-contained holiday set is computed without external packages (pure stdlib + calendar module). Juneteenth included from 2019 onward for symmetry even though it became federal only in 2021 (travel patterns on June 19 pre-2021 are unaffected by this choice since the federal designation does not change historical airport volumes).

---

## What this is and is not

**Is:** a clean daily time series of US air travel volume, chart-ready for conditions desk display. Useful as a high-frequency consumer health proxy (discretionary travel spending), a regime context indicator (COVID/recovery/normalization), and a seasonal baseline comparison.

**Is not:** a signal family (no gates registered, no trial ledger entry). The YoY and vs2019 columns are display-level context only — they have not been tested for predictive content and should not be used as entry signals without a separate research program.

---

## Tests

21 unit tests in `tests/test_tsa_throughput.py`. All pure logic, no network calls.

- Parser: row count, column types, value accuracy, header skip, blank-cell drop (amendment A1), deduplication, empty-HTML error, sort order, decoy-second-table isolation
- Display fields: avg7d correctness, min_periods behavior, YoY null for first year, YoY=0 for flat series, vs2019 null without 2019 data, vs2019≈0 for flat series, column presence
- Holiday exclusion (Amendment A3): holiday target date returns NaN, holiday 2019 candidate excluded (non-holiday match used instead), self-contained holiday set includes Independence Day, non-holiday weekday correctly identified

Result: **21/21 pass**.

---

## Nightly wiring (for consolidation)

**Non-standard adapter — do not wire through the standard runner.**

`TsaThroughputAdapter.fetch()` calls `store.upsert()` internally and returns the already-stored frames. The standard runner (`collectors/base.py fetch_with_breaker`) expects `fetch()` to return raw frames and then handles validate/quarantine/circuit-breaker/store itself. Wiring this adapter through the standard registry path would double-store and bypass the runner's validation and quarantine logic.

Wire via a dedicated nightly step instead:

```python
# In scripts/collect.py (or a dedicated tsa_collect.py step) — NOT in the adapter registry list
from collectors.tsa_throughput import TsaThroughputAdapter

# Incremental (fetches only the current-year page; < 1 second)
TsaThroughputAdapter().fetch()

# Full backfill (run once or when the store is missing; fetches all year pages)
TsaThroughputAdapter().fetch(full_history=True)
```

The adapter uses `self.http_get` (retries + exponential backoff + config-sponsored User-Agent). No additional config keys, credentials, or rate-limit headers required. The TSA site has no documented rate limits; one request per year-page per nightly run is well within any reasonable threshold.

**Destination for display:** conditions desk (`conditions.html` or equivalent macro context panel). Suggested display: sparkline of `avg7d` with latest `yoy_pct` and `vs2019_pct` as badge labels.
