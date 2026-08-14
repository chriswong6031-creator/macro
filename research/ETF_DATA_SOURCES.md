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
| **Roundhill** | 10 | ✅ ONE master `roundhillinvestments.com/.../FilepointRoundhill.40RU.RU_Holdings_<MMDDYYYY>.csv` covering all ~53 funds (filter `Account`) | ✅ to 2024 | **soft-404s with HTTP 200 + SPA page — validate body starts with `Date,Account`**; internal `Date` ≠ URL date; swap/option income funds (MAGS/QDTE/*W) skipped (messy tickers) |
| **Amplify** | 3 | ✅ Firestore doc-per-date `firestore.googleapis.com/v1/projects/amplify-etfs-data-feed/.../funds/<T>/holdings` | ✅ ~10.5 months (180 dated docs) | needs `AMPLIFY_FIREBASE_KEY` — the sponsor's PUBLIC web key, already in daily.yml's secrets; a worktree does not inherit the root `.env`, which is the only reason W2 read it as unset |
| SSGA / SPDR | 20 | ❌ current-only XLSX | forward only | verified daily, no date in URL, no Wayback |
| Invesco | 5 | ❌ (API `interval=monthly`, latest only) | forward only | idType=cusip reliable |

Fund counts above are the 2026-08-12 universe. Full per-sponsor inventory
(14 sponsors, 106 universe funds + ARKK/ARKW): `config.yml` `etf_holdings.universe`
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
- ~~**Amplify**~~ — ADDED 2026-08-12 (W3, below). The "current-only, same Filepoint
  master as Roundhill" reading in this D72 row was wrong: Amplify serves a Firebase
  **Firestore** feed with one dated document per fund per day, ~10.5 months deep.

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
  swap wrapper, or a foreign-listed basket. **NCLD** was rejected here and is
  **ADMITTED 2026-08-12 (W3, below)** on a declared `nav_equity_frac` — the mechanism
  that reads a partial-NAV equity sleeve as complete instead of as a broken parse. The
  rest stand: **DRAM** (Korea/Taiwan/Japan
  memory names + a Micron swap), **LYTE** (China A-share optics + 27% T-bill),
  **UX** (uranium via swaps on a physical trust), **LOHA** (102 clean US names but a
  broad multi-sector basket, not a theme).
- **SOXQ (Invesco)** — needs a CUSIP (`idType=ticker` 500s); both the product page and
  the profile API return **406** without a real browser. Semis are covered by
  SMHX/FTXL/XSD/SMH/PSI.
- **QTUM (Defiance, incumbent)** — every dated XLSX in the probe window returns **403**.
  Not a parser bug; the sponsor is blocking. QTUM has zero snapshots on disk and will
  keep collecting nothing until someone gets past that WAF. **Left broken — flagged,
  not fixed.**
- ~~**Amplify (SILJ, BATT)**~~ — **ADMITTED 2026-08-12 (W3, below).** The block was
  never a missing secret: the key has been in the repo-root `.env` and in daily.yml's
  secrets since 2026-07-18, and a git worktree does not inherit a gitignored `.env`.
  360 dated snapshots landed on the first re-probe.

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

**roundhill** (10 funds) — Roundhill — MIXED: index funds pre-2024, actively-managed thematics after

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
| `NCLD` | Roundhill Neocloud | `active` | confirmed | W3 add; prospectus says "actively-managed", quarterly rebalance. Only fund carrying `nav_equity_frac` (0.63). |

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

**amplify** (3 funds) — Amplify — BLOK is actively managed; SILJ/BATT are index products

| Fund | Fund name | Type | Verdict | Note |
|---|---|---|---|---|
| `BLOK` | Amplify Transformational Data Sharing | `active` | confirmed |  |
| `SILJ` | Amplify Junior Silver Miners | `thematic_passive` | confirmed | W3 add; tracks the Nasdaq Junior Silver Miners Index. |
| `BATT` | Amplify Lithium & Battery Technology | `thematic_passive` | confirmed | W3 add; tracks the EQM Lithium & Battery Technology Index ("not actively managed"). |

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


---

# 2026-08-12 — W3: the two data-expansion leads W2 left open

W2 closed with two named leads (§"Probed and REJECTED", above): Amplify's SILJ/BATT
blocked on a key, and Roundhill's NCLD — the most on-theme fund found anywhere —
blocked on a swap sleeve. Both are now on the board. Universe **103 → 106** funds
(105 → 108 counting ARKK/ARKW). Same rule as W2: a fund ships ONLY because a real
snapshot parsed and landed on disk.

## Lead 1 — Amplify SILJ + BATT: the block was a worktree, not a secret

`AMPLIFY_FIREBASE_KEY` had been set the whole time — in the repo-root `.env` since
2026-07-18 and in `daily.yml`'s repo secrets, which is why the incumbent BLOK has
17 snapshots on disk. What W2 actually hit is that **a git worktree does not inherit
`.env`**: it is gitignored, so `git worktree add` never copies it, and
`lib/config.py:_load_dotenv` reads `<checkout>/.env`. A probe run from a build
worktree therefore reports every keyed sponsor as unset. Fixes, so it cannot recur:
the key is now listed in the committed `.env.example` with the worktree caveat, and
`config.yml`'s Amplify block says it out loud. Local recipe:
`set -a && . ../../../.env && set +a`.

The D72 row calling Amplify "current-only, same Filepoint master as Roundhill" was
also simply wrong. Amplify serves a **Firebase Firestore** feed, one dated document
per fund per day: `.../funds/<TICKER>/holdings?mask.fieldPaths=asOfDate` lists the
dates, `.../holdings/<date>` returns the file. 180 dated docs per fund,
2025-09-25 → 2026-08-12 — **deeper than any source on the board except Global X**.

| Fund | Fund name | Theme | Type | as_of | rows | Σ weight | US-listed wt |
|---|---|---|---|---|---|---|---|
| SILJ | Amplify Junior Silver Miners | precious-miners | thematic_passive | 2026-08-12 | 64 | 99.82% | 73.57% |
| BATT | Amplify Lithium & Battery Technology | critical-minerals | thematic_passive | 2026-08-12 | 51 | 99.60% | 29.77% |

Both are index-tracking off the sponsor's own fund page (SILJ → Nasdaq Junior Silver
Miners Index; BATT → EQM Lithium & Battery Technology Index, "The Fund is not
actively managed"), so both register `thematic_passive` = flow-primary.

**Backfilled 180 snapshots each** (2025-09-25 → 2026-08-12, 2.4 MB total). Every one
re-validated end-to-end: exact `[ticker,name,weight_pct,shares,market_value,as_of]`
schema, >5 rows, weight sum in bounds, no null shares, `as_of` == filename.
SILJ ranges 53–64 rows / 98.93–101.73%; BATT 50–53 rows / 98.65–100.07%.

**Joinability** — the bar NIKL failed in W2 (2.7% US-listed against a ≥11.9%
incumbent floor). SILJ carries 72.67–80.72% of weight in US-listed lines over the
full backfill and BATT 28.60–34.06%, so both clear it; BATT sits between COPX
(11.90%) and LIT (37.11%). Measured with the same rule that reproduces W2's
published COPX/LIT/GDX numbers exactly.

## Lead 2 — NCLD: `nav_equity_frac`, a declared partial-NAV sleeve

Roundhill's NCLD (inception 2026-08-06, **actively managed**, quarterly rebalance)
holds its CoreWeave/Nebius exposure twice: once as ordinary shares and once as total
return swaps, because the RIC diversification tests cap the direct position. With the
non-equity lines dropped, a perfectly parsed snapshot sums to ~63% of NAV — and the
weight-sum sanity guard, whose entire job is to reject a snapshot that sums far from
100, quarantined all of them. That is what "would trip a weight-sum sanity guard"
meant in W2, and it is now a declared quantity:

```yaml
NCLD: {sponsor: roundhill, active: true, nav_equity_frac: 0.63, ...}
```

`engine/holdings_signals.py::weight_sum_bounds(fund)` scales `WEIGHT_SUM_BOUNDS`
**relatively** by the declaration — NCLD is checked against 50.4–75.6 instead of
80–120, so the tolerance stays ±20% *of the sleeve* rather than growing looser as
the sleeve shrinks. Absent (every other fund), the fraction is 1.0 and nothing moves;
a declaration outside (0, 1] falls back to 1.0 rather than opening the guard.

Three properties are deliberate and pinned by `tests/test_etf_partial_nav_sleeve.py`:

1. **Declared, never derived.** A fraction computed from the snapshot it checks could
   not fail. This one can: if the sponsor's sleeve mix drifts off 0.63, every NCLD
   snapshot quarantines loudly and a human re-declares.
2. **It relaxes the guard, it does not remove it.** A genuinely broken NCLD parse is
   still quarantined and still printed as a `::warning`.
3. **The verdict reaches the ranked consumer.** `engine/etf_consensus.py`'s sparkline
   gate takes the fund too — otherwise the picture would quarantine the snapshots the
   numbers beside it accepted.

| Fund | Fund name | Theme | Type | as_of | rows | Σ weight | bounds |
|---|---|---|---|---|---|---|---|
| NCLD | Roundhill Neocloud | data-center | active | 2026-08-12 | 15 | 63.00% | 50.4–75.6 |

5 snapshots (2026-08-06 → 2026-08-12, the fund's whole life), 14–15 rows,
Σ weight **61.55–64.40%** — the declaration is well-centred with room either side.

**Disclosed cost.** The swap legs are dropped (their "shares" are swap units, not a
float claim), so the board reads CRWV at 9.15% and NBIS at 9.07% while NCLD's real
economic exposure to each is ~27.7% / ~27.5%. Folding swap notionals into the equity
line would publish an aggregation the sponsor never reported, so the understatement
is recorded here and in `config.yml` instead. DRAM/LYTE stay rejected on the *other*
half of their W2 verdict — foreign-listed baskets — which `nav_equity_frac` does not
address.

## The sleeve that was leaking into 13 other funds

Shipping NCLD's equity sleeve required `is_non_equity_holding` to actually recognise
a sleeve, and it did not. Two forms walked past it — the same defect class as the
`-USD CASH-` line W2 fixed (masterplan §6b), where a cash balance sitting in the
SUM-ratio denominator made SMH publish a phantom +5.12% on every constituent.

**(a) Government money-market sweeps.** `FGXXX` "First American Government
Obligations Fund" and `AGPXX` "Invesco Government & Agency Portfolio" have real
tickers and names that say neither "cash" nor "money market". They are $1-NAV funds:
on the live feed their `shares` equals their `market_value` **exactly** (METV FGXXX
1,722,754.52 / 1,722,754.52), i.e. the share count IS a dollar balance. In METV that
balance was **18.9% of the fund's total share count at 0.81% of its weight**.

Blast radius, measured across every tracked fund's shipped window — 14 rows in 14
funds change verdict (all of them FGXXX/AGPXX; no real equity moves), and 13 funds'
published common-scale factor moves, **6 of them at or over the 5% alert bar**:

| Fund | scale now | scale fixed | phantom on every constituent |
|---|---|---|---|
| METV | 1.4164 | 1.1688 | **+21.18%** |
| MEME | 0.6404 | 0.7619 | **−15.94%** |
| NERD | 1.1492 | 1.0833 | +6.09% |
| UFO | 0.9388 | 0.8877 | +5.76% |
| HUMN | 0.9902 | 1.0446 | −5.20% |
| PHO | 1.0430 | 0.9924 | +5.10% |
| BLOK | 1.0263 | 0.9797 | +4.76% |
| PSI | 1.0583 | 1.0122 | +4.56% |
| BETZ | 1.1247 | 1.1711 | −3.96% |
| OZEM · CHAT · PPA · CABZ | | | +1.25% · +0.85% · −0.60% · −0.21% |

**(b) A swap line the name cannot give away.** Roundhill files the same TRS two ways
depending on the date: `21873S108 TRS 090827 GS` named `COREWEAVE, INC.-SWAP-GOLD-L`
(caught by the existing `\bswap\b` name pattern) and, on other dates, `21873S108 SWP`
whose **name column merely repeats the ticker**. The second form survived as a 16.38%
and a 20.38% phantom equity constituent. It is now matched structurally: a
`SWP`/`SWAP`/`TRS` token *beside another token* in the ticker. NCLD is the only fund
on the board that carries it today.

Both patterns are anchored narrowly on purpose. A loose `bill|liquidity|treasury|trs`
rule would silently delete **BILL Holdings** (XSW/FINX/MDY), **Liquidity Services**
(EBIZ), Treasury Wine and TriMas (ticker `TRS`) from the board — every one of those is
a live case in `tests/test_etf_partial_nav_sleeve.py`, alongside a mutation check that
each rule is load-bearing.

## Theme coverage after W3
precious-miners gains SILJ (GDX/GDXJ/SIL/SGDM/SGDJ/SLVR/GBUG/**SILJ**) ·
critical-minerals gains BATT (REMX/XME/LIT/COPX/COPP/LITP/SETM/COPJ/EMET/METL/**BATT**) ·
data-center doubles to two funds (DTCR/**NCLD**). Still thin: **drones**, and
**defense** (SHLD/PPA/XAR/ARKX unchanged).
