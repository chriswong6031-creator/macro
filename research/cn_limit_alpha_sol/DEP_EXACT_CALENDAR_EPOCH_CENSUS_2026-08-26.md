# CN limit-up alpha -- joint SSE/SZSE calendar epoch census

- store: `/Users/chriswong/.local/share/macro-dashboard/china_tushare_spine`
- generated_at: 2026-08-26T07:02:24.576369+00:00
- decision rule: Earliest year Y such that every year from Y through the last observed year is jointly complete (both exchanges report the exact civil-day count for that year -- 365, or 366 in a leap year -- and agree on is_open for every civil date both exchanges observe). This is a trailing rule: an early jointly-complete year followed by a later broken year is never selected; only an unbroken run reaching the most recently observed year counts as the epoch.
- **EARLIEST_JOINTLY_COMPLETE_EPOCH: 1992**

## Per-year

| year | want | SSE | SSE_open | SZSE | SZSE_open | shared | parity_mismatch | complete | joint |
|---|---|---|---|---|---|---|---|---|---|
| 1991 | 365 | 365 | 255 | 0 | 0 | 0 | -1 | False | False |
| 1992 | 366 | 366 | 255 | 366 | 255 | 366 | 0 | True | True |
| 1993 | 365 | 365 | 257 | 365 | 257 | 365 | 0 | True | True |
| 1994 | 365 | 365 | 252 | 365 | 252 | 365 | 0 | True | True |
| 1995 | 365 | 365 | 251 | 365 | 251 | 365 | 0 | True | True |
| 1996 | 366 | 366 | 247 | 366 | 247 | 366 | 0 | True | True |
| 1997 | 365 | 365 | 243 | 365 | 243 | 365 | 0 | True | True |
| 1998 | 365 | 365 | 246 | 365 | 246 | 365 | 0 | True | True |
| 1999 | 365 | 365 | 239 | 365 | 239 | 365 | 0 | True | True |
| 2000 | 366 | 366 | 239 | 366 | 239 | 366 | 0 | True | True |
| 2001 | 365 | 365 | 240 | 365 | 240 | 365 | 0 | True | True |
| 2002 | 365 | 365 | 237 | 365 | 237 | 365 | 0 | True | True |
| 2003 | 365 | 365 | 241 | 365 | 241 | 365 | 0 | True | True |
| 2004 | 366 | 366 | 243 | 366 | 243 | 366 | 0 | True | True |
| 2005 | 365 | 365 | 242 | 365 | 242 | 365 | 0 | True | True |
| 2006 | 365 | 365 | 241 | 365 | 241 | 365 | 0 | True | True |
| 2007 | 365 | 365 | 242 | 365 | 242 | 365 | 0 | True | True |
| 2008 | 366 | 366 | 246 | 366 | 246 | 366 | 0 | True | True |
| 2009 | 365 | 365 | 244 | 365 | 244 | 365 | 0 | True | True |
| 2010 | 365 | 365 | 242 | 365 | 242 | 365 | 0 | True | True |
| 2011 | 365 | 365 | 244 | 365 | 244 | 365 | 0 | True | True |
| 2012 | 366 | 366 | 243 | 366 | 243 | 366 | 0 | True | True |
| 2013 | 365 | 365 | 238 | 365 | 238 | 365 | 0 | True | True |
| 2014 | 365 | 365 | 245 | 365 | 245 | 365 | 0 | True | True |
| 2015 | 365 | 365 | 244 | 365 | 244 | 365 | 0 | True | True |
| 2016 | 366 | 366 | 244 | 366 | 244 | 366 | 0 | True | True |
| 2017 | 365 | 365 | 244 | 365 | 244 | 365 | 0 | True | True |
| 2018 | 365 | 365 | 243 | 365 | 243 | 365 | 0 | True | True |
| 2019 | 365 | 365 | 244 | 365 | 244 | 365 | 0 | True | True |
| 2020 | 366 | 366 | 243 | 366 | 243 | 366 | 0 | True | True |
| 2021 | 365 | 365 | 243 | 365 | 243 | 365 | 0 | True | True |
| 2022 | 365 | 365 | 242 | 365 | 242 | 365 | 0 | True | True |
| 2023 | 365 | 365 | 242 | 365 | 242 | 365 | 0 | True | True |

## Integrity

- partition purity: OK (0 impure rows)
- duplicate keys: 0

- SSE: rows=12053 span=1991-01-01..2023-12-31 pretrade_violations=0 missing_civil_dates=0
- SZSE: rows=11688 span=1992-01-01..2023-12-31 pretrade_violations=0 missing_civil_dates=0
