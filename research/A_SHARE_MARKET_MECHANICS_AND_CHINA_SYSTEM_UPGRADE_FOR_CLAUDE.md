# A-Share Market Mechanics And China System Upgrade Plan For Claude

Date: 2026-07-08

Purpose: This memo is a research and build handoff for upgrading the China dashboard, A-share dashboard, China engines, lobes, and Neural Web so the system can reason about mainland A-shares as a distinct market rather than as a generic macro equity market with a China label.

Status: research artifact. No code authority. No investment advice. All new signal authority proposed here must pass the repo's measurement gauntlet before it can size, rank, or originate trades.

## 0. Executive Thesis

Our current China stack has useful pieces, but it still under-models the thing that makes mainland A-shares different: the market is not driven only by macro growth, earnings, and simple sector momentum. It is driven by a reflexive loop among policy expectation, domestic liquidity, retail/institutional participation, margin and turnover intensity, daily price-limit mechanics, theme propagation, state intervention, property-cycle confidence, CNY/USD pressure, and the household asset-allocation alternatives available behind capital controls.

The A-share market often rallies when the economy is still weak because the market is discounting a policy/liquidity turn, a household reallocation away from property/deposits, or a state-supported "risk asset should stabilize" phase. It often sells off even before macro collapses because liquidity/participation turns, regulators cool speculation, the yuan comes under pressure, property trust breaks again, margin deleveraging begins, or theme breadth narrows. The economy matters, but the tradable cycle is usually a policy-liquidity-participation cycle layered on top of a slower property/export/consumer cycle.

The system upgrade should therefore create a canonical `china_market_state` object and a set of China-specific lobes:

- A-share Market Structure and Participation Lobe.
- Policy Transmission and State Put Lobe.
- A-share Cycle Phase Lobe.
- Theme and Concept Rotation Lobe.
- Execution and Price-Limit Mechanics Lobe.
- Stock Lifecycle and Entry Lobe.
- China Macro Transmission Lobe.
- HK/Offshore/Dollar Linkage Lobe.
- China Allocation and Cash Lobe.

The biggest principle: stop asking "is China good or bad?" and start asking "which A-share phase are we in, whose money is moving, what policy/liquidity impulse is priced, what sector/theme is gaining breadth, which names are fillable at good entries, and what would invalidate the phase?"

## 1. What The Current Repo Already Has

The current system is not blank. It already has a lot of China infrastructure, but it is fragmented and some of the most A-share-specific knowledge is not promoted to a top-level market brain.

Existing useful pieces:

- `engine/china_run.py` builds China regime artifacts, feature tables, market drivers, conditions, fear/euphoria, and display-only alerts.
- `engine/china_regime.py` classifies China with a growth/inflation quad and a simple liquidity overlay. This is useful but too macro-generic.
- `engine/china_market_drivers.py` fingerprints recent tape drivers such as PBoC/rates, CNY shock, liquidity impulse, stimulus tape, commodities, AI/semis, southbound/mainland appetite, and risk-off/washout. It is deterministic and display-only.
- `engine/china_conditions.py` has display-only RORO, slowdown/recession, drawdown, and fear/euphoria gauges. RORO legs already include copper/gold, breadth, southbound, M1-M2, turnover, QVIX, USDCNH, margin, and AH premium.
- `engine/china_signals.py` knows A-share board mechanics better than most of the stack: main board 10 percent limit, STAR/ChiNext 20 percent, BSE 30 percent, T-style reversal, limit-up chase veto, QVIX inversion, and margin crowding as risk.
- `engine/china_liquidity.py` has per-name ADV and turnover ratio from deep OHLCV storage.
- `engine/china_sector_cycles.py` has 31 Shenwan L1 sectors, washout/euphoria signatures, sector forward logs, and conditional pathway display.
- `engine/china_allocation.py` already learned that China A-share beta is mean-reverting and whipsaw-prone, while income/dividend plus gold plus bonds is more useful as an allocation spine.
- `engine/china_intel_bus.py` creates `china_intel.briefing.v3`, a context-only intelligence bus. It explicitly does not feed scoring, regime, or allocation.
- `docs/SIGNAL_BUS.md` already lists China-alpha and Neural Web artifacts and confirms that `site-china-intel-briefing` is display-only.

Important local research already established:

- `research/CHINA_ENGINE_REASSESSMENT.md` found validated or measured edges: 3-month within-sector reversal, forward-drawdown radar for market sizing, global AI/semi to China CPO weekly confirmer, low-vol defensive sleeve, and sector washout/euphoria context.
- `research/china_alpha/phase1/ashare-signal-research.md` found that raw OHLCV exists for about 1,495 A-share names in `data/china_stocks_raw/*.parquet`, but engines mostly do not consume it. This is a major upgrade lever.
- The same phase-1 research falsified many tempting ideas: raw LHB, block-trade premium, limit-up continuation buys, generic cross-sectional momentum, volume dry-up bases, northbound net flow, and southbound/AH premium/margin-velocity as standalone timing signals.
- `research/china_alpha/phase1/rotation-machinery.md` found that `china_sector_central` suppresses bullish conviction, sector-cycle display does not feed stock construction enough, and THS concept confluence is implemented but not wired into daily build.
- `research/CHINA_SECTOR_PATHWAY_PHASE0.md` found that no single China-specific sector driver clears a strict multiple-testing bar, but state signatures do: bottoms are price below trend, deep drawdown, breadth collapse, and deleveraging; tops are euphoria/crowding, broad euphoric breadth, and hot momentum.

Main diagnosis:

The repo has strong ingredients, but the dashboard still lacks one sovereign China market brain that says:

1. What phase is A-share in?
2. Whose capital is in control?
3. Is the move policy, liquidity, theme, earnings, global-dollar, or forced-deleveraging driven?
4. Is the move early, broadening, exhausted, or distributional?
5. Which stocks are entry-quality, which are just exciting, and which are unbuyable because of execution mechanics?
6. Should Neural Web read the China output as context, de-risking advice, a validated sleeve, or a tradable signal?

## 2. A-Share Market Structure: How This Market Actually Works

### 2.1 The Market Is Mostly Domestic Capital Under Capital Controls

Mainland A-shares are mostly a domestic household, institution, and state-policy market. Foreign capital matters at the margin and for sentiment, but it is not the whole machine.

Participant groups:

- Retail households: still a huge share of trading activity. Older research and CSRC-linked summaries place retail at roughly 80 percent of aggregate trading volume, while ChinaClear-linked public reporting showed more than 214 million securities investors by February 2023. Retail does not mean one behavior: small speculative accounts, wealthy active accounts, and disciplined private investors behave differently.
- Domestic mutual funds: important in institutionalized rallies, especially when fund cash falls and equity exposure rises.
- Insurance companies and pensions: increasingly important in low-rate, high-dividend, SOE/value markets. They can support dividend/low-vol/large-cap styles even when retail chases themes.
- Private funds and quant funds: important in factor crowding, high-turnover rotation, intraday liquidity, and small/mid-cap breadth.
- Broker margin accounts: critical in bull accelerations and crashes.
- State-linked capital, often called the "National Team": can stabilize large indices, ETFs, banks, brokers, and key SOEs, but does not eliminate all drawdown risk.
- Corporates and insiders: buybacks, pledges, unlock schedules, capital raises, and block trades matter more than a generic U.S. dashboard usually assumes.
- Foreign investors through QFII/RQFII and Stock Connect: useful as sentiment and ownership pressure, but live northbound data disclosure has been curtailed since 2024. The system must not rely on live northbound net flow as if it were still a complete tape.
- Southbound mainland money into Hong Kong: vital for HK and offshore China, and also a clue for mainland risk appetite, but not a clean A-share timing signal.

System implication:

We need a participation lobe. A rally led by insurers, ETFs, and SOE dividends is not the same as a retail/margin concept mania. A market with high index returns but weak new-account growth and mediocre breadth is not the same as a blow-off retail bull.

### 2.2 Trading Rules Shape Behavior

A-shares are structurally different from U.S. stocks:

- Daily price limits matter. Main-board A-shares generally have 10 percent limits. STAR and ChiNext use 20 percent limits after their initial no-limit IPO window. BSE uses a wider regime. These limits create queueing, unfilled orders, "sealed" limit-up/limit-down behavior, and next-day gap pressure.
- T+1 matters. You generally cannot buy and sell the same share on the same day. This changes intraday reversal, chase, and stop behavior.
- Short selling and securities lending are constrained relative to the U.S. There is no deep U.S.-style single-name short ecosystem for most traders.
- Stock Connect northbound investors can use only eligible securities and order types, with daily quota and price-limit constraints.
- Circuit-breaker and intervention history affects behavior. Participants remember that regulation can appear suddenly in speculative phases.
- IPO, refinancing, unlocks, pledges, and ST/risk-warning mechanics matter. A broad stock score that ignores these will be wrong in China.

System implication:

We cannot rank A-share entries from close-only U.S.-style signals. We need fillability, limit-state, open/high/low, locked-limit exclusion, T+1 path realism, turnover shape, and execution-grade fields on every stock packet.

### 2.3 Price Limits Create Special Reflexivity

Price limits are not just risk controls. They produce behavior:

- Limit-up hits can attract attention and next-day chasers.
- Sealed limit-up names may be practically unbuyable.
- Failed seals can become distribution clues.
- Limit-down clusters can trap sellers and defer selling pressure.
- A hot theme can look stronger than it is because supply is blocked at upper limits.
- A panic can look orderly until locked limit-down queues release.

Local repo research already says limit-up continuation buys are dead/unbuyable as a system edge. That does not mean limit-up data is useless. It means limit-up data should be a market-structure and theme-breadth input, not a naive buy trigger.

## 3. What Drives A-Share Bulls And Bears

### 3.1 The Core Equation

A-share trend is usually a function of:

Policy expectation + liquidity + participation + property/credit confidence + sector/theme narrative + CNY/USD/global liquidity + execution reflexivity.

Corporate earnings matter, but they are often a slower confirmation layer rather than the first spark. That is why A-shares can rally in weak macro periods and fall in acceptable macro periods.

### 3.2 Bull-Market Ignition

Typical bull ignition ingredients:

- Policy pivot: leadership, State Council, PBoC, CSRC, NDRC, or fiscal language shifts from restraint to support.
- Liquidity relief: RRR cuts, rate cuts, OMO/MLF support, lower LPR, funding-rate easing, fiscal bond acceleration, or credit impulse stabilization.
- Property pressure stops getting worse: not necessarily a real housing bull, but "less bad" enough to release risk appetite.
- Household asset rotation: deposit yields are low, property wealth creation is impaired, and equities become one of the few available domestic upside assets.
- Participation acceleration: turnover rises, new accounts rise, fund issuance improves, margin balances expand, and brokers outperform.
- Theme leadership: AI, semis, CPO, NEV, defense, SOE reform, anti-involution, consumption upgrade, or policy-favored industrial chains start to gain breadth.
- State confidence signal: ETF buying, stabilization funds, buybacks, market-support rhetoric, reduced IPO supply, or direct capital-market policy.

The first move is often from extreme pessimism to policy-put recognition. The second move requires participation. The third move requires breadth. The dangerous late move is turnover and margin acceleration without earnings/credit validation.

### 3.3 Bear-Market And Crash Triggers

Typical bear or crash drivers:

- Property confidence deterioration: sales, new starts, developer funding, land sales, and local-government finance weaken.
- Credit impulse disappointment: TSF/loan flow looks okay in stock terms but weak in flow terms; government bonds carry financing while household/private demand stays weak.
- CNY pressure and USD strength: easing becomes constrained by FX stability; foreign/HK risk appetite weakens.
- Regulatory cooling: limits on margin, quant trading, IPO/refinancing, short-selling optics, or theme speculation can change tape behavior.
- Margin deleveraging: the 2015 crash is the classic case. NBER research on 2015 found shadow-financed margin accounts and leverage-induced fire sales were central to the crash dynamic.
- Theme exhaustion: leaders extend, breadth fails, limit-up continuation weakens, failed seals rise, and laggards stop catching up.
- Retail fatigue: turnover remains high, but prices stop responding.
- External shock: tariffs, sanctions, global risk-off, U.S. rate shock, dollar spike, commodity shock, or geopolitical stress.

The most dangerous A-share selloffs are not ordinary earnings corrections. They are participation and leverage unwind phases, where correlations go to one and "defensive stocks" only fall less.

### 3.4 Why The Market Can Rally When The Economy Is Weak

The user asked the right question: if the economy is bad, why did A-shares rally last year and this year?

Answer: because A-shares often trade the expected change in policy/liquidity/participation before the real economy improves. Weak economy can be bullish for equities if it raises the probability of support and pushes households out of low-yield deposits/property into stocks. It becomes bearish only when weakness overwhelms the policy put, credit transmission fails, or the yuan/dollar constraint blocks easing.

Current official macro is mixed, not one-directionally "terrible":

- NBS June 2026 manufacturing PMI returned to expansion at 50.3, with production 51.4 and new orders 51.2.
- May 2026 industrial value added rose 4.5 percent year over year, with computers/communications/electronics up 17.0 percent.
- Retail is weak: May retail sales fell 0.6 percent year over year, while January-May retail was only up 1.4 percent.
- Property remains deeply weak: January-May real estate development investment was down 16.2 percent, new starts down 22.6 percent, sales floor area down 10.8 percent, and developer funds down 19.0 percent.
- Fixed asset investment is weak: January-May FAI was down 4.1 percent, private investment down 7.1 percent.
- CPI is mild and demand-sensitive, while PPI turned positive partly through upstream price pressure.
- Aggregate financing stock is still growing, but flow was lower than the prior year, and government bonds are a major support.
- FX reserves were stable around USD 3.4422 trillion at end-May 2026.
- Exports remain strong, but the composition is shifting away from the U.S. and toward ASEAN, Africa, EU, and higher-value goods.

So the current rally is not "the economy is fixed." It is more like:

policy put + low domestic yields + property-wealth alternative + institutional participation + export/AI/industrial pockets + liquidity expectation.

That is a tradable rally, but not automatically a durable earnings-led bull.

## 4. Historical Regime Map

This section should become a future `china_cycle_memory` or Time Machine artifact. A-share cycles are not identical, but the same ingredients recur.

### 2005-2007: Share Reform, RMB Appreciation, Liquidity Boom

Dominant drivers:

- Non-tradable share reform.
- Rapid growth, WTO/export boom, strong credit, RMB appreciation.
- Retail participation and wealth effect.
- Valuation expansion into mania.

System lesson:

Policy reform plus liquidity plus household participation can create a vertical bull. Valuation warnings arrive early and do not stop the move until participation exhausts.

### 2008: Global Crisis And Domestic Shock

Dominant drivers:

- Global recession, export shock, commodity crash, risk-off.
- A-shares collapsed despite eventual massive stimulus.

System lesson:

China policy response matters, but external demand and global liquidity can overwhelm until the policy impulse is credible and broad.

### 2009: Stimulus Reflation

Dominant drivers:

- Credit surge, infrastructure, property, commodities, cyclicals.
- Fast rebound with heavy macro beta.

System lesson:

Credit impulse and fiscal infrastructure can create powerful cyclical rallies, but they plant future leverage/property problems.

### 2014-2015: Leverage And Retail Bubble

Dominant drivers:

- Policy encouragement, margin financing, shadow leverage, retail account surge.
- Brokers, tech, small caps, ChiNext-style growth.
- Crash after margin regulation, deleveraging, and forced selling.

System lesson:

Margin plus retail plus policy narrative is rocket fuel. It must be tracked as both upside participation and crash risk. The phase transition from "participation confirms bull" to "leverage creates fire-sale convexity" is the key.

### 2016-2017: National Team Stabilization And Blue-Chip/Quality

Dominant drivers:

- Post-crash stabilization, supply-side reform, large-cap quality, consumption leaders.
- Lower appetite for extreme small-cap speculation.

System lesson:

After a crash, leadership can narrow to large, liquid, policy-safe names. Defensive/quality can work as relative leadership.

### 2019: STAR/Tech And Policy Innovation

Dominant drivers:

- STAR Market launch, tech self-sufficiency, trade-war pressure, policy industrialization.

System lesson:

Geopolitical pressure can be a bullish driver for policy-favored domestic substitutes, but only if liquidity and domestic risk appetite support the theme.

### 2020-2021: Core Assets, Baijiu, NEV, Solar, Healthcare

Dominant drivers:

- Pandemic liquidity, institutional fund flows, "core asset" concentration, growth themes.
- Crowding and valuation overshoot.

System lesson:

China can have U.S.-style mega-quality/growth concentration phases, but they can unwind violently when policy, valuation, and liquidity reverse.

### 2021-2024: Property Bear, Regulation, Deflation Psychology

Dominant drivers:

- Property developer crisis, platform regulation, education crackdown memory, weak consumer confidence, foreign outflows, CNY pressure.
- Dividend/SOE/low-vol worked better than many high-growth sleeves.

System lesson:

Macro weakness does not select every stock equally. In grinding bears, cash yield, gold, bonds, SOE dividends, and low-vol can matter more than broad equity beta.

### Late 2024-2026: Policy-Put And Liquidity/Theme Rally

Dominant drivers:

- Stimulus/support expectations after deep pessimism.
- Domestic liquidity, low yields, institution-led participation, southbound/HK linkage, AI/semi themes, and some export/industrial resilience.
- As of July 2026, current repo output says China A-shares are in a fragile stagflation quadrant, liquidity overlay neutral, cycle tag mid, fear/euphoria Greed, RORO neutral/divergent, and recent market driver is mainland risk-off via southbound selling/HK/AH divergence.

System lesson:

This is not a clean early-cycle, broad economic bull. It is a mature policy/liquidity/theme rally with weak property/consumer backing. Blow-off risk exists, but so does topping-without-blowoff risk because participation may be more institutional and policy-managed than 2015.

## 5. Current Regime As Of 2026-07-08

### 5.1 Market Tape

External market reads:

- Trading Economics reported the Shanghai Composite near 3971 on July 8, 2026, down on the session and slightly down over one month but up about 13.7 percent year over year.
- GuruFocus reported CSI 300 Total Return at 7213.96 as of July 6, 2026, up about 25.1 percent year over year and near its historical high.
- Invesco's 2026 midyear China equity outlook noted early-2026 daily turnover above RMB 3.6 trillion and strong southbound Stock Connect flows in the first four months.

Internal repo snapshot:

- `data/china_regime/latest.json` as of 2026-07-03: `quad=Q3`, `liquidity_overlay=neutral`, `cycle_tag=mid`, fear/euphoria score 74 (`Greed`), RORO neutral/divergent.
- Breadth and QVIX legs are risk-off while turnover, copper/gold, M1-M2, southbound, and USDCNH lean risk-on. That is not a clean consensus bull.
- `site/china_brief.json` says A-shares are in a fragile stagflation quadrant with weak growth but building PBoC easing impulse; semis are extended/smart-money exhaustion; oversold laggards show early accumulation; HK is more dollar/global-risk sensitive.
- `site/factordata/china_standouts.json` has a lifecycle-like board already: 110 `buy`, 24 `ripening`, 15 `ran`, plus a drawdown-radar sleeve chip. But the trust copy correctly says the reversal context is validated but high-variance and "not a buy list."

### 5.2 Why We May Be Topping Without A Blow-Off Top

A classic A-share blow-off needs broad retail entry, margin acceleration, brokers exploding, account-opening frenzy, limit-up mania, and broad small-cap/theme euphoria. The current rally has elements of liquidity and theme strength, but it also has brakes:

- Property remains deeply weak, so household confidence is not universally healed.
- Consumer data is soft, so the rally is not backed by broad income optimism.
- Policy support appears targeted and stability-focused rather than "let speculation rip."
- Institutions, insurers, ETFs, and hedge funds appear more important this cycle than pure retail mania.
- Global constraints remain: dollar, yuan, tariffs, geopolitics, export re-routing, and commodity/inflation pressure.
- Internal breadth is divergent. Turnover is hot, but breadth/QVIX/margin legs are not giving a clean risk-on consensus.
- Leaders like semis/AI can get extended before the whole market reaches a final blow-off.

Inference: this looks more like a mature policy-liquidity rally trying to broaden than a fresh all-in retail bubble. If broadening fails, it can top by rotation fatigue rather than a vertical 2015-style climax.

### 5.3 Conditional Next-Phase Map

Bull-continuation path:

- Breadth improves while turnover remains strong but not parabolic.
- Margin rises gradually, not explosively.
- Policy and PBoC liquidity stay supportive.
- Property indicators stop deteriorating at the margin.
- CNY is stable or stronger against USD.
- Sector leadership broadens from semis/AI into brokers, financials, consumption, industrial upgrades, healthcare, and laggards.
- THS concepts show T3/T4 breadth, not just a few leaders.

Distribution/top path:

- Index holds high while breadth weakens.
- Turnover stays high but forward returns flatten.
- Failed limit-up seals rise.
- Leaders gap/chase but fail to hold.
- Margin/turnover froth rises.
- QVIX remains inverted or stops confirming upside.
- Southbound/HK divergence worsens.
- CNY weakens and PBoC support becomes constrained.

Bear/re-risk-off path:

- Property and private credit weaken again.
- USD/CNH rises.
- Policy language disappoints.
- Margin balances contract into selling.
- Limit-down clusters rise.
- Broad sector washout returns.
- Defensive equity sleeves fall less but do not protect absolute capital enough.
- Cash, gold, and CGB/bonds become the true defense.

## 6. How To Trade A-Shares Differently From U.S. Equities

### 6.1 U.S. Strategies That Do Not Port Cleanly

Classic U.S. momentum:

- Local research and external academic work both warn that classic weekly/monthly stock momentum is weak or absent in China, with reversal and turnover effects more robust.
- Do not import "winner keeps winning" screens without China-specific validation.

Breakout chasing:

- Daily price limits and T+1 make breakouts dangerous and often unfillable.
- Limit-up continuation buying is already falsified locally.

Confirmation gating:

- Local research found that adding quality/confirmation gates to the validated 3-month within-sector reversal edge can flip it negative. This is exactly the kind of "sounds prudent, kills edge" behavior the system must avoid.

Northbound flow timing:

- Disclosure changed, and local research already says northbound net is not a reliable standalone timing edge.

Macro equals market:

- China can rally on weak macro if policy/liquidity expectation improves. It can sell off on okay macro if participation, FX, or policy expectation turns.

### 6.2 What Works Better In A-Shares

Validated or measured in the repo:

- 3-month within-sector reversal as the only name-selection edge that currently earns respect, with caveats.
- Forward-drawdown radar as market-sizing risk control, currently unwired or under-promoted.
- Low-vol defensive sleeve as a relative/portfolio tool, not a magic crash hedge.
- Deep-discount block trades as a positive measured edge; premium blocks are not.
- Global AI/semi to China CPO weekly confirmer.
- Sector washout/euphoria signatures as phase context.

Promising but must be tested:

- Abnormal turnover as an avoid/crowding signal. External research finds abnormal turnover negatively predicts future returns.
- MAX/lottery avoid. China investors chase lottery-like stocks; high extreme daily return behavior should be treated as risk unless validated otherwise.
- Limit-up/limit-down breadth as market phase, not buy list.
- Failed seal ratio as distribution.
- THS concept breadth thrust and first-tick-up after washout.
- ETF/fund issuance/insurance participation as regime context.
- Policy phrase diffs and State Council/PBoC/CSRC/NDRC event taxonomy as context first, then validation candidate.

### 6.3 How People Make A Lot Of Money In A-Shares

Legal, system-relevant routes:

- They catch policy/liquidity turns before broad confirmation.
- They buy hated but liquid names when washout and reversal setup align, then sell when participation gets excited.
- They ride policy-favored industrial themes early: semis, AI/CPO, defense, NEV, robotics, equipment upgrade, SOE reform, anti-involution winners, etc.
- They understand the phase: early bull wants beta/brokers/themes; mid bull wants breadth/rotation; late bull rewards discipline and selling; bear wants cash/income/gold/bonds/selective reversal.
- They avoid chasing unfillable limit-up names and lottery spikes after the edge is gone.
- Institutions and quants harvest turnover/reversal/liquidity anomalies with strict execution and risk control.
- Long-only managers outperform by avoiding landmines: ST risk, pledge/unlock pressure, accounting quality, refinancing dilution, policy-crackdown sectors, and crowded themes.

Routes we should not systematize:

- Rumor chasing, insider information, manipulation, pump groups, or anything dependent on illegal/private information.
- Blind "hot money" LHB copying.
- Buying sealed limit-up queues after the move is already inaccessible.

### 6.4 Do Defensive Stocks Work?

Sometimes, but not in the simple U.S. way.

In grinding bear regimes, high-dividend SOEs, utilities, telecom, energy/coal/oil, banks, low-vol, and cash-flow names can outperform and sometimes produce positive absolute returns. In true deleveraging or limit-down panic, correlations go to one and most stocks fall. Defensive equities then are relative defense, not complete defense.

The system should separate:

- Defensive equity sleeve: dividend/low-vol/SOE/high FCF, useful for relative equity exposure.
- True portfolio defense: cash, gold, CGBs, policy-bank bonds, short-duration yield, and possibly offshore USD/HKD instruments depending on user constraints.

## 7. Sector And Rotation Mechanics

A-share rotation is not the same as U.S. sector rotation.

U.S. sector rotation often follows business-cycle, earnings, rate, and factor regimes. A-share rotation is more often:

- Policy theme first.
- Liquidity and retail attention second.
- Sector breadth third.
- Earnings confirmation later.
- Regulatory cooling or crowding exhaustion last.

Common early-bull leaders:

- Brokers/non-bank financials: participation and turnover beta.
- Semis/software/AI/CPO/robotics: policy and innovation themes.
- Defense and security: geopolitics and state priority.
- Small/mid-cap concepts: retail and quant breadth.

Common mid-cycle broadening:

- Industrial equipment, manufacturing upgrade, EV/auto chain, materials, machinery.
- Healthcare and consumer laggards after washout if policy/earnings stabilize.
- Banks and insurers if yield, value, and policy stabilization matter.

Common late-cycle/euphoria:

- Hot concepts, low-quality small caps, repeated limit-up chains, high abnormal turnover, MAX/lottery names.

Common bear/defensive:

- High dividend SOEs, telecom, utilities, coal/energy, banks, gold/miners, low-vol, CGBs.

Important nuance:

During A-share selloffs, rotations can fail because the whole market becomes a liquidity event. The dashboard must know when to rotate and when to go cash. "Everything falling together" should be a distinct phase, not a failed sector model.

## 8. Best China Asset Classes For 1-3 Years, Scenario-Based

This is not personalized investment advice. It is a system-planning view for what the dashboard should be able to compare.

Base case: policy put, weak property, mixed consumer, resilient exports, low domestic yields.

- Core: China high-dividend/low-vol/SOE/free-cash-flow equity income.
- Ballast: CGBs/policy-bank bonds, short-duration yield, gold.
- Tactical: A-share reversal/sector washout entries, not broad all-in beta.
- Offshore: HK tech/China internet only when USD/CNH and global liquidity support it.

Bull case: credit impulse improves, property stops falling, consumer stabilizes, USD weakens, policy encourages capital markets.

- Add: brokers, insurers, consumer, healthcare, industrial upgrades, semis/AI/robotics, high-beta themes, CSI300/ChiNext beta.
- Watch: breadth thrust, margin not too hot, ETF/fund issuance, new accounts, limit-up breadth.

Bear case: property relapses, CNY weakens, USD/liquidity tightens, tariffs/geopolitics worsen, policy disappoints.

- Raise cash materially.
- Favor gold, CGBs, high-dividend defensives only as relative equity sleeve.
- Avoid broad beta, limit-up chase, high-turnover themes, property-chain beta, and weak balance sheets.

External-liquidity bull case: Fed easing or dollar weakness boosts HK/offshore China more than onshore.

- Favor HK tech, China internet, offshore high beta, southbound/foreign-flow beneficiaries.
- Keep A-share stock selection separate because onshore execution and policy mechanics differ.

## 9. System Upgrade: Required New Brain Architecture

### 9.1 Create A Canonical `china_market_state.v1`

Add a single daily object that all China pages, engines, and Neural Web adapters can read.

Proposed path:

- `data/china_state/market_state.json`
- `site/chinastatedata/market_state.json`

Schema:

```json
{
  "schema": "china_market_state.v1",
  "asof": "YYYY-MM-DD",
  "phase": {
    "label": "POLICY_IGNITION|BROADENING|EUPHORIA|DISTRIBUTION|DELEVERAGING|GRINDING_BEAR|REPAIR",
    "confidence": 0.0,
    "evidence": [],
    "contradictions": [],
    "falsifiers": []
  },
  "macro": {
    "growth": {},
    "inflation": {},
    "property": {},
    "consumer": {},
    "exports": {},
    "credit": {},
    "fiscal": {}
  },
  "policy": {
    "pboc_liquidity": {},
    "capital_market_support": {},
    "property_support": {},
    "industrial_policy": {},
    "tone_diff": {}
  },
  "participation": {
    "turnover": {},
    "margin": {},
    "fund_flows": {},
    "insurance_pension": {},
    "retail_proxy": {},
    "state_support_proxy": {},
    "foreign_proxy": {}
  },
  "microstructure": {
    "limit_up_down": {},
    "failed_seals": {},
    "locked_limits": {},
    "fillable_ratio": {},
    "t_plus_one_risk": {}
  },
  "rotation": {
    "sector_phase": {},
    "theme_breadth": {},
    "ths_concepts": {},
    "leadership_age": {},
    "broadening_score": {}
  },
  "external": {
    "usdcnh": {},
    "dxy": {},
    "us_yields": {},
    "global_liquidity": {},
    "commodities": {},
    "geopolitics": {}
  },
  "allocation": {
    "equity_gross_context": {},
    "cash_context": {},
    "dividend_income": {},
    "gold": {},
    "cgb_bonds": {},
    "hk_offshore": {}
  },
  "authority": {
    "tier": "context_only|de_escalation_allowed|validated_sizing|validated_signal",
    "why": [],
    "cannot_do": []
  }
}
```

Rule: this state object can be context-only at first. Do not let it originate buy/sell decisions until ledgers prove it. It can still be useful immediately because Neural Web can read contradictions and falsifiers.

### 9.2 New Engine: `engine/china_participation.py`

Goal: identify whose money controls the market right now.

Inputs:

- Market turnover, turnover/value traded, turnover/free-float market cap.
- Turnover acceleration: 5d/20d/60d z-scores.
- Margin financing balance, margin balance/market cap, margin net change, margin turnover.
- Limit-up/down count, sealed limit-up count, failed seal count, lianban count, limit-down queue.
- ETF flows if available.
- Fund issuance/redemption proxies.
- New investor accounts where available.
- Insurance/pension equity exposure proxies where available.
- Buybacks, corporate net issuance, major shareholder sale bans/unlocks.
- Northbound replacement proxies since live disclosure is incomplete.

Outputs:

- `participation_regime`: dormant, institutional_accumulation, retail_ignition, margin_acceleration, broad_mania, distribution, forced_deleveraging.
- `who_controls`: retail, institutional, margin, state, foreign/offshore, mixed, unclear.
- `risk`: low, normal, frothy, fire_sale.
- Evidence and contradictions.

Why this matters:

The same index return has different meaning depending on whether it comes from insurers buying dividends, quant breadth, retail margin, or state ETF support.

### 9.3 New Engine: `engine/china_policy_transmission.py`

Goal: translate Chinese policy into market-relevant impulse without letting LLMs invent signal.

Inputs:

- PBoC: OMO, MLF, SLF, RRR, LPR, DR007, SHIBOR, relending facilities.
- Credit: TSF/AFRE stock and flow, RMB loans, household loans, corporate loans, government bonds.
- Fiscal: special bond issuance, local-government debt, infrastructure approvals.
- Property: purchase restrictions, mortgage rates, down-payment rules, inventory purchase, developer funding.
- Capital market: CSRC language, IPO/refinancing pace, ETF support, buyback/re-lending tools, trading rule changes.
- Industrial policy: State Council, NDRC, MIIT, commerce policy and anti-involution campaigns.
- Text diffs: phrase changes from "prevent risk" to "stabilize market" to "boost capital markets."

Outputs:

- `policy_impulse`: easing, neutral, tightening, targeted_support, market_rescue.
- `transmission_channel`: liquidity, property, fiscal, industrial, capital_market, FX_constrained.
- `priced_in_check`: not_priced, partly_priced, crowded, failed.
- `event_ledger`: append-only policy events with source, timestamp, affected sectors, and validation status.

Authority:

Context-only first. It can de-escalate risk if validated later. It must not generate a stock buy just because policy mentions a sector.

### 9.4 New Engine: `engine/china_cycle_phase.py`

Goal: classify the A-share market cycle as a phase specific to China.

Proposed phases:

- `CAPITULATION`: deep drawdown, breadth collapse, low turnover, pessimism, policy pressure rising.
- `POLICY_PUT`: policy support appears, market stops making new lows, state/intervention proxies rise.
- `LIQUIDITY_IGNITION`: turnover and breadth rise, brokers respond, liquidity legs improve.
- `THEME_LEADERSHIP`: one or more policy/global themes lead with rising concept breadth.
- `BROADENING`: more sectors and styles participate; laggards work; drawdown radar improves.
- `EUPHORIA`: turnover/margin/limit-up breadth extreme; MAX/lottery names lead; failed quality.
- `DISTRIBUTION`: index high but breadth/leadership weakens; failed seals and abnormal turnover rise.
- `DELEVERAGING`: margin and locked-limit stress drive all-boats selling.
- `GRINDING_BEAR`: no panic, but policy transmission weak and rallies fail.
- `REPAIR`: volatility fades, breadth stops deteriorating, but upside not confirmed.

Inputs:

- Existing China regime quad and liquidity overlay.
- Existing fear/euphoria and RORO legs.
- Participation lobe.
- Limit-up/down lobe.
- Sector washout/euphoria signatures.
- Drawdown radar.
- Policy impulse.
- USD/CNH and global liquidity.

Outputs:

- Phase label.
- Confidence.
- `allowed_actions`: cash, defensive_income, reversal_only, half_size_entries, broad_beta_allowed, no_chase, trim_extended, de_risk.
- Falsifiers: e.g. "phase fails if breadth falls below X while turnover remains above Y."

This is the missing dashboard spine.

### 9.5 New Engine: `engine/china_microstructure.py`

Goal: make every stock packet executable in A-share reality.

Inputs:

- Raw OHLCV from `data/china_stocks_raw/*.parquet`.
- Adjusted price data.
- Board type and price-limit width.
- Limit-up/down flags.
- Locked-limit state.
- Volume, amount, turnover ratio, free float if available.
- Open/high/low path for fill simulation.

Outputs per name:

- `board`: main, STAR, ChiNext, BSE, ST, other.
- `limit_width`: 10, 20, 30, etc.
- `limit_state`: normal, near_up_limit, sealed_up, failed_up_seal, near_down_limit, sealed_down, failed_down_seal.
- `fillable`: true/false/context.
- `t_plus_one_risk`: low/medium/high.
- `entry_fill_model`: next-day open, H/L midpoint, VWAP proxy, no-fill locked limit.
- `chase_veto`: true/false with reason.

Rule:

No A-share stock output should say "buy now" without a fillability and chase-veto field.

### 9.6 Upgrade Stock Selection: `engine/china_stock_lifecycle.py`

Goal: replace generic buy boards with lifecycle shelves.

Shelves:

- `RIPENING`: washed out, liquid, not locked, sector/theme starting to repair, no final trigger.
- `ENTRY`: reversal edge active, fillable, not extended, market phase allows risk, sector/theme support acceptable.
- `HOLD`: prior entry working, invalidation clear, not yet euphoric.
- `RAN_LATE`: moved too far, turnover/extension hot, limit mechanics risky, wait for reset.
- `AVOID`: ST/pledge/unlock/accounting/liquidity/locked-limit/lottery/abnormal-turnover risk.

Features:

- Within-sector 3-month reversal is the core validated selection leg.
- Quality/fundamental gates should be separate context, not hard gates, unless validated.
- Entry timing should use raw OHLCV, not close-only.
- Theme/sector tailwind should use THS breadth and sector phase, not trailing 20d performance alone.
- Risk sizing should read drawdown radar, participation phase, and microstructure.

Output:

- `stock_state_packet.v1` for every candidate:

```json
{
  "ticker": "000000.SZ",
  "asof": "YYYY-MM-DD",
  "shelf": "RIPENING|ENTRY|HOLD|RAN_LATE|AVOID",
  "selection_basis": ["within_sector_reversal"],
  "entry_basis": [],
  "sector_theme": {},
  "microstructure": {},
  "risk": {},
  "action_context": "watch|partial|full_context|trim|avoid",
  "authority": "context_only|validated_reversal|validated_sizing",
  "falsifiers": []
}
```

### 9.7 Upgrade Rotation: `engine/china_theme_rotation.py`

Goal: catch sector/theme first-ticks without falling into momentum chase.

Inputs:

- THS concept confluence already implemented but not wired.
- Sector washout/euphoria signatures.
- Member breadth thrust.
- RS slope inflection.
- Member dispersion compression.
- COILED fraction.
- Global read-throughs: AI/semi/CPO, commodities, luxury, healthcare, autos/EV, industrials.
- Policy theme tags from policy lobe.

Outputs:

- `theme_phase`: dormant, washout, first_tick, breadth_thrust, leadership, crowded, failed.
- `theme_age`: number of days/weeks since first thrust.
- `leader_vs_laggard`: leaders extended, laggards catching, broadening, narrowing.
- Candidate feeder for stock lifecycle, not a standalone buy list.

Important:

Use theme data to prefer early repair and reject late chase. Do not rebuild a U.S. momentum board.

### 9.8 Upgrade Allocation: `engine/china_allocation.py`

Goal: turn current allocation research into a real China asset-class cockpit.

Asset buckets:

- A-share broad beta.
- A-share reversal sleeve.
- A-share dividend/low-vol/SOE income.
- HK/offshore China tech.
- Gold/gold miners.
- CGB/policy-bank bonds.
- Cash/short-duration yield.
- Commodities/cyclicals where relevant.

Inputs:

- Cycle phase.
- Policy impulse.
- USD/CNH/DXY.
- PBoC liquidity.
- Property/consumer/export regimes.
- Drawdown radar.
- Participation/crowding.
- Existing allocation backtests.

Outputs:

- `china_allocation_context.v1` with scenario weights, not direct personalized advice.
- `gross_context`: raise, neutral, add, max.
- `cash_instruction_context`: hold cash, deploy only into reversal, deploy into broadening, trim euphoria.
- `asset_class_rank_context`: display-only until validated.

## 10. Dashboard Upgrade Plan

### 10.1 China Macro Dashboard

Add a first-viewport China Market State strip:

- A-share phase.
- Who controls the tape.
- Policy impulse.
- Liquidity/credit transmission.
- Property/consumer/export split.
- USD/CNH/global liquidity pressure.
- Breadth/turnover/margin/limit stress.
- Cash/beta context.

Compress existing copy. Use progressive disclosure for evidence. The top page should answer:

"Are China equities early, broadening, euphoric, distributing, or deleveraging?"

### 10.2 A-Share Dashboard

Replace any generic "buy board" feel with lifecycle shelves:

- Ripening.
- Entry.
- Hold.
- Ran late.
- Avoid/chase veto.

Each stock card should show:

- Why this stock exists here.
- Entry status.
- Fillability and limit-state.
- Sector/theme phase.
- Reversal validation tier.
- Extension and abnormal-turnover warning.
- Market phase permission.
- Falsifier.

The board should actively tell the user when not to buy. In A-shares, "do not chase" is a primary alpha feature.

### 10.3 New Page: A-Share Market Mechanics

Purpose: a cockpit for the market's internal engine.

Panels:

- Participation: turnover, margin, new accounts/fund issuance, ETFs, state support proxy.
- Limit mechanics: limit-up/down breadth, failed seals, locked queues, lianban.
- Phase memory: current phase vs historical analogs.
- Policy tape: policy events and phrase diffs.
- Cross-market: HK/offshore, USD/CNH, DXY, U.S. yields, commodities.
- Breadth/rotation: sector and THS concepts.

This page should not be a wall of text. It should be a control room with drilldowns.

### 10.4 New Page: China Cycle Memory / Time Machine

Purpose: show historical A-share regimes and current analogs.

Episodes:

- 2005-07 reform/liquidity mania.
- 2008 crash.
- 2009 stimulus.
- 2014-15 leverage bubble/crash.
- 2016-17 stabilization/blue-chip.
- 2019 tech/policy.
- 2020-21 core assets.
- 2021-24 property/regulation bear.
- 2024-26 policy-put/liquidity rally.

Fields:

- Starting conditions.
- Ignition driver.
- Participation driver.
- Sector leaders.
- Blow-off/distribution markers.
- Crash/failure trigger.
- Best defense.
- System analog score to today.

### 10.5 New Page: China Asset Allocation Cockpit

Purpose: compare A-shares, HK, dividends, gold, CGBs, and cash under regimes.

Panels:

- 1-3 year scenario matrix.
- Current base/bull/bear scenario.
- Which asset class benefits from policy easing, dollar weakness, property repair, export boom, or deleveraging.
- Allocation lobe confidence and authority.

## 11. Neural Web Integration

### 11.1 Lobe Outputs

Every China lobe should produce a standard Neural Web packet:

```json
{
  "lobe": "china_participation",
  "schema": "neuralweb_lobe_packet.v1",
  "asof": "YYYY-MM-DD",
  "state": {},
  "evidence": [],
  "contradictions": [],
  "falsifiers": [],
  "confidence": 0.0,
  "authority": "context_only",
  "may_de_escalate": false,
  "may_originate": false,
  "consumers": []
}
```

Neural Web should never ask an LLM to hallucinate the state. It should ask:

- What do deterministic lobes say?
- What contradicts the primary state?
- What would change the state?
- Does any validated lobe allow de-risking or sizing adjustment?
- Is this context-only?

### 11.2 China Decision Packet

When Neural Web answers "what should we do in China?", it should produce a decision packet:

```json
{
  "question": "China A-share risk and entries",
  "market_phase": {},
  "policy_liquidity": {},
  "participation": {},
  "macro_backdrop": {},
  "external_pressure": {},
  "sector_theme": {},
  "stock_candidates": [],
  "execution_constraints": [],
  "action_context": "cash|watch|reversal_only|partial_entries|broad_beta|trim",
  "falsifiers": [],
  "authority": {
    "originates_signal": false,
    "can_de_escalate": true,
    "validated_components": []
  }
}
```

### 11.3 Authority Ladder

Tier 0: Display/context only.

- China intel, policy text, theme narrative, external news, unvalidated phase reads.

Tier 1: De-escalation allowed.

- Validated drawdown radar, locked-limit stress, chase veto, fillability veto, extreme crowding.

Tier 2: Sizing context.

- Only after market-phase ledgers prove forward drawdown/return utility by era.

Tier 3: Signal support.

- Existing validated within-sector reversal can support candidate selection, but still with high-variance and execution caveats.

Tier 4: Origination.

- No new China lobe reaches this tier until it passes PIT/replay, T+1 fills, locked-limit exclusion, effective-N controls, and out-of-sample era splits.

## 12. Data Upgrade Requirements

Priority 1:

- Wire `data/china_stocks_raw/*.parquet` into daily stock construction.
- Maintain raw and adjusted data planes.
- Add O/H/L based fill simulation.
- Add board/limit metadata to every ticker.
- Create market-wide limit-up/down and failed-seal ledgers.
- Add margin market series and per-name margin where feasible.
- Add market turnover/free-float turnover.

Priority 2:

- THS concept breadth and membership snapshots.
- ETF/fund issuance and redemption proxies.
- Buyback, pledge, unlock, and insider/major-holder sale data.
- Block trade discount/premium split.
- LHB participant classification but only as probationary context.

Priority 3:

- Policy phrase-diff corpus from State Council, PBoC, CSRC, NDRC, MOF, SAFE, NBS.
- Property high-frequency data: sales, new starts, developer funding, land sales.
- Consumer high-frequency proxies: travel, box office, online retail, services, sentiment.
- Export/global trade proxies by destination and product category.
- Global inputs: DXY, U.S. yields, Fed liquidity, copper/iron ore/oil, semis, tariffs/geopolitical events.

## 13. Validation Gauntlet

Every new signal/lobe should be measured as:

- CSI300-relative and absolute.
- T+1 realistic.
- Fill simulated with next-day open and H/L midpoint variants.
- Locked-limit no-fill exclusion.
- Slippage and liquidity caps.
- Raw and adjusted price consistency.
- PIT membership where possible.
- Era splits: 2007, 2008-09, 2014-15, 2016-17, 2020-21, 2021-24, 2024-26.
- Regime splits: bull, bear, policy-put, deleveraging, broadening, euphoria.
- Sector/theme clusters with effective-N controls.
- FWER/false-discovery discipline for sector drivers.
- Null output printed next to results.
- Can-force pattern for any override.

Minimum ledgers:

- `data/china_validation/stock_lifecycle_forward_log.jsonl`
- `data/china_validation/cycle_phase_forward_log.jsonl`
- `data/china_validation/participation_forward_log.jsonl`
- `data/china_validation/theme_rotation_forward_log.jsonl`
- `data/china_validation/allocation_forward_log.jsonl`

## 14. Claude Build Waves

### Wave 0: Contracts And No-Authority Scaffolding

Files:

- `docs/SIGNAL_BUS.md`
- `engine/china_state_schema.py`
- `engine/china_market_state.py`
- `scripts/build_china_market_state.py`

Work:

- Define `china_market_state.v1`.
- Emit context-only JSON using existing regime, conditions, sector cycles, allocation, and intel outputs.
- Add no new signal authority.

### Wave 1: Participation Lobe

Files:

- `engine/china_participation.py`
- `scripts/build_china_participation.py`
- `site/chinastatedata/participation.json`

Work:

- Turnover, margin, breadth, limit-up/down, ETF/fund proxies where available.
- Output `who_controls`, `participation_regime`, `froth/fire_sale`.

### Wave 2: Microstructure Lobe

Files:

- `engine/china_microstructure.py`
- `engine/china_liquidity.py` extensions
- `tests/test_china_microstructure.py`

Work:

- Board metadata.
- Limit-state detection.
- Fillability.
- T+1 fill models.
- Chase veto.

### Wave 3: Cycle Phase Classifier

Files:

- `engine/china_cycle_phase.py`
- `data/china_state/cycle_phase.json`

Work:

- Rule-based classifier first.
- Evidence/contradiction/falsifier output.
- Do not score trades.

### Wave 4: Stock Lifecycle Board

Files:

- `engine/china_stock_lifecycle.py`
- Existing China stock builder templates.
- `site/factordata/china_standouts.json` schema extension.

Work:

- Promote `ripening`, `entry`, `hold`, `ran_late`, `avoid`.
- Add microstructure/fillability fields.
- Preserve validated reversal caveat.
- Remove any copy that makes high-variance context look like a direct buy list.

### Wave 5: Theme Rotation

Files:

- `engine/china_theme_rotation.py`
- Wire existing THS confluence into daily build.
- `site/chinastatedata/theme_rotation.json`

Work:

- Theme phase, breadth thrust, leadership age, failed/crowded flags.
- Feed stock lifecycle as context.

### Wave 6: Policy Transmission

Files:

- `engine/china_policy_transmission.py`
- `data/china_policy/events.jsonl`
- `site/chinastatedata/policy_transmission.json`

Work:

- Deterministic taxonomy first.
- Source links and phrase diffs.
- Context-only.

### Wave 7: Allocation Cockpit

Files:

- `engine/china_allocation.py` extensions.
- `templates/china_allocation.html.j2` or China dashboard panel.

Work:

- Compare A-share beta, reversal, dividend/low-vol, HK tech, gold, CGBs, cash.
- Output scenario context and gross/cash guidance only to validated authority level.

### Wave 8: Neural Web Adapter

Files:

- `engine/neuralweb/adapters/china_market_state.py`
- `engine/neuralweb/query.py` extension.
- `docs/SIGNAL_BUS.md`

Work:

- Add lobe packets.
- Add decision packet.
- Preserve authority ladder.

### Wave 9: Measurement And Promotion

Files:

- `tests/test_china_state_contracts.py`
- `tests/test_china_lobe_authority.py`
- `research/china_alpha/phase2/*.md`

Work:

- Forward ledgers.
- PIT/replay.
- Promote only after evidence.

## 15. Explicit Do-Not-Build List

Do not:

- Let China intel or LLM summaries originate signals.
- Resurrect raw LHB as positive alpha.
- Treat premium block trades as bullish.
- Treat limit-up continuation as a buy signal.
- Use northbound net flow as a complete live timing signal after disclosure changes.
- Import U.S. cross-sectional momentum without A-share validation.
- Add quality/confirmation hard gates to the reversal edge unless validation proves they help.
- Treat macro weakness as mechanically bearish or macro strength as mechanically bullish.
- Build a page that shows "China is good/bad" without phase, participation, execution, and falsifiers.

## 16. Source Notes

Current and structural sources used:

- NBS June 2026 PMI: https://www.stats.gov.cn/english/PressRelease/202607/t20260701_1964047.html
- NBS May 2026 industrial production: https://www.stats.gov.cn/english/PressRelease/202606/t20260617_1963964.html
- NBS January-May 2026 fixed asset investment: https://www.stats.gov.cn/english/PressRelease/202606/t20260617_1963965.html
- NBS January-May 2026 real estate development: https://www.stats.gov.cn/english/PressRelease/202606/t20260617_1963968.html
- NBS January-May 2026 retail sales: https://www.stats.gov.cn/english/PressRelease/202606/t20260617_1963969.html
- NBS May 2026 CPI: https://www.stats.gov.cn/english/PressRelease/202606/t20260611_1963931.html
- NBS May 2026 PPI: https://www.stats.gov.cn/english/PressRelease/202606/t20260611_1963929.html
- SAFE May 2026 FX reserves: https://www.safe.gov.cn/en/2026/0607/2424.html
- State Council/GACC April 2026 trade summary: https://english.www.gov.cn/archive/statistics/202605/09/content_WS69fee048c6d00ca5f9a0ad76.html
- Shanghai Stock Exchange trading mechanism: https://english.sse.com.cn/start/trading/mechanism/
- Shanghai-Hong Kong Stock Connect introduction: https://english.sse.com.cn/access/stockconnect/introduction/
- HKEX Stock Connect investor book: https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Getting-Started/Information-Booklet-and-FAQ/Information-Book-for-Investors/Investor_Book_En.pdf
- NBER Digest on 2015 leverage/fire sales: https://www.nber.org/digest/nov18/leverage-fire-sales-and-2015-chinese-stock-market-crash
- NBER paper on leverage-induced fire sales: https://www.nber.org/papers/w25040
- Trading Economics Shanghai Composite July 2026: https://tradingeconomics.com/china/stock-market
- GuruFocus CSI 300 Total Return July 2026: https://www.gurufocus.com/economic_indicators/6198/csi-300-total-return
- Invesco 2026 China equity outlook: https://www.invesco.com/apac/en/institutional/insights/equity/china-equities-outlook.html
- Business Insider/Goldman note on institutional participation in the 2025 rally: https://markets.businessinsider.com/news/stocks/china-stock-market-rally-forecast-institutional-investors-not-retail-2025-9
- ChinaDaily investor account report: https://www.chinadaily.com.cn/a/202303/18/WS641575a4a31057c47ebb53c5.html
- ScienceDirect anomaly summary: https://www.sciencedirect.com/science/article/pii/S0927538X21001141
- ScienceDirect short-term momentum/reversal summary: https://www.sciencedirect.com/science/article/abs/pii/S0927538X22002153
- Review of Finance abnormal turnover paper listing: https://ideas.repec.org/a/oup/revfin/v20y2016i5p1835-1865..html
- MERICS Q1 2026 China economy tracker: https://merics.org/en/tracker/chinas-economy-q1-economy-rebounds-geopolitical-fallout-yet-come
- USCC May 2026 China Bulletin: https://www.uscc.gov/trade-bulletins/china-bulletin-may-5-2026

Local repo sources used:

- `CLAUDE.md`
- `docs/SIGNAL_BUS.md`
- `engine/china_run.py`
- `engine/china_regime.py`
- `engine/china_market_drivers.py`
- `engine/china_conditions.py`
- `engine/china_inputs.py`
- `engine/china_signals.py`
- `engine/china_liquidity.py`
- `engine/china_sector_cycles.py`
- `engine/china_allocation.py`
- `engine/china_intel_bus.py`
- `research/CHINA_ENGINE_REASSESSMENT.md`
- `research/CHINA_STOCKS_OVERHAUL.md`
- `research/CHINA_INTEL_POWERHOUSE.md`
- `research/CHINA_SECTOR_PATHWAY_PHASE0.md`
- `research/china_alpha/CHINA_ALPHA_MASTERPLAN_BY_FABLE.md`
- `research/china_alpha/phase1/ashare-signal-research.md`
- `research/china_alpha/phase1/rotation-machinery.md`
- `data/china_regime/latest.json`
- `site/china_brief.json`
- `site/china_intel/briefing.json`
- `site/factordata/china_standouts.json`

## 17. One-Line Build Mandate

Build China as a market-structure, policy-transmission, participation-cycle, theme-rotation, execution-aware system. The win condition is not "more China data." The win condition is that Neural Web can say, with evidence and humility: what phase mainland A-shares are in, whose money is moving, which risks are becoming nonlinear, which sectors are early versus late, which stocks are actually fillable at good entries, and when cash beats cleverness.
