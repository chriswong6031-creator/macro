# S&P 500 and Nasdaq Regime & Sector-Rotation Atlas, 2013–July 2026

> **Canonical deliverable.** Deep historical investigation, quantitative pattern audit, weekly-MACD test, and point-in-time cycle assessment as of **Sunday, July 12, 2026**. The latest tradable close in the study is **Friday, July 10, 2026**.

## Decision answer first

**A defensive rotation was attempted in June, but a defensive regime has not been confirmed.** The best current label is **inflation-constrained rotational bull market**: technology and semiconductors remain the dominant 3–6 month leaders, while healthcare, financials, and industrials have broadened underneath them. Staples and utilities have not established the synchronized relative leadership, and credit/volatility/index trend have not shown the stress that would justify calling the whole tape defensive. The mature bull and uneven labor backdrop can look late-cycle, but “late-cycle” is not treated here as a recession clock.

The 2013–2026 record also rejects the simplest version of the “U.S. just rotates from tech to defensives and back” hypothesis. That oscillation exists, but four separate forces repeatedly determine the winner:

1. **Duration and real yields:** falling yields favor technology, utilities, and real estate; rising yields can hurt all three, even though utilities and real estate are conventionally called defensive.
2. **Growth/recession risk:** growth scares favor staples, utilities, and sometimes healthcare; recoveries favor discretionary, financials, industrials, and technology.
3. **Inflation and physical scarcity:** energy and materials—not classic defensives—win when oil, inflation, or geopolitical scarcity dominates.
4. **Concentration versus breadth:** Nasdaq/mega-cap technology can lead while most sectors lag, or the index can stay healthy while leadership broadens into financials, industrials, healthcare, and equal weight.

The strongest practical conclusions are:

- **Defensives cushion an active decline, mostly because they are low beta—not because the relative gain proves fresh capital rotation.** In 46 SPY-down months from 2013–2025, an equal-weight healthcare/staples/utilities basket beat SPY by 1.48% on average and did so 70% of the time. Its measured beta was about 0.60, which explains nearly all of that contemporaneous cushion. This sample showed no detectable next-month excess-return edge.
- **Utilities and staples were more consistently defensive than healthcare.** Utilities produced +2.30% average excess in down months; staples +1.49%; healthcare only +0.65% with a 52% hit rate. Healthcare is a hybrid quality/growth/policy sector, not a guaranteed haven.
- **There is no robust calendar month for healthcare or staples.** Modern-sample “best months” moved around in the longer history. March utilities is the one interesting seasonal prior, but even it is too unstable to trade alone.
- **Midterms are a risk modulator, not a law.** The three completed modern midterms (2014/2018/2022) strongly favored defensives, but that full-year defensive effect failed in the non-overlapping 1999–2012 check. Q2 index weakness repeated directionally and was the strongest exploratory midterm pattern.
- **Standard weekly MACD failed as a standalone binary exit/re-entry system in this window.** QQQ was still positive 84% of the time 26 weeks after a bearish cross, and the asset gained during 29 of 31 completed bear-to-next-bull episodes. Selling every bear cross reduced maximum drawdown but substantially reduced CAGR. Whether MACD adds value as one corroborating input was not tested.
- **As of July 10, no weekly bear cross exists.** SPY and QQQ weekly MACD histograms remain positive, though about 74–75% below their recent 13-week peaks. Weekly RSI is about 66 and 64, respectively—not conventionally overbought.

### Confidence map

| Finding | Confidence | Why |
|---|---|---|
| Standard 12/26/9 weekly MACD should not be a binary Nasdaq exit/re-entry rule in this 2013–2026 window | High | 31 bear and 32 bull QQQ events; event study and full strategy agree |
| Current tape has not confirmed a full defensive regime | High | Price trend, breadth, VIX, credit, and defensive-sector confirmation agree |
| Low-beta defensives cushion active down months; no next-month edge was detected in this sample | High | 156 complete modern months; beta decomposition and next-month test agree |
| Midterm Q2 may be more hostile to the index | Medium-low | Repeats directionally before and after 2013; partitioned tests do not survive family adjustment |
| March utilities / May or October technology seasonality is tradable | Low | Month rankings drift across samples and multiple-testing adjustment removes most effects |

## 1. Research design and important boundaries

### What was measured

- **SPY** is the investable total-return proxy for the S&P 500. It tracks the S&P 500 before fees and expenses; see [State Street’s official fund description](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy).
- **QQQ** is the investable proxy used for Nasdaq leadership. It tracks the Nasdaq-100, not the full Nasdaq Composite; see [Invesco QQQ](https://www.invesco.com/qqq-etf/en/home.html) and Nasdaq’s [Nasdaq-100 versus Nasdaq Composite explanation](https://www.nasdaq.com/newsroom/nasdaq-composite-vs-nasdaq-100-what-investors-should-know).
- Sector returns use the 11 [Select Sector SPDRs](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs): XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLRE, and XLC.
- The repo’s `data/yahoo/<ticker>.parquet` **`close`** field is split- and dividend-adjusted. Results therefore approximate ETF total returns after fund expenses; they will not exactly match headline cash-index price returns.
- `DEF` is one consistent, equal-weight, daily-rebalanced total-return index of XLV, XLP, and XLU in the conditional, seasonal, and election tests.
- The main MACD study uses that adjusted total-return price field. A separate raw-close signal-basis check is reported because conventional chart MACD can differ around dividends.
- A “winner” is the sector with the best endpoint total return in the span. During a crash it may still have lost money.
- “Rotation” means **revealed relative pricing and leadership**, not directly observed mutual-fund or ETF dollar flows. Returns can reveal where the market repriced exposure; they cannot prove which investor class moved the money.

### What was deliberately not claimed

- Regime boundaries were chosen **ex post** at economically coherent market turns. They describe history; they are not proof those exact dates could have been traded in real time.
- Catalyst labels are context, not a claim that one headline caused every price move.
- Monthly seasonality and election-cycle tables are diagnostics, not promoted signals.
- The current regime conclusion is point-in-time and must be updated after the July 14 CPI report and Q2 earnings evidence.

### Structural breaks that matter

- **XLC began in June 2018.** The 2018 GICS restructuring moved Alphabet and Meta/Facebook from technology and media names from discretionary into Communication Services. Pre/post-2018 XLK, XLY, and XLC are not compositionally identical. See the [S&P DJI 2018 GICS revision](https://www.spglobal.com/spdji/en/documents/indexnews/announcements/20180111-646149/646149_gicspressreleasejan2018.pdf).
- **XLRE began in October 2015**, and real estate was carved out of Financials in 2016. Earlier XLF contained REIT exposure. See [S&P DJI’s sector-change FAQ](https://www.spglobal.com/spdji/en/documents/education/faq-the-impact-of-sector-changes-on-the-gics-framework-and-indices.pdf).
- Annual rankings exclude XLC’s partial 2018 and XLRE’s partial 2015. Span tables include them only after inception.

## 2. Whole-year scoreboard

| Year | SPY | QQQ | Leading sectors | Main laggard / weak cluster | Dominant annual regime |
|---|---:|---:|---|---|---|
| 2013 | +32.3% | +36.6% | XLY +42.7%, XLV +41.4%, XLI +40.5% | XLU +13.1% | QE recovery; risk-on broadening after taper shock |
| 2014 | +13.5% | +19.2% | XLU +28.7%, XLV +25.1%, XLK +17.8% | XLE -8.7% | Growth scares, falling yields, oil collapse |
| 2015 | +1.2% | +9.4% | XLY +9.9%, XLP +6.9%, XLV +6.8% | XLE -21.5% | Narrow quality/growth; commodity bear; China shock |
| 2016 | +12.0% | +7.1% | XLE +28.0%, XLF +22.4%, XLI +20.0% | XLV -2.8% | Commodity bottom and reflation; Trump trade |
| 2017 | +21.7% | +32.7% | XLK +34.3%, XLB +24.0%, XLI +24.0% | XLE -0.9% | Goldilocks technology bull, then tax/reflation breadth |
| 2018 | -4.6% | -0.1% | XLV +6.3%, XLU +3.9%, XLY +1.6% | XLE -18.2% | Late-cycle growth, then Q4 tightening bear |
| 2019 | +31.2% | +39.0% | XLK +49.9%, XLF +31.9%, XLC +31.0% | XLE +11.7% | Fed pivot and liquidity-led risk-on |
| 2020 | +18.3% | +48.4% | XLK +43.6%, XLY +29.6%, XLC +26.9% | XLE -32.7% | Pandemic crash, policy rescue, work-from-home duration bull |
| 2021 | +28.7% | +27.4% | XLE +53.3%, XLRE +46.1%, XLF +34.8% | XLC +16.0% | Reopening/reflation, then duration/quality rebound |
| 2022 | -18.2% | -32.6% | XLE +64.3%, XLU +1.4%, XLP -0.8% | XLC -37.6% | Inflation and rate-shock bear; energy scarcity |
| 2023 | +26.2% | +54.9% | XLK +56.0%, XLC +52.8%, XLY +39.6% | XLU -7.2% | Disinflation, banking stress, narrow AI leadership |
| 2024 | +24.9% | +25.6% | XLC +34.7%, XLF +30.6%, XLY +26.5% | XLB +0.1% | AI plus intermittent broadening and election reflation |
| 2025 | +17.7% | +20.8% | XLK +24.6%, XLC +23.1%, XLI +19.3% | XLP +1.5% | Tariff shock/reversal, then AI/power-capex rally |
| 2026 YTD | +11.0% | +18.3% | XLK +29.2%, XLE +24.0%, XLI +17.6% | XLC -4.9%, XLY -1.6% | Q1 inflation defense → Q2 tech melt-up → June broadening probe |

The annual table hides the most useful information: leadership frequently changes two to five times inside a year. The next section reconstructs those rotations.

## 3. Regime and rotation atlas

`SPY / QQQ` is the endpoint total return in each span. “Leaders” and “laggards” are the three highest and lowest available sector ETFs. Exact per-sector returns for every row are in `regime_rotation_spans.csv`.

### 2013–2017: QE recovery, commodity bust, then reflation and Goldilocks

| Span | Regime / catalyst | SPY / QQQ | Leaders | Laggards | Capital-rotation read |
|---|---|---:|---|---|---|
| 2013 Jan 2–May 21 | QE-supported recovery and improving labor market | +15.0% / +10.8% | XLV +21.7%, XLY +19.4%, XLF +19.2% | XLB +7.6%, XLK +8.1%, XLU +9.1% | Broad domestic rally: health plus consumer/financial cyclicals, not yet Nasdaq domination. |
| May 21–Jun 24 | Taper tantrum after Bernanke signaled purchases could change ([testimony](https://www.federalreserve.gov/newsevents/testimony/bernanke20130522a.htm)) | -5.6% / -5.8% | XLV -4.4%, XLP -4.9%, XLY -5.0% | XLU -8.2%, XLE -6.9%, XLB -6.5% | Yield-sensitive utilities were worse than staples/health: “defensive” did not mean rate-proof. |
| Jun 24–Dec 31 | Growth confidence and risk-on normalization; Fed later began tapering ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20131218a.htm)) | +18.8% / +26.9% | XLI +26.9%, XLY +23.4%, XLB +22.5% | XLU +6.1%, XLP +11.0%, XLE +13.2% | Nasdaq and cyclicals took the baton; bond proxies lagged. |
| 2014 Jan 2–Feb 3 | Global/EM growth scare | -4.8% / -3.4% | XLU +3.7%, XLV -0.5%, XLK -3.0% | XLY -8.0%, XLB -6.2%, XLE -5.5% | Classic early risk-off rotation into utilities and health. |
| Feb 3–Jun 30 | Falling yields plus oil’s last advance | +13.4% / +12.4% | XLE +23.4%, XLB +16.4%, XLU +16.0% | XLY +9.8%, XLP +11.0%, XLF +11.1% | Unusual commodity-plus-duration barbell, not a clean cyclical/defensive split. |
| Jun 30–Oct 15 | Global-growth concern and oil collapse ([EIA review](https://www.eia.gov/finance/review/annual/)) | -4.3% / -1.4% | XLP +0.2%, XLV -0.2%, XLU -1.0% | XLE -19.1%, XLB -7.8%, XLI -7.3% | Staples/health preserved while commodities and industrial beta were sold. |
| Oct 15–Dec 31 | Policy reassurance, end of QE, and cheaper-energy consumer tailwind ([Fed](https://www.federalreserve.gov/newsevents/pressreleases/monetary20141029a.htm)) | +10.9% / +12.2% | XLY +14.7%, XLI +13.5%, XLV +13.4% | XLE -1.1%, XLB +7.8%, XLF +8.7% | Consumer/industrial rebound; energy’s bear market persisted. |
| 2015 Jan 2–May 21 | Slow-growth quality rally | +4.4% / +7.7% | XLV +9.8%, XLY +8.0%, XLK +6.2% | XLU -5.2%, XLE -2.5%, XLB -0.9% | Growth/quality beat commodities and rate-sensitive defensives. |
| May 21–Aug 17 | Sideways index, deep commodity deterioration | -0.9% / +1.0% | XLU +3.5%, XLY +3.0%, XLF +2.3% | XLE -13.1%, XLB -9.7%, XLI -4.7% | Index calm concealed a major energy/materials bear market. |
| Aug 17–Sep 29 | China devaluation/global-volatility shock ([IMF account](https://www.elibrary.imf.org/view/journals/001/2019/050/article-A001-en.xml)) | -10.2% / -10.5% | XLU -6.2%, XLP -6.3%, XLY -8.5% | XLB -14.5%, XLV -14.5%, XLE -13.3% | Utilities/staples cushioned; healthcare failed as drug-pricing risk joined macro risk. |
| Sep 29–Dec 31 | Relief rebound into first Fed hike ([Fed](https://www.federalreserve.gov/newsevents/pressreleases/monetary20151216a.htm)) | +9.0% / +12.8% | XLB +11.9%, XLV +11.5%, XLK +11.1% | XLE +1.8%, XLU +2.8%, XLP +7.4% | Growth/quality returned; commodity rebound lacked energy confirmation. |
| 2016 Jan 4–Feb 11 | China/oil panic and credit fear | -9.0% / -11.8% | XLU +5.8%, XLP -1.0%, XLE -6.2% | XLF -15.9%, XLY -10.8%, XLB -10.6% | Pure preservation: utilities/staples versus banks and high beta. |
| Feb 11–Jun 23 | Commodity bottom and global reflation | +16.5% / +13.3% | XLE +29.9%, XLB +25.1%, XLRE +21.8% | XLP +10.9%, XLV +11.5%, XLU +12.3% | Hard rotation into beaten-down real assets; Nasdaq lagged SPY. |
| Jun 23–Jul 8 | Brexit shock and rapid recovery ([official result](https://www.electoralcommission.org.uk/media-centre/official-result-eu-referendum-declared-electoral-commission-manchester)) | +0.9% / +1.4% | XLU +4.4%, XLRE +4.2%, XLV +3.2% | XLB -2.4%, XLE -1.9%, XLF -1.8% | Lower yields rewarded utilities/REITs and punished financials. |
| Jul 8–Nov 7 | Yields bottom; reflation expectations rebuild | +0.7% / +5.7% | XLF +7.8%, XLK +7.4%, XLE +2.9% | XLRE -9.7%, XLV -7.1%, XLU -5.7% | Banks and tech advanced while rate-sensitive defensives rolled over. |
| Nov 7–Dec 30 | Post-election reflation/deregulation | +5.5% / +2.1% | XLF +16.9%, XLE +9.4%, XLI +8.2% | XLP -0.7%, XLU +0.5%, XLV +1.7% | Textbook cyclicals-over-defensives handoff; SPY beat QQQ. |
| 2017 Jan 3–Sep 8 | Goldilocks: synchronized growth, low inflation and volatility | +10.5% / +21.2% | XLK +19.9%, XLV +19.1%, XLU +16.1% | XLE -14.4%, XLF +3.3%, XLRE +4.6% | Tech plus defensive-growth barbell; energy collapsed despite strong indices. |
| Sep 8–Dec 29 | Higher yields, tax reform, late-year reflation ([Fed normalization](https://www.federalreserve.gov/publications/2017-ar-monetary-policy.htm), [Tax Cuts and Jobs Act](https://www.congress.gov/bill/115th-congress/house-bill/1/summary/36)) | +9.3% / +8.5% | XLF +16.8%, XLE +14.4%, XLI +12.0% | XLU -3.2%, XLV +0.9%, XLRE +2.5% | Capital moved from defensives into banks, energy, and industrials. |

The 2013–2017 lesson is already enough to reject a two-bucket model. Utilities led the early-2014 growth scare, but energy and utilities then rose together in the falling-yield/oil barbell. In 2016, commodities and banks—not technology—were the decisive transition out of the panic.

### 2018–2022: tightening, pandemic, reopening, and the inflation shock

| Span | Regime / catalyst | SPY / QQQ | Leaders | Laggards | Capital-rotation read |
|---|---|---:|---|---|---|
| 2018 Jan 2–Jan 26 | Tax-cut growth melt-up | +6.6% / +7.8% | XLV +9.5%, XLY +8.8%, XLF +8.1% | XLP +3.8%, XLRE -1.8%, XLU -2.2% | Health and cyclicals led together while bond proxies fell. |
| Jan 26–Apr 2 | Volatility/rate shock and trade escalation ([USTR Section 301 record](https://ustr.gov/issue-areas/enforcement/section-301-investigations/section-301-china/investigation)) | -9.8% / -8.9% | XLU -1.0%, XLRE -4.0%, XLK -7.4% | XLB -12.8%, XLV -12.8%, XLE -14.2% | Utilities preserved capital, but healthcare did not; this was not a uniform defensive trade. |
| Apr 2–Sep 20 | Strong U.S. earnings and growth | +14.5% / +19.0% | XLY +20.0%, XLV +19.2%, XLK +18.1% | XLP +8.6%, XLF +8.0%, XLU +7.3% | Growth/quality led; staples and utilities lagged despite rising. |
| Sep 20–Dec 24 | Fed/trade tightening and growth scare; the Fed delivered its fourth 2018 hike on Dec. 19 ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20181219a.htm)) | -19.3% / -22.0% | XLU -1.6%, XLRE -9.0%, XLP -10.5% | XLK -22.7%, XLI -23.6%, XLE -27.2% | Classic late-cycle defensive preservation; energy and cyclicals absorbed the largest losses. |
| Dec 24–Dec 31 | Oversold policy-reassessment bounce | +6.6% / +7.5% | XLY +7.6%, XLK +7.6%, XLV +7.2% | XLP +4.2%, XLRE +4.0%, XLU +2.6% | The first rebound was high beta, not defensive. |
| 2019 Jan 2–Apr 30 | Fed pivot and broad rebound | +18.0% / +22.6% | XLK +27.3%, XLI +21.2%, XLY +20.8% | XLU +13.7%, XLB +13.6%, XLV +5.2% | Policy relief restored tech/cyclical leadership. |
| Apr 30–Aug 30 | Trade escalation and yield-curve scare; the Fed cut in July ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20190731a.htm)) | -0.1% / -0.9% | XLRE +9.7%, XLU +7.4%, XLP +6.0% | XLI -2.5%, XLF -3.4%, XLE -12.3% | Falling yields produced a clean REIT/utilities/staples rotation while the cap-weighted index went nowhere. |
| Aug 30–Dec 31 | Fed cuts and trade stabilization | +11.1% / +13.9% | XLK +16.0%, XLF +15.5%, XLV +14.1% | XLP +5.2%, XLU +4.9%, XLRE +0.4% | Technology and financials led the risk-on handoff; bond proxies lagged. |
| 2020 Jan 2–Feb 19 | Late-cycle secular growth/falling-yield barbell | +4.1% / +9.6% | XLK +10.1%, XLU +10.0%, XLRE +7.9% | XLF +0.2%, XLB -0.3%, XLE -9.5% | Technology and duration defensives rose together—an important counterexample to a simple alternation model. |
| Feb 19–Mar 23 | COVID liquidity/recession crash ([NBER chronology](https://www.nber.org/research/business-cycle-dating)) | -33.7% / -27.9% | XLP -24.2%, XLV -27.9%, XLC -29.8% | XLI -41.6%, XLF -42.8%, XLE -56.1% | Defensives only lost less; energy and financials were liquidated. |
| Mar 23–Aug 31 | Policy rescue, reopening hope, and work-from-home boom; the Fed launched broad support on Mar. 23 ([release](https://www.federalreserve.gov/newsevents/pressreleases/monetary20200323b.htm)) | +57.4% / +73.3% | XLK +76.0%, XLY +71.9%, XLB +65.2% | XLF +42.8%, XLP +35.9%, XLU +33.0% | Extreme duration/growth rebound; defensives became funding sources. |
| Aug 31–Oct 30 | Growth consolidation and election uncertainty | -6.1% / -8.6% | XLU +6.2%, XLB +0.8%, XLI -2.1% | XLC -6.2%, XLK -10.1%, XLE -18.1% | Utilities counter-trended positively as mega-cap growth corrected. |
| Oct 30–Dec 31 | Vaccine/reopening trade ([FDA COVID-19 record](https://www.fda.gov/emergency-preparedness-and-response/public-health-preparedness-and-response/coronavirus-disease-2019-covid-19)) | +15.0% / +16.7% | XLE +33.7%, XLF +24.2%, XLK +17.6% | XLP +9.2%, XLRE +8.4%, XLU +1.4% | Energy/banks took the baton; tech still participated. |
| 2021 Jan 4–May 7 | Reopening, fiscal impulse, and rising inflation | +14.8% / +8.2% | XLE +42.8%, XLF +30.5%, XLB +23.1% | XLK +8.9%, XLU +8.9%, XLP +6.4% | Reflation was a relative bear market for duration and a boom for physical/cyclical exposure. |
| May 7–Sep 2 | Delta concern and falling yields | +7.7% / +14.0% | XLRE +15.8%, XLK +14.4%, XLV +10.6% | XLI +0.2%, XLB -1.8%, XLE -7.9% | Technology, real estate, and health became the duration/quality barbell. |
| Sep 2–Oct 4 | Inflation and yield shock | -5.1% / -7.2% | XLE +13.3%, XLF -0.9%, XLY -2.2% | XLU -6.9%, XLRE -7.2%, XLV -8.0% | Rising yields hurt conventional defensives while energy surged. |
| Oct 4–Dec 31 | Earnings-led year-end rally and taper; the Fed began reducing purchases in November ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20211103a.htm)) | +11.2% / +13.0% | XLK +17.7%, XLRE +16.2%, XLY +14.1% | XLF +3.8%, XLE +2.7%, XLC -2.3% | Growth/duration resumed even as policy normalization began. |
| 2022 Jan 3–Mar 8 | Inflation, invasion, and first-hike pricing | -12.9% / -19.5% | XLE +35.5%, XLU -0.2%, XLP -6.0% | XLC -18.0%, XLK -18.2%, XLY -22.2% | Energy scarcity dominated; utilities/staples were relative shelters. |
| Mar 8–Jun 16 | Accelerated tightening and earnings compression; the Fed began hiking in March ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm)) | -11.6% / -16.0% | XLE +1.2%, XLP -4.3%, XLB -5.6% | XLRE -14.0%, XLC -17.0%, XLY -17.5% | Inflation hedges and staples preserved while duration/consumer beta de-rated. |
| Jun 16–Aug 16 | Peak-inflation hope / bear-market rally after June CPI reached 9.1% ([BLS release](https://www.bls.gov/news.release/archives/cpi_07132022.htm)) | +17.7% / +22.7% | XLY +28.8%, XLK +22.7%, XLU +19.4% | XLV +12.1%, XLB +9.4%, XLE -0.2% | High-duration beta snapped back; utilities also benefited from yield relief. |
| Aug 16–Oct 12 | Jackson Hole/higher-real-yield reset ([Powell speech](https://www.federalreserve.gov/newsevents/speech/powell20220826a.htm)) | -16.7% / -20.8% | XLE +5.5%, XLV -8.6%, XLP -11.7% | XLC -20.3%, XLK -22.7%, XLRE -24.7% | Energy was the only positive sector; rate-sensitive real estate was worse than staples. |
| Oct 12–Dec 30 | Inflation-peak/soft-landing hope | +7.7% / +1.6% | XLI +16.4%, XLU +15.5%, XLB +14.1% | XLK +7.1%, XLC +1.0%, XLY -6.8% | Old-economy breadth and utilities led; Nasdaq failed to confirm. |

The 2018–2022 sequence shows why the macro driver matters more than the label. Utilities protected in the Q4 2018 growth scare and the 2020 election correction, but were poor hedges when the shock itself was higher inflation or yields. Energy was the crucial third pole: it led both the 2021 reopening and 2022 bear market.

### 2023–July 2026: AI concentration, intermittent breadth, tariff shock, and inflation constraint

| Span | Regime / catalyst | SPY / QQQ | Leaders | Laggards | Capital-rotation read |
|---|---|---:|---|---|---|
| 2023 Jan 3–Feb 2 | Disinflation risk-on | +9.4% / +17.9% | XLC +22.2%, XLY +21.6%, XLK +16.0% | XLP -0.8%, XLU -1.6%, XLV -1.8% | High-duration growth immediately displaced defensives. |
| Feb 2–May 31 | Regional-bank stress plus AI breakout; authorities created the BTFP after SVB failed ([Fed](https://www.federalreserve.gov/newsevents/pressreleases/monetary20230312a.htm), [FDIC](https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list/silicon-valley.html)) | +0.6% / +11.8% | XLK +15.2%, XLC +5.1%, XLP -0.9% | XLB -11.3%, XLF -12.9%, XLRE -13.2% | A near-flat SPY hid an enormous mega-cap/AI-versus-banks split. Nvidia’s May outlook accelerated the theme ([release](https://investor.nvidia.com/news/press-release-details/2023/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2024/)). |
| May 31–Jul 31 | Breadth broadening / soft landing | +10.0% / +10.4% | XLE +15.2%, XLY +14.8%, XLB +14.8% | XLV +5.4%, XLP +5.0%, XLU +4.1% | Cyclicals caught up without breaking the index trend. |
| Jul 31–Oct 27 | Higher-for-longer yield shock | -10.0% / -9.9% | XLE -2.5%, XLV -7.8%, XLC -8.1% | XLI -12.3%, XLY -13.7%, XLRE -14.6% | Real estate was the worst “defensive”; healthcare preserved better. |
| Oct 27–Dec 29 | Fed-pivot/rate-relief rally; December projections opened the door to easier policy ([Fed](https://www.federalreserve.gov/newsevents/pressreleases/monetary20231213a.htm)) | +16.2% / +18.9% | XLRE +25.2%, XLF +20.1%, XLY +19.7% | XLP +9.0%, XLU +8.9%, XLE +0.0% | Falling yields drove an unusually broad rally led by the prior duration casualties. |
| 2024 Jan 2–Mar 28 | AI earnings plus reflation broadening | +11.0% / +10.4% | XLC +13.3%, XLE +12.3%, XLI +12.0% | XLY +4.0%, XLU +3.0%, XLRE -1.6% | SPY kept pace with QQQ as communications, energy, and industrials broadened. |
| Mar 28–Jul 10 | AI concentration and power-demand theme; Nvidia again raised the earnings bar ([release](https://investor.nvidia.com/news/press-release-details/2024/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2025/default.aspx)) | +7.7% / +13.5% | XLK +14.3%, XLC +7.8%, XLU +6.7% | XLI -2.9%, XLB -4.4%, XLE -4.6% | Technology concentration coexisted with utility demand from the data-center power theme. |
| Jul 10–Sep 17 | Mega-cap unwind / rate-cut rotation | +0.3% / -5.9% | XLRE +16.4%, XLU +13.8%, XLI +8.2% | XLC -0.0%, XLE -1.8%, XLK -7.8% | A textbook internal handoff: the S&P stayed flat while REITs/utilities/industrials displaced tech. |
| Sep 17–Nov 5 | Post-cut risk-on; the Fed cut 50 basis points on Sep. 18 ([decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm)) | +2.7% / +4.1% | XLC +6.4%, XLY +5.3%, XLK +3.7% | XLRE -2.0%, XLP -2.6%, XLV -4.6% | Growth leadership resumed after the initial rate-cut rotation. |
| Nov 5–Dec 31 | Post-election growth/deregulation | +2.0% / +4.0% | XLY +10.8%, XLC +4.2%, XLF +3.9% | XLRE -6.2%, XLV -6.5%, XLB -9.7% | Consumer beta and financials won; defensives/materials were funding sources. |
| 2025 Jan 2–Feb 19 | Soft-landing broadening | +4.8% / +5.7% | XLF +8.3%, XLB +8.1%, XLC +7.9% | XLK +4.4%, XLP +4.1%, XLY +2.2% | Financials/materials led an index advance without a defensive signal. |
| Feb 19–Apr 8 | Tariff shock and growth downgrade; reciprocal tariffs were announced Apr. 2 ([White House order](https://www.whitehouse.gov/presidential-actions/2025/04/regulating-imports-with-a-reciprocal-tariff-to-rectify-trade-practices-that-contribute-to-large-and-persistent-annual-united-states-goods-trade-deficits/)) | -18.8% / -22.8% | XLP -5.9%, XLU -8.3%, XLV -8.8% | XLC -17.7%, XLY -21.8%, XLK -25.7% | Clean defensive preservation as growth and consumer beta de-rated. |
| Apr 8–Jun 30 | Tariff pause/de-escalation and AI rebound; rates were modified Apr. 9 ([order](https://www.whitehouse.gov/presidential-actions/2025/04/modifying-reciprocal-tariff-rates-to-reflect-trading-partner-retaliation-and-alignment/)) | +24.8% / +32.7% | XLK +41.1%, XLI +27.1%, XLC +26.3% | XLE +11.9%, XLP +6.8%, XLV +1.8% | Violent high-beta reversal; healthcare barely participated. |
| Jun 30–Oct 29 | AI and power-capex rally | +11.6% / +15.4% | XLK +20.3%, XLU +11.1%, XLY +10.2% | XLF -0.2%, XLRE -1.1%, XLP -4.8% | Tech and utilities again formed a capex/power barbell, not a risk-off signal. |
| Oct 29–Dec 31 | Mega-cap pause / health and breadth rebound | -0.5% / -3.3% | XLV +8.0%, XLF +5.5%, XLB +4.4% | XLY +0.1%, XLU -4.5%, XLK -5.2% | Healthcare-led rotation cushioned an index pause, but utilities did not confirm. |
| 2026 Jan 2–Mar 30 | Energy/inflation/geopolitical risk | -7.2% / -8.8% | XLE +36.6%, XLU +7.1%, XLB +6.9% | XLY -10.5%, XLF -11.5%, XLK -11.5% | Energy scarcity and inflation hedging led; this was not a pure staples/health defense. |
| Mar 30–Jun 2 | AI reacceleration / risk-on melt-up | +19.9% / +33.5% | XLK +55.3%, XLY +11.1%, XLI +11.0% | XLP -0.8%, XLU -5.0%, XLE -7.1% | An extreme tech sprint: QQQ gained nearly twice SPY and defensives became funding sources. |
| Jun 2–Jul 10 | Technology consolidation / broadening pulse | -0.4% / -2.7% | XLV +10.4%, XLF +8.6%, XLI +4.7% | XLC -1.4%, XLE -4.3%, XLK -6.2% | Healthcare/financials/industrials took the baton, but staples and utilities did not lead strongly enough to confirm a defensive regime. |

The live macro backdrop is unusually mixed. The Fed held its target range at 3.5%–3.75% on June 17 and described growth as solid while inflation remained elevated ([statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm)). Q1 real GDP was revised to +2.1%, yet Q1 core PCE inflation ran at a 4.4% annualized rate ([BEA](https://www.bea.gov/index.php/news/2026/gdp-third-estimate-industries-corporate-profits-state-gdp-and-state-personal-income-1st)). May headline/core PCE were 4.1%/3.4% year over year ([BEA](https://www.bea.gov/news/2026/personal-income-and-outlays-may-2026)), while June payrolls rose 57,000 and unemployment was 4.2% ([BLS](https://www.bls.gov/news.release/archives/empsit_07022026.htm)). The jobs report alone does not establish recession risk; combined with sticky inflation and the market tape, it explains the label **inflation-constrained rotational bull** better than either “Goldilocks” or “recession defense.”

### The important rotations that crossed New Year’s Eve

Calendar years can cut a genuine regime in half. Four especially clear bridges are:

| Cross-year span | SPY / QQQ | Leaders | Laggards | Read |
|---|---:|---|---|---|
| 2018 Dec 24–2019 Apr 30 | +26.0% / +32.3% | XLK +37.0%, XLY +31.0%, XLI +30.0% | XLP +19.1%, XLU +14.7%, XLV +11.0% | Fed-pivot recovery was a continuous tech/cyclical regime, not two separate annual stories. |
| 2020 Oct 30–2021 May 7 | +30.2% / +24.4% | XLE +91.2%, XLF +59.9%, XLB +40.4% | XLV +23.0%, XLP +15.0%, XLU +7.6% | Vaccine-to-reopening reflation decisively transferred leadership away from duration. |
| 2023 Oct 27–2024 Mar 28 | +28.3% / +29.1% | XLF +35.1%, XLI +31.7%, XLC +30.1% | XLP +16.4%, XLU +13.8%, XLE +13.5% | Rate relief evolved into AI/reflation breadth while the index trend persisted. |
| 2024 Nov 5–2025 Feb 19 | +6.6% / +9.8% | XLC +13.0%, XLF +12.2%, XLY +11.7% | XLV -0.5%, XLRE -2.4%, XLB -3.5% | Post-election growth continued into the 2025 soft-landing phase before the tariff break. |

These bridges are the main reason not to force a December 31 reset into a regime model.

## 4. What actually repeats

### The useful rotation map is four-dimensional

| Dominant force | Typical winners | Typical losers | Historical examples | Diagnostic implication |
|---|---|---|---|---|
| Falling yields / disinflation | XLK, QQQ, XLRE, often XLU | XLE, sometimes XLF | 2019 pivot; 2020 pre-COVID barbell; late 2023 | Tech and utilities rising together can be a duration trade, not “risk-on plus risk-off confusion.” |
| Growth/recession scare | XLP, XLU, sometimes XLV; cash-like quality | XLY, XLI, XLF, small caps | early 2014; Q4 2018; COVID crash; tariff shock | Relative defense is strongest during the selloff, but the sector can still lose outright. |
| Inflation / scarcity / rising real yields | XLE, XLB, sometimes XLF and XLI | XLK/QQQ, XLRE, XLY; XLU can also fail | 2016 reflation; 2021 reopening; 2022; Q1 2026 | Energy is a separate regime pole and must not be grouped mechanically with cyclicals or defensives. |
| Soft landing / breadth expansion | XLF, XLI, XLB, XLY, RSP/IWM catch-up | Prior narrow leaders may consolidate; defensives usually lag | late 2016; 2019; vaccine trade; mid-2023; early 2024/2025 | Broadening is not automatically bearish for the index or technology. |
| Secular earnings concentration | XLK, XLC, QQQ, SMH | Most equal-weight sectors | 2017; 2020; early 2023; 2024; Q2 2026 | Cap-weighted indices can look excellent while the median stock is mediocre. |

So the user’s intuition is directionally right but incomplete: technology and defensives often trade leadership, yet the tape also spends long periods in **reflation**, **energy scarcity**, **broad cyclical recovery**, and **tech-plus-duration barbell** regimes.

### Sector personalities distilled from the spans

- **Technology/Nasdaq:** best when either yields are falling or earnings growth is strong enough to overwhelm yields. Its cleanest regimes were 2017, 2019, the post-March-2020 rebound, 2023, and the 2025–Q2 2026 AI waves. It is most vulnerable when inflation forces real yields up or when positioning becomes extreme—not merely because it has risen.
- **Healthcare:** usually behaves as quality growth rather than a pure bond proxy. It led during 2013 domestic growth, 2014 defense, 2018 late-cycle preservation, and the June 2026 broadening pulse; it failed badly in the 2015 China/drug-pricing shock and did not protect much in the 2025 rebound. Policy, patent, and earnings breadth matter.
- **Staples:** the cleanest demand defense. It tends to lose less during acute growth shocks but rarely leads the first powerful recovery leg. That is exactly what happened in 2020 and the 2025 tariff reversal.
- **Utilities:** the strongest average down-month hedge in this sample, but also a duration asset. It can lead a growth scare when yields fall and fail a selloff caused by higher yields. Data-center power demand created a second, non-defensive utility thesis in 2024–2025.
- **Energy:** the recurring answer when the shock is physical scarcity rather than deficient demand. It dominated 2016, the 2020–2021 vaccine/reopening bridge, 2022, and Q1 2026.
- **Financials/industrials/materials:** the most reliable broadening/reflation cluster. When these lead while credit stays calm and SPY remains above trend, the better interpretation is often “healthy handoff,” not “defensive warning.”
- **Real estate:** highly sensitive to the rates channel. It led the 2019 growth scare and late-2023 rate relief but was the worst sector in the 2023 higher-for-longer shock. Calling it defensive without a yield view is dangerous.

### Low-beta defensives cushion now, not necessarily next

`DEF` is compared with SPY across the 156 complete months from January 2013 through December 2025.

| State | N | DEF excess vs SPY | Excess hit rate | XLV excess | XLP excess | XLU excess | XLK excess |
|---|---:|---:|---:|---:|---:|---:|---:|
| SPY up month | 110 | -1.03% | 38.2% | -0.48% | -1.25% | -1.38% | +0.71% |
| SPY down month | 46 | +1.48% | 69.6% | +0.65% | +1.49% | +2.30% | -0.04% |

The first-principles explanation is mostly ordinary beta. Monthly `DEF` beta to SPY was **0.601**. Given the realized size of down months, the fitted low-beta model predicted +1.66% excess; observed excess was +1.48%. The conditional residual was -0.18% with p=.569. In up months, the model predicted -1.11% versus -1.03% observed; residual p=.734. The basket cushioned, but the cushion is not by itself proof of active rotation.

The **following** month also provides no reliable forecast:

- after an SPY up month, next-month defensive excess averaged -0.19% (95% CI -0.67% to +0.28%, p=.423);
- after an SPY down month, it averaged -0.54% (95% CI -1.55% to +0.46%, p=.282), with exactly a 50% hit rate.

Those are conventional month-level t intervals, not HAC/block-robust inference. The defensible statement is failure to detect a one-month edge in this sample—not proof that no predictive relationship can exist. Defensive leadership describes contemporaneous low-beta shelter; a single defensive month is not, by itself, a forward recession or bear-market signal. This is consistent with the many fast handoffs in the atlas: the first rebound leg often goes directly back to growth or cyclicals.

## 5. Seasonality and the election cycle

### There is no dependable “healthcare month” or “staples season”

The table reports average monthly **excess return versus SPY**, not raw return. `p` is a conventional two-sided t-test. `q-asset` applies Benjamini–Hochberg across one asset’s 12 months; `q-family` applies it across all 108 asset/month tests in that sample. The 1999–2025 view is expanded context, not independent validation, because it contains 2013–2025. The 1999–2012 column is a non-overlapping pre-2013 check, not a prospectively reserved holdout.

| Claim tested | 2013–2025 modern | 1999–2012 independent history | 1999–2025 expanded context | Assessment |
|---|---|---|---|---|
| Defensive basket in March | +1.66%, 84.6% hit, p=.016, q-family=.568 | -0.63%, 57.1% hit, p=.360 | +0.47%, 70.4% hit, p=.344 | Failed independent replication. |
| Utilities in March | +2.97%, 92.3% hit, p=.0009, q-asset=.0109, q-family=.0978 | -0.41%, 64.3% hit, p=.747 | +1.22%, 77.8% hit, p=.129 | The most interesting modern prior, but not a globally adjusted or out-of-sample edge. |
| Staples in March | +1.33%, 69.2% hit, p=.086 | -0.89%, 35.7% hit, p=.230 | +0.18%, 51.9% hit, p=.742 | Failed. |
| Healthcare | Modern best was March: +0.62%, 38.5% hit, p=.502 | March -0.64%; earlier best was January +1.34%, p=.056, q-family=.963 | Expanded best was January +0.78%, p=.200 | Month ranking changes; no stable edge. |
| Technology in May | +1.87%, 76.9% hit, p=.035, q-family=.681 | -0.32%, p=.762 | +0.74%, p=.284 | Failed independent replication. |
| Technology in October | +0.88%, 61.5% hit, p=.143 | +1.80%, 71.4% hit, p=.254 | +1.36%, 66.7% hit, p=.109 | Directionally interesting, statistically weak. |

Why the drift? A calendar month mixes very different macro states: September 2021 was an inflation/yield shock, September 2024 a rate-cut rotation, and September 2025 part of an AI/power rally. **Regime state dominates month name.** Seasonality belongs as a small prior after trend, breadth, yields, credit, and earnings—not as a standalone sector switch.

### Midterm years look different in this sample; Q2 weakness is the strongest exploratory repeat

The modern sample has only three completed midterms: 2014, 2018, and 2022. The independent earlier sample contributes 2002, 2006, and 2010. The six-observation expanded view is still small.

| Test | Modern 2013–2025 | Independent 1999–2012 | Expanded 1999–2025 | Interpretation |
|---|---:|---:|---:|---|
| Full-year SPY return | -3.09% | +3.11% | +0.01% vs +12.83% other years | Midterms were weak on average, but not uniformly negative. |
| Full-year DEF excess | +11.18% | -1.32% | +4.93%; permutation p=.131, within-sample q=.276 | Modern defensive leadership failed independent replication. |
| Full-year healthcare excess | +12.87% | +0.10% | +6.49%; p=.079, q=.276 | Suggestive expanded result, absent earlier. |
| Full-year utilities excess | +14.47% | -3.96% | +5.25%; p=.236, q=.362 | Modern effect does not replicate. |
| Q2 SPY return | -2.47% | -8.72% | -5.60%; p=.0026, within-sample q=.044 | The most persistent midterm observation. |
| Jul–Dec SPY return | +0.48% | +8.50% | +4.49% | Late-year recovery was broad, not automatic defense. |

The four-year labels are deterministic, so permutation exchangeability is debatable; all election p/q values are exploratory. The defensible conclusion is modest: **midterm Q2 is the only calendar feature worth retaining as a low-weight risk prior**, especially when liquidity, breadth, or earnings already weaken. Full-year defensive leadership is not a robust rule. Do not front-run a defensive regime merely because the calendar says “midterm.”

## 6. Weekly MACD: direct answer to the exit/re-entry question

### Test design

- Friday weekly adjusted closes; standard **12/26/9 exponential MACD**.
- A crossover is known at the weekly close. Event returns begin at the **next trading session’s adjusted close** to avoid same-close look-ahead.
- Forward horizons are 4, 8, 13, 26, and 52 weeks. The table below focuses on the user’s tactical-to-intermediate horizons.
- “Recent RSI≥70” means weekly RSI(14) had reached at least 70 in the preceding four weeks before a bearish cross.
- The full strategy also executes at the next trading session’s close and charges 10 basis points per one-way switch. It is shown with both zero-yield cash and an approximate effective-fed-funds cash return.
- Events overlap and are serially dependent. The artifact deliberately reports them as descriptive statistics without naive IID confidence intervals; the continuous strategy is the more important economic test.

### What happened after QQQ crosses, 2013–July 2026

| Event | N | 4-week return / positive | 13-week return / positive | 26-week return / positive |
|---|---:|---:|---:|---:|
| Bullish cross | 32 / 31 at longer horizons | +1.77% / 71.9% | +3.69% / 71.0% | +6.71% / 74.2% |
| Bearish cross | 31 | +1.64% / 74.2% | +4.43% / 80.6% | +11.73% / 83.9% |
| Bearish cross after recent RSI≥70 | 12 | +1.17% / 75.0% | +5.28% / 91.7% | +11.63% / 83.3% |
| Unconditional weekly observation | 701 / 692 / 678 | +1.67% / 69.2% | +5.26% / 78.2% | +10.41% / 83.2% |

Two conclusions follow immediately:

1. **A bearish MACD cross is not an overbought reading.** MACD measures trend/momentum; RSI is the overbought-style input. Conditioning on recent RSI≥70 still did not produce negative average forward returns, although only 12 events qualified; an RSI-conditioned strategy was not separately backtested.
2. **A bullish cross is confirmation, not a cheap-entry oracle.** Its four-week return was slightly better than the unconditional observation, but its 13- and 26-week returns were lower. Waiting for confirmation often means rebuying after part of the rebound.

The bear-to-next-bull path makes the rule’s realized opportunity cost explicit. Across 31 completed QQQ episodes, QQQ gained while the rule was out of market in **29 cases (93.5%)**; mean/median missed return was **+4.86%/+5.09%**. The mean worst excursion after the bearish exit was -5.78%, so the rule sometimes avoided painful drawdowns—but most episodes recovered before the bullish re-entry. This statistic is not independent confirmation: the endpoint is mechanically the next moment momentum improves enough to create a bullish cross. The continuous strategy is the valid economic comparison.

### Continuous strategy result

| QQQ strategy | CAGR | Max drawdown | Volatility | Zero-rate Sharpe | Time invested | Switches |
|---|---:|---:|---:|---:|---:|---:|
| Weekly MACD bull / zero-yield cash | 7.76% | -26.47% | 12.66% | 0.66 | 57.3% | 63 |
| Weekly MACD bull / effective-fed-funds cash | 8.54% | -25.89% | 12.66% | 0.71 | 57.3% | 63 |
| Buy and hold | 20.23% | -35.12% | 20.85% | 0.99 | 100% | 0 |

The more realistic cash-accrual variant reduced drawdown by about 9.2 percentage points, but surrendered roughly 11.7 percentage points of annualized return and produced a lower Sharpe ratio. Under zero-yield cash the CAGR gap was 12.5 points. SPY told the same story: 4.61% with effective-fed-funds cash versus 14.84% buy-and-hold. This is not a close call.

The adjusted-total-return MACD basis differs slightly from a conventional raw-price chart. For QQQ, **59 of 63** crossover dates matched exactly. Using raw-price MACD signals while still measuring adjusted investment returns produced 7.14% CAGR with zero cash and 7.92% with effective-fed-funds cash—still far below 20.23% buy-and-hold. The conclusion is not a dividend-adjustment artifact.

**Proposed practical use, not a validated result:** a weekly bearish cross can be treated as a yellow flag for reviewing leverage or demanding confirmation. Whether it adds incremental value beside breadth, QQQ/SPY and XLK/SPY relative trends, credit spreads/VIX, and defensive leadership remains a hypothesis for a joint walk-forward test. It should not be the sole permission either to exit or to buy.

### Current weekly state

| Asset | MACD | Signal | Histogram | Weekly RSI(14) | Histogram vs 13-week peak | Last bull / bear cross |
|---|---:|---:|---:|---:|---:|---|
| SPY | 21.12 | 19.29 | +1.83 | 65.6 | -73.9% | Apr. 24, 2026 / Nov. 21, 2025 |
| QQQ | 32.78 | 29.62 | +3.16 | 64.2 | -75.3% | Apr. 24, 2026 / Nov. 21, 2025 |

Momentum has decelerated sharply, but **both histograms remain positive**. That is a warning of cooling impulse, not a completed bearish crossover.

## 7. Where the cycle stands on July 12, 2026

### The apparent contradiction is a time-horizon problem

| Horizon through Jul. 10 | SPY | QQQ | XLK | XLV | XLP | XLU | What it says |
|---|---:|---:|---:|---:|---:|---:|---|
| 6 months | +9.8% | +16.4% | +26.9% | +1.2% | +10.4% | +9.2% | Technology remains the dominant intermediate trend. |
| 3 months | +11.0% | +18.9% | +30.8% | +7.7% | +0.8% | -3.7% | Still a tech regime, not broad defense. |
| Jun. 2–Jul. 10 | -0.4% | -2.7% | -6.2% | +10.4% | +3.5% | +4.1% | A genuine healthcare-led broadening/defensive probe. |
| Latest week | +1.4% | +1.8% | +2.9% | -1.8% | -1.0% | -0.8% | The defensive probe stalled as tech/semis rebounded. |

Calling the tape defensive from only the June 2–July 10 window would ignore both the massive March–June tech move and the latest weekly reversal. Calling it still purely tech-led would ignore the internal improvement in healthcare, financials, industrials, and equal weight. The most precise label is therefore:

> **Inflation-constrained rotational bull, with a real but unconfirmed defensive/broadening probe.**

### Evidence for broadening, not yet defense

- **Index trend is intact:** SPY and QQQ are 2.0% and 1.5% above their 50-day averages, and 9.0% and 13.9% above their 200-day averages. Their 52-week drawdowns are only -0.4% and -2.7%.
- **Breadth is healthy enough:** 69.0% of the 496 current members with a valid latest price and all 50 required observations are above their 50-day average; 67.7% of 495 fully eligible names are above their 200-day average. The full current-member snapshot contains 503 names. Current-membership history is survivorship-bound, so this is used only as a point-in-time cross-section.
- **The rotation is visible underneath the cap-weighted indices:** 93.2% of healthcare, 90.5% of financials with valid inputs, 87.1% of utilities, and 73.4% of industrials are above their 50-day averages, versus only 51.4% of technology and 36.4% of communications.
- **Credit is not signaling recession:** high-yield OAS was 2.70% and investment-grade OAS 0.76% on July 9 ([FRED HY](https://fred.stlouisfed.org/series/BAMLH0A0HYM2), [FRED IG](https://fred.stlouisfed.org/series/BAMLC0A0CM)).
- **Financial conditions are still loose:** the Chicago Fed NFCI was -0.515 on July 3, where negative values indicate looser-than-average conditions ([FRED](https://fred.stlouisfed.org/series/NFCI)).
- **Volatility is calm:** VIX closed 15.03 on July 10, far from a stress regime; Cboe explains that VIX reflects S&P 500 option-implied near-term volatility ([Cboe](https://www.cboe.com/tradable-products/vix/)).
- **But inflation/rates constrain duration:** the repo’s latest Treasury inputs, dated July 9, were 4.16% at two years and 4.54% at ten years ([Treasury](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=2026&type=daily_treasury_yield_curve)). Long duration is not receiving the clean disinflation tailwind of late 2023. The official July 10 row subsequently printed 4.21% and 4.56%; this does not change the classification.

This mixture is much closer to the **mid-2023 breadth catch-up**, **early-2024 reflation broadening**, or **early-2025 soft-landing broadening** than to the confirmed defenses of Q4 2018, the 2020 crash, 2022, or Feb.–Apr. 2025.

### Decision tree for the next regime

#### 1. Healthy rotational broadening — current base case

This remains the best interpretation if SPY holds its 50-day/10-week trend, equal weight improves versus cap weight, and XLF/XLI/XLV continue to gain relative strength while VIX and credit remain calm. Technology can consolidate or merely match SPY; it does not need to collapse. This path resembles mid-2023 and early 2024.

#### 2. Technology reacceleration

This gains confidence if QQQ, XLK, and SMH reclaim their June relative/absolute highs, technology breadth rises from 51.4% to above roughly 65% on the 50-day measure, and the weekly MACD histogram turns up without credit stress. The latest week—SMH +3.2%, XLK +2.9%, QQQ +1.8%—is the first hint, not confirmation.

#### 3. Confirmed defensive regime

Require persistence and corroboration, not one healthcare burst. The following are **monitoring heuristics, not thresholds validated by this study**:

1. the equal-weight XLV/XLP/XLU basket beats both SPY and XLK for at least four to six weeks;
2. at least two, preferably all three, show rising weekly relative trends;
3. QQQ/SPY and XLK/SPY make lower highs and lower lows;
4. SPY/QQQ lose their 50-day or 10-week trends rather than merely consolidating;
5. S&P 500 50-day breadth falls below 50%, with below 40% a stronger warning;
6. VIX sustains above roughly 20–25 and high-yield OAS widens through roughly 3.25%, then 4%; and
7. low volatility/quality beats high beta while financials and industrials stop broadening.

The first, price-leadership leg **did briefly trigger** on the June 2–July 10 endpoint: all three defensives beat SPY and XLK over roughly five and a half weeks. It was led overwhelmingly by healthcare, however, and the latest week reversed the trio’s leadership. More importantly, the relative index trend, breadth, credit, volatility, and cyclical-sector tests in items 3–7 did not corroborate systemic defense.

No single threshold is magic. The purpose is cross-domain confirmation, not a mechanically backtested gate. The historical failure mode is calling every utility or healthcare rally “defensive” even when it is actually yield relief, data-center capex, policy-specific healthcare repricing, or a healthy broadening episode.

#### 4. Inflation/scarcity shock rather than classic defense

If oil, the ten-year yield, and breakevens rise while XLU/XLRE fail, the likely winners are energy, selected materials, pricing-power quality, and perhaps healthcare—not the full defensive basket. Q1 2026 and 2022 are the templates. This distinction matters because buying rate-sensitive “defensives” into an inflation shock can compound the error.

### What could falsify the current call quickly

- A July CPI/earnings combination that sends yields higher, tech estimates lower, and credit wider would push the tape toward inflationary risk-off.
- Conversely, softer inflation with stable earnings could turn the June healthcare move into ordinary broadening and reignite duration/tech.
- A decisive payroll/claims deterioration with falling yields would favor the classic staples/utilities/healthcare defense.
- A QQQ price break without breadth or credit deterioration would be only a concentration correction, not necessarily an S&P bear regime.

## 8. Hard brainstorming: how to turn the study into a usable rotation process

The history argues against a single “tech ↔ defensives” switch. A better live framework has five independent lenses and an explicit evidence ladder.

### A five-lens regime state

1. **Trend:** SPY/QQQ/RSP/IWM versus 10-week and 40-week trends; weekly MACD state and slope.
2. **Relative leadership:** rolling 4-, 8-, and 13-week XLK, DEF, XLE, and broad-cyclical excess versus SPY. Use persistence, not one endpoint.
3. **Breadth/concentration:** percent above 50/200-day averages by sector; RSP/SPY, IWM/SPY, and share of sectors beating SPY.
4. **Macro transmission:** changes in real yields, curve, oil, dollar, and financial conditions. The change and covariance matter more than the absolute level.
5. **Stress:** VIX term structure, HY/IG spreads, HYG/TLT, and cross-asset drawdown. Defense without stress is usually broadening or rate relief.

### Classify the shock before choosing the hedge

| Shock type | Confirming tape | Likely beneficiaries | Bad shortcut |
|---|---|---|---|
| Growth scare / disinflation | Yields down, oil down, spreads wider, XLP/XLU outperform | Staples, utilities, healthcare quality, long duration after confirmation | Buying energy because it was last year’s winner |
| Inflation/scarcity | Yields/oil up, duration down, XLE/XLB strong | Energy, materials, pricing power, selected healthcare | Assuming all defensives protect |
| Liquidity/policy easing | Yields down, spreads stable/tighter, breadth improving | Tech, discretionary, REITs, then cyclicals | Exiting risk because utilities also rally |
| Earnings concentration | QQQ/SMH up, equal weight flat, credit calm | Tech/communications; disciplined position sizing | Treating narrow breadth as an immediate crash signal |
| Recovery/reflation | Curve steepens, credit calm, RSP/IWM improve | Financials, industrials, materials, energy | Calling cyclical leadership late-stage defense |

### A practical evidence ladder (proposed heuristic, not backtested authority)

- **Observation:** one week of new leadership. Log it; do not promote it.
- **Probe:** two to four weeks, at least two related sectors, improving relative trend.
- **Confirmed rotation:** four to six weeks plus breadth and macro/stress agreement.
- **Regime:** persistent leadership across 8–13 weeks and material change in index/risk behavior.

This would have kept the July–September 2024 REIT/utility handoff distinct from a bear market, treated the 2025 tariff episode as genuine defense, and prevented a June 2026 healthcare burst from being prematurely promoted to full defensive authority.

### Hypotheses for better use of weekly MACD (not yet validated)

- Test **histogram deterioration** as a position-sizing input before a cross, not as proof of overbought conditions.
- Test whether a bearish cross adds information conditional on breadth and credit—for example, when fewer than 40–50% of members are above 50-day trend and HY spreads are widening.
- Test bullish crosses below zero after a material drawdown separately from shallow whipsaws above zero—but note that this study has only five QQQ below-zero bullish events.
- Test a three-state allocator—full risk, reduced risk, defense/cash—rather than a binary 100% QQQ/100% cash rule.
- Add a **minimum bear-state duration** or two-week confirmation to reduce whipsaw, then validate out of sample. Do not optimize on this same 2013–2026 window and call it discovered alpha.

### Best next research extensions

1. **Point-in-time sector breadth and constituents:** removes survivorship bias and allows honest historical breadth triggers.
2. **Flow confirmation:** ETF creations/redemptions, CFTC positioning, options skew, and mutual-fund flows can test whether revealed relative returns correspond to actual capital movement.
3. **Macro-conditioned sector matrix:** estimate sector excess by joint real-yield, inflation-surprise, growth-surprise, oil, and credit states instead of calendar month.
4. **Walk-forward regime classifier:** set definitions on an earlier training window, freeze them, and evaluate later years with transaction costs.
5. **Sub-industry decomposition:** XLV can hide biotech versus managed care versus pharma; XLK can hide semis versus software. The broad ETF is sometimes too blunt for the causal story.
6. **International and size cross-check:** compare S&P 500 sectors with Russell 2000, equal weight, Europe, and emerging markets to distinguish U.S. mega-cap concentration from a global regime.

## 9. Reproducibility, artifacts, and limitations

### Canonical files

- **Narrative decision memo:** `research/SP500_NASDAQ_REGIME_ROTATION_ATLAS_2013_2026.md`
- **Rebuild script:** `scripts/research/sp500_nasdaq_regime_rotation_study.py`
- **Machine-readable pack:** `research/artifacts/sp500_nasdaq_regime_rotation_2013_2026/`
- **Method contract:** `research/artifacts/sp500_nasdaq_regime_rotation_2013_2026/methodology.json`

The artifact pack contains annual, monthly, quarterly, regime-span, cross-year, defensive-conditional and beta-decomposition, election-cycle, seasonality, MACD-event, MACD-strategy and price-basis robustness, current-market, current-breadth, and current-macro tables. This memo rounds for readability; the CSVs retain full precision.

### Material limitations

1. **Endpoint dependence:** an ex-post span can make leadership look cleaner than it felt in real time. Max drawdowns are retained in the CSV to expose path risk.
2. **ETF proxy limits:** QQQ is Nasdaq-100, not the full Composite; sectors have fees and tracking error. XLC/XLRE history and GICS migrations create structural breaks.
3. **No direct flow data:** “capital rotated” is inferred from relative returns. This is revealed preference, not a fund-flow identity.
4. **Small samples:** 13 modern observations per calendar month and only 3 modern/6 expanded-history midterm years. The expanded sample overlaps the modern window; independent 1999–2012 results are shown separately. Multiple-testing adjustment is essential.
5. **MACD overlap:** forward-event windows overlap and serial dependence inflates apparent precision. The continuous strategy result is therefore given more weight.
6. **Breadth survivorship:** the July 2026 constituent breadth snapshot uses current membership and is not used to backtest historical signals.
7. **Current data revisions:** GDP, payrolls, PCE, and other macro releases can be revised. The point-in-time conclusion uses the latest repo snapshot available on July 12, 2026.
8. **Not investment advice:** this is historical regime research and a decision framework, not a personalized allocation recommendation.

### Reproduction command

```bash
/Users/chriswong/Documents/Cluade/Macro\ Dashboard/.venv/bin/python \
  scripts/research/sp500_nasdaq_regime_rotation_study.py
```

The script is deterministic given the repository data snapshot: fixed event definitions, a fixed permutation seed, next-session-close event and strategy execution, explicit zero-yield/effective-fed-funds cash variants, and explicit transaction costs.

## Bottom line

The 2013–2026 tape does rotate repeatedly between technology and defense, but that is only one slice of the cycle. The more durable pattern is **shock transmission**:

- weak growth plus falling yields → staples/utilities/healthcare preservation;
- falling yields plus stable credit → technology/REIT duration rally;
- inflation/scarcity → energy/materials and sometimes financials;
- improving growth plus calm credit → industrial/financial/material breadth;
- strong secular earnings → concentrated Nasdaq/semiconductor leadership.

As of July 12, 2026, June delivered a credible healthcare-led handoff after an extreme Q2 tech run. It has not yet crossed the evidence ladder from **probe** to **confirmed defensive rotation**. The latest week favored technology again, the weekly MACD remains bullish, about two-thirds of S&P members with valid inputs remain above 50- and 200-day trends, VIX is near 15, and credit spreads are tight. The correct posture is to monitor the rotation—not to declare the Nasdaq cycle over.
