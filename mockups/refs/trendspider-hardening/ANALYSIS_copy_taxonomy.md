# @TrendSpider Post-Corpus Analysis (n=396)

Source: `/private/tmp/.../scratchpad/ts_corpus.json` + `trendspider_tweets.jsonl` (full field set, incl. `createdAt` and nested `quoted_tweet` objects). Analysis scripts: `.../scratchpad/an2.py` (taxonomy), `.../scratchpad/an3.py` (Q2–Q7). Chart images: `.../scratchpad/ts_images/` (32 files, 23 with legible timeframe labels).

---

## 0. Corpus provenance — three corrections to the brief before any number is used

| Brief says | Corpus says | Evidence |
|---|---|---|
| "13 days" | **19.90 days** (Tue Jul 14 03:00Z → Mon Aug 03 00:30Z 2026) | `createdAt` min/max |
| "~30 posts/day" | **19.9/day**; median full UTC day = **17**; range 14–33 | 396 / 19.90 |
| implied complete window | **cap-truncated sample** | `pull_trendspider.py:19` `MAX_TWEETS = 400`; the pull returned exactly 400 → the cap bound, so the window is truncated at the old end |

Two further coverage gaps that constrain what can be concluded:

- **Zero replies in the corpus** (`isReply: True` count = 0; `conversationId == id` for all 396). The `last_tweets` endpoint excludes replies, so native reply-threading — a plausible fourth follow-up mechanic alongside self-quotes — is **invisible**, not absent. Any claim that they "don't thread" is unsupported.
- 4 self-retweets were stripped (400 → 396). All 396 are `Twitter for iPhone`.

**View-accrual confound: checked and small.** Median views by 2-day age bucket run 69k → 108k with no monotone trend, so views substantially settle inside ~2 days and cross-post comparison is sound. The single exception is the final post (`$RIVN`, 13,029 views, 0.5h old at pull) — it is the corpus minimum purely because it is unsettled. **Exclude it from any tail analysis.**

Reach distribution (all 396): p10 44,237 · p25 53,855 · **median 81,735** · p75 128,840 · p90 217,941 · max 1,066,688. Total 44,719,640 views. The top 40 posts carry **31.0%** of all views; the bottom 200 carry 24.9%.

**Classifier accuracy:** taxonomy is regex-derived then hand-verified bucket-by-bucket against full text dumps. Residual misassignment ≈ 4–5%, concentrated at the `ticker_news_reaction` / `chart_*` boundary (a post that both reports a fundamental event and shows a chart). Counts below are ±2 in those buckets.

---

## 1. POST-TYPE TAXONOMY

13 types. `medV` = median views; `medB` = median bookmarks; `selfQ` = how many are self-quote-tweets; `img` = how many carry a photo.

| # | Type | n | share | medV | medL | medB | medRT | selfQ | img |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `chart_technical` | 66 | 16.7% | 98,441 | 435 | 52 | 28 | 49 | 66 |
| 2 | `chart_quip` | 55 | 13.9% | 103,837 | 465 | 44 | 29 | 40 | 53 |
| 3 | `earnings_print` | 48 | 12.1% | 50,312 | 145 | 8 | 8 | 13 | 46 |
| 4 | `product_promo` | 44 | 11.1% | 56,355 | 58 | 15 | 5 | 17 | 26 |
| 5 | `ticker_news_reaction` | 30 | 7.6% | 78,514 | 322 | 26 | 24 | 19 | 29 |
| 6 | `chart_stat_extreme` | 28 | 7.1% | 93,609 | 326 | 35 | 18 | 26 | 28 |
| 7 | `breadth_macro` | 28 | 7.1% | 62,637 | 327 | 17 | 26 | 9 | 27 |
| 8 | `breaking_news` | 26 | 6.6% | 88,742 | 475 | 21 | 42 | 2 | 21 |
| 9 | `meme_quip` | 25 | 6.3% | 62,733 | 446 | 20 | 20 | 4 | 17 |
| 10 | `news_report` | 19 | 4.8% | 59,738 | 211 | 11 | 18 | 1 | 16 |
| 11 | `valuation_obs` | 12 | 3.0% | **161,427** | 635 | 56 | 47 | 9 | 12 |
| 12 | `livestream_promo` | 9 | 2.3% | 141,924 | 37 | 4 | 3 | 0 | 0 |
| 13 | `exec_quote` | 6 | 1.5% | 97,990 | 297 | 22 | 25 | 4 | 6 |

**The chart family (types 1, 2, 6, 11) = 161 posts = 40.7% of the account.** That is the unit a ticker-chart post engine is competing with.

### Per-type exemplars and structural formulas

**1. `chart_technical` (66, 16.7%, medV 98,441)** — names a specific structure or level.
> `$NOW looking to reclaim key EMAs as momentum picks up 👀` (293,504)
> `Overlaid the weekly MACD on the daily chart and all of a sudden I don't feel so good... $QQQ` (265,559)

Formula: `[structure/level verb] + [named indicator or MA] + [👀 or 😬 stance glyph] + $TICKER` → chart. Never a target, never an entry. Highest **bookmarks-per-1k-views of any class (0.55 vs 0.30 corpus)** — these are the posts people save.

**2. `chart_quip` (55, 13.9%, medV 103,837)** — the signature unit. Caption ≤14 words carrying only a stance; the chart carries 100% of the information.
> `My oh my 😲 $SPY` (401,685)
> `Getting scary 😬 $SNDK` (355,999) · `Phew 😮‍💨 $NOW` (311,685)

Formula: `[3–8 word emotional beat] + [emoji] + $TICKER` → chart. Verified against the image: the `$SPY` post's chart is `SPY DAILY` with a cup drawn, a Squeeze panel annotated "Squeezing", volume profile, and a momentum filter. **The tweet contains no claim at all; the chart makes every claim.**

**3. `earnings_print` (48, 12.1%, medV 50,312)** — the numeric card. Highest-volume, lowest-value type.
> `$TSM Q2 EARNINGS DOUBLE BEAT 🔥 / EPS: $4.31 vs $3.77 est / REV: $40.20B vs $39.76B est / Gross Margin: 67.7%...` (286,620)
> `$CMG Q2 Earnings Double Beat ✅ / Adj. EPS: $0.33 vs $0.32 est / Sales: $3.349B vs $3.331B est / 🟩 +5.87%` (34,838)

Formula: `$TICKER [Q#] EARNINGS [verdict word] [🔥/🩸/✅]` ⏎⏎ `EPS: X vs Y est` ⏎ `Sales: X vs Y est` ⏎⏎ `[🟩/🟥] ±x.xx%`. Verdict vocabulary is a fixed ladder: `GOD CANDLE` > `SMASHED`/`CRUSHED` > `DOUBLE BEAT` > `MIXED` > `MISS`/`DUMPING`. **42 of 48 land in the ET 16:00 hour.** Engagement floor: 2.39 likes/1k, 0.13 bookmarks/1k.

**4. `product_promo` (44, 11.1%, medV 56,355)** — 1.02 likes/1k, the engagement floor. Peaks at **ET 23:00 (17 of 44)** — parked in the dead hour, out of the way of content.

**5. `ticker_news_reaction` (30, 7.6%, medV 78,514)** — event + price consequence, prose form.
> `Tesla is now down more than -20% since Burry disclosed a short position 🌶️ $TSLA` (290,305)

**6. `chart_stat_extreme` (28, 7.1%, medV 93,609)** — a records/streak statistic as the whole payload.
> `Worst losing streak for Micron $MU on the weekly in over 2 years 😬` (359,502)
> `Oracle $ORCL has now officially suffered its worst weekly losing streak since 1997 as price breaks down to 2 year lows 🩸` (217,941)

Formula: `[superlative] + [named ticker] + [timeframe] + [historical anchor: "since YYYY" / "in over N years"] + [🩸/😬]`. **Second-highest top-decile hit rate of any feature at 28.6%.**

**7. `breadth_macro` (28, 7.1%, medV 62,637)** — sector scoreboard or index state. **0 of 40 top-decile posts. Lift 0.00x.**
> `July has been nothing but brutal to chip and memory stocks 🩸 / Month-to-date change % / 🔴 $SNDK -50% / 🔴 $KLAC -40%...` (151,129)

**8. `breaking_news` (26, 6.6%, medV 88,742)** — highest retweets-per-1k (0.34) and the corpus maximum.
> `BREAKING: Lucid $LCID stock crashes -30% in 30 minutes on bankruptcy news 🩸` (**1,066,688** — the single biggest post)

**9. `meme_quip` (25, 6.3%, medV 62,733)** — no ticker, no number. **Highest likes/1k of any class (6.30)** but near-zero reach lift.
> `that's all i needed to hear` (667,586) · `i'm TRYING` (78,144) · `bow down peasant` (71,561)

**10. `news_report` (19)**, **11. `valuation_obs` (12, medV 161,427 — the highest-reach type in the corpus)**, **12. `livestream_promo` (9, medV 141,924 but 0.32 likes/1k — reach without engagement; link posts)**, **13. `exec_quote` (6)**.

> `valuation_obs`: `Buying Microsoft here means you're paying the same valuation as: / -2020 Covid lows / -2022/23 Bear Market lows / $MSFT` (848,481)

---

## 2. LONG-TERM vs SHORT-TERM

Two independent measurements, and they disagree in a way that is itself the finding.

**Text-language measurement** (denominator = 161 chart posts):

| | n | share | medV |
|---|---|---|---|
| long-horizon language only | 41 | 25.5% | 101,570 |
| short/intraday language only | 6 | 3.7% | 63,396 |
| both | 4 | 2.5% | 63,432 |
| **neither — horizon never stated in text** | **110** | **68.3%** | 100,732 |

**Image ground truth** — 23 legible `TICKER TIMEFRAME` labels from the top-right of the chart PNGs:

| Timeframe | n | share |
|---|---|---|
| 5-MIN | 2 | 8.7% |
| DAILY | 10 | 43.5% |
| WEEKLY | 9 | 39.1% |
| MONTHLY | 2 | 8.7% |
| **WEEKLY + MONTHLY** | **11** | **47.8%** |

**The reconcile: the horizon lives in the chart, not the copy.** Two-thirds of chart posts state no timeframe in text, yet ~48% of the charts are weekly or monthly. Only ~9% are intraday, and both instances are event-driven crash coverage (`LCID 5-MIN` on the bankruptcy flush, `NFLX 5-MIN` on the earnings dump) — not setup calls.

*Sample caveat:* the 23 labels come from a 32-image sample whose first 12 are the top-12 by views. Within that top-12 subsample the mix is 5 weekly / 5 daily / 1 intraday — essentially the same ratio — so the view-skew does not appear to distort the estimate, but n=23 gives a ±20pp confidence band.

**Long-horizon framing language, verbatim:**
> `Buy great companies below the 200 week EMA and hold forever 🔒 $MCD` (271,071)
> `Nokia $NOK just saw its worst weekly losing streak since 2002... 😬` (229,842)
> `Microsoft $MSFT just printed its best week in over 25 YEARS 🔥` (199,425)
> `Final boss: 3 decades of support / $AMZN` (118,619)
> `The last 4 times Oracle $ORCL read a weekly RSI below 45: / -2008 / -2016 / -2022 / -Now` (101,570)
> `AeroVironment $AVAV sitting below its 200 weekly SMA for just the 2nd time in the past 4 years 🌶️` (49,676)
> `IBM $IBM just officially had its worst day in the company's 115 year history 🩸 / Do you dare buy the blood?` (127,576)
> `✅ 2001 / ✅ 2008 / ✅ 2022 / ❔ 2026 / $AMZN` (153,247)

That last one is the corpus's most reusable mechanic and I verified it against the image. The chart is `AMZN MONTHLY (LOG)`, a trendline drawn from the 1997 IPO, with **Oct 2001, Nov 2008, Dec 2022 circled and labeled, and the current touch marked "YOU ARE HERE" in gold**. The four text lines map 1:1 onto four chart annotations. The text enumerates instances; the chart proves them; the open `❔` is the entire hook. Zero adjectives, zero stance, zero disclaimer.

Same mechanic in the `$ONDS WEEKLY` chart behind `Record-breaking volume after a streak of red...? / We've seen this story play out before 👀`: exactly two circled analogues (the prior one, and now), a labeled `200 EMA`, and a boxed volume bar annotated `Highest weekly volume ever`. **"We've seen this before" is a claim the text asserts and the chart enumerates — the text never names the analogue.**

---

## 3. SELF-QUOTE MECHANIC

**193/396 (48.7%) are quote-tweets; 190 self, 3 external** (`@JensenHuang`, `@unusual_whales`, `@CENTCOM`). 161 distinct parent posts; 25 parents are quoted more than once.

### Timing — strongly bimodal, not a single "follow-up" cadence

p10 0.4h · p25 5.0h · **median 72.5h (3.0 days)** · p75 301.8h (12.6d) · p90 765.7h (31.9d) · max 2,700h (112d)

| gap | n | share | medV (child) | medV (parent) |
|---|---|---|---|---|
| <1h | 36 | 18.7% | 73,513 | 178,375 |
| 1–4h | 10 | 5.2% | 109,930 | 163,252 |
| 4–12h | 8 | 4.1% | 57,371 | 112,122 |
| 12–24h | 11 | 5.7% | 73,484 | 232,819 |
| 1–2d | 21 | 10.9% | 109,147 | 209,985 |
| 2–4d | 22 | 11.4% | **131,577** | 244,675 |
| 4–7d | 19 | 9.8% | 104,796 | 315,810 |
| **>7d** | **66** | **34.2%** | 97,542 | 205,609 |

Two distinct machines:
- **Sub-1h laddering (18.7%)** — live-event decomposition. One earnings drop becomes 4–6 posts inside 90 minutes, each quoting the anchor.
- **Multi-day/multi-week reawakening (55.4% at >2d, 34.2% at >7d)** — a dormant chart call is revived when price reaches the level. The 2–4 day band is the reach sweet spot (medV 131,577 vs 81,735 corpus median).

### Chains, not pairs

Visible chain depth: `{1: 133, 2: 36, 3: 13, 4: 5, 5: 3, 6: 2, 7: 1}`. The deepest is a 7-link `$GOOG` chain spanning 9 days and starting from a livestream link:

```
Wed 07-22 19:45Z  178,375  livestream    TSLA Earnings LIVE: TSLA Q2 2026 Results, Call & Reaction (+GOOGL, NOW, IBM)
  +0.4h  255,541  earnings   GOOGLE JUST ABSOLUTELY SMASHED EPS 🔥 / Q2 EPS: $9.11 vs $2.90 est...
    +3.4h  289,307  quip      Now it gets interesting 👀 / $GOOG $GOOGL
      +22.4h  404,399  valuation  🚨 Google just closed below its 200-day simple moving average for the first time in over a year...
        +23.6h  569,873  valuation  Wow... this is insane. Google crushed earnings by so much, it's TTM P/E ratio fell from 24x to 16x overnight...
          +76.9h  248,155  quip     Blink and you missed it 💥 / $GOOG $GOOGL
            +84.5h   47,784  technical  Déjà vu at the 200SMA 👀 / $GOOG $GOOGL
```

One earnings event → 6 downstream posts → 1.81M cumulative views. Note the chain **peaks in the middle** (569,873 at link 5) and then decays, and each link changes register: numbers card → quip → valuation stat → valuation stat → quip → technical.

### Copy formula of the follow-up

| Follow-up kind | n | share | medV | median gap |
|---|---|---|---|---|
| adds a **new hard fact** (number/record) | 97 | 50.3% | 91,050 | 25.0h |
| **soft narrative beat** (no new data) | 39 | 20.2% | 95,075 | 100.1h |
| **new technical read** (new level/indicator) | 38 | 19.7% | 101,893 | 131.4h |
| **bare emotional beat** (≤6 words) | 19 | 9.8% | **120,551** | 149.9h |

The pattern is clean: **the longer the gap, the shorter the copy.** Sub-day follow-ups carry data; multi-week follow-ups carry three words and a face.

> `My oh my 😲 $SPY` — +149.9h after `Full steam ahead 🚂 $SPY` (401,685)
> `Getting scary 😬 $SNDK` — +25.8h (355,999)
> `Phew 😮‍💨 $NOW` — +104.1h after the Jensen quote post (311,685)
> `Back in business? $MU` — +24.4h (207,180)

**98% (149/152) of self-quotes share ≥1 cashtag with their parent.** Six children carry **no** cashtag at all and let the parent supply it (`Burry rn:`, `Hands up! 🎢`).

**Victory lap is the minority read, and it underperforms.** Confirming/"called it" language: 29 posts, medV 75,763. Deteriorating/"ouch" language: 30 posts, **medV 107,538**. Watching a call go *wrong* out-reaches watching it go right by 42%.

**Timeframe zoom-out on follow-up:** 15 children introduce weekly/monthly framing the parent lacked — e.g. `Getting scary 😬 $SNDK` (daily chart) → `Sandisk $SNDK just lost its 21 week EMA for the first time the entire run up, while printing its worst week in nearly 8 months 😬`. The `$DUOL` pair confirms this at the image level: parent is `DUOL DAILY (LOG)`, child is `DUOL WEEKLY`.

**Median child/parent view ratio is 0.51; the child beats the parent only 10% of the time.** But that is a regression-to-the-mean artifact of quoting your own hits. Controlled within class, the self-quote *lifts*:

| class | self-quote medV | original medV |
|---|---|---|
| `chart_quip` | 119,903 (n=40) | 84,346 (n=15) |
| `chart_technical` | 98,502 (n=49) | 69,966 (n=17) |
| `earnings_print` | 97,282 (n=13) | 45,429 (n=35) |
| `ticker_news_reaction` | 116,455 (n=19) | 46,903 (n=11) |
| `breadth_macro` | 84,278 (n=9) | 60,192 (n=19) |
| `product_promo` | 59,348 (n=17) | 50,902 (n=27) |
| `meme_quip` | 57,250 (n=4) | 66,570 (n=21) |

---

## 4. HOOK ENGINEERING

Top-decile threshold: **217,941 views** (= 2.67× median). 40 posts qualify.

**Full corpus, ranked by median views:**

| hook | n | medV | top-decile rate |
|---|---|---|---|
| interjection opener (`Wow`/`OUCH`/`Uh oh`/`Phew`/`My oh my`) | 14 | **114,337** | **35.7%** |
| superlative/record in first line | 35 | 98,381 | **28.6%** |
| bare cashtag caption ≤6 words | 31 | 97,835 | 12.9% |
| ellipsis `...` tease | 57 | 91,489 | 12.3% |
| `BREAKING:` | 26 | 88,742 | 11.5% |
| ALLCAPS ticker card | 46 | 88,516 | 10.9% |
| 2nd-person `you/your` | 38 | 86,771 | 10.5% |
| emoji in first line | 193 | 82,433 | 12.4% |
| **[CORPUS BASELINE]** | **396** | **81,735** | **10.1%** |
| lowercase-only opener | 16 | 73,189 | 6.2% |
| question-ending | 8 | 70,760 | 0.0% |
| pattern-echo (`We've seen this before`/`Déjà vu`) | 8 | 70,664 | **25.0%** |
| siren 🚨 without `BREAKING` | 9 | 59,738 | 22.2% |
| **numbers-first opener** | 34 | **48,460** | **2.9%** |

Most-frequent first tokens: `BREAKING:` ×26, `The` ×12, `🚨` ×9, `President` ×7, `Just` ×5, `Chip`/`Sandisk`/`Futures`/`Google`/`One` ×4.

**Controlled to the chart family only** (baseline medV 98,502, top-decile 16.8%) — this strips the class confound:

| hook | n | medV | top-decile |
|---|---|---|---|
| interjection opener | 12 | **171,405** | **41.7%** |
| ellipsis | 27 | 124,737 | 25.9% |
| named person (`Burry`/`Jensen`/`Trump`/`Leopold`) | 14 | 118,204 | 14.3% |
| self-quote | 124 | 101,327 | 19.4% |
| question mark anywhere | 13 | 100,380 | 15.4% |
| superlative/record | 35 | 98,502 | **28.6%** |
| 7–14 words | 76 | 97,818 | 18.4% |
| ≤6 words | 31 | 97,835 | 12.9% |
| named MA level (200/50/21 EMA/SMA) | 18 | 96,706 | **5.6%** |
| `👀` anywhere | 48 | 90,127 | 12.5% |
| contains `%` | 19 | 72,105 | **5.3%** |
| ≥25 words | 20 | 69,352 | 15.0% |

**Findings that survive the control:**
1. **The interjection opener is the single strongest hook** — 41.7% top-decile vs a 16.8% chart baseline. It is a pure emotional register-shift with no informational content.
2. **Numbers-first openers are the worst hook in the corpus** (2.9% top-decile, medV 48,460 vs 81,735 baseline) — but this is *almost entirely the earnings-print class*. Within chart posts, `contains %` also underperforms (5.3%). Numbers belong in the image, not the first line.
3. **Naming the moving average in text underperforms** (5.6% top-decile) while `chart_technical` as a class performs fine — i.e. it is fine to *show* the 200 EMA and bad to *say* "200 EMA" in the hook.
4. `pattern-echo` and `siren 🚨` have high top-decile rates (25.0%, 22.2%) on **low median views** — bimodal, high-variance hooks. n=8 and n=9. Do not build a rule on these.

---

## 5. TICKER STRATEGY

**140 unique cashtags** across 415 post-level ticker mentions in 396 posts (matching the brief), over **19.9 days** (not 13).

Top 20: `NVDA` 20 · `MU` 17 · `SNDK` 15 · `STX` 13 · `MSFT` 13 · `AMZN` 13 · `SPY` 11 · `GOOG` 11 · `GOOGL` 11 · `TSLA` 10 · `INTC` 10 · `WDC` 9 · `AAPL` 9 · `META` 9 · `TSM` 8 · `QQQ` 8 · `NOW` 8 · `AMAT` 7 · `LCID` 6 · `AMD` 6

**Head/tail structure:**
- **76/140 (54%) appear exactly once.** 27 appear twice. Only **27 appear ≥5 times.**
- Top-10 tickers = **32%** of mentions; top-20 = **52%**.
- Unique tickers per day: median **16** (range 9–32).
- New tickers introduced per day after day 1: median ≈ **5** (11, 9, 7, 12, 7, 4, 10, 5, 3, 1, 3, 5, 9, 4, 6, 9, –, 2, 1).

So: **a stable ~20-name rotation carries half the coverage, and roughly five brand-new long-tail names are injected per day.** The long tail is not opportunistic clutter — it is a deliberate daily quota (`$EOSE`, `$CIFR`, `$OSCR`, `$AAL`, `$DOCU`, `$PATH`, `$AEO`, `$MMM`, `$JOBY`, `$AXON`, `$KTOS`, `$NU`, `$AVAV`).

**Hot-name cadence:**

| ticker | posts | distinct days | median inter-post gap |
|---|---|---|---|
| `$NVDA` | 20 | 14 | 16.1h |
| `$MU` | 17 | 13 | 25.5h |
| `$SNDK` | 15 | 10 | 16.1h |
| `$STX` | 13 | 7 | 9.8h |
| `$MSFT` | 13 | 8 | 16.1h |
| `$AMZN` | 13 | 7 | 9.4h |

A mega-cap gets touched roughly **every other day**; a ticker in an active story gets **2–3 posts per day** for the duration of the story and then goes quiet.

**Pure ticker-chart observations per day: median 8, mean 7.7** (range 4–12) — 161 chart posts over 21 calendar dates. **91% (147/161) are single-ticker.**

Notably: **weekday median 7, weekend median 8.5.** Chart posts do *not* thin out on weekends — only the news/earnings flow does (overall weekday ~24/day vs weekend ~14.7/day). The weekend is where the chart-observation share of output is highest, and it runs on the weekly/monthly charts that don't require a live tape.

**Posting clock (ET, UTC−4):** ET 16:00 = **74 posts (18.7%)**, the single dominant hour (post-close; 42 of 48 earnings prints land here). `chart_technical` peaks ET 20:00–22:00. `product_promo` peaks ET 23:00 (17 of 44). Dead window ET 02:00–07:00 (1 post total across 20 days).

---

## 6. STYLE MECHANICS

**Length.** All posts (t.co links stripped): p25 **54 chars**, median **94**, p75 146, p90 235, max 645. Words: p25 10, median **17**, p75 26, max 99.
Chart posts alone: median **61 chars / 11 words**, p75 93 chars. **The chart post is a caption, not a paragraph.**

**Line breaks.** 179/396 (45%) contain **no newline at all**. Blank-line-separated blocks: 0 → 203 posts, 1 → 91, 2 → 67, 3 → 29, 4+ → 6. When they do break, the pattern is rigid: `hook` ⏎⏎ `body` ⏎⏎ `$TICKER` or `⏎⏎ [🟩/🟥] ±x%`. The lone cashtag on its own trailing line is a recurring device (`Now it gets interesting 👀` ⏎ `$GOOG $GOOGL`).

**Emoji.** 50 distinct glyphs. **256/396 (65%) carry ≥1.** **210 posts (53%) have an emoji inside the last 14 characters** — emoji functions as terminal punctuation, not decoration.

Vocabulary, ranked: `👀` 61 · `🔥` 52 · `🟢` 50 · `🩸` 34 · `🔴` 31 · `🟩` 20 · `🌶️` 18 · `🟥` 17 · `✅` 14 · `🚨` 10 · `😬` 8 · `⬇️` 7 · `🔎` 6 · `💰` 5 · `🐢` 4 · `😲` 4 · `🧠` 4 · `🎯` 3 · `🍿` 3 · `❌` 3

Three functional registers, and they do not mix:
- **Stance markers** (`👀` "watch this", `😬` tension, `🌶️` spicy stat, `🩸` blood) — trail the caption.
- **Ledger markers** (`🟢🔴🟩🟥✅❌`) — lead each line inside scoreboards and earnings cards.
- **Alarm** (`🚨`) — leads the post, used 10× only.

Within-chart-family view medians by glyph: `😬` 177,306 (n=8) · `🌶️` 110,595 (n=13) · `🩸` 98,502 (n=13) · `👀` 90,127 (n=48) · `🔥` 68,512 (n=10) vs chart baseline 98,502. **Tension glyphs beat celebration glyphs.**

**Numbers vs vague claims.** 180/396 (45%) of all posts contain a hard number. **Within the chart family only 41/161 (25%).** The number lives in the image; the caption stays qualitative.

**Confound control matters here.** Uncontrolled, "emoji" and "hard number" both look *negative* (emoji medV 72,828 vs 88,595; numbers 72,214 vs 88,704). Restricted to the chart family the effect nearly vanishes (emoji 96,280 vs 107,033; numbers 87,500 vs 100,668; all-caps 97,835 vs 102,940). **The apparent penalty was `earnings_print` + `product_promo` — the two emoji-and-number-dense low-reach classes — not the features.** Do not port the uncontrolled reading into a spec.

**Length vs reach within the chart family:** 1–6 words medV 97,835 (n=31) · 7–12 words **103,837** (n=59) · 13–20 words 101,020 (n=44) · 21+ words 84,847 (n=27). The optimum is **7–12 words**; going past 20 is the only real penalty.

**Explicit opinion.** Only **7/161 chart posts (4%)** contain an explicit directional or action verb. Complete list:
> `"Go out and buy a Dell" $DELL / -President Donald J Trump` *(attributed to a third party)*
> `IBM $IBM just officially had its worst day in the company's 115 year history 🩸 / Do you dare buy the blood?` *(rhetorical question)*
> `Buy great companies below the 200 week EMA and hold forever 🔒 $MCD` *(a maxim, not a call)*
> `Buying Microsoft here means you're paying the same valuation as: / -2020 Covid lows / -2022/23 Bear Market lows / $MSFT`
> `Oracle $ORCL is now just $1 away from hitting its lowest price since June 2024 🌶️ / Burry is still holding half his original short position.` *(third party's position)*
> `Taiwan Semi $TSM on its worst losing streak since 2022 🩸 / You buying the dip in semi stocks?` *(question to the reader)*
> `Picking up steam off the long term trendline $AXON 👀`

**96% of chart posts are pure observation.** Direction is delegated three ways: to a named third party (Burry, Jensen, Trump, a CEO), to the reader as a question, or to the chart's own annotation. 14/161 chart posts carry an explicit hedge verb (`perhaps`, `looks like`, `nearing`, `approaching`, `trying to`).

**Questions.** 30 posts contain `?`; only 8 end on one. **Question marks do not lift replies** (median 20 replies with `?` vs 19 without). They are a stance-avoidance device, not an engagement device.

**Disclaimers: 0 of 396.** No "not financial advice", no NFA, no DYOR, anywhere in the corpus. The compliance posture is carried entirely by never making a claim — a structural choice, not a legal-boilerplate one.

---

## 7. TOP-DECILE AUTOPSY (top 40, ≥217,941 views = 31.0% of all corpus views)

**Class lift vs corpus share:**

| class | top-40 | corpus | lift |
|---|---|---|---|
| `valuation_obs` | 4 (10.0%) | 12 (3.0%) | **3.30×** |
| `chart_stat_extreme` | 6 (15.0%) | 28 (7.1%) | **2.12×** |
| `chart_quip` | 10 (25.0%) | 55 (13.9%) | **1.80×** |
| `breaking_news` | 3 (7.5%) | 26 (6.6%) | 1.14× |
| `livestream_promo` | 1 | 9 | 1.10× |
| `chart_technical` | 7 (17.5%) | 66 (16.7%) | 1.05× |
| `ticker_news_reaction` | 3 | 30 | 0.99× |
| `earnings_print` | 3 | 48 | 0.62× |
| `news_report` | 1 | 19 | 0.52× |
| `meme_quip` | 1 | 25 | 0.40× |
| `product_promo` | 1 | 44 | 0.23× |
| `breadth_macro` | **0** | 28 | **0.00×** |
| `exec_quote` | **0** | 6 | **0.00×** |

**Shared properties:**

| property | top-40 | corpus |
|---|---|---|
| chart family (quip/tech/stat/val) | **27/40 (67.5%)** | 40.7% |
| self-quote | **29/40 (72.5%)** | 48.7% |
| has image | 37/40 (92.5%) | 87.6% |
| median words | **13** | 17 |
| median chars | **72** | 94 |
| ≤8 words | 10/40 (25%) | — |
| single-ticker | 29/40 | 91% of chart posts |
| zero-ticker | 4/40 | — |
| mega-cap ticker | 14/40 | — |
| hard number in text | 15/40 (37.5%) | 45% |
| named person (Burry/Jensen/Trump/Leopold/Musk) | **6/40 (15%)** | 37/396 (9.3%) |
| median likes/1k views | **2.94** | 3.45 |
| median bookmarks/1k | 0.35 | 0.30 |

Ticker concentration in the top 40: `GOOG` 5 · `GOOGL` 5 · `NOW` 5 · `MU` 3 · `ORCL` 3 · `MSFT` 2 · `ONDS` 2 · `DUOL` 2 · `NVDA` 2 · `SNDK` 2 · `QQQ` 2.

**The four properties that actually separate the top decile:**
1. **Shorter, not longer.** Median 13 words vs 17; a quarter are ≤8 words. The three shortest in the top 40 are 3, 4, and 5 words (`Phew 😮‍💨 $NOW`, `Getting scary 😬 $SNDK`, `My oh my 😲 $SPY`).
2. **It is a follow-up, not an origination** (72.5% vs 48.7%).
3. **It is a stance or a superlative, never a scoreboard.** Zero breadth/scoreboard posts and zero exec quotes reached the top decile despite 34 attempts.
4. **Reach outruns engagement.** Likes/1k are *lower* in the top decile (2.94 vs 3.45). These posts travel on impression volume, not on interaction rate — consistent with algorithmic amplification of the parent-quote structure rather than intrinsic engagement quality.

### Statistical caveat that governs this whole section

**The 40 top-decile posts are not 40 independent observations.** 16 of them have a parent that is *also* in the top 40, and tracing every one back to its chain root leaves only **22 distinct roots** — with `$GOOG` and `$NOW` chains contributing 5 posts each. Effective n ≈ 22, and the units are correlated *within* chain by construction (a quote-tweet inherits its parent's audience). Any per-hook rate computed on this set has roughly √(40/22) ≈ 1.35× the stated standard error, and the "self-quote share is 72.5%" figure is partly a restatement of "chains cluster in the top decile" rather than independent evidence that quoting lifts a post. The controlled within-class comparison in §3 is the sounder evidence for that claim.

---

## 8. Transfer notes for a ticker-chart post engine — and two traps

**Mechanics that are directly portable and cheap:**
- Caption budget: **7–12 words, ≤93 chars**, single line 45% of the time, terminal stance glyph.
- Hard numbers go in the **image**, not the caption (chart posts: 25% carry a number vs 45% corpus-wide; `contains %` = 5.3% top-decile).
- Chart anatomy is fixed and load-bearing: dark canvas · `TrendSpider` mark top-left · **`TICKER TIMEFRAME` in caps top-right** (this is where the horizon is disclosed, and it is the *only* place in 68% of posts) · company logo watermark · circled-and-labeled prior instances · one boxed annotation naming the claim (`Highest weekly volume ever`, `24x P/E`, `Squeezing`) · `YOU ARE HERE` marker on the current bar · sub-panel plotting the exact metric the caption implies.
- The enumerate-and-circle pattern (`✅ 2001 / ✅ 2008 / ✅ 2022 / ❔ 2026`) is the highest-density claim/proof coupling in the corpus and needs no prose.
- Sequencing: post the observation, then reawaken it at **+2–4 days** with a ≤6-word beat when price reaches the level. That band has the highest child medV (131,577) and the copy gets *shorter* as the gap gets longer.

**Trap 1 — the follow-up ledger is a selection-biased track record.** 161 parents drew a follow-up; the corpus contains no signal for how many calls were quietly dropped. Porting the self-quote mechanic without a forward ledger that records *every* call and grades it on a pre-set schedule manufactures an implied hit rate whose denominator has been deleted — the resolution-conditioned-denominator failure, in publishing form. The nightly forward log has to write the row at origination, not at follow-up time. Worth noting that TrendSpider's own numbers argue this is not even the reach-optimal play: "ouch" follow-ups out-reach victory laps 107,538 vs 75,763.

**Trap 2 — every superlative is a PIT claim.** `worst weekly losing streak since 1997`, `worst day in the company's 115 year history`, `first time in over a year`, `cheapest valuation since Jan 2015` — 35 posts open on a superlative and it is the second-strongest hook in the corpus (28.6% top-decile). Each one is a max/min over a full history window computed at post time. Generating these from a snapshot rather than a point-in-time-correct series produces claims that were never true as of the stated date, and they are exactly the claims that get screenshotted. Any such generator needs the PIT anchor on the max-date path, and a null there must suppress the post rather than fall back to the snapshot.

**Also worth carrying:** 0/396 disclaimers, 4% explicit directional verbs, and direction delegated to a third party, a question, or the chart's own annotation. That posture — never say the thing the chart already shows — is a good structural match for display-only-until-validated, and it is achieved by construction rather than by appending a hedge sentence.
