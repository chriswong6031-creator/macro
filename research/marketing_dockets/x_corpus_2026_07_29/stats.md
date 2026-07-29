# X Finance-Account Style Corpus — stats.md
Computed over `corpus.jsonl`: 286 original posts (replies and pure retweets excluded; quote-tweets included and flagged `is_quote`) across 17 accounts.
Source: twitterapi.io `GET /twitter/user/last_tweets?userName=<handle>`, 1 page (~20 raw tweets) per account, fetched 2026-07-28/29.
## Methodology notes

- **Raw line count** = `text.strip()` then split on `\n`; a blank line inside a post (paragraph break) counts as its own line, matching how it visually renders on X (a blank line still takes up vertical space). `0` lines = empty/media-only text.
- **Content line count** = same split, but blank-line spacers are dropped before counting. This separates "2 dense back-to-back lines" from "headline / blank spacer / body" (which is 2 chunks of content, but 3 RAW lines because of the gap). Report BOTH — they tell different stories and the gap between them is itself a finding (see Key findings #1).
- **Decimal (strict, per spec)** = regex `\d+\.\d\d` (exactly 2+ digits after the point, e.g. `4.75`, `102.50`). This EXCLUDES common single-decimal numbers like `4.7%` — see `pct_decimal_any` for the supplementary any-decimal metric (`\d+\.\d+`), which is the more realistic read on "does this account use precise decimal numbers."
- **Bare integer** = a digit run not touching a `.` on either side (`\b100\b` counts; the `4` and `7` inside `4.7` do not).
- **Starts with cashtag/ticker** = `$TICKER` at the very start (`pct_starts_cashtag_only`), OR (combined stat `pct_starts_cashtag_or_ticker`) a bare 1-5 letter all-caps leading token that isn't a common non-ticker caps word (BREAKING, GDP, CPI, FOMC, FED, US, CEO, etc — see script for full exclude-list). This is a heuristic; edge cases exist both ways.
- **ALL-CAPS lead word** = first alphabetic token in the post (skipping leading emoji/digits/punctuation) is 2+ letters and fully uppercase. Note this overlaps with cashtags, since `$AAPL` reads as leading token `AAPL` (all caps).
- **Emoji** = presence of any codepoint in the common emoji blocks (misc pictographs, dingbats, flags, geometric shapes ext., arrows+VS16).
- **Median words/sentence** = each post is split on newlines, then each line split on `.!?` boundaries; word count = whitespace split; median taken over ALL sentence fragments pooled in the group (not per-post-then-averaged).
- Percentages are of that group's post count `n`, rounded to 1 decimal.
## Overall
| Account | n | char p10/p50/p90 | raw lines 1/2/3+ | content lines 1/2/3+ | $cashtag | digits | decimal strict (any) | bare int | starts $/ticker | ALL-CAPS lead | emoji | ends `?` | URL | quote-RT | med words/sentence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ALL ACCOUNTS** | 286 | 55.5/131.0/516.5 | 48.6% / 2.8% / 48.6% | 48.6% / 17.1% / 34.3% | 33.6% | 72.4% | 5.9% (15.4%) | 68.2% | 25.2% | 31.5% | 17.8% | 1.0% | 49.3% | 13.6% | 9 |

## By register
| Account | n | char p10/p50/p90 | raw lines 1/2/3+ | content lines 1/2/3+ | $cashtag | digits | decimal strict (any) | bare int | starts $/ticker | ALL-CAPS lead | emoji | ends `?` | URL | quote-RT | med words/sentence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wire/breaking | 59 | 55.8/91/374.8 | 72.9% / 0.0% / 27.1% | 72.9% / 6.8% / 20.3% | 10.2% | 49.2% | 5.1% (16.9%) | 42.4% | 35.6% | 52.5% | 1.7% | 0.0% | 10.2% | 0.0% | 10 |
| news/numbers aggregator | 77 | 85.6/171/804.6 | 33.8% / 0.0% / 66.2% | 33.8% / 22.1% / 44.2% | 57.1% | 80.5% | 6.5% (20.8%) | 77.9% | 35.1% | 55.8% | 35.1% | 1.3% | 49.4% | 10.4% | 10.0 |
| data-driven commentary | 41 | 61/129/279 | 56.1% / 0.0% / 43.9% | 56.1% / 19.5% / 24.4% | 41.5% | 90.2% | 4.9% (14.6%) | 85.4% | 4.9% | 2.4% | 12.2% | 0.0% | 75.6% | 12.2% | 9 |
| trader/setup | 87 | 49.2/147/522.0 | 31.0% / 9.2% / 59.8% | 31.0% / 21.8% / 47.1% | 33.3% | 70.1% | 8.0% (10.3%) | 66.7% | 23.0% | 16.1% | 18.4% | 2.3% | 54.0% | 26.4% | 8.0 |
| macro color | 22 | 41.2/113.0/284.1 | 90.9% / 0.0% / 9.1% | 90.9% / 4.5% / 4.5% | 0.0% | 81.8% | 0.0% (13.6%) | 77.3% | 9.1% | 4.5% | 9.1% | 0.0% | 86.4% | 13.6% | 9 |

## By account
| Account | n | char p10/p50/p90 | raw lines 1/2/3+ | content lines 1/2/3+ | $cashtag | digits | decimal strict (any) | bare int | starts $/ticker | ALL-CAPS lead | emoji | ends `?` | URL | quote-RT | med words/sentence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DeItaone (wire/breaking) | 20 | 60.4/149.0/404.5 | 50.0% / 0.0% / 50.0% | 50.0% / 10.0% / 40.0% | 15.0% | 45.0% | 5.0% (25.0%) | 45.0% | 70.0% | 85.0% | 0.0% | 0.0% | 0.0% | 0.0% | 12.0 |
| FirstSquawk (wire/breaking) | 20 | 55.8/75.0/102.3 | 100.0% / 0.0% / 0.0% | 100.0% / 0.0% / 0.0% | 0.0% | 45.0% | 10.0% (15.0%) | 30.0% | 30.0% | 35.0% | 0.0% | 0.0% | 0.0% | 0.0% | 11.5 |
| unusual_whales (wire/breaking) | 19 | 59.6/115/210.0 | 68.4% / 0.0% / 31.6% | 68.4% / 10.5% / 21.1% | 15.8% | 57.9% | 0.0% (10.5%) | 52.6% | 5.3% | 36.8% | 5.3% | 0.0% | 31.6% | 0.0% | 8 |
| KobeissiLetter (news/numbers aggregator) | 20 | 145.5/580.0/908.6 | 15.0% / 0.0% / 85.0% | 15.0% / 15.0% / 70.0% | 20.0% | 100.0% | 5.0% (35.0%) | 100.0% | 0.0% | 60.0% | 0.0% | 0.0% | 35.0% | 0.0% | 15 |
| Barchart (news/numbers aggregator) | 20 | 68.3/108.0/152.6 | 80.0% / 0.0% / 20.0% | 80.0% / 15.0% / 5.0% | 45.0% | 85.0% | 0.0% (10.0%) | 85.0% | 5.0% | 25.0% | 95.0% | 5.0% | 95.0% | 10.0% | 12 |
| StockMKTNewz (news/numbers aggregator) | 18 | 77.7/122.0/300.2 | 38.9% / 0.0% / 61.1% | 38.9% / 38.9% / 22.2% | 72.2% | 77.8% | 11.1% (22.2%) | 66.7% | 44.4% | 44.4% | 33.3% | 0.0% | 61.1% | 33.3% | 3 |
| wallstengine (news/numbers aggregator) | 19 | 129.4/438/823.0 | 0.0% / 0.0% / 100.0% | 0.0% / 21.1% / 78.9% | 94.7% | 57.9% | 10.5% (15.8%) | 57.9% | 94.7% | 94.7% | 10.5% | 0.0% | 5.3% | 0.0% | 10 |
| charliebilello (data-driven commentary) | 9 | 78.8/179/279.0 | 22.2% / 0.0% / 77.8% | 22.2% / 44.4% / 33.3% | 22.2% | 100.0% | 22.2% (22.2%) | 88.9% | 0.0% | 0.0% | 0.0% | 0.0% | 88.9% | 22.2% | 4 |
| RyanDetrick (data-driven commentary) | 12 | 34.8/101.0/267.7 | 58.3% / 0.0% / 41.7% | 58.3% / 16.7% / 25.0% | 16.7% | 66.7% | 0.0% (0.0%) | 66.7% | 16.7% | 8.3% | 41.7% | 0.0% | 66.7% | 25.0% | 7 |
| bespokeinvest (data-driven commentary) | 20 | 60.4/128.0/297.4 | 70.0% / 0.0% / 30.0% | 70.0% / 10.0% / 20.0% | 65.0% | 100.0% | 0.0% (20.0%) | 95.0% | 0.0% | 0.0% | 0.0% | 0.0% | 75.0% | 0.0% | 11 |
| markminervini (trader/setup) | 14 | 102.3/382.5/1307.2 | 21.4% / 21.4% / 57.1% | 21.4% / 21.4% / 57.1% | 14.3% | 71.4% | 7.1% (7.1%) | 64.3% | 7.1% | 0.0% | 28.6% | 0.0% | 78.6% | 14.3% | 10.0 |
| PeterLBrandt (trader/setup) | 17 | 66.4/164/2641.6 | 52.9% / 11.8% / 35.3% | 52.9% / 11.8% / 35.3% | 5.9% | 64.7% | 0.0% (5.9%) | 64.7% | 23.5% | 0.0% | 11.8% | 5.9% | 47.1% | 29.4% | 11 |
| alphatrends (trader/setup) | 19 | 33.6/108/261.0 | 26.3% / 5.3% / 68.4% | 26.3% / 42.1% / 31.6% | 42.1% | 52.6% | 5.3% (5.3%) | 52.6% | 5.3% | 5.3% | 26.3% | 0.0% | 63.2% | 26.3% | 4 |
| traderstewie (trader/setup) | 20 | 64.9/231.5/456.3 | 15.0% / 10.0% / 75.0% | 15.0% / 15.0% / 70.0% | 35.0% | 75.0% | 20.0% (20.0%) | 75.0% | 30.0% | 25.0% | 25.0% | 0.0% | 60.0% | 25.0% | 6 |
| Mr_Derivatives (trader/setup) | 17 | 43.6/81/191.8 | 41.2% / 0.0% / 58.8% | 41.2% / 17.6% / 41.2% | 64.7% | 88.2% | 5.9% (11.8%) | 76.5% | 47.1% | 47.1% | 0.0% | 5.9% | 23.5% | 35.3% | 4 |
| jam_croissant (macro color) | 4 | 23.9/36.5/503.4 | 75.0% / 0.0% / 25.0% | 75.0% / 0.0% / 25.0% | 0.0% | 100.0% | 0.0% (0.0%) | 100.0% | 0.0% | 0.0% | 50.0% | 0.0% | 75.0% | 75.0% | 15.0 |
| LizAnnSonders (macro color) | 18 | 54.2/124.0/278.7 | 94.4% / 0.0% / 5.6% | 94.4% / 5.6% / 0.0% | 0.0% | 77.8% | 0.0% (16.7%) | 72.2% | 11.1% | 5.6% | 0.0% | 0.0% | 88.9% | 0.0% | 9 |

## Key findings

**1. Line-count distribution is the headline finding — and "exactly 2 lines, always" matches nobody.** Across 286 real posts from winning finance accounts, RAW line count (blank spacer lines counted, i.e. what actually renders vertically):
- **48.6%** are a single line (no line break at all)
- **2.8%** are exactly 2 raw lines — this is the RAREST shape, not the default
- **48.6%** are 3+ raw lines

That 3+ bucket is inflated by a very common structural move that is easy to miss: **headline, then a blank spacer line, then one line of body** (`"HEADLINE\n\nBody detail."`) — 2 chunks of actual content, but 3 raw lines because of the visual gap. Re-counting by CONTENT lines only (ignoring blank spacers) reshapes the picture:
- **48.6%** 1 content line
- **17.1%** 2 content lines
- **34.3%** 3+ content lines

So the honest read is: real posts are **roughly half one dense line, and half multi-chunk** — and when they ARE multi-chunk, the single most common real pattern is "headline + blank line + body," not two lines butted together with no gap. A bot that is ALWAYS exactly 2 lines with no blank-line option, no 1-line option, and no 3+-chunk option matches none of the three real shapes — it's not merely "the wrong ratio," it's missing an entire structural move (the blank-line spacer) that real accounts lean on constantly. Distribution varies heavily by register: wire/breaking accounts (DeItaone, FirstSquawk) are close to pure 1-line, or 1-line-headline+blank+1-line-body; data-commentary and trader-setup accounts range much wider, often into numbered lists or multi-line chart call-outs (pushing char p90 to 516.5 chars — far beyond a terse 2-liner).

**2. Decimal vs round numbers.** Strict decimal (`\d+\.\d\d`, e.g. `4.75`, `102.50`) appears in only **5.9%** of posts, but the any-decimal metric (`\d+\.\d+`, catching common 1-decimal numbers like `4.7%`, `2.1%`) appears in **15.4%**. Bare integers (`\b100\b`-style, no decimal point) appear in **68.2%** of posts — round numbers are far more common than precise 2-decimal figures. When real accounts do use decimals it is almost always 1 decimal place (percent moves, ratios), not 2. A bot that defaults to 2-decimal precision (`$102.50`) everywhere is over-precise relative to real usage, which favors rounded/whole numbers or 1-decimal percentages.

**3. Cashtag usage is real but not universal.** 33.6% of posts contain a `$cashtag` anywhere; 25.2% open with one. This varies hugely by register — data/wire accounts lead with the headline fact, not the ticker; trader-setup accounts are more likely to open with the symbol.

**4. ALL-CAPS lead words (31.5%) are a wire-desk signature**, not a house style — concentrated in DeItaone/FirstSquawk/unusual_whales-style breaking accounts; data-commentary and macro-color accounts rarely open in caps.

**5. Emoji (17.8%), question-endings (1.0%), and URLs (49.3%)** are all minority patterns overall but concentrated by register — see per-account table. URLs are especially common on chart/data posts (linking a chart image or thread) and trader-setup posts (linking a levels chart).

**6. Median words/sentence (9)** — real posts write in short, often sentence-fragment bursts, not full grammatical paragraphs.
## Per-account raw post counts (fetch → kept-original)
See `corpus.jsonl` for the full row set. Counts of ORIGINAL posts kept (replies excluded [none were returned by the API for these accounts — endpoint default `includeReplies=false`], pure retweets excluded) out of 20 raw tweets fetched per account:

- DeItaone: 20/20 kept as original posts
- FirstSquawk: 20/20 kept as original posts
- unusual_whales: 19/20 kept as original posts
- KobeissiLetter: 20/20 kept as original posts
- Barchart: 20/20 kept as original posts
- StockMKTNewz: 18/20 kept as original posts
- wallstengine: 19/20 kept as original posts
- charliebilello: 9/20 kept as original posts
- RyanDetrick: 12/20 kept as original posts
- bespokeinvest: 20/20 kept as original posts
- markminervini: 14/20 kept as original posts
- PeterLBrandt: 17/20 kept as original posts
- alphatrends: 19/20 kept as original posts
- traderstewie: 20/20 kept as original posts
- Mr_Derivatives: 17/20 kept as original posts
- jam_croissant: 4/20 kept as original posts
- LizAnnSonders: 18/20 kept as original posts
