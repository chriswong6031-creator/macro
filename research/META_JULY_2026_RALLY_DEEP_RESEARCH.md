# META July 2026 Liftoff — Deep Research, Durability Assessment & Prediction Analysis

**Date:** Saturday, 2026-07-11 (written after Friday's close)
**Scope:** Why META suddenly rallied (Jul 1–10), whether it continues into summer, how durable it is, whether Q2 earnings season is a catalyst or risk event for Meta and Alphabet, and the predicted chain of events.
**Method:** Fresh web research only (no internal research reports used, per instruction) — 8 parallel research lanes, 14 load-bearing claims put through 2-vote adversarial verification (11 confirmed, 2 corrected, 1 refuted), plus raw local price/options tape and an event-study base rate computed from first principles. Evidence tiers are tagged throughout: **[V]** adversarially verified (2 independent refutation attempts failed), **[C]** multi-source corroborated, **[S]** single-sourced (treat as provisional), **[L]** computed from local raw price/options data.

---

## 0. TL;DR

META rallied **+27% from its March trough and +14.8% in the last six sessions** (582.90 → 669.21), its best week since early 2024, because a cluster of news between July 1–10 attacked the single load-bearing bear argument — **$125–145bn of 2026 capex with zero external revenue to show for it** — from three directions at once: a cloud business to *sell* compute (Meta Compute), custom silicon to *cheapen* compute (Iris), and a hosted-model API to *monetize* compute (Muse Spark 1.1 at ~¼ of rivals' prices). Nothing about 2026 cash flows actually changed; what repriced was the *probability distribution around the capex's return*.

The rally is **real but now priced for confirmation**. My probability-weighted expected value for META at Labor Day is ≈ $660 — roughly flat versus Friday's $669 — but with fat two-sided tails (30%+ scenarios above $720, 30%+ scenarios below $610). The easy money (washed-out positioning → narrative repricing) was made July 1–10. The next leg requires *proof*, and the proof events are compressed into a three-week gauntlet: CPI Jul 14 → TSMC Jul 16 → **GOOGL Jul 22 (confirmed)** → FOMC Jul 28–29 → **META ~Jul 29 (expected, not yet officially confirmed)** + MSFT same day → AMZN/AAPL Jul 30 → the states' $1.4T penalty trial in August → Iris mass production in September.

Earnings season is best understood as a **sorting event, not a directional one**: the 2026 market regime pays for demonstrated AI monetization and punishes capex-without-proof (GOOGL +10% on its Q1 cloud beat; META −8.5–10% and MSFT sold off on their Q1 capex raises). For GOOGL the July 22 print carries modest positive skew (expectations already reset −11% from May highs). For META, at $669 after a +15% pre-positioning week, the event is genuinely two-sided with slightly negative *event-day* skew — but positive *full-summer* skew if management converts the Meta Compute story into numbers.

---

## 1. What actually happened — the verified timeline

### 1.1 The two-wave rally

**Wave 1 — July 1 (the liftoff day).** META rose **+8.81% to $612.91 on ~45M shares (~2.6–3x average volume)** — its sharpest single-day gain of 2026 — after Bloomberg reported Meta is building **"Meta Compute"**, a cloud infrastructure business to sell AI computing power externally, considering both a Bedrock-style hosted-model tier and CoreWeave-style raw GPU capacity sales, led by infrastructure head Santosh Janardhan, Meta Superintelligence Labs leader Daniel Gross, and president Dina Powell McCormick. CNBC's Julia Boorstin independently confirmed the story the same day. **[V]** The move was META-specific: GOOGL +1.1%, NVDA −1.3% that day **[L]** — and it was violently redistributive *within* the AI complex: CoreWeave −14%, Nebius −17%, Micron −10% **[C]**, because Meta as a compute *seller* is a new competitor to, and a demand hedge against, the neoclouds it currently rents from.

Important timeline correction the adversarial pass surfaced: **"Meta Compute" was not new on July 1.** Zuckerberg established it as a top-level *internal buildout* initiative via a Threads post around **Jan 12, 2026** ("tens of gigawatts this decade, and hundreds of gigawatts or more over time") — with no mention of external sales — and at the **May 27 shareholder meeting** he framed selling compute as a contingency *"if we get to a point where we feel that we have overbuilt"*, noting "almost every week there are different companies that come to us asking if we have compute that they could buy." **[V]** What was new on July 1 was that the *external sales business* is organizationally real, staffed, and led by named executives.

July 2 gave back −4.9% (fast-money profit taking into the July 4 weekend), closing the holiday-shortened week at $582.90. **[L]**

**Wave 2 — the week of July 6–10 (the confirmation cascade).** Day by day **[L for prices through Jul 8; V/C for Jul 9–10 prices and all news]**:

| Date | Close | Move | Driver |
|---|---|---|---|
| Mon Jul 6 | 600.29 | +2.98% | Momentum + residual Meta Compute optimism; Wells Fargo PT 765→767 (Jul 2, Overweight) |
| Tue Jul 7 | 615.58 | +2.55% | **Muse Image launch** — first image model from Meta Superintelligence Labs (Alexandr Wang), deployed across Meta AI app, Instagram Stories, WhatsApp, and into Advantage+ ad-creative tools. Outperformed a Nasdaq down >1%. Erste upgrade to Buy; BNP Paribas Outperform, PT $955 |
| Wed Jul 8 | 603.12 | −2.02% | The week's only down day: leaked Zuckerberg town-hall recording — AI agent deployment *"hasn't really accelerated in the way that we expected"* **[V]**; four states disclose **$1.4 trillion penalty demand** in the August children's-addiction trial **[V]**; France orders publisher-fee talks |
| Thu Jul 9 | 631.48 | +4.70% | **Reuters exclusive (internal memo): "Iris" custom AI chip — designed with Broadcom, fabbed by TSMC — cleared six weeks of testing, mass production September 2026**; memo targets 7 GW of compute in 2026 doubling to **14 GW in 2027**, a new custom processor roughly every six months through 2027 **[V]**; multi-year supply lock-ins with SanDisk (NAND, +6.8% on the news), Samsung (DRAM), Sumitomo (fiber) **[C]**. Same day: **Meta Model API public preview with Muse Spark 1.1 at $1.25/$4.25 per M tokens — ~¼ of Claude Opus 4.8 input pricing ($5/$25) and GPT-5.5 ($5/$30)** **[V]**; Zuckerberg returns to X after ~3 years to announce it; SemiAnalysis publishes its 1-year Meta Superintelligence progress report; BofA reiterates Buy $835 and **cuts its cost-per-gigawatt estimate to ~$22bn from $45bn** **[S]** |
| Fri Jul 10 | **669.21** | **+5.97%** | 40.6M shares (~2.4–3x avg); **crossed the 200-day moving average (~643) for the first time in over two months** **[L/C]**. Absorbed two negatives without breaking: EU DSA preliminary finding (design features breach; fine up to 6% of global revenue) **[C]**; Muse Image photo-referencing feature pulled after SAG-AFTRA/CAA backlash ("missed the mark") **[C]** |

**Net: +14.8% week-over-week (Jul 2 → Jul 10), best week since early 2024; market cap ≈ $1.70T; −15.1% below the Aug 12, 2025 closing all-time high of $788.15; back to roughly +1.4% YTD** (from −8.6% YTD as of Wednesday). **[V, L]**

The SemiAnalysis quote needs precision (one verifier caught wire services garbling it): the report actually says Meta is *"the only hyperscaler/neolab on track to be world class at all three"* (data, talent, compute) with *"the best chance at catching up with Anthropic/OpenAI"* — parity expected end-2026 at the earliest. The widely circulated "will overtake Google's frontier models within six months" framing was media paraphrase, not the report. **[V-corrected]**

### 1.2 Where META came from (why there was this much coiled spring)

The stock fell **−28.7% from $788 (Aug 12, 2025) to $525.72 (Mar 27, 2026)** **[L]**, in what is best understood as three sequential capex shocks against an accelerating ad business:

- **Oct 29, 2025 (Q3'25):** revenue beat (+26% YoY) but 2026 capex warned "notably larger" → −7.7% after hours. **[S]**
- **Jan 28, 2026 (Q4'25):** beats again; 2026 capex formally set at **$115–135bn** (~2x 2025's ~$72bn), expenses $162–169bn including Superintelligence Labs costs (Alexandr Wang, Nat Friedman, the $14.3bn/49% Scale AI stake, reported nine-figure packages). Yann LeCun's November 2025 departure marked the strategic rupture; Llama 4 Behemoth was never publicly released and Meta pivoted to closed-weight **Muse Spark** in April 2026, abandoning open-weights-first at the frontier. **[S/C]**
- **Apr 29, 2026 (Q1'26):** revenue **$56.31bn, +33% YoY — fastest growth since 2021**, 41% operating margin — and the stock *fell 8.5–10% anyway* (≈$150–175bn of market cap), because capex was raised again to **$125–145bn** and Meta disclosed **~$107bn of new multi-year infrastructure commitments in a single quarter**, with no cloud-revenue offset. The same week, Alphabet reported Google Cloud +63% YoY to $20.0bn with a $460bn+ backlog and was *rewarded*. **[V]**

Add the March macro washout (tariff shock; ~$7bn of Chinese advertiser spend flagged at risk **[S]**), a $375M New Mexico child-safety verdict **[S]**, Reality Labs still burning ~$19bn/yr **[C]**, a June FT report of a possible equity raise (denied, −5% intraday) **[S]** — and by late June META sat at $543, 20x forward earnings, PEG ~1.0, with 49 of 63 analysts still at Strong Buy. The market didn't disbelieve the business; it disbelieved the *capital allocation*. That is precisely the condition under which a credible capital-allocation narrative shock produces a +15% week.

---

## 2. Why it happened — first-principles mechanism

### 2.1 The AI-ROI equation, and why this news cluster hit all three terms

In the 2026 regime, a hyperscaler's multiple is being set by the market's estimate of **NPV(AI capex) = (revenue attributable to compute) − (cost of compute) − (risk that the compute is stranded)**. The whole 2026 bifurcation falls out of this one equation:

- **GOOGL +16% YTD** (before this week's fade): Cloud +63% growth, $460bn+ contracted backlog → the revenue term is *observable*. Capex of $180–190bn is forgiven because each dollar maps to booked demand. **[V]**
- **MSFT −20% YTD:** capex to ~$190bn calendar-2026 (+61% YoY, 23% above consensus) with FCF −22%, gross margin at multi-year lows, and Copilot paid penetration stuck at ~3–4% of the 365 base → revenue term *not yet observable* at the scale of the spend. **[C]**
- **META (−29% peak-to-trough):** the extreme case — 98% advertising revenue, capex justified by products generating no direct revenue today. The market was pricing a meaningful probability of *stranded compute*.

The July 1–10 news cluster repriced **all three terms simultaneously**, which is why the move was so large and so persistent across a down day:

1. **Revenue term (Meta Compute + Meta Model API):** external compute sales and hosted-model inference create a *salvage market* for the fleet. Even before any contract is signed, the existence of a sales channel truncates the left tail of "stranded asset" outcomes. The API launch on July 9 made this concrete: real endpoints, real pricing, Zuckerberg personally marketing it. This is the AWS-2006 template — and the market has a 20-year memory of what happened to the last company that turned its internal infrastructure into a product.
2. **Cost term (Iris):** custom silicon entering mass production in September, with a new processor every ~6 months and Broadcom/TSMC as partners, attacks the *denominator*. BofA's halving of its cost-per-gigawatt estimate ($45bn → ~$22bn) **[S]** is the cleanest illustration: if a gigawatt costs half as much, the same capex guidance buys twice the compute, and the ROI hurdle for every downstream product halves.
3. **Risk term (supply lock-ins + third-party validation):** multi-year SanDisk/Samsung/Sumitomo agreements signal execution seriousness toward 14 GW by 2027; SemiAnalysis — a source the buy side actually prices — independently ranked Meta as the only player world-class in data, talent, *and* compute simultaneously.

Cheap pricing on Muse Spark ($1.25/$4.25 vs $5/$25–30) is itself informative: you price at ¼ of the market when your marginal cost of inference is low (Iris + owned DCs) and your objective is share capture. It's the classic capacity-owner's move — and it quietly corroborates that the compute-cost term really is falling.

### 2.2 The flow mechanics (why the tape moved the way it did)

- **This was not a short squeeze.** Short interest was 1.58% of float (34.5M shares, 2.0 days to cover) as of Jun 30. **[C]** The buying was long-only re-entry plus hedge-fund re-grossing into the *laggard* — Goldman prime data shows Mag-7 net HF exposure rebuilt from ~11% (early April) to ~19% (Q2) with META specifically the most-added mega-cap name in Q1. **[C]**
- **It was funded partly by rotation out of the crowded winners.** During META's +11% intraweek run, GOOGL *fell* (Jul 9 −0.84%, Jul 10 −0.48%, closing $357.18, near its weekly low), and Goldman's high-beta AI momentum basket (GSPRHIMO) crashed **−18% in two sessions — its worst two-day move since 2020 — with HF momentum exposure at the 92nd percentile**. **[V]** The same week that made META was a bloodbath for the momentum expression of the AI trade. This is dispersion, not beta.
- **Options amplified, then dampened, then amplified.** July 1: ~$608M of premium, put/call 0.58, +$1.26bn positive delta flow, ~51% of it zero-DTE — a call-buying avalanche **[L]**. Dealers went long gamma (net GEX +0.6–1.0bn, flip down at ~546–559), which explains the orderly 600–620 chop of Jul 6–8 (max pain sat at 620) — until Thursday's Iris/API news forced price out of the pin zone, and Friday's 200-dma break (643) added systematic/CTA and breakout buyers on 3x volume. **[L]** Note: by Friday's close, flagged unusual activity skewed to *call selling* at the 650 (Jul 17) and 700 (Jul 24) strikes — profit-taking/overwriting into strength, not fresh chase. **[S]** IV30 ~50% vs 20-day realized ~52% — the options market is pricing continued turbulence, with no complacency discount. **[L]**

### 2.3 What did NOT happen (the honest columns of the ledger)

- **No dollar of new revenue was announced.** No Meta Compute customer, no pricing for raw capacity, no launch date. The Bloomberg story is *exploratory-but-organizationally-real*; Meta has not formally confirmed the cloud business. **[V]**
- **A structural constraint got less attention than it deserves:** Meta's leases with CoreWeave (~$21bn through 2032, atop an earlier ~$14.2bn deal) and Nebius (up to ~$27bn) reportedly **prohibit reselling leased capacity** (per Rosenblatt's read of the no-sublet clauses). Meta Compute can only sell from Meta-*owned* data centers — the first purpose-cited facility (Ohio) comes online in 2026. **[V]** The sellable fleet is therefore smaller and later than the headline suggests.
- **The one authentic inside data point this week was negative:** Zuckerberg, to his own employees, on AI agents — "hasn't really accelerated in the way that we expected." **[V]** The market chose to weight the promise over the leak. That is a sentiment statement, not an evidence statement.
- **The FCF math worsened, if anything.** Selling compute at neocloud economics (cloud opm 30–33% at maturity; Google Cloud took ~5 years and $4–5bn/yr of losses to get there) *dilutes* a 41%-margin ad monopoly. JPMorgan's projection — FCF ≈ **−$4bn in 2026 and −$24bn in 2027**, capex ~$202bn by 2027 (Anmuth, Neutral, PT $725, the street's only meaningful dissent) — was not touched by anything announced this week. **[V]** Morgan Stanley, constructive on the stock, still calls the neocloud "a stopgap, not a permanent business to scale." **[C]**

---

## 3. Where the rally sits now — durability scorecard

### 3.1 Supports (why this is more than a squiggle)

| Factor | Evidence |
|---|---|
| Valuation still cheap vs history | Forward P/E ~20.4x vs ~26x 10-yr average; PEG ~0.99 on +33% growth; EV/EBITDA ~15.6x vs GOOGL ~25x **[C]** |
| Street has room to chase | 57/63 Buy or better, avg PT $827–838 = ~24% above Friday's close; the *marginal* analyst action this week was mixed (Erste upgrade vs Citizens JMP trim to $800), i.e., the street has not yet re-rated for the news **[C]** |
| Positioning light, not crowded | SI 1.58%; HF re-grossing only partially rebuilt; Bridgewater had cut ~46% while Tepper/ValueAct added — ownership is contested, not consensus **[C]** |
| Narrative now has *scheduled* proof points | Sept Iris mass production; Muse Spark API adoption (observable via developer chatter/pricing pages); Q2 call; 2027 capex frame — each is a re-rating trigger if hit |
| Technical structure repaired | Reclaimed 200-dma (643) and broke the May high (635); YTD flipped positive (attracts systematic/momentum re-entry); next gate = April high 689 **[L]** |
| Base rate favors continuation | Event study (below): 60–61% probability of higher prices 1–3 months after this setup, median +4.3%/+10.4% |

**Event-study base rate [L]:** across 15 mega/large-cap techs since 1998, I found 233 de-overlapped instances of a **≥+7% single day on ≥2x volume while ≥20% below the 52-week high** (META's exact July 1 configuration):

| Horizon | Median | Win rate | p25 | p75 |
|---|---|---|---|---|
| +5d | +0.7% | 52% | −4.8% | +5.6% |
| +21d | +4.3% | 60% | −7.0% | +13.3% |
| +63d | +10.4% | 61% | −10.4% | +29.6% |

META's own four prior instances split 2–2: 2019-01 and 2023-02 worked (+15.5%, +23.7% at 63d); the two 2022 instances failed badly (−17% to −23%), because the *macro bear market* overwhelmed the stock-specific news. That conditional is the right lens for 2026: the setup works **unless the broader AI-capex complex cracks**. Caveats: descriptive only — survivor-biased ticker set, earnings-gap events included, events cluster in bear markets (effective sample is much smaller than n=233 implies).

### 3.2 Threats (what kills it)

1. **The rally is 100% narrative, 0% cash flow.** Every dollar of the +$220bn market-cap recovery since March rests on probability-weighting future proof. If Q2 delivers "beat + capex raise + vague cloud talk," that is *literally the April 29 configuration*, from a higher price.
2. **A capex guidance raise is more likely than not.** BNP's Nick Jones explicitly expects a possible raise to **$135–155bn** on the Q2 call **[V]**; management has raised the number at each of the last three prints. The question is not the raise — it's whether a monetization frame arrives *in the same breath*.
3. **The macro window is hostile.** Fed on hold at 3.50–3.75% (4th consecutive, June dots erased the 2026 cut; Goldman's first cut is June *2027*, with a flagged ~20% tail odds of a *hike*); May headline CPI 4.2% after the Iran war/Hormuz oil shock (Brent >$120 in March, ceasefire mid-June); June CPI lands **July 14** (~3.9% headline / ~2.9% core expected). **[V]** Duration-sensitive, negative-FCF-trajectory megacaps do not get multiple expansion in a hiking-tail regime.
4. **The AI complex itself is showing stress fractures.** GSPRHIMO −18% in two days; BIS's June annual report flagged AI-capex sustainability as a top financial-stability pressure point; Sequoia's Cahn quantifies a ~$600bn industry revenue gap; Allianz notes capex-vs-revenue divergence (46%) already exceeds the 2001 telecom peak (32%). **[V/C]** META's July bid came *from* rotation within the complex — if the complex de-rates wholesale (a second DeepSeek-type shock, a TSMC warning, an OpenAI funding stumble), rotation won't save the laggard.
5. **Legal tails with dates attached:** the four-state **$1.4T penalty demand goes to trial in August** (the demand ≈ 82% of Meta's market cap; it is a negotiating anchor, not an expected award, but August headlines are guaranteed) **[V]**; EU DSA preliminary finding (fine up to 6% of global revenue) **[C]**; FTC's appeal of its lost antitrust case, with 29 states as amici **[S]**.
6. **Competitive reality vs narrative:** Muse Spark reportedly trails GPT-5.4 and Claude Opus 4.6 on blended intelligence benchmarks and is weakest at agentic tasks — the exact workload enterprises buy **[S]**; OpenAI shipped GPT-5.6 the *same day* as Muse Spark 1.1; Google's Gemini claims 750M MAU. Cheap pricing buys developers, not necessarily durable share.

**Durability verdict:** The floor has genuinely risen — the salvage-value option is real, the valuation support is real, positioning is not stretched, and scheduled catalysts exist. But the move has consumed most of the *unconditional* upside; from $669, further gains are **conditional on confirmation events**. I'd characterize it as: *the drawdown regime ended; the proof regime began.*

---

## 4. Earnings season: catalyst or risk?

**Direct answer: it is a risk-shaped catalyst — a sorting event.** The Q1 season established the rule: proof gets paid (GOOGL +10% on the Cloud beat), promises get punished (META −8.5–10%, MSFT sold off on capex). Q2 will apply the same rule at higher stakes, with three structural observations:

### 4.1 The calendar (verification status noted — one date is NOT confirmed)

| Date | Event | Status |
|---|---|---|
| Mon Jul 14 | June CPI (~3.9% headline / ~2.9% core expected) | scheduled **[V]** |
| Thu Jul 16 | TSMC Q2 (cons. ~$40bn, +32% YoY) — AI supply bellwether | scheduled **[C]** |
| **Wed Jul 22** | **GOOGL Q2, 4:30pm ET call** | **officially confirmed via Alphabet IR** **[V]** |
| Tue–Wed Jul 28–29 | FOMC (≈85% hold priced) | scheduled **[V]** |
| **Wed Jul 29 (expected)** | **META Q2 after close** — *aggregator estimate; Meta has NOT issued the IR announcement yet* — plus MSFT same day (expected) | **unconfirmed [V-refuted as "confirmed"]** |
| Thu Jul 30 | AMZN + AAPL (expected) | consensus estimate **[C]** |
| August | Four-state children's-addiction trial ($1.4T demand) | scheduled **[V]** |
| September | Iris mass production start | company memo **[V]** |

Note the compression: if META confirms July 29, the market will digest a **Fed decision at 2pm and META+MSFT earnings after the close of the same session**. That is a maximum-volatility day by construction.

### 4.2 META (~Jul 29): high bar, two-sided, decided by one variable

- **The numbers themselves are likely fine.** Guidance $58–61bn; consensus ~$60.2bn (+~26% YoY) and EPS ~$7.11–7.18. Q1 ads grew 33% with impressions +19% *and* price +12% — and Muse Image is now inside Advantage+, a direct ad-creative tailwind. **[V/C]** P(revenue ≥ $60bn) ≈ 70%; P(EPS beat) ≈ 65%.
- **The capex line is the tripwire.** P(2026 guide raised, to ~$135–155bn) ≈ 60%. In the Q1 regime, a raise alone = −8–12%. What changed since April is the existence of an *offset narrative*.
- **The deciding variable: does management put numbers on Meta Compute / Model API?** Formal segment framing, an anchor customer, capacity-committed revenue, even a "we expect external compute revenue in 2027 of $X–Y bn" bracket — any of these converts the capex raise from confession to investment, GOOGL-style. They have already launched the API and put the CEO on X to market it; the machinery is clearly moving. But companies rarely guide a business unit into existence one quarter after a leak. P(concrete commercial detail on the call) ≈ 55%; P(vague "early days" language) ≈ 45%.
- **The options market agrees this is binary:** META has historically priced ±7–10% implied into earnings and *realized beyond the implied move in ~63% of recent reports* (10-yr median realized ≈ ±11%). **[C]** With the stock +15% into the event, the *event-day* skew is mildly negative (more room to disappoint a freshly repriced narrative), while the *post-event 1-month* skew is positive in the confirmation branch.

### 4.3 GOOGL (Jul 22, confirmed): moderate bar, positive skew, and the sector's tone-setter

GOOGL enters the print having *faded* 11% from its May high ($402 → $357) while META ripped — the crowd rotated out. The bar: **Cloud ≥ ~$22–23bn (holding growth above ~55% vs Q1's 63%)**, evidence that FCF (−47% YoY in Q1 on $35.7bn quarterly capex) is troughing, and no new DOJ-remedy damage. **[V]** Expectations have already reset; implied move is typically ±4–7%. P(positive reaction) ≈ 55–60%.

Its bigger role is **sequencing**: GOOGL reports a week before META and is the only company that can *prove* AI demand at scale before Meta speaks. A strong Cloud print validates the demand curve Meta wants to sell into (bullish read-through); a deceleration below ~55% would re-open the "AI revenue can't absorb the capex" question complex-wide and raise the risk premium on META's own print.

### 4.4 The regime answer

For hyperscalers as a group, Q2 2026 earnings season is **the highest-information three weeks of the summer, with dispersion — not direction — as the main output**. The market will not buy or sell "hyperscalers"; it will re-sort them along the monetization-proof axis, exactly as it did in April. Positioning into the season: GOOGL = modest positive skew (reset expectations, provable narrative); META = two-sided binary (repriced narrative awaiting proof); MSFT = shows up to the same exam with the worst YTD grade and the least new evidence.

---

## 5. Prediction: the chain of events

### 5.1 Modal path (my single most-likely sequence)

1. **Jul 13–15:** Consolidation/digestion of the +15% week; June CPI (Jul 14) prints near expectations (headline relief from post-ceasefire energy, core sticky ~2.9%) — enough to avoid a momentum-unwind extension, not enough to reprice the Fed. META chops in a $635–675 band; the 650-strike call wall and rolled-up put support define the range.
2. **Jul 16:** TSMC beats and guides up on AI (P≈70%) — keeps the "supply-constrained, demand-real" frame alive; META and AVGO catch a bid on the Iris/custom-silicon read-through.
3. **~Jul 13–17:** Meta formally confirms the Q2 date (P≈85% it lands Jul 29–30). Watch for a *pre-earnings quiet-period pattern*: the July news cadence (a leak or launch every 48h) has been deliberate; expect one more product/customer headline before the quiet period as management shapes the narrative into the print.
4. **Jul 22:** GOOGL delivers Cloud ~$22bn+ (P≈65% growth holds ≥55%); stock reaction positive but contained; complex tone improves; META drifts toward the upper band ($660–690) with the April high (689) acting as the pre-earnings ceiling.
5. **Jul 28–29:** FOMC holds (≈85% priced). Then the binary: **META prints a revenue/EPS beat, raises capex to ~$135–150bn, and gives directionally real but numerically incomplete Meta Compute commentary** — my modal read of how a company behaves one quarter after an unplanned leak.
6. **Reaction:** the modal print is a fight between a beat+tailwind (Muse-boosted ads) and a raise+vagueness (capex). Modal outcome: an initial negative jerk on the capex line that finds buyers within days because the salvage-option now exists — net: choppy, mildly positive through early August, i.e., **$640–700 two weeks post-print**.
7. **August:** the $1.4T trial supplies recurring scare headlines (P of an actual crippling award ≈ ~0; P of at least one −3% headline day ≈ 60%); low-liquidity summer tape amplifies.
8. **September:** Iris mass-production start is the next *verifiable* milestone; if confirmed on schedule, it revives the cost-curve narrative into the fall.

### 5.2 Scenario tree (Labor Day horizon, Sep 7, 2026 — base $669.21)

| Scenario | Prob | Path | META @ Labor Day |
|---|---|---|---|
| **A. Confirmation** — CPI benign, TSMC strong, GOOGL Cloud ≥55%, META beats + capex raise *absorbed* by concrete Meta Compute framing (customer/number/segment) | **35%** | Breaks 689 post-print; systematic + fundamental buyers stack; street PTs migrate toward $850–900 | **~735** (+10%) |
| **B. Beat-but-replay** — good quarter, capex to $135–155bn, cloud talk stays vague; April 29 rhyme from a higher price | **30%** | −8–12% event move, then range; floor higher than June (the option now exists); waits for September | **~615** (−8%) |
| **C. Macro/AI-complex shock** — hot core CPI or hike-tail repricing, or TSMC/GOOGL disappoint; momentum unwind round 2 hits the whole complex before META even reports | **20%** | META gives back most of July pre-print regardless of its own news; earnings become a coin-flip from $580–620 | **~575** (−14%) |
| **D. Blowout** — everything in A *plus* capex guide unchanged (the surprise no one models) or an anchor compute customer / external revenue guidance named on the call | **10%** | Melt-up through the Jan high (738) toward the 750 gamma magnet; ATH retest chatter by late August | **~780** (+17%) |
| **E. Exogenous tail** — trial shock/injunction headline, adverse FTC appeal development, DSA fine lands big, or Hormuz re-escalation | **5%** | Narrative-independent de-rating | **~535** (−20%) |

**Probability-weighted expected value ≈ $660 — within 1.5% of Friday's close.** That is the honest headline of this entire report: *the market has, in one week, moved the price to approximately the probability-weighted fair value of the confirmation tree.* What remains is not drift but **variance**: P(META > $669 at Labor Day) ≈ 45–48%; P(> $720) ≈ 27%; P(< $600) ≈ 32%; P(new all-time high > $788 by year-end) ≈ 15–20% (requires A or D *plus* a cooperative macro).

### 5.3 Second-order chain (the moves the first move causes)

- **Neoclouds stay structurally impaired.** Meta pivoting from anchor tenant to competitor is a permanent narrative change for CoreWeave/Nebius (−14%/−17% on day one). Every Meta Compute milestone is a headwind for them; P(neoclouds underperform hyperscalers through summer) ≈ 60%.
- **Inference-price deflation accelerates.** Muse Spark at ¼ pricing forces a response: expect OpenAI/Anthropic price adjustments or capability-tier repackaging within 1–2 quarters. Deflationary for AI app-layer costs (bullish software adopters), margin-compressive for model labs.
- **Custom-silicon read-through hardens.** Iris at mass production validates the Broadcom ASIC franchise (AVGO) and marginally erodes the "NVDA takes all inference" assumption — watch whether NVDA's next print/commentary acknowledges hyperscaler internal silicon as a mix headwind. Not a 2026 revenue event; very much a 2027 multiple event.
- **If Meta Compute succeeds, MSFT has the most to lose narratively** (fourth hyperscaler enters just as Azure's capex is being questioned); if it *fails*, the "overbuild admission" reading retroactively strengthens — Zuckerberg's May "if we overbuilt" sentence remains the single most quotable bear exhibit either way. **[V]**
- **Watch the flywheel claim vs the leak.** The town-hall admission (agents "hasn't really accelerated") is the one data point from *inside* the building. If the Q2 call's tone on agents contradicts it without metrics, discount accordingly; if Meta ships agent usage numbers that refute its own leak, that is scenario-D fuel.

### 5.4 Falsifiable predictions ledger (score me after each event)

| # | Prediction | Prob | Resolves |
|---|---|---|---|
| 1 | Meta officially confirms Q2 date of Jul 29 or 30 | 85% | by ~Jul 17 |
| 2 | June core CPI prints 2.8–3.0%, no Fed repricing shock | 65% | Jul 14 |
| 3 | TSMC beats and raises on AI demand | 70% | Jul 16 |
| 4 | GOOGL Cloud revenue ≥ $22bn and growth ≥ 55% | 65% | Jul 22 |
| 5 | GOOGL positive next-day reaction | 55–60% | Jul 23 |
| 6 | META Q2 revenue ≥ $60bn | 70% | print |
| 7 | META raises 2026 capex guidance | 60% | print |
| 8 | META gives concrete Meta Compute commercial detail (customer, number, or segment guide) | 55% | print |
| 9 | META's realized earnings move exceeds the options-implied move | 63% (base rate) | print +1d |
| 10 | META > $669.21 at Labor Day (Sep 7) | ~47% | Sep 7 |
| 11 | META trades ≥ $720 at some point before Labor Day | ~35% | Sep 7 |
| 12 | META trades ≤ $600 at some point before Labor Day | ~40% | Sep 7 |
| 13 | Neocloud basket (CRWV/NBIS) underperforms META from Jul 10 through Labor Day | 60% | Sep 7 |
| 14 | At least one ≥3% down day on August trial headlines | 60% | Aug 31 |

### 5.5 Kill conditions (what would change this assessment)

- **Bear-case confirmation:** capex raised *without any* monetization framing AND ad growth decelerating below ~22% → the April regime never ended; fade all A/D probability toward B/C.
- **Bull-case confirmation:** a named Meta Compute anchor customer or external-revenue guidance → move A+D from 45% toward 65%+, and the Labor-Day EV from ~$660 toward ~$710.
- **Complex-level kill:** GOOGL Cloud < $21.5bn or growth < 50%, or a TSMC AI-order warning → the demand curve itself is in question; META's stock-specific news cannot outrun that (2022 base-rate lesson: 0-for-2).
- **Macro kill:** core CPI ≥ 3.2% or a live hike discussion at the July FOMC → duration shock to all negative-FCF-trajectory capex stories.

---

## 6. For the tape (levels, from raw data)

- **Resistance:** 689 (April swing high — *the* structural gate; above it, the 2026 lower-high pattern is broken), then 720–738 (January high zone), 750 (standing upside gamma magnet), 788 (ATH).
- **Support:** 643 (200-dma, just reclaimed — first retest is informative), 635 (May high, now support), 620 (long-standing max-pain/battle zone), 600–601 (50-dma + gamma magnet), 559 (last measured gamma flip — below it, dealer hedging flips to accelerant). **[L]**
- **Practical read:** chasing $669 into a three-week event gauntlet buys the top half of the probability distribution at EV≈0. The better-asymmetry entries are the 620–643 confluence on a pre-earnings fade (if the thesis is confirmation), and convexity (long-vol structures) into the print itself given the 63% implied-move-exceedance base rate — noting IV30 ≈ 50% already prices much of this. Post-event, the confirmation branch (A/D) is the trend trade; do not pre-position for it at full size.

---

## 7. Sources & verification appendix

**Adversarially verified [V]** (2 independent Opus refutation attempts each; corrections applied): Bloomberg Meta Compute report + leadership trio (TechCrunch corr.); Jul 1 +8.81%/$612.91/~3x vol; Meta Compute Jan-2026 Threads origin + May 27 "overbuilt" contingency quote; Meta Model API launch Jul 9 + Muse Spark 1.1 pricing $1.25/$4.25; Reuters Iris memo (Sept production, Broadcom/TSMC, 7→14 GW); week +14.8% to $669.21 (corrected from "+11.5%"); Alphabet Q2 call **confirmed Jul 22** (abc.xyz IR) vs META Jul 29 **estimated only** (refuted as "confirmed"); META Q2 consensus (rev ~$60.2bn on $58–61bn guide, EPS ~$7.11–7.18, capex guide $125–145bn, Q1 capex $19.84bn); Q1'26 print (+33% rev, −8.5–10% reaction, ~$107bn new commitments, ~$175bn cap loss); JPM downgrade/FCF projections + BNP capex-raise warning; CoreWeave/Nebius no-resale clauses (~$21bn/~$27bn contracts); GOOGL Q1 Cloud +63%/$20.0bn/backlog $462–468bn/capex $180–190bn/FCF −47%; Goldman GSPRHIMO −18% 2-day + 92nd-pct momentum crowding + BIS June report + Fed hold 3.50–3.75% (Goldman first cut Jun-2027, ~20% hike tail); SemiAnalysis quote (corrected to "only hyperscaler/neolab on track to be world class at all three"); Zuckerberg town-hall leak quote; four-state $1.4T penalty demand.

**Key primary/corroborated URLs:** Bloomberg via [TechCrunch](https://techcrunch.com/2026/07/01/meta-like-spacex-looks-to-turn-excess-ai-compute-into-cash/) · [Alphabet IR Q2 date](https://abc.xyz/investor/news/news-details/2026/Alphabet-Announces-Date-of-Second-Quarter-2026-Financial-Results-Conference-Call-2026-2h_R0kzZHY/) · [Meta AI blog — Muse Spark/Model API](https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/) · [Muse Image launch](https://about.fb.com/news/2026/07/introducing-muse-image-meta-ai/) · [Reuters Iris memo via US News](https://money.usnews.com/investing/news/articles/2026-07-09/exclusive-meta-to-put-ai-chip-into-production-in-september-as-it-looks-to-double-computing-capacity-memo-shows) · [CNBC Iris](https://www.cnbc.com/2026/07/09/meta-to-put-ai-chip-into-production-in-september-report.html) · [SemiAnalysis progress report](https://newsletter.semianalysis.com/p/the-future-of-meta-superintelligence) · [Motley Fool Jul 1 recap](https://www.fool.com/investing/2026/07/06/meta-stock-surged-july-1-report-zuckerberg-cloud/) · [town-hall leak](https://www.fool.com/investing/2026/07/08/mark-zuckerberg-admitted-ai-agents-hasnt-really-ac/) · [$1.4T demand](https://www.benzinga.com/markets/large-cap/26/07/60309780/metas-1-4-trillion-penalty-scare-is-almost-as-big-as-meta-itself) · [neocloud fallout](https://www.actuia.com/en/news/why-the-rumor-of-a-meta-cloud-is-sinking-neoclouds/) · [daily closes](https://stockanalysis.com/stocks/meta/history/) · [JPM downgrade](https://www.cnbc.com/2026/04/30/meta-platforms-gets-a-downgrade-from-jpmorgan-on-massive-ai-spending-forecast.html) · [Goldman AI-trade reversal](https://finance.yahoo.com/markets/stocks/articles/goldman-says-ai-trade-reversal-131007052.html)

**Local raw-data computations [L]:** daily OHLCV through Jul 8 (`data/stocks/*.parquet`), options flow and dealer-gamma summaries through Jul 9 (`data/options_flow/`, `data/polygon_gex/`), 233-event base-rate study, moving averages/levels. Local store lags two sessions; Jul 9–10 prices are web-corroborated to the cent.

**Known residual uncertainties:** META/MSFT/AMZN/AAPL report dates are consensus estimates until IR confirmations; BofA's $22bn/GW figure and several drawdown-chronology details (Q3'25 reaction magnitude, NM verdict, FT equity-raise report) are single-lane sourced **[S]**; the GOOGL Q2 Cloud consensus band (~$22–23bn) is analyst framing, not a compiled consensus print; one research lane's GOOGL total-revenue consensus was internally inconsistent and was discarded rather than repaired.

---

*Prepared with fresh web research (8 lanes, 37 agents, 629 tool calls) + adversarial verification + local raw-tape analysis. No internal research reports were used, per instruction. Prediction probabilities are calibrated judgments, not outputs of a tested model — score them against the ledger in §5.4.*
