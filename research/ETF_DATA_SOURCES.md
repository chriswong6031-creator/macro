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


---

# 2026-08-12 — Registry type audit (ETF page upgrade, masterplan §6c M2)

All **105** `etf_holdings.registry` rows re-checked against their sponsor's
product line. Stamped in config as `etf_holdings.registry_audited: "2026-08-12"`;
bump that key only in the same commit as a retype.

**Why the audit happened.** Four Roundhill funds (CHAT, OZEM, CABZ, HUMN) shipped
typed `thematic_passive` while this repo's own masterplan §2 and
`docs/site_semantics/etfs.md` both used OZEM as the *worked example of an active
fund*. A registry that disagrees with the glossary one directory away is not a
typo, it is an unaudited block — and nothing in the suite could tell "checked and
correct" from "never looked at".

**Where the stakes actually are.** `engine.etf_consensus.PRIMARY_COMPONENT` maps
`sector` and `thematic_passive` to the SAME primary component (`flow`), so that
half of the taxonomy has zero effect on the weighting lens — it only groups the
free fleet directory. The load-bearing axis is **active vs not-active**: typing an
index fund `active` hands full weight to its per-name residual, which for a basket
is mostly index reconstitution. A mistype in that direction promotes noise; the
other direction merely discounts a real pick to 0.35. So the standing rule for an
unresolved row is **leave it at the least-claiming default and flag it** — the same
fail-soft contract `fund_registry()` itself runs on.

**Evidence used** (no network; this is an audit of what the repo can prove):
1. the sponsor's own product line, per `collectors/etf_holdings.py`'s adapter map;
2. the fund's legal name in `etf_holdings.universe` — a sponsor that writes
   "Active" into a name is telling us how the fund is run (now CI-pinned by
   `tests/test_etf_registry.py::test_a_fund_whose_name_says_active_is_typed_active`);
3. the `universe.<fund>.active` flag. **Caveat, and it is the audit's main
   finding about method:** that flag and the registry `type` are hand-set in the
   same file by the same edit, so when they agree they are *one* witness, not two.

**Result: 97 confirmed · 4 retyped · 4 flagged.**

| | Funds |
|---|---|
| **Retyped** `thematic_passive` → `active` | `CHAT` `OZEM` `CABZ` `HUMN` |
| **Flagged, left as-is** | `MARS` `WARP` `NODE` (typed passive, may be active) · `BITQ` (typed active, may be passive) |
| Confirmed | the other 97 |

**Deliberately NOT changed.** The four retypes touch `etf_holdings.registry` only.
The sibling `etf_holdings.universe.<fund>.active` flag stays false for them: it
drives the `ACTIVE` chip and `is_active` on the per-fund rows, which is a
designer-owned surface, and §6c M2 scopes the ruling to the registry. The two
blocks are read for different jobs and `build_site.build_etf_page` already
comments that the registry — not `is_active` — is what types a fund for the fleet
directory. Reconciling the chip is a follow-up, not this wave.

## Per-fund verdicts

**globalx** (21 funds) — Global X — Solactive / Indxx / mirae thematic index funds

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `URA` | Global X Uranium | `thematic_passive` | confirmed |  |
| `LIT` | Global X Lithium & Battery Tech | `thematic_passive` | confirmed |  |
| `COPX` | Global X Copper Miners | `thematic_passive` | confirmed |  |
| `SIL` | Global X Silver Miners | `thematic_passive` | confirmed |  |
| `MLPX` | Global X MLP & Energy Infrastructure | `thematic_passive` | confirmed |  |
| `PAVE` | Global X U.S. Infrastructure Dev | `thematic_passive` | confirmed |  |
| `BOTZ` | Global X Robotics & AI | `thematic_passive` | confirmed |  |
| `BUG` | Global X Cybersecurity | `thematic_passive` | confirmed |  |
| `CLOU` | Global X Cloud Computing | `thematic_passive` | confirmed |  |
| `HERO` | Global X Video Games & Esports | `thematic_passive` | confirmed |  |
| `AIQ` | Global X AI & Technology | `thematic_passive` | confirmed |  |
| `SNSR` | Global X Internet of Things | `thematic_passive` | confirmed |  |
| `FINX` | Global X FinTech | `thematic_passive` | confirmed |  |
| `DTCR` | Global X Data Center & Digital Infra | `thematic_passive` | confirmed |  |
| `SHLD` | Global X Defense Tech | `thematic_passive` | confirmed |  |
| `HYDR` | Global X Hydrogen | `thematic_passive` | confirmed |  |
| `EBIZ` | Global X E-commerce | `thematic_passive` | confirmed |  |
| `GNOM` | Global X Genomics & Biotechnology | `thematic_passive` | confirmed |  |
| `BKCH` | Global X Blockchain | `thematic_passive` | confirmed |  |
| `DRIV` | Global X Autonomous & Electric Vehicles | `thematic_passive` | confirmed |  |
| `CTEC` | Global X CleanTech | `thematic_passive` | confirmed |  |

**ssga** (20 funds) — SPDR — S&P Select Industry / S&P Kensho index funds; no active ETF in this set

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `XBI` | SPDR S&P Biotech | `sector` | confirmed |  |
| `XOP` | SPDR S&P Oil & Gas E&P | `sector` | confirmed |  |
| `XHB` | SPDR S&P Homebuilders | `sector` | confirmed |  |
| `XRT` | SPDR S&P Retail | `sector` | confirmed |  |
| `KRE` | SPDR S&P Regional Banking | `sector` | confirmed |  |
| `KBE` | SPDR S&P Bank | `sector` | confirmed |  |
| `XME` | SPDR S&P Metals & Mining | `sector` | confirmed |  |
| `XSD` | SPDR S&P Semiconductor | `sector` | confirmed |  |
| `XAR` | SPDR S&P Aerospace & Defense | `sector` | confirmed |  |
| `XSW` | SPDR S&P Software & Services | `sector` | confirmed |  |
| `XTN` | SPDR S&P Transportation | `sector` | confirmed |  |
| `XPH` | SPDR S&P Pharmaceuticals | `sector` | confirmed |  |
| `XES` | SPDR S&P Oil & Gas Equipment & Services | `sector` | confirmed |  |
| `KCE` | SPDR S&P Capital Markets | `sector` | confirmed |  |
| `XHE` | SPDR S&P Health Care Equipment | `sector` | confirmed |  |
| `XTL` | SPDR S&P Telecom | `sector` | confirmed |  |
| `ROKT` | SPDR S&P Kensho Final Frontiers | `thematic_passive` | confirmed |  |
| `CNRG` | SPDR S&P Kensho Clean Power | `thematic_passive` | confirmed |  |
| `HAIL` | SPDR S&P Kensho Smart Mobility | `thematic_passive` | confirmed |  |
| `SIMS` | SPDR S&P Kensho Intelligent Structures | `thematic_passive` | confirmed |  |

**vaneck** (14 funds) — VanEck — MarketVector / MVIS index funds; Morningstar index for MOAT

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `SMH` | VanEck Semiconductor | `sector` | confirmed |  |
| `SMHX` | VanEck Fabless Semiconductor | `sector` | confirmed |  |
| `GDX` | VanEck Gold Miners | `thematic_passive` | confirmed |  |
| `GDXJ` | VanEck Junior Gold Miners | `thematic_passive` | confirmed |  |
| `NLR` | VanEck Uranium & Nuclear | `thematic_passive` | confirmed |  |
| `REMX` | VanEck Rare Earth & Strategic Metals | `thematic_passive` | confirmed |  |
| `IBOT` | VanEck Robotics | `thematic_passive` | confirmed |  |
| `MOAT` | VanEck Morningstar Wide Moat | `thematic_passive` | confirmed | a quality/factor index, not a theme; typed `thematic_passive`. Not active, which is the axis that matters. |
| `OIH` | VanEck Oil Services | `sector` | confirmed |  |
| `DAPP` | VanEck Digital Transformation | `thematic_passive` | confirmed |  |
| `WARP` | VanEck Space | `thematic_passive` | flagged | VanEck 2025 launch; index vs active not resolvable from the collector config or the fund name. Left at the least-claiming default. |
| `EMET` | VanEck Copper and Electrification | `thematic_passive` | confirmed |  |
| `NODE` | VanEck Onchain Economy | `thematic_passive` | flagged | VanEck 2025 launch; same. Left at the least-claiming default. |
| `BBH` | VanEck Biotech | `sector` | confirmed |  |

**sprott** (11 funds) — Sprott — Nasdaq Sprott index funds, EXCEPT the two named 'Active'

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `URNM` | Sprott Uranium Miners | `thematic_passive` | confirmed |  |
| `URNJ` | Sprott Junior Uranium Miners | `thematic_passive` | confirmed |  |
| `COPP` | Sprott Copper Miners | `thematic_passive` | confirmed |  |
| `LITP` | Sprott Lithium Miners | `thematic_passive` | confirmed |  |
| `SGDM` | Sprott Gold Miners | `thematic_passive` | confirmed |  |
| `SGDJ` | Sprott Junior Gold Miners | `thematic_passive` | confirmed |  |
| `SETM` | Sprott Critical Materials | `thematic_passive` | confirmed |  |
| `SLVR` | Sprott Silver Miners & Physical Silver | `thematic_passive` | confirmed |  |
| `COPJ` | Sprott Junior Copper Miners | `thematic_passive` | confirmed |  |
| `GBUG` | Sprott Active Gold & Silver Miners | `active` | confirmed |  |
| `METL` | Sprott Active Metals Miners | `active` | confirmed |  |

**roundhill** (9 funds) — Roundhill — MIXED: index funds pre-2024, actively-managed thematics after

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `MEME` | Roundhill MEME | `thematic_passive` | confirmed |  |
| `METV` | Roundhill Ball Metaverse | `thematic_passive` | confirmed |  |
| `CHAT` | Roundhill Generative AI & Tech | `active` | **RETYPED** | was `thematic_passive`; actively managed (§6c M2). |
| `BETZ` | Roundhill Sports Betting & iGaming | `thematic_passive` | confirmed |  |
| `MARS` | Roundhill Space | `thematic_passive` | flagged | same post-2024 Roundhill thematic cohort as the four retyped; no in-repo evidence either way. Left at the least-claiming default. |
| `OZEM` | Roundhill GLP-1 & Weight Loss | `active` | **RETYPED** | was `thematic_passive`; actively managed (§6c M2). |
| `NERD` | Roundhill Video Games | `thematic_passive` | confirmed |  |
| `CABZ` | Roundhill Robotaxi & Autonomous | `active` | **RETYPED** | was `thematic_passive`; actively managed (§6c M2). |
| `HUMN` | Roundhill Humanoid Robotics | `active` | **RETYPED** | was `thematic_passive`; actively managed (§6c M2). |

**ark** (8 funds) — ARK — actively managed, EXCEPT the two index products (PRNT, IZRL)

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `ARKK` | ARK ARKK | `active` | confirmed |  |
| `ARKW` | ARK ARKW | `active` | confirmed |  |
| `ARKG` | ARK Genomic Revolution | `active` | confirmed |  |
| `ARKQ` | ARK Autonomous Tech & Robotics | `active` | confirmed |  |
| `ARKF` | ARK Blockchain & Fintech Innovation | `active` | confirmed |  |
| `ARKX` | ARK Space & Defense Innovation | `active` | confirmed |  |
| `PRNT` | The 3D Printing ETF | `thematic_passive` | confirmed |  |
| `IZRL` | ARK Israel Innovative Technology | `thematic_passive` | confirmed |  |

**firsttrust** (8 funds) — First Trust — Nasdaq CTA / ISE / Dow Jones index funds

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `SKYY` | First Trust Cloud Computing | `thematic_passive` | confirmed |  |
| `CIBR` | First Trust NASDAQ Cybersecurity | `thematic_passive` | confirmed |  |
| `FDN` | First Trust Dow Jones Internet | `sector` | confirmed |  |
| `GRID` | First Trust Clean Edge Smart Grid | `thematic_passive` | confirmed |  |
| `ROBT` | First Trust Nasdaq AI & Robotics | `thematic_passive` | confirmed |  |
| `FTXL` | First Trust Nasdaq Semiconductor | `sector` | confirmed |  |
| `QCLN` | First Trust NASDAQ Clean Edge Green Energy | `thematic_passive` | confirmed |  |
| `FAN` | First Trust Global Wind Energy | `thematic_passive` | confirmed |  |

**invesco** (5 funds) — Invesco — third-party index funds (MAC Solar, WilderHill, SPADE, Nasdaq)

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `TAN` | Invesco Solar | `thematic_passive` | confirmed |  |
| `PBW` | Invesco WilderHill Clean Energy | `thematic_passive` | confirmed |  |
| `PSI` | Invesco Semiconductors | `sector` | confirmed |  |
| `PPA` | Invesco Aerospace & Defense | `sector` | confirmed | SPADE Defense Index is a theme, not an industry classification; typed `sector`. No-op for the lens (both types read FLOW). |
| `PHO` | Invesco Water Resources | `sector` | confirmed | Nasdaq OMX US Water is a theme, not an industry classification; typed `sector`. No-op for the lens. |

**etc** (4 funds) — Exchange Traded Concepts (white-label) — ROBO Global / Range index funds

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `NUKZ` | Range Nuclear Renaissance | `thematic_passive` | confirmed |  |
| `ROBO` | ROBO Global Robotics & Automation | `thematic_passive` | confirmed |  |
| `THNQ` | ROBO Global Artificial Intelligence | `thematic_passive` | confirmed |  |
| `HTEC` | ROBO Global Healthcare Technology & Innovation | `thematic_passive` | confirmed |  |

**amplify** (1 funds) — Amplify — BLOK is actively managed

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `BLOK` | Amplify Transformational Data Sharing | `active` | confirmed |  |

**bitwise** (1 funds) — Bitwise — BITQ is benchmarked to an in-house 30-name index

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `BITQ` | Bitwise Crypto Industry Innovators | `active` | flagged | typed `active` on the strength of `universe.active: true` ALONE — and that flag and this row are hand-set in the same file, so they are not two independent witnesses. The name is index-shaped. Left as-is: changing a type on this evidence is the same mistake in reverse. |

**defiance** (1 funds) — Defiance — BlueStar index funds

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `QTUM` | Defiance Quantum | `thematic_passive` | confirmed |  |

**procure** (1 funds) — ProcureAM — S-Network Space Index

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `UFO` | Procure Space | `thematic_passive` | confirmed |  |

**stockanalysis** (1 funds) — unofficial feed (no sponsor page in the collector)

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `WGMI` | CoinShares Bitcoin Mining (WGMI) | `thematic_passive` | confirmed |  |
