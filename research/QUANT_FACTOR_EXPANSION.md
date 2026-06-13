# Quant-factor expansion — what firms use beyond technical & momentum, and what we can build free

Research dossier + feasibility matrix + build roadmap. Question that started it:
*"Outside technical and momentum indicators, what else do quantitative and
investment firms use — and which of it can we obtain and add to the dashboard?"*

Method: 6 parallel web-research agents (one per factor family) against primary
sources — Fama-French, Novy-Marx, Frazzini-Pedersen (BAB), AQR (QMJ, Style
Premia), MSCI/BlackRock/Dimensional factor literature, and the Fed research
ecosystem — cross-referenced against a full audit of this repo's collectors and
engine so nothing already covered gets re-proposed. Verdicts below are graded
for THIS stack (free, static, daily, parquet-as-DB).

The headline finding: the dashboard already lives in the non-technical world
(credit OAS, breakevens, net liquidity, COT, dealer GEX, factor ETFs, on-chain
valuation, a commodity residual-shock engine). The gaps that are **free and
feasible** cluster in four places:

1. **The Fed research feed** — financial-conditions indices, growth/inflation
   nowcasts, recession-probability models, term premium, the Excess Bond
   Premium. All free on FRED/Fed-Board, all slot straight into the regime engine.
2. **Option-implied risk** — equity volatility-risk-premium, VIX term structure,
   the CBOE SKEW tail index. We do this for BTC (DVOL/VRP/skew) but not equities.
3. **Cross-sectional equity factors** — value/quality/profitability/investment/
   low-vol/BAB over the S&P 1500, buildable from **SEC EDGAR XBRL frames** (free,
   keyless) + the prices we already store. The one genuine new *feature*.
4. **Portfolio-construction overlays** — volatility targeting, drawdown control,
   realized-correlation regime, a Risk-On/Risk-Off composite. Pure compute on
   data we already hold.

---

## 1. The landscape — six families firms use outside price/momentum

### Family A — Cross-sectional equity factors (the "factor zoo")
The fundamental/balance-sheet/positioning factors behind smart-beta and quant
equity. **Value** (B/P, E/P, FCF yield, EV/EBITDA, S/P), **Quality &
profitability** (gross profitability `GP/Assets` — Novy-Marx; ROE; accruals —
Sloan; Piotroski F-score; AQR Quality-Minus-Junk), **Investment / asset growth**
(Fama-French CMA), **Low-volatility / Betting-Against-Beta** (Frazzini-Pedersen,
Sharpe ~0.78 1926-2012 ≈ 2× value), **Size** (quality-controlled — raw SMB
"basically disappeared" post-Banz), **Shareholder/buyback yield** (total payout
beats dividends-alone), **earnings revisions** (paid only), **short interest /
days-to-cover**.

Used by: Fama-French/Dimensional, AQR, Robeco, MSCI, BlackRock/iShares.
Key caveat across all of them: post-publication decay (~58%, McLean-Pontiff),
crowding, value's 2010s drawdown (intangibles break B/P), and look-ahead risk in
fundamentals (must lag to filing date).

### Family B — Multi-asset style premia & portfolio construction
The AQR "Style Premia" world. **Carry** in every asset class — FX (rate
differentials; Sharpe ~0.6-0.85 but negatively-skewed crash risk), bond/rates
carry + **term premium** + roll-down, **commodity carry / roll yield**
(backwardation earned ~7.7% vs 2.1% contango — the dominant long-run commodity
return driver), equity carry (dividend/earnings yield vs cash). **Cross-asset
value** (country CAPE, FX via REER, commodity 5y mean-reversion). **Defensive/BAB
across assets.** Portfolio construction: **risk parity / All-Weather (ERC),
volatility targeting** (Moreira-Muir: lifts Sharpe across factors), inverse-vol /
risk budgeting, **trend-following as crisis-alpha overlay** (positive in 8 of the
10 worst 60/40 drawdowns), drawdown control.

### Family C — Macro regime & nowcasting
Global-macro / Bridgewater-"economic-machine" toolkit. **Yield-curve recession
probability** (NY Fed probit on 10y-3m), **ACM term premium** (low/negative TP
mechanically inverts the curve WITHOUT signalling recession — the 2022-24 false
inversion), **Excess Bond Premium** (Gilchrist-Zakrajšek — credit-risk-appetite
orthogonal to fundamentals; forecasts activity AND asset prices), **Atlanta Fed
GDPNow** + **NY Fed/Dallas Weekly Economic Index** (real-time growth), **Cleveland
inflation nowcast + Atlanta sticky/flexible CPI** (persistent vs transitory
inflation), **Sahm rule** (concurrent labor recession confirm), **Financial
Conditions Indices** (Chicago Fed NFCI/ANFCI — 105 inputs in one z-score; Fed
Board FCI-G in growth units; St Louis/KC stress), global liquidity, a Risk-On/
Risk-Off correlation composite (KC Fed publishes one).

### Family D — Sentiment & positioning
COT **Index/percentile** normalization + the **disaggregated / TFF** reports
(dealer/asset-mgr/leveraged-fund detail vs the "blunt" legacy buckets), surveys
(NAAIM/UMich free; AAII blocked; Investors Intelligence & BofA FMS paid), options
sentiment (put/call, **CBOE SKEW**, VIX term structure, 25-delta risk reversal),
**short interest / days-to-cover** (FINRA, free), fund flows (money-market &
ICI free; EPFR/Lipper paid), **CTA / trend-follower positioning estimates**
(model-implied from price), Google Trends attention, NLP/news (RavenPack paid).

### Family E — Volatility & tail-risk premia
**Volatility/variance risk premium** (implied−realized; Bollerslev-Tauchen-Zhou),
**VIX term structure / vol carry**, **CBOE SKEW**, dispersion / implied-correlation
(partly paid), **realized correlation regime** (the 2022 stock-bond flip broke
60/40 and risk-parity together), **MOVE** (rates vol leads equity vol), vol
targeting, tail hedging / crisis alpha (Universa vs Israelov "pathetic
protection" debate — only deep-OTM continuously-rolled puts are convex).

### Family F — Alternative data
Satellite, card spend, web/app traffic, shipping/AIS — almost all vendor-only.
The free-and-obtainable slice: **EIA** petroleum/gas inventories (the single
biggest missing oil supply-shock driver per `COMMODITY_DATA_AUDIT`), **Baker
Hughes** rig count, **USDA** WASDE/NASS, **SEC EDGAR** Form-4 insider buys + 13F
institutional holdings (free, lagged — and the honest 45-day path to the
iShares/Vanguard holdings the daily feeds block), money-market/N-MFP. The rest
(satellite/card/AIS/RavenPack) is parked.

---

## 2. Feasibility matrix (this stack)

`status`: none / partial(=proxied) / full · `feas`: 🟢 free+feasible · 🟡 needs work · ⚫ paid/no

| Factor / method | Family | Status | Free source | Plugs into | Effort | Feas |
|---|---|---|---|---|---|---|
| Chicago Fed NFCI/ANFCI (+ risk/credit/leverage) | C | none | FRED `NFCI ANFCI NFCIRISK NFCICREDIT NFCILEVERAGE` | new Financial-Conditions panel; replaces home-built risk proxy | S | 🟢 |
| St Louis / KC stress | C | none | FRED `STLFSI4 KCFSI` | corroborate NFCI; risk-off alert | S | 🟢 |
| Atlanta GDPNow + Weekly Economic Index | C | none | FRED `GDPNOW WEI` | growth axis (direct nowcast) | S | 🟢 |
| Cleveland inflation nowcast / sticky-flex CPI | C | partial | FRED `STICKCPIM157SFRBATL CORESTICKM157SFRBATL FLEXCPIM157SFRBATL MEDCPIM158SFRBCLE` | inflation axis (persistent vs transitory) | S | 🟢 |
| Sahm rule + NY Fed recession prob | C | partial | FRED `SAHMREALTIME RECPROUSM156N` | recession-risk panel + alert | S | 🟢 |
| Excess Bond Premium (Gilchrist-Zakrajšek) | C | none | Fed Board `ebp_csv.csv` | recession-risk; upgrade over OAS levels | M | 🟢 |
| NY Fed ACM 10y term premium | C | none | FRED `THREEFYTP10` | term-premium-adjusted curve (fixes 2022-24 false inversion) | S | 🟢 |
| UMich sentiment + inflation expectations | D | none | FRED `UMCSENT MICH` | sentiment/inflation context | S | 🟢 |
| Fuller curve + 5y inflation leg | C | partial | FRED `DGS3MO DGS5 DGS30 T10Y3M T5YIE DFII5` | curve, gold/silver real-yield anchor | S | 🟢 |
| CBOE SKEW (tail pricing) | E/D | none | CBOE CDN `SKEW_History.csv` (1990→) | vol/risk-appetite panel; transition gate | S | 🟢 |
| Equity Volatility Risk Premium | E | none | `VIXCLS` + computed realized vol | new VRP gauge (mirrors BTC DVOL/VRP) | M | 🟢 |
| VIX term structure / vol carry | E/D | partial | `^VIX ^VIX9D ^VIX3M` (in stack) | risk-appetite regime | S | 🟢 |
| Realized stock-bond / cross-asset correlation regime | E/B | none | existing closes (SPY,TLT/IEF,sectors) | regime overlay | M | 🟢 |
| Risk-On/Risk-Off composite | C/E | partial | OAS,VIX,DXY,gold,JPY,MOVE (in stack) | single RORO gauge | M | 🟢 |
| Volatility targeting / drawdown overlay | B/E | none | pure compute | vol-scale the playbook dial | M | 🟢 |
| COT Index / percentile + disaggregated/TFF | D | partial | CFTC (already) + sibling datasets | positioning panel | M | 🟢 |
| Short interest / days-to-cover | A/D | none | FINRA Equity Short Interest (files+API) | stock library factor | M | 🟢 |
| **Cross-sectional equity factors** (value/quality/profitability/investment/accruals/Piotroski/payout) | A | partial(ETF) | **SEC EDGAR XBRL frames** + stored prices | new Factor-Rankings page + factor-regime tile | L | 🟢 |
| Betting-Against-Beta / low-vol (single-stock) | A/E | partial(ETF) | prices only (S&P 1500) | factor engine (zero new data) | M | 🟢 |
| Cross-asset / country VALUE (CAPE, REER) | B | none | Siblis/Barclays CAPE; FRED REER | global cross-asset map | M | 🟡 |
| Commodity carry / roll yield | B | none | Yahoo dated contracts | Commodity Vector driver axis | M | 🟡 |
| EIA inventories + Baker Hughes rigs | F | none | EIA API; Baker Hughes CSV | Commodity Vector supply leg | M | 🟡 |
| SEC 13F / Form-4 insider | A/F | none | SEC EDGAR | conviction layer for stock library | L | 🟡 |
| Homemade LEI diffusion + model-surprise index | C | none | FRED components | leading-diffusion panel | L | 🟡 |
| Earnings revisions / estimate momentum | A | partial | I/B/E/S, Zacks, FactSet | — | — | ⚫ |
| EPFR/Lipper flows, BofA FMS, Investors Intelligence | D | none | vendor | — | — | ⚫ |
| RavenPack NLP, retail order flow, options dispersion history | D/E | none | vendor | — | — | ⚫ |

---

## 3. Build roadmap (tiers)

**Tier 1 — Fed-research feeds → regime engine (S, 🟢).** Almost pure config: add
the FRED series above (auto-collected by `FredAdapter`), one collector each for
EBP and CBOE SKEW, then wire into `engine/inputs.py` and a new
`engine/conditions.py`. New value: a Financial-Conditions index, real-time
growth/inflation nowcasts feeding the axes, a recession-risk panel
(Sahm+probit+EBP+TP-adjusted curve), and three alerts (NFCI tightening, Sahm
trigger, EBP spike). Fixes the documented 2022-24 false-inversion problem.

**Tier 2 — option-implied risk + portfolio overlays (M, 🟢).** `engine/conditions.py`
also computes Equity VRP, VIX term-structure regime, SKEW percentile, realized
stock-bond correlation regime, and a RORO composite; the playbook exposure dial
becomes volatility-scaled; COT readings get Index/percentile normalization.

**Tier 3 — cross-sectional equity factor engine (L, 🟢).** New `collectors/edgar.py`
(XBRL frames) + `engine/equity_factors.py` computing value/profitability/
investment/accruals/payout/low-vol/BAB ranks over the S&P 1500, a new
Factor-Rankings page, and a factor-leadership tile that enriches the
macro-regime → factor-appetite narrative. Per-stock factor scores flow into the
existing stock search / watchlist.

**Parked (⚫ paid/no):** earnings-revision breadth (I/B/E/S), EPFR/Lipper,
BofA FMS, Investors Intelligence, RavenPack NLP, retail order flow, full
options-dispersion history, AAII (403-blocked). Don't fake these.

House-rule discipline applies throughout: mechanical, backtestable, split-half
validatable, free, and graceful-degrading (every new leg renormalizes away if
its source is stale — the run never crashes). Each new factor ships with its
caveat (decay/crowding/look-ahead) the way the existing signals do.

---

## 4. Key sources
- Fama-French 5-factor (2015) · Novy-Marx gross profitability (2013, NBER w15940)
- Frazzini-Pedersen "Betting Against Beta" (JFE 2014) · Asness-Frazzini-Pedersen
  "Quality Minus Junk" (RAS 2019) · Asness et al. "Size Matters If You Control
  Your Junk" (2018)
- Bollerslev-Tauchen-Zhou VRP (RFS 2009) · Moreira-Muir vol-managed portfolios (JF 2017)
- NY Fed yield-curve recession model & ACM term premium · Atlanta Fed GDPNow &
  sticky-price CPI · Cleveland Fed inflation nowcast · Chicago Fed NFCI ·
  Fed Board Excess Bond Premium / FCI-G · Sahm rule (FRED)
- SEC EDGAR XBRL APIs (`data.sec.gov/api/xbrl/frames`) · FINRA Equity Short Interest
- McLean-Pontiff factor decay (JF 2016) · Arnott et al. "Reports of Value's Death…" (FAJ 2021)
</content>
