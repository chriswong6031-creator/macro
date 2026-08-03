I've studied all 16. Here is the complete analysis.

---

# TrendSpider Chart-Design Analysis — Images 16–31

**Corpus:** 16 images, 10 price charts + 6 non-chart cards. All 10 price charts are exactly **1200×898 px (4:3)** — a fixed export preset, not incidental. Non-chart formats use three other canvases (1200×686 logo card, 1200×674 deck screenshot, portrait screenshots).

**Sampled palette (exact):** chart background `#1c1b29` (near-black indigo), up candle `#b8fa88` (lime), down candle `#d94e49` (coral), annotation `#ffffff` pure white. Sidekick sub-brand: background `#242424`, series cyan `#00f6ff` / orange `#ff9400`.

---

## Part 1 — Per-image catalog

### Price charts (10)

| # | Ticker / TF | Span & bars | Indicators (precise) | Annotations | Text↔chart relationship | Views |
|---|---|---|---|---|---|---|
| **16** | ASTS **WEEKLY** | Feb '25→Jul '26 (~72 wk bars); axis runs to Jan '27 | Volume-by-Price (right, red/green split, unlabeled); volume pane (flat blue-grey); **MACD (12,26,9,close), Weekly** — blue MACD + orange signal, no histogram | 1 white ascending trendline (Apr '25→Jul '26 support), **broken**; translucent red rectangle boxing the breakdown candle; red dotted horizontal to right-axis tag `55.01` | "Oh dear god 🩸 $ASTS" — text carries **zero** analysis. The chart argues alone: 15-month support snapped by one candle, and the profile shows a volume air-pocket below the break. Caption is pure affect. | 97.8k |
| **19** | TSLA **WEEKLY** | Mar '25→Jul '26 (~72 bars); axis to Mar '27 | VbP (right); volume pane; **no oscillator pane** | Symmetrical triangle (2 white converging trendlines); blue-grey **glow disc** on the disclosure candle; thin white leader-line → callout "Burry discloses short position on $TSLA"; **red measurement box `−95.09 (−23.320%) / 2 bars (2 weeks)`**; red tag `313.03` | "Perhaps Burry does still got it..." — the *entire* claim is the annotation: dated cause marker + arithmetic effect. Text supplies only snark. Best cause→effect specimen in the set. | 165.7k |
| **21** | META **MONTHLY** | Jan '19→Jul '26 (~91 monthly bars); axis to 2028 | VbP (right); volume pane; **Squeez (20,2,2,10,close), Monthly** — zero-line dots (red=squeeze on / green=off) + cyan/orange momentum bars; **Put/Call Ratio donut gauge `0.46`** floating as a card in upper-left whitespace | Symmetrical coil (2 thin white trendlines, 2024–26); grey highlight rect over the last 7 squeeze dots + white text "7 month squeeze"; green tag `646.01` | "7 month squeeze on $META has **options traders** interested 👀" — two claims, two matched objects: the squeeze count is boxed *and* counted; "options traders" is instantiated by the P/C donut. Tightest text↔chart mapping in the corpus. | 178.7k |
| **23** | LMT **DAILY** | Jul '25→Jul '26 (~250 bars); axis to Oct '26 | VbP (right); volume pane; **Momentum Filter (close,3,7,14,40,14), Daily** — red/green/white histogram + thin blue smoothing line | Falling wedge (upper descending from Mar '26 high + lower rising support from Aug '25); tall green breakout candle piercing the upper line; green tag `570.65` | "ripping out of the **wedge** after an earnings double beat" — the wedge is drawn, the "ripping out" is the pierce. Momentum pane's lone tall green right-edge bar independently confirms. **No earnings marker drawn** despite earnings being the cause. | 62.9k |
| **24** | PANW **WEEKLY** | Jan '24→Jul '26 (~135 bars) | **"Insider Trades On Chart"** declared in red under the logo → green `buy` pill on the bar; volume pane. **No VbP, no oscillator, no MA** — deliberately stripped | Dark-green translucent rect = the ~2.3-year $130–145 accumulation shelf; green `buy` marker at its right edge; white arrow → "CEO $10M Buy"; white measurement arrow + **green box `+207.22 (+136.807%) / 15 bars (3 months 2 weeks)`**; green tag `358.68` | "$PANW simply hasn't stopped ripping **since** the CEO dropped $10,000,000" — "since" is literally an arrow from a dated marker; "hasn't stopped ripping" is quantified. Two-object chart, top-3 performer. | 250.9k |
| **25** | NOW **DAILY** | 9 Feb→27 Jul (~120 bars); axis to 5 Oct; **day-precision fortnightly x-ticks** ("9. Feb / 23. Feb") | VbP (right); volume pane; **no oscillator**; **Value Area High / Value Area Low** horizontals in cyan with inline left-anchored text labels sitting *on* the lines | Ascending channel (2 thin light-blue parallels); **five soft green glow discs**, one per higher low; green tag `98.08` | "Quietly printing **higher lows** since early April 👀" — the 5 discs *count* the higher lows; the channel proves "since early April." The VAH/VAL adds an argument the caption never makes (price sitting at value-area low). **Highest-viewed chart in the set.** | 251.8k |
| **26** | NFLX **5-MIN** | One session, 10:00→18:00, post-market region shaded as a lighter vertical band | Volume pane only. **No MA, no oscillator, no VbP** — maximally stripped for an event chart | Floating **"AH Change" info table** (bordered card: Session Close 74.35 / Current Candle 67.94 / Last Candle Time `16:20` in yellow / **AH Change −8.62%** on a red-filled cell); red tag `67.85`; NETFLIX wordmark placed in the dead zone the crash created | "OUCH 🩸 $NFLX getting smoked, now down -8.6%" — the table **restates the caption's number inside the image**, so the chart survives being screenshotted away from the tweet. Zero drawn annotation; the red waterfall does the work. | 177.2k |
| **27** | MU **DAILY** | 3 Nov→13 Jul (~175 bars); axis to 10 Aug | **50 SMA** (thin salmon line) with inline same-color text label "50 SMA" placed on the curve — **no legend box**; volume pane; **Multi-Length Alignment Oscillator (14,0,50,80), Daily** — blue/red gradient histogram | **Five blue-grey glow discs**, one per prior 50-SMA touch/reclaim, including the live one at the right edge; green tag `977.56` | "It's a dogfight **at the 50**... Who you taking?" — "the 50" is labeled on the line; the 5 discs establish the base rate (tested 5×, held 5×). Chart supplies the prior, text supplies the question. Note the oscillator has just flipped red — a counter-signal the caption doesn't claim. | 104.8k |
| **28** | SNDK **DAILY** | 9 Mar→27 Jul (~100 bars); axis to 7 Sep | Top-left legend block: **`EMA (200, 0, close)`** (green text) + **`VbP (100, visible range)`** (blue text); 200 EMA drawn gold; VbP right; volume pane; **MACD (12,26,9,close), Daily** | Gold **glow disc** at the exact price/EMA intersection; inline gold text "200 EMA"; **second right-axis tag in gold `998.35`** marking the EMA's own value, below the green last-price tag `1,205.01` | "highest trading volume in months, **right at the 200EMA** 👀" — both claims independently checkable in-frame: volume pane's right-most bar is visibly the tallest since March; the glow disc + gold axis tag pin the level numerically. | 101.0k |
| **29** | OSCR **DAILY** | 2 Mar→20 Jul (~105 bars); axis to 17 Aug | Legend: **`MA Cloud (EMA, 9, 21, 0, close)`** (green) / **`VbP (100, visible range)`** (blue) / **`Minervini Trend Template (yes)`** (grey). Cloud renders as a dark-green translucent 9/21-EMA ribbon. VbP right; volume pane; **MACD (12,26,9,close), Daily**. **Candles are NOT green/red** — a relative-strength heat gradient (deep red→orange→yellow→pale blue→cyan) showing the trend maturing | **Minervini Trend Template scorecard panel**: bordered card, header "Minervini Trend Template (D) - 10/10", 10 named criteria each with a green ✓ (RP>70, Price>SMA50/150/200, SMA50>150, SMA50>200, SMA150>200, Price 30%>52W Low, Price w/in 25% of 52W High, SMA200 Rising), then **"Current Values:"** RP 96.8 / Price vs 52W High −5.9% (red) / Price vs 52W Low +191.3% (green). Plus two short white descending trendlines over the two bull-flag consolidations; green tag `31.15` | "Checking every box ✅ $OSCR" — the panel **is** the caption, rendered as 10 literal checkmarks. Highest information density in the corpus, and it works only because the checklist is a *pre-registered, publicly named, externally owned* rule set. | 52.2k |

### Non-chart formats (6)

| # | Format | Contents & design | Text relationship | Views |
|---|---|---|---|---|
| **17** | **Document + highlighter** (682×1200 portrait) | Screenshot of a Truth Social post, dark navy `#09071d`, white body text, avatar/name/verified badge, generous line-height. **Yellow highlighter** on exactly three phrases: "TSMC", "additional 100 Billion Dollar Investment... in Arizona.", "265 Billion Dollars." | Caption restates the highlighted numbers. The highlighter converts a wall of text into a 3-second read. Portrait aspect = mobile-native. | 103.2k |
| **18** | **Logo card** (1200×686) | Pure black `#000`, Reddit lockup centered, ticker `RDDT` top-left in bold caps **in the brand's own orange**. Zero data in the image. | Post carries every number (EPS/sales beat, 🟥 −7.30%). Image is a scroll-stopping identity token. | 138.8k |
| **20** | **Product/provenance screenshot** (617×1165 portrait) | TrendSpider Sidekick panel: `#242424`, amber accent. "Analyst personality: **Warren, the Long Term Investor**"; "Model size: **Claude Opus 5.0**" on a 5-stop slider pushed to max; 3 suggestion cards; prompt box with **the user's exact question yellow-highlighted**; footer "279 more messages available until Aug 14, 2026." | Caption reports the model's stock picks; the image proves the provenance (which model, which persona, verbatim prompt). Highlighter again isolates the one load-bearing line. | 48.6k |
| **22** | **Sidekick analytics chart** (1024×680) | Grouped bar chart, 6 banks × 2 series. Cyan `#00f6ff` EPS Surprise %, orange `#ff9400` Revenue Surprise %. **Different design system from the price charts**: grey bg, rounded-rect plot container with faint dashed border, dashed gridlines on both axes, monospace-ish axis/legend type, bold white title top-left, **"Sidekick" chip badge top-right** replacing the TrendSpider logo. No data labels, no units on bars. | "Q2 saw the banks cashing in... 💰" — chart carries the whole claim; GS towers at 49% EPS surprise. | 43.5k |
| **30** | **Document + highlighter** (1200×674) | Tesla Q2 shareholder-deck page 3, grey `#595959`, two columns HIGHLIGHTS / SUMMARY. **Yellow highlighter** on two sentences: the $100B TTM revenue first, and "Tesla Semi remains on track for production this year at our new factory in Nevada." | Caption quotes the highlighted sentence **verbatim**. They screenshot the primary source rather than paraphrase — the receipt is the point. | 41.7k |
| **31** | **Logo card** (1200×686) | Identical template to #18: black, Google logo centered, `GOOG` top-left in the brand's amber. | Post carries all eight figures. **Highest-viewed image in the corpus (255.5k) — and it contains no information whatsoever.** | 255.5k |

---

## Part 2 — Synthesis

### (a) Indicator frequency table (n = 10 price charts)

| Element | Count | Charts |
|---|---|---|
| Volume pane (bottom, uncolored blue-grey) | **10/10** | all |
| Right-axis last-price tag (green up / red down) | **10/10** | all |
| Volume-by-Price / Volume Profile (right, red/green) | **7/10** | 16, 19, 21, 23, 25, 28, 29 |
| Any lower study pane | 6/10 | 16, 21, 23, 27, 28, 29 |
| — MACD (12,26,9,close) | 3 | 16, 28, 29 |
| — Squeez (20,2,2,10,close) | 1 | 21 |
| — Momentum Filter (close,3,7,14,40,14) | 1 | 23 |
| — Multi-Length Alignment Oscillator (14,0,50,80) | 1 | 27 |
| Any moving average | 3/10 | 27 (50 SMA), 28 (200 EMA), 29 (MA Cloud 9/21 EMA) |
| Volume Profile–derived horizontals (VAH/VAL) | 1/10 | 25 |
| Options Put/Call gauge | 1/10 | 21 |
| Insider-trades overlay | 1/10 | 24 |
| Rule-set scorecard panel | 1/10 | 29 |
| Live-state info table | 1/10 | 26 |
| **RSI** | **0/10** | — |
| **Bollinger Bands** | **0/10** | — |
| **Ichimoku** | **0/10** | — |
| **ATR bands / Keltner (drawn)** | **0/10** | — |
| **Fibonacci retracement/extension** | **0/10** | — |
| **Earnings / news event flags** | **0/10** | — |

| Annotation object | Count | Charts |
|---|---|---|
| Trendlines (incl. paired patterns) | 6/10 | 16(1), 19(2), 21(2), 23(2), 25(2), 29(2) |
| Glow discs (translucent touch markers) | 4/10 | 19(1), 25(5), 27(5), 28(1) |
| Rectangles / zones | 3/10 | 16, 21, 24 |
| Text callout with leader-line arrow | 2/10 | 19, 24 |
| Inline text label on the object itself | 4/10 | 25, 27, 28, 21 |
| **Measurement box (Δ, %, bar count, elapsed time)** | 2/10 | 19, 24 |
| Horizontal S/R lines | 1/10 | 25 |
| Pattern *name* written on the chart | **0/10** | — |

### (b) The house annotation grammar

**Always:**
- **Fixed 1200×898 (4:3)** for every price chart. One preset, no exceptions.
- **Header triad:** TrendSpider mark top-left → indicator legend directly beneath it (only when non-obvious studies are on) → `TICKER TIMEFRAME` top-right in letterspaced caps, **ticker bold white, timeframe light weight**. 10/10.
- **Footer triad:** `©2026 TrendSpider` bottom-left micro-type; `Your local time zone` micro-caption above the x-axis right; x-axis labels in muted grey.
- **The company's own logo/wordmark placed in whatever region of the chart is empty** — upper-left (16, 24, 27), top-center (19, 21, 23, 25, 28, 29), or the void the move itself created (26, where NETFLIX fills the space the crash opened). It is a whitespace-filler *and* an instant identity anchor at thumbnail size.
- **A future runway:** the last bar sits at ~70–80% of frame width, leaving 20–30% empty to the right. The volume profile is drawn **into that runway**, extending leftward from the right edge, so it never occludes a single candle.
- **Right-axis price tag** on every chart, colored by direction. Where a *level* matters (28), it gets its **own second tag in the indicator's color** (gold `998.35`) so the level is a number, not a picture.
- **Pure white is reserved exclusively for annotation.** Candles are lime/coral; indicators are gold, cyan, blue, salmon, green. Nothing in the *data* layer is ever white. This is the single highest-leverage rule in the whole system.
- **Zero gridlines in the price pane.** The only straight lines on the chart are the ones a human drew.

**Never:**
- Never write the pattern's name on the chart. They draw the wedge; the *tweet* says "wedge" (23). They draw the higher lows; the tweet says "higher lows" (25). Zero redundancy between caption and canvas.
- Never more than **~3 annotation objects**. The densest chart (25) is a channel + one repeated dot motif + two labeled horizontals — and the 5 dots read as one object.
- Never stack indicators. Max one MA construct, max one lower pane. Never an MA *and* Bollinger *and* RSI.
- Never Fibonacci, never Ichimoku, never RSI — despite these being the retail-charting defaults. The absence is a positioning choice.
- Never an earnings/news event flag from a data feed — even on 23 where earnings caused the move. Events appear only as (a) a real transaction marker from a real dataset (24, insider `buy` pill) or (b) a hand-written callout at a specific bar (19).
- Never a legend when the label can sit inline on the object (27's "50 SMA" written on the curve, 25's "Value Area High" written on the line).
- Never a light background, never a second font family.

### (c) Precision of indicator→angle matching

This is where the work is genuinely disciplined — the indicator set is chosen *per post* to be the minimum that proves the specific sentence.

- **Claim is about a level** → the level is the only overlay. 28 says "at the 200EMA," so the chart carries exactly one MA, one glow disc at the touch, and a gold axis tag with the level's number. 27 says "a dogfight at the 50," so: one 50 SMA, five discs, nothing else on price.
- **Claim is about compression + options positioning** → 21 carries the *two* studies that measure exactly those two things (Squeez for compression, Put/Call donut for positioning) and nothing else. A P/C gauge appears on precisely the one chart whose caption mentions options traders.
- **Claim is about a dated human decision** → 24 turns on the Insider Trades overlay and turns *everything else off* (no profile, no oscillator, no MA), because any additional line would compete with the one marker that matters.
- **Claim is about a single-session shock** → 26 strips to bare candles + volume and adds a state table. On a 5-minute event chart, a 200 EMA would be noise.
- **Claim is a checklist** → 29 renders the checklist, and adds the MA Cloud because the ribbon visually corroborates the "price > all MAs, MAs stacked" rows.
- **Claim is a breakdown** → 16's MACD pane is not decorative: both lines are rolling over and the fast line has just crossed below zero, which is the only element on the chart that says the break is *confirmed* rather than a wick.
- **Timeframe matches claim horizon rigorously:** "7 month squeeze" → monthly (21). "worst losing streak on the weekly" family → weekly. "at the 200EMA" → daily. "down -8.6% after hours" → 5-minute. Zero mismatches in 10.
- **Even the axis granularity adapts:** 25's 5-month daily chart uses `9. Feb / 23. Feb` fortnightly day-ticks instead of month names, so the reader can date each higher low.

### (d) Why these are legible at feed-scroll size

1. **Luminance hierarchy is single-purpose.** Background is the darkest thing on screen; candles are mid-saturation; white is reserved for annotation only. At 400px wide the white lines survive when everything else has blurred to texture.
2. **No gridlines in the price pane** — so a drawn trendline is the *only* straight line in the frame and the eye lands on it in under 200ms.
3. **4:3, not 16:9.** More vertical pixels means a 3-pane stack (price / volume / oscillator) still leaves the price pane with ~55% of the height. A 16:9 export would crush the panes into illegibility.
4. **One number is always duplicated as a colored axis tag** — even at thumbnail size you can read the price without reading an axis.
5. **The company logo is the ticker.** Recognizing the Netflix wordmark is faster than parsing "NFLX." The logo also absorbs the empty space, so the frame never looks half-used.
6. **The payoff bar is never at the frame edge.** The future runway puts the decisive candle at ~75% width, with breathing room, so it reads as a moment rather than a truncation.
7. **Object count ≤ 3.** Nothing to disambiguate. The reader gets one idea.
8. **The caption and the canvas never repeat each other**, so the reader's two channels (text, image) carry different halves of one argument and neither is wasted.

### (e) The 5 most distinctive techniques to adopt

**1. Cause marker + quantified effect box (#19, #24).**
A dated pill at the causal bar, a leader-line naming the event, and a box giving `Δ absolute (Δ%) / N bars (elapsed calendar time)`. This is precisely the render shape of a PIT-honest forward-window row: the marker is the entry date, the box is pure arithmetic from it. Both charts using it are top-3 performers.
> **Adoption caveat — this format is a selection-bias engine if adopted naively.** TrendSpider posts only the markers that worked. If we render measurement boxes, they must be emitted for **every** marked event in the ledger (including the losers), driven by the nightly ledger advance — never hand-picked per post. Otherwise the visual grammar itself manufactures a track record we haven't earned, which is exactly what display-only-until-validated exists to prevent.

**2. The touch-count glow disc (#25, #27).**
Instead of asserting "support held," mark **every prior test** with a soft translucent disc and let the reader count. It converts an assertion into a countable in-frame base rate. This is the most directly house-law-compatible device in the corpus: if a level was tested 5 times and failed 2, you draw 5 discs in two colors and the honest base rate is legible without a sentence — a genuine "nulls printed, not hidden" rendering, and one that survives the plain-word glance-tier budget because it needs no words at all.

**3. Named, externally-owned rule-set scorecard (#29).**
A bordered panel: header with `name (timeframe) — k/n`, one row per **pre-registered, publicly named** criterion with a pass/fail glyph, then a `Current Values:` block printing the raw numbers behind the checks. It makes no promotion claim, cites a rule set it doesn't own, and prints the values so each line is disputable. This is the display-tier pattern done correctly, and it is the right render for our gauntlet criteria — **including the ✗ rows**, which the reference chart never has to show because 10/10 was cherry-picked.

**4. In-frame restatement so the image survives decontextualization (#26, #28).**
Every number the caption claims is re-rendered inside the image: the AH Change table restates `−8.62%`; the gold axis tag restates the EMA's value as `998.35`. A screenshot separated from its post is still complete and still attributable. Directly portable rule for our marketing/social cards: **any stat in the copy must also be printed on the card, and any level named in prose gets its own axis tag in the indicator's color.**

**5. White reserved exclusively for annotation + zero gridlines in the price pane (all 10).**
Data uses lime/coral/gold/cyan/blue; pure white is only ever a human-drawn line, arrow, or callout. Two config lines, and they are the reason these charts read at thumbnail size. Pairs with the *future-runway layout*: reserve 20–30% of frame width to the right of the last bar, render the volume profile into that runway so it never occludes price, and drop the identity logo into whatever region remains empty.

---

## Part 3 — Two flags for the orchestrator

**Flag 1 — #20 is a competitor shipping LLM-originated rankings.** The Sidekick screenshot plus its caption ("Opus 5 gave its answer: $AMP, $LMT, $IT, and $GOOGL ranked at the top of its list") is an LLM originating a ranked security list as the product. Our CLAUDE.md is explicit: *"LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations"* (A7). **Adopt the format, never the practice.** The genuinely good idea in that image is the **provenance panel** — model name, analyst persona, verbatim prompt, and remaining quota all rendered in-frame. That format is worth stealing for our Mastermind/brain surfaces, where it would make grounding auditable. The ranking behavior is a standing kill for us.

**Flag 2 — the Sidekick sub-brand is a design pattern worth copying (#20, #22).** Sidekick output uses a visually **incompatible** design system from the engine charts: grey `#242424` vs navy `#1c1b29`, cyan/orange vs green/red, dashed gridlines vs none, monospace-ish type vs the chart's grotesque, and a `Sidekick` chip badge that *replaces* the TrendSpider logo. A reader can never mistake AI-generated analytics for engine output. That maps cleanly onto our display-tier vs authority-tier separation and is a cheaper enforcement mechanism than copy discipline alone.

**Non-finding, stated as a hypothesis only:** the two highest-viewed charts (#25 NOW 252k, #24 PANW 251k) both have **no oscillator pane**, while the two lowest (#29 OSCR 52k, #23 LMT 63k) are the two most indicator-dense. n=16 and heavily confounded by ticker fame (GOOG/TSLA/META/NFLX are mega-caps; OSCR and LMT are not) and by news-cycle timing. This is not evidence that simpler charts perform better — it is a testable question, not a result.
