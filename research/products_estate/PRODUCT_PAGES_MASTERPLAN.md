# Product Pages Masterplan — the three flagship chapters

Operator order 2026-07-28: `products/market-terminal.html`, `products/mastermind-ai.html`,
`products/market-dashboards.html` become intricately crafted, landing-native pages —
same menu/submenu as `index.html`, per-section illustrations, full feature depth.
Program home: this file. Design authority: main loop (Fable) per CLAUDE.md §Design lane.
Build authority: Opus `builder` lanes. Committed references:

- `mockups/refs/products/_skeleton.html` — the EXACT chrome (nav/gear/footer/JS byte-copied
  from `site/index.html`, hrefs depth-fixed) + the shared design-system layer. Builders start
  from this file; do not re-derive chrome.
- `site/index.html` + `site/landing.css` — the "Neural Cover" family: tokens, type, feature
  idioms (`.feature/.feat-grid/.demo/.live-tag/.lanes/.sf/.tapp`), reveal (`.rv` + `--d`).
- `mockups/x-ads-2026-07/index.html` — the Codex Category ad set (PR #3883): drawn Terminal
  browser surface, Prophet signal card (stage meter, entry/invalidation cells), desk chips,
  capability pills, two-tone gradient headline. Lift component CSS from here where specified.

## §0 ACCEPTANCE GATES — not done unless

1. **Chrome parity**: nav (3 dropdown panels + Pricing), gear popover (EN/中文 toggle,
   account block), footer are byte-equivalent to the skeleton's blocks (which mirror
   index.html) apart from the sanctioned `aria-current` addition. All internal hrefs
   resolve from `/products/` depth (`../…`). Breadcrumb + `est-crumb` markup present.
2. **Fresh-eyes happy path, zero manual workarounds**: page loads from the local preview
   server with console clean (no errors; warnings triaged), every nav panel opens/closes
   by mouse, keyboard (ArrowDown/Escape) and mobile toggle at 375px, gear language switch
   flips EN⇄中文 instantly and persists on reload.
3. **Bilingual parity**: EVERY visible string carries `data-zh` on its leaf element (inline
   `<b>/<i>/<span>` allowed inside the attr). 中文 is native plain Mandarin — no raw EN
   state names, no translated text in `title=` attributes (CI-guarded). Vignette labels
   included. The ILLUSTRATIVE tag reads 示意 in zh.
4. **Doctrine compliance** (docs/DESIGN_DOCTRINE.md): stance words on signal-shaped copy;
   no banned Tier-1 vocab (no engine/study/internal names, no bare stats); numbers arrive
   with meaning; NO invented counts/rates — every factual number traces to the source cited
   in this plan (landing, plans.html, or census line). "validated" never appears.
   Falsifier/refutation vocabulary never appears (windows/projection language only).
5. **Honesty furniture**: every drawn vignette that shows figures carries the
   `live-tag ill` ILLUSTRATIVE/示意 tag; each page carries the access/limitations callout
   station and the microline "Market intelligence, not individualized investment advice.
   Product UI examples are illustrative." (EN+zh) above the footer; pricing boundary is
   stated as "the pricing page owns the current access boundary" — no hardcoded prices
   (Founding rate is withdrawal-sensitive; never restate the dollar figure).
6. **Motion floor**: `.rv` reveals via the skeleton's IntersectionObserver; all bespoke
   animation respects `prefers-reduced-motion` (landing.css patterns); `?still` query
   freezes motion for QA capture. No animation on the honesty station.
7. **Performance/self-containment**: no new external requests beyond the skeleton's asset
   set (onboard.css, landing.css, mm_brain.js, onboard.js, wh_banner.js, favicon set). No
   webfont additions, no images — every illustration is DOM/inline-SVG. Page ≤ ~140KB.
8. **Verification artifacts returned to the commissioning session**: full-page screenshots
   desktop EN + ZH, mobile 375px EN, plus a crop of each section vignette. Builders do NOT
   run git; the commissioning session reviews, commits, and ships.
9. **Suite**: `python3 -m scripts.build_free_content --check` exits 0 (carve-out landed);
   `python3 -m pytest tests/test_free_content.py tests/test_builder_shim_writes.py -q` green;
   `python3 -m scripts.check_template_site_sync` untouched by this work (no template pairs edited).

## §1 Architecture & ship path

- The three pages are HAND-AUTHORED SOURCE files in `site/products/` (carved out of
  `scripts/build_free_content.py` via `HAND_AUTHORED`; the generator keeps consuming
  `content/seo/products/*.md` front-matter for the products hub + related links only).
- Ship path: plain-copy site files → commit to main → VPS 3-min pull. No render needed.
- Keep the CURRENT pages' SEO head shapes verbatim where noted: `<title>` pattern,
  meta description (refresh copy allowed, same length class), canonical, OG/twitter,
  `BreadcrumbList` + `WebPage`+`SoftwareApplication` JSON-LD (update descriptions to match
  new copy). Keep the `data-dbase` shim (skeleton has it).
- Scripts: skeleton tail only (`MM_API` global + mm_brain.js + onboard.js + wh_banner.js).
  NO theme.js, NO supabase.js/account.js — the landing chrome (onboard.js) owns gear/auth.
- zh directional colors: the landing family ships house colors (green-up) even in zh —
  these pages match the landing (family consistency; vignettes are ILLUSTRATIVE-tagged).

## §2 Design system (family voice)

- **Field**: porcelain `--bg`, white panels, hairlines; dark moments only inside product
  chrome (`.sf` browser plate, `--plate` navy) and the `cband` closer. Light-only page.
- **Type**: everything inherits landing tokens. Display = `var(--display)` 800 tight.
  Kickers = `.kicker` colored `var(--pg-accent)` per page. Figures request `tnum`.
- **The one gradient**: each hero H1 = line 1 ink, line 2 `.pgrad` (blue→violet→teal arc,
  the ads' family arc). Gradient appears ONCE per page (hero). Section titles stay ink.
- **Per-page accent** via `--pg-accent` on `<body>`: Terminal `var(--blue)`,
  Mastermind AI `var(--violet)`, Dashboards `var(--teal)`. Accent drives: kicker color,
  chapter-ribbon underline, `.anno` dots, vignette highlight strokes. Q-colors stay
  reserved for market semantics inside vignettes.
- **Chapter ribbon** (`.chap`, in skeleton): `01 Market Terminal · 02 Mastermind AI ·
  03 Market Dashboards` — real pillar order (matches nav-card marks 01/02/03), current
  chapter inked + accent underline, siblings link across. Sits at the top of `.phero`.
- **Section anatomy** (the landing's, deepened): `section.feature[.flip]` → `.feat-grid` →
  copy column (`.kicker` + `.feat-title` 2-line + `.feat-sub` + `.fx` bullets with bold
  lead-ins + `.feat-cta`) beside a `.demo` panel vignette. EVERY section has a vignette.
  Between-pillar dividers: `.section-pad.hair-top` rhythm as on the landing.
- **Vignette doctrine**: DOM-drawn miniatures of the real product (divs + tiny inline
  SVGs, landing/ad idioms) — never screenshots, never Plotly. Honest labels: `PREVIEW`
  only when the element live-loads real data (none planned here); otherwise
  `ILLUSTRATIVE/示意`. Delayed/limited-data pills where the real product shows them
  (e.g. 15-MIN DELAYED) are part of the drawing — honesty is a visual feature.
- **Annotation callouts** (`.anno`): ≤4 per hero artifact, desktop-only, thin hairline
  pills naming what the viewer is seeing. None inside body sections (heroes only).
- **Reveal choreography**: hero copy `rv` immediate, artifact `rv --d:.12s`; per section
  copy then vignette `--d:.1s`; wall/grid children stagger `--d` by index ≤ .4s.

## §3 Page 01 — market-terminal.html (accent blue)

SEO: title `Market Terminal & Browser Charting — MastermindX` (keep); slug market-terminal.
Meta description (new, ≤160c): "Institutional-grade charting in your browser — candles,
indicators, watchlists, key stats, engine reads and Mastermind AI beside the chart. Free to start."

HERO — kicker `The Terminal` / 终端
H1: `Institutional charting,` / `机构级图表，` + grad `with a desk built in.` / `台席内建其中。`
Sub: "Candles, indicators and live watchlists in your browser — nothing to install. Beside
the chart: ranked signals, key stats, filings and Mastermind AI. <b>Free to start, in seconds.</b>"
zh: "蜡烛图、指标与实时自选就在浏览器里——无需安装。K线旁边：分级信号、关键数据、申报披露与
Mastermind AI。<b>免费开始，几秒上手。</b>"
CTAs: `Open the Terminal →` (https://app.mastermind-x.com) primary; `See plans` ../plans.html.
Micro: `FREE CORE ACCESS · NOTHING TO INSTALL` / 核心功能免费 · 无需安装.

Hero artifact — **the browser IS the hero**: full-width `.sf` frame (clone the landing
tsec `.sf/.sf-bar` chrome exactly, URL app.mastermind-x.com/terminal), inside it a rich
`.tapp`: the landing's tt-top bar (logo/symbol NVDA/Compare/Last/24H/Volume/day-range/
Mastermind AI button/avatar — reuse markup, but replace the landing's "Live" pill with an
honest basis pill reading `15-MIN DELAYED`/`延迟15分钟` — that is what the real product
shows on US symbols, and the approved ad drew exactly this), then a two-pane body: left = candle
chart (staggered `<rect>` candles fade-in + two MA `<path>`s dash-drawing + volume bars +
an RSI subpane), right = watchlist rail (CRYPTO: BTC-USD, ETH-USD · EQUITIES: NVDA, AAPL,
MSFT with q-color changes). Overlaid bottom-right: the **intelligence-layer card** (ad
mx-cat-03 idiom): `NEAR` pill + NVDA + `EDGE 81`, `.ezc` entry/invalidation cells, stance
line "Setup intact; entry gate closed. Regime, theme and flow agree — wait for price." /
"结构完好；入场门未开。格局、主题与资金流一致——等价格。" ILLUSTRATIVE tag on the frame.
`.anno` pins: "Live quote strip"/实时报价条 → top bar; "Your watchlists"/你的自选 → rail;
"Engine read — its own timestamp"/引擎研判——独立时间戳 → card; "Draws with you"/随手绘图 → chart.

CENSUS-PINNED FACTS for this page (charting-app terminal, cited by the census lane —
numbers usable in copy, nothing else): 14 timeframes in 5 groups · 5 chart types
(candles/heikin/bars/line/area) · up to 4 chart panes + one-click MTF split · bar replay ·
Day Trade Mode · 21 core studies + 31 advanced modules across five complementary systems ·
a Pine-style editor (the complete system library and saved custom scripts are Pro;
exact tier counts live on pricing surfaces) · 9 drawing tools + 4 auto-detection modes (auto trendlines, auto Fib,
S/R heatmap, MTF S/R) · 5 markets (US · China A · Hong Kong · Canada · crypto) · honest
freshness badges (LIVE / 15-MIN DELAYED / end-of-day basis tags) · full fundamentals
dossier tabs (statements incl. earnings-call transcripts, earnings, dividends, forecast,
insider gauge, seasonality) · 10-tab options suite (Prophet · Flow Desk · Tape · Tide ·
Tickers · Screener · GEX · PRISM · Leaders · Radar) · 6 alert condition types · screener +
conviction-book portfolio view · market heatmap · chart snapshot & share links · EN/中文.
FORBIDDEN claims (census-flagged): cross-device/account sync of watchlists, alerts,
layouts or scripts (login is disabled in prod today); any model name for the in-terminal
assistant; "live everywhere" quotes (US/crypto legs are 15-min delayed; Canada has no
intraday); Prophet as a proven track record; the 9 engine-coded but unpickable indicators;
PRISM VEX/Unusual lenses; heatmap 1W/1M/YTD.

SECTIONS (feature/flip alternating; each with `.demo` vignette):
1. `#charting` — kicker Charting engine/图表引擎 · title "Every timeframe,<br>one chart." /
   "从日内到月线，<br>一张图。" · sub: candles to monthly across 14 timeframes and 5 chart
   types, up to 4 synced panes, bar replay and a one-toggle Day Trade Mode. fx: **14
   timeframes, 5 chart types.** minutes to months · **Four synced panes.** one click lays
   D/3D/W/1M · **Replay the tape.** step history bar by bar. Vignette: chart panel with
   timeframe tab row (D · 3D · W · 1M), price strip + two stacked indicator panes, a
   replay scrubber chip.
2. `#indicators` — Indicator systems/指标体系 · "Five complementary systems.<br>One clearer
   technical workflow." / "五套互补系统。<br>一条更清晰的技术流程。" · customer-level story, not documentation:
   31 advanced modules grouped into Structure Core, Trend Waves, Pulse Oscillator,
   RSI Ultimate and MACD Ultimate. fx: **31 advanced modules.** Focus / Workflow /
   Research depth · **From structure to trade management.** context, rotation,
   confirmation, risk and TP1–TP6 · **Honest multi-timeframe context.** responsive
   Chart plus completed 2× and 4× blocks. Vignette: a finite four-stage illustration (structure → rotation →
   confirmation → targets/risk) with manual steps, replay, visibility pause and a
   reduced-motion final state. Below it, five compact system cards and one understated
   "All five, complete · Available in Pro" signature. Insider is described as a curated
   selection and the plans page owns exact tier counts; do not duplicate a pricing-card
   ladder here. Pine-style editor stays a secondary note; saving custom scripts is Pro.
3. `#watchlists` — Watchlists & quotes/自选与报价 · "Watchlists with<br>honest quotes." /
   "自选列表，<br>报价如实标注。" · sub: named lists with sections and drag order; every
   quote wears its basis — LIVE, 15-MIN DELAYED or end-of-day — because pretending
   everything is live is how desks lie. fx: **Sections that match how you think.** crypto ·
   equities · themes · **Basis badges on every quote.** live, delayed or settled ·
   **Five markets.** US · China A · Hong Kong · Canada · crypto. Vignette: watchlist rail,
   grouped, one row mid-update + a 15-MIN DELAYED basis pill.
4. `#dossier` — The dossier/个股档案 · "The filing cabinet<br>behind the chart." /
   "图表背后，<br>整柜资料。" · sub: statements with earnings-call transcripts, earnings
   with estimates and surprises, dividends, analyst forecast fans, an insider-conviction
   gauge and multi-year seasonality — per symbol, beside the chart. fx: **Statements to
   transcripts.** one click deep · **Forecast fans, honest.** targets drawn as ranges ·
   **Seasonality that admits variance.** Vignette: fanned dossier tab cards (Overview /
   Statements / Seasonality), top card detailed.
5. `#signals` — Engine reads/引擎研判 · "The desk's read,<br>one glance away." / "台席研判，<br>一眼可及。"
   · sub: when MastermindX engines carry a current reading for the symbol, the Terminal
   shows it beside the chart — with its own timestamp, never pretending to share the
   chart's. fx: **Stances in plain words.** · **Its own timestamp.** · **Nothing to chase** —
   when the honest read is wait, it says wait. Vignette: intelligence-layer card (hero
   idiom, smaller) with `.stgm` stage meter (Bottoming→Turning→Ready→Trend, Ready on).
6. `#options` — Options suite/期权套件 · "A ten-desk<br>options floor." / "十个页签的<br>期权台。" ·
   sub: flow desk, tape, market tide, per-ticker IV surface and smile, GEX strike ladders
   and a structure matrix — live options requires an eligible plan; the pricing page owns
   the boundary. fx: **Flow, tape and tide.** the day's options money · **GEX walls
   drawn.** where hedging pins price · **Plan-gated, said plainly.** live options is the
   paid line. Vignette: mini GEX strike ladder + flow rows + a plan chip (lock glyph +
   "Live options · Insider & Pro"/实时期权 · Insider 与 Pro).
7. `#ai` — Mastermind AI/Mastermind AI · "The analyst rides<br>in the terminal." /
   "分析师就坐在<br>终端里。" · sub: open the copilot on the symbol you're reading — it can
   explain a field, mark support and resistance on the chart, or screen the universe, and
   it shows the tools it called. A research aid: check it against the source. NO model
   names. CTA `Meet Mastermind AI →` mastermind-ai.html. Vignette: compact chat bubble
   pair with symbol chip + a drawn level line annotation + a "tools called" chip row.
8. HONESTY STATION `#access` (`.callout` + prose, no vignette): keep the shipped copy —
   "Research workspace, not execution venue" · The Terminal does not place trades; data,
   research panels and engine outputs update on different schedules; some live options or
   intraday features require an eligible plan or trial; the pricing page owns the current
   access boundary. + timestamp line. zh twin required.
CBAND closer: "The desk is open." / "台席已就绪。" · Start free + Open the Terminal + trust
dots (landing cband idiom, no card required / nothing to install / cancel anytime).

## §4 Page 02 — mastermind-ai.html (accent violet)

SEO title: `Mastermind AI — Market Research Assistant — MastermindX` (keep current form).
Meta description: "An AI analyst grounded in the page you're on — it cites the desks it
used, draws what it means, and leaves decisions to the engines. Flash and Pro modes."

CENSUS-PINNED FACTS for this page (the SITE assistant — mm_brain.js + chat.html +
brain_gateway; the Terminal's in-app copilot is a separate implementation and is covered
on the Terminal page): floating launcher across the site's pages · full-page "Ask the
Mastermind" chat with thread history (../chat.html) · hover-any-panel "Ask the Brain" orb
that pre-loads "explain this panel" · active-symbol chip + live dashboard-state snapshot
ride with every turn · slash commands /chart /research /explain · live narrated reasoning
strip that collapses into an "Analyzed for Ns · N checks" receipt (expandable) · up to 8
citation chips linking to the source dashboards · contradiction honesty (disagreeing
boards reported as unresolved, never averaged) · every answer ends with exactly one plain
stance (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore) ·
inline branded chart drawn inside the reply · three follow-up chips after every answer ·
turns survive a closed tab (server keeps the run; reopening resumes) · image attach (up to
4 charts/screenshots) on the Pro lane · Fast ⚡ / Pro ◈ lane toggle (LIVE widget naming) ·
public lane names: "Mastermind chat" (fast) and "Deep Opus chat" (heavyweight, no version
numbers) · Free tier: 5 quick questions a week (plans.html) · Deep Research forces the Pro
lane and produces a structured multi-section report (regime, rotation, positioning,
tensions, what's ahead).
FORBIDDEN claims (census-flagged): "Flash AI/Pro AI" naming and the landing demo's quota
copy ("unlimited on Insider", "20-page/20-50 per mo" — all stale/cosmetic); any model
version numbers; raw chain-of-thought visibility (the strip is a narrated activity trace);
a user-visible response-log/audit surface (admin-only); anonymous no-signup access
(default off); "it never gives a direct answer" framing (direct stance answers are
shipped); citations in the Terminal copilot.

HERO — kicker `Mastermind AI`
H1: `Ask the desk anything.` / `有问题，问台席。` + grad `It answers with receipts.` / `回答必附出处。`
Sub: "Mastermind AI reads the desks before it speaks — signals, filings, flow, the
regime — cites what it used, and ends every answer on a plain stance. <b>Even when the
stance is wait.</b>"
zh: "Mastermind AI 开口前先读完各台席——信号、申报、资金流、市场格局——引用所依据的来源，
并以一句大白话立场收尾。<b>哪怕立场是「先等」。</b>"
CTAs: `Ask Mastermind →` ../chat.html · `See plans` ../plans.html.
Micro: `FAST LANE FREE TO TRY · 5 QUESTIONS A WEEK` / 快速通道免费体验 · 每周5问.

Hero artifact — **a conversation with receipts**: large `.chat` panel (landing #ai idiom,
deepened; segment reads `⚡ Fast / ◈ Pro` — the LIVE widget's naming, NOT the demo's):
thread showing one exchange — user: "What changed in semiconductors this week?"/
「这周半导体发生了什么变化？」; answer streaming with (a) a collapsed reasoning receipt chip
"Analyzed for 6s · 4 checks"/「分析6秒 · 4项核对」, (b) two short plain sentences, (c) an
inline drawn mini-chart (violet level lines on a candle strip), (d) three CITATION CHIPS:
Macro regime · Options desk · Factors (the real citeToPage routes), (e) a closing stance
line "Watch — don't chase."/「观察——不追高。」, (f) three follow-up chips; composer below
with an image-attach glyph + send. ILLUSTRATIVE tag.
`.anno` pins: "Shows its working"/展示分析过程 → receipt chip; "Citations open the real
desk"/引用直达台席 → chips; "Every answer lands on a stance"/每个回答都有立场 → stance line.

SECTIONS:
1. `#everywhere` — Entry points/入口 · "One analyst,<br>every page." / "一位分析师，<br>每页都在。" ·
   sub: a floating launcher rides the site; a full-page desk with saved threads lives at
   Ask the Mastermind; hovering any dashboard panel offers "explain this panel"; in the
   Terminal it opens on the active symbol. fx: **Launcher on every page.** · **A full-page
   desk with history.** · **Answers survive the tab.** close it mid-answer; the run
   finishes and resumes when you return. Vignette: three entry chips (bubble / full page /
   panel orb) strung to a violet core.
2. `#grounded` — Grounding/上下文 · "It reads the page<br>you're reading." / "你看哪页，<br>它读哪页。" ·
   sub: the active symbol and a snapshot of the dashboard state ride along with your
   question — you never re-type what the screen already says. Slash commands jump lanes:
   /chart, /research, /explain. Vignette: context chip (NVDA · US stocks) flowing along a
   hairline into a composer + a small slash-palette card.
3. `#receipts` — Receipts/出处 · "Answers that<br>show their work." / "每个回答，<br>都亮出功课。" ·
   sub: while it works you watch the steps; when it's done the strip folds into a receipt —
   and citation chips under the answer open the exact desks it used. fx: **A working
   receipt.** "Analyzed for Ns · N checks", expandable · **Citations open the real page.**
   up to eight chips per answer · **Disagreement said out loud.** conflicting boards come
   back "unresolved", never averaged into mush. Vignette: answer block + expanded receipt
   step-list + citation chip row, one chip hover-popped.
4. `#stance` — Stances/立场 · "Every answer lands<br>on a stance." / "每个回答，<br>落在立场上。" ·
   sub: it answers the question you actually asked — plainly, and always closing on one of
   six stances, even when the honest one is wait. Vignette: the six stance chips in a row
   (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore), one lit,
   with zh twins.
5. `#draws` — Visual answers/可视回答 · "It draws<br>what it means." / "它会画出<br>自己的意思。" ·
   sub: a branded chart can appear inside the reply; on the Terminal it marks support and
   resistance from fetched data — never invented levels; attach up to four charts or
   screenshots for image analysis on the Pro lane. Vignette: reply bubble containing a
   mini chart + level labels + an attach chip with a small ◈ Pro tag.
6. `#lanes` — Fast & Deep/快与深 · "Fast for the question.<br>Deep for the research." /
   "快，答问题。<br>深，做研究。" · sub: the Fast lane answers quick market questions — free
   to try at five a week; the Deep Opus chat lane and Deep Research produce structured,
   multi-section reports — regime, rotation, positioning, tensions, what's ahead. Metered
   by plan; the pricing page owns the numbers. Vignette: two lane cards ⚡/◈, the deep one
   with a report outline peeking out (section list), each with a small meter chip.
7. HONESTY STATION `#guardrails` — callout keeps the SHIPPED product-page line verbatim:
   "A cited answer can still be wrong" / 「有出处的回答，也可能出错」 — Mastermind AI can be
   incomplete, misread a source or lag the latest market move. It does not place trades or
   provide personalized investment advice. Verify important claims against the linked
   evidence and its timestamp. + microline: research, not advice; it never touches order
   flow. + the illustrative microline.
CBAND: "Ask your first question." / "提出你的第一个问题。" · Ask Mastermind → ../chat.html + See plans.

## §5 Page 03 — market-dashboards.html (accent teal)

SEO title: `Market Intelligence Dashboards — MastermindX` (keep current form).
Meta description: "Macro regime, plain-language stock lanes, theme rotations, filings,
options flow, China and HK — a full research floor, rebuilt nightly. Free to read."

HERO — kicker `The Dashboards` / 市场仪表盘
H1: `Every desk, one floor.` / `所有台席，同层排开。` + grad `Rebuilt every night.` / `每晚整体重建。`
Sub: "Macro regime, stock lanes, rotations, filings, flow, China and HK — the whole floor
reads the market together, and the engines check each other's work. <b>Free to read.</b>"
zh: "宏观格局、个股通道、主题轮动、申报披露、资金流、中国与港股——整层台席一起读市场，
引擎相互校验。<b>免费阅读。</b>"
CTAs: `Open the dashboards →` ../start.html · `See plans` ../plans.html.
Micro: `FREE TO READ · REBUILT NIGHTLY` / 免费阅读 · 每晚重建.

Hero artifact — **THE WALL**: a staggered grid (2 rows × 4-5 on desktop, scrollable column
pairs on mobile) of miniature drawn dashboard cards, each = tiny vignette + real display
name + one-word state chip, each an `<a>` to the REAL page (all verified on disk):
Regime dial → ../macro.html · Stock lanes → ../us_stocks.html · Theme rotations →
../baskets.html · Filings desk → ../congress_trades.html · Options flow →
../intraday_flow.html · China desk → ../china.html · Hong Kong → ../hk.html · News →
../news.html · Leader radar → ../leader_radar.html · Cycle Intelligence → ../cycle.html ·
Bitcoin Vector → ../vector.html · Track record & calibration → ../measurement.html.
(12 tiles; no prophet.html exists — do not invent tiles.) Tile microcopy reuses each
page's OWN shipped voice where given: "Observation, not prediction" (leader radar),
"windows, not certainties" (cycle), "Measured, not asserted" (calibration). Corner
ILLUSTRATIVE tag; cards stagger-reveal. The wall IS the sitemap — hover lifts +
"open"/打开 affordance.
`.anno` pins: "Each tile is a real page — free to read"/每块都是真实页面——免费阅读 · "States,
not scores"/状态，而非分数 · "Rebuilt nightly"/每晚重建.

SECTIONS:
1. `#regime` — The regime/市场格局 · "Start with<br>the weather." / "先看<br>大势。" · sub:
   the morning read answers whether this is a market to press or to protect — in plain
   stance words. Vignette: regime quadrant + dial with plain anchors + a one-line stance
   chip ("Risk on — leaders first"/「偏险资产占优——龙头先行」 form, ILLUSTRATIVE).
2. `#lanes` — Stock lanes/个股通道 · "Stocks in<br>plain lanes." / "个股按<br>大白话分道。" · sub:
   ranked names sorted into lanes whose names ARE the stance — Buy now · Almost ready ·
   Take profits · Stand aside (cite index.html:489-492). fx: **Lane names are stances.** ·
   **Unknown states park in the cautious lane.** · **Every lane opens into the names.**
   Vignette: 4-lane board with chips (landing #lanes idiom, richer: one chip mid-move).
3. `#rotations` — Theme rotations/主题轮动 · "34 themes,<br>watched nightly." / "34个主题，<br>每晚重排。"
   (count cite index.html:475) · sub: money rotates; the board shows chips changing lanes
   as leadership turns; every basket opens into ranked members. Vignette: rotation ribbon —
   theme chips crossing between two lanes with motion trails.
4. `#filings` — Filings/申报披露 · "Insiders and Congress,<br>read and scored." /
   "内部人与国会申报，<br>逐份读取打分。" · sub: 96,000+ disclosures read and scored to date;
   clusters beat one-offs; entry timing included (cites index.html:507-509,520-521).
   Vignette: filings feed rows + summary cell (fi-sum idiom).
5. `#flow` — Options flow/期权资金流 · "Flow, beside<br>the tape." / "资金流，<br>对着盘面看。" ·
   sub: intraday options flow with honest freshness labels — delayed marks stay visible.
   Vignette: flow tape rows with side chips + a freshness pill (≈15-min delayed form).
6. `#china` — China & HK/中国与港股 · "China and Hong Kong,<br>read natively." /
   "中国与港股，<br>本土视角解读。" · sub: A-share breadth, sector desks and HK context built
   from native sources, bilingual by design. Vignette: dual-market strip (上证/深证/HK chips
   + breadth bars + a zh-first label pair).
7. `#record` — Track record/公开留档 · "Every call goes<br>on the record." / "每次研判，<br>都公开留档。" ·
   sub: reads are timestamped when made and graded after the market answers — including
   the wrong ones. Projection windows, re-drawn nightly; full verdicts live in the
   Calibration Lab. NO invented win-rates. Vignette: graded-calls strip (✓/✗/… chips over
   dated stubs, ILLUSTRATIVE) + "windows, not certainties"/「是窗口，不是定论」 microcopy.
8. `#beyond` — Beyond stocks/股票之外 · "One floor,<br>every asset." / "一层台席，<br>纵览资产。" ·
   sub: the same engines run Bitcoin, commodities, bonds and the dollar — same plain
   words (cite index.html:587; commodities desk covers 17 members, commodities.html:39).
   fx: **Bitcoin Vector.** regime with a stance · **17 commodities on one board.** ·
   **Rates, credit and the dollar.** transmission in plain words. Vignette: four asset
   chips (₿ · 🛢 · 🏛 · $) with mini-sparklines strung to one engine node.
9. `#nightly` — The engines/引擎 · "Engines that check<br>each other's work." /
   "引擎之间，<br>相互校验。" · sub: every night the floor is rebuilt as one piece — signals
   cross-checked against filings, flow and regime; when a signal has no edge, the page
   says so in plain words. Vignette: nightly conveyor — moon glyph → three engine blocks
   with cross-checking hairlines → page cards stamped "rebuilt nightly"/每晚重建.
9. HONESTY STATION `#access` — callout "Free to read, honestly labeled" / 「免费阅读，如实标注」:
   dashboards are free to read; some desks and live features require an eligible plan —
   the pricing page owns the boundary; every surface carries its own timestamp; readings
   are research context, not individualized advice. + illustrative microline.
CBAND: "Walk the floor." / "逛一圈台席。" · Open the dashboards → + Start free.

## §6 Copy & claims law (binding)

Numbers allowed ONLY with a source: 34 themes (index.html:475), 96,000+ disclosures
(index.html:507; 96,412 figure index.html:520 — use the rounded form in prose), Flash/Pro
allowances (index.html:659-660), lane names (index.html:489-492), AI caps (index.html:645-648).
Census additions must carry their file:line into the PR body. Everything else: plain words,
no counts. Banned: validated · falsifier/refuted · internal state/study names · bare stats.
Landing-approved phrases reusable verbatim: "It explains; the engines decide." · "engines
that check each other's work" · "graded after the market answers" · "Free to read." ·
"windows, not certainties — re-drawn nightly".

## §7 Verification protocol (builders + commissioning session)

Local preview via the repo's static server (`python3 -m http.server` from `site/` is
acceptable for these plain pages) or the session Browser pane; check: console clean; nav
panels (mouse/keyboard/mobile); EN⇄zh gear flip + reload persistence; reveal choreography;
`?still` freeze; 375px layout; reduced-motion emulation. Screenshots per §0.8. The
commissioning session re-verifies independently before commit, then runs the ship loop.
