# Cross-Border Flow Regimes — Field Guide

Distilled from a 4-lane web-research fan-out (2026-07-13), adjudicated by Fable. This is the
understanding-before-backtest artifact for the CBF program
(`research/CROSS_BORDER_FLOW_REGIMES_MASTERPLAN_BY_FABLE.md`). Every panel stance, threshold,
and copy line in CBF derives from here. Claims carry named sources; where evidence is weak we
say so.

---

## §1 — How cross-border flows are measured (and why we infer from prices)

**The accounting spine.** BoP identity: Current Account + Capital/Financial Account + Official
Reserves = 0. A CA deficit means foreigners are accumulating claims on you — fragility appears
when the financing is *reversible* (portfolio/short-term bank debt rather than FDI), in *foreign
currency* (original sin: depreciation blows up the real debt stock — Eichengreen-Hausmann-Panizza),
against *thin reserves* (Guidotti-Greenspan: reserves ≥ short-term external debt), through a
*fragile banking system* (short-term inflows intermediated into long loans — Calvo 1998).

**Official data are too slow for a desk.** TIC: monthly, ~6–7wk lag, misses custodial re-routing
and derivatives. IMF BoP: quarterly, ~90d lag — ground truth for backtests only. EPFR: daily but
paid, and covers only funds (~$11bn/q avg EM flows vs $68–71bn true BoP flows — Koepke-Paetzold,
IMF WP/2020/171); it is a mutual-fund *sentiment* proxy. IIF tracker: monthly, paid. BIS banking
stats: quarterly, ~6mo lag.

**The practitioner proxy triangle (what CBF implements).** Daily, free, directional:
1. **Relative equity** — country/bloc equity return (USD terms) minus benchmark beta × benchmark.
2. **FX move** — country FX vs an EM-basket residual (separates country pressure from broad-dollar).
3. **Spread velocity** — local/EM OAS change minus EM aggregate (where collected).
When all three deteriorate *disproportionately vs peers*, that residual is the best free daily
signature of country-specific outflow. When everything falls together, the global push factor
dominates (ECB WP 2538/1364; Bruno-Shin NBER 19038: VIX + US policy are the dominant push factors).

**Confirmation layers where data exists:** country-ETF shares-outstanding flow (we have SO-delta
proxies for US broad/sector ETFs only — country-ETF SO is a future data wish); ETF
premium/discount; ADR/AH premium (we have AH premium, ~5wk deep); onshore-offshore basis
(CNH basis exists; peg management makes it illustrative-tier).

**EMP indices.** True exchange-market pressure = FX depreciation + reserve drain + rate defense,
volatility-weighted (Girton-Roper 1977; Eichengreen-Rose-Wyplosz 1996; Goldberg-Krogstrup NY Fed
SR834 in depreciation-equivalent units). Reserves/intervention are not observable free+daily ⇒
CBF ships a **partial EMP** (FX leg + equity residual + FX realized-vol change) and discloses the
missing leg on-surface. NY Fed SR1051: EMP risk-sensitivity is amplified ~1.9pp by high NBFI
leverage in the borrowing country — fragility context, not a daily input.

**Forbes-Warnock (JIE 2012) episode taxonomy** — the canonical flow-episode language:
*surge/stop* (foreigners driving gross inflows up/down) vs *flight/retrenchment* (domestic
residents moving out/home). Definitions are quarterly (±1σ vs 5y rolling mean, ≥2 quarters).
Global risk (VIX) is the dominant driver of stops; capital controls barely help. Our daily read
approximates the same object from prices; the episode names are reserved for the field guide —
surfaces use plain words.

**Known blind spots (printed, not hidden):** FX-hedged flows leave no FX trace; SWF/central-bank
OTC flows are invisible to every proxy; managed pegs truncate the FX leg (all CNH-side reads stay
illustrative — forex_regime already flags this); a local earnings/news shock can mimic outflow in
the equity residual for days.

## §2 — The regime taxonomy (the dollar smile, operationalized)

**Dollar smile** (Jen-Yilmaz, Morgan Stanley 2001): USD strengthens at both extremes — global
crisis (left) and US exceptionalism (right) — and weakens in synchronized global growth (center).
Reproduced in 2022; the 2025 "smirk" reassessment (weakened crisis leg via hedging costs, Asian
repatriation, reserve diversification 70%→~58% since 2000) is practitioner commentary
(Eurizon SLJ, GSAM) — tail-watch, not a regime.

| Regime | Observable signature | What performs (documented) | Episodes |
|---|---|---|---|
| **Goldilocks / synchronized** (smile center) | US & RoW equities both up, neither dominant; USD flat/soft; VIX subdued; commodities firm | EM ~29%/yr 2002-07 (Invesco, practitioner-grade); EAFE/EM ≥ US; carry high-Sharpe; breadth broad | 2003–06, 2017 (all 45 OECD economies expanding; DXY −10%), 2020–21 |
| **US exceptionalism / outflow** (smile right) | US > RoW by wide margin; USD grinding up (drift, not spike); EM FX broadly soft; US real-rate differential widening | US growth/quality leads; EM equity+FX both lose (double pain in USD terms); carry squeezed; commodities mixed-weak | 2013 taper ($150B gross EM equity outflows, Fragile Five −10–20% — IMF SDN14/09), 2014–15 (DXY +25%), 2018, 2022–23 (DXY 114.78 peak) |
| **EM rotation / inflow** (center-left) | RoW > US; USD falling from a peak; EM FX firm; commodities inflecting up | EM strongly outperforms; local-currency debt attracts flows (BIS: 1σ USD fall ⇒ +0.29pp local-bond flows); EM-DM equity corr FALLS (<0.45 May-2025, 25y low — MSCI) | 2003–07, 2009–10, 2017, 2020–21, 2025 (MSCI EM +8.9% vs SPX +1.1% through May) |
| **Risk-off convergence** (smile far-left) | Everything down together; USD/JPY/CHF spike; VIX >30; credit gapping; correlations → 1 | Only havens work; carry catastrophic (Aug-2024: 65–75% of positions closed in days — BIS Bull.90); EM worst in USD terms | 2008 (USD +22% while SPX −44%), Mar-2020, brief 2022 episodes |

**Sub-shading inside risk-off** (Fed research, 6-of-8 major EM stress episodes were growth-shocks):
monetary shock = VIX↑ + HY↑ + US yields↑ (2013); growth shock = VIX↑ + HY↑ + US yields↓
(2008/2020). The smile decomposition (IRD-R10, already shipped) carries this read — CBF
cross-references it rather than re-deriving.

**Stagflation divergence note (2022):** USD strong + US equities down + commodity-exporter EM
outperforming importers — a within-regime split, not a fifth state; the bloc gauges express it.

**Correlation structure is regime-dependent, not stable:** USD-SPX correlation flips sign by
regime (negative in risk-off, can be positive under exceptionalism); EM equity-FX correlate
positively in almost every regime (double gain in rotation, double pain in exceptionalism).
Never quote a single "the" USD-equity correlation.

**Transition-watch observables (descriptive chips only — ADJ-4 forbids lead-lag scoring):**
DXY multi-year cycle turns (1985/2001/2022 peaks, ~7–10y spacing — Crescat, practitioner-grade);
US-vs-global PMI differential narrowing; real-rate differential compression; carry-to-risk
deterioration (BIS MXN/BRL-vs-JPY read); gold outperforming Treasuries in stress (pre-dollar-peak
pattern, weak evidence); EM-DM rolling correlation regime.

## §3 — Contagion channels and Fed swap lines (the flow-reversal case law)

**Channel taxonomy (fast → slow):**
1. **Funding / dollar shortage** — real-time; shows in FX-swap/CIP space before credit (BIS
   WP291 "US dollar shortage in global banking"); Rey (2013): one global financial cycle driven
   by US policy + VIX makes the trilemma a dilemma.
2. **Portfolio rebalancing / margin** — VaR-breach forced selling hits unrelated countries;
   informed selling read as fundamental news amplifies (Ahnert-Bertsch wake-up-call formalization).
3. **Common creditor / banking** — the dominant 1990s channel (Kaminsky-Reinhart 2000): a shared
   lender's losses in A cut credit to B/C/D regardless of fundamentals (Asia 1997 via Japanese
   banks: Thailand → Indonesia → Malaysia → Korea → Russia → Brazil).
4. **Wake-up call / informational** — reassessment of *similar-type* countries (CA deficit +
   dollar debt) even with zero direct linkage.
5. **Trade** — weeks-to-months; slowest.

**Forbes-Rigobon (JF 2002) measurement law:** crisis-window correlations are heteroskedasticity-
biased UP; after adjustment, most "contagion" is pre-existing interdependence. Alert implication:
a correlation spike during a vol spike is necessary-but-insufficient evidence — CBF's discriminator
never lets the correlation filter stand alone (CBF-R5).

**Who gets hit next (vulnerability ordering, strong evidence):** common-lender exposure >
short-term external debt / reserves (Guidotti-Greenspan breach) > CA deficit + low reserves >
USD-debt stock (original sin amplifier: FX −20% can add 20–40pp debt/GDP — Argentina 2001,
Turkey 2018) > pegged FX (attack target) > benchmark-membership redemption pressure.
IRD's slow vulnerability map (IMF WEO + BIS gaps) is exactly this screen — CBF links to it
rather than rebuilding.

**Fed swap lines — mechanics and case law:**
- Structure: two-leg FX swap at fixed spot; foreign CB bears its own FX risk, pays OIS+spread;
  on-lends dollars domestically. Standing C6 network (Fed, ECB, BoJ, BoE, SNB, BoC) unlimited
  since Oct-2013; temporary capped lines added in crises (2008: 14 CBs; Mar-2020: +9 CBs at
  $30–60B each). Most of EM has NO line — they get FIMA repo (standing since Jul-2021, ~180
  account holders, dollars against custodied USTs, IORB+25bp) — option value; 2020 peak usage
  was trivial (~$1.4B).
- Usage history: GFC peak **$583B** (Dec-2008); euro crisis ~$100B (2011); COVID **$449B**
  (May-2020); Mar-2023 just **$590.5M** — the announcement was the signal; stress was
  solvency-specific (Credit Suisse), not a dollar-funding freeze.
- Effectiveness (Bahaj-Reis, ReStud 2022 — the rigorous study): swap lines put a **ceiling on
  CIP deviations** (the funding cost cannot persistently exceed the line's cost), lower banks'
  realized dollar funding costs, and raise ex-ante dollar lending. They do **NOT** move CDS or
  long yields — liquidity tools, not solvency tools. Copy law: a drawing never "resolves" a
  crisis; it confirms and caps the funding leg.
- Selection is political-economic: 2008 lines tracked US bank exposure; 2020 lines also tracked
  military alliance (Aizenman-Ito-Pasricha NBER 28585). The hierarchy (C6 → temporary lines →
  FIMA → IMF) is the dollar system's pecking order (BU GDP Center 2021).

**Drawing-interpretation tiers (drives CBF panel copy; SWPT is weekly Wednesday level, lags
price stress by days-to-weeks — IRD-R5):**
| Tier | Signal | Plain-word read |
|---|---|---|
| 1 | C6 CB draws size | Dollar funding stress CONFIRMED in that zone; watch basis, that currency, offshore CP |
| 2 | Temporary-line EM CB draws | EM dollar squeeze real; capital-flow reversal underway there; screen similar-type countries |
| 3 | Coordination announcement, ~zero draws | Precautionary; if no draws in ~72h it was solvency-specific, not systemic funding |
| 4 | FIMA usage visible | Pressure OUTSIDE the swap network — a country with no backstop is under strain |
Stigma asymmetry: **non-zero drawings = confirmed stress; zero drawings ≠ absence of stress.**

## §4 — Desk playbooks (the "so what" layer)

**Per-regime institutional positioning (documented practice):**
- *US exceptionalism / outflow*: underweight EM (equity and especially local-currency debt —
  BIS: dollar strength dominates local-bond flows, and its grip has tightened since 2014);
  long USD; watch dollar-debt-heavy names (Bruno-Shin: 10% USD up ≈ 70–80bp EM credit tightening).
- *Goldilocks*: broad risk-on; carry fully expressed (long BRL/ZAR/MXN vs JPY/EUR funders,
  vol-targeted); commodity-exporter EM leads; the risk is regime exit via US re-divergence or
  vol shock.
- *Risk-off*: havens (USD, JPY, CHF, short Treasuries); carry unwinds are non-linear and
  self-reinforcing (Aug-2024: BoJ surprise → 65–75% of carry closed within days — BIS Bull.90);
  don't chase rebounds until vol settles.
- *EM rotation*: overseas + commodity exposure benefits; short-USD structural; the single
  biggest risk is a dollar reversal (watch DXY stabilization, carry-to-risk peaking).

**The EM blow-up warning ladder (desk practice, rung by rung):**
1. *Monitor* — DXY grinding up while Fed holds/hikes; carry returns flattening; positioning
   crowded; CA-deficit screen (>3–4% GDP — the Fragile-Five heuristic); IMF ARA reserve metric
   <100%.
2. *Reduce/hedge* — NDF/onshore spread widening (hedge-cost barometer); reserve drain >15–20%
   in 90d (Aizenman-Hutchison); partial-EMP multi-sigma; local-vs-hard-currency spread
   divergence (~150–200bp is an editorial threshold, not published research); 3m FX implied vol
   >2σ. *(NDF/reserve/implied-vol legs are data-walls for us — printed as nulls.)*
3. *De-risk/exit* — multi-currency breadth (>50% of EM FX down >2% in 30d = common-factor,
   not idiosyncratic); EM stress bleeding into US IG/HY or periphery CDS; cross-border dollar
   credit growth turning negative (BIS qt1409g: USD-claims share explained ~45% of taper-tantrum
   lending variation).
4. *Crisis* — Guidotti-Greenspan + import-cover both breached; IMF talks public; NDF persistently
   inverted; hard-currency CDS >500bp.

**Idio-vs-systemic three-filter test (the operationally critical discriminator):**
(1) *Breadth* — 1–3 currencies falling with the rest stable = idiosyncratic (Turkey 2018:
TRY −40%, BRL/ZAR/INR recovered, VIX/HY "modest and mixed"); >50% of EM FX falling = systemic
(2013 phase-1 "indiscriminate" — IMF SDN14/09; Mar-2020 universal).
(2) *Common-factor share* — first-PC / average-pairwise-correlation share of EM FX variance
>60–70% = systemic, <30% = idiosyncratic (synthesis of Fed IFDP methodology + factor practice;
no single published desk rule — flagged as such).
(3) *DM credit transmission* — Turkey 2018: none ⇒ fade; CNY 2015: US HY widened ⇒ global
de-risk; COVID 2020: immediate freeze ⇒ maximum de-risk.
Case classification: 2013 systemic→differentiated (fundamentals sorted phase-2 recovery);
2015 systemic; 2018 idiosyncratic; 2020 systemic.

**USD as risk thermostat (why the dollar anchors every CBF read):** Bruno-Shin balance-sheet
channel (dollar up ⇒ EM dollar-debt service up ⇒ bank VaR capacity down ⇒ global credit
tightens); BIS 2024 investor-VaR channel (dollar down ⇒ unhedged EM positions gain ⇒ risk
headroom ⇒ more inflows); Rey global financial cycle (US policy + VIX transmit everywhere;
floating rates don't insulate). A rising broad dollar IS tightening global liquidity.

**Plain-word states (retail-facing; these are the CBF glance-tier stances):**
| State | Label | Guidance line |
|---|---|---|
| Goldilocks | Broad global risk-on — supported | Global growth is steady and money is flowing to markets everywhere. Diversified risk is being rewarded. |
| Exceptionalism | Capital favors the US — overseas headwind | Money looks to be moving toward the US. Overseas and commodity-linked assets face a headwind; countries with big deficits are the ones to watch. |
| Rotation | Money rotating overseas — dollar soft | The dollar is weakening and foreign markets are leading. Overseas exposure tends to benefit; a dollar turn is the main risk. |
| Risk-off | Global de-risking — havens bid | Risk appetite has dropped everywhere at once. Havens are in demand; don't chase rebounds until volatility settles. |
| Mixed | No clear flow direction — watch | Signals disagree. Wait for the picture to clear rather than leaning on a weak read. |
| + discriminator | Isolated stress / Spreading / Broad and systemic | One country's problem — broader markets not infected / Watch breadth — pressure widening / Weakness is broad and reaching developed-market credit — de-risking has historically been right here. |

## §5 — Evidence-quality ledger

Strong (multiple institutional/peer-reviewed sources): dollar smile core; BIS dollar-flow
elasticities; Bruno-Shin channel; taper-tantrum mechanics; Kaminsky-Reinhart common-creditor;
Forbes-Rigobon bias; Bahaj-Reis swap-line CIP ceiling; Calvo sudden stops; original sin.
Moderate: wake-up-call channel; Forbes-Warnock daily proxying; carry-unwind non-linearity
(well documented for Aug-2024 specifically). Weak/practitioner-grade (used for framing only,
never thresholds): 7–10y dollar cycles; "smirk"/de-dollarization; 29%/yr EM goldilocks return;
150–200bp local-vs-hard divergence threshold; PCA >60% desk rule (methodological synthesis).

Primary sources: BIS qt2409d/qt2409a/Bull.90/WP695/WP291/qt1409g; IMF SDN14/09, WP/2020/171,
WP/2020/179; NY Fed SR834/SR1051; NBER 17351 (Forbes-Warnock), 21162 (Rey), 28585
(Aizenman-Ito-Pasricha), 31004 (Obstfeld-Zhou); ReStud 89(4) Bahaj-Reis; JF 57(5)
Forbes-Rigobon; JIE 51(1) Kaminsky-Reinhart; Fed FEDS Notes 2023 (taper +10y), FEDS 2025 (TIC);
ECB WP 2538/1364/3017/2658; full URL list preserved in the research fan-out transcripts
(2026-07-13, workflow cbf-census-fieldguide).
