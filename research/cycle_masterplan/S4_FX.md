# S4 — FX / Local-Currency Feasibility for Country Cycles

Scout date: 2026-07-02  
Repo root: /tmp/macro-cycle-fable-main/  
Canonical engine: engine/country_cycles.py

---

## 1. Engine design — explicit USD-denomination choice

engine/country_cycles.py lines 5-8 state the design intent verbatim:

> "USD denomination is the deliberate choice: it is a US investor's actual experience,
> strips out local-FX noise, and lets every market overlay cleanly on one shared rebased axis."

The engine has **zero FX decomposition logic today**. All cycle math runs on the ETF USD close stored in data/yahoo/<TICKER>.parquet. This is not an omission — it is documented design.

---

## 2. Full universe

### 2a. Countries (24 ETFs) — engine/country_cycles.py lines 48-78

| ETF   | Country        | Region            | Dev | Local FX pair  | Yahoo FX ticker | FX data location         | Rows / date range                 |
|-------|---------------|-------------------|-----|----------------|-----------------|--------------------------|-----------------------------------|
| EWG   | Germany        | Europe            | DM  | EUR            | EURUSD=X        | data/yahoo/EURUSD_X      | 5861 rows 2003-12-01→2026-07-02   |
| EWU   | UK             | Europe            | DM  | GBP            | GBPUSD=X        | data/yahoo/GBPUSD_X      | 5875 rows 2003-12-01→2026-07-02   |
| EWQ   | France         | Europe            | DM  | EUR            | EURUSD=X        | data/yahoo/EURUSD_X      | (same as EWG)                     |
| EWL   | Switzerland    | Europe            | DM  | CHF            | USDCHF=X        | data/yahoo/USDCHF_X      | 5931 rows 2003-09-17→2026-07-02   |
| EWP   | Spain          | Europe            | DM  | EUR            | EURUSD=X        | data/yahoo/EURUSD_X      | (same as EWG)                     |
| EWI   | Italy          | Europe            | DM  | EUR            | EURUSD=X        | data/yahoo/EURUSD_X      | (same as EWG)                     |
| EWN   | Netherlands    | Europe            | DM  | EUR            | EURUSD=X        | data/yahoo/EURUSD_X      | (same as EWG)                     |
| EWD   | Sweden         | Europe            | DM  | SEK            | USDSEK=X        | **ABSENT** in both stores | FRED DEXSDUS available (1971->)   |
| EWJ   | Japan          | Developed ex-EU   | DM  | JPY            | USDJPY=X        | data/yahoo/USDJPY_X AND data/intl/USDJPY_X | 7700 rows 1996-10-30→2026-07-02 |
| EWA   | Australia      | Developed ex-EU   | DM  | AUD            | AUDUSD=X        | data/yahoo/AUDUSD_X AND data/intl/AUDUSD_X | 5242 rows 2006-05-16→2026-07-02 |
| EWH   | Hong Kong      | Developed ex-EU   | DM  | HKD (peg)      | USDHKD=X        | data/hk/HKD_X (6324 rows 2001-07-16→2026-07-02) | **not in yahoo store** |
| EWS   | Singapore      | Developed ex-EU   | DM  | SGD            | USDSGD=X        | **ABSENT** in all stores  | FRED DEXSIUS available (1981->)   |
| EWC   | Canada         | Developed ex-EU   | DM  | CAD            | USDCAD=X        | data/yahoo/USDCAD_X      | 5934 rows 2003-09-17→2026-07-02   |
| FXI   | China          | EM Asia           | EM  | CNY (onshore) / CNH (offshore) | CNH=F | data/yahoo/CNH_F (3299 rows 2013-02-11→2026-07-02); CNH_X = 16 rows (useless); FRED DEXCHUS = 11348 rows 1981-01-02→2026-06-18 | |
| INDA  | India          | EM Asia           | EM  | INR            | USDINR=X        | data/intl/USDINR_X       | 5859 rows 2003-12-01→2026-07-02   |
| EWT   | Taiwan         | EM Asia           | EM  | TWD            | USDTWD=X        | data/intl/USDTWD_X       | 5367 rows 2004-03-24→2026-07-02   |
| EWY   | South Korea    | EM Asia           | EM  | KRW            | USDKRW=X        | data/intl/USDKRW_X       | 5860 rows 2003-12-01→2026-07-02   |
| EIDO  | Indonesia      | EM Asia           | EM  | IDR            | USDIDR=X        | **ABSENT** in all stores  | FRED DEXIDUS available (1997->)   |
| EWZ   | Brazil         | EM LatAm          | EM  | BRL            | USDBRL=X        | data/yahoo/USDBRL_X      | 5447 rows 2003-12-01→2026-07-01   |
| EWW   | Mexico         | EM LatAm          | EM  | MXN            | USDMXN=X        | data/yahoo/USDMXN_X      | 5885 rows 2003-12-01→2026-07-02   |
| ECH   | Chile          | EM LatAm          | EM  | CLP            | USDCLP=X        | **ABSENT** in all stores  | No FRED DEX; Yahoo only           |
| EZA   | South Africa   | EM EMEA           | EM  | ZAR            | USDZAR=X        | **ABSENT** in all stores  | FRED DEXSFUS available (1995->)   |
| TUR   | Turkey         | EM EMEA           | EM  | TRY            | USDTRY=X        | **ABSENT** in all stores  | No FRED DEX; Yahoo only           |
| EPOL  | Poland         | EM EMEA           | EM  | PLN            | USDPLN=X        | **ABSENT** in all stores  | FRED DEXPOUS available (1999->)   |

### 2b. Aggregates / blocs (7 ETFs) — engine/country_cycles.py lines 82-90

| ETF   | Name             | Underlying index            |
|-------|------------------|-----------------------------|
| EFA   | Developed ex-US  | MSCI EAFE                   |
| VGK   | Europe           | FTSE Dev. Europe            |
| VPL   | Developed Pacific| FTSE Dev. Pacific           |
| EEM   | Emerging Markets | MSCI EM                     |
| AAXJ  | Asia ex-Japan    | MSCI AC Asia ex-JP          |
| ILF   | Latin America    | S&P Latin America 40        |
| VXUS  | All-World ex-US  | FTSE Global ex-US           |

All 7 bloc ETFs have parquet files present in data/yahoo/ (confirmed by ls).

---

## 3. FX data stores — what exists and where

### data/yahoo/ FX files (collected by collectors/yahoo.py, config.yml yahoo.tickers.fx)
Config line: `fx: ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "USDMXN=X", "USDBRL=X", "CNH=X", "CNH=F"]`

Present parquets:
- AUDUSD_X.parquet — 5242 rows 2006-05-16→2026-07-02
- EURUSD_X.parquet — 5861 rows 2003-12-01→2026-07-02
- GBPUSD_X.parquet — 5875 rows 2003-12-01→2026-07-02
- USDBRL_X.parquet — 5447 rows 2003-12-01→2026-07-01
- USDCAD_X.parquet — 5934 rows 2003-09-17→2026-07-02
- USDCHF_X.parquet — 5931 rows 2003-09-17→2026-07-02
- USDJPY_X.parquet — 7700 rows 1996-10-30→2026-07-02
- USDMXN_X.parquet — 5885 rows 2003-12-01→2026-07-02
- CNH_X.parquet — **16 rows only** (2026-06-12→2026-07-02; effectively empty/current-only)
- CNH_F.parquet — 3299 rows 2013-02-11→2026-07-02 (offshore CNH futures; usable)

### data/intl/ FX files (collected by collectors/intl_prices.py, config.yml intl.countries)
Covers only the 7 macro-entity countries defined in config intl.countries (JP/KR/TW/IN/AU/GB/EZ):
- USDJPY_X.parquet — 7698 rows 1996-10-30→2026-07-02 (duplicate of yahoo)
- USDKRW_X.parquet — 5860 rows 2003-12-01→2026-07-02
- USDTWD_X.parquet — 5367 rows 2004-03-24→2026-07-02
- USDINR_X.parquet — 5859 rows 2003-12-01→2026-07-02
- AUDUSD_X.parquet — 5240 rows 2006-05-16→2026-07-02 (duplicate of yahoo)
- EURUSD_X.parquet — 5860 rows 2003-12-01→2026-07-02 (duplicate of yahoo)
- GBPUSD_X.parquet — 5874 rows 2003-12-01→2026-07-02 (duplicate of yahoo)

### data/intl/ local-currency index files (also from collectors/intl_prices.py)
Present: _N225, _KS11, _TWII, _FTSE, _GDAXI, _FCHI, _STOXX, _STOXX50E, _NSEI, _AXJO, _BSESN, _FTMC, _INTLC

### data/hk/ FX
- HKD_X.parquet — 6324 rows 2001-07-16→2026-07-02 (collected by hk collectors, USDHKD=X)

### data/fred/ FRED DEX series present
DEXBZUS(BRL 1995->), DEXCAUS(CAD 1971->), DEXCHUS(CNY 1981->), DEXJPUS(JPY 1971->),
DEXMXUS(MXN 1993->), DEXSZUS(CHF 1971->), DEXUSAL(AUD 1971->), DEXUSEU(EUR 1999->), DEXUSUK(GBP 1971->)

---

## 4. Forex engine coverage vs country_cycles universe

The forex engine (engine/forex_*.py, config.yml forex.active) covers 9 pairs:
`EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, USDMXN, USDBRL, USDCNH`

Cross-reference with the 24 country ETFs:

| Coverage | ETFs | Notes |
|----------|------|-------|
| **FULL** — forex engine data + data/yahoo tape | EWG, EWU, EWQ, EWP, EWI, EWN (EUR); EWJ (JPY); EWA (AUD); EWL (CHF); EWC (CAD); EWZ (BRL); EWW (MXN) | 12 of 24; all G10 majors |
| **PARTIAL** — FX tape present but NOT in forex engine | FXI (CNH_F 2013->; FRED CNY 1981->); INDA (USDINR intl store); EWT (USDTWD intl store); EWY (USDKRW intl store); EWH (USDHKD hk store) | 5 of 24 |
| **ABSENT** — no FX tape anywhere in the repo | EWD (SEK); EWS (SGD); EIDO (IDR); ECH (CLP); EZA (ZAR); TUR (TRY); EPOL (PLN) | 7 of 24 |

---

## 5. Local-currency index tape availability

Free via Yahoo Finance (yfinance already used by intl_prices collector):

| Country ETF | Local index Yahoo ticker | Status in data/intl/ |
|-------------|--------------------------|----------------------|
| EWG Germany | ^GDAXI | PRESENT (_GDAXI 9735 rows 1987->) |
| EWU UK | ^FTSE | PRESENT (_FTSE 10734 rows 1984->) |
| EWQ France | ^FCHI | PRESENT (_FCHI 9227 rows 1990->) |
| EWL Switzerland | ^SSMI | ABSENT |
| EWP Spain | ^IBEX | ABSENT |
| EWI Italy | ^FTSEMIB | ABSENT |
| EWN Netherlands | ^AEX | ABSENT |
| EWD Sweden | ^OMX or ^OMXS30 | ABSENT |
| EWJ Japan | ^N225 | PRESENT (_N225 15117 rows 1965->) |
| EWA Australia | ^AXJO | PRESENT (_AXJO 8495 rows 1992->) |
| EWH Hong Kong | ^HSI | ABSENT |
| EWS Singapore | ^STI | ABSENT |
| EWC Canada | ^GSPTSE | ABSENT |
| FXI China | 000001.SS | ABSENT |
| INDA India | ^NSEI | PRESENT (_NSEI 4608 rows 2007->) |
| EWT Taiwan | ^TWII | PRESENT (_TWII 7106 rows 1997->) |
| EWY South Korea | ^KS11 | PRESENT (_KS11 7275 rows 1996->) |
| EIDO Indonesia | ^JKSE | ABSENT |
| EWZ Brazil | ^BVSP | ABSENT |
| EWW Mexico | ^MXX | ABSENT |
| ECH Chile | ^IPSA | ABSENT |
| EZA South Africa | ^JTOPI or ^J203.JO | ABSENT |
| TUR Turkey | ^XU100 | ABSENT |
| EPOL Poland | ^WIG20 | ABSENT |

All absent tickers are plausibly available via yfinance (same mechanism as existing _N225, ^KS11 etc.).
The intl_prices collector (collectors/intl_prices.py) already handles this pattern exactly — it just needs
these tickers added to config.yml intl.countries.

---

## 6. Bloc/aggregate FX decomposition — feasibility

The 7 bloc ETFs (EFA, VGK, VPL, EEM, AAXJ, ILF, VXUS) aggregate dozens of markets with time-varying
country weights. FX decomposition for a bloc is **not well-defined** without the current holdings file.

Analysis:
- EFA (MSCI EAFE): ~60% EUR+GBP+JPY. A weighted EUR/GBP/JPY composite is plausible but imprecise.
- VGK (Europe): ~85% EUR zone + GBP. EUR dominates; CHF and SEK present.
- VPL (Pacific): ~57% JPY, ~22% AUD, rest SGD/HKD. JPY-dominated.
- EEM (MSCI EM): China ~27%, Taiwan ~17%, India ~14%, Korea ~12% as of recent weights. No single FX.
- AAXJ (Asia ex-JP): China+Taiwan+India+Korea together >80%. No single FX.
- ILF (LatAm 40): Brazil ~60%, Mexico ~25%. BRL+MXN approximate.
- VXUS (All-World ex-US): broadest basket; FX decomposition is portfolio analytics, not a scalar.

**Recommendation**: For blocs, do NOT attempt FX decomposition in the engine. The USD-ETF price IS the
return as experienced. If designers want FX attribution for blocs, recommend a holdings-weighted
approximation displayed separately (display-only annotation, not a cycle input).

---

## 7. Existing forex engine reuse potential

The forex engine (engine/forex_inputs.py + engine/forex_regime.py) manages:
- Price loading from data/yahoo and data/fred (with inversion logic for USD-base quotes)
- Carry, REER, COT, and regime overlay

For FX decomposition in country_cycles, only the **price loading** function is reusable:
`engine/forex_inputs.load_price(meta)` at forex_inputs.py line 58. It handles inversion
(`meta['invert']`), FRED fallback when Yahoo is shallow, and outputs a clean OHLC frame.

The regime/conviction/carry layers of the forex engine are NOT needed for a cycle-page
FX decomposition — that only requires dividing the ETF USD return by the FX return to back out
the local-currency return.

Math: `lc_return = usd_etf_return / (1 + fx_return)` where fx_return = change in foreign-per-USD.

---

## 8. FX sources for the 7 absent pairs

All 7 absent currencies are fetchable free via yfinance (same as existing collection):

| Currency | Yahoo ticker | FRED fallback | Notes |
|----------|-------------|---------------|-------|
| SEK | USDSEK=X | DEXSDUS (1971->, not yet collected) | Nordic DM, liquid |
| SGD | USDSGD=X | DEXSIUS (1981->, not yet collected) | Pegged band; de-facto managed |
| IDR | USDIDR=X | DEXIDUS (1997->, not yet collected) | EM; 1997 crisis gap risk |
| CLP | USDCLP=X | No FRED DEX series | Yahoo only; 2000-> plausible |
| ZAR | USDZAR=X | DEXSFUS (1995->, not yet collected) | Volatile; 1995 start sufficient |
| TRY | USDTRY=X | No FRED DEX series | Yahoo only; history truncated by redenomination |
| PLN | USDPLN=X | DEXPOUS (1999->, not yet collected) | Eurozone candidate; liquid |

Special case — **HKD**: USDHKD=X available on Yahoo. data/hk/HKD_X.parquet exists (6324 rows, 2001->).
HKD is a hard peg (7.75–7.85 band). FX decomposition for EWH is meaningful only during peg-stress
episodes; the FX contribution is near-zero otherwise. Recommend treating EWH local return ≈ USD return
with a peg-distance annotation.

---

## 9. Summary: per-market feasibility table

| ETF | Currency | FX tape in repo | LC index in repo | Decomp feasibility |
|-----|----------|-----------------|------------------|--------------------|
| EWG | EUR | PRESENT (yahoo+intl) | PRESENT (^GDAXI) | HIGH — both tapes present |
| EWU | GBP | PRESENT (yahoo+intl) | PRESENT (^FTSE) | HIGH |
| EWQ | EUR | PRESENT (yahoo+intl) | PRESENT (^FCHI) | HIGH |
| EWL | CHF | PRESENT (yahoo) | ABSENT (^SSMI) | MEDIUM — FX present; LC index needs collect |
| EWP | EUR | PRESENT (yahoo+intl) | ABSENT (^IBEX) | MEDIUM |
| EWI | EUR | PRESENT (yahoo+intl) | ABSENT (^FTSEMIB) | MEDIUM |
| EWN | EUR | PRESENT (yahoo+intl) | ABSENT (^AEX) | MEDIUM |
| EWD | SEK | **ABSENT** | ABSENT (^OMXS30) | LOW — both need new collect |
| EWJ | JPY | PRESENT (yahoo+intl) | PRESENT (^N225) | HIGH |
| EWA | AUD | PRESENT (yahoo+intl) | PRESENT (^AXJO) | HIGH |
| EWH | HKD | PRESENT (hk store) | ABSENT (^HSI) | MEDIUM — peg; FX contrib ~0 |
| EWS | SGD | **ABSENT** | ABSENT (^STI) | LOW — both need new collect |
| EWC | CAD | PRESENT (yahoo) | ABSENT (^GSPTSE) | MEDIUM — FX present; LC index needs collect |
| FXI | CNY/CNH | PARTIAL (CNH_F 2013->; FRED CNY 1981->) | ABSENT (000001.SS) | MEDIUM — FX history only 2013 in Yahoo |
| INDA | INR | PRESENT (intl store) | PRESENT (^NSEI 2007->) | HIGH (post-2007 only) |
| EWT | TWD | PRESENT (intl store) | PRESENT (^TWII 1997->) | HIGH |
| EWY | KRW | PRESENT (intl store) | PRESENT (^KS11 1996->) | HIGH |
| EIDO | IDR | **ABSENT** | ABSENT (^JKSE) | LOW — both need new collect |
| EWZ | BRL | PRESENT (yahoo) | ABSENT (^BVSP) | MEDIUM — FX present; LC index needs collect |
| EWW | MXN | PRESENT (yahoo) | ABSENT (^MXX) | MEDIUM |
| ECH | CLP | **ABSENT** | ABSENT (^IPSA) | LOW — both need new collect; no FRED fallback |
| EZA | ZAR | **ABSENT** | ABSENT (^JTOPI) | LOW — both need new collect |
| TUR | TRY | **ABSENT** | ABSENT (^XU100) | LOW — both need new collect; no FRED fallback |
| EPOL | PLN | **ABSENT** | ABSENT (^WIG20) | LOW — both need new collect |
| EFA | basket | N/A (multi-FX) | N/A (multi-country) | NOT DEFINED — see §6 |
| VGK | basket | N/A | N/A | NOT DEFINED |
| VPL | basket | N/A | N/A | NOT DEFINED |
| EEM | basket | N/A | N/A | NOT DEFINED |
| AAXJ | basket | N/A | N/A | NOT DEFINED |
| ILF | basket | N/A | N/A | NOT DEFINED |
| VXUS | basket | N/A | N/A | NOT DEFINED |

---

## 10. Collection gap to close (for HIGH/MEDIUM feasibility upgrade)

**Add to config.yml yahoo.tickers.fx** (8 new pairs; all fetchable via existing yahoo.py collector):
`USDSEK=X, USDSGD=X, USDIDR=X, USDCLP=X, USDZAR=X, USDTRY=X, USDPLN=X, USDHKD=X`

**Add to config.yml intl.countries** (or a new country_cycles section in config) for local LC indices:
`^SSMI, ^IBEX, ^FTSEMIB, ^AEX, ^OMXS30, ^STI, ^GSPTSE, ^HSI, ^JKSE, ^BVSP, ^MXX, ^IPSA, ^JTOPI, ^XU100, ^WIG20, 000001.SS`

**FRED DEX** series to add to fred collector for FRED-fallback depth (optional; Yahoo=X is primary):
`DEXSDUS(SEK), DEXSIUS(SGD), DEXSFUS(ZAR), DEXIDUS(IDR), DEXPOUS(PLN), DEXKOUS(KRW-already intl), DEXTAUS(TWD-already intl), DEXINUS(INR-already intl)`

**No code changes needed in intl_prices.py** — it already generalises via config.yml intl.countries.
The collector uses `c["fx"]` and `c["index"]` per country; adding entries to config is sufficient.

---

## 11. Key facts confirmed by file inspection

- engine/country_cycles.py lines 5-8: USD denomination is **explicit documented design choice**
- All 31 ETFs (24 countries + 7 blocs) have parquet files in data/yahoo/ (confirmed by ls)
- data/yahoo/ has 8 FX pairs collected, all from forex engine board (config.yml forex.active)
- data/intl/ has 7 FX pairs for the 7 macro-entity countries (intl_prices.py → intl store)
- data/hk/HKD_X.parquet exists (6324 rows; fetched by hk_prices/hkma collectors)
- data/intl/ has 13 local-currency index files (from intl_prices.py ^N225, ^KS11, ^TWII, ^FTSE, ^GDAXI, ^FCHI, ^STOXX, ^STOXX50E, ^NSEI, ^AXJO, ^BSESN, ^FTMC, ^INTLC)
- 7 FX pairs entirely absent (SEK/SGD/IDR/CLP/ZAR/TRY/PLN); all fetchable via USDXXX=X on Yahoo
- engine/forex_inputs.py load_price() is reusable for FX decomp math; regime/conviction layers are not needed
- CNH_X (spot) is effectively empty (16 rows); CNH_F (futures) has 3299 rows from 2013
