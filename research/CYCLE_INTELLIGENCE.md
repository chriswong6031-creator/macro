# Cycle Intelligence — research & dataset provenance

**As of 2026-06-25.** Source-of-truth research behind the Cycle Intelligence
dashboard (`site/cycle.html`, data in `site/cycle_data.js`). Compiled from a
six-stream web-research pass (all mid-2026 levels web-verified; training cutoff is
Jan 2026). Each cycle is **falsifiable**: it states a probability-weighted next
turn, a date range, and the condition that proves the read wrong — in keeping with
the house doctrine of *confirmation over prediction*.

> **Modelling note.** The dashboard plots a normalised "cycle position" 0–100
> where, for **every** cycle, 100 = euphoric cyclical high (price top / tightest
> credit spreads / deepest market calm) and 0 = capitulation low (crash / spread
> blow-out / vol spike). Credit and volatility are stored in *risk-on* semantics
> (tights/calm = high). Each cycle's oscillator is a smooth (half-cosine) curve
> anchored to its **real dated turning points**, and the curve is pinned to pass
> through the research-grounded current position at TODAY. History is solid;
> projection is dashed with an uncertainty cone widened by the timing range and
> tilted by the regime. It is an **honest reconstruction** — "history first,
> forecast second" — not a claim of precision.

---

## The cross-cycle thesis (June 2026)

- **Master variable — the 2026 Iran war / Strait-of-Hormuz oil shock.** It spiked
  CPI to 4.2% (May), flipped the Fed from cutting to a **hiking bias** (on hold
  3.50–3.75%, ~68% Sept-hike odds), lifted **DXY to ~101** and the 10Y to ~4.4%. A
  **mid-June ceasefire** is unwinding the oil tail (WTI ~$70s from >$100). Regime:
  **late-cycle stagflation scare**. It cuts both ways — war tightens shipping/energy;
  peace loosens them — and decides whether the whole regime resolves to soft-landing
  or stagflation.
- **A cluster of late-cycle tops in a 2026–2028 window** — the dashboard's signature
  read: **Housing** (18-yr clock ~14 yrs up, starts at a 6-yr low), **US Business /
  ISM** (mature expansion, ISM cresting at 54), **Credit** (HY spreads ~263bp, near
  record-tight complacency), **Copper** (record ~$13.3k/t off the Jan ATH) and
  **Semis / Memory** (parabolic AI blow-off).
- **Fresh declines already underway:** **Bitcoin** (~$126k Oct-25 → ~$62k now, a
  ~50% down-leg) and **Gold** (parabola to ~$5,589 Jan → ~$4,000 now).
- **Early-cycle recoveries:** **Lithium** (off its Feb-25 bottom), **Uranium**
  (mid-bull higher-low base), **Shipping** (mid-recovery; container spiking on tariff
  frontloading), **Biotech** (IPO window reopening), **Agriculture** (4th year below
  breakeven, bottoming).
- **Volatility** normalised to ~16 post-ceasefire — complacency rebuilding; the next
  spike is the open question.

That spread — assets at **every** phase from bottoming to post-peak decline — is what
makes the overlay worth building.

## Macro regime (June 2026)

| Read | Value | Note |
|---|---|---|
| Fed policy | 3.50–3.75% | 4th hold; dot-plot erased 2026 cuts, ~68% Sept-hike odds |
| US 10Y | ~4.41% | +~18bp YoY |
| Dollar (DXY) | ~101.4 | strong-dollar regime, highest since early-2025 |
| Inflation | CPI 4.2% YoY (May), core 2.9% | hot, reaccelerating on the energy shock |
| Liquidity | neutral-to-tightening | QT ended Dec-2025; strong USD tightens global liquidity |
| Recession odds | ~30–40% (12-mo) | Goldman ~30%, EY ~40% severe |
| Risk appetite | cautious / fragile | steadied on the ceasefire, defensive not risk-on |

**Cycle conditioning:** restrictive policy + strong dollar + recession odds cap
demand-sensitive cyclicals; the cheap-liquidity tailwind that powered 2021-era booms
is absent — this regime rewards confirmed cash-flow and real-asset cyclicals over
speculative capex stories. Oil is the swing factor for all of them.

Sources: federalreserve.gov (FOMC 2026-06-17), cnbc.com (Fed decision / CPI May-2026),
tradingeconomics.com (10Y, DXY, VIX), aljazeera.com & cbsnews.com (Iran war / recession risk).

---

## The 15 cycles

For each: archetype · typical period · proxy · the major dated turning points used to
build the oscillator · the current read · the regime-conditioned projection + falsifier
· sources. Levels are approximate where tagged; the well-sourced turns (2018→2026) carry
the load.

### 1 · Semiconductors — *Technology* · ~3.8 yr (3–4.5)
Proxy: PHLX Semiconductor (SOX) / WSTS global sales. Capacity-led: a demand surprise
lifts utilisation → fabs over-invest on a ~2-yr lag → glut crushes ASPs until cuts
re-tighten. **Turns:** 2000-03 peak (SOX ~1362, dot-com) · 2001-10 trough · 2008-11
trough (GFC) · 2018-10 peak (memory super-cycle) · 2019-04 trough (glut + trade war) ·
2022-01 peak (SOX ~4068, COVID blow-off) · 2023-06 trough (genAI ignites). **Now (REVISED
2026-06-25):** **TOPPING NOW** (phase Peak, pos 91) — not "still rising into H1-2027". The
adversarial re-date (5-lens workflow) found the second derivative has turned: Broadcom's
Jun-3 refusal to raise its FY-AI outlook triggered a ~10% SOX wipeout, the Jun-22 record
(~14,655) came on narrowing breadth (NVDA/AMD/AVGO only, A/D diverging), and the YoY
sales-growth peak is base-locked for Q3-2026. **Projection:** PEAK **~Nov-2026** (Sep-26→
Mar-27), mixed (was H1-2027). **Falsifier:** a new SOX high on BROADENING breadth + Broadcom
raising its AI outlook + hyperscaler capex guides revised up flips it back to expansion.
Sources: semiconductors.org (SIA/WSTS), the Jun-2026 Broadcom/Micron/SK Hynix prints, en.macromicro.me/series/353/sox.

### 2 · Memory (DRAM/NAND) — *Technology* · ~3.5 yr (2.5–4.5)
Proxy: DRAM contract ASP, big-3 capex. The sharpest commodity sub-cycle in chips; leads
semis by 1–2 quarters. **Turns:** 2008-12 trough (Qimonda) · 2016-06 trough · 2018-10
peak (2017–18 super-cycle) · 2019-09 trough · 2021-12 peak (COVID) · 2023-06 trough.
**Now (REVISED 2026-06-25):** level still rising, **momentum peak already in** (phase
Expansion, pos 87). Q2 DRAM contracts still +58–63% and Micron's Jun-24 print ($41.5B,
+268% YoY, HBM booked into 2028) keep the ASP LEVEL climbing — but Q1-2026 contract growth
*halved* to ~60% (the rate-of-change peak). The level peaks a step behind semis. **Projection:**
PEAK **~Dec-2026** (Sep-26→Jun-27), tailwind (was H1-2027). **Falsifier:** Q3-2026 DRAM
contract prices print flat-to-down QoQ, or spot DDR5 stops climbing off record-low inventories.
Sources: trendforce.com, the Jun-2026 Micron / SK Hynix prints, useluminix.com, uncoveralpha.com.

### 3 · Housing / Real Estate — *Real assets* · ~18 yr (15–20)
Proxy: Case-Shiller / starts; the Hoyt–Harrison–Anderson land cycle (~14 up, ~4 down).
**Turns:** 1973-11 peak · 1989-09 peak (→S&L crisis) · 2006-07 peak (Case-Shiller ATH) ·
2012-02 trough (GFC bottom). **Now:** late-cycle plateau / topping — the clock sits ~14
years up (the peak window); Case-Shiller flat (+0.7% YoY, 10th straight month of negative
real returns), starts at a 6-yr low, >half of metros down YoY. **Projection:** PEAK ~2026
(2025H2→2028), then a ~4-yr downswing troughing ~2029–2032, headwind. **Falsifier:** fresh
accelerating Case-Shiller ATHs AND starts re-accelerating >~1.5M SAAR through 2027.
Sources: fred.stlouisfed.org/series/CSUSHPINSA, advisorperspectives.com, progress.org (18.6-yr cycle), cato.org.

### 4 · US Business Cycle — *Macro* · ~4.5 yr (3–6)
Proxy: ISM Manufacturing PMI / NBER. The ~3–5-yr Kitchin inventory cycle inside the NBER
expansion. **Turns:** 2018-08 peak (PMI 60.8) · 2020-04 trough (PMI 41, COVID) · 2021-03
peak (PMI 64.7) · 2023-06 trough (PMI 46) · 2026-05 peak (PMI 54, cresting). **Now:**
mature expansion ~74 months from the Apr-2020 trough (past the postwar average); ISM
upswing cresting. **Projection:** trough / recession ~2027 (late-26→2028), headwind.
**Falsifier:** ISM holding >54 through H2-2026 with firm new orders; unemployment ≤4.5%
and positive payrolls through 2027 (soft-landing extension).
Sources: nber.org, ism (prnewswire 2026-05), bls.gov.

### 5 · Crude Oil / Energy — *Energy* · ~7 yr (5–10)
Proxy: WTI/Brent + rig count. **Turns:** 1980-04 peak ($35) · 1986 trough ($10) · 2008-07
peak ($147) · 2009-02 trough ($34) · 2016-02 trough ($26) · 2020-04 trough (−$37, negative
WTI) · 2022-06 peak ($122, Ukraine) · 2025-12 trough ($57, OPEC+ unwind) · 2026-02 peak
($100+, Iran war / Hormuz). **Now:** post-war-spike normalisation — a US–Iran deal
collapsed the spike back to ~$70s; the underlying capex cycle is still early/oversupplied
(US oil rigs ~433). **Projection:** trough re-test ~H2-2026 (mid-26→mid-27); next genuine
capex peak 2028–2030; mixed. **Falsifier:** WTI below ~$55 for 2+ months (down-leg not
over) or a hold above ~$95 absent a fresh shock (up-cycle underway).
Sources: eia.gov, en.wikipedia.org/wiki/Price_of_oil, tradingeconomics.com, bakerhughes rig count, cnn.com (2026-06).

### 6 · Copper / Base Metals — *Metals* · ~8 yr (4–10)
Proxy: LME copper + exchange inventories. New mine supply lags ~7–10 yrs → multi-year
deficits and overshoots. **Turns:** 2008-07 peak ($8,940) · 2008-12 trough ($2,850) ·
2011-02 peak ($10,190) · 2016-01 trough ($4,330) · 2020-03 trough ($4,700) · 2022-03 peak
($10,845) · 2022-07 trough ($7,000) · 2026-01 peak ($14,527, ATH). **Now:** late structural
up-leg — eased to ~$13,300 on a firmer dollar (consolidation, not a top); ICSG flips to its
first deficit since 2009. **Projection:** cyclical pullback/trough ~2027 (2026H2→2028); next
secular high ~2029–2030; mixed. **Falsifier:** a hold below ~$9,000/t for 2+ months (deficit
floor broken) or a sustained break above ~$15,000/t (up-leg not mature).
Sources: lme.com, tradingeconomics.com, goldmansachs.com, spglobal.com, investingnews.com, macrotrends.net.

### 7 · Uranium — *Energy* · ~9–10 yr, irregular (8–17)
Proxy: spot U₃O₈ / SPUT flows. A thin, sentiment-driven market — long bear flats punctuated
by parabolic spikes. **Turns:** 2007-06 peak ($136, Cigar Lake) · 2016-11 trough ($18,
post-Fukushima glut) · 2024-01 peak ($106, nuclear renaissance) · 2025-03 trough ($64).
**Now:** mid-bull consolidation — spot ~$85/lb (a higher-low above the 2025 $63 trough)
while the term price sits at a 17-yr high (the precursor to spot follow-through). A coiled
spring. **Projection:** breakout / PEAK ~H1-2027 (late-26→2028), tailwind. **Falsifier:** a
sustained close below ~$63/lb breaks the higher-low base.
Sources: uraniumtracker.com, tradingeconomics.com, investingnews.com (uranium forecast/update), sprott.com.

### 8 · Gold / Precious Metals — *Metals* · ~17 yr secular (15–20)
Proxy: spot gold, real rates, CB buying. **Turns:** 1980-01 peak ($850) · 2001-04 trough
($255, Brown's Bottom) · 2011-09 peak ($1,921) · 2015-12 trough ($1,050) · 2026-01 peak
($5,589, parabolic ATH on tariff + Iran panic). **Now:** post-blow-off correction — ~$4,000
now (~28% off the Jan record, sharpest monthly fall since 2013) as the inflation read
repriced the Fed hawkishly; record central-bank buying is the structural floor — a violent
correction, not a 2011-style top. **Projection:** correction bottom ~H2-2026, new high 2027
(some see ~$6,000+); mixed. **Falsifier:** a sustained close below ~$3,300/oz breaks the
secular bull.
Sources: fortune.com (2026-06-25 price), tradingeconomics.com, cnbc.com, jpmorgan.com, usagold.com.

### 9 · Bitcoin / Crypto — *Digital* · ~4 yr (3.5–4.5)
Proxy: BTC/USD + the halving clock. **Turns:** 2013-11 peak ($1,150) · 2015-01 trough
($200) · 2017-12 peak ($19.8k) · 2018-12 trough ($3.2k) · 2021-11 peak ($69k) · 2022-11
trough ($15.5k, FTX) · 2025-10 peak ($125,836, spot-ETF ATH). **Now:** post-peak cyclical
bear — ~$62k (~50% off ATH), heavy long liquidations; the 4-yr clock held (peak ~18 months
post-halving); the drawdown is shallower than 2018/2022, consistent with the ETF-dampened
thesis. **Projection:** cycle trough ~Q4-2026 (Q3-26→Q2-27), price ~$40–60k; headwind.
**Falsifier:** a new ATH (>~$126k) before the trough; or a decisive break below the ~$64k
halving level toward sub-$40k (kills the "shallow bear" read).
Sources: fortune.com (2026-06-24 price), coingecko.com, fidelity.com, ccn.com, en.wikipedia.org (FTX).

### 10 · Credit Cycle — *Macro* · ~6.5 yr (5–8)
Proxy: ICE BofA US HY OAS (plotted risk-on: tights = high). **Turns:** 2007-06 peak (241bp
tights) · 2008-12 trough (2,182bp blow-out) · 2016-02 trough (887bp) · 2020-03 trough
(1,087bp, COVID) · 2021-12 peak (~305bp) · 2022-10 trough (~600bp, partial) · 2026-06 peak
(263bp). **Now:** late-cycle complacency — spreads near the 2007 record-tight pricing benign
credit, yet banks are tightening C&I standards and leveraged-loan defaults run ~7% (2× the
average): a late-cycle divergence with little cushion. **Projection:** spread blow-out
(trough) ~2027 (late-26→2029), headwind. **Falsifier:** HY OAS above ~500bp confirms the
turn; spreads ≤300bp with loan defaults falling toward ~3.4% through 2027 refute it.
Sources: fred.stlouisfed.org/series/BAMLH0A0HYM2, tradingeconomics.com, federalreserve.gov/data/sloos, moodys.com.

### 11 · Shipping / Freight — *Industrial* · ~3.5 yr (3–4)
Proxy: Baltic Dry + container WCI. **Turns:** 2008-05 peak (BDI ~11,793) · 2008-12 trough
(663) · 2016-02 trough (290, ATL) · 2021-10 peak (5,650, COVID container boom) · 2023-02
trough (530). **Now:** mid-cycle recovery, split sub-cycles — BDI ~2,634 (+58% YoY) cooling
off a spring high; container WCI surging to an 18-month high on cargo frontloaded ahead of
July US tariffs. **Projection:** container rollover (PEAK) ~Q4-2026; mixed. **Falsifier:**
WCI holding above ~$4,000/40ft through Q4-2026 (past the tariff window) implies structural
demand, not a pull-forward.
Sources: tradingeconomics.com/commodity/baltic, drewry.co.uk (WCI), handybulk.com.

### 12 · Lithium / Battery Materials — *Metals* · ~5 yr (4–6)
Proxy: battery-grade Li carbonate spot. **Turns:** 2020-06 trough (~$6.5k) · 2022-11 peak
(~$80k, EV bottleneck ATH) · 2025-02 trough (sub-$10k, 4-yr low). **Now:** early recovery /
first leg up — ~$22–25k/t, +159% YoY off the bottom on ESS/EV demand + supply discipline,
but −13% MoM as a possible CATL Jianxiawo restart caps the rally; real but fragile.
**Projection:** consolidation H2-2026, durable PEAK 2027+ (2026H2→2028); mixed.
**Falsifier:** a confirmed Jianxiawo restart **plus** spot back below ~$15,000/t (return to
oversupply).
Sources: tradingeconomics.com/commodity/lithium, metal.com, investingnews.com (lithium forecast), carboncredits.com.

### 13 · Agriculture / Grains — *Energy* (soft) · ~5.5 yr (4–7)
Proxy: GSCI Agriculture / corn-wheat-soy. **Turns:** 2008-06 peak (biofuel + oil $140) ·
2012-08 peak (US drought, corn ~$8) · 2016-08 trough · 2022-05 peak (Ukraine grain shock) ·
2025-09 trough (4th year below breakeven). **Now:** late-cycle bottoming — corn ~$4.07, soy
~$11.09 (4-mo low), wheat ~$5.86. Notably the 2026 Iran war hit the **cost** side (fertiliser
+30–40%) but **not** grain supply (the Mideast is a net food importer), so it has not ignited
a bull; wet US weather is capping prices. **Projection:** bull leg ~2027 (late-26→2028),
mixed — a drought is the classic ignition. **Falsifier:** corn holding above ~$5.50–6.00/bu
into tightening stocks-to-use.
Sources: tradingeconomics.com (CBOT corn/wheat/soy), usda framing, investing.com.

### 14 · Volatility Regime — *Macro* · irregular spikes (~1–3 yr)
Proxy: CBOE VIX (plotted risk-on: calm = high, a stress spike = low). **Turns (spikes/calms):**
2008-11 spike (~80, GFC) · 2017-06 calm (~10) · 2018-02 spike (~37, Volmageddon) · 2020-03
spike (~82, COVID) · 2024-08 spike (~65, yen carry unwind) · 2025-04 spike (~52, tariff crash)
· 2026-03 spike (~35, Iran war) · 2026-06 calm (~16, ceasefire). **Now:** normalising → calm,
complacency rebuilding; the March Iran spike was milder than 2024/2025. **Projection:** the
next spike >30 within ~6–18 months (late-26→2028), event-driven. **Falsifier:** a sustained
VIX >25–30 for more than a few sessions flips the regime to stress.
Sources: VIXCLS (FRED), tradingeconomics.com/commodity/vix.

### 15 · Biotech / IPO — *Digital* (risk-appetite) · ~6 yr (5–7)
Proxy: XBI + the IPO window. **Turns:** 2015-07 peak (~$90) · 2016-11 trough (~$48) · 2021-02
peak ($174, COVID mania ATH) · 2023-06 trough ($62, capitulation). **Now:** recovery / IPO
window reopening — XBI ~$154 (top of its 52-wk range, ~12% below the 2021 ATH); the window is
reopening but selective (record-size, late-stage deals; most 2026 debuts hold issue) — a
high-bar reopening, not a 2021-style mania. **Projection:** PEAK ~2027 (late-26→2028),
headwind (rate-sensitive). **Falsifier:** XBI below ~$120–125 with deteriorating IPO pricing
(window stalled); a clean break above ~$175 confirms the next leg.
Sources: XBI quote (2026-06-25), ipo issuance trackers, biopharma deal trackers.

---

## Expansion — 8 more cycles (researched 2026-06-25)

A second workflow proposed & researched eight additional, genuinely distinct cycles (a vet
pass kept 4 cleanly and flagged 4 for the fixes applied below: DXY turn-alternation, PGM
platinum `v`, and the bond price-vs-yield `v` convention — note the dashboard plots the
oscillator from `k`, not `v`, so those tooltip-only fields don't affect rendering).

### 16 · Long Bonds — *Rates & Sovereign* · ~7 yr (4–10)
Proxy: TLT / 10Y-30Y yield (oscillator = bond PRICE; low yield = high). **Turns:** 2007-06
trough · 2008-12 peak (10Y 2.1%, QE1) · 2012-07 peak (10Y 1.43%) · 2016-07 peak (10Y 1.36%) ·
2020-03 peak (10Y 0.32%, TLT ~$171 — secular price top) · 2023-10 trough (10Y 5.0%) · 2024-09
peak (TLT ~$100) · 2026-05 trough (30Y 5.20%, 19-yr high). **Now:** Recovery (pos 30) — TLT
~$87 off the May low, 10Y ~4.41%; recovering as oil eases but a hawkish Fed + 4.2% CPI keep it
cheap. **Projection:** PEAK ~2027-05 (2026-11→2028-05), mixed. **Falsifier:** 30Y back above
5.2% / TLT below ~$83. Sources: FRED DGS10/DGS30, cnbc.com (2026), etf.com.

### 17 · US Dollar (DXY) — *FX & Global Liquidity* · ~15 yr (6–17)
Proxy: DXY. **Turns:** 1985-02 peak (164.7→Plaza) · 2008-03 trough (70.70 ATL) · 2017-01 peak
(103.8) · 2022-09 peak (114.78, 20-yr high) · 2025-09 trough (96.2, worst H1 since 1973). **Now:**
Recovery (pos 38) — DXY ~101.4 (highest since Mar-2025) on a hawkish dot-plot + Iran ceasefire,
but ~13% below the 2022 peak: a counter-trend rally in a structurally lower regime. **Projection:**
PEAK ~2026-11 (2026-09→2027-05), tailwind. **Falsifier:** weekly close below ~97. Sources:
macrotrends.net, tradingeconomics.com, crescat.net (dollar cycles).

### 18 · Natural Gas — *Energy* · ~1 yr seasonal / multi-yr super-cycle
Proxy: Henry Hub / TTF. **Turns:** 2014-01 peak (polar vortex) · 2020-06 trough ($1.63) · 2022-08
peak ($8.81, Ukraine) · 2024-03 trough ($1.49, 25-yr real low) · 2026-01 peak ($7.46, Winter
Storm Fern, record 2,020 Bcf draw). **Now:** Downturn (pos 32) — HH front-month ~$3.2, −57% off
the Jan peak as record production + storage ~7% above the 5-yr average rebuild. **Projection:**
TROUGH ~2026-09 (summer shoulder), mixed; LNG demand +9% (2026)/+11% (2027) is the structural
bull. **Falsifier:** a hold above ~$4.00 in injection season. Sources: eia.gov (STEO/Henry Hub), tradingeconomics.com (TTF).

### 19 · Iron Ore / Steel — *Industrial Metals* · ~4 yr (3–7)
Proxy: 62% Fe / SHFE rebar / SLX. **Turns:** 2011-02 peak ($187) · 2015-12 trough ($38.5 ATL) ·
2021-07 peak ($219.8 ATH) · 2022-11 trough ($81, Evergrande) · 2024-09 trough ($89) · 2025-09
trough ($93.65) · 2025-11 peak ($110, stimulus bounce). **Now:** Downturn (pos 34) — ~$100/t
(−8% MoM) as the late-2025 stimulus rebound fades; China crude steel −2.7% YoY, starts −20%+, a
structural property deleveraging + Simandou supply. **Projection:** TROUGH ~2026-11, headwind.
**Falsifier:** credible China stimulus lifting 62% Fe above ~$120 with starts positive YoY.
Sources: tradingeconomics.com/commodity/iron-ore, sgx.com, discoveryalert (2026).

### 20 · Silver — *Precious Metals* · ~8 yr (5–11)
Proxy: spot silver / gold-silver ratio. **Turns:** 2011-04 peak ($49.5) · 2020-03 trough ($11.94,
COVID) · 2021-02 peak ($30, Reddit squeeze) · 2022-09 trough ($17.8) · 2026-01 peak ($121.67 ATH,
parabolic mania). **Now:** Downturn (pos 32) — ~$56/oz, ~54% below the Jan ATH as a hawkish Fed,
DXY ~101 and rising real yields unwind the parabola; a 6th straight supply deficit persists.
**Projection:** TROUGH ~2026-09, headwind. **Falsifier:** close back above ~$72 or a Fed pivot.
Sources: tradingeconomics.com/commodity/silver, silverinstitute.org, fortune.com (2026-06).

### 21 · EM Equities — *Global Equities* · ~6.5 yr (4–9)
Proxy: MSCI EM / EEM. **Turns:** 2007-10 peak (1338) · 2008-10 trough (567) · 2021-02 peak (1445,
post-COVID ATH) · 2022-10 trough (848, DXY 114.8 shock) · 2026-06 peak (1809, AI-chip + weak-dollar
euphoria, Taiwan/Korea-led). **Now:** Peak rolling over (pos 82) — fresh high ~1,809 (Jun-22) then
−3.3% to ~1,698 as DXY ~101 and the oil-CPI hawkish Fed bite; still ~14× fwd (~36–40% discount to
the US). **Projection:** TROUGH ~2027-03 (2026-12→2027-09), headwind. **Falsifier:** break back
above ~1,809 with DXY below ~99. Sources: msci.com, investing.com (MSCI EM), goldmansachs.com.

### 22 · Japan / Nikkei — *Global Equities* · ~18 yr secular (7–35)
Proxy: Nikkei 225 / TOPIX / EWJ. **Turns:** 1989-12 peak (38,915, held 34 yrs) · 2009-03 trough
(7,055 — secular bottom) · 2024-02 peak (39,098 — reclaims the record) · 2024-08 trough (carry
unwind, worst day since 1987) · 2025-04 trough (tariff shock) · 2026-06 peak (72,831, first >70k).
**Now:** Peak, momentum just cracked (pos 90) — record 72,831 (Jun-22) then a 3.55% chip-led hit;
weak yen (~¥162) + ~$100B foreign inflows, but the BOJ is hiking into it (1% in June).
**Projection:** TROUGH ~2026-11 (2026-08→2027-05), headwind. **Falsifier:** sustained close above
~73,000 with the yen holding ¥160–165. Sources: nippon.com, cnbc.com (BOJ 2026), tradingeconomics.com/japan.

### 23 · PGMs (Platinum/Palladium) — *Precious Metals* · ~7 yr (4–11)
Proxy: platinum & palladium / Pt-gold ratio. **Turns:** 2008-03 peak ($2,273 Pt) · 2020-03 trough
($562, COVID) · 2022-03 peak (palladium ATH $3,440, Russia panic) · 2024-08 trough ($900, EV
substitution) · 2026-01 peak ($2,923 Pt ATH, 4th-straight deficit + squeeze). **Now:** Downturn
(pos 42) — Pt ~$1,580 (~46% below the Jan ATH) yet still +17% YoY; the parabola deflated but a 4th
straight deficit + cheap Pt/gold ~2.6× leave it elevated. **Projection:** TROUGH ~2026-11, headwind.
**Falsifier:** Pt holding above ~$1,900 (Pt/gold below ~2.2×). Sources: tradingeconomics.com
(platinum/palladium), platinuminvestment.com (WPIC deficit), macrotrends.net.

> **Density note.** The board now carries **23 cycles**, grouped into 6 families (Technology ·
> Energy · Metals · Macro & Rates · Risk Assets · Real & Trade) with a **group filter** to declutter
> the overlay, plus **timeline zoom** (scroll/drag/presets) to inspect any window. The overlay's
> through-line: a **broad 2026–2028 topping cluster** (semis now, EM & Japan equities, credit,
> housing, copper) sitting *above* fresh declines (bitcoin, gold, silver, nat-gas, iron-ore, PGMs)
> and early recoveries (lithium, uranium, shipping, long-bonds, the dollar's counter-rally).

---

## Dataset provenance & how it maps to the build

- Every cycle above is one object in **`site/cycle_data.js`** (`window.CYCLES`):
  `turns[]` (dated peaks/troughs → the oscillator), `now` (June-2026 phase, position,
  read), `proj` (next turn, central + range, drivers, falsifier, regime `tilt`),
  `accent` (its distinct colour), `archetype`, `period`, `proxy`, `regimeNote`.
- The macro block above is `window.CYCLE_META.regime`.
- **Confidence is uneven and tagged in-line.** The 2018→2026 turns and all current
  levels are well-sourced; several pre-2010 levels (exact ASPs, intraday extremes) are
  secondary/approximate and load less of the model. Phase / "% through cycle" reads are
  analytical calls, not dated facts.
- **Updating:** edit `site/cycle_data.js` (new turning point, revised projection, a
  fired falsifier). The hero overlay, the scorecard sparklines and the per-asset deep
  pages all read the same object, so they can never disagree. Opus can refresh the
  `now`/`proj` blocks as developments land — that is expected and supported.
