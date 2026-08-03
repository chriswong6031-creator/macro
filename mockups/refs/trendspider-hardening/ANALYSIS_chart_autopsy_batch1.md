# TrendSpider Chart-Design Analysis — Images 00–15

**Source:** `/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-trendspider-hardening-pass-af0839/4b0b39df-11cf-4f60-9d62-92903cf7d505/scratchpad/ts_images/`
**Manifest:** `.../ts_images/manifest.json`

**Sample caveat, stated up front:** files `00`–`11` are ordered strictly descending by views (1.07M → 356k); `12`–`15` are not (34.8k, 153k, 262k, 92k). So the first 12 are a *top-performers* sample, not a random draw of TrendSpider's output. Everything below is safe to read as "what their best work does" and unsafe to read as "what they typically do" or as an engagement causal claim.

**Composition:** 13 of the 16 are TrendSpider app charts. Three are not: `05` (SEC filing screenshot), `12` (bare logo card), `15` (Truth Social screenshot). All 13 charts are **exactly 1200×898 px (AR 1.336)** — a fixed export canvas, verified programmatically.

---

## 1. Per-image catalog

| # | Ticker / TF / span | Type | Indicators (precise) | Annotations | Panes | Text↔chart fit |
|---|---|---|---|---|---|---|
| 00 | LCID · 5-min · one session ~08:30–15:30 | Candles | Volume (20, SMA); **VbP (100, visible range)** right-axis profile, red/green split | White measured-move arrow high→low; red callout box `-1.68 (-30.317%) / 6 bars (30 minutes)`; red last-price tag 3.85; LUCID wordmark | price + volume | **Exact.** Caption says −30% in 30 min; the box prints −30.317% and 6 bars |
| 01 | MSFT · Weekly · Jul'19→Jul'26 (7y) | Candles, linear | **Fundamentals (revenue, no_comparison)** green step-boxes; Volume; **P/E Ratio (Trailing), Weekly** pane | White "Revenue Growth" arrow; ~28 auto quarter labels (`Q3'19 +14.0%`…) w/ teal+grey dots; dashed line at 24 in P/E pane; **3 blue-grey circle spotlights** on its touches (Jan'20, Jan'23, Jul'26); bold `24x P/E`; blue-grey support band at price; green tag 393.82; MS logo | price + volume + 1 | **Exact.** "Same valuation as COVID lows and 22/23 lows" = one dashed line + three circles |
| 02 | GOOG · Daily · Jan'25→Jul'26 (19m) | Candles, linear | **200 SMA** (olive, inline-labeled); Volume; VbP profile; **P/E Ratio (Trailing), Daily** pane | Gold circle on price at the 200-SMA touch; gold circle + dashed line in P/E pane; gold `16x P/E`; green tag 319.33; Google logo | price + volume + 1 | Partial — see §3 slippage |
| 03 | ONDS · Weekly · Jan'25→Jul'26 (18m) | Candles, linear | **200 EMA** (orange, inline-labeled); Volume; VbP profile; **Put/Call Ratio donut gauge (0.42)** widget | 2 blue-grey circles on price at the two 200-EMA events; 2 blue rectangles boxing the 2 volume spikes; `Highest weekly volume ever`; dual right-axis tags (red 6.53 last, gold 5.73 = EMA); ONDAS logo | price + volume | **Strong.** "Seen this before" = a boxed + circled analog pair |
| 04 | DUOL · Daily **(LOG)** · Dec→Jul (8m) | Candles, log | **Weinstein Stage Analysis (30, 5, sma)** — 30-week SMA on a daily chart + regime bar-painting; Volume; **RSI (14, 70, 30, close), Daily** (30/50/70 guides, tag 59.90) | `Stage 4` / `Stage 1` text; blue-grey supply→support band; ascending white trendline; inline `30-Week SMA`; Duolingo logo | price + volume + 1 | **Exact.** Regime flip is legible as a *candle-color* flip |
| 05 | — (SEC Schedule 13G) | Document screenshot, 1200×577 | none | **4 yellow highlighter blocks**: issuer "Nebius Group N.V.", filer "NVIDIA Corporation", Sole Voting Power `22,256,412.00`, Sole Dispositive Power. No TrendSpider chrome at all | — | Caption's "22.2M shares" is highlighted; the derived "~10%" is **not** in frame |
| 06 | GOOG · Daily · Jun'25→Jul'26 (13m) | Candles, linear | **200 SMA** (olive); Volume; VbP profile (bars extend left over price); **P/E Ratio (Trailing), Daily** | **3 gold circles** at the three 200-SMA interactions incl. the break; gold circle + dashed line in P/E pane; `24x P/E`; red tag 318.88; Google logo | price + volume + 1 | Partial — same template as `02`, different multiple |
| 07 | SPY · Daily · ~20 Apr→18 Jul (3m) | Candles, linear | Volume; VbP profile; **Squeeze (30, 2, 2, 10, close), Daily** (cyan lollipops, green/orange/red dots); **Momentum Filter (close, 3, 7, 14, 40, 14), Daily** | Single white **arc** (rounding bottom) closed by a straight rim line; blue-grey rectangle over the compressed Squeeze section + `Squeezing`; red tag 750.72; serif `S&P 500` title | price + volume + 2 | Caption is wordless ("My oh my"). Chart carries 100% of the message |
| 08 | NOW · Weekly · Jul'24→Jul'26 (2y) | Candles, linear | Volume; VbP profile; **MACD (12, 26, 9, close), Weekly**; **PoC (visible range)** magenta horizontal line | **3 white arcs** under the lows labeled `LS` / `H` / `RS` (inverse H&S); the PoC line doubles as the neckline; red tag 103.24; ServiceNow logo | price + volume + 1 | **Strong.** Jensen quote "market's got it wrong" ↔ a completed base + MACD curling up |
| 09 | DUOL · Weekly · Oct'21→Jul'26 (4.75y) | Candles, linear | **Fundamentals (revenue, no_comparison)** green step-boxes; **VbP (100, visible range)**; Volume; **PoC (visible range)** pink line | Green "Revenue Growth" arrow; ~19 auto quarter labels (`Q3'21 +40.4%`…`Q1'26 +26.5%`); red tag 122.24; Duolingo logo | price + volume | **Exact.** The joke *is* the divergence — revenue steps climb while price sits at the PoC, both in one panel |
| 10 | MU · Weekly · Mar'23→Jul'26 (3.3y) | Candles, linear | **50 SMA** (salmon, inline-labeled); Volume; **Consecutive Candles (Candle Color)** pane, readout `-4.000 0.000` | Translucent red rectangle around the 4 red weeks; blue-grey circle on the −4 print in the streak pane; red `4 consecutive red weeks`; red tag 865.41; Micron logo | price + volume + 1 | **Best-in-set.** The indicator's y-unit *is* the claim's unit — no VbP used |
| 11 | SNDK · Daily · 22 Dec→20 Jul (7m) | Candles, linear | Volume; VbP profile; **PoC (visible range)** purple line | **3 unlabeled white arcs** (H&S); blue-grey neckline **band** at ~1,500; translucent red circle on the breakdown candle; red tag 1,414.54; Sandisk logo | price + volume | Caption "Getting scary" adds nothing; the drawing is the argument |
| 12 | CMG | Bare logo card, 1200×686 (16:9) | none | none. Pure black frame, Chipotle wordmark, grey `CMG` corner watermark. Not a TrendSpider asset | — | Image contributes zero information; all facts live in the post text |
| 13 | AMZN · Monthly **(LOG)** · 1997→2026 (29y) | Candles, log | **Volume only.** No MA, no oscillator, no VbP | One white ascending trendline anchored at the IPO low; **4 circles**: blue-grey at Oct 2001 / Nov 2008 / Dec 2022, **gold** at the current bar; **serif** labels `1997 IPO`, `Oct 2001`, `Nov 2008`, `Dec 2022`; gold `YOU ARE HERE`; red tag 232.11; Amazon logo bottom-right | price + volume | **Best isomorphism.** Caption `✅2001 ✅2008 ✅2022 ❓2026` = 4 circles, and blue/gold encodes ✅ vs ❓ |
| 14 | ORCL · Weekly · Nov'24→Jul'26 (1.7y) | Candles, linear | Volume; **RSI (14, 70, 30, close), Weekly** (tag 34.37). No MA, no VbP | Solid white full-width horizontal at **119.00** with a bold manual `119.00` label at the right edge; dotted descending trendline on price; dotted **ascending** trendline under RSI lows; `Bullish RSI Divergence`; red tag 120.04; ORACLE logo | price + volume + 1 | **Mismatch** — caption is bearish, the annotation argues bullish. See §3 |
| 15 | — (Truth Social) | Portrait screenshot, 722×1200 (AR 0.602) | none | 4 company names re-colored yellow (Apple/Meta/Amazon/Google) + **2 full-sentence yellow highlight blocks** (the "301 Investigation" clause, the "entirely reversed… substantial TARIFF" clause). Native dark UI kept as-is | — | The post's 3 claims = the 3 highlighted spans, in order |

---

## 2. Synthesis

### (a) Indicator frequency (n = 13 charts; `05`/`12`/`15` excluded)

| Indicator | Count | Charts |
|---|---|---|
| Volume histogram pane | **13 / 13** | all |
| VbP / volume-by-price profile (right axis) | **8 / 13** | 00, 02, 03, 06, 07, 08, 09, 11 |
| Any moving average (**never more than one**) | 5 / 13 | 02 (200 SMA), 03 (200 EMA), 04 (30-wk SMA), 06 (200 SMA), 10 (50 SMA) |
| PoC (visible range) horizontal line | 3 / 13 | 08, 09, 11 |
| P/E Ratio (Trailing) sub-pane | 3 / 13 | 01, 02, 06 |
| Fundamentals (revenue) price-panel overlay | 2 / 13 | 01, 09 |
| RSI (14, 70, 30, close) | 2 / 13 | 04, 14 |
| MACD (12, 26, 9) | 1 / 13 | 08 |
| Squeeze (30,2,2,10) | 1 / 13 | 07 |
| Momentum Filter (3,7,14,40,14) | 1 / 13 | 07 |
| Consecutive Candles (Candle Color) | 1 / 13 | 10 |
| Weinstein Stage Analysis (30,5,sma) | 1 / 13 | 04 |
| Put/Call Ratio gauge widget | 1 / 13 | 03 |
| **Bollinger Bands** | **0** | — |
| **Ichimoku** | **0** | — |
| **ATR bands / Keltner** | **0** | — |
| **Anchored VWAP** | **0** | — |
| **Fibonacci retracement / extension** | **0** | — |
| **Pivot points** | **0** | — |

Pane budget: 3 charts run price+volume only (`03`, `11`, `13`); 8 run price+volume+**one**; exactly one (`07`) runs two sub-panes. **Nothing in the sample exceeds two sub-panes.** The price pane always holds ≥55% of canvas height.

Manual annotation marks per chart: **2–7, median ≈5** (excluding the auto-generated quarter labels on `01`/`09`).

Notable: the brief's hypothesis that anchored VWAP would appear for post-event drift is **not supported** — zero instances, including on `02`/`06`, which are post-earnings charts where it would be the textbook instrument. Their post-event vocabulary is instead `200 SMA + circle spotlight`.

### (b) The house annotation grammar

**Always (13/13 unless noted):**
- Header `TICKER TIMEFRAME` top-right, white caps, letterspaced, bold ticker + lighter timeframe; `(LOG)` appended when log scale (`04`, `13`).
- TrendSpider mark top-left; `©2026 TrendSpider` bottom-left, tiny, ~50% grey. Never over data.
- **Company logo dropped into the largest empty quadrant** — top-center (`03`,`04`,`08`,`09`,`14`), top-left (`01`,`02`,`06`), mid-left (`10`,`11`), bottom-right (`13`, because the top was occupied by price). Real high-res brand assets at ~⅓ canvas width.
- Exactly one right-axis last-price tag; red if down, green if up.
- **Zero gridlines.** No horizontal or vertical grid anywhere in 13/13.
- **Dead space to the right**: 15–40% of the x-axis is empty beyond the last bar, so the price tag + VbP have room and the last candle sits center-right, not jammed at the crop edge.
- MAs labeled **inline, in the line's own color, next to the line** (`200 SMA`, `200 EMA`, `50 SMA`, `30-Week SMA`) — never in a legend box.
- Volume pane present whether or not volume is the argument.

**Never:**
- Two moving averages, or an MA ribbon.
- Bollinger, Ichimoku, ATR/Keltner, Fibonacci, pivots, anchored VWAP — 0 occurrences each.
- A color-key legend box, a data table, axis titles, a "Source:" line, or a burned-in caption bar.
- More than ~2 annotation ink colors beyond candle red/green.
- A chart title inside the plot area (the corner header + logo do that job).
- Crowding: even the densest (`01`, ~28 labels) confines every label to the empty upper-left triangle above the price path.

**The vocabulary is five shapes, reused:**
1. **Translucent circle spotlight** (~40–70px) — "this bar / this touch". Color-coded *by tense*: blue-grey = historical instance, **gold/amber = the current one or the answer**, red = damage. (`01`,`02`,`03`,`06`,`10`,`11`,`13`)
2. **Horizontal zone band** — semi-transparent blue-grey, 10–20px tall. S/R is *never* a hairline. (`01`,`04`,`07`,`11`)
3. **Free-drawn arc** — formations are outlined with curves, not connect-the-dots polylines. H&S (`08`,`11`), rounding bottom (`07`). This is their single most distinctive habit.
4. **Straight trendline** — solid white for the structural line (`04`,`13`), dotted white for the diagnostic/divergence line (`14`).
5. **A 2–6 word text callout** in the annotation's own color: `YOU ARE HERE`, `Squeezing`, `Highest weekly volume ever`, `4 consecutive red weeks`, `Bullish RSI Divergence`, `Stage 4`/`Stage 1`, `LS`/`H`/`RS`, `Revenue Growth`.

**Numbers appear as annotations only when the number is the story** — the measure box on `00`, the manual `119.00` on `14`, the `24x`/`16x P/E` tags. Otherwise numbers stay on the axis.

**Palette:** background near-black desaturated navy (~#16182a, not pure black); up candles bright green ~#3ddc5a, down bright red ~#ea3e3c; volume bars muted slate-blue (~#3a4160) so they never compete; VbP dark red/green at ~35–45% opacity; annotation ink = white, gold (~#d9a441), translucent blue-grey (~#5a7099 @30%), translucent red, magenta for PoC; MA colors olive-yellow / orange / salmon. Axis type is small low-contrast lavender-grey (~#8b8fa8).

**Typography tell worth stealing:** chrome and operational annotations are a humanist sans; **long-horizon/editorial charts switch to a high-contrast serif** — `07`'s "S&P 500" title and every date label on `13` (`1997 IPO`, `Oct 2001`, `Nov 2008`, `Dec 2022`). Serif = history/index; sans = operational. Consistent across both instances.

**Two artifacts they never clean up:** the `Your local time zone` micro-label above the bottom-right axis appears on 13/13 and adds nothing; and `00` ships with the app's semi-opaque settings card overlaying the first ~18% of the session, dimming real candles.

### (c) Indicator choice ↔ analytical angle

In 12 of 13, the indicator selected is the **minimum instrument that makes the caption checkable** — not decoration:

- **`10` MU** — "worst losing streak in over 2 years" → **Consecutive Candles**. The pane's y-value *is* the claim's unit (streak length), so a superlative becomes a visual scan: look for a deeper red bar anywhere since 2023; there is none. No other indicator makes a superlative falsifiable in one image.
- **`01`/`02`/`06`** — valuation claims are *level* claims, so they're drawn as **a dashed horizontal at the claimed multiple** in a P/E sub-pane, with circles on the touches.
- **`09` DUOL** — "dying business looks good" is a *divergence* claim, so revenue step-boxes and price share **one panel**. Splitting them into two panes would have destroyed the argument.
- **`03` ONDS** — an *analog* claim needs two things equal (volume extreme) at one place (the 200 EMA); it gets exactly 2 volume boxes + 2 price circles + the EMA.
- **`08` NOW** — **PoC used structurally, not decoratively**: the point of control is both the volume-based fair-value level and the inverse-H&S neckline, so one magenta line carries a value argument and a trigger argument simultaneously. This is the sharpest single design decision in the set.
- **`04` DUOL** — a *regime* claim gets **Weinstein Stage Analysis**, whose whole ontology is regime labels, and whose bar-painting makes the regime flip legible as a color flip.
- **`13` AMZN** — a 29-year analog claim gets **nothing but log scale and four marks**. Adding indicators would have added noise.

**Where the precision slips — flag these before adopting:**

| Chart | Problem | Severity |
|---|---|---|
| `02` | Caption asserts "cheapest valuation since **Jan 2015**" and "top 20% of lowest P/E in the S&P 500"; the plotted P/E history starts **Jan 2025** and no cross-sectional distribution is shown. Neither claim is visible in the evidence. | major |
| `06` | Caption asserts "cheapest since **September 2025**" on a chart starting **Jun 2025** — the evidence window barely spans the claim, and the P/E pane's own low is ambiguous at that resolution. | major |
| `03` | `Highest weekly volume ever` drawn on a range starting **Jan 2025**. "Ever" is not in frame. | major |
| `14` | The chart's own annotation (`Bullish RSI Divergence`, plus a dotted rising RSI trendline) argues the **opposite direction** from the caption's bearish framing. Only directional contradiction in the set. | major |
| `13` | The 29-year trendline is visually fitted on log price with 4 touches, no band, no method note. On a log axis a fitted line flatters any long uptrend. "YOU ARE HERE" implies a support test the drawing does not establish. | major |
| `05` | The caption's "nearly 10% of the company" is a **derived** figure; only the raw share count is highlighted. The denominator is off-frame. | minor |
| `10` | Cleanest of the set: the streak pane's visible history genuinely covers the ">2 years" claim. No slip. | — |

The house-law read: their charts **assert without disclosure** — no null shown, no window stated, no method note anywhere in 16 images. Under our display-only-until-validated and PIT rules, the *visual grammar* is adoptable but the *epistemic habit* is not. Any analog-count or streak-superlative we render must have its lookback window actually contain the claim, or the claim must be re-scoped to what's plotted — the `03`/`02`/`06` failure mode (superlative wider than the axis) is exactly the kind of thing that reads as a validated claim to a user and would trip `scripts/check_validated_claims.py` territory if the copy ever said so in words.

### (d) Why they survive feed-scroll size

Assume ~500px rendered width (≈42% of the 1200px master):

1. **Fixed 1200×898 (1.336) on 13/13.** Near-4:3, deliberately *taller* than the 16:9 most charting tools export — X crops 16:9 harder, and 4:3 buys more vertical pixels per candle. Consistency also gives the account a recognizable silhouette mid-scroll.
2. **Zero gridlines.** Grid is the first thing that turns to grey mush at 42% scale; deleting it hands the entire contrast budget to the candles.
3. **Deliberate contrast hierarchy**: saturated candles on near-black, *muted* volume so it never competes, one desaturated color for everything else.
4. **One idea, one big shape.** The dominant annotation is always ≥5% of canvas width (arc, circle, band, arrow) — readable as a blob even when no text is.
5. **Annotation text is set 1.5–2× the axis-label size**, in white or gold. The axis furniture recedes; the message survives the downscale.
6. **The company logo is the subject line.** At 500px the Duolingo owl or the Google wordmark is legible when `DUOL DAILY (LOG)` is not.
7. **Fixed lookup position** for ticker+timeframe (top-right, caps, letterspaced) — once you know the account, you know where to glance.
8. **Empty right margin** keeps the payload (last candle, price tag, profile) away from the crop edge.
9. **≤2 sub-panes, price pane ≥55% height.**
10. **≤2 annotation ink colors**, so the eye never has to reconstruct a legend.

One more observation the sample supports weakly but consistently: **the image must carry a *verifiable fact*, not necessarily a chart.** `05` — a highlighted SEC filing with no TrendSpider chrome at all — ranked 6th of 16 at 417k views. `12` — the only item whose image carries no information (bare logo card) — is dead last at 34.8k. Engagement here is confounded by topic, timing, and cadence, so treat this as directional only; but the *design* rule it implies is clean: for a primary-source fact, screenshot the source and highlight exactly the spans that back the caption (`05`, `15` use identical grammar — yellow highlighter, nothing else added, native chrome kept).

### (e) The 5 techniques to adopt

**1. The measure-tool receipt box** (`00`). When a caption makes a numeric claim, draw the measurement on the chart with the tool's actual output: anchor-to-anchor arrow plus a filled box with signed change, percent, and duration/bar count (`-1.68 (-30.317%) / 6 bars (30 minutes)`). The reader never has to trust the prose. Trivial to generate from data we already have, and it is the top-viewed item in the set.

**2. Circle spotlights color-coded by tense** (`13`, `01`, `06`). Translucent circles on every historical instance of a condition, plus a **differently colored** circle on the current one — blue-grey = happened, gold = you are here. It converts "this has happened 3 times before" into a countable object with no legend. Pair it with a caption listing the same instances in the same order (`13`'s four-line ✅/❓ checklist ↔ four circles is the model). This also gives us an honest place to put the disclosure our rules require: the count of instances *is* the n.

**3. Choose the indicator whose y-axis unit IS the claim's unit** (`10`). "Worst losing streak in 2 years" → a consecutive-candles pane, so the superlative becomes a scan. Generalizes directly: a breadth claim gets a breadth pane, a dispersion claim gets a dispersion pane, a drift claim gets a cumulative-drift pane. This is the discipline separating their work from decorated screenshots — and it is the only honest way to make a superlative checkable inside one image. **Adopt with the guardrail their own charts violate: the pane's visible history must cover the claimed window.**

**4. Arcs for patterns, bands for levels** (`11`, `08`, `07` / `01`, `04`, `11`). Two rules that make a chart read as interpretation rather than clutter. Outline a formation with a **free curve** over the highs/lows instead of a peak-to-peak polyline — a curve reads as "shape", a polyline reads as "more lines". And draw support/resistance as a **semi-transparent 10–20px band**, never a 1px line — the band honestly admits the level is approximate, and it stays visible at scroll size where a hairline disappears. Bonus move from `08`: when the level is volume-derived (PoC/HVN), let that one line serve as both the value argument and the pattern trigger.

**5. The restraint stack: one overlay, one sub-pane, zero gridlines, dead space right.** Never two MAs; label the MA inline in its own color instead of a legend; cap sub-panes at two and keep the price pane ≥55% of height; leave 15–40% of the x-axis empty past the last bar. Plus the serif/sans split — serif for long-horizon and index-level editorial charts, sans for operational ones. This stack is the entire reason a 3-indicator chart still reads at 500px, and it maps cleanly onto our glance-tier doctrine: one shape, one plain-word callout, technicals demoted.

---

**Things in this set worth *not* copying:** the `Your local time zone` artifact on 13/13; the app settings panel obscuring live candles on `00`; and — most importantly — the practice of asserting a superlative ("ever", "cheapest since 2015", "since September 2025") whose evidence window is not on the axis. Three of thirteen charts do this, and it is exactly the failure our display-only-until-validated law exists to prevent.
