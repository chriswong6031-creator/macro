# ETF holdings / flow data-source recon (D72, 2026-06-13)

Goal: free, no-key, **dated** daily full-holdings feeds (with per-holding share
counts) so the ETF flow radar can both collect forward AND backfill history. The
gold standard is a dated URL you can walk backward (like Global X).

Verified by actually fetching the endpoints (HTTP codes + payload inspection),
not by reading marketing pages.

## Live in the collector
| Sponsor | Funds | Dated? | Backfill | Notes |
|---|---|---|---|---|
| **Global X** | 10 (URA, LIT, COPX, SIL, MLPX, PAVE, BOTZ, BUG, CLOU, HERO) | ✅ per-fund `assets.globalxetfs.com/funds/holdings/<fund>_full-holdings_YYYYMMDD.csv` | ✅ to ≥ Apr 2026 | clean equity holdings; reference source |
| **Roundhill** | 6 (MEME, METV, CHAT, BETZ, MARS, OZEM) | ✅ ONE master `roundhillinvestments.com/.../FilepointRoundhill.40RU.RU_Holdings_<MMDDYYYY>.csv` covering all ~51 funds (filter `Account`) | ✅ to 2024 | **soft-404s with HTTP 200 + SPA page — validate body starts with `Date,Account`**; internal `Date` ≠ URL date; swap/option income funds (MAGS/QDTE/*W) skipped (messy tickers) |
| SSGA / SPDR | 12 | ❌ current-only XLSX | forward only | verified daily, no date in URL, no Wayback |
| Invesco | 2 | ❌ (API `interval=monthly`, latest only) | forward only | idType=cusip reliable |

Backfill: `scripts/backfill_etf.py` (Global X per-fund + Roundhill master-per-date).
Thresholds were retuned for index ETFs (they rebalance over weeks, not days):
`active_change_window_d: 40`, `active_change_alert_pct: 5` (was 5d/15%, tuned for ARK).

## Viable, not yet added (good future expansion)
- **ProShares** — `accounts.profunds.com/etfdata/psdlyhld.csv`: ONE keyless CSV, ALL
  ~168 funds (incl. BITO), per-holding Shares/Contracts. Forward = trivial. Backfill =
  Wayback only (`web.archive.org/.../id_/...psdlyhld.csv`, irregular). Bonus:
  `historical_nav.csv` = multi-year dated Shares-Outstanding + AUM (fund-level FLOW history).
  Mostly leveraged/swap funds → messier holdings. **effort low, partial.**
- **SEC EDGAR N-PORT** — official, free (real User-Agent only). Full holdings WITH shares
  + embedded monthly creation/redemption flow. **Quarterly, ~1-2mo lag**, backfillable for
  any ETF. Best for fund-level FLOW history + a universal fallback. **effort medium.**
- **Amplify** — same Filepoint vendor/parser as Roundhill, ONE master, but **current-only**
  (no dated archive) → forward only.

## Not viable (free)
VanEck / Direxion / ARK / First Trust / Invesco: current-only (no dated history) →
forward collection only, no backfill. iShares & Schwab: Akamai/consent walls (need a
headless browser). FMP / Tiingo / EODHD / WisdomTree: paywalled or no free historical
ETF holdings.
