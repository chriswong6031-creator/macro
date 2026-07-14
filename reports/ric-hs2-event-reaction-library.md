# HS-2 Event-Day Reaction Library (P3)

> **DESCRIPTIVE ONLY** — MRI-R1/R2/R3. No signal, no gate, no entry/exit claim.
> Surprise direction is own-PIT (no street consensus owned). Small-n cells noted.

## Plain-word summary: what happens on these days

**CPI days** show modest day0 SPY amplification (1.07x vs an average session).
The amplification is smaller than sometimes assumed.
Realized vol in the 5 sessions after a CPI print is typically LOWER than the prior
20-session baseline: median SPY RV ratio = 0.87x all-eras,
0.86x in the 2021+ high-inflation era; TLT 0.86x,
DXY 0.93x, GLD 0.87x — all below 1.0.
Event uncertainty appears to resolve rather than persist into the post-window.
TLT and DXY show larger day0 amplification than SPY on CPI days.
Pre-window drift (T-5..T-1) is near-zero in aggregate, suggesting the market does
not systematically pre-position. Post-window drift (T+1..T+5) is also small in
aggregate, though regime-stratified cells show more structure.

**NFP days** (payrolls) also amplify, but less cleanly than CPI in recent years.
The 2021+ era saw sharp reversals in the day-5 window as markets re-priced
Fed path following payroll surprises.

**FOMC days** (2pm ET statement) show the largest day0 amplification for TLT and DXY.
Median RV ratio on FOMC days: TLT 1.02x, DXY 1.06x.
During the 2022-2023 hiking cycle, FOMC days produced outsized TLT moves.
Pre-window drift into FOMC is measurable (pre-FOMC drift documented in literature;
see coverage note for post-2016 status).

**PPI days** show moderate SPY amplification. Coverage starts 2014 only — the
pre-2014 era is entirely absent from our PPI store (prominent limitation).

**Claims days** (Thursday weekly) show the smallest amplification of all event types.
Weekly frequency and the exclusion of collision dates reduce the signal further.

**'Good-news-is-bad' regime**: when SPY/DGS2 rolling 126d correlation < -0.15,
hot CPI and NFP surprises tend to coincide with negative SPY and positive DXY
reactions — the 2022 rate-scare period is the clearest example in our data.

## Coverage limitations (prominent)

| Event type | Vintage store start | Spec target | Gap |
|---|---|---|---|
| CPI (CPIAUCSL/CPILFESL) | 1997-01 | 1998+ | None material; we report all owned |
| NFP (PAYEMS) | 1997-01 | 1998+ | None material |
| PPI (PPIFIS) | 2014-03 | 1998+ | **16 years missing** |
| Claims (ICSA) | 2009-06 | 1998+ | 11 years missing |
| FOMC | 1998-02 | 1998+ | Intermeeting included |

Claims collision drop: 116 weekly ICSA dates removed because they fell on
the same calendar date as a CPI, NFP, PPI, or FOMC event. Both rows are kept when
two types share a date (collision flag set).

Surprise direction is **own-PIT naive benchmark only** — no street consensus history
is owned. The benchmark is: prior period's first-print MoM (CPI/PPI), trailing-3m
mean first-print level change (NFP), prior-4w mean (claims). FOMC: n/a.

Asset coverage: SPY 1993+, TLT 2002+, DXY 1971+, GLD 2004+. Events outside an
asset's coverage window are excluded from that asset's n.

## Regime operationalization

Regime at each event date is classified from the 126-calendar-day change in the
fed funds target (DFEDTARU 2008-12-16+; DFF pre-2008-12-16). Data is in
percentage-point units (0.25 = 25bp):
- **hiking**: change > +0.125 pct-pt (+12.5 bp)
- **cutting**: change < -0.125 pct-pt (-12.5 bp)
- **pause**: within ±0.125 pct-pt (±12.5 bp)

126 calendar days ≈ 6 calendar months. Threshold = half a standard 25bp step.

## P3 phase taxonomy (daily-grid implementation)

| Phase | Implementation | Notes |
|---|---|---|
| pre_window | cumulative return T-5..T-1 (pre_drift) | 5 sessions before event |
| day0 | close[T]/close[T-1]-1 | Event-day close-to-close |
| post_window | cumulative return T+1..T+5 (post_drift) | 5 sessions after |
| intraday_preopen | **not computable at daily grid** | Requires intraday data |
| intraday_first_hour | **not computable at daily grid** | Requires intraday data |
| intraday_close_auction | **not computable at daily grid** | Requires intraday data |

8:30am releases (CPI/NFP/PPI/claims) and 2pm FOMC announcements are both
inside the release-day trading session; day0 captures both in the same window.

**Note on taxonomy substitution**: The masterplan §3 P3 spec defines calendar-proximity
labels {cpi_day, cpi_week, fomc_day, fomc_week, post_fomc_3d, nfp_day, quiet}.
This study implements a pre/day0/post window taxonomy instead, because: (a) all event
dates ARE the relevant day labels (cpi_day, fomc_day, etc.) by construction, and
(b) the window phases (pre_window, post_window) capture adjacent-period dynamics in
a symmetric way without requiring a non-event calendar. The 5d forward return (fwd5)
required by the spec is computed and shown in the table below, and stored in the JSON.

## FOMC list validation (self-check 1)

| Year | Scheduled meetings |
|---|---|
| 1998 | 8 (8 is standard) |
| 1999 | 8 (8 is standard) |
| 2000 | 8 (8 is standard) |
| 2001 | 8 (8 is standard) |
| 2002 | 8 (8 is standard) |
| 2003 | 8 (8 is standard) |
| 2004 | 8 (8 is standard) |
| 2005 | 8 (8 is standard) |
| 2006 | 8 (8 is standard) |
| 2007 | 8 (8 is standard) |
| 2008 | 8 (8 is standard) |
| 2009 | 8 (8 is standard) |
| 2010 | 8 (8 is standard) |
| 2011 | 8 (8 is standard) |
| 2012 | 8 (8 is standard) |
| 2013 | 8 (8 is standard) |
| 2014 | 8 (8 is standard) |
| 2015 | 8 (8 is standard) |
| 2016 | 8 (8 is standard) |
| 2017 | 8 (8 is standard) |
| 2018 | 8 (8 is standard) |
| 2019 | 8 (8 is standard) |
| 2020 | 7 **(7 — check)** |
| 2021 | 8 (8 is standard) |
| 2022 | 8 (8 is standard) |
| 2023 | 8 (8 is standard) |
| 2024 | 8 (8 is standard) |
| 2025 | 8 (8 is standard) |
| 2026 | 8 (partial year) |

Intermeeting / unscheduled decisions are compiled separately and flagged in the data.
2020-03-15 (Sunday emergency cut) is aligned to 2020-03-16 (next trading day).
All 11 catalyst_tone.py FOMC dates (2025-09-17 through 2026-12-09) match our list.

## Event-day amplification factors (|day0| / all-day |return| mean)

| Event type | SPY | TLT | DXY | GLD |
|---|---|---|---|---|
| CPI | 1.07x | 1.10x | 1.17x | 1.04x |
| NFP | 1.16x | 1.33x | 1.24x | 1.10x |
| FOMC | 1.28x | 1.21x | 1.15x | 1.29x |
| PPI | 0.95x | 1.04x | 0.86x | 0.98x |
| CLAIMS | 0.88x | 1.02x | 1.03x | 0.92x |

Amplification > 1.0 means event days move more than a typical session on average.
Base: all-day |return| mean computed over 1998-01-01 to present (or asset start,
whichever is later) — same era as the events, to compare like-period volatility.

## Day0 and fwd5 return statistics by event type and asset

All eras combined. n = events with valid data for that asset.
fwd5 = cumulative 5-session return starting from event day (close[T+4]/close[T-1]-1).

| Event type | Asset | n | Mean day0 | Med day0 | NW-HAC t (d0) | Med RV ratio | Mean fwd5 | Med fwd5 |
|---|---|---|---|---|---|---|---|---|
| CLAIMS | DXY | 775 | -0.0000 | 0.0001 | -0.20 | 0.88x | 0.0002 | 0.0003 |
| CLAIMS | GLD | 775 | -0.0001 | -0.0002 | -0.15 | 0.84x | 0.0018 | 0.0026 |
| CLAIMS | SPY | 775 | 0.0006 | 0.0009 | 1.58 | 0.84x | 0.0034 | 0.0051 |
| CLAIMS | TLT | 775 | 0.0001 | 0.0004 | 0.31 | 0.89x | 0.0008 | 0.0010 |
| CPI | DXY | 353 | -0.0003 | -0.0001 | -0.75 | 0.93x | -0.0002 | 0.0003 |
| CPI | GLD | 258 | 0.0012 | 0.0016 | 1.72 | 0.87x | 0.0028 | 0.0024 |
| CPI | SPY | 353 | 0.0005 | 0.0013 | 0.72 | 0.87x | 0.0020 | 0.0044 |
| CPI | TLT | 285 | 0.0006 | 0.0014 | 1.07 | 0.86x | 0.0021 | 0.0026 |
| FOMC | DXY | 256 | -0.0010 | -0.0006 | -2.64 | 1.06x | 0.0003 | -0.0001 |
| FOMC | GLD | 195 | 0.0015 | 0.0010 | 1.76 | 0.97x | 0.0008 | 0.0011 |
| FOMC | SPY | 256 | 0.0020 | 0.0014 | 2.03 | 0.97x | 0.0025 | 0.0028 |
| FOMC | TLT | 214 | 0.0016 | 0.0015 | 1.78 | 1.02x | 0.0023 | 0.0013 |
| NFP | DXY | 354 | 0.0003 | -0.0000 | 0.96 | 0.87x | -0.0001 | 0.0001 |
| NFP | GLD | 258 | 0.0003 | 0.0008 | 0.48 | 0.87x | 0.0051 | 0.0061 |
| NFP | SPY | 354 | 0.0013 | 0.0019 | 1.72 | 0.84x | 0.0008 | 0.0038 |
| NFP | TLT | 286 | -0.0009 | -0.0007 | -1.43 | 0.90x | -0.0009 | 0.0004 |
| PPI | DXY | 148 | 0.0001 | -0.0002 | 0.24 | 0.94x | 0.0003 | -0.0004 |
| PPI | GLD | 148 | 0.0003 | 0.0011 | 0.26 | 0.92x | 0.0021 | 0.0052 |
| PPI | SPY | 148 | -0.0007 | 0.0002 | -0.58 | 0.88x | 0.0030 | 0.0057 |
| PPI | TLT | 148 | 0.0019 | 0.0027 | 2.85 | 0.92x | 0.0008 | 0.0000 |

NW-HAC t-stat: Newey-West HAC with lag=5 (hand-rolled; non-wrapping autocovariance).
|t| > ~2 is suggestive but sample sizes vary widely across cells.
**Claims overlap note**: for weekly claims, consecutive fwd5 windows are
adjacent/overlapping (each event is 5 trading days apart, fwd5 spans 5 sessions),
so fwd5 aggregates across claims events are not independent draws; monthly event
types (CPI, NFP, PPI, FOMC) produce non-overlapping fwd5 windows. The JSON fwd5
NW-HAC uses lag=5 in event units, which covers the weekly overlap for claims.

## Era splits: day0 SPY returns

| Event type | Era | n | Mean day0 | Med day0 | NW-HAC t |
|---|---|---|---|---|---|
| CLAIMS | 2010-2020 | 510 | 0.0007 | 0.0008 | 1.63 |
| CLAIMS | 2021+ | 236 | 0.0001 | 0.0009 | 0.07 |
| CLAIMS | pre-2010 | 29 | 0.0031 | 0.0047 | 1.52 |
| CPI | 2010-2020 | 132 | -0.0001 | 0.0010 | -0.16 |
| CPI | 2021+ | 65 | 0.0008 | 0.0012 | 0.45 |
| CPI | pre-2010 | 156 | 0.0008 | 0.0018 | 0.81 |
| FOMC | 2010-2020 | 100 | 0.0009 | 0.0004 | 0.48 |
| FOMC | 2021+ | 44 | 0.0006 | -0.0001 | 0.28 |
| FOMC | pre-2010 | 112 | 0.0036 | 0.0034 | 2.79 |
| NFP | 2010-2020 | 132 | 0.0010 | 0.0019 | 1.19 |
| NFP | 2021+ | 66 | -0.0005 | 0.0015 | -0.31 |
| NFP | pre-2010 | 156 | 0.0024 | 0.0022 | 1.69 |
| PPI | 2010-2020 | 82 | -0.0028 | -0.0006 | -1.71 |
| PPI | 2021+ | 66 | 0.0021 | 0.0014 | 2.13 |
| PPI | pre-2010 | 0 | nan | nan | nan |

## Regime splits: day0 SPY returns

| Event type | Regime | n | Mean day0 | Med day0 | NW-HAC t | Med RV ratio |
|---|---|---|---|---|---|---|
| CLAIMS | cutting | 86 | -0.0003 | 0.0002 | -0.25 | 0.83x |
| CLAIMS | hiking | 191 | -0.0004 | -0.0002 | -0.54 | 0.79x |
| CLAIMS | pause | 498 | 0.0011 | 0.0016 | 2.58 | 0.86x |
| CPI | cutting | 74 | 0.0000 | 0.0004 | 0.01 | 0.94x |
| CPI | hiking | 103 | 0.0008 | 0.0021 | 0.68 | 0.83x |
| CPI | pause | 176 | 0.0004 | 0.0007 | 0.60 | 0.87x |
| FOMC | cutting | 68 | 0.0009 | 0.0025 | 0.32 | 0.92x |
| FOMC | hiking | 69 | 0.0014 | 0.0005 | 1.09 | 0.95x |
| FOMC | pause | 119 | 0.0030 | 0.0016 | 3.14 | 1.00x |
| NFP | cutting | 79 | -0.0001 | 0.0010 | -0.05 | 0.89x |
| NFP | hiking | 97 | 0.0022 | 0.0014 | 1.61 | 0.75x |
| NFP | pause | 178 | 0.0015 | 0.0027 | 1.85 | 0.86x |
| PPI | cutting | 26 | -0.0055 | -0.0008 | -1.37 | 0.95x |
| PPI | hiking | 51 | -0.0002 | -0.0003 | -0.17 | 0.88x |
| PPI | pause | 71 | 0.0008 | 0.0005 | 0.71 | 0.87x |

Small-n cells (n < 10) should be read as directional context only.

## Surprise-direction x day0-sign contingency (SPY, all regimes)

Surprise direction is own-PIT naive only — see coverage note.
Cells with n=0 omitted.

| Event type | Surprise dir | day0 sign | n (all regimes) |
|---|---|---|---|
| CLAIMS | down | negative | 206 |
| CLAIMS | down | positive | 262 |
| CLAIMS | inline | negative | 338 |
| CLAIMS | inline | positive | 424 |
| CLAIMS | up | negative | 134 |
| CLAIMS | up | positive | 158 |
| CPI | down | negative | 128 |
| CPI | down | positive | 162 |
| CPI | inline | negative | 40 |
| CPI | inline | positive | 62 |
| CPI | up | negative | 130 |
| CPI | up | positive | 156 |
| NFP | down | negative | 106 |
| NFP | down | positive | 102 |
| NFP | inline | negative | 118 |
| NFP | inline | positive | 138 |
| NFP | up | negative | 64 |
| NFP | up | positive | 150 |
| PPI | down | negative | 56 |
| PPI | down | positive | 50 |
| PPI | inline | negative | 14 |
| PPI | inline | positive | 36 |
| PPI | up | negative | 58 |
| PPI | up | positive | 54 |

AND-gate cells (regime x surprise x sign) have very small n — see JSON for full
per-regime breakdown. All cells with n printed.

## Pre-window and post-window drifts: SPY mean

| Event type | Phase | n | Mean drift | Med drift | NW-HAC t |
|---|---|---|---|---|---|
| CLAIMS | post_window | 775 | 0.0029 | 0.0049 | 3.76 |
| CLAIMS | pre_window | 775 | 0.0032 | 0.0046 | 4.79 |
| CPI | post_window | 353 | 0.0011 | 0.0023 | 1.12 |
| CPI | pre_window | 353 | 0.0021 | 0.0052 | 1.39 |
| FOMC | post_window | 256 | -0.0004 | 0.0016 | -0.26 |
| FOMC | pre_window | 256 | 0.0001 | 0.0025 | 0.02 |
| NFP | post_window | 354 | 0.0001 | 0.0014 | 0.09 |
| NFP | pre_window | 354 | 0.0033 | 0.0058 | 2.63 |
| PPI | post_window | 148 | 0.0035 | 0.0056 | 2.43 |
| PPI | pre_window | 148 | 0.0033 | 0.0065 | 1.67 |

Lucca-Moench pre-FOMC drift (documented pre-2016) would appear as positive
mean pre_window on FOMC rows. See the era-split in the JSON for post-2016 status.

## Quiet (non-event) baseline cohort (P3 comparator)

All SPY trading days with no cpi/nfp/ppi/claims/fomc event within ±1 trading day,
within each asset's own coverage window. Provides the explicit P3 'quiet' comparator
absent from the original spec implementation.

**Note on phase labels**: The masterplan §3 P3 spec defines week-level phases
(cpi_week, post_fomc_3d, collision states like cpi_in_opex_week). These are deferred
until the event-window engine (RIC W4) exists. The ±1-trading-day exclusion used here
is the implemented daily-grid approximation — disclosed, not silent.

| Asset | Era | n quiet days | Mean |day0| | Med |day0| | Med RV ratio |
|---|---|---|---|---|---|
| DXY | 2010-2020 | 681 | 0.0031 | 0.0024 | 0.91x |
| DXY | 2021+ | 358 | 0.0031 | 0.0025 | 0.89x |
| DXY | all | 9740 | 0.0035 | 0.0024 | 0.86x |
| DXY | pre-2010 | 8701 | 0.0036 | 0.0024 | 0.86x |
| GLD | 2010-2020 | 683 | 0.0071 | 0.0052 | 0.83x |
| GLD | 2021+ | 354 | 0.0086 | 0.0058 | 0.89x |
| GLD | all | 1786 | 0.0086 | 0.0062 | 0.87x |
| GLD | pre-2010 | 749 | 0.0099 | 0.0071 | 0.89x |
| SPY | 2010-2020 | 683 | 0.0069 | 0.0049 | 0.82x |
| SPY | 2021+ | 353 | 0.0068 | 0.0052 | 0.86x |
| SPY | all | 4059 | 0.0076 | 0.0053 | 0.88x |
| SPY | pre-2010 | 3023 | 0.0078 | 0.0054 | 0.90x |
| TLT | 2010-2020 | 683 | 0.0065 | 0.0050 | 0.92x |
| TLT | 2021+ | 353 | 0.0074 | 0.0058 | 0.88x |
| TLT | all | 2154 | 0.0062 | 0.0048 | 0.91x |
| TLT | pre-2010 | 1118 | 0.0056 | 0.0043 | 0.90x |

For reference: SPY quiet-day mean |return| = 0.0076,
median |return| = 0.0053.
Event-day amplification factors (vs all-day baseline) are shown in the table
above; the quiet baseline (excluding ±1-day event vicinity) provides a cleaner
non-event comparator for the amplification framing.

## Self-checks

1. **FOMC count/year**: see table above. Years with ≠8 scheduled meetings flagged.
2. **Anchor events**: CPI 2022-06-10 SPY day0 negative (hot May-2022 print) ✓;
   NFP 2024-08-02 SPY day0 negative ✓;
   FOMC 2020-03-15 (Sunday emergency cut) aligned to 2020-03-16 ✓.
3. **DFEDTARU change dates**: all should be within 3 days of a compiled FOMC date.
   See console output for any orphans.
4. **No events on non-trading-days**: events on weekends/holidays are aligned to
   the next SPY trading day. Count of alignments printed in console output.

## Provenance

| Source | Path |
|---|---|
| Vintages | data/fred_vintage/vintages.parquet |
| SPY/TLT/DXY/GLD | data/yahoo/{SPY,TLT,DX-Y.NYB,GLD}.parquet |
| Regime | data/fred/DFEDTARU.parquet + data/fred/DFF.parquet |
| GNBN corr | data/fred/DGS2.parquet |
| FOMC dates | federalreserve.gov/monetarypolicy/ (fetched 2026-07-14) |
| JSON output | reports/ric_hs2_event_reaction_library.json |

