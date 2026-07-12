# Risk-On Regime Shift Postmortem — 2026-06-29 to 2026-07-08

Prepared July 12, 2026.

Status: private research memo. This is an event reconstruction, not financial advice or a claim that the rally is durable. Market data and policy status should be refreshed before a trading decision.

Epistemic convention:

- **Observed:** dated prices, flows, official releases, balance-sheet data, and company disclosures.
- **Causal inference:** an explanation supported by timing, mechanism, and cross-asset confirmation, but not directly observable as a counterfactual.
- **Rejected:** an explanation contradicted by timestamp, breadth, flows, policy records, or cross-asset behavior.

Scope boundary: this memo complements the broader forward-looking `research/SECOND_ACT_NOTE.md`. It is the canonical forensic reconstruction of the June 29-July 8 event, not a replacement for that longer cycle thesis.

## 0. Executive ruling

There was no single June 29 Federal Reserve pivot, White House stimulus plan, or hidden US-China bargain that suddenly turned every market risk-on.

The reversal happened in three stages:

1. **June 26-29 floor:** the US-Iran/Hormuz tail risk stopped worsening at the same time that quarter-end, index-reconstitution, hedge-fund, CTA, and options-related selling was reaching exhaustion.
2. **June 30-July 7 stabilization:** Treasury cash spending temporarily released a large amount of reserve liquidity; weak payrolls reduced immediate Fed-hike risk; China supplied funding support and explicit AI-policy direction; July allocation seasonality began.
3. **July 8-10 acceleration:** Alibaba, Nvidia, Apple, and Meta received different company- or policy-specific catalysts. Lighter positioning, low spot volatility, short covering, and options/systematic chasing magnified those moves.

The first-principles answer is:

> A market bottom does not require every problem to be solved. It requires the marginal seller to run out, the probability of disaster to fall, and enough liquidity or standing demand to absorb the remaining supply.

That is what changed around June 29. The later “god candles” were confirmations and accelerants, not the original common cause.

## 1. Tape correction: the move was not one synchronized bottom

The premise needs two corrections.

First, Alibaba 9988.HK made its actual low on **June 26**, not June 29. June 29 was its first forceful reversal day.

Second, broad semiconductors did not bottom on June 29. The semiconductor ETFs continued falling through **July 7**. Nvidia was an important positive divergence from a still-weak group.

| Asset | Actual local floor | June 29 | July 8 | What the sequence says |
|---|---:|---:|---:|---|
| Alibaba 9988.HK | Jun 26 low HK$88.65 | Close HK$93.00, +3.91% | Close HK$107.50, +12.21% | Capitulation first; later earnings/flow reprice |
| Alibaba ADR | Jun 26 low $91.99 | Close $95.51 | Close $108.98, +11.05% | Same company reset in US hours |
| Nvidia | Jun 29 low $189.80 | Close $194.97, +1.27% | Close $204.12, +3.65% | Stock-specific divergence, then China optionality |
| SOXX | Jun 26-June 29 floor area | Close $614.35 | +1.87% on the day | Fell to $551.69 on Jul 7; no Jun 29 group bottom |
| SMH | Jun 26 close $611.61 | +3.33% | +1.99% | Jul 10 close $611.03 was still roughly flat vs Jun 26 |
| Apple | Jun 25 low $273.75 | -0.72% | Near record territory | Different bottom and different catalyst chain |
| Meta | Jun 25 low $540.18 | +2.24% | Not the decisive day | Jul 1 and Jul 9-10 were its real catalyst days |
| SPY | Jun 26 low/close zone | +1.65% | -0.31% | Common macro floor, but Jul 8 was not broad risk-on |
| Hang Seng | Jun 26 low/close zone | +1.57% | +2.99% | HK rebound broadened later than the floor |

Price references: [9988.HK](https://stockanalysis.com/quote/hkg/9988/history/), [Nvidia](https://stockanalysis.com/stocks/nvda/history/), [Apple](https://stockanalysis.com/stocks/aapl/history/), [Meta](https://stockanalysis.com/stocks/meta/history/), and [SMH](https://stockanalysis.com/etf/smh/history/).

Data-vendor note: some HK feeds print the July 8 Alibaba close at HK$107.80 rather than HK$107.50. This memo uses the linked price-history convention; the roughly 12% move and causal conclusion are unchanged.

### Breadth proves this was selective

The local breadth feed does not show a broad all-clear:

| Date | Advancers | Decliners | Tape interpretation |
|---|---:|---:|---|
| Jun 26 | 322 | 178 | Capitulation/rebound participation beginning |
| Jun 29 | 231 | 270 | Index rally with negative breadth |
| Jun 30 | 212 | 289 | Another narrow index-led session |
| Jul 2 | 355 | 145 | Best genuine broad participation day in the sequence |
| Jul 8 | 111 | 390 | Highly selective winners despite broad weakness |

On July 8, mainland Chinese benchmarks also declined while Hang Seng Tech rose about 5% and Alibaba rose 12.2%. That is rotation into cheap Hong Kong internet exposure, not proof of a broad Chinese growth boom. [Reuters Hong Kong market report](https://www.indopremier.com/ipotnews/newsDetail.php?group_news=IPOTNEWS&jdl=Hong+Kong+stocks+surge+as+dip-buyers+emerge%2C+mainland+benchmarks+at+one-month+low&news_id=223656)

## 2. What created the risk-off setup before the bottom

The June decline combined six different pressures. Their overlap made the selling look like one macro signal even though the mechanisms were different.

### 2.1 Hormuz, oil, freight, and inflation risk

Renewed US-Iran strikes, attacks on vessels, and uncertainty about passage through the Strait of Hormuz raised the probability of another oil and freight shock. Higher energy prices fed directly into inflation expectations and Fed-hike pricing.

### 2.2 A hawkish Fed repricing

The June FOMC held the target rate at 3.50%-3.75%, but the meeting and projections kept an additional hike in play. That hurt long-duration and crowded growth equities.

### 2.3 An overcrowded AI/memory trade

Semiconductors and memory had experienced extraordinary first-half gains. Retail options activity, leveraged ETF exposure, hedge-fund concentration, and momentum positioning made the group vulnerable to de-grossing even if end demand remained intact.

### 2.4 First evidence of AI-capex digestion

Investors were asking whether inference efficiency, custom silicon, cloud-capacity monetization, and customer concentration would slow purchases from Nvidia and memory suppliers. The concern was legitimate even though it had not yet become a confirmed demand collapse.

### 2.5 Alibaba-specific negative-news stacking

Alibaba absorbed the [Pentagon Chinese military-company designation](https://media.defense.gov/2026/Jun/08/2003945537/-1/-1/1/ENTITIES-IDENTIFIED-AS-CHINESE-MILITARY-COMPANIES-OPERATING-IN-THE-UNITED-STATES-IN-ACCORDANCE-WITH-SECTION-1260H.PDF), its legal challenge, [Anthropic’s model-distillation allegation](https://www.investing.com/news/stock-market-news/anthropic-says-alibaba-illicitly-extracted-claude-ai-model-capabilities-4759021), weak 618 shopping data, e-commerce regulation, instant-commerce subsidy losses, and fear that AI capex was not producing enough profit.

### 2.6 Quarter-end forced selling

Pension rebalancing, CTA reductions, hedge-fund de-grossing, options expiry, and the Russell reconstitution concentrated supply into the final sessions of June.

The important conclusion is that the selloff mixed **fundamental uncertainty** with **mechanical selling**. Once the mechanical component exhausted and the geopolitical probability distribution improved, prices could reverse before every fundamental question was answered.

## 3. Stage one — June 26-29: capitulation and geopolitical relief

### 3.1 The cleanest common trigger was the US-Iran stand-down

On June 28, the United States and Iran agreed to halt their renewed attacks, continue technical discussions, and allow vessels to move through the Strait of Hormuz. That news arrived before the June 29 trading day and reduced the immediate probability of another oil, shipping, and military escalation. [Reuters account](https://www.investing.com/news/world-news/us-carries-out-fresh-strikes-against-iran-after-tanker-struck-in-hormuz-escalating-hostilities-4764056)

This was the best common explanation for simultaneous relief across US equities, Hong Kong, China, oil-sensitive assets, and volatility.

It was not a permanent peace agreement. It was a reduction in the near-term disaster probability. Markets price that probability change immediately.

### 3.2 Mechanical supply was clearing at quarter-end

The 2026 Russell reconstitution became effective at the June 29 open after a record approximately $553.9 billion traded in the June 26 closing auction. The event created large, non-discretionary transfers between index buyers and sellers. It should be interpreted as a supply-clearing event, not a directional fundamental signal. [FTSE Russell summary](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/2026-russell-us-indexes-reconstitution-summary.pdf), [closing-auction report](https://www.tradersmagazine.com/departments/equities/june-russell-reconstitution-concludes-with-record-553-9-billion-traded-at-the-close/)

Citadel Securities’ July flow outlook also described temporary quarter-end pension selling, the start of fresh monthly/quarterly allocations on July 1, heavy retail and leveraged semiconductor exposure, and historically strong first-half July seasonality. [Citadel Securities July flow outlook](https://www.citadelsecurities.com/news-and-insights/global-market-intelligence/july/)

Its historical framing put the S&P 500’s first half of July positive about 69% of the time since 1928, with an average gain near 1.5%, and the Nasdaq 100 positive about 76% of the time since 1985, with an average gain near 2.2%. Seasonality was an amplifier after the floor, not the cause of the floor.

The causal interpretation is:

- Quarter-end selling did not make prices bullish.
- It transferred inventory and lightened books.
- Once a positive geopolitical headline arrived, fewer investors remained forced to sell.
- Lighter CTA and hedge-fund positioning created more room for upside chasing.

### 3.3 Volatility fell, but investors kept protection

VIX fell from 18.41 on June 26 to 17.65 on June 29 and continued toward 15 by July 10. Meanwhile, the local SKEW series rose from 139.4 on June 26 to 149.6 on June 30 and above 154 on July 1.

That combination means investors were buying spot risk while retaining tail insurance. It was a **risk-on-with-protection** regime, not an all-clear.

Narrative sentiment had also been repairing before the reversal. The local FRBSF news-sentiment series moved from -0.033 on June 18 to +0.016 on June 26, +0.050 on June 29, +0.067 on July 2, and +0.100 on July 5. The improvement preceded the largest candles, supporting a gradual probability reset rather than a single July 8 headline shock.

### 3.4 Credit never confirmed a systemic crisis

US high-yield option-adjusted spreads were approximately 2.83% on June 26, 2.80% on June 29, and 2.67% by July 7. The National Financial Conditions Index remained loose, and the OFR Financial Stress Index stayed deeply negative/calm.

Because credit and funding markets were not breaking, the equity selloff did not have a self-reinforcing balance-sheet or default mechanism. That allowed a fast rebound once equity supply exhausted. [FRED high-yield OAS](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)

### 3.5 Alibaba created a standing buyer exactly at the reversal

Before June 29, Alibaba was repurchasing roughly 0.95-1.06 million ordinary-share equivalents per day, or about $12.5 million.

On June 29, the company increased the purchase to **4.20348 million ordinary-share equivalents for $49.994 million**. It continued buying at roughly $50 million per day through the early-July grind. [Alibaba HKEX disclosure](https://www.hkexnews.hk/listedco/listconews/sehk/2026/0630/2026063001808.pdf)

This was not enough to manufacture the entire rally, but it mattered at the margin:

- The stock had already fallen roughly 27% in a month.
- Negative-news sellers were becoming exhausted.
- The company introduced a credible, persistent absorber of supply.
- The accelerated buyback signalled management’s assessment that the selloff had become excessive.

### 3.6 What did not cause the initial Alibaba reversal

Southbound Connect was a large net outflow on June 29. Mainland investors were still selling while Alibaba rose.

That is strong evidence that mainland flows did not create the bottom. The stock first rose by absorbing forced selling; mainland money became an accelerator only from July 6 onward.

## 4. Stage two — June 30-July 7: liquidity and policy stabilization

### 4.1 Treasury cash spending released temporary reserve liquidity

The Treasury General Account moved approximately as follows in the local official-source feed:

| Date | TGA balance | Liquidity implication |
|---|---:|---|
| Jun 29 | $876.96B | Already below the prior-week level |
| Jun 30 | $919.15B | Quarter-end rebuild/spike |
| Jul 1 | $807.36B | Large cash release into the private system |
| Jul 2 | $770.59B | About $149B below Jun 30 |
| Jul 7 | $784.96B | Still materially below quarter-end |
| Jul 9 | About $744.6B | Roughly $175B below Jun 30 |

When Treasury spends from its account at the Federal Reserve, the money generally lands in private deposits and bank reserves. This improves market plumbing even when the Fed itself does nothing.

The local canonical net-liquidity proxy rose by roughly $162 billion from June 30 to July 2. Almost all of that improvement came from the TGA drawdown and quarter-turn RRP mechanics.

This was **not QE**:

- Fed assets fell by about $11 billion from June 24 to July 1.
- ON RRP usage briefly spiked at quarter-end and then collapsed back near $1 billion.
- The move was a Treasury cash-flow effect, not a new central-bank asset-purchase program.

Official references: [Federal Reserve H.4.1](https://www.federalreserve.gov/releases/h41/) and [Treasury Quarterly Refunding statement](https://home.treasury.gov/news/press-releases/sb0489).

The distinction matters because Treasury projected that the TGA could rebuild toward **$1 trillion plus or minus $50 billion in late July**. A rebuild would withdraw some of the same liquidity that supported the early-July rebound.

### 4.2 The Fed became less threatening at the margin, not dovish

The June FOMC minutes showed:

- Inflation remained elevated.
- Risks to inflation were skewed upward.
- A few participants saw a case for raising rates.
- Many participants expected the appropriate year-end rate to be above the current range.

That is inconsistent with a June 29 Fed-pivot explanation. [Official June FOMC minutes](https://www.federalreserve.gov/monetarypolicy/files/fomcminutes20260617.pdf)

The marginal relief arrived on July 2 when payrolls increased by only 57,000, participation fell to 61.5%, and April-May payrolls were revised down by a combined 74,000. Markets reduced the probability of an immediate July hike without immediately pricing a recession. [Official BLS report](https://www.bls.gov/news.release/archives/empsit_07022026.htm)

The correct label is **less hawkish at the margin**, not easing.

The strongest cross-asset falsifier is that the 10-year Treasury yield rose from roughly 4.38% on June 29 to 4.56% on July 8. Nvidia rallied despite a higher discount rate.

### 4.3 China prevented funding stress from compounding the selloff

The PBOC used an overnight reverse-repo facility and other operations to smooth half-year-end liquidity. The June 29 operation was not a stimulus bazooka; after maturities, the net daily effect was close to flat/slightly draining. Its importance was as a funding backstop and signal that the PBOC would not allow a calendar squeeze to become disorderly. [Contemporaneous PBOC operation report](https://www.marketscreener.com/news/china-central-bank-conducts-overnight-reverse-repos-again-keeps-rate-at-1-25-sources-say-ce7f5fdfde81f123)

Hong Kong funding also eased:

| Measure | Jun 29 | Jul 8 | Interpretation |
|---|---:|---:|---|
| 1-month HIBOR | About 2.95% | About 2.69% | Lower local funding pressure |
| HK Aggregate Balance | Roughly HK$54B | Roughly stable | No emergency peg intervention |
| USD/HKD | Near weak-side zone | Only modestly firmer | No dramatic FX inflow at the bottom |

The funding channel removed a possible accelerant to the selloff. It did not by itself create a bull market.

### 4.4 China’s macro data stopped deteriorating

China’s June manufacturing PMI improved to 50.3, with production at 51.4 and new orders at 51.2. This weakened the immediate hard-landing narrative without proving that domestic consumption or property had fully recovered. [National Bureau of Statistics](https://www.stats.gov.cn/english/PressRelease/202607/t20260701_1964047.html)

### 4.5 Beijing supplied explicit AI-policy direction

The June 29 State Council meeting, released June 30, called for:

- Faster breakthroughs in key AI technologies.
- Ultra-large-scale intelligent-computing clusters.
- Greater talent and funding support.
- Large-scale commercial deployment of AI products and services.

This announcement arrived after the June 29 Hong Kong session, so it reinforced continuation rather than causing the initial bottom. It was nevertheless directly relevant to Alibaba’s cloud/AI valuation. [China State Council](https://english.www.gov.cn/news/202606/30/content_WS6a430b6ac6d00ca5f9a0be11.html)

### 4.6 Mainland flows finally changed direction

The local Southbound Connect feed shows the sequence clearly:

| Date | Net flow, RMB mn (collector convention) | Interpretation |
|---|---:|---|
| Jun 26 | -2,503.8M | Selling into the low |
| Jun 29 | -10,338.8M | Large outflow despite reversal |
| Jun 30 | +5,895.2M | First positive response |
| Jul 3 | +4,537.8M | Gradual confirmation |
| Jul 6 | +20,527.8M | Hot inflow; acceleration begins |
| Jul 7 | +497.2M | Pause before the impulse |
| Jul 8 | +14,194.4M | Strong confirmation/amplification |

The causal order is therefore:

**price bottom and buyback absorption first -> mainland flow reversal second -> explosive acceleration third.**

### 4.7 The July 7 Hong Kong package strengthened the policy floor

The PBOC, HKMA, and SFC announced measures to expand Hong Kong’s fixed-income, collateral, Bond Connect, and offshore-RMB infrastructure. The HKMA RMB Business Facility increased from RMB200 billion to RMB500 billion effective July 10. [HKMA announcement](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2026/07/20260707-3/)

This was mainly an offshore-RMB and fixed-income initiative, not a direct order to buy internet equities. Its market significance was the policy signal: Beijing wanted Hong Kong to remain a stronger financing and capital-market hub.

## 5. Why the semiconductor rollover did not become a fundamental collapse

The broad semiconductor rollover did continue after June 29. What changed was that investors received evidence against the most extreme demand-collapse scenario.

### 5.1 Memory demand remained structurally strong

Micron reported that customers had made approximately $22 billion of commitments to secure memory supply, with demand still exceeding supply and tightness expected beyond 2027. [Reuters memory-demand report](https://www.marketscreener.com/news/south-korean-chip-shares-surge-after-micron-flags-strong-ai-related-demand-ce7f5fd8d88ef420)

On June 29, Samsung, SK Hynix, and South Korea’s government announced a roughly $518 billion, four-fab semiconductor hub in response to rising AI demand and limited capacity. [AP semiconductor-hub report](https://apnews.com/article/korea-samsung-ai-hynix-chips-22352d95c7a821c5f4548b2d1a4ebde8)

These facts did not guarantee that semiconductor stocks were cheap. They did weaken the claim that the physical AI demand cycle had already collapsed.

### 5.2 The selloff was partly a crowding correction

Hedge funds had net-sold US technology hardware and semiconductors for four consecutive weeks. CTA exposure had also been materially reduced. Once positioning is lighter, positive news produces a larger percentage price response because investors must rebuild exposure rather than merely add to an already full book. [Reuters hedge-fund positioning report](https://www.investing.com/news/stock-market-news/hedge-funds-dumped-chip-stocks-for-a-fourth-week-as-ai-shares-sold-off-4776190)

### 5.3 Nvidia separated from the group

Nvidia’s June 29 low and July 8 breakout were not proof that every memory or semiconductor name had bottomed. Nvidia gained a direct China revenue option while other semiconductor companies still faced inventory, pricing, customer-mix, or capex-digestion questions.

That distinction explains how Nvidia could rally while SOXX/SMH remained below their June 29 levels.

## 6. Stage three — July 8-10: separate catalysts produced the “god candles”

### 6.1 Alibaba: the July 8 Hong Kong catalyst was earnings-expectation relief

A media-reported pre-earnings briefing indicated that:

- Instant-commerce losses narrowed faster than expected.
- Overall profitability remained intact.
- Alibaba Cloud growth accelerated.
- The company was consolidating its enterprise AI-agent product line.

This was preliminary reporting rather than an audited filing. Nevertheless, it attacked the two largest company-specific fears:

1. Quick-commerce subsidies would permanently destroy earnings.
2. AI capex would produce growth but no visible profit bridge.

The stock rose 12.2% in Hong Kong on approximately 2.9 times its recent median volume. [Contemporaneous Alibaba report](https://www.investing.com/news/stock-market-news/why-is-alibaba-stock-surging-today-93CH-4780851)

The move was magnified by:

- Roughly $300 million of cumulative company repurchases from June 29 through July 7.
- Strong Southbound inflows on July 6 and July 8.
- Rotation from crowded Korean/Taiwan semiconductor winners into cheaper Hong Kong internet names.
- Heavy short and underweight positioning.

### 6.2 The H200 report did not cause the Hong Kong candle

The report that Beijing was preparing to allow Alibaba, ByteDance, and DeepSeek to buy a limited number of Nvidia H200 accelerators arrived during US trading, after Hong Kong had closed.

It therefore cannot explain 9988.HK’s initial July 8 surge.

It did provide a powerful cross-market confirmation:

- Nvidia gained China revenue optionality that was excluded from guidance.
- Alibaba gained potential access to scarce, high-end compute.
- The report confirmed that Chinese AI demand remained constrained by supply and policy, not absent.

[Reuters H200 report](https://www.investing.com/news/stock-market-news/china-plans-to-let-top-ai-firms-buy-limited-amount-of-nvidia-h200-chips-the-information-reports-4782000)

### 6.3 The US administration did not create a new H200 regime on July 8

The Trump administration had already announced controlled H200 exports, and Commerce moved the relevant chips to case-by-case license review on January 13, 2026. By May, the United States had reportedly cleared several Chinese buyers, but Beijing had withheld purchase approval.

The July 8 change was the **China-side gate beginning to open**, not a new same-day White House action. [Official Commerce/BIS framework](https://media.bis.gov/press-release/department-commerce-revises-license-review-policy-semiconductors-exported-china)

Adjacent-report reconciliation: any earlier repo statement treating H200 deliveries to China as completely frozen describes the pre-July 8 state. This memo updates that state to **reported limited permission under discussion**—not confirmed shipments or realized Nvidia revenue.

### 6.4 Nvidia: direct revenue optionality hit a compressed valuation

Nvidia entered July 8 near approximately 18 times forward earnings, reported as a seven-year valuation low. BofA reiterated a Buy rating and $350 target while the H200 report introduced upside optionality to a base case that excluded China data-center compute revenue. [Valuation context](https://news.bloomberglaw.com/artificial-intelligence/nvidias-1-trillion-slide-sends-valuation-to-pre-ai-boom-levels), [BofA rating summary](https://www.benzinga.com/markets/equities/26/07/60326448/is-nvda-stock-a-buy-bofa-says-tech-giants-massive-moat-is-completely-unappreciated-sees-78-upside)

The stock also crossed the psychologically important $200 area. Heavy short-dated call activity around $205-$210 plausibly caused dealer hedging to amplify the breakout, but dealer positioning cannot be observed directly. Gamma amplification should therefore be treated as an inference, not the primary cause.

### 6.5 July 8 was not a broad macro risk-on day

On July 8:

- Trump declared the Iran ceasefire over.
- Oil rose roughly 6%.
- Treasury yields rose.
- Broad US stocks declined.
- Local US breadth was 111 advancers versus 390 decliners.
- Mainland Chinese benchmarks declined.

Nvidia and Alibaba rose through deteriorating macro conditions. That is strong evidence that their moves were stock/AI-policy specific. [AP geopolitical update](https://apnews.com/article/72181b48494a6367c40cf6e9a817e6b4)

## 7. Apple and Meta were different trades

Their rallies reinforced the AI-capex monetization narrative, but neither shared Alibaba’s exact bottom or Nvidia’s exact catalyst.

### 7.1 Apple

Apple’s actual low was June 25 after large Mac, iPad, and home-device price increases raised fears about memory costs, margins, and consumer demand. The stock rebounded as analysts interpreted the price increases as margin protection and pricing power rather than pure demand destruction.

The July 8 Apple/Broadcom announcement added a new catalyst:

- A multiyear commitment expected to exceed $30 billion.
- More than 15 billion US-made chips.
- A $1.5 billion expansion of Broadcom’s Fort Collins facility.
- Explicit alignment with Apple’s $600 billion US investment commitment.

This improved long-term component supply visibility and aligned Apple with the administration’s domestic-manufacturing agenda. A reduction in tariff/political risk is a reasonable inference, but it was not an announced market subsidy. [Apple’s official announcement](https://www.apple.com/newsroom/2026/07/apple-to-increase-spend-with-broadcom-to-produce-billions-more-us-chips/)

### 7.2 Meta

Meta’s important catalyst days were July 1 and July 9-10:

- July 1: reports that Meta was exploring the sale of cloud compute and model access, creating a possible external revenue stream from its AI infrastructure.
- July 9-10: paid model/API developments, a reported September production start for its custom AI chip, and plans to expand compute capacity toward 14 GW in 2027.

The market interpretation changed from “capex is a cost” to “some of this infrastructure may become a revenue-bearing asset.” [Axios Meta cloud report](https://www.axios.com/2026/07/01/meta-cloud-mark-zuckerberg), [TechCrunch custom-chip report](https://techcrunch.com/2026/07/09/metas-new-ai-chips-will-begin-production-in-september/)

## 8. Actor ledger: what the Fed, administration, Treasury, and China actually did

| Actor | Action | Timing | Market role | What it was not |
|---|---|---|---|---|
| White House / US diplomacy | June 28 US-Iran stand-down and renewed talks | Before Jun 29 open | Primary common macro trigger | Permanent peace agreement |
| US Treasury | TGA spend-down after quarter-end | Jun 30-Jul 9 | Large temporary reserve-liquidity tailwind | QE or a new stimulus bill |
| Federal Reserve | Held 3.50%-3.75%; ample-reserve operations | Jun 17 onward | Less threatening only after soft jobs | Dovish pivot or rate cut |
| Supreme Court | [Rejected immediate removal of Fed Governor Lisa Cook](https://www.supremecourt.gov/opinions/25pdf/25a312_5468.pdf) | Jun 29 | Small reduction in Fed-independence risk | Main cause of the open-to-close rally |
| US Commerce | Existing H200 case-by-case licensing framework | Jan-May 2026 | Created a policy option later monetized | New Jul 8 US action |
| PBOC | Half-year funding operations and liquidity smoothing | Jun 25-Jul 6 | Prevented calendar/funding stress | Giant equity stimulus |
| China State Council | AI clusters, technology, talent, funding, commercialization direction | Jun 29 meeting; Jun 30 release | Reinforced China AI valuation | Cause of Jun 29 intraday HK reversal |
| PBOC/HKMA/SFC | Hong Kong/offshore-RMB package | Jul 7 | Confidence and financing-hub signal | Direct internet-stock purchase order |
| Beijing | Reported limited H200 purchase approval | Jul 8 US hours | Linked Nvidia revenue to Chinese compute demand | Cause of 9988.HK’s already-completed Jul 8 session |
| Alibaba | Accelerated buybacks and reported better commerce/cloud trajectory | Jun 29-Jul 8 | Direct standing demand and earnings reset | Broad China macro rescue |
| Apple / Meta | Supply-chain and AI-monetization announcements | Jul 1-Jul 10 | Separate cash-flow catalysts | Evidence of a Fed-led rally |

## 9. Causal-confidence scorecard

| Candidate explanation | Role | Confidence | Evidence |
|---|---|---:|---|
| US-Iran/Hormuz stand-down | Common June 29 trigger | High | Correct timestamp; oil/volatility response; broad international relief |
| Quarter-end/Russell/options supply exhaustion | Floor amplifier | High | Record close, effective-date timing, known rebalance flows |
| Treasury TGA drawdown | Continuation liquidity | High | Direct official balance data; reserve-mechanics channel |
| Alibaba accelerated buyback | BABA-specific absorber | High | Official disclosure; exact timing |
| Soft June payrolls | Reduced near-term hike tail | High | Official July 2 release; market repricing |
| China AI/compute policy | China-tech continuation support | High | Official Jun 29 meeting released Jun 30 |
| Southbound flow reversal | Jul 6-8 accelerator | High | Initial outflow, later strong inflows |
| Alibaba commerce/cloud briefing | Jul 8 HK micro catalyst | Medium-high | Correct timing and fear-removal mechanism; not audited |
| Beijing H200 approval | Jul 8 US-session NVDA/BABA confirmation | High | Direct revenue/compute link; after-HK-close timestamp |
| July seasonality and fresh allocations | Amplifier | Medium-high | Strong historical/flow prior, but not sufficient alone |
| CTA/vol-control/gamma chasing | Price-move amplifier | Medium | Mechanically plausible; exact dealer/systematic sign unobservable |
| Supreme Court Fed-independence ruling | Secondary sentiment help | Medium-low | Supportive, but late and inconsistent with higher yields |
| Secret Fed/administration plan | Claimed common cause | Rejected | No matching announcement or cross-asset confirmation |

## 10. Explanations that the evidence rejects

### 10.1 “The Fed pivoted on June 29”

Rejected. The Fed held rates, June minutes remained inflation-focused, some officials discussed hikes, and Treasury yields rose into July 8.

### 10.2 “The Fed printed money or restarted QE”

Rejected. Fed assets fell slightly into July 1. The liquidity improvement came primarily from Treasury cash spending and quarter-turn RRP movements.

### 10.3 “A new administration stimulus plan was released June 29”

Rejected. The relevant administration action was geopolitical—the Iran stand-down—not a new broad fiscal, tariff, or equity-market stimulus program.

### 10.4 “Mainland investors rescued Alibaba at the bottom”

Rejected. Southbound flows were strongly negative on June 29. Mainland buying followed the price reversal and became powerful on July 6 and July 8.

### 10.5 “Every semiconductor bottomed June 29”

Rejected. Broad semiconductor ETFs fell sharply through July 7. Nvidia was a positive divergence and later received a direct catalyst.

### 10.6 “The H200 report caused 9988.HK’s July 8 candle”

Rejected by timestamp. The report arrived after Hong Kong closed. It reinforced the ADR and Nvidia later.

### 10.7 “July 8 was global risk-on”

Rejected. Oil and yields rose, the Iran ceasefire broke down, broad US breadth was negative, US indices weakened, and mainland China fell.

## 11. The deeper mechanism

The observed sequence can be expressed as a causal chain:

```text
Oil/Hormuz tail risk falls
        +
Quarter-end and index-rebalance sellers finish
        +
Credit remains calm; no systemic contagion
        ↓
June 26-29 floor
        +
Treasury cash spending releases reserves
        +
Soft jobs reduce immediate hike risk
        +
China funding and AI policy stabilize expectations
        ↓
July 1-7 persistence and lighter positioning
        +
Alibaba earnings-expectation relief
        +
H200 optionality for Nvidia and Chinese hyperscalers
        +
Apple supply/onshoring and Meta monetization news
        ↓
Short covering, options chase, systematic re-risking
        ↓
July 8-10 concentrated “god candles”
```

The common underlying factor was not “the Fed turned dovish.” It was a shift from **accelerating tail risk plus forced selling** to **reduced tail risk plus available liquidity**, followed by separate company catalysts.

## 12. Regime judgment

The correct regime label is:

> **Narrow liquidity-and-catalyst reprice with high dispersion—not yet a fully confirmed broad risk-on regime.**

Evidence supporting a genuine improvement:

- VIX and oil fell from their late-June stress levels.
- High-yield spreads tightened.
- Treasury cash spending improved reserve liquidity.
- US payrolls reduced the immediate hike tail.
- China PMI and AI policy stabilized expectations.
- Southbound flows turned strongly positive.
- Alibaba, Nvidia, Apple, and Meta received cash-flow-relevant catalysts.

Evidence against an all-clear:

- Breadth was negative on June 29, June 30, and July 8.
- SKEW remained elevated/rising.
- Broad semiconductors continued down through July 7.
- Treasury yields rose into July 8.
- The Iran ceasefire failed again.
- Onshore China did not confirm the Hong Kong July 8 rally.
- The Hong Kong peg/funding state improved only gradually and remained fragile.

## 13. Forward invalidation and watchpoints

### 13.1 US liquidity reversal

Treasury projected a late-July TGA peak near $1 trillion. A fast TGA rebuild plus larger bill issuance would drain part of the early-July liquidity tailwind.

Watch:

- Daily TGA balance.
- Reserve balances.
- SOFR/EFFR and repo stress.
- Bill issuance and money-fund absorption.
- Whether net liquidity remains expansionary once the TGA rebuild begins.

### 13.2 Iran/Hormuz failure

The June 29 floor relied partly on lower oil-tail risk. Renewed shipping disruption, Brent above the mid-$80s, or failure of a permanent agreement would reactivate the inflation/Fed channel.

Watch:

- Vessel transit and insurance/freight rates.
- Brent and refined-product spreads.
- Inflation breakevens.
- Fed-hike probabilities.

### 13.3 H200 implementation failure

The July 8 report added option value, not delivered revenue. The catalyst weakens if approvals remain symbolic, quantities are too small, or no shipments occur.

Watch:

- Chinese purchase approvals.
- US license issuance.
- Shipment evidence.
- Nvidia’s China revenue guidance.
- Alibaba cloud capex and compute availability.

### 13.4 Alibaba earnings confirmation

The July 8 briefing was not an audited filing. The rally becomes a short-covering event if the August report does not confirm:

- Narrower instant-commerce losses.
- Sustained overall profitability.
- Cloud acceleration.
- AI product monetization.
- Continued buybacks.

### 13.5 Breadth and credit confirmation

A durable broad risk-on regime should eventually produce:

- More advancers than decliners across several sessions.
- Semiconductor participation beyond Nvidia.
- Continued HY-spread tightening.
- Better small/mid-cap participation.
- Reduced SKEW rather than only lower spot VIX.

If megacaps continue rising while breadth and credit deteriorate, the correct label remains a narrow squeeze.

## 14. Local evidence ledger

The event reconstruction used the following local repo artifacts in addition to the external sources below:

| Question | Local artifact |
|---|---|
| US breadth | `data/breadth/breadth.parquet` |
| Tail hedging | `data/cboe/skew.parquet` |
| News-sentiment direction | `data/frbsf/news_sentiment.parquet` |
| High-yield credit | `data/fred/BAMLH0A0HYM2.parquet` |
| Financial conditions | `data/fred/NFCI.parquet` or current FRED input path |
| Fed net liquidity | `data/macro/fed_net_liquidity.parquet` |
| Treasury General Account | `data/treasury/tga.parquet` |
| ON RRP | `data/nyfed/rrp.parquet` |
| Fed assets | `data/nyfed/h41_assets.parquet` |
| Liquidity-quality interpretation | `data/neuralweb/liquidity_plumbing.json` |
| Southbound flow | `data/china_connect/southbound.parquet` |
| Hong Kong funding | `data/hkma/interbank_liquidity.parquet` |
| HKD peg/FX | `data/hk/HKD_X.parquet` |
| HK regime | `data/hk_regime/latest.json` |

## 15. External source ledger

### Policy, geopolitics, and macro

- [Reuters — US and Iran agree to halt attacks and renew talks](https://www.investing.com/news/world-news/us-carries-out-fresh-strikes-against-iran-after-tanker-struck-in-hormuz-escalating-hostilities-4764056)
- [Federal Reserve — June 16-17 FOMC minutes](https://www.federalreserve.gov/monetarypolicy/files/fomcminutes20260617.pdf)
- [Federal Reserve — H.4.1 balance-sheet releases](https://www.federalreserve.gov/releases/h41/)
- [BLS — June 2026 employment situation](https://www.bls.gov/news.release/archives/empsit_07022026.htm)
- [US Treasury — quarterly refunding statement and TGA guidance](https://home.treasury.gov/news/press-releases/sb0489)
- [AP — July 8 Iran escalation and oil response](https://apnews.com/article/72181b48494a6367c40cf6e9a817e6b4)

### Flows and market structure

- [FTSE Russell — 2026 US index reconstitution summary](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/2026-russell-us-indexes-reconstitution-summary.pdf)
- [Traders Magazine — record June 26 closing-auction volume](https://www.tradersmagazine.com/departments/equities/june-russell-reconstitution-concludes-with-record-553-9-billion-traded-at-the-close/)
- [Citadel Securities — July flow and seasonality outlook](https://www.citadelsecurities.com/news-and-insights/global-market-intelligence/july/)
- [Reuters — hedge funds sold chip stocks for a fourth week](https://www.investing.com/news/stock-market-news/hedge-funds-dumped-chip-stocks-for-a-fourth-week-as-ai-shares-sold-off-4776190)
- [FRED — US high-yield option-adjusted spread](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)

### China and Hong Kong

- [China State Council — June 29 AI and trade meeting](https://english.www.gov.cn/news/202606/30/content_WS6a430b6ac6d00ca5f9a0be11.html)
- [China NBS — June 2026 PMI](https://www.stats.gov.cn/english/PressRelease/202607/t20260701_1964047.html)
- [HKMA — July 7 Hong Kong/offshore-RMB measures](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2026/07/20260707-3/)
- [PBOC — overnight reverse-repo operation report](https://www.marketscreener.com/news/china-central-bank-conducts-overnight-reverse-repos-again-keeps-rate-at-1-25-sources-say-ce7f5fdfde81f123)
- [Reuters — July 8 Hong Kong rotation into cheap internet stocks](https://www.indopremier.com/ipotnews/newsDetail.php?group_news=IPOTNEWS&jdl=Hong+Kong+stocks+surge+as+dip-buyers+emerge%2C+mainland+benchmarks+at+one-month+low&news_id=223656)

### Companies and AI policy

- [Alibaba — June 29 accelerated repurchase disclosure](https://www.hkexnews.hk/listedco/listconews/sehk/2026/0630/2026063001808.pdf)
- [US Department of Defense — June 8 Section 1260H entities](https://media.defense.gov/2026/Jun/08/2003945537/-1/-1/1/ENTITIES-IDENTIFIED-AS-CHINESE-MILITARY-COMPANIES-OPERATING-IN-THE-UNITED-STATES-IN-ACCORDANCE-WITH-SECTION-1260H.PDF)
- [Reuters — Anthropic’s Alibaba model-distillation allegation](https://www.investing.com/news/stock-market-news/anthropic-says-alibaba-illicitly-extracted-claude-ai-model-capabilities-4759021)
- [Alibaba July 8 catalyst summary](https://www.investing.com/news/stock-market-news/why-is-alibaba-stock-surging-today-93CH-4780851)
- [Reuters — China preparing limited H200 purchases](https://www.investing.com/news/stock-market-news/china-plans-to-let-top-ai-firms-buy-limited-amount-of-nvidia-h200-chips-the-information-reports-4782000)
- [US Commerce/BIS — H200 case-by-case license framework](https://media.bis.gov/press-release/department-commerce-revises-license-review-policy-semiconductors-exported-china)
- [Reuters — memory demand and customer commitments](https://www.marketscreener.com/news/south-korean-chip-shares-surge-after-micron-flags-strong-ai-related-demand-ce7f5fd8d88ef420)
- [AP — South Korea’s semiconductor hub](https://apnews.com/article/korea-samsung-ai-hynix-chips-22352d95c7a821c5f4548b2d1a4ebde8)
- [Bloomberg Law — Nvidia valuation compression](https://news.bloomberglaw.com/artificial-intelligence/nvidias-1-trillion-slide-sends-valuation-to-pre-ai-boom-levels)
- [BofA rating summary — Nvidia Buy and $350 target](https://www.benzinga.com/markets/equities/26/07/60326448/is-nvda-stock-a-buy-bofa-says-tech-giants-massive-moat-is-completely-unappreciated-sees-78-upside)
- [Apple — Broadcom and US-chip commitment](https://www.apple.com/newsroom/2026/07/apple-to-increase-spend-with-broadcom-to-produce-billions-more-us-chips/)
- [Axios — Meta explores external cloud business](https://www.axios.com/2026/07/01/meta-cloud-mark-zuckerberg)
- [TechCrunch — Meta custom AI chips](https://techcrunch.com/2026/07/09/metas-new-ai-chips-will-begin-production-in-september/)

## 16. Final conclusion

The June 29 reversal was the moment three earlier pressures stopped worsening: geopolitical/oil tail risk, forced quarter-end selling, and the probability that AI/memory demand had already collapsed.

Treasury liquidity, softer labor data, China funding support, and July allocation seasonality made the floor durable. They did not create a Fed pivot.

The July 8-10 surge was then built from separate company catalysts:

- Alibaba: buyback absorption plus a quick-commerce/cloud expectation reset.
- Nvidia: China H200 revenue optionality at a compressed valuation.
- Apple: supply certainty and administration-aligned US manufacturing.
- Meta: a possible path from AI capex to cloud/API/chip monetization.

The cleanest label is therefore:

> **A common macro/positioning floor followed by selective AI-policy and company rerating—not one synchronized global risk-on switch.**
