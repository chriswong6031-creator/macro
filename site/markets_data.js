/* markets_data.js — Global Market Cycles Dashboard · REAL web-sourced dataset
   9 national equity-market bull/bear cycles. Each turn carries its real closing
   LEVEL (v) and drawdown (draw); `now` carries the live level / % off ATH / returns;
   `valuation` carries P/E, CAPE, yield. Researched + adversarially verified via web
   (workflow market-cycles-REAL), as of ~2026-06-25. */
(function(){
  "use strict";
  window.MARKET_META = {
  "asOf": "2026-07-16",
  "today": 2026.48,
  "xDomain": [
    2000,
    2031
  ],
  "regime": {
    "label": "Records Up Top, Two-Speed World",
    "sub": "AI-led peaks, EM laggards diverge",
    "headline": "Most developed equity markets sit at or just below record highs in mid-2026, led by an AI-fueled, weak-yen blow-off in Japan and record runs in the US, Europe and Taiwan, while the laggards (Hong Kong, India) correct hard off earlier peaks and China grinds higher on stimulus without euphoria. The US alone is ~75% of world market cap and trades near 25x forward earnings, an extreme that makes global breadth deceptively narrow under the cap-weighted surface. The backdrop turned less friendly: under new Chair Warsh the Fed held at 3.50-3.75% for a fourth meeting but flipped its dot plot toward a hike, with the 10Y near 4.4-4.5% and DXY at a one-year high around 101.6.",
    "stats": [
      {
        "k": "S&P 500 fwd P/E",
        "v": "~24-25x",
        "note": "Record ~7,600; well above the ~18x long-run average"
      },
      {
        "k": "US % of MSCI ACWI",
        "v": "~75%",
        "note": "Up from ~63% end-2023; cap-weight concentration extreme"
      },
      {
        "k": "US 10Y yield",
        "v": "~4.4-4.5%",
        "note": "Higher-for-longer; hawkish dot-plot flip"
      },
      {
        "k": "DXY",
        "v": "~101.6",
        "note": "One-year high on rate-differential + safe-haven bid"
      },
      {
        "k": "Fed funds",
        "v": "3.50-3.75%",
        "note": "4th hold; median dot now 3.8% (a hike on the table)"
      },
      {
        "k": "ACWI fwd EPS growth",
        "v": "~24%",
        "note": "Q1 earnings +24% y/y; growth doing the heavy lifting"
      }
    ],
    "tilt": "The tape rewards confirmation, not prophecy: the AI/record cohort (US, Japan, Taiwan, Europe) is extended and increasingly rate- and concentration-sensitive, so the late-June tech wobble is the kind of crack to respect rather than fade blindly. The cleaner asymmetry sits in the not-yet-euphoric expanders (China on stimulus, UK still cheap at ~13x) and in mean-reversion candidates among the correctors (Hong Kong, India) once they stop making lower lows. With a hawkish Fed, a firm dollar, and 4.5% cash competing, lean toward quality and valuation discipline over chasing the blow-off.",
    "asOfNote": "Figures are web-sourced and approximate as of ~June 2026."
  }
};
  window.MARKET_PHASES = {
    Trough:    { label: "Trough",    short: "Bottoming",   hue: "#e06464" },
    Recovery:  { label: "Recovery",  short: "Early up",    hue: "#45b873" },
    Expansion: { label: "Expansion", short: "Trending up", hue: "#3da564" },
    Peak:      { label: "Peak",      short: "Topping",     hue: "#e0a030" },
    Downturn:  { label: "Downturn",  short: "Rolling over", hue: "#e0556b" }
  };
  window.MARKETS = [
  {
    "id": "us",
    "name": "United States / S&P 500",
    "short": "US",
    "group": "North America",
    "accent": "#3b82f6",
    "proxy": "S&P 500 (SPX) · NYSE breadth",
    "archetype": "The S&P 500 cycle is driven by the interaction of corporate earnings, the Fed liquidity/rate regime, and the dominant secular theme (tech/telecom in 2000, housing/credit in 2007, mega-cap platforms and AI today). Bull markets are powered by margin expansion plus multiple re-rating into a leadership narrative; bears are triggered when monetary tightening, a credit shock, or a valuation air-pocket collides with concentrated positioning. Because the index is cap-weighted, a handful of mega-caps now dominate breadth, so cycle tops increasingly hinge on whether market leadership broadens or narrows.",
    "period": {
      "central": 5,
      "low": 2,
      "high": 11
    },
    "turns": [
      {
        "t": "2000-03",
        "k": "peak",
        "v": 1527.46,
        "e": "Dot-com bubble peak",
        "draw": null
      },
      {
        "t": "2002-10",
        "k": "trough",
        "v": 776.76,
        "e": "Tech bust / 9-11 aftermath",
        "draw": -49.2
      },
      {
        "t": "2007-10",
        "k": "peak",
        "v": 1565.15,
        "e": "Pre-GFC credit-cycle top",
        "draw": 101.5
      },
      {
        "t": "2009-03",
        "k": "trough",
        "v": 676.53,
        "e": "Global Financial Crisis low",
        "draw": -56.8
      },
      {
        "t": "2011-04",
        "k": "peak",
        "v": 1363.61,
        "e": "Post-QE2 high",
        "draw": 101.6
      },
      {
        "t": "2011-10",
        "k": "trough",
        "v": 1099.23,
        "e": "EU debt crisis / US downgrade",
        "draw": -19.4
      },
      {
        "t": "2015-05",
        "k": "peak",
        "v": 2130.82,
        "e": "Pre-China-deval high",
        "draw": 93.8
      },
      {
        "t": "2016-02",
        "k": "trough",
        "v": 1829.08,
        "e": "China/oil growth scare",
        "draw": -14.2
      },
      {
        "t": "2018-09",
        "k": "peak",
        "v": 2930.75,
        "e": "Late-cycle Fed-hike top",
        "draw": 60.2
      },
      {
        "t": "2018-12",
        "k": "trough",
        "v": 2351.1,
        "e": "Q4 hawkish-Fed selloff",
        "draw": -19.8
      },
      {
        "t": "2020-02",
        "k": "peak",
        "v": 3386.15,
        "e": "Pre-COVID high",
        "draw": 44
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 2237.4,
        "e": "COVID crash low",
        "draw": -33.9
      },
      {
        "t": "2022-01",
        "k": "peak",
        "v": 4796.56,
        "e": "Post-stimulus liquidity top",
        "draw": 114.4
      },
      {
        "t": "2022-10",
        "k": "trough",
        "v": 3577.03,
        "e": "Inflation/rate-hike bear low",
        "draw": -25.4
      },
      {
        "t": "2023-07",
        "k": "peak",
        "v": 4588.96,
        "e": "Soft-landing rally high",
        "draw": 28.3
      },
      {
        "t": "2023-10",
        "k": "trough",
        "v": 4117.37,
        "e": "Rate-spike correction",
        "draw": -10.3
      },
      {
        "t": "2025-02",
        "k": "peak",
        "v": 6144.15,
        "e": "AI-led record top",
        "draw": 49.2
      },
      {
        "t": "2025-04",
        "k": "trough",
        "v": 4982.77,
        "e": "Liberation-Day tariff crash",
        "draw": -18.9
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 7609.78,
        "e": "Record high (Jun 2 ATH)",
        "draw": 52.7
      }
    ],
    "now": {
      "level": 7533.77,
      "asOf": "2026-07-16",
      "ath": 7609.78,
      "athDate": "2026-06",
      "pctFromATH": -1.0,
      "ytd": 10.9,
      "ret1y": 25,
      "pos": 82,
      "phase": "Peak",
      "phaseLabel": "Near record, mild pullback",
      "confidence": "high",
      "read": "The S&P 500 closed at 7,358.22 on 2026-06-24, about 3.3% below its 2026-06-02 all-time-high close of 7,609.78, after a record-setting run (24+ new highs in 2026, ~+11% YTD, ~+25% over 12 months). Valuations are stretched: trailing P/E ~25.1, forward P/E ~25.1, and a Shiller CAPE near 40 — among the highest readings in history (versus a long-run mean of ~17 and a modern post-1990 average around 27). The index sits in an aging late-cycle expansion, still close to euphoric levels, but a hawkish Warsh-led Fed on hold at 3.50-3.75% and a Middle East oil/inflation shock have capped the melt-up, hence a position score in the low-80s rather than a blow-off 100."
    },
    "valuation": {
      "trailingPE": 25.06,
      "forwardPE": 25.1,
      "cape": 39.7,
      "divYield": 1.07,
      "pb": null,
      "note": "rich vs 10y avg; CAPE ~40 near historic extremes (long-run mean ~17)"
    },
    "proj": {
      "nextTurn": "peak",
      "central": "2026-12",
      "low": "2026-09",
      "high": "2027-09",
      "tilt": "mixed",
      "drivers": [
        "Hawkish Fed on hold, dot-plot tilted to hikes",
        "AI/mega-cap earnings still expanding",
        "Oil/Mideast inflation shock + rich CAPE cap upside"
      ],
      "falsifier": "A sustained close back above 7,610 with broadening breadth (NYSE advance-decline new highs) would invalidate the near-term peak call and reopen the melt-up."
    },
    "regimeNote": "Mid-2026's regime is a headwind-tilted-mixed one for the S&P 500: a hawkish Warsh Fed holding at 3.50-3.75% with a hike-leaning dot plot, sticky ~3.6% PCE inflation aggravated by a Strait-of-Hormuz oil spike, and ~2.2% GDP growth, all pressing on a market priced for perfection at a ~40 CAPE.",
    "regime_claim": { "quad": "Q3", "as_of": "2026-06-24", "conf": "low" },
    "sources": [
      "https://en.wikipedia.org/wiki/Closing_milestones_of_the_S%26P_500",
      "https://www.gurufocus.com/economic_indicators/56/sp-500-shiller-cape-ratio",
      "https://www.gurufocus.com/economic_indicators/57/sp-500-pe-ratio",
      "https://www.gurufocus.com/economic_indicators/150/sp-500-dividend-yield",
      "https://www.multpl.com/shiller-pe",
      "https://www.cnbc.com/2026/06/17/fed-interest-rate-decision-june-2026.html",
      "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
      "https://en.wikipedia.org/wiki/2025_stock_market_crash",
      "https://en.wikipedia.org/wiki/2022_stock_market_decline",
      "https://en.wikipedia.org/wiki/United_States_bear_market_of_2007%E2%80%932009",
      "https://fred.stlouisfed.org/series/SP500",
      "https://www.slickcharts.com/sp500/returns/ytd"
    ]
  },
  {
    "id": "canada",
    "name": "Canada / S&P-TSX",
    "short": "Canada",
    "group": "North America",
    "accent": "#8ca0b8",
    "proxy": "S&P/TSX Composite · banks/energy/gold",
    "archetype": "The TSX is a commodity-and-credit cycle index: roughly two-thirds of its weight sits in financials (the Big Six banks), energy and materials (oil, gold, base metals). Bull legs are driven by rising commodity prices, a steep yield curve that fattens bank net-interest margins, and a stable-to-weak Canadian dollar; bears are triggered by oil/metal crashes, credit stress in over-levered housing/banks, and global risk-off. Because it lacks a large secular-growth tech engine, it lags the US in disinflationary tech-led bulls but outperforms sharply in inflationary, hard-asset regimes like 2021-2026.",
    "period": {
      "central": 7,
      "low": 4,
      "high": 13
    },
    "turns": [
      {
        "t": "2000-09",
        "k": "peak",
        "v": 11388,
        "e": "Dot-com/Nortel telecom mania peak",
        "draw": null
      },
      {
        "t": "2002-10",
        "k": "trough",
        "v": 5695,
        "e": "Tech bust bottom, Nortel collapse",
        "draw": -50
      },
      {
        "t": "2008-06",
        "k": "peak",
        "v": 15073,
        "e": "Oil/commodity super-cycle peak (~$147 crude)",
        "draw": 164.7
      },
      {
        "t": "2009-03",
        "k": "trough",
        "v": 7567,
        "e": "Global financial crisis bottom",
        "draw": -49.8
      },
      {
        "t": "2011-04",
        "k": "peak",
        "v": 14271,
        "e": "Post-GFC commodity rebound peak",
        "draw": 88.6
      },
      {
        "t": "2011-10",
        "k": "trough",
        "v": 11251,
        "e": "EU sovereign-debt crisis low",
        "draw": -21.2
      },
      {
        "t": "2014-09",
        "k": "peak",
        "v": 15685,
        "e": "Pre-oil-crash high, crude rolls over",
        "draw": 39.4
      },
      {
        "t": "2016-01",
        "k": "trough",
        "v": 11531,
        "e": "Oil crash to ~$26, energy capitulation",
        "draw": -26.5
      },
      {
        "t": "2018-07",
        "k": "peak",
        "v": 16586,
        "e": "Late-cycle peak before Q4 selloff",
        "draw": 43.8
      },
      {
        "t": "2018-12",
        "k": "trough",
        "v": 13780,
        "e": "Global Q4 growth-scare / Fed-hike low",
        "draw": -16.9
      },
      {
        "t": "2020-02",
        "k": "peak",
        "v": 17944,
        "e": "Pre-COVID record high",
        "draw": 30.2
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 11228,
        "e": "COVID crash, oil briefly negative",
        "draw": -37.4
      },
      {
        "t": "2022-03",
        "k": "peak",
        "v": 22087,
        "e": "Post-COVID commodity/reflation peak",
        "draw": 96.7
      },
      {
        "t": "2022-10",
        "k": "trough",
        "v": 18206,
        "e": "Fed-hiking bear-market low",
        "draw": -17.6
      },
      {
        "t": "2025-12",
        "k": "peak",
        "v": 31713,
        "e": "Record year-end; +28%, best since 2009",
        "draw": 74.2
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 35630,
        "e": "Fresh ATH on banks, gold, energy",
        "draw": 12.4
      }
    ],
    "now": {
      "level": 59.49,
      "asOf": "2026-07-15",
      "ath": 59.49,
      "athDate": "2026-07",
      "pctFromATH": 0.0,
      "ytd": 9.9,
      "ret1y": 22.5,
      "pos": 82,
      "phase": "Peak",
      "phaseLabel": "Late-cycle, near record highs",
      "confidence": "high",
      "read": "The TSX closed near 34,850 on 2026-06-25, about 2% below its June all-time high of ~35,630 and up roughly 10% YTD after a blistering +28% price year in 2025 (its best since 2009). The melt-up is real and broad-based: record gold, elevated oil from the Middle-East conflict, and fat bank margins under a steep curve are all firing at once. With a trailing P/E of ~20.5 and CAPE near 27-28, it is rich versus its own history, placing it in a euphoric, late-cycle Peak zone rather than at fresh-fundamentals takeoff."
    },
    "valuation": {
      "trailingPE": 20.5,
      "forwardPE": 16.5,
      "cape": 27.5,
      "divYield": 2,
      "pb": null,
      "note": "rich vs 10y avg; cheaper than US but extended"
    },
    "proj": {
      "nextTurn": "peak",
      "central": "2026-12",
      "low": "2026-09",
      "high": "2027-09",
      "tilt": "mixed",
      "drivers": [
        "Record gold + elevated oil lift materials/energy",
        "BoC at 2.25% on hold, steep curve aids banks",
        "Stretched valuation + US trade-policy risk cap upside"
      ],
      "falsifier": "A sustained break above ~36,500 with broadening breadth and rising 2027 earnings revisions would invalidate the near-term peak call and signal the expansion still has a leg."
    },
    "regimeNote": "Mid-2026's inflationary, hard-asset regime — record gold, oil kept elevated by the Middle-East conflict, a paused BoC at 2.25% and a steep curve — is a structural tailwind for the TSX's bank/energy/gold mix, but stretched valuations and US trade-policy uncertainty make the risk/reward two-sided near record highs.",
    "sources": [
      "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index",
      "https://tradingeconomics.com/canada/stock-market",
      "https://finance.yahoo.com/quote/%5EGSPTSE/history/",
      "https://siblisresearch.com/data/canada-pe-earnings/",
      "https://www.bankofcanada.ca/2026/06/fad-press-release-2026-06-10/",
      "https://kalkine.ca/news/general-news/sptsx-composite-index-closing-performance-june-4-2026",
      "https://www.marketscreener.com/news/latest/S-P-TSX-Composite-Index-Ends-0-06-Lower-at-18206-28-Data-Talk--41993953/",
      "https://www.visualcapitalist.com/sp/lessons-recessions-tsx/"
    ]
  },
  {
    "id": "uk",
    "name": "United Kingdom / FTSE 100",
    "short": "UK",
    "group": "Europe",
    "accent": "#a78bfa",
    "proxy": "FTSE 100 · energy/banks/miners",
    "archetype": "The FTSE 100 is a value/cyclical, externally-geared index: roughly three-quarters of constituent revenue is earned abroad, so its cycle is driven less by UK domestic growth than by global commodity prices (energy majors Shell/BP, miners Rio/Glencore/Anglo), global bank net-interest margins (HSBC, Barclays, Lloyds), defensives (AstraZeneca, GSK, Unilever, Diageo) and the sterling exchange rate — a weak pound mechanically lifts the index by inflating overseas earnings. It lacks the megacap tech that powered the US, so it underperformed badly in the 2010s growth regime but shines when energy, financials and value lead. Bull cycles ride commodity super-cycles and re-rating of cheap UK assets; bears come from oil/metal busts, global credit crises and sterling/rate shocks.",
    "period": {
      "central": 7,
      "low": 4,
      "high": 11
    },
    "turns": [
      {
        "t": "1999-12",
        "k": "peak",
        "v": 6930.2,
        "e": "Dot-com / TMT peak",
        "draw": null
      },
      {
        "t": "2003-03",
        "k": "trough",
        "v": 3287,
        "e": "Dot-com bust, Iraq war low",
        "draw": -52.6
      },
      {
        "t": "2007-10",
        "k": "peak",
        "v": 6730.7,
        "e": "Pre-GFC credit peak",
        "draw": 104.8
      },
      {
        "t": "2009-03",
        "k": "trough",
        "v": 3512.1,
        "e": "Global financial crisis low",
        "draw": -47.8
      },
      {
        "t": "2011-10",
        "k": "trough",
        "v": 4944.4,
        "e": "Eurozone debt crisis low",
        "draw": 40.8
      },
      {
        "t": "2015-04",
        "k": "peak",
        "v": 7103,
        "e": "QE-era high, China/oil peak",
        "draw": 43.7
      },
      {
        "t": "2016-02",
        "k": "trough",
        "v": 5537,
        "e": "China devaluation / oil crash",
        "draw": -22
      },
      {
        "t": "2018-05",
        "k": "peak",
        "v": 7877.5,
        "e": "Synchronized global growth high",
        "draw": 42.3
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 4993.9,
        "e": "COVID-19 crash",
        "draw": -36.6
      },
      {
        "t": "2022-02",
        "k": "peak",
        "v": 7672.4,
        "e": "Reopening / value-cyclical high",
        "draw": 53.6
      },
      {
        "t": "2022-10",
        "k": "trough",
        "v": 6826.2,
        "e": "Gilt/mini-budget & rate shock",
        "draw": -11
      },
      {
        "t": "2026-02",
        "k": "peak",
        "v": 10910.55,
        "e": "Record high, value re-rating",
        "draw": 59.8
      },
      {
        "t": "2026-06",
        "k": "trough",
        "v": 10529.89,
        "e": "Pullback, Mideast energy risk",
        "draw": -3.5
      }
    ],
    "now": {
      "level": 10515.9,
      "asOf": "2026-07-15",
      "ath": 10910.6,
      "athDate": "2026-02",
      "pctFromATH": -3.6,
      "ytd": 6,
      "ret1y": 20.5,
      "pos": 68,
      "phase": "Expansion",
      "phaseLabel": "Late expansion near record",
      "confidence": "high",
      "read": "The FTSE 100 sits at 10,529.89 (25 Jun 2026), about 3.5% below its 27 Feb 2026 record close of 10,910.55, and is up roughly 20% over the past year (52-week range 8,726.90–10,934.90) after first breaching 9,000 (Jul 2025) and 10,000 (Jan 2026). The index ended 2025 at 9,931.38 (+21.5% on the year), so the 2026 year-to-date gain is a more modest ~6%. Despite record nominal highs, valuation is undemanding — trailing P/E ~14.9 and CAPE ~20 — so the move reflects an overdue re-rating of cheap UK value/cyclicals plus heavy buybacks rather than froth. It is therefore late-expansion but not euphoric; the soft patch since February ties to Middle East energy volatility and a still-subdued UK economy."
    },
    "valuation": {
      "trailingPE": 14.9,
      "forwardPE": 13.35,
      "cape": 20.2,
      "divYield": 3.05,
      "pb": null,
      "note": "Cheap vs US; ~in line with own 37-yr average despite record price"
    },
    "proj": {
      "nextTurn": "peak",
      "central": "2026-12",
      "low": "2026-09",
      "high": "2027-06",
      "tilt": "mixed",
      "drivers": [
        "Cheap valuation + record buybacks/dividends",
        "BoE on hold at 3.75%, sticky H2 inflation",
        "Energy/metals and global bank earnings"
      ],
      "falsifier": "A decisive break and close above ~11,000 with broadening leadership would invalidate the near-term peak call and confirm a fresh leg of expansion."
    },
    "regimeNote": "Mid-2026's mix — BoE holding at 3.75% with CPI (2.8%) set to drift back above 3%, a firmer pound, subdued UK growth but elevated/unstable Middle East energy prices — is broadly neutral-to-supportive for the FTSE's energy-and-banks tilt while capping any domestic-cyclical upside.",
    "sources": [
      "https://tradingeconomics.com/united-kingdom/stock-market",
      "https://en.wikipedia.org/wiki/FTSE_100_Index",
      "https://global.morningstar.com/en-gb/markets/ftse-100-hits-10000-points-first-time-history",
      "https://siblisresearch.com/data/ftse-100-cape-pe-yield/",
      "https://www.mondovisione.com/media-and-resources/news/ftse-100-ends-the-year-at-993138-points-a-2151-increase-from-the-previous-y-20251231/",
      "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/june-2026",
      "https://www.dividenddata.co.uk/dividendyield.py?market=ftse100",
      "https://www.bbntimes.com/global-economy/ftse-100-climbs-0-65-to-10-530-as-energy-easing-and-ai-optimism-drive-london-markets-higher"
    ]
  },
  {
    "id": "europe",
    "name": "Europe / STOXX 600",
    "short": "Europe",
    "group": "Europe",
    "accent": "#2dd4bf",
    "proxy": "STOXX Europe 600 · Euro STOXX 50",
    "archetype": "The STOXX 600 is a value/cyclical-heavy, externally-levered index: banks, energy, industrials, autos and luxury exporters dominate, so its cycle is driven less by domestic tech than by global growth, the credit cycle, commodity/energy shocks, China demand, the euro, and the sovereign-debt/ECB policy axis. Bull legs come from earnings recovery off cheap valuations plus capital rotation into Europe when the dollar softens or the US looks crowded; bear legs come from recessions, banking/sovereign stress (2008, 2011), energy spikes, and trade shocks. It is structurally more macro- and crisis-sensitive than the US, with shallower secular drift and a persistent valuation discount to Wall Street.",
    "period": {
      "central": 7,
      "low": 4,
      "high": 11
    },
    "turns": [
      {
        "t": "2000-03",
        "k": "peak",
        "v": 405,
        "e": "Dot-com / TMT mania top",
        "draw": null
      },
      {
        "t": "2003-03",
        "k": "trough",
        "v": 160,
        "e": "Tech bust, Iraq-war low",
        "draw": -60.5
      },
      {
        "t": "2007-06",
        "k": "peak",
        "v": 401,
        "e": "Pre-crisis credit peak",
        "draw": 150.6
      },
      {
        "t": "2009-03",
        "k": "trough",
        "v": 158,
        "e": "Global financial crisis bottom",
        "draw": -60.6
      },
      {
        "t": "2011-02",
        "k": "peak",
        "v": 292,
        "e": "Post-GFC recovery top",
        "draw": 84.8
      },
      {
        "t": "2011-09",
        "k": "trough",
        "v": 211,
        "e": "Euro sovereign-debt crisis",
        "draw": -27.7
      },
      {
        "t": "2015-04",
        "k": "peak",
        "v": 415,
        "e": "ECB QE / Draghi rally peak",
        "draw": 96.7
      },
      {
        "t": "2016-02",
        "k": "trough",
        "v": 303,
        "e": "China/oil scare, Brexit fears",
        "draw": -27
      },
      {
        "t": "2018-01",
        "k": "peak",
        "v": 403,
        "e": "Synchronized-growth top",
        "draw": 33
      },
      {
        "t": "2018-12",
        "k": "trough",
        "v": 335,
        "e": "Q4 global selloff, Fed/trade",
        "draw": -16.9
      },
      {
        "t": "2020-02",
        "k": "peak",
        "v": 434,
        "e": "Pre-COVID record high",
        "draw": 29.6
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 280,
        "e": "COVID crash bottom",
        "draw": -35.5
      },
      {
        "t": "2022-01",
        "k": "peak",
        "v": 495,
        "e": "Post-COVID liquidity peak",
        "draw": 76.8
      },
      {
        "t": "2022-09",
        "k": "trough",
        "v": 388,
        "e": "Ukraine war, energy/inflation",
        "draw": -21.6
      },
      {
        "t": "2025-03",
        "k": "peak",
        "v": 565,
        "e": "Defense/bank-led record run",
        "draw": 45.6
      },
      {
        "t": "2025-04",
        "k": "trough",
        "v": 470,
        "e": "Trump 'Liberation Day' tariffs",
        "draw": -16.8
      },
      {
        "t": "2026-02",
        "k": "peak",
        "v": 625,
        "e": "AI/bank/luxury record high",
        "draw": 33
      },
      {
        "t": "2026-04",
        "k": "trough",
        "v": 520,
        "e": "Mideast war, Hormuz oil shock",
        "draw": -16.8
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 640,
        "e": "US-Iran peace deal record close",
        "draw": 23.1
      }
    ],
    "now": {
      "level": 642.71,
      "asOf": "2026-07-15",
      "ath": 652.77,
      "athDate": "2026-07",
      "pctFromATH": -1.5,
      "ytd": 7.4,
      "ret1y": 13,
      "pos": 78,
      "phase": "Peak",
      "phaseLabel": "Record high, relief-rally extended",
      "confidence": "high",
      "read": "The STOXX 600 closed at a record 640.21 on 2026-06-25 (intraday ATH 642.09), within ~0.3% of its all-time high after a relief rally sparked by a US-Iran preliminary peace deal reopening the Strait of Hormuz and ending a three-month Middle East war. It sits high in its cycle: after +17% in 2025 and fresh records, valuation is full (trailing P/E ~19, forward P/E ~16, CAPE ~22) but not extreme, and the rally is V-shaped off an April Iran-war scare. The tension is that the index is making records into a tightening, not easing, backdrop — the ECB just hiked for the first time since 2023 and euro-area 2026 growth is only ~0.8%."
    },
    "valuation": {
      "trailingPE": 19.4,
      "forwardPE": 15.9,
      "cape": 22.4,
      "divYield": 3.1,
      "pb": 2,
      "note": "~25-30% forward-PE discount to US; yield-rich"
    },
    "proj": {
      "nextTurn": "trough",
      "central": "2026-09",
      "low": "2026-07",
      "high": "2027-03",
      "tilt": "mixed",
      "drivers": [
        "ECB hiking into 3% inflation, weak euro",
        "Post-war relief & cheap-vs-US rotation flows",
        "Fragile 0.8% growth, energy-shock overhang"
      ],
      "falsifier": "A sustained break above ~660 with broad sector participation and easing inflation would invalidate a near-term peak and signal a fresh expansion leg rather than a cyclical top."
    },
    "regimeNote": "Mid-2026 macro is two-sided for Europe: a post-war energy-price relief and a cheap-valuation, soft-euro rotation case support inflows, but the ECB hiking into 3% inflation amid sub-1% growth and a hawkish Fed (US rates 3.50-3.75%, hike risk) caps upside and leaves the index extended at record highs.",
    "sources": [
      "https://en.wikipedia.org/wiki/STOXX_Europe_600",
      "https://tradingeconomics.com/euro-area/stock-market/news/513937",
      "https://www.kitco.com/news/off-the-wire/2026-06-15/stoxx-600-hits-record-high-after-us-iran-preliminary-peace-deal",
      "https://www.brecorder.com/news/40427341/european-shares-hit-record-close-high",
      "https://siblisresearch.com/data/europe-pe-ratio/",
      "https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.mp260611~4d41bd5e83.en.html",
      "https://tradingeconomics.com/euro-area/currency",
      "https://en.wikipedia.org/wiki/2025_stock_market_crash",
      "https://curvo.eu/backtest/en/market-index/stoxx-europe-600",
      "https://www.investing.com/indices/stoxx-600"
    ]
  },
  {
    "id": "japan",
    "name": "Japan / Nikkei 225",
    "short": "Japan",
    "group": "Asia-Pacific",
    "accent": "#f472b6",
    "proxy": "Nikkei 225 / TOPIX",
    "archetype": "Japan's equity cycle is driven less by domestic demand than by two external/policy levers: the yen (a weak yen mechanically inflates the export-heavy, USD-earning index in yen terms and pulls in foreign inflows) and the BoJ's stance versus the rest of the world. Secular regime shifts dominate the ordinary business cycle: the 1990 bubble burst and three \"lost decades\" of deflation, then Abenomics (2013), and finally the 2023-26 escape from deflation with rising nominal GDP, TSE corporate-governance reform (buybacks/ROE), and an AI/semiconductor capex super-cycle. Because so much of the move is currency- and global-tech-driven, Japan is acutely vulnerable to carry-trade unwinds and global risk shocks.",
    "period": {
      "central": 6,
      "low": 4,
      "high": 9
    },
    "turns": [
      {
        "t": "2000-04",
        "k": "peak",
        "v": 20833,
        "e": "IT/dot-com bubble high",
        "draw": null
      },
      {
        "t": "2003-04",
        "k": "trough",
        "v": 7607.88,
        "e": "Lost-decade / dot-com bust low",
        "draw": -63.5
      },
      {
        "t": "2007-07",
        "k": "peak",
        "v": 18261.98,
        "e": "Pre-GFC global credit peak",
        "draw": 140
      },
      {
        "t": "2009-03",
        "k": "trough",
        "v": 7054.98,
        "e": "Lehman / GFC bottom",
        "draw": -61.4
      },
      {
        "t": "2011-11",
        "k": "trough",
        "v": 8160.01,
        "e": "Tohoku quake + EU debt crisis low",
        "draw": 15.7
      },
      {
        "t": "2018-10",
        "k": "peak",
        "v": 24270.62,
        "e": "Late-cycle / pre-trade-war top",
        "draw": 197.4
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 16552.83,
        "e": "COVID-19 crash",
        "draw": -31.8
      },
      {
        "t": "2021-09",
        "k": "peak",
        "v": 30670.1,
        "e": "Post-COVID reflation rally",
        "draw": 85.3
      },
      {
        "t": "2022-03",
        "k": "trough",
        "v": 24717.53,
        "e": "Fed hiking / Ukraine shock low",
        "draw": -19.4
      },
      {
        "t": "2024-07",
        "k": "peak",
        "v": 42224.02,
        "e": "AI rally; reclaims 1989 high",
        "draw": 70.8
      },
      {
        "t": "2024-08",
        "k": "trough",
        "v": 31458.42,
        "e": "Yen carry-trade unwind crash",
        "draw": -25.5
      },
      {
        "t": "2025-04",
        "k": "trough",
        "v": 31136.58,
        "e": "Trump 'Liberation Day' tariff rout",
        "draw": -1
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 72366.34,
        "e": "Physical-AI capex boom + weak yen",
        "draw": 132.4
      }
    ],
    "now": {
      "level": 67135.13,
      "asOf": "2026-07-16",
      "ath": 72366.34,
      "athDate": "2026-06",
      "pctFromATH": -7.2,
      "ytd": 43.8,
      "ret1y": 85,
      "pos": 93,
      "phase": "Peak",
      "phaseLabel": "Euphoric AI/weak-yen blow-off at record",
      "confidence": "high",
      "read": "The Nikkei closed at a record 72,366 on 2026-06-25, the seventh-plus straight record after a near-vertical run from the ~50,339 end-2025 close (+43.8% YTD) and roughly +85% over twelve months. The melt-up is powered by Japan's 10.5 trillion yen 'physical AI' investment plan, a yen pinned near 160/USD that flatters exporters, and chip names (Advantest, Screen, Taiyo Yuden) leading daily. Valuations are full and have stretched with the run-up: the only published Nikkei-225-specific multiples are stale (Siblis Jan-2026: trailing P/E ~17.9, CAPE ~29.4), and after a ~25% further price move the current trailing P/E is in the low-20s (broad TSE Prime P/E was ~25 in June 2026) with CAPE near the mid-30s. So the risk is less a 1989-bubble valuation air-pocket than a sharp yen reversal or AI-sentiment crack of the kind that produced the Aug-2024 carry-unwind crash (indeed the Nikkei dropped ~4% intraday on 2026-06-26 on tech selling, SoftBank -10.8%)."
    },
    "valuation": {
      "trailingPE": 22,
      "forwardPE": 20,
      "cape": 36,
      "divYield": 2.1,
      "pb": 1.6,
      "note": "full and stretched by the 2026 melt-up; figures estimated by uplifting the Siblis Jan-1-2026 base (trailing 17.9 / fwd 16.9 / CAPE 29.4) for the ~25% subsequent price move, as no fresh Nikkei-225-specific print is published; broad TSE Prime P/E ~25 (Jun 2026, CEIC); official Nikkei 225 div yield was 2.62% in Apr 2026, compressed by the rally; growth-priced, dividend low"
    },
    "proj": {
      "nextTurn": "peak",
      "central": "2026-09",
      "low": "2026-07",
      "high": "2027-03",
      "tilt": "mixed",
      "drivers": [
        "physical-AI capex + weak-yen earnings tailwind",
        "BoJ at 1% (highest since 1995), more hikes flagged",
        "carry-unwind / yen-reversal fragility"
      ],
      "falsifier": "A sustained yen rally below ~150/USD or an abrupt BoJ tightening that breaks the export-earnings tailwind, sending the Nikkei into a >15% drawdown, would mark the cyclical peak earlier than the central case."
    },
    "regimeNote": "Mid-2026's combination of a still-weak yen near 160, a global AI/semiconductor capex boom, and a BoJ only gradually normalizing (1% policy rate) is a powerful tailwind for Japan's exporter-heavy index, but the same yen weakness sets up the carry-trade reversal that is the market's signature downside risk.",
    "sources": [
      "https://en.wikipedia.org/wiki/Nikkei_225",
      "https://www.nippon.com/en/news/yjj2026061900882/",
      "https://tradingeconomics.com/japan/stock-market",
      "https://indexes.nikkei.co.jp/en/nkave/archives/data",
      "https://www.bbntimes.com/financial/nikkei-225-surges-to-record-high-72-354-powered-by-physical-ai-investment-and-weak-yen",
      "https://www.cnn.com/2024/08/05/investing/japan-nikkei-225-stock-market-rebound-intl-hnk/index.html",
      "https://www.nippon.com/en/news/yjj2025081200197/nikkei-hits-record-intraday-high-above-42-800.html",
      "https://siblisresearch.com/data/japan-nikkei-pe-cape/",
      "https://www.ceicdata.com/en/indicator/japan/pe-ratio",
      "https://indexes.nikkei.co.jp/en/nkave/factsheet?idx=nk225hdy",
      "https://www.gurufocus.com/economic_indicators/4422/nikkei-225"
    ]
  },
  {
    "id": "taiwan",
    "name": "Taiwan / TAIEX",
    "short": "Taiwan",
    "group": "Asia EM",
    "accent": "#84cc16",
    "proxy": "TAIEX (TWII) · TSMC ~30% weight",
    "archetype": "The TAIEX is a high-beta, semiconductor-leveraged proxy on the global tech/capex cycle, with TSMC plus the broader chip supply chain (foundry, packaging, IC design, electronics manufacturing) dominating index weight. Its bull/bear cycle is driven by the world demand cycle for chips and electronics, the USD/NTD exchange rate (a strong dollar/weak NTD boosts export earnings and foreign inflows), and global risk appetite for tech — meaning it amplifies US Nasdaq/SOX moves. Cross-strait geopolitical risk with China is the persistent tail that periodically compresses its valuation multiple versus peers.",
    "period": {
      "central": 7,
      "low": 5,
      "high": 9
    },
    "turns": [
      {
        "t": "2000-02",
        "k": "peak",
        "v": 10202,
        "e": "Dot-com / tech mania peak",
        "draw": null
      },
      {
        "t": "2001-09",
        "k": "trough",
        "v": 3446,
        "e": "Dot-com bust + 9/11",
        "draw": -66.2
      },
      {
        "t": "2007-10",
        "k": "peak",
        "v": 9809,
        "e": "Pre-GFC global liquidity peak",
        "draw": 184.6
      },
      {
        "t": "2008-11",
        "k": "trough",
        "v": 3955,
        "e": "Global financial crisis",
        "draw": -59.7
      },
      {
        "t": "2011-12",
        "k": "trough",
        "v": 6633,
        "e": "Euro sovereign-debt crisis low",
        "draw": 67.7
      },
      {
        "t": "2015-08",
        "k": "trough",
        "v": 7410,
        "e": "China deval / global growth scare",
        "draw": 11.7
      },
      {
        "t": "2018-01",
        "k": "peak",
        "v": 11270,
        "e": "Synchronized global growth peak",
        "draw": 52.1
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 8681,
        "e": "COVID-19 crash",
        "draw": -23
      },
      {
        "t": "2022-01",
        "k": "peak",
        "v": 18619,
        "e": "Post-COVID chip super-cycle peak",
        "draw": 114.5
      },
      {
        "t": "2022-10",
        "k": "trough",
        "v": 12629,
        "e": "Fed tightening / chip downcycle",
        "draw": -32.2
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 47742,
        "e": "AI / TSMC mega-bull record",
        "draw": 278
      }
    ],
    "now": {
      "level": 45855.02,
      "asOf": "2026-07-16",
      "ath": 47741.51,
      "athDate": "2026-06",
      "pctFromATH": -4.0,
      "ytd": 54.8,
      "ret1y": 98.5,
      "pos": 88,
      "phase": "Peak",
      "phaseLabel": "Record-high pullback, AI-driven",
      "confidence": "high",
      "read": "The TAIEX set a record close of 47,742 on June 22, 2026 and printed an intraday all-time high of 48,218.87 on June 23, capping a roughly 4x run off the October 2022 low of ~12,629 powered by the AI/TSMC capex super-cycle (Taiwan exports +40%, Q4-2025 GDP +12.65%). It has since pulled back ~7% to ~44,829 (June 26) on a global AI/semiconductor correction, the new hawkish Fed under Chair Warsh, and US strikes on Iran. Trailing 12-month return is ~+98% and YTD ~+55%, with the market PE near 23x versus a ~22.7x three-year average — richly valued and momentum-extended but still earnings-supported, hence a late-cycle, euphoric-but-cooling read."
    },
    "valuation": {
      "trailingPE": 23.3,
      "forwardPE": 18.5,
      "cape": null,
      "divYield": 1.5,
      "pb": null,
      "note": "PE ~23x vs ~22.7x 3yr avg — rich but ~26% fwd EPS growth; dividend yield has compressed to ~1.5% (was 2.36% at YE2025) after the ~55% YTD run"
    },
    "proj": {
      "nextTurn": "trough",
      "central": "2026-11",
      "low": "2026-08",
      "high": "2027-03",
      "tilt": "headwind",
      "drivers": [
        "AI/semiconductor demand cycle and TSMC capex",
        "Hawkish Fed + strong-USD vs NTD-appreciation tension",
        "Middle East war and global risk-off rotation"
      ],
      "falsifier": "A V-shaped rebound to fresh closing record highs above 47,742 within 8 weeks would invalidate the near-term corrective call."
    },
    "regimeNote": "Mid-2026 macro is mixed-to-negative for TAIEX: blistering AI/chip export fundamentals and a 2% CBC hold support it, but a newly hawkish Fed (1-2 hikes projected), a Middle East war, a June AI-sector correction, and NTD-appreciation risk to exporter margins all argue for a near-term consolidation after the record run.",
    "sources": [
      "https://tradingeconomics.com/taiwan/stock-market",
      "https://en.wikipedia.org/wiki/TAIEX",
      "https://simplywall.st/markets/tw",
      "https://focustaiwan.tw/business/202606220015",
      "https://www.taiwannews.com.tw/news/6388748",
      "https://www.taiwannews.com.tw/news/6387951",
      "https://www.taipeitimes.com/News/biz/archives/2026/06/23/2003859552",
      "https://www.twse.com.tw/downloads/zh/about/company/factbook/2026/2.08.html",
      "https://www.taipeitimes.com/News/front/archives/2026/01/01/2003849853",
      "https://en.macromicro.me/series/5683/taiwan-stock-price-to-earnings-ratio",
      "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260318.htm"
    ]
  },
  {
    "id": "india",
    "name": "India / Nifty 50",
    "short": "India",
    "group": "Asia EM",
    "accent": "#fbbf24",
    "proxy": "Nifty 50 · BSE Sensex",
    "archetype": "India's equity cycle is driven by a structural domestic-flow engine (SIP/mutual-fund inflows that have become a permanent bid) layered over a globally sensitive FII channel: bull legs run on robust nominal GDP (10-12%), strong earnings compounding and re-rating of a premium consumption/financials franchise; bears come from FII risk-off, crude/rupee shocks and rich starting valuations. Because domestic flows now cushion downside while foreign flows drive marginal price, drawdowns since 2020 have tended to be shallower and shorter than the 2008/2011 GFC-era crashes, but valuation premiums make India vulnerable when global liquidity tightens.",
    "period": {
      "central": 6,
      "low": 3,
      "high": 8
    },
    "turns": [
      {
        "t": "2000-02",
        "k": "peak",
        "v": 1818,
        "e": "Dot-com / Ketan Parekh bull peak",
        "draw": null
      },
      {
        "t": "2001-09",
        "k": "trough",
        "v": 854,
        "e": "Tech bust + 9/11 shock",
        "draw": -53
      },
      {
        "t": "2008-01",
        "k": "peak",
        "v": 6357,
        "e": "Pre-GFC credit/EM boom top",
        "draw": 644.4
      },
      {
        "t": "2008-10",
        "k": "trough",
        "v": 2524,
        "e": "Global financial crisis crash",
        "draw": -60.3
      },
      {
        "t": "2010-11",
        "k": "peak",
        "v": 6312,
        "e": "Post-GFC liquidity recovery high",
        "draw": 150.1
      },
      {
        "t": "2011-12",
        "k": "trough",
        "v": 4531,
        "e": "EU debt crisis, policy paralysis",
        "draw": -28.2
      },
      {
        "t": "2015-03",
        "k": "peak",
        "v": 9119,
        "e": "Modi-reform re-rating peak",
        "draw": 101.3
      },
      {
        "t": "2016-02",
        "k": "trough",
        "v": 6826,
        "e": "China/EM scare, oil collapse",
        "draw": -25.1
      },
      {
        "t": "2018-08",
        "k": "peak",
        "v": 11739,
        "e": "Pre-IL&FS / NBFC cycle high",
        "draw": 72
      },
      {
        "t": "2018-10",
        "k": "trough",
        "v": 10234,
        "e": "NBFC crisis, crude + rupee shock",
        "draw": -12.8
      },
      {
        "t": "2020-01",
        "k": "peak",
        "v": 12430,
        "e": "Pre-COVID cyclical high",
        "draw": 21.5
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 7610,
        "e": "COVID-19 crash",
        "draw": -38.8
      },
      {
        "t": "2021-10",
        "k": "peak",
        "v": 18604,
        "e": "Post-COVID liquidity blow-off",
        "draw": 144.5
      },
      {
        "t": "2022-06",
        "k": "trough",
        "v": 15183,
        "e": "Fed hikes, Ukraine war, FII exit",
        "draw": -18.4
      },
      {
        "t": "2024-09",
        "k": "peak",
        "v": 26277,
        "e": "Domestic-flow bull market record",
        "draw": 73.1
      },
      {
        "t": "2025-04",
        "k": "trough",
        "v": 22161,
        "e": "Trump tariff shock, FII outflows",
        "draw": -15.7
      },
      {
        "t": "2026-01",
        "k": "peak",
        "v": 26373,
        "e": "New all-time high, rate-cut rally",
        "draw": 19
      },
      {
        "t": "2026-06",
        "k": "trough",
        "v": 24056,
        "e": "Geopolitics/energy, FII outflows",
        "draw": -8.8
      }
    ],
    "now": {
      "level": 24115.9,
      "asOf": "2026-07-16",
      "ath": 26328.55,
      "athDate": "2026-01",
      "pctFromATH": -8.4,
      "ytd": -7.9,
      "ret1y": -4.4,
      "pos": 48,
      "phase": "Downturn",
      "phaseLabel": "Correcting below January peak",
      "confidence": "high",
      "read": "Nifty closed ~24,056 on 25-Jun-2026, about 8.8% below its 5-Jan-2026 all-time high of 26,373.20 and down ~7.9% YTD (from 26,129.60 on 31-Dec-2025). It fell ~16% into an April 2026 low near 22,183 before recovering, so it sits mid-cycle: not euphoric, not capitulated. Valuation (PE ~20.8, ~15% below the 10-yr average; PB ~3.1) is reasonable, but heavy FII outflows (~$13.7bn YTD), a cautious RBI (repo held at 5.25%) and energy/geopolitical risk keep it in a corrective, range-bound posture."
    },
    "valuation": {
      "trailingPE": 20.75,
      "forwardPE": 18.5,
      "cape": null,
      "divYield": 1.2,
      "pb": 3.15,
      "note": "PE ~15% below 10y avg; rich vs EM peers but off highs"
    },
    "proj": {
      "nextTurn": "trough",
      "central": "2026-09",
      "low": "2026-07",
      "high": "2026-12",
      "tilt": "mixed",
      "drivers": [
        "RBI easing bias + 6.6% GDP support",
        "FII outflows + rupee/energy-price drag",
        "Domestic SIP flows cushion downside"
      ],
      "falsifier": "A sustained close above 26,373 (new ATH) before September 2026 would invalidate the near-term trough call and confirm the next leg is a fresh expansion peak."
    },
    "regimeNote": "Mid-2026's regime — a cautious RBI holding 5.25% amid sticky inflation and energy-price risk, a narrowed US-India rate gap driving record FII outflows and a soft rupee, but resilient ~6.6% domestic growth and structural SIP inflows — leaves India range-bound: domestically supported but externally pressured.",
    "sources": [
      "https://finance.yahoo.com/quote/%5ENSEI/history/",
      "https://univest.in/blogs/nifty-50-weekly-summary-8-12-june-2026",
      "https://nifty-pe-ratio.com/",
      "https://craytheon.com/charts/nifty-pe-ratio/",
      "https://trendlyne.com/equity/PB/NIFTY50/1887/nifty-50-price-to-book-ratio/",
      "https://moneyvesta.com/nifty-50-drawdowns-and-recoveries/",
      "https://www.cnbc.com/amp/2026/06/05/india-rbi-rate-gdp-inflation.html",
      "https://www.goldmansachs.com/insights/articles/the-outlook-for-indias-economy-in-2026-amid-new-us-tradedeal",
      "https://akarresearch.com/nifty-50-corrections-insights-and-lessons-2/",
      "https://www.dnaindia.com/business/report-nifty-hits-all-time-high-surges-past-26277-points-after-14-months-know-what-is-driving-the-rally-3190717",
      "https://www.indmoney.com/blog/stocks/us-tariff-war-crashes-nifty-fifty",
      "https://en.wikipedia.org/wiki/NIFTY_50"
    ]
  },
  {
    "id": "hk",
    "name": "Hong Kong / Hang Seng",
    "short": "Hong Kong",
    "group": "Greater China",
    "accent": "#fb923c",
    "proxy": "Hang Seng Index · HS Tech",
    "archetype": "The Hang Seng is a high-beta proxy on China's growth and policy cycle, refracted through Hong Kong's USD-pegged, offshore-liquidity plumbing. Its bull/bear swings are driven by three structural forces: mainland Chinese earnings and stimulus (tech platforms, property, banks now dominate the index), the Fed/US-dollar rate cycle (because the HKD peg imports US monetary policy and global risk appetite drives Southbound and foreign flows), and geopolitics/regulation (US-China tensions, Beijing's tech and property crackdowns). This makes it one of the most cyclical, sentiment-whipped major indices, prone to 30-60% peak-to-trough drawdowns and explosive policy-driven rebounds.",
    "period": {
      "central": 6,
      "low": 3,
      "high": 10
    },
    "turns": [
      {
        "t": "2000-03",
        "k": "peak",
        "v": 18301,
        "e": "Dot-com / tech bubble peak",
        "draw": null
      },
      {
        "t": "2003-04",
        "k": "trough",
        "v": 8409,
        "e": "SARS epidemic + post-dot-com low",
        "draw": -54
      },
      {
        "t": "2007-10",
        "k": "peak",
        "v": 31958,
        "e": "China A-share boom; 'through-train' euphoria",
        "draw": 280
      },
      {
        "t": "2008-10",
        "k": "trough",
        "v": 11016,
        "e": "Global financial crisis crash",
        "draw": -65.5
      },
      {
        "t": "2011-10",
        "k": "trough",
        "v": 16250,
        "e": "Euro debt crisis intermediate low",
        "draw": 47.5
      },
      {
        "t": "2015-04",
        "k": "peak",
        "v": 28133,
        "e": "Shanghai-HK Connect / A-share mania",
        "draw": 73.1
      },
      {
        "t": "2016-02",
        "k": "trough",
        "v": 18320,
        "e": "China devaluation + capital-flight scare",
        "draw": -34.9
      },
      {
        "t": "2018-01",
        "k": "peak",
        "v": 33484,
        "e": "Record high; synchronized global growth",
        "draw": 82.8
      },
      {
        "t": "2020-03",
        "k": "trough",
        "v": 21696,
        "e": "COVID-19 crash",
        "draw": -35.2
      },
      {
        "t": "2021-02",
        "k": "peak",
        "v": 31084,
        "e": "Reflation / tech reopening peak",
        "draw": 43.3
      },
      {
        "t": "2022-10",
        "k": "trough",
        "v": 14687,
        "e": "Tech/property crackdown + zero-COVID + Fed hikes",
        "draw": -52.8
      },
      {
        "t": "2024-01",
        "k": "trough",
        "v": 14961,
        "e": "Deflation fears; decade-low retest",
        "draw": 1.9
      },
      {
        "t": "2026-02",
        "k": "peak",
        "v": 28056,
        "e": "DeepSeek AI + China stimulus melt-up; highest since 2021",
        "draw": 87.5
      },
      {
        "t": "2026-06",
        "k": "trough",
        "v": 23077,
        "e": "Hawkish Fed (Warsh) + Chinese-tech selloff (Alibaba); in progress",
        "draw": -17.7
      }
    ],
    "now": {
      "level": 22.08,
      "asOf": "2026-07-15",
      "ath": 24.16,
      "athDate": "2026-05",
      "pctFromATH": -8.6,
      "ytd": -6.9,
      "ret1y": 4,
      "pos": 44,
      "phase": "Downturn",
      "phaseLabel": "Correcting off Feb-2026 melt-up peak",
      "confidence": "high",
      "read": "After a +28% 2025 and a DeepSeek/stimulus melt-up to 28,056 in early February 2026 (highest since July 2021), the HSI has rolled over ~18% to a 23,076.91 close on June 25, 2026 (briefly below 23,000 intraday for the first time in a year), down roughly 7% YTD and ~31% below its January-2018 record of 33,484. The latest leg lower is driven by a hawkish Fed pivot under new chair Kevin Warsh (held at 3.50-3.75% on June 17, dot plot tilting toward a possible hike) plus a global tech rout and a sharp Chinese-tech selloff — Alibaba slumped to a 16-month low after Anthropic accused it of illicitly extracting capabilities from its Claude model — with Middle East tension adding to risk-off. Valuations remain among the cheapest of any major market (trailing PE ~12.9, CAPE ~14.7, ~3% yield), so this reads as a cyclical correction within a still-incomplete recovery rather than a fresh capitulation."
    },
    "valuation": {
      "trailingPE": 12.9,
      "forwardPE": 13.75,
      "cape": 14.7,
      "divYield": 3.07,
      "pb": null,
      "note": "Cheapest major market; CAPE ~14.7 vs ~12.5 median, deep discount to US"
    },
    "proj": {
      "nextTurn": "trough",
      "central": "2026-10",
      "low": "2026-08",
      "high": "2027-03",
      "tilt": "headwind",
      "drivers": [
        "Hawkish Fed/strong USD via HKD peg pressuring liquidity",
        "China stimulus + cheap valuations as a floor",
        "Global tech/AI sentiment and US-China geopolitics swing factor"
      ],
      "falsifier": "A decisive break and hold above the ~28,000 February-2026 peak, or a Fed pivot back to cuts, would invalidate the 'correction toward a near-term trough' thesis and signal the bull leg has resumed."
    },
    "regimeNote": "Mid-2026's hawkish Fed (held at 3.50-3.75% with a hiking tilt under Warsh) and firm US dollar are a clear headwind for the USD-pegged HSI, partially offset by China's ongoing fiscal/monetary stimulus and Hong Kong's rock-bottom valuations.",
    "regime_claim": { "quad": "Q3", "as_of": "2026-07-01", "conf": "medium" },
    "sources": [
      "https://tradingeconomics.com/hong-kong/stock-market",
      "https://www.gurufocus.com/economic_indicators/4421/hang-seng-index",
      "https://en.wikipedia.org/wiki/Hang_Seng_Index",
      "https://siblisresearch.com/data/hang-seng-cape/",
      "https://siblisresearch.com/data/cape-ratios-by-country/",
      "https://www.scmp.com/business/china-business/article/3358314/hang-seng-index-briefly-slips-below-23000-alibaba-leads-tech-sell",
      "https://www.thestandard.com.hk/finance/article/335675/Hang-Seng-Index-plunges-below-23000-points-in-early-trading-on-Friday",
      "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
      "https://www.cnbc.com/2026/06/17/fed-interest-rate-decision-june-2026.html",
      "https://www.gurufocus.com/economic_indicators/5731/shiller-pe-ratio-for-the-hang-seng-index"
    ]
  },
  {
    "id": "china",
    "name": "China / CSI 300",
    "short": "China",
    "group": "Greater China",
    "accent": "#ef4444",
    "proxy": "CSI 300 · Shanghai Composite",
    "archetype": "China's equity cycle is policy- and liquidity-driven more than earnings-driven: bull markets ignite when Beijing turns on credit (RRR/LPR cuts, property easing, \"national team\" buying) and retail leverage floods in, producing violent, narrow manias (2007, 2015, the 2024-25 stimulus rally) that overshoot fundamentals. Busts follow tightening, deleveraging campaigns, regulatory crackdowns, or external shocks (2008 GFC, 2018 trade war, the 2021-24 property/tech unwind). Because the float is retail-heavy and state-steered, the market trades on the perceived policy \"put\" rather than slow macro, making turns abrupt and sentiment-led.",
    "period": {
      "central": 7,
      "low": 4,
      "high": 10
    },
    "turns": [
      {
        "t": "2007-10",
        "k": "peak",
        "v": 5877,
        "e": "Pre-GFC A-share mania peak",
        "draw": null
      },
      {
        "t": "2008-11",
        "k": "trough",
        "v": 1607,
        "e": "Global financial crisis crash",
        "draw": -72.7
      },
      {
        "t": "2009-08",
        "k": "peak",
        "v": 3786,
        "e": "4-trillion-yuan stimulus rebound",
        "draw": 135.6
      },
      {
        "t": "2010-07",
        "k": "trough",
        "v": 2693,
        "e": "Tightening and property curbs",
        "draw": -28.9
      },
      {
        "t": "2011-04",
        "k": "peak",
        "v": 3279,
        "e": "Brief recovery high",
        "draw": 21.8
      },
      {
        "t": "2014-03",
        "k": "trough",
        "v": 2161,
        "e": "Slow-growth deleveraging grind",
        "draw": -34.1
      },
      {
        "t": "2015-06",
        "k": "peak",
        "v": 5380,
        "e": "Margin-fueled retail bubble",
        "draw": 149
      },
      {
        "t": "2016-01",
        "k": "trough",
        "v": 3000,
        "e": "Crash and circuit-breaker failure",
        "draw": -44.2
      },
      {
        "t": "2018-01",
        "k": "peak",
        "v": 4404,
        "e": "Supply-side reflation high",
        "draw": 46.8
      },
      {
        "t": "2019-01",
        "k": "trough",
        "v": 2935,
        "e": "US-China trade-war selloff",
        "draw": -33.4
      },
      {
        "t": "2021-02",
        "k": "peak",
        "v": 5808,
        "e": "Liquidity/tech post-COVID high",
        "draw": 97.9
      },
      {
        "t": "2024-02",
        "k": "trough",
        "v": 3120,
        "e": "Property bust and tech-crackdown unwind",
        "draw": -46.3
      },
      {
        "t": "2024-10",
        "k": "peak",
        "v": 4256,
        "e": "September stimulus 'bazooka' rally",
        "draw": 36.4
      },
      {
        "t": "2025-01",
        "k": "trough",
        "v": 3740,
        "e": "Post-rally consolidation pullback",
        "draw": -12.1
      },
      {
        "t": "2026-06",
        "k": "peak",
        "v": 4887,
        "e": "AI/easing-led advance, highest since 2021",
        "draw": 30.7
      }
    ],
    "now": {
      "level": 4887,
      "asOf": "2026-06-26",
      "ath": 5877,
      "athDate": "2007-10",
      "pctFromATH": -16.8,
      "pos": 68,
      "ytd": 11.5,
      "ret1y": 24.6,
      "phase": "Expansion",
      "phaseLabel": "Stimulus-led advance, not yet euphoric",
      "confidence": "medium",
      "read": "The CSI 300 closed near 4,887 on 2026-06-26, up ~24.6% over the trailing year and having touched ~5,031 intraday on June 22 (its highest since December 2021) before a ~2.6% pullback. It sits about 17% below the October-2007 all-time high of ~5,877 (the February-2021 high of ~5,808 was the prior-cycle peak), so this is a maturing recovery/expansion rather than a euphoric top. Cheap valuation (PE TTM ~15, CAPE ~17) and a still-supportive PBoC argue the cycle has room, but the rally is increasingly extended and analysts flag overheating risk after 2025's strong year."
    },
    "valuation": {
      "trailingPE": 15.1,
      "forwardPE": null,
      "cape": 17.4,
      "divYield": null,
      "pb": null,
      "note": "cheap vs US; CAPE ~17 below long-run, mid-range for China"
    },
    "proj": {
      "nextTurn": "peak",
      "central": "2026-12",
      "low": "2026-09",
      "high": "2027-06",
      "tilt": "mixed",
      "drivers": [
        "PBoC moderately-loose stance, LPR at record lows",
        "Q1-2026 GDP ~5% reduces stimulus urgency",
        "Cheap valuation plus AI/policy-put sentiment vs property/trade drag"
      ],
      "falsifier": "A sustained break back below ~4,000 on the CSI 300, or an explicit PBoC tightening/RRR-hike signal, would invalidate the continued-expansion-toward-a-peak path."
    },
    "regimeNote": "Mid-2026's mix of a still-accommodative PBoC (1Y LPR 3.0%, 5Y 3.5% at record lows), ~5% GDP growth, soft inflation, and cheap valuations is a net tailwind, but cautious data-dependent easing, lingering property strains, and US-China trade frictions cap the upside.",
    "sources": [
      "https://tradingeconomics.com/shsz300:ind",
      "https://www.gurufocus.com/economic_indicators/4424/csi-300-index",
      "https://www.gurufocus.com/economic_indicators/4569/pe-ratio-ttm-for-the-csi-300-index",
      "https://www.gurufocus.com/economic_indicators/4568/shiller-pe-ratio-for-the-csi-300-index",
      "https://www.ceicdata.com/en/china/china-securities-index--daily/cn-index-csi-300-index",
      "https://en.wikipedia.org/wiki/CSI_300_Index",
      "https://finance.yahoo.com/quote/000300.SS/history/"
    ]
  }
];
})();
