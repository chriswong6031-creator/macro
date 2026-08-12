# ETF holdings / flow data-source recon (D72, 2026-06-13)

Goal: free, no-key, **dated** daily full-holdings feeds (with per-holding share
counts) so the ETF flow radar can both collect forward AND backfill history. The
gold standard is a dated URL you can walk backward (like Global X).

Verified by actually fetching the endpoints (HTTP codes + payload inspection),
not by reading marketing pages.

## Live in the collector
| Sponsor | Funds | Dated? | Backfill | Notes |
|---|---|---|---|---|
| **Global X** | 21 | ✅ per-fund `assets.globalxetfs.com/funds/holdings/<fund>_full-holdings_YYYYMMDD.csv` | ✅ to ≥ Apr 2026 | clean equity holdings; reference source |
| **Roundhill** | 9 | ✅ ONE master `roundhillinvestments.com/.../FilepointRoundhill.40RU.RU_Holdings_<MMDDYYYY>.csv` covering all ~53 funds (filter `Account`) | ✅ to 2024 | **soft-404s with HTTP 200 + SPA page — validate body starts with `Date,Account`**; internal `Date` ≠ URL date; swap/option income funds (MAGS/QDTE/*W) skipped (messy tickers) |
| SSGA / SPDR | 20 | ❌ current-only XLSX | forward only | verified daily, no date in URL, no Wayback |
| Invesco | 5 | ❌ (API `interval=monthly`, latest only) | forward only | idType=cusip reliable |

Fund counts above are the 2026-08-12 universe. Full per-sponsor inventory
(14 sponsors, 103 universe funds + ARKK/ARKW): `config.yml` `etf_holdings.universe`
and the `etf_holdings.registry` block beneath it.

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

---

# 2026-08-12 — W2 universe expansion (ETF page upgrade, masterplan §3)

Universe **75 → 103** funds (+28), or **77 → 105** counting ARKK/ARKW (collected by
`collectors/holdings.py` into `data/holdings/`). Every fund below was probed with
the live adapter in the build worktree and ships ONLY because a real snapshot
parsed and landed on disk — nothing was added on faith. No new sponsor adapter
was written; the expansion rides sponsors the collector already supports, plus one
parser fix (First Trust, below).

## Added — receipts
Rows/weights are the snapshot actually written to
`data/etf_holdings/<TICKER>/<as_of>.parquet`. All 372 new parquet files were
re-validated end-to-end: exact `[ticker,name,weight_pct,shares,market_value,as_of]`
schema, >5 rows, weight sum inside 90–110%, no null shares, `as_of` == filename.

**Global X** (dated CSV — forward-collected AND backfilled)

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| GNOM | biotech-genomics | 2026-08-11 | 50 | 99.99% |
| BKCH | crypto-infra | 2026-08-11 | 33 | 99.84% |
| DRIV | transport-mobility | 2026-08-11 | 74 | 99.84% |
| CTEC | grid-power | 2026-08-11 | 40 | 99.85% |

**SSGA / SPDR S&P Kensho** (current-only XLSX — forward collection)

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| ROKT | space | 2026-08-11 | 37 | 99.90% |
| CNRG | grid-power | 2026-08-11 | 39 | 99.83% |
| HAIL | transport-mobility | 2026-08-11 | 87 | 99.40% |
| SIMS | industrials-infra | 2026-08-11 | 53 | 99.50% |

**VanEck** (current-only XLSX — forward collection). Slugs were enumerated off
`vaneck.com/us/en/investments/etfs/` (117 live slugs), not guessed.

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| SMHX | semis | 2026-08-11 | 23 | 100.00% |
| IBOT | robotics | 2026-08-11 | 68 | 99.93% |
| WARP | space | 2026-08-11 | 23 | 100.02% |
| EMET | critical-minerals | 2026-08-11 | 62 | 99.96% |
| NODE | crypto-infra | 2026-08-11 | 54 | 99.85% |
| BBH | biotech-genomics | 2026-08-11 | 25 | 100.04% |

**Sprott** (current-only data-URI CSV — forward collection). Slugs were scraped off
a live fund page; GBUG/METL are the first ACTIVELY MANAGED non-ARK funds on the
board, so they carry `active: true` and register as selection-primary.

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| SGDM | precious-miners | 2026-08-12 | 47 | 99.90% |
| SGDJ | precious-miners | 2026-08-12 | 29 | 97.10% |
| SLVR | precious-miners | 2026-08-12 | 77 | 99.96% |
| GBUG | precious-miners (active) | 2026-08-12 | 46 | 97.60% |
| SETM | critical-minerals | 2026-08-12 | 153 | 99.45% |
| COPJ | critical-minerals | 2026-08-12 | 69 | 99.90% |
| METL | critical-minerals (active) | 2026-08-12 | 41 | 96.72% |

**First Trust** (current-only HTML grid — forward collection; parser fixed below)

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| ROBT | robotics | 2026-08-11 | 122 | 99.63% |
| FTXL | semis | 2026-08-11 | 34 | 99.91% |
| QCLN | grid-power | 2026-08-11 | 52 | 99.90% |
| FAN | grid-power | 2026-08-11 | 54 | 99.90% |

**Exchange Traded Concepts / ROBO Global** (JSON CMS — forward collection)

| Fund | Theme | as_of | rows | Σ weight |
|---|---|---|---|---|
| ROBO | robotics | 2026-08-11 | 79 | 99.26% |
| THNQ | ai-compute | 2026-08-11 | 53 | 99.77% |
| HTEC | healthcare | 2026-08-11 | 61 | 98.20% |

## Revived — 4 configured funds that were collecting NOTHING
`SKYY / CIBR / FDN / GRID` have been in the universe since the 2026-07-12 sweep and
had **zero** snapshots on disk. Cause: First Trust's ASP.NET holdings grid ships its
header as an ordinary first `<tr><td>` row, so `pandas.read_html` numbers the columns
`0..6` and `_pick_html_table`'s header scan matched nothing — every First Trust fund
raised `no holdings table found`, silently, per-fund, forever. Fixed by a **fallback-
only** row-0 promotion in `_pick_html_table` (the normal `<th>` path is tried first and
still wins, so bitwise/stockanalysis behaviour is unchanged); pinned by
`tests/test_etf_registry.py::test_pick_html_table_*`, including a
`prefers_a_real_header_over_promotion` case. Receipts: SKYY 63 rows / 99.91%,
CIBR 44 / 99.62%, FDN 41 / 99.88%, GRID 126 / 99.77% (all as_of 2026-08-11).

## Backfill achieved
| Sponsor | Funds | Cadence | Range | Files | Size |
|---|---|---|---|---|---|
| Global X | GNOM, BKCH, DRIV, CTEC | daily | 2026-04-09 → 2026-08-11 | 86 each (339 backfilled + 4 live) | 2.31 MB |
| everything else | 24 new + 4 revived | — | single live snapshot | 33 | 0.19 MB |

Total new payload **2.50 MB / 372 files** (budget was 25 MB). Global X's CDN floor is
~2026-04-09, so the new funds are backfilled to the same depth as the incumbents —
daily, not weekly, since the whole set costs ~2.3 MB. `scripts/backfill_etf.py` gained
`--step N` (sample every Nth day) and `--only T1,T2` (restrict to funds) so a future
wide backfill can be thinned without hand-editing the script; it also now sleeps 0.2s
between GETs (this walk is ~500 requests per 4 funds).

## Probed and REJECTED (with cause)
- **`stockanalysis.com` serves only the TOP 25 holdings.** Measured on the live pages:
  SOXX "Showing 25 of 34", ITA 25/53, IRBO 25/64, ICLN 25/187, IBB 25/252. Parsed
  weight sums confirm the truncation (IBB 65.7%, ICLN 72.6%, IRBO 78.1%). A truncated
  snapshot manufactures **phantom exits** every time a name crosses the rank-25 line,
  so all five were dropped. ⚠️ The incumbent **WGMI is 25 of 29** — it looks healthy
  (24 equity rows, 99.3%) only because the fund is small; treat this fallback layer as
  safe ONLY for funds with ≤25 holdings, and re-check WGMI if it grows.
- **RAYS, WNDY (Global X)** — no holdings file at any date in the probe window; funds
  closed. Not seeded.
- **NIKL (Sprott)** — parses fine (26 rows, 99.79%) but only **2.7%** of weight sits in
  US-listed lines vs ≥11.9% for every incumbent (COPX 11.9%, LIT 37.1%, GDX 76.8%), so
  it would add almost nothing joinable. Nickel stays covered by SETM/METL/EMET.
- **Roundhill has no clean adds left.** The 2026-08-11 master lists 53 accounts; every
  one outside the 9 already configured is a weekly-income/covered-call `*W` sleeve, a
  swap wrapper, or a foreign-listed basket. Specifically: **NCLD** (Neocloud — the most
  on-theme fund found anywhere: 30% T-bills + CoreWeave TRS swaps, equity sleeve only
  ~half of NAV, would trip a weight-sum sanity guard), **DRAM** (Korea/Taiwan/Japan
  memory names + a Micron swap), **LYTE** (China A-share optics + 27% T-bill),
  **UX** (uranium via swaps on a physical trust), **LOHA** (102 clean US names but a
  broad multi-sector basket, not a theme). Re-open NCLD only once the engine can carry
  a declared non-equity NAV fraction.
- **SOXQ (Invesco)** — needs a CUSIP (`idType=ticker` 500s); both the product page and
  the profile API return **406** without a real browser. Semis are covered by
  SMHX/FTXL/XSD/SMH/PSI.
- **QTUM (Defiance, incumbent)** — every dated XLSX in the probe window returns **403**.
  Not a parser bug; the sponsor is blocking. QTUM has zero snapshots on disk and will
  keep collecting nothing until someone gets past that WAF. **Left broken — flagged,
  not fixed.**
- **Amplify (SILJ, BATT)** — both are exactly on-theme (junior silver miners, battery
  materials) and Amplify is Firestore-**backfillable ~9 months**, but
  `AMPLIFY_FIREBASE_KEY` is not set in this environment, so no receipt could be taken.
  Best single lead for the next wave: set the key and re-probe.

## Theme coverage after this wave
space ROKT/WARP/MARS/UFO/ARKX · ai-compute AIQ/CHAT/CLOU/SKYY/THNQ/QTUM/SNSR ·
data-center DTCR · nuclear-uranium URA/NLR/URNM/URNJ/NUKZ · robotics
BOTZ/ROBO/ROBT/IBOT/HUMN/ARKQ · defense SHLD/PPA/XAR/ARKX · crypto-infra
BKCH/NODE/BLOK/BITQ/DAPP/WGMI · semis SMH/SMHX/XSD/PSI/FTXL · precious-miners
GDX/GDXJ/SIL/SGDM/SGDJ/SLVR/GBUG · biotech-genomics XBI/GNOM/BBH/ARKG ·
critical-minerals REMX/XME/LIT/COPX/COPP/LITP/SETM/COPJ/EMET/METL · grid-power
TAN/PBW/HYDR/GRID/CNRG/QCLN/CTEC/FAN.
Still thin: **drones** (no parseable dedicated fund found) and **defense** (no new
sponsor-parseable fund beyond the four already carried).
