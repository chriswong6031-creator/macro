# TrendSpider Playbook, Master-Technicals & Autonomous Chart Engine

## Fable's learning synthesis + build/rollout plan for the Marketing Content Studio

**Prepared:** 2026-07-19
**Author:** Fable (autonomous CMO)
**Corpus:** 258 TrendSpider X-post screenshots (with likes/reach where visible) + 30 full-res charts, machine-vision-extracted (21 agents, ~812k tokens). Grounded in our repo capability map.
**Companions:** `MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md`, `docs/MARKETING_COCKPIT_BUILD_SPEC.md`.

---

## 0. The thesis

TrendSpider is the best-in-class example of a charting brand turning **technical analysis into distribution**. They post beautiful, information-dense charts with a strong human-written hook, and it works: charts out-reach text by ~51%, and their technical/signal charts average ~145k views. We can match — and in some ways beat — this **without a human technician**, because the two things a human social-media technician does (1) *decide which chart is worth posting* and (2) *draw the indicators and annotations* are both things our stack already does deterministically:

1. **We already have the "which chart is worth posting" engine.** `engine/tech_confluence.py` mines 2–4-signal confluences and ranks them by *historical, train/test-split, month-collapsed win rate* (`tech_lab.html#combos`). A human technician eyeballs a chart and guesses; our engine *measures* which signal stacks won historically and tells us which tickers have them firing **right now** (`tech_confluence.json → active_now`). That is a strictly stronger trigger than a human's eye.
2. **We can draw the indicators deterministically.** We compute MACD, RSI, StochRSI, Bollinger, Ichimoku, MA-crosses, ADX/DMI, ATR, OBV, CMF, TTM-squeeze, choppiness, Connors-RSI, Donchian, BBWP and ~40 more today. A pure-SVG chart engine can render candlesticks + those indicators + the highlight, at industrial volume, for free.

So the honest answer to the operator's question — *can the Content Studio reach TrendSpider quality with no human manager?* — is **yes for the mechanical 80% (chart generation, indicator drawing, signal selection, reach-optimized formatting), and yes-with-a-governor for the judgment 20%** (hook writing, "is this worth posting," compliance). The 20% is where an LLM (Opus/Sonnet, gated) writes the hook and the auditor checks it — not a human. What we must build is the **chart engine + the confluence→post loop + a richer indicator suite + the reach-optimized copy model.** This document is the rules, the anatomy spec, and the phased plan.

---

## 1. What actually gets reach (grounded in the corpus)

Mean views by format, where visible (n=156 posts with view counts):

| Format | Mean reach | Read |
|---|---:|---|
| signal_chart | 147,424 | **Top tier.** A clean chart + a signal/level + a punchy hook. |
| technical_analysis | 144,312 | **Top tier.** Same, with more drawn annotation (patterns, PoC, divergence). |
| breaking_news | 105,071 | Strong. Speed + a cited source. 73 of 259 posts — their highest-*volume* format. |
| earnings | 77,923 | Solid. Posted the instant numbers drop, with a company-logo illustration. |
| heatmap | 77,333 | Solid, differentiated. Sector-pain treemaps + an engagement question. |
| truth_social | 70,750 | Trump Truth-Social screenshots/illustrations, key parts highlighted. |
| centcom / macro | ~60–63k | Geopolitical/macro breaking, cited. |

Cross-cutting findings:
- **Charts beat text by ~51%** (122,788 vs 81,420 mean reach). *Always attach a visual.*
- **Bearish ≥ bullish** (122,574 vs 113,475). Pain, blow-offs, and "bulls tested" hooks travel. **Not everything is a buy** — post bearish setups, breakdowns, and risk.
- **The mega-hits are contrarian/superlative hooks over a dramatic chart**: "*Many have bet against Microsoft over the years… and many have lost*" (378k), "*Bulls haven't been tested like this the entire run* $SNDK" (278k), "*Don't shoot the messenger*" (253k). The pattern: **emotional/contrarian one-liner + a chart that visually proves it.**
- **Hook grammar** (observed): shock-stat, superlative/record ("worst week in 8 months", "highest weekly volume ever"), milestone break ("lost its 21-week EMA for the first time"), rhetorical question to the reader ("who's most likely to comeback?"), celebrity quote ("Jensen Huang on $NOW"), investing maxim ("buy great companies below the 200-week EMA"), and confluence-stat ("surging volume + bullish RSI divergence").
- **Every chart post carries a cashtag.** Breaking news cites a source (company IR, WSJ, Bloomberg, Reuters, CENTCOM, Truth Social).

### Reach-optimized copy rules (for the Studio's hook model)
1. Lead with an **emotion or a superlative**, not a description. ("Talk about volatility 🤯" beats "INTC daily chart".)
2. **State one checkable fact** the chart proves (a %, a level break, a record).
3. **Ask the reader a question** on sector/comeback posts (drives replies → reach).
4. **Cashtag always**; 1–2 emojis; short.
5. **Mix stance** — bearish and neutral posts are ~40% of theirs and reach as well or better.
6. On breaking news: **speed + source citation**, no chart needed but a logo illustration helps.

---

## 2. Chart anatomy — the v2 spec (reverse-engineered)

Our current chart is a thin line with a tiny watermark. TrendSpider's is a full terminal-grade panel. The reproduction spec (from 23 full-res charts):

**Canvas & theme.** ~1200×900 (portrait-ish for X), dark navy **not pure black** (`#0E1420`–`#1C1B29`). Gridless price panel; faint subpanel dividers `#232A3D`.

**Header band (top ~6–7%).**
- **Top-left brand lockup** — glyph + wordmark, ~185px wide, full opacity, ~20px inset. *Ours must be this prominent — the current tiny footer mark is the "logo too small" complaint.*
- **Top-right TICKER + TIMEFRAME** — ticker **bold white `#FFFFFF` ~26–30px**, timeframe lighter grey, letter-spaced, uppercase, `(LOG)` suffix on log charts. ("MSFT DAILY", "AMZN WEEKLY (LOG)").

**Price panel.**
- **Candlesticks** (not a line): up lime-green `#4CAF50`/`#3FCF3F`, down red `#E23B3B`/`#E5484D`, filled borderless, thin same-color wicks, body ~60–70% of slot pitch.
- **Right price axis only**, no left axis, no gridlines; muted-grey round-number labels with thousands commas; a **colored last-price pill** (green up / red down) overlapping the axis at the live close.
- **Giant monochrome-white company logo** overlaid on the upper price area — *the signature move.* (Amazon keeps its orange smile as the lone color exception.)
- Optional **50/200 SMA/EMA overlays** with inline same-color labels ("200 EMA" amber).

**Subpanels (stacked, ~12–15% each, own right-axis).** Volume (blue-grey bars) always; then any of MACD (blue line + orange signal), RSI (lavender, 70/50/30 guides), TTM-squeeze histogram (cyan + green/red/yellow dots), or a **horizontal Volume Profile / Point-of-Control** pinned to the right axis (green accepted / red rejected + magenta PoC line).

**Annotation layer (the "technician" work).**
- **Big % change callout box** — rounded rect, filled green/red, white text, two lines: `+207.22 (+136.807%)` / `15 bars (3 months 2 weeks)`. High-signal, appears on most posts.
- **Highlighted signal zone** — translucent circle/disc over the key candle(s), or a support/resistance **zone rectangle**, or a **"buy" RE-ENTRY green pill** with an arrow leader. *This is where we draw the fired-confluence area.*
- White hand-drawn **trendlines / channels / necklines**; pattern labels (H&S "LS/H/RS", double-bottom, triangle apex).
- Milestone discs ("$1T Market Cap"), insider-buy `$` callouts, prev-close reference line.

**Footer.** "©YEAR Mastermind" + "Your local time zone".

**Logo whitening (operator's question — answered).** They knock company logos to **pure monochrome white** (`#FFFFFF`, ~90–100% opacity). The operator's hypothesis is right: the treatment recolors non-white elements to white; AMD's icon stays green because it's a *partial* white-text-only treatment. Two viable pipelines: (a) fetch the color logo (we already reference the `nvstly/icons` CDN) and **alpha-threshold → fill white** (any non-transparent pixel → white) with Pillow; (b) use a logo API that serves monochrome variants. (a) is free and in-house; it loses partial-color treatments but yields the clean white overlay that dominates their charts.

---

## 3. The confluence → chart-post loop (the core new capability)

This is the loop that replaces a human technician. It closes the gap the operator identified ("we do have that engine — tech_lab#combos!").

```
1. tech_confluence.json  →  combos[long|short] ranked by historical win rate,
                            each with `active_now: [tickers currently firing all legs]`
2. Studio picks a fired combo with high edge_wr_test + healthy fires_per_year + active_now non-empty
3. Eligibility gate (the QCOM fix, already shipped): fresh, live, not-invalidated
4. Chart engine renders the ticker's candlesticks + THE COMBO'S LEGS as indicators
   (e.g. if the combo is {macd_cross_up, rsi_turning_up, above_200sma}, draw MACD + RSI + the 200 SMA)
   and HIGHLIGHTS the fire bar(s) with a translucent zone + a "setup" pill
5. Hook model writes a reach-optimized caption: superlative/contrarian + the combo's plain-word edge
   ("$X just triggered a setup that's won 71% of the time over the last 8 years 👀")
   — NEVER naming the raw indicators publicly if we choose to hide technicals; the win-rate stat is the hook
6. Auditor checks: claim provenance (win rate traces to tech_confluence.json), no overstatement,
   disclosure ("historical, not a guarantee"), compliance
7. Post with cashtag + the generated chart
8. Outcome-reopen later: grade it (the receipts habit)
```

Why this beats a human: the human guesses which pattern matters; our engine **already ranked every 2–4-signal stack by out-of-sample win rate** and tells us which are live now. The win-rate number is *itself the most reach-optimized hook we could ask for* ("won 71% historically") and it's honest because it's measured.

**Decision the operator must make (records both ways):** do public charts *show* the technical indicators (TrendSpider does — MACD/RSI panels visible) or *hide* them (earlier instruction: "don't reveal we use technicals, just a buy marker")? These conflict. My recommendation: **show them.** TrendSpider's whole edge is that the technicals ARE the content — the visible MACD/divergence/PoC is what makes the chart credible and shareable, and the win-rate framing ("this setup won 71%") is more compelling than a bare marker. Hiding technicals made sense when the chart was a thin line with a lone marker; a full terminal-grade chart *with* indicators is the product. I'll build the engine to support **both modes** (a `show_indicators` flag) so the operator chooses per-desk, defaulting to *show* for the technical-analysis desks and *marker-only* for the plain flagship.

---

## 4. Master-Technicals — the indicator program (toward ~300)

We have ~58 registered signals + ~25 computed-but-unregistered + core primitives. TrendSpider visibly uses volume (89 charts), **volume profile / PoC** (34+), MACD (21), RSI (10), 200/50 SMA-EMA (17), squeeze (3), put/call gauge (3), and pattern overlays. Our gaps vs. what drives their charts: **VWAP (absent), Volume Profile / Point-of-Control (absent as a computed indicator), and pattern-detection overlays.**

### Phased plan
- **Phase M1 — register what we already compute (cheap, ~25 signals).** Wrap the indicators already in `engine/stock_technicals.py` + `engine/entry_primitives.py` (ADX/DMI, ATR%, OBV-slope, CMF, TTM-squeeze, choppiness, NR7, BBWP, Connors-RSI2, Donchian-position, RS-1/3/6m) into the `tech_catalog.py` SIGNALS registry so the confluence miner can use them. Zero new math; immediate combo richness.
- **Phase M2 — build the highest-value missing indicators.** In priority order by TrendSpider frequency: **Volume Profile / Point-of-Control** (the single most-used differentiator on their charts), **VWAP + anchored VWAP**, Williams %R, CCI, Aroon, Parabolic SAR, SuperTrend, Keltner Channels, Hull MA, Elder Ray, CMO, DEMA/TEMA, linear-regression slope/channel. Each gets a compute fn + a SIGNALS wrapper + registration.
- **Phase M3 — multi-timeframe variants.** Weekly/monthly variants of the M1+M2 set (each a distinct signal id), which is how you cross ~300 and how the miner finds cross-timeframe confluences (TrendSpider's weekly-EMA + daily-MACD style stacks).
- **Phase M4 — pattern detectors as first-class signals.** Head-and-shoulders, double-bottom/top (we have `formations.py`), triangles/wedges, and the volume-profile "acceptance/rejection" — so the chart engine can auto-draw the pattern the way their technician hand-draws it.

Every new indicator flows automatically into `tech_confluence.py` (no miner changes needed — the explore confirmed it accepts any registered signal), which means **more indicators → more discovered high-win-rate combos → more postable, differentiated chart content.** The indicator program and the content program compound.

**On "importing TrendSpider's 300 indicators":** we don't copy their code (we can't and shouldn't). We reproduce the *standard* indicators (all public math) and, more importantly, we have something they don't publish — a **win-rate-ranked confluence miner**. The goal isn't 300 indicators for their own sake; it's enough indicator vocabulary that the miner finds a deep, diverse set of high-edge combos to post about daily.

---

## 5. Breaking-desk programs (news, earnings, Truth-Social, CENTCOM, heatmaps)

TrendSpider's 73 breaking-news + 17 earnings + 9 Truth-Social + 2 CENTCOM posts are a big share of volume and reach ~60–105k. These are **relevance-filtered, summarized, source-cited reposts with a generated illustration** — all automatable.

- **Earnings desk.** On an earnings release, post the numbers instantly with a **company-logo illustration** (Phase M2 logo-whitening → a clean branded card: white logo, EPS/rev vs. est, beat/miss chips, cite "Company IR"). We have the earnings calendar and fundamentals; the missing piece is the logo card renderer (part of the chart engine build).
- **News desk.** A relevance filter over company newsrooms/wires (skip low-signal PR), summarize, cite the source, illustrate. Reuses our existing news/event infra; the new part is the relevance ranker + the summarize-and-cite formatter + an illustration.
- **Truth-Social / CENTCOM trackers.** Poll the specific accounts, screenshot or machine-illustrate the post with **key parts highlighted**, repost as breaking with a market-impact line. (Highest-sensitivity lane — routes through the auditor + a jurisdiction/consequence check before posting; political content is a compliance surface.)
- **Heatmap desk.** We already have 5 heatmaps (S&P, themes, CN, HK, CA) with a generic renderer. Expand types (drone-stock-style **custom-universe** treemaps, "% off 52w-high" coloring, unusual-activity heatmaps) and post "unusual heatmap activity" updates + sector-pain engagement questions (their drone-stocks post format). Low build cost (the renderer is already generic per the capability map).

Each desk is a **department engine** under Broadcast/Radar with its own eligibility + auditor gate; they slot into the existing Content-Studio mixed-tilt model as content types.

---

## 6. Can the Content Studio match TrendSpider with no human manager? (honest assessment)

**Mechanically: yes, and at higher volume.** Chart generation, indicator drawing, signal selection (via the win-rate miner — *better* than a human's eye), formatting, cashtags, and scheduling are all deterministic. We can produce more, faster, and with a measured edge behind each post.

**On taste/judgment: yes, with a gated LLM, not a human.** The two human-technician jobs left are (a) writing the reach-optimized hook and (b) the "is this worth posting / is this claim fair" call. (a) is an LLM copy task constrained by the reach rules in §1; (b) is the auditor + eligibility gate. Neither needs a standing human.

**Where we can BEAT them:** (1) **measured edge** — we can say "this setup won 71% historically" with a real train/test number; they mostly assert. (2) **receipts** — we grade our posts publicly (the outcome-reopen habit); they don't. (3) **volume + breadth** — the miner surfaces dozens of live combos daily across a 200+ universe. (4) **the accountability brand** — our whole positioning is "show your work," which a chart-with-a-win-rate-and-a-later-grade embodies perfectly.

**Where they still lead today, and what closes it:** (1) **chart beauty** — closed by the v2 chart engine (this session). (2) **indicator breadth / volume profile / VWAP** — closed by Phases M1–M2. (3) **breaking-news speed with illustrations** — closed by the breaking-desk programs + logo whitening. (4) **the human's occasional brilliant contrarian hook** — narrowed by a good LLM hook model trained on the §1 rules, and it's the one area where we accept "very good, not always genius."

**Net:** with the v2 chart engine + the confluence→post loop + Phases M1–M2 + the hook model, the Studio reaches TrendSpider's quality bar on the *chart* posts and beats them on *credibility*, autonomously. The breaking/earnings/Truth-Social desks reach parity as those programs land. No human social-media manager required — a gated Opus/Sonnet writes hooks, the auditor governs, and the win-rate miner is the technician.

---

## 7. Build order

1. **Chart Engine v2** (this session) — pure-SVG, TrendSpider-grade: 1200×900 dark-navy, big Mastermind lockup top-left, TICKER+TIMEFRAME top-right, **candlesticks**, volume subpanel, right-axis + last-price pill, **% change callout box**, **highlighted signal zone**, giant-logo slot, footer, `show_indicators` flag (MACD/RSI/MA subpanels + volume profile), and a `render_earnings_card` for the earnings desk. Wired into Content Studio; charts drawn for the eligible signal (Prophet *and* fired-confluence) posts.
2. **Confluence→post wiring** (this session or next) — Studio sources signal posts from `tech_confluence.json` fired combos (win-rate hook), draws the combo's legs, highlights the fire bar.
3. **Phase M1** indicator registration (next) — wrap+register the ~25 computed indicators.
4. **Phase M2** VWAP + Volume-Profile/PoC + top missing indicators (next) — richest ROI for chart beauty + combo depth.
5. **Breaking/earnings/heatmap/Truth-Social desks** (subsequent) — relevance filter + summarize-cite + logo cards, each auditor-gated.
6. **Hook model + reach optimizer** — LLM hook generation constrained by §1, A/B'd on real reach, promoted by the Lab.
7. **Phases M3–M4** (MTF variants + pattern detectors) — cross-300 and auto-draw patterns.

Items 1–2 are concrete engine work; 3–7 are the phased program. The chart engine is the unlock: it makes every downstream desk look TrendSpider-grade.

---

## 8. Standing rules derived (for the Studio's memory)

- Always attach a visual; charts out-reach text by half again.
- Mix stance — post bearish and neutral, not just buys.
- Lead with emotion/superlative + one checkable fact; cashtag always; ask a question on sector posts.
- The win-rate number is the hook. "Won X% historically" beats a bare marker — and it's honest because the miner measures it.
- Every consequential claim traces to `tech_confluence.json` / a Prophet plan; the auditor checks provenance + disclosure; failed/stale signals never post (the eligibility gate).
- Grade posts publicly later (receipts) — the credibility moat.
- Company logos → monochrome white for chart overlays and earnings cards.
- Breaking/political content routes through the jurisdiction/consequence check before posting.
