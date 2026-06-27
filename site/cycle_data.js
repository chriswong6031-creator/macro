/* ============================================================================
   cycle_data.js — Cycle Intelligence Dashboard · curated dataset
   ----------------------------------------------------------------------------
   SINGLE SOURCE OF TRUTH for the hero overlay, the scorecard sparklines and the
   (future) per-asset deep pages. Every number here is research-grounded and
   web-verified to mid-2026 (see research/CYCLE_INTELLIGENCE.md for sources).

   The oscillator is normalised "cycle position" on a 0–100 axis where, for EVERY
   cycle, 100 = euphoric cyclical high (price top / tightest credit spreads /
   deepest market calm) and 0 = capitulation low (crash / spread blow-out / vol
   spike). Credit and volatility are therefore stored in *risk-on* semantics:
   a "peak" = complacency/tights/calm, a "trough" = the stress event. That single
   convention makes the overlay legible — every line HIGH = late/expensive/
   euphoric, every line LOW = washed-out/stressed/cheap.

   turns[].t  : "YYYY-MM" (parsed to a decimal year by cycle_app.js)
   turns[].k  : "peak" (oscillator 100) | "trough" (oscillator 0)
   turns[].v  : raw level for the tooltip (price / index / bps), or null
   turns[].e  : the coincident event (one phrase)
   now        : the June-2026 read (phase, position, last turns, prose, confidence)
   proj       : the regime-conditioned forward path (next turn, central + range,
                drivers, falsifier, tilt) — all tweakable / Opus-updatable.
   ========================================================================== */
(function () {
  "use strict";

  window.CYCLE_META = {
    asOf: "2026-06-25",
    today: 2026.48,            // decimal year, ~late June 2026
    xDomain: [2004, 2031],     // hero calendar window (years)
    regime: {
      label: "Late-cycle stagflation scare",
      sub: "Oil-shock disinflation reversal",
      headline:
        "A 2026 Iran war / Strait-of-Hormuz oil shock is the master variable — " +
        "it spiked CPI to 4.2%, flipped the Fed from cutting to a hiking bias, and " +
        "lifted the dollar. A mid-June ceasefire is now unwinding the oil tail.",
      stats: [
        { k: "Fed funds", v: "3.50–3.75%", note: "on hold · hiking bias" },
        { k: "US 10Y", v: "4.41%", note: "+18bp YoY" },
        { k: "DXY", v: "101.4", note: "strong-dollar regime" },
        { k: "CPI", v: "4.2%", note: "hot · reaccelerating" },
        { k: "VIX", v: "16", note: "calm post-ceasefire" },
        { k: "Recession odds", v: "30–40%", note: "12-month" }
      ],
      tilt:
        "Restrictive Fed + strong dollar + 30–40% recession odds cap demand-sensitive " +
        "cyclicals; the cheap-liquidity tailwind that powered 2021-era booms is absent. " +
        "Oil is the swing factor: normalisation → soft-landing tailwind; a re-spike → " +
        "stagflationary headwind across the board."
    }
  };

  // Shared phase taxonomy (oscillator position + slope) — drives chips + shading.
  window.CYCLE_PHASES = {
    Trough:    { label: "Trough",    short: "Bottoming",  hue: "#e06464" },
    Recovery:  { label: "Recovery",  short: "Early up",   hue: "#45b873" },
    Expansion: { label: "Expansion", short: "Trending up",hue: "#3da564" },
    Peak:      { label: "Peak",      short: "Topping",    hue: "#e0a030" },
    Downturn:  { label: "Downturn",  short: "Rolling over",hue: "#e0556b" }
  };

  window.CYCLES = [
    /* ---------------------------------------------------------------- SEMIS -- */
    {
      id: "semis", name: "Semiconductors", short: "Semis", group: "Technology",
      accent: "#38bdf8",
      proxy: "PHLX Semiconductor (SOX) · WSTS sales",
      archetype:
        "Capacity-led: a demand surprise lifts utilisation → fabs/equipment over-invest " +
        "on a ~2-yr lag → supply lands as demand cools → an inventory glut crushes ASPs " +
        "until cuts re-tighten supply. Memory pricing is the whip.",
      period: { central: 3.8, low: 3.0, high: 4.5 },
      turns: [
        { t: "2000-03", k: "peak",   v: 1362, e: "Dot-com / telecom bubble top" },
        { t: "2001-10", k: "trough", v: null, e: "Dot-com bust · 9/11 demand collapse" },
        { t: "2004-06", k: "peak",   v: null, e: "First post-bubble inventory top" },
        { t: "2008-11", k: "trough", v: null, e: "Global financial crisis" },
        { t: "2010-06", k: "peak",   v: null, e: "Post-GFC restock" },
        { t: "2012-12", k: "trough", v: null, e: "PC decline · weak memory" },
        { t: "2018-10", k: "peak",   v: null, e: "Crypto/datacenter/memory super-cycle top" },
        { t: "2019-04", k: "trough", v: null, e: "Memory glut · US–China trade war" },
        { t: "2022-01", k: "peak",   v: 4068, e: "COVID shortage blow-off" },
        { t: "2023-06", k: "trough", v: null, e: "Glut clears · genAI demand ignites" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Topping on narrowing breadth",
        pos: 91, lastTrough: "2023-06", lastPeak: "2022-01", confidence: "medium",
        read:
          "Topping now even as absolute sales grind higher: the SOX hit a record ~14,655 (Jun-22) " +
          "but led by only NVDA/AMD/AVGO with the advance-decline line diverging, and Broadcom's " +
          "Jun-3 refusal to raise its AI outlook triggered a ~10% wipeout. The YoY rate-of-change " +
          "peak is base-locked for Q3-2026 — so the prior 'still rising into H1-2027' read was lagging."
      },
      proj: {
        nextTurn: "peak", central: "2026-11", low: "2026-09", high: "2027-03", tilt: "mixed",
        drivers: ["the rate-of-change peak is base-locked (H2-2025 base ~doubles)", "the equity tape is already distributing (breadth narrowing)", "hyperscaler AI-capex durability & ROI"],
        falsifier:
          "Wrong if a new SOX high above 14,655 comes on BROADENING breadth (A/D confirming, not " +
          "just the big-3) with Broadcom raising its AI outlook and hyperscaler capex guides revised " +
          "up — that flips it back to expansion into H1-2027."
      },
      regimeNote: "AI-capex still the tailwind, but the second derivative has turned — the cycle is topping on narrowing breadth."
    },

    /* --------------------------------------------------------------- MEMORY -- */
    {
      id: "memory", name: "Memory (DRAM / NAND)", short: "Memory", group: "Technology",
      accent: "#818cf8",
      proxy: "DRAM contract ASP · big-3 capex",
      archetype:
        "The sharpest commodity sub-cycle in chips: an oligopoly over-builds into strong " +
        "pricing → bit-supply outruns demand → ASPs collapse 50–80% → producers cut → " +
        "undersupply re-ignites a violent spike.",
      period: { central: 3.5, low: 2.5, high: 4.5 },
      turns: [
        { t: "2006-06", k: "peak",   v: null, e: "Vista / PC cycle top" },
        { t: "2008-12", k: "trough", v: null, e: "GFC · Qimonda distress" },
        { t: "2010-06", k: "peak",   v: null, e: "Post-GFC restock" },
        { t: "2013-01", k: "trough", v: null, e: "PC slump · consolidation to 3 players" },
        { t: "2014-12", k: "peak",   v: null, e: "Mobile / server demand" },
        { t: "2016-06", k: "trough", v: null, e: "Pre-super-cycle low" },
        { t: "2018-10", k: "peak",   v: null, e: "2017–18 DRAM/NAND super-cycle blow-off" },
        { t: "2019-09", k: "trough", v: null, e: "Datacenter digestion · trade war" },
        { t: "2021-12", k: "peak",   v: null, e: "COVID PC/server pull-forward" },
        { t: "2023-06", k: "trough", v: null, e: "Post-COVID glut · producers cut output" }
      ],
      now: {
        phase: "Expansion", phaseLabel: "Level rising, momentum peaked",
        pos: 87, lastTrough: "2023-06", lastPeak: "2021-12", confidence: "medium",
        read:
          "The latest, hottest leg: Q2 DRAM contracts are still +58–63% and Micron's Jun-24 print " +
          "($41.5B, +268% YoY, HBM booked into 2028) keeps the ASP LEVEL rising — but the " +
          "rate-of-change peak is already in (Q1-2026 contract growth halved to ~60%). The level " +
          "peaks a step behind semis, ~Q4-2026."
      },
      proj: {
        nextTurn: "peak", central: "2026-12", low: "2026-09", high: "2027-06", tilt: "tailwind",
        drivers: ["the rate-of-change peak is already in (Q1-26 contract growth halved)", "HBM vs commodity wafer mix", "big-3 discipline vs pulling commodity supply forward (SK Hynix DDR5 reallocation)"],
        falsifier:
          "Wrong if Q3-2026 DRAM contract prices print flat-to-down QoQ, or spot DDR5 stops climbing " +
          "and supplier inventories normalise off record lows — that dates the level peak to now."
      },
      regimeNote: "Demand-led, supply-disciplined; level still rising but the momentum peak is in — the last hot leg before the roll."
    },

    /* -------------------------------------------------------------- HOUSING -- */
    {
      id: "housing", name: "Housing / Real Estate", short: "Housing", group: "Real assets",
      accent: "#f4a259",
      proxy: "Case-Shiller · starts · the 18-yr land cycle",
      archetype:
        "The ~18-yr land cycle (Hoyt / Harrison / Anderson): cheap credit capitalises into " +
        "land prices over a long ~14-yr upswing; a late-cycle land-grab (the 'Winner's Curse') " +
        "tops it, a banking/credit bust follows, then a ~4-yr rebuild.",
      period: { central: 18, low: 15, high: 20 },
      turns: [
        { t: "1973-11", k: "peak",   v: null, e: "1973–74 oil shock / property top" },
        { t: "1975-06", k: "trough", v: null, e: "Post-recession rebuild begins" },
        { t: "1989-09", k: "peak",   v: null, e: "Late-80s top → S&L crisis" },
        { t: "1992-06", k: "trough", v: null, e: "Early-90s housing low" },
        { t: "2006-07", k: "peak",   v: 206,  e: "2000s bubble top (Case-Shiller ATH)" },
        { t: "2012-02", k: "trough", v: 134,  e: "GFC housing-bust bottom" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Late-cycle plateau · topping",
        pos: 90, lastTrough: "2012-02", lastPeak: "2006-07", confidence: "medium",
        read:
          "The 18-yr clock sits ~14 years up — exactly the peak window. Case-Shiller is flat " +
          "(+0.7% YoY, 10th straight month of negative real returns), starts have collapsed to " +
          "a 6-yr low, and >half of metros show YoY price declines. The top tell is present."
      },
      proj: {
        nextTurn: "peak", central: "2026-09", low: "2025-09", high: "2028-06", tilt: "headwind",
        drivers: ["mortgage-rate path / Fed cuts (a cut could extend it)", "structural supply shortage cushioning prices", "credit conditions"],
        falsifier:
          "Wrong if Case-Shiller posts fresh accelerating ATHs AND starts/permits re-accelerate " +
          "above ~1.5M SAAR through 2027 — a new leg up, not a rollover. A confirmed top implies " +
          "a downswing troughing ~2029–2032."
      },
      regimeNote: "Headwind: high mortgage rates + a strong dollar pin affordability; the clock and the macro align bearishly."
    },

    /* ------------------------------------------------------- BUSINESS CYCLE -- */
    {
      id: "business", name: "US Business Cycle", short: "Business", group: "Macro",
      accent: "#8896b5",
      proxy: "ISM Manufacturing PMI · NBER",
      archetype:
        "The ~3–5-yr Kitchin inventory cycle visible in the ISM PMI (firms over/under-order " +
        "around final demand) nested inside the NBER expansion/recession cycle. Manufacturing " +
        "leads; employment lags.",
      period: { central: 4.5, low: 3, high: 6 },
      turns: [
        { t: "2009-12", k: "peak",   v: null, e: "Post-GFC restock" },
        { t: "2012-11", k: "trough", v: null, e: "Euro-crisis soft patch" },
        { t: "2014-10", k: "peak",   v: null, e: "Synchronised global growth" },
        { t: "2016-01", k: "trough", v: null, e: "Manufacturing recession · oil bust" },
        { t: "2018-08", k: "peak",   v: 60.8, e: "Late-cycle manufacturing top" },
        { t: "2020-04", k: "trough", v: 41,   e: "COVID collapse" },
        { t: "2021-03", k: "peak",   v: 64.7, e: "Post-COVID restock boom" },
        { t: "2023-06", k: "trough", v: 46,   e: "2022–23 mfg / inventory recession" },
        { t: "2026-05", k: "peak",   v: 54,   e: "Mfg re-expansion (ISM 54, cresting)" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Mature expansion · ISM cresting",
        pos: 74, lastTrough: "2023-06", lastPeak: "2026-05", confidence: "low",
        read:
          "The expansion is ~74 months from the Apr-2020 trough — past the postwar average, so " +
          "late-cycle. The ISM/Kitchin upswing hit 54 in May (best since 2022) but looks to be " +
          "cresting. NBER never confirms turns in real time."
      },
      proj: {
        nextTurn: "trough", central: "2027-06", low: "2026-09", high: "2028-06", tilt: "headwind",
        drivers: ["Fed rate path", "labor-market slack feeding through", "housing drag"],
        falsifier:
          "ISM holding >54 through H2-2026 with firm new orders refutes an imminent inventory " +
          "peak; unemployment ≤4.5% and positive payrolls through 2027 refute the late-cycle " +
          "recession call (soft-landing extension)."
      },
      regimeNote: "Headwind: late-cycle age + restrictive policy; the inventory upswing is cresting into a 2027 recession risk."
    },

    /* ---------------------------------------------------------------- OIL --- */
    {
      id: "oil", name: "Crude Oil / Energy", short: "Oil", group: "Energy",
      accent: "#c77d3a",
      proxy: "WTI / Brent · US rig count",
      archetype:
        "High prices pull forward E&P capex → new supply lands with a lag → glut → crash → " +
        "capex cut and shut-ins → deficit → the next spike. Demand (recessions) and supply " +
        "(OPEC, wars) shocks overlay the capex clock violently.",
      period: { central: 7, low: 5, high: 10 },
      turns: [
        { t: "1980-04", k: "peak",   v: 35,   e: "Iranian revolution · 2nd oil shock" },
        { t: "1986-04", k: "trough", v: 10,   e: "Saudi share war (1980s glut)" },
        { t: "1990-10", k: "peak",   v: 40,   e: "Gulf War spike" },
        { t: "1998-12", k: "trough", v: 11,   e: "Asian-crisis demand collapse" },
        { t: "2008-07", k: "peak",   v: 147,  e: "Demand super-cycle blow-off" },
        { t: "2009-02", k: "trough", v: 34,   e: "GFC demand crash" },
        { t: "2013-08", k: "peak",   v: 110,  e: "2011–14 plateau · pre-shale tightness" },
        { t: "2016-02", k: "trough", v: 26,   e: "US shale glut · OPEC share war" },
        { t: "2018-10", k: "peak",   v: 76,   e: "Pre-Iran-sanctions tightness" },
        { t: "2020-04", k: "trough", v: -37,  e: "COVID + Cushing storage (negative WTI)" },
        { t: "2022-06", k: "peak",   v: 122,  e: "Russia invades Ukraine" },
        { t: "2025-12", k: "trough", v: 57,   e: "2025 glut slide · OPEC+ unwind" },
        { t: "2026-02", k: "peak",   v: 100,  e: "2026 Iran war · Hormuz closed (spike)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-war-spike normalisation",
        pos: 44, lastTrough: "2025-12", lastPeak: "2026-02", confidence: "low",
        read:
          "A war premium spiked WTI above $100 in spring, then a US–Iran deal to reopen Hormuz " +
          "collapsed it back to the ~$70s. The underlying capex cycle is still early/oversupplied " +
          "(US oil rigs only ~433) — geopolitics dominates the tape."
      },
      proj: {
        nextTurn: "trough", central: "2026-10", low: "2026-06", high: "2027-06", tilt: "mixed",
        drivers: ["how fast Hormuz fully reopens & Iranian flows return", "OPEC+ spare-capacity policy", "US shale discipline vs growth"],
        falsifier:
          "WTI sustaining below ~$55 for 2+ months proves the down-leg isn't over (trough not in); " +
          "a clean hold above ~$95 absent a fresh shock proves a fundamental up-cycle is underway. " +
          "Next genuine capex peak likely 2028–2030."
      },
      regimeNote: "The master variable: oil's path decides whether the whole regime resolves to soft-landing or stagflation."
    },

    /* -------------------------------------------------------------- COPPER -- */
    {
      id: "copper", name: "Copper / Base Metals", short: "Copper", group: "Metals",
      accent: "#e08a5b",
      proxy: "LME copper · exchange inventories",
      archetype:
        "New mine supply takes ~7–10 yrs from discovery, so demand upswings tighten the market " +
        "for years before supply responds → multi-year deficit & overshoot → new mines + softening " +
        "demand flip it to surplus → underinvestment seeds the next deficit.",
      period: { central: 8, low: 4, high: 10 },
      turns: [
        { t: "2008-07", k: "peak",   v: 8940,  e: "Commodity super-cycle blow-off" },
        { t: "2008-12", k: "trough", v: 2850,  e: "GFC demand collapse" },
        { t: "2011-02", k: "peak",   v: 10190, e: "China stimulus + global QE" },
        { t: "2016-01", k: "trough", v: 4330,  e: "China slowdown · post-super-cycle surplus" },
        { t: "2018-06", k: "peak",   v: 7300,  e: "Synchronised growth · pre-trade-war" },
        { t: "2020-03", k: "trough", v: 4700,  e: "COVID demand shock" },
        { t: "2022-03", k: "peak",   v: 10845, e: "Post-COVID reflation · green demand" },
        { t: "2022-07", k: "trough", v: 7000,  e: "Fed hiking · China property scare" },
        { t: "2026-01", k: "peak",   v: 14527, e: "Structural deficit · AI/grid demand (ATH)" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Late structural up-leg · record",
        pos: 88, lastTrough: "2022-07", lastPeak: "2026-01", confidence: "medium",
        read:
          "A new ATH (~$14,527/t in Jan) has eased to ~$13,300 on a firmer dollar — a consolidation, " +
          "not a top. The ICSG flips to its first structural deficit since 2009. Consensus sees a " +
          "fade from records even as the multi-year deficit persists."
      },
      proj: {
        nextTurn: "trough", central: "2027-06", low: "2026-09", high: "2028-06", tilt: "mixed",
        drivers: ["China demand / property & stimulus", "speed of grid + EV + data-center electrification", "mine-supply additions & disruptions"],
        falsifier:
          "A break and hold below ~$9,000/t for 2+ months kills the deficit-floor thesis (genuine bear); " +
          "a sustained break above ~$15,000/t confirms the up-leg isn't yet mature. Next secular high " +
          "likely 2029–2030."
      },
      regimeNote: "Mixed: a strong dollar + recession odds cap the price, but the structural deficit floors downside."
    },

    /* ------------------------------------------------------------- URANIUM -- */
    {
      id: "uranium", name: "Uranium", short: "Uranium", group: "Energy",
      accent: "#7fd43a",
      proxy: "Spot U₃O₈ · SPUT flows",
      archetype:
        "A thin, sentiment-driven spot market where tiny incremental demand ratchets price " +
        "violently against slow primary supply (long mine lead-times, a producer oligopoly) — " +
        "long bear flats punctuated by parabolic boom spikes.",
      period: { central: 9.5, low: 8, high: 17 },
      turns: [
        { t: "2007-06", k: "peak",   v: 136, e: "Cigar Lake flood + China build" },
        { t: "2016-11", k: "trough", v: 18,  e: "Post-Fukushima glut · secondary supply" },
        { t: "2024-01", k: "peak",   v: 106, e: "Nuclear renaissance · SMR/AI demand" },
        { t: "2025-03", k: "trough", v: 64,  e: "2025 range-bound weakness · spot lull" }
      ],
      now: {
        phase: "Recovery", phaseLabel: "Mid-bull consolidation · higher-low base",
        pos: 58, lastTrough: "2025-03", lastPeak: "2024-01", confidence: "medium",
        read:
          "Spot ~$85/lb, a constructive higher-low above the 2025 $63 trough, while the term price " +
          "sits at a 17-yr high — the classic precursor to spot follow-through. A coiled spring: " +
          "supply discipline + reactor/SMR/AI demand vs thin near-term utility buying."
      },
      proj: {
        nextTurn: "peak", central: "2027-03", low: "2026-09", high: "2028-06", tilt: "tailwind",
        drivers: ["pace of utility long-term contracting", "SPUT / financial buying flows", "reactor-restart & SMR timelines"],
        falsifier:
          "A sustained close below ~$63/lb breaks the higher-low structure and reframes 2024–26 as a " +
          "completed top rather than a base."
      },
      regimeNote: "Tailwind: energy-security + AI/data-center nuclear demand are structural, not liquidity-driven."
    },

    /* ---------------------------------------------------------------- GOLD -- */
    {
      id: "gold", name: "Gold / Precious Metals", short: "Gold", group: "Metals",
      accent: "#e7c03b",
      proxy: "Spot gold · real rates · CB buying",
      archetype:
        "A secular monetary cycle driven by real interest rates (gold rises as real yields fall), " +
        "the dollar, and official-sector demand. Long bulls run on inflation fear, debasement and " +
        "central-bank accumulation; bears come when real rates rise.",
      period: { central: 17, low: 15, high: 20 },
      turns: [
        { t: "1980-01", k: "peak",   v: 850,  e: "Inflation · Iran hostage crisis" },
        { t: "2001-04", k: "trough", v: 255,  e: "End of 20-yr bear (Brown's Bottom)" },
        { t: "2011-09", k: "peak",   v: 1921, e: "Euro debt crisis · post-GFC QE" },
        { t: "2015-12", k: "trough", v: 1050, e: "Fed hike cycle · strong USD" },
        { t: "2026-01", k: "peak",   v: 5589, e: "Tariff + Iran panic (parabolic ATH)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-blow-off correction",
        pos: 62, lastTrough: "2015-12", lastPeak: "2026-01", confidence: "medium",
        read:
          "Gold went vertical to ~$5,589 in January on tariff + Iran geopolitics, then corrected " +
          "hard to ~$4,000 as the inflation read repriced the Fed hawkishly (higher real rates). " +
          "Record central-bank buying is the structural floor — a violent correction, not a 2011-style top."
      },
      proj: {
        nextTurn: "trough", central: "2026-12", low: "2026-09", high: "2027-06", tilt: "mixed",
        drivers: ["Fed real-rate path (the dominant lever)", "US–Iran resolution vs escalation", "central-bank purchase pace"],
        falsifier:
          "A sustained close below ~$3,300/oz breaks the secular-bull structure (a 2011-style top); " +
          "the bull path retests/exceeds ~$5,589 in 2027 (some see ~$6,000+)."
      },
      regimeNote: "Mixed: sticky-high real rates are the near-term headwind; debasement + CB demand are the long floor."
    },

    /* ------------------------------------------------------------- BITCOIN -- */
    {
      id: "bitcoin", name: "Bitcoin / Crypto", short: "Bitcoin", group: "Digital",
      accent: "#f7931a",
      proxy: "BTC/USD · the 4-yr halving",
      archetype:
        "A supply-shock momentum cycle anchored to the ~4-yr halving: issuance halves, reflexive " +
        "demand drives a blow-off ~12–18 months later, then a multi-quarter drawdown to a deep " +
        "trough. Amplitude is compressing as ETF/institutional flows replace retail reflexivity.",
      period: { central: 4, low: 3.5, high: 4.5 },
      turns: [
        { t: "2013-11", k: "peak",   v: 1150,   e: "First mainstream mania (Mt. Gox era)" },
        { t: "2015-01", k: "trough", v: 200,    e: "Post-Mt.Gox capitulation" },
        { t: "2017-12", k: "peak",   v: 19800,  e: "ICO mania / retail blow-off" },
        { t: "2018-12", k: "trough", v: 3200,   e: "Crypto-winter capitulation" },
        { t: "2021-11", k: "peak",   v: 69044,  e: "Pandemic liquidity · institutional adoption" },
        { t: "2022-11", k: "trough", v: 15479,  e: "FTX collapse" },
        { t: "2025-10", k: "peak",   v: 125836, e: "Spot-ETF inflows (ATH)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-peak cyclical bear",
        pos: 45, lastTrough: "2022-11", lastPeak: "2025-10", confidence: "medium",
        read:
          "The 4-yr clock held — the peak landed ~18 months post-halving and price has since " +
          "broken $62k support (~50% off the ATH) with heavy long liquidations. The drawdown is " +
          "shallower than 2018 (~84%) / 2022 (~77%), consistent with the ETF-dampened thesis."
      },
      proj: {
        nextTurn: "trough", central: "2026-10", low: "2026-07", high: "2027-04", tilt: "headwind",
        drivers: ["spot-ETF / institutional flows damping volatility", "macro liquidity & rate path", "whether the 4-yr pattern is weakening"],
        falsifier:
          "A new ATH (> ~$126k) before the trough invalidates 'we're in the down-leg'; a decisive " +
          "break below the ~$64k halving level toward sub-$40k falsifies the 'shallow, ETF-cushioned' read."
      },
      regimeNote: "Headwind: the priced-out-cuts, hiking-bias regime drains the liquidity that fuels crypto up-legs."
    },

    /* -------------------------------------------------------------- CREDIT -- */
    {
      id: "credit", name: "Credit Cycle", short: "Credit", group: "Macro",
      accent: "#b06ce6",
      proxy: "ICE BofA US HY OAS (risk-on inverted)",
      archetype:
        "Corporate-credit boom-bust: tight spreads + easy lending fuel leverage and complacency " +
        "at the top; a shock triggers a spread blow-out, banks tighten, defaults clear, then " +
        "spreads re-compress and the cycle restarts. (Plotted risk-on: tights = high, blow-out = low.)",
      period: { central: 6.5, low: 5, high: 8 },
      turns: [
        { t: "2007-06", k: "peak",   v: 241,  e: "Pre-GFC peak complacency (tights)" },
        { t: "2008-12", k: "trough", v: 2182, e: "GFC / Lehman spread blow-out" },
        { t: "2014-06", k: "peak",   v: 340,  e: "Pre-energy-bust complacency" },
        { t: "2016-02", k: "trough", v: 887,  e: "Oil / energy HY default wave" },
        { t: "2018-09", k: "peak",   v: 316,  e: "Late-cycle complacency" },
        { t: "2020-03", k: "trough", v: 1087, e: "COVID shock blow-out" },
        { t: "2021-12", k: "peak",   v: 305,  e: "Post-COVID stimulus complacency" },
        { t: "2022-10", k: "trough", v: 600,  e: "Fed hiking · regional-bank scare (partial)" },
        { t: "2026-06", k: "peak",   v: 263,  e: "Late-cycle complacency · near record-tight" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Late-cycle complacency · tights",
        pos: 94, lastTrough: "2022-10", lastPeak: "2026-06", confidence: "medium",
        read:
          "HY spreads ~263bp, near the 2007 record-tight, pricing benign credit — yet banks are " +
          "tightening C&I standards and the leveraged-loan default rate runs ~7% (2× its average). " +
          "A classic late-cycle divergence: little cushion against a shock."
      },
      proj: {
        nextTurn: "trough", central: "2027-06", low: "2026-12", high: "2029-06", tilt: "headwind",
        drivers: ["timing/severity of any macro or default shock", "the loan-vs-bond default divergence", "how long private-credit refi access suppresses defaults"],
        falsifier:
          "HY OAS above ~500bp confirms the turn to stress; spreads holding ≤300bp with loan defaults " +
          "falling toward ~3.4% through 2027 falsifies 'late-cycle, turn imminent'."
      },
      regimeNote: "Headwind building: the tightest part of the cycle, with the thinnest cushion against the regime's shocks."
    },

    /* ------------------------------------------------------------ SHIPPING -- */
    {
      id: "shipping", name: "Shipping / Freight", short: "Shipping", group: "Industrial",
      accent: "#2bb6c4",
      proxy: "Baltic Dry Index · container WCI",
      archetype:
        "A capex-driven boom-bust: the orderbook lags demand, so capacity overshoots and collapses " +
        "rates — ~3–4-yr freight sub-cycles inside a ~7–10-yr capex super-cycle. Reroutes (Red Sea / " +
        "Hormuz) tighten effective supply.",
      period: { central: 3.5, low: 3, high: 4 },
      turns: [
        { t: "2008-05", k: "peak",   v: 11793, e: "China super-cycle · pre-GFC trade peak" },
        { t: "2008-12", k: "trough", v: 663,   e: "GFC trade collapse" },
        { t: "2010-05", k: "peak",   v: 4200,  e: "Post-GFC restock (newbuild flood begins)" },
        { t: "2016-02", k: "trough", v: 290,   e: "All-time low · fleet oversupply" },
        { t: "2021-10", k: "peak",   v: 5650,  e: "COVID supply-chain snarl · container boom" },
        { t: "2023-02", k: "trough", v: 530,   e: "Post-COVID destock" }
      ],
      now: {
        phase: "Recovery", phaseLabel: "Mid-cycle recovery · split sub-cycles",
        pos: 52, lastTrough: "2023-02", lastPeak: "2021-10", confidence: "low",
        read:
          "BDI ~2,634 (+58% YoY) but cooling off a spring high, while container WCI surges to an " +
          "18-month high on cargo frontloaded ahead of July US tariffs. The two sub-cycles have " +
          "diverged — container spiking, dry-bulk softening."
      },
      proj: {
        nextTurn: "peak", central: "2026-11", low: "2026-09", high: "2027-03", tilt: "mixed",
        drivers: ["timing/scope of July US tariffs & whether frontloading is a pull-forward", "Red Sea / Hormuz status (war tightens, peace loosens)", "China commodity demand"],
        falsifier:
          "Container WCI holding above ~$4,000/40ft through Q4-2026 (past the tariff window into the weak " +
          "winter) breaks the 'frontloading → rollover' thesis and implies structural demand."
      },
      regimeNote: "Mixed / two-faced: the Iran war tightens freight via reroutes; the ceasefire loosens it."
    },

    /* ------------------------------------------------------------- LITHIUM -- */
    {
      id: "lithium", name: "Lithium / Battery Materials", short: "Lithium", group: "Metals",
      accent: "#34d399",
      proxy: "Battery-grade Li carbonate spot",
      archetype:
        "A commodity capex boom-bust amplified by EV/ESS demand reflexivity and concentrated " +
        "Chinese supply: mine/refinery lead-times drive long supply lags and deep overshoots " +
        "in both directions.",
      period: { central: 5, low: 4, high: 6 },
      turns: [
        { t: "2020-06", k: "trough", v: 6500,  e: "COVID demand trough · pre-EV-boom" },
        { t: "2022-11", k: "peak",   v: 80000, e: "EV demand explosion + bottleneck (ATH)" },
        { t: "2025-02", k: "trough", v: 9000,  e: "Peak oversupply · 4-yr low" }
      ],
      now: {
        phase: "Recovery", phaseLabel: "Early recovery · first leg up",
        pos: 30, lastTrough: "2025-02", lastPeak: "2022-11", confidence: "low",
        read:
          "Carbonate ~$22–25k/t, up ~159% YoY off the Feb-2025 sub-$10k bottom, on genuine ESS/EV " +
          "demand + supply discipline — but down ~13% MoM as a possible CATL Jianxiawo restart caps " +
          "the rally. The recovery is real but fragile; idled Chinese supply can return fast."
      },
      proj: {
        nextTurn: "peak", central: "2027-06", low: "2026-09", high: "2028-06", tilt: "mixed",
        drivers: ["CATL Jianxiawo & other Chinese restart decisions (the biggest swing)", "EV + grid-storage demand trajectory", "Chinese policy / quota signals"],
        falsifier:
          "A confirmed Jianxiawo restart PLUS spot back below ~$15,000/t invalidates the demand-driven " +
          "deficit / sustained-recovery read (a return to oversupply)."
      },
      regimeNote: "Mixed: rates/dollar weigh on the marginal price, but ESS/EV demand is a structural pull — early in its arc."
    },

    /* --------------------------------------------------------- AGRICULTURE -- */
    {
      id: "agriculture", name: "Agriculture / Grains", short: "Agriculture", group: "Energy",
      accent: "#bccb3f",
      proxy: "GSCI Agriculture · corn / wheat / soy",
      archetype:
        "A weather- and stocks-to-use-driven soft-commodity boom-bust: supply shocks (drought, " +
        "war, export bans) spike prices, then big harvests and high acreage rebuild stocks and " +
        "grind prices below breakeven. Sharp brief peaks, long grinding troughs.",
      period: { central: 5.5, low: 4, high: 7 },
      turns: [
        { t: "2008-06", k: "peak",   v: null, e: "Biofuel mandate + oil $140 + export curbs" },
        { t: "2009-09", k: "trough", v: null, e: "Post-GFC demand unwind" },
        { t: "2012-08", k: "peak",   v: null, e: "US Midwest drought (corn ~$8 record)" },
        { t: "2016-08", k: "trough", v: null, e: "Record global harvests" },
        { t: "2022-05", k: "peak",   v: null, e: "Russia–Ukraine Black Sea grain shock" },
        { t: "2025-09", k: "trough", v: null, e: "4th straight year below breakeven" }
      ],
      now: {
        phase: "Trough", phaseLabel: "Late-cycle bottoming",
        pos: 16, lastTrough: "2025-09", lastPeak: "2022-05", confidence: "medium",
        read:
          "Corn ~$4.07, soy ~$11.09 (4-mo low), wheat ~$5.86 — all below breakeven for a 4th year. " +
          "Notably the 2026 Iran war hit the COST side (fertiliser +30–40%) but not grain supply (the " +
          "Mideast is a net food importer), so it hasn't ignited a bull — wet US weather is capping prices."
      },
      proj: {
        nextTurn: "peak", central: "2027-06", low: "2026-09", high: "2028-06", tilt: "mixed",
        drivers: ["2026/27 growing-season weather (a drought is the classic ignition)", "energy/fertiliser cost-floor", "China imports · biofuel demand"],
        falsifier:
          "Corn holding above ~$5.50–6.00/bu into tightening stocks-to-use means the trough thesis is " +
          "wrong and a bull leg has begun."
      },
      regimeNote: "Mixed: the cheapest, most washed-out real-asset cycle — a coiled weather-trade with a cost-push floor."
    },

    /* ----------------------------------------------------------- VOLATILITY -- */
    {
      id: "vol", name: "Volatility Regime", short: "Volatility", group: "Macro",
      accent: "#ef5d6b",
      proxy: "CBOE VIX (complacency↔stress)",
      archetype:
        "A regime oscillation, not a periodic cycle: long calm stretches (vol-selling builds leverage " +
        "and complacency) punctuated by violent, fast-decaying spikes when leverage unwinds. " +
        "(Plotted risk-on: calm/complacency = high, a stress spike = low.)",
      period: { central: 2, low: 1, high: 3 },
      turns: [
        { t: "2008-11", k: "trough", v: 80, e: "GFC / Lehman spike (VIX ~80, max stress)" },
        { t: "2017-06", k: "peak",   v: 10, e: "Short-vol complacency (VIX ~9–11)" },
        { t: "2018-02", k: "trough", v: 37, e: "Volmageddon (XIV blow-up)" },
        { t: "2019-12", k: "peak",   v: 13, e: "Calm before COVID" },
        { t: "2020-03", k: "trough", v: 82, e: "COVID crash (highest close ever)" },
        { t: "2021-11", k: "peak",   v: 16, e: "Post-COVID reflation calm" },
        { t: "2024-08", k: "trough", v: 65, e: "Yen carry-trade unwind" },
        { t: "2025-04", k: "trough", v: 52, e: "'Liberation Day' tariff crash" },
        { t: "2026-03", k: "trough", v: 35, e: "2026 Iran war / Hormuz spike" },
        { t: "2026-06", k: "peak",   v: 16, e: "Ceasefire · calm rebuilding" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Normalising → calm · complacency",
        pos: 80, lastTrough: "2026-03", lastPeak: "2026-06", confidence: "medium",
        read:
          "VIX back to ~16 after the US–Iran deal — pre-war levels, complacency rebuilding. The " +
          "March Iran spike (~35) was notably milder than 2024's carry unwind (~65) or 2025's tariff " +
          "crash (~52). The question is never if calm ends, only when."
      },
      proj: {
        nextTurn: "trough", central: "2027-03", low: "2026-09", high: "2028-06", tilt: "n/a",
        drivers: ["fragile Iran ceasefire / Hormuz re-closure", "AI-tech valuation air-pocket", "tariff re-escalation"],
        falsifier:
          "A sustained VIX >25–30 for more than a few sessions flips the regime from calm to stress. " +
          "Base rate: a >30 spike within ~6–18 months."
      },
      regimeNote: "The complacency gauge — high now, but the regime's live tails (oil, tariffs, AI) keep the next spike close."
    },

    /* ------------------------------------------------------------- BIOTECH -- */
    {
      id: "biotech", name: "Biotech / IPO", short: "Biotech", group: "Digital",
      accent: "#e66fb0",
      proxy: "XBI · the IPO window",
      archetype:
        "A risk-appetite + funding cycle: cheap money floods early-stage biotech (IPO/SPAC mania, " +
        "XBI rips) → rate hikes freeze the window and force a brutal multi-year bear → M&A + rate " +
        "relief reopen the window and re-rate survivors.",
      period: { central: 6, low: 5, high: 7 },
      turns: [
        { t: "2015-07", k: "peak",   v: 90,  e: "First biotech boom top" },
        { t: "2016-11", k: "trough", v: 48,  e: "Drug-pricing overhang" },
        { t: "2021-02", k: "peak",   v: 174, e: "COVID mania · SPAC/issuance record (ATH)" },
        { t: "2023-06", k: "trough", v: 62,  e: "Capitulation · cash-burn / down-rounds" }
      ],
      now: {
        phase: "Expansion", phaseLabel: "Recovery · IPO window reopening",
        pos: 70, lastTrough: "2023-06", lastPeak: "2021-02", confidence: "medium",
        read:
          "XBI ~$154, top of its 52-wk range but still ~12% below the 2021 ATH. The IPO window is " +
          "reopening but selective (record-size, late-stage deals; most 2026 debuts hold issue) — a " +
          "high-bar reopening, not a 2021-style broad mania."
      },
      proj: {
        nextTurn: "peak", central: "2027-06", low: "2026-09", high: "2028-06", tilt: "headwind",
        drivers: ["Fed rate path (long-duration, rate-sensitive)", "large-pharma M&A (the patent cliff)", "FDA / drug-pricing policy"],
        falsifier:
          "XBI rolling back below ~$120–125 with deteriorating IPO pricing means the window-open " +
          "expansion has stalled; a clean break above ~$175 confirms the next leg."
      },
      regimeNote: "Headwind: the most rate-sensitive risk cycle — a hawkish Fed or a vol spike re-shuts the window."
    },

    /* ===================== EXPANSION — 8 more asset classes ================== */
    /* researched 2026-06-25 (workflow); oscillator semantics: peak = euphoric
       cyclical high, trough = capitulation low (bonds = bond-PRICE; dollar = strong). */

    /* ----------------------------------------------------------- LONG BONDS -- */
    {
      id: "long-bonds", name: "US Long Treasurys / Rate Cycle", short: "Long Bonds", group: "Rates & Sovereign",
      accent: "#5d6cef",
      proxy: "TLT · 10Y/30Y yield",
      archetype:
        "Inflation/policy drives the discount rate: disinflation + cuts push yields down and bond " +
        "prices to euphoric highs; reflation + hikes + deficit/term-premium fears crush prices to lows.",
      period: { central: 7, low: 4, high: 10 },
      turns: [
        { t: "2007-06", k: "trough", v: 5.26, e: "10Y ~5.25% pre-GFC — bond prices at a cycle low" },
        { t: "2008-12", k: "peak",   v: 2.08, e: "GFC flight-to-quality; 10Y ~2.1%, QE1 — bond-price spike" },
        { t: "2010-04", k: "trough", v: 3.99, e: "Post-GFC reflation; 10Y back near 4%" },
        { t: "2012-07", k: "peak",   v: 1.43, e: "Euro-crisis + Operation Twist; 10Y record ~1.43%" },
        { t: "2013-12", k: "trough", v: 3.04, e: "Taper tantrum; 10Y ~3.0%, TLT ~$102" },
        { t: "2016-07", k: "peak",   v: 1.36, e: "Brexit; 10Y all-time-low ~1.36%" },
        { t: "2018-11", k: "trough", v: 3.24, e: "Fed hiking + QT; 10Y ~3.24%" },
        { t: "2020-03", k: "peak",   v: 0.32, e: "COVID; 10Y 0.32%, TLT ATH ~$171 — secular bond-price peak" },
        { t: "2023-10", k: "trough", v: 5.0,  e: "Treasury tantrum; 10Y 5.0%, TLT ~$83" },
        { t: "2024-09", k: "peak",   v: 3.62, e: "First Fed cut; 10Y ~3.6%, TLT ~$100" },
        { t: "2026-05", k: "trough", v: 5.0,  e: "Iran-war oil shock; 30Y 5.20% (19-yr high), TLT ~$83" }
      ],
      now: {
        phase: "Recovery", phaseLabel: "Bouncing off the May-2026 yield-spike low",
        pos: 30, lastTrough: "2026-05", lastPeak: "2024-09", confidence: "medium",
        read:
          "TLT ~$87 (off the ~$83 May low), 10Y ~4.41% / 30Y ~4.85% after May's 5.20% spike (a 19-yr " +
          "high). Bonds are recovering as oil eases, but a hawkish Fed (3.5–3.75%, hike-biased) and " +
          "4.2% CPI keep the oscillator in the cheap half."
      },
      proj: {
        nextTurn: "peak", central: "2027-05", low: "2026-11", high: "2028-05", tilt: "mixed",
        drivers: ["oil/energy de-escalation cooling the inflation shock", "30–40% recession odds that would force fast cuts and a bond-price surge", "counterweight: hawkish Fed, ~9% deficit, sticky term premium"],
        falsifier:
          "A renewed energy shock or a failed long-bond auction pushing 30Y back above 5.2% / 10Y " +
          "above 4.9% (TLT below ~$83) voids the recovery and confirms the price downtrend intact."
      },
      regimeNote: "Stagflation-tilted: long Treasurys are simultaneously an inflation victim and a recession hedge — duration is cheap, but the catalyst for a durable price peak (decisive disinflation or a growth scare) hasn't confirmed."
    },

    /* ----------------------------------------------------------- US DOLLAR --- */
    {
      id: "dollar", name: "US Dollar Index (DXY)", short: "US Dollar", group: "FX & Global Liquidity",
      accent: "#2fa37a",
      proxy: "DXY index · UUP",
      archetype:
        "Rate-differential + safe-haven flows drive a multi-year dollar bull until US monetary " +
        "advantage and global stress peak together, then easing/over-valuation and capital rotation " +
        "abroad force a prolonged unwind to a new low.",
      period: { central: 15, low: 6, high: 17 },
      turns: [
        { t: "1985-02", k: "peak",   v: 164.7, e: "Volcker real-rate peak → 1985 Plaza Accord" },
        { t: "1992-09", k: "trough", v: 78.4,  e: "ERM crisis trough; post-Plaza devaluation" },
        { t: "2001-07", k: "peak",   v: 121,   e: "Dot-com strong-dollar peak" },
        { t: "2008-03", k: "trough", v: 70.7,  e: "All-time DXY low (70.70) at the commodity-boom peak" },
        { t: "2010-06", k: "peak",   v: 88.7,  e: "Post-GFC bounce / euro-crisis safe-haven high" },
        { t: "2011-04", k: "trough", v: 72.7,  e: "QE2 + Eurozone-crisis secondary low" },
        { t: "2017-01", k: "peak",   v: 103.8, e: "Trump-reflation interim high" },
        { t: "2021-01", k: "trough", v: 89.4,  e: "Post-COVID stimulus low" },
        { t: "2022-09", k: "peak",   v: 114.78, e: "20-yr peak on the fastest Fed tightening since the 1980s" },
        { t: "2025-09", k: "trough", v: 96.2,  e: "4-yr low (worst H1 since 1973) on tariff/debasement fears" }
      ],
      now: {
        phase: "Recovery", phaseLabel: "Cyclical rebound off the Sep-2025 low",
        pos: 38, lastTrough: "2025-09", lastPeak: "2022-09", confidence: "medium",
        read:
          "DXY ~101.4 (highest since Mar-2025), up ~5 pts off the ~96.2 four-year low, on a hawkish " +
          "June dot-plot (median 2026 funds lifted to 3.8%) and the Iran ceasefire — but still ~13% " +
          "below the 2022 peak, so a counter-trend rally within a structurally lower regime."
      },
      proj: {
        nextTurn: "peak", central: "2026-11", low: "2026-09", high: "2027-05", tilt: "tailwind",
        drivers: ["hawkish Fed (9/18 see 2026 hikes; median 3.8%)", "oil-shock 4.2% CPI keeps US yields elevated", "counterweight: reserve-diversification / de-dollarization caps the upside"],
        falsifier:
          "A weekly close back below ~97 (toward the ~96.2 low), or a dovish July-FOMC pivot plus " +
          "sub-4% CPI, confirms the secular downtrend resuming toward a fresh trough."
      },
      regimeNote: "~15-yr framing (lows ~1980→1992→2008): the secular bull peaked Sep-2022 at 114.78; the 2025 plunge to ~96 suggests the multi-year down-leg is underway, with the ~101 bounce a hawkish-Fed counter-rally. (unverified) periodicity is a heuristic — recent legs ran 6–8yr."
    },

    /* ---------------------------------------------------------- NATURAL GAS -- */
    {
      id: "natural-gas", name: "Natural Gas (Henry Hub / TTF)", short: "Nat Gas", group: "Energy",
      accent: "#8ad0e0",
      proxy: "Henry Hub front-month · UNG · TTF",
      archetype:
        "Weather/storage whipsaw: a cold-snap or supply shock drains storage and spikes price, " +
        "luring record shale + LNG-fed drilling, which refills storage and crushes price back to " +
        "sub-cost lows that choke supply and reset the loop.",
      period: { central: 1, low: 0.6, high: 4.5 },
      turns: [
        { t: "2014-01", k: "peak",   v: 4.71, e: "2013–14 polar vortex drains storage" },
        { t: "2016-03", k: "trough", v: 1.73, e: "Shale glut + warm El Niño; 17-yr low" },
        { t: "2018-11", k: "peak",   v: 4.84, e: "Cold blast hits low storage" },
        { t: "2020-06", k: "trough", v: 1.63, e: "COVID demand destruction (~$1.38, lowest since 1998)" },
        { t: "2021-10", k: "peak",   v: 5.51, e: "Pre-energy-crisis supply scramble" },
        { t: "2022-08", k: "peak",   v: 8.81, e: "Russia–Ukraine crisis; intraday $9.85" },
        { t: "2024-03", k: "trough", v: 1.49, e: "Mild winter + record glut; 25-yr real low, Waha negative" },
        { t: "2026-01", k: "peak",   v: 7.46, e: "Polar vortex / Winter Storm Fern; record 2,020 Bcf draw" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-peak slide into the summer-shoulder trough",
        pos: 32, lastTrough: "2024-03", lastPeak: "2026-01", confidence: "high",
        read:
          "Henry Hub front-month ~$3.2/MMBtu, down ~57% from the Jan polar-vortex peak (~$7.46) as " +
          "record production and storage ~7% above the 5-yr average rebuild fast — the classic " +
          "shoulder-season discount. TTF ~€42/MWh mirrors a well-supplied global market."
      },
      proj: {
        nextTurn: "trough", central: "2026-09", low: "2026-08", high: "2026-11", tilt: "mixed",
        drivers: ["bearish near-term: record US production, storage ~7% above the 5-yr average", "bullish structural: LNG feedgas demand +9% 2026 / +11% 2027 (Plaquemines/Golden Pass)", "record summer power burn from coal retirements + data-center load"],
        falsifier:
          "A sustained break above ~$4.00 front-month during the July–Sep injection season (with " +
          "storage staying above the 5-yr average) invalidates the summer-trough thesis."
      },
      regimeNote: "Loosely coupled to the rate/dollar cycle — driven by the ~1-yr weather/storage seasonal over a multi-year shale/LNG super-cycle. A textbook post-winter-peak downturn meeting record supply, with a structurally tightening 2027 demand backdrop."
    },

    /* ----------------------------------------------------------- IRON ORE --- */
    {
      id: "iron-ore", name: "Iron Ore / Steel (China Property)", short: "Iron Ore", group: "Industrial Metals",
      accent: "#c0533e",
      proxy: "62% Fe (SGX/Platts) · SHFE rebar · SLX",
      archetype:
        "China property/infrastructure credit pulse drives mill steel output → seaborne iron-ore " +
        "demand; cheap-debt building booms overshoot, then property deleveraging + new low-cost mine " +
        "supply (Vale/Rio/BHP/FMG + Simandou) crush prices into a glut bust.",
      period: { central: 4, low: 3, high: 7 },
      turns: [
        { t: "2011-02", k: "peak",   v: 187,   e: "China stimulus + restock boom" },
        { t: "2015-12", k: "trough", v: 38.5,  e: "Decade-low capitulation; supply glut (ATL $38.54)" },
        { t: "2016-12", k: "peak",   v: 80,    e: "China shantytown PSL + supply-side reform rally" },
        { t: "2018-12", k: "trough", v: 68,    e: "Trade-war growth scare" },
        { t: "2019-07", k: "peak",   v: 120,   e: "Brumadinho (Vale) supply shock" },
        { t: "2020-04", k: "trough", v: 80,    e: "COVID demand low before the China restart" },
        { t: "2021-07", k: "peak",   v: 219.8, e: "Euphoric ATH $219.77; post-COVID property/infra blow-off" },
        { t: "2022-11", k: "trough", v: 81,    e: "Zero-COVID + Evergrande collapse" },
        { t: "2023-03", k: "peak",   v: 130,   e: "China reopening rally" },
        { t: "2024-09", k: "trough", v: 89,    e: "Property-led demand slump; starts −20% YoY" },
        { t: "2025-09", k: "trough", v: 93.65, e: "Lowest since Nov-2022 before Sept-2025 stimulus" },
        { t: "2025-11", k: "peak",   v: 110,   e: "Stimulus-hope rebound (low-amplitude)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Structural property downturn; stimulus bounce fading",
        pos: 34, lastTrough: "2025-09", lastPeak: "2025-11", confidence: "high",
        read:
          "Iron ore ~$100/t (−8% MoM) as the late-2025 stimulus rebound fades; SHFE rebar at " +
          "two-month lows and China crude-steel output −2.7% YoY in May. A structural multi-year " +
          "property deleveraging (starts still −20%+) with rising seaborne supply (Simandou ramping), " +
          "not a clean cyclical trough."
      },
      proj: {
        nextTurn: "trough", central: "2026-11", low: "2026-09", high: "2027-05", tilt: "headwind",
        drivers: ["China property in structural deleveraging (starts −20%+ YoY)", "rising seaborne supply + Simandou into falling demand = widening glut", "only swing factor is Beijing stimulus (Sept-2025 = a low-amplitude bounce)"],
        falsifier:
          "A large credible China property/fiscal stimulus lifting 62% Fe back above ~$120/t with " +
          "rebar and starts positive YoY for two months would signal an early Recovery."
      },
      regimeNote: "Largely decoupled from the US rate cycle — hostage to Beijing's willingness to re-stimulate construction. Strong dollar + global recession odds add a mild headwind atop the dominant China-property structural bust."
    },

    /* ------------------------------------------------------------- SILVER --- */
    {
      id: "silver", name: "Silver (Monetary + Industrial)", short: "Silver", group: "Precious Metals",
      accent: "#c3cdd8",
      proxy: "Spot silver (XAG) · SLV · gold/silver ratio",
      archetype:
        "Dual monetary+industrial metal: easy money + safe-haven flight + a chronic supply deficit " +
        "ignites a leveraged momentum melt-up, which margin hikes and a hawkish-Fed/strong-dollar " +
        "real-yield shock then violently unwind.",
      period: { central: 8, low: 5, high: 11 },
      turns: [
        { t: "2011-04", k: "peak",   v: 49.51, e: "Post-GFC reflation squeeze; CME margin hikes pop it" },
        { t: "2015-12", k: "trough", v: 13.65, e: "Fed liftoff + strong dollar bottom" },
        { t: "2016-08", k: "peak",   v: 20.71, e: "Brexit safe-haven countertrend high" },
        { t: "2018-11", k: "trough", v: 13.97, e: "Fed hiking + strong dollar" },
        { t: "2020-03", k: "trough", v: 11.94, e: "COVID liquidity crash — major low" },
        { t: "2021-02", k: "peak",   v: 30.1,  e: "Reflation + Reddit 'silver squeeze'" },
        { t: "2022-09", k: "trough", v: 17.81, e: "Fed hikes + DXY 114 re-test low" },
        { t: "2026-01", k: "peak",   v: 121.67, e: "Parabolic monetary+industrial mania; deficit + solar/AI (ATH)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-parabolic correction / unwind",
        pos: 32, lastTrough: "2022-09", lastPeak: "2026-01", confidence: "medium",
        read:
          "Silver ~$56/oz (−24% MoM, ~54% below the Jan ATH of $121.67) as a hawkish Fed, DXY ~101 " +
          "and rising real yields hammer the metal. The gold/silver ratio ~67 and a 6th straight " +
          "supply deficit persist — a sharp downturn within a still-elevated secular bull."
      },
      proj: {
        nextTurn: "trough", central: "2026-09", low: "2026-08", high: "2026-12", tilt: "headwind",
        drivers: ["hawkish Fed (~68% Sept-hike odds), rising real yields cap a non-yielding metal", "strong dollar (DXY ~101)", "structural floor: a 6th consecutive supply deficit + recession odds could pull forward a dovish pivot"],
        falsifier:
          "A decisive close back above ~$72/oz, or a Fed pivot to cuts, would argue the trough is already in."
      },
      regimeNote: "Textbook headwind for silver's monetary leg: a hawkish, hike-biased Fed, DXY ~101 and rising real yields are unwinding the January parabola; a recession-driven dovish pivot is the variable that flips it. (unverified) exact trough inferred."
    },

    /* --------------------------------------------------------- EM EQUITIES -- */
    {
      id: "em-equities", name: "Emerging-Market Equities", short: "EM Equities", group: "Global Equities",
      accent: "#d24fb0",
      proxy: "MSCI EM · EEM",
      archetype:
        "Cheap-capital + weak-dollar inflows chase EM growth/commodity/tech earnings into euphoria; " +
        "a Fed/dollar/oil shock reverses the flow, currencies and equities sell off together, and the " +
        "cycle troughs when the dollar peaks and valuations capitulate.",
      period: { central: 6.5, low: 4, high: 9 },
      turns: [
        { t: "2007-10", k: "peak",   v: 1338, e: "Pre-GFC EM boom top" },
        { t: "2008-10", k: "trough", v: 567,  e: "GFC crash (ultimate bottom Mar-2009 ~454)" },
        { t: "2011-04", k: "peak",   v: 1208, e: "China-stimulus / BRIC high" },
        { t: "2016-01", k: "trough", v: 692,  e: "China devaluation / commodity-crash bottom" },
        { t: "2018-01", k: "peak",   v: 1278, e: "Synchronized-growth top before the trade war" },
        { t: "2020-03", k: "trough", v: 758,  e: "COVID crash low" },
        { t: "2021-02", k: "peak",   v: 1445, e: "Post-COVID reflation ATH" },
        { t: "2022-10", k: "trough", v: 848,  e: "DXY 114.8 rate-shock bottom; China zero-COVID nadir" },
        { t: "2026-06", k: "peak",   v: 1809, e: "AI-chip supercycle + weak-dollar euphoria (Taiwan/Korea-led)" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Peak rolling over — euphoria into a dollar/oil shock",
        pos: 82, lastTrough: "2022-10", lastPeak: "2026-06", confidence: "medium",
        read:
          "MSCI EM made a fresh high ~1,809 (Jun-22) on an AI-chip rally led by Taiwan/Korea, then " +
          "rolled to ~1,698 (−3.3%) as DXY pushed to ~101, oil-driven 4.2% CPI hardened a hawkish " +
          "Fed, and foreign outflows hit. Still only ~14× forward (a ~36–40% discount to the US) — " +
          "the topping edge of an expensive-but-cheaply-valued cycle."
      },
      proj: {
        nextTurn: "trough", central: "2027-03", low: "2026-12", high: "2027-09", tilt: "headwind",
        drivers: ["strong/strengthening dollar (DXY ~101) on a hawkish, oil-CPI-anchored Fed", "oil supply shock taxing energy-importing Asia", "stretched AI-chip concentration (Taiwan + Korea ~52% of the index)"],
        falsifier:
          "A clean break back above the ~1,809 high with the dollar rolling below ~99 and oil easing " +
          "would confirm the expansion is still intact rather than topping."
      },
      regimeNote: "Structurally hostile regime for EM: hawkish Fed, DXY ~101, oil-shock 4.2% CPI, 30–40% recession odds — the classic strong-dollar/high-rate combo that marks EM tops. The cushion is a ~36–40% valuation discount; the risk is Taiwan+Korea concentration tying EM to the chip cycle."
    },

    /* -------------------------------------------------------------- JAPAN --- */
    {
      id: "japan", name: "Japan / Nikkei Secular Cycle", short: "Japan", group: "Global Equities",
      accent: "#cc3d5f",
      proxy: "Nikkei 225 / TOPIX · EWJ · DXJ",
      archetype:
        "Weak-yen + reflation + corporate-governance reform pulls global capital into Japan Inc.; " +
        "BOJ normalization and yen strength eventually unwind the carry-funded leverage and reverse it.",
      period: { central: 18, low: 7, high: 35 },
      turns: [
        { t: "1989-12", k: "peak",   v: 38915, e: "Asset-bubble top (held for 34 yrs)" },
        { t: "2003-04", k: "trough", v: 7831,  e: "Post-bubble nadir, −80% from peak" },
        { t: "2007-07", k: "peak",   v: 18261, e: "Pre-GFC cyclical high on the global credit boom" },
        { t: "2009-03", k: "trough", v: 7055,  e: "GFC capitulation; 26-yr low — secular bottom" },
        { t: "2012-11", k: "trough", v: 9400,  e: "Pre-Abenomics inflection low" },
        { t: "2018-10", k: "peak",   v: 24270, e: "Abenomics-era cyclical high" },
        { t: "2020-03", k: "trough", v: 16553, e: "COVID crash low" },
        { t: "2021-09", k: "peak",   v: 30670, e: "Post-COVID high (first >30k since 1991)" },
        { t: "2022-03", k: "trough", v: 24682, e: "Fed-tightening / Ukraine drawdown" },
        { t: "2024-02", k: "peak",   v: 39098, e: "Reclaims the 1989 record — regime change" },
        { t: "2024-08", k: "trough", v: 31458, e: "Yen carry-trade unwind (worst day since 1987)" },
        { t: "2025-04", k: "trough", v: 31136, e: "Trump 24% tariff-shock low" },
        { t: "2026-06", k: "peak",   v: 72831, e: "AI-infra + weak-yen + governance euphoria (record >70k)" }
      ],
      now: {
        phase: "Peak", phaseLabel: "Late-cycle euphoria, momentum just cracked",
        pos: 90, lastTrough: "2025-04", lastPeak: "2026-06", confidence: "high",
        read:
          "The Nikkei printed a record 72,831 (Jun-22, first >70k), then took a 3.55% chip-led hit and " +
          "sat ~71,270. A weak yen (~¥162) inflates exporter earnings while ~$100B of foreign inflows " +
          "chase AI-infra and governance reform — classic late-cycle euphoria, but the BOJ is hiking " +
          "into it (1% in June)."
      },
      proj: {
        nextTurn: "trough", central: "2026-11", low: "2026-08", high: "2027-05", tilt: "headwind",
        drivers: ["BOJ normalizing (1% in June, highest since 1995) — a steady carry-trade headwind", "yen ~¥162 extremely stretched; a snap stronger deflates exporters (cf. Aug-2024 −12.4% day)", "valuation/positioning extended after three up years and the >70k milestone"],
        falsifier:
          "A sustained close above ~73,000 on broadening breadth with the yen holding ¥160–165 would " +
          "extend the expansion leg into 2027."
      },
      regimeNote: "Two-sided: weak yen + governance reform + AI-capex powered the Nikkei past 70k, but the BOJ is the lone hawk-by-necessity hiking into a fragile global risk regime — and Japan's carry-funded, FX-sensitive complex is exactly what unwinds violently when the yen snaps stronger."
    },

    /* --------------------------------------------------------------- PGMs --- */
    {
      id: "pgms", name: "Platinum-Group Metals", short: "PGMs", group: "Precious Metals",
      accent: "#6fa6a8",
      proxy: "Platinum & palladium (XPT/XPD) · PPLT · Pt/gold ratio",
      archetype:
        "Thin-supply autocatalyst/jewellery metal: structural mine deficits + a supply-shock or " +
        "investment mania spark a parabolic squeeze, then demand destruction (substitution, EV " +
        "displacement, recycling) and speculative unwind collapse the price.",
      period: { central: 7, low: 4, high: 11 },
      turns: [
        { t: "2008-03", k: "peak",   v: 2273, e: "Platinum record ~$2,273 on SA power-crisis cuts" },
        { t: "2008-10", k: "trough", v: 763,  e: "GFC demand collapse −67%" },
        { t: "2011-08", k: "peak",   v: 1918, e: "Post-GFC reflation; last cyclical high above gold" },
        { t: "2016-01", k: "trough", v: 811,  e: "China slowdown + dieselgate fears" },
        { t: "2018-01", k: "peak",   v: 1015, e: "Brief reflation bounce; diesel erosion caps it" },
        { t: "2020-03", k: "trough", v: 562,  e: "COVID crash low" },
        { t: "2021-02", k: "peak",   v: 1310, e: "Reflation / green-hydrogen narrative" },
        { t: "2022-03", k: "peak",   v: 1166, e: "Russia–Ukraine PGM supply panic (palladium ATH $3,440)" },
        { t: "2024-08", k: "trough", v: 900,  e: "EV substitution + thrifting bottom the PGM bear" },
        { t: "2026-01", k: "peak",   v: 2923, e: "Platinum ATH $2,923; 4th-straight deficit + squeeze (+43%)" }
      ],
      now: {
        phase: "Downturn", phaseLabel: "Post-mania correction off the Jan-2026 ATH",
        pos: 42, lastTrough: "2024-08", lastPeak: "2026-01", confidence: "medium",
        read:
          "Platinum ~$1,580/oz (−18% MoM, ~46% below the Jan ATH of $2,923) yet still +17% YoY and far " +
          "above the 2024 ~$900 base; the gold/platinum ratio ~2.6× is historically cheap. The " +
          "parabolic investment squeeze has deflated, but a 4th straight structural deficit leaves it " +
          "elevated, not capitulated."
      },
      proj: {
        nextTurn: "trough", central: "2026-11", low: "2026-09", high: "2027-06", tilt: "headwind",
        drivers: ["hawkish Fed + strong dollar (~101 DXY) pressure dollar-priced metals", "30–40% recession odds threaten autocatalyst/jewellery demand", "offsetting floor: a 4th-consecutive deficit + depleted above-ground stocks support a higher trough"],
        falsifier:
          "Platinum reclaiming and holding above ~$1,900/oz (Pt/gold below ~2.2×) signals the " +
          "deficit-driven uptrend resumed; a break below ~$1,300 marks a deeper bust."
      },
      regimeNote: "Net headwind: hawkish Fed, strong dollar and oil-shock CPI lift real yields (negative for non-yielding metals), while recession odds threaten cyclical auto/jewellery demand. The counterweight — a 4th straight deficit + depleted stocks + extreme cheapness vs gold — should make this downturn shallower than 2008 or 2014–16."
    }
  ];
})();
