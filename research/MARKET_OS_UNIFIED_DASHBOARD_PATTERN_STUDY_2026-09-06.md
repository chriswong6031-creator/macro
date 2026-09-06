# Market OS — Unified Dashboard Pattern Study (2026-09-06)

**Commission:** Chairman directive 2026-09-06 — "clear and user friendly, not wicked advanced,
not machine text and too much text; see marketontology's dashboard, theirs is super nice."
**Audience:** both Market Ontology Meta-CEOs (A and B). Words only; no build in this document.
**User job it serves:** a retail fintech-SaaS user opens ONE dashboard and can tell, in plain
words, **what the product knows, what is missing, and what to do next** — without machine text
and without walls of text.

---

## 0. Method

### 0.1 What was actually observed, and at what width

Browser: the user's real Chrome, via the Claude-in-Chrome extension, in a new tab in the MCP tab
group. Session date 2026-09-06 (page clocks read 11:07–11:08 PM local on the marketing surface).

| # | Surface | URL | Width observed | Capture |
|---|---|---|---|---|
| 1 | Marketing home (product thesis + embedded live feed panel) | `marketontology.com/` | 1095×906 desktop | screenshot + full text |
| 2 | Route-not-found state | `/app` | 1095×906 | screenshot + text |
| 3 | Auth wall (sign-in / create account) | `/auth?redirect=/dashboard` and `?redirect=/public` | 1095×906 | screenshot + a11y tree |
| 4 | Prediction ledger (public forecast record) | `/ledger` | 1095×906 | screenshot + full text + a11y tree |
| 5 | Desk / teams surface, incl. the live **Intelligence Feed** panel | `/map/desk` | 1095×906 | screenshot + full a11y tree |
| 6 | Macro dashboard product page | `/macro-dashboard` | 1095×906 | screenshot |
| 7 | Live-map hub, incl. the Intelligence Feed in its **detailed** density | `/map` | 1095×906 + one window-resize to 390×844 | screenshot + a11y tree |

Total: 8 screenshots at scale 0.5, none written into this repository.

### 0.2 The honest limit on this study — read before using it

**The authenticated dashboard ("Capital Command") was NOT reachable from this browser session.**
Every authenticated route (`/dashboard`, `/public`) redirected to `/auth?redirect=…` with a
create-account form. The Chairman's message said the site is logged in; this Chrome profile, as
exposed through the extension's MCP tab group, is not. Signing in is prohibited to me (entering
credentials is a prohibited action, and no session cookie was available to reuse), so I did not
attempt it and did not create an account.

Consequently:

* **Sections 1.1–1.9 are grounded in the *unauthenticated* product surfaces** — which are
  substantial: the live Intelligence Feed panel renders real, dated, scored rows inside `/map`
  and `/map/desk`, the prediction ledger is a full product-grade data page, and the marketing
  spine states the product's own workflow vocabulary. What I could NOT observe is the rail
  grouping, top product tabs, sub-tabs, KPI strip, and settings of the logged-in shell.
* **Every claim below is labelled `[observed]` or `[inferred]`.** Nothing about the logged-in
  rail is asserted as observed.
* **Meta-CEO A/B should re-run §1 against the logged-in shell** before freezing an IA. §4 lists
  exactly which questions that re-run must answer.
* Mobile: the resize call succeeded at the window level but the page's own viewport still
  reported 1095×906 at capture time, so **I did not obtain a true 390px rendering.** Responsive
  claims in §1.9 are `[inferred]` from the composition, not measured.

### 0.3 No-copy statement (charter §7)

No Market Ontology text, code, CSS, icon, font, colour value, or datum is reproduced, adapted,
or carried into this repository. Patterns are described in my own words. Exactly one phrase is
quoted, as a four-word example of register: the feed section heads itself with the promise of a
current public map **"with sources and timestamps."** Their instrument tickers, impact scores,
ledger rows, and headline text are deliberately not transcribed. Nothing in §2 or §3 asks anyone
to clone their layout — §2/§3 are our own doctrine applied to our own data.

---

## 1. The observed pattern

### 1.1 The one idea worth stealing (in the legal sense: the *principle*, not the artefact)

`[observed]` The whole product is organised around **one repeated unit of meaning** — a
development — and **four fixed verbs** the user can apply to it. Every feed row carries the same
four actions, in the same order, always enabled. The marketing spine names the same four:
build a thesis, find trades, audit holdings, monitor.

Why it reads as "super nice" and not "wicked advanced":

1. **The user never has to learn a taxonomy to act.** There is one card shape and four verbs.
2. **Every card is complete.** Category, headline, one-line consequence, affected instruments,
   a score, a timestamp, and the four actions — one row, no drill required to know if it matters.
3. **The verbs are outcomes, not features.** "Audit holdings" is a thing a person wants; it is
   not a module name. Contrast our estate's habit of naming a page after its engine.
4. **Density is the user's choice, not the designer's.** A three-way density switch sits at the
   top of the feed (compact / detailed / briefing). The wall-of-text problem is solved by
   letting the reader ask for the wall, never by defaulting to it.

### 1.2 Information architecture

`[observed]` Two chrome families are in play on the unauthenticated side — a marketing header
(Product / Research / For teams / Ledger / Pricing / Sign in / one gold primary button) and a
"map" header (Live Maps / Product / Pricing / For Teams / API / Sign in / one gold primary
button). Both are **six items or fewer plus exactly one primary action.** No mega-menu, no
nested flyouts, no icon rail on the public side.

`[observed]` Within a page, the top-level rhythm is: eyebrow (small caps, one or two words) →
one large sentence-case headline → one short paragraph → the live module. The eyebrow does the
job our estate does with breadcrumbs, and costs one line.

`[inferred]` The logged-in shell almost certainly reuses the map header's item count discipline
with a left rail; the feed panel observed inside `/map` is plainly a shell-grade component
(it carries its own refresh control, density switch, and filter row), i.e. it is the dashboard's
centre module rendered in a preview frame.

### 1.3 The feed card — the atomic unit

`[observed]` Anatomy, top to bottom, left to right:

```
┌ INTELLIGENCE FEED ─────────────────────────────────── ⟳ ┐
│ COMPACT · DETAILED · BRIEFING            ← density switch │
│ ALL · FOR YOU · MACRO · GEOPOLITICAL · CAPITAL · FX ·     │
│ OPTIONS · TICKERS                        ← scope filters  │
├───────────────────────────────────────────────────────────┤
│ CATEGORY EYEBROW                              IMPACT      │
│ Headline, sentence case, wraps to 2 lines        94       │
│ One-line consequence summary, clipped with an ellipsis    │
│ [▲ instrument] [▲ instrument] [▼ instrument]  YESTERDAY   │
│ ── action row: four verbs, always present ──              │
│ ── secondary row: four destinations ──                    │
└───────────────────────────────────────────────────────────┘
```

Load-bearing details:

* **The score is a right-rail number with a one-word label above it**, not an inline statistic in
  the sentence. It never interrupts the reading line.
* **Time is relative and lowercase-plain** ("yesterday", "1h") — not a machine timestamp in the
  card. Absolute timestamps live in the methodology block, not the card.
* **Instrument chips carry a direction glyph**, so the chip is a claim, not a tag cloud.
* **The consequence line is deliberately clipped.** The card promises one line; if the sentence
  is longer, it truncates rather than reflowing the card. Consistent card height beats complete
  sentences at the glance tier. That is the same trade our doctrine makes with hard word budgets.

### 1.4 The KPI-strip and honest-null vocabulary

`[observed]` I did not see the logged-in KPI strip. What I did see is the product's **null
grammar**, and it is genuinely good — it is stated on the ledger's methodology block:

* Rows without a lock record are **returned with an explicit unverified flag rather than
  omitted**. Absence is a value, not a gap.
* Forecasts whose horizon has not elapsed, or whose price series is unavailable, **are not
  measured and are counted as neither hit nor miss** — the third state is named, not folded into
  either of the two.
* The measurement definition, baseline, benchmark, price source, hit definition, verification
  and exclusions are each **one labelled line**, not a paragraph.

`[observed, and this is the anti-pattern to NOT copy]` The ledger headline reads a single
hit-rate figure over a table of hundreds of rows, on a denominator of one measured forecast.
A big number with a tiny denominator caption is exactly the failure our Law 3 exists to stop
(`docs/DESIGN_DOCTRINE.md:75-81`): the number arrives without its meaning, and the meaning
(one measured case) is set smaller than the claim. **We must not reproduce that shape.** Our
equivalent rule is already law in this repo — a source that failed to read is missing evidence,
not zero alerts, and the board withholds the overall stance and score rather than publishing a
cheerful one (`templates/alerts.html.j2:270`, `:473`).

### 1.5 Empty / degraded / calm state language

`[observed]` Three specimens:

* **Route not found:** a small warning glyph, the code, a two-word plain description, the offending
  path in muted mono, and exactly one action button back to the dashboard. Four elements, no prose.
* **Gated module:** the feed panel renders its own chrome and a single button to activate access —
  the empty state is an *invitation*, and it never pretends the module is broken.
* **Auth wall:** left column states what you get in your first session as three short bullets;
  right column is the form. The wall sells the next screen rather than apologising for the gate.

`[inferred]` A calm state (nothing happening) was not observable. This is the single biggest gap
in the study, because **calm is the state our users will see most often** and it is where our
own estate is weakest.

### 1.6 Density and word budgets per region

`[observed]`, measured off the rendered surfaces:

| Region | Observed budget |
|---|---|
| Eyebrow | 2–4 words, upper case, letterspaced |
| Page headline | one sentence, 6–12 words, sentence case |
| Page deck | 2–3 lines, ~35–55 words |
| Card category eyebrow | 1–2 words |
| Card headline | ≤ 2 lines, ~10–16 words |
| Card consequence line | exactly 1 line, clipped |
| Instrument chips | ≤ 4 visible |
| Action verbs per card | exactly 4 (+4 secondary destinations) |
| Section head | ≤ 8 words |
| Methodology line | label + one sentence |

The estate-wide effect: **no region ever exceeds three lines except the reading paragraphs**, and
the reading paragraphs are confined to marketing bands, never to a working module.

### 1.7 Drill paths

`[observed]` Drilling is **lateral, not downward.** A card does not open "more detail about this
card"; it opens the same development inside a *workflow* (thesis / trades / holdings / monitor).
The secondary row adds four *destinations* rather than four more facts. There is no
breadcrumb trail because there is no hierarchy to climb back up — you are always one action from
a workflow and one back-link from the map.

`[observed]` The `/desk` surface also demonstrates a **calculator as a drill path**: five labelled
numeric inputs, three derived outputs, each output a plain label over a large figure. It answers
"what is this worth to me" without a single technical term. That is a reusable device.

### 1.8 Plain language vs technical, and how technicals are demoted

`[observed]` The split is clean and worth naming precisely:

* **On the surface:** verbs a person owns (build, find, audit, monitor), consequence sentences in
  ordinary English, relative time, direction glyphs, a single unlabelled-unit score.
* **Demoted to a disclosure block:** the estimator definition, the fitting window, the benchmark,
  the price vendor, the hit rule, the verification chain, the exclusions. All of it exists; none
  of it is on the card.
* **Never present anywhere:** internal study names, model identifiers, pipeline slugs.

The demotion device is a **labelled definition list under a "how this is measured" heading**, not
a tooltip. That is a genuine improvement over hover-only receipts: it is linkable, printable, and
survives touch devices. Our LENS hover tier (`docs/DESIGN_DOCTRINE.md:25`) should keep its
per-number receipts, but **each working page should also carry one end-of-page measurement block**
that a sceptical user can read straight through.

### 1.9 Theming and responsive

`[observed]` The product ships **one art direction: near-black ground, warm gold single accent,
cool white text, hairline separators, small-caps utility type.** No light toggle was exposed on
any observed surface. Direction is carried by glyph + hue on chips; the accent is spent almost
exclusively on the one primary action per screen.

`[inferred]` Responsive: the composition is a single-column stack of full-bleed bands with one
card grid; the feed panel is self-contained and would collapse to one column without
re-composition. The header would need a drawer. I could not measure this — see §0.2.

**Our constraint differs and must not be quietly dropped.** We are bound to two art directions,
not one (CLAUDE.md §Theme art direction; `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:587`
light-mode component contract). The reference gives us a dark command centre to learn from and
**nothing at all** for light. §2.7 therefore states our light direction from our own doctrine, and
any builder who ships this must produce both evidence sets.

---

## 2. Proposal — the Mastermind "Market OS command" dashboard

### 2.1 The one job, stated once

> **Market OS answers: what changed in the world's money system since you last looked, what we
> can and cannot see today, and which one of our workspaces is worth opening now.**

Everything below serves that sentence. Archetype: **`command_center`** (A) —
"what changed; what deserves attention now", L1 budget 5, identity device the two-column command
layout with stance rows (`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:432`). It is not a regime
dashboard (D): the fourteen workspaces are the regime dashboards; this page is the door.

Route: one new page in the existing macro family, using the existing authenticated header
(`templates/_site_nav.html.j2` family, inventory `templates/_navlinks.html.j2`). **No third header
family is created** (CLAUDE.md §Navigation source-of-truth). The page is reachable from the
United States group beside the Macro Dashboard row (`templates/_navlinks.html.j2:64`).

### 2.2 The fourteen F01 pages → modules

All fourteen exist today as macro-native suite pages built on `templates/_macro_suite_shell.html.j2`
(726 lines), merged in PRs #6836 → #6852:

| # | Template | PR | Group on the command page | Module tile label (EN / ZH) |
|---|---|---|---|---|
| 1 | `templates/macro_monetary_policy.html.j2` | #6845 | A · Money & policy | Policy setting / 政策取向 |
| 2 | `templates/macro_liquidity_central_banks.html.j2` | #6846 | A | Central-bank cash / 央行流动性 |
| 3 | `templates/macro_liquidity_regime.html.j2` | #6836 | A | Is money easy or tight / 松紧格局 |
| 4 | `templates/macro_rates_curves.html.j2` | #6851 | A | Rates and the curve / 利率与曲线 |
| 5 | `templates/macro_financial_conditions.html.j2` | #6845 | A | How easy it is to borrow / 融资环境 |
| 6 | `templates/macro_inflation_system.html.j2` | #6845 | B · Prices, jobs, activity | Prices / 物价 |
| 7 | `templates/macro_growth_real_economy.html.j2` | #6845 | B | Growth / 增长 |
| 8 | `templates/macro_labor_markets.html.j2` | #6845 | B | Jobs / 就业 |
| 9 | `templates/macro_business_activity.html.j2` | #6845 | B | What businesses are doing / 企业活动 |
| 10 | `templates/macro_consumer_payments.html.j2` | #6848 | B | What households are spending / 居民消费 |
| 11 | `templates/macro_capital_structure.html.j2` | #6847 | C · Balance sheets & flows | Who is borrowing / 融资结构 |
| 12 | `templates/macro_national_debt_liabilities.html.j2` | #6848 | C | Government debt / 政府债务 |
| 13 | `templates/macro_housing_real_estate.html.j2` | #6847 | C | Housing / 房地产 |
| 14 | `templates/macro_trade_flows.html.j2` | #6852 | C | Goods crossing borders / 跨境贸易 |

**Grouping rule (the design act):** three groups of 5 / 5 / 4, named by what a person is asking
about — money, the economy, balance sheets — never by data family or producer. A user who does
not know what "financial conditions" means still knows whether they are asking about borrowing.

**Nothing is a sub-tab of the command page.** Each of the fourteen keeps its own URL and its own
in-page tabbar (`templates/_macro_suite_shell.html.j2:221-234`, roles `tablist`/`tab`, panels at
`:666-682`). The command page owns *one* new thing only: a tile per workspace carrying **state
word + one plain line + freshness + an absence chip when the workspace could not read**. That
respects the §9 density law ("the engine may know 400 things; the page may show seven",
`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:363-365`) — fourteen tiles are one L1 section, not
fourteen sections.

### 2.3 Layout — desktop 1440

```
┌ site header (existing _site_nav family; unchanged) ──────────────────────────┐
├──────────────────────────────────────────────────────────────────────────────┤
│ MARKET OS                                              Region · US           │  chrome band
│ Where the money system stands today                    Newest reading · 06:40│  (context header,
│                                                        Page built · 07:12    │   mq-context reuse)
├───────────────────────────────────┬──────────────────────────────────────────┤
│ L1-1  THE READ                    │  L1-2  WHAT CHANGED OVERNIGHT            │
│                                   │                                          │
│   MIXED                           │  · Jobs — cooled a step        (new)     │
│   Money is still tight, but the   │  · Prices — no change                    │
│   pressure stopped building.      │  · Housing — could not be read           │
│                                   │  · Rates — steeper                       │
│   ┌────┬────┬────┬────┬────┐      │  · Trade — first read in 3 days          │
│   │KPI │KPI │KPI │KPI │KPI │      │                                          │
│   └────┴────┴────┴────┴────┘      │  Nothing else moved enough to say so.    │
├───────────────────────────────────┴──────────────────────────────────────────┤
│ L1-3  THE FOURTEEN WORKSPACES                                                │
│  Money & policy            Prices, jobs, activity      Balance sheets & flows│
│  ┌─────────┐┌─────────┐    ┌─────────┐┌─────────┐      ┌─────────┐┌─────────┐│
│  │ tile    ││ tile    │    │ tile    ││ tile    │      │ tile    ││ tile    ││
│  └─────────┘└─────────┘    └─────────┘└─────────┘      └─────────┘└─────────┘│
├──────────────────────────────────────────────────────────────────────────────┤
│ L1-4  WHAT WE'RE WATCHING NEXT   (≤3 rows: condition · window · why it matters)│
├──────────────────────────────────────────────────────────────────────────────┤
│ L1-5  WHAT WE COULD NOT SEE TODAY  (named sources, plain reason, what it costs)│
└──────────────────────────────────────────────────────────────────────────────┘
```

Five L1 sections — at the archetype-A budget, under the hard ceiling of 7. Above the fold at
1440×900: chrome + THE READ + the first row of WHAT CHANGED, satisfying the above-fold budget
(`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:359-361`).

### 2.4 The KPI strip — five tiles, every field from data we already produce

Each tile is **label (plain) / value / one-line meaning**. No tile shows a number our own doctrine
would call decoration (Tier-1 statistic test, `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:366-369`).

| Tile | Value source that already exists | EN meaning line (≤ 12 words) | Honest-null form |
|---|---|---|---|
| Today's stance | alerts board stance — risk-off / mixed / constructive / partial read (`templates/alerts.html.j2:243-246`) | "How the tape is leaning before you do anything." | "Read incomplete — we are not calling a stance today." |
| Pressure | alerts pressure score /100, with the existing withhold rule (`templates/alerts.html.j2:248`, `:270`) | "How much stress is showing across the alerts we read." | Withheld, printed as "—" with the reason, never as 0 |
| Changed overnight | count of workspaces whose accepted snapshot state moved (from the R7 nightly artifact lane, PR #6849) | "How many of the fourteen moved since yesterday." | "We could not compare — yesterday's file is missing." |
| Data we could read | required-source availability + coverage (`templates/_macro_suite_shell.html.j2:80-86`) | "How much of what we need actually arrived." | Coverage prints "—" with the named absent source |
| Newest reading | last accepted source cut, distinct from page build (`templates/_macro_suite_shell.html.j2:88-94`) | "The freshest number on this page, not when the page was made." | "No accepted reading yet today." |

Two rules I want frozen here:

1. **Page build time is never a KPI.** The suite shell already says this in user-facing words —
   build time is not an economic clock (`templates/_macro_suite_shell.html.j2:94`). The strip
   inherits that separation: *newest reading* is a tile, *page built* is a chrome footnote.
2. **The conservative-over-required rule is user-visible.** A degraded optional input cannot turn
   availability green (`templates/_macro_suite_shell.html.j2:83`). Keep that sentence — in plain
   words it is the reason a user can trust the green.

### 2.5 Region word budgets (hard limits, enforced at review — doctrine Law 4, `docs/DESIGN_DOCTRINE.md:82-89`)

| Region | Title | Body | Rows | Footnotes |
|---|---|---|---|---|
| Context band | ≤ 4 words | deck ≤ 14 words | — | 1 as-of line, once |
| L1-1 stance word | 1 word from the stance vocabulary | 1 line ≤ 16 words | — | 0 |
| KPI tile | label ≤ 3 words | meaning ≤ 12 words | — | 0 |
| L1-2 change row | subject ≤ 3 words | verdict ≤ 8 words | ≤ 5 rows + 1 closing line | 0 |
| Workspace tile | name ≤ 4 words | state word + ≤ 10 words | — | freshness chip only |
| L1-4 watch row | condition ≤ 8 words | window + why ≤ 14 words | ≤ 3 rows | 0 |
| L1-5 null row | source name (display name, never a slug) | reason ≤ 12 words + cost ≤ 12 words | ≤ 5 rows | 1 merged footnote |
| Whole page | — | — | — | **one** as-of stamp, **one** footnote |

Stance vocabulary is closed and already ratified: Act · Get ready · Watch — don't chase · Protect
gains · Stand aside · Ignore (`docs/DESIGN_DOCTRINE.md:44`). Banned on this page: every term in
the Law 2 list (`docs/DESIGN_DOCTRINE.md:50-62`) — internal state names, bare backtest statistics,
raw slugs, unexplained thresholds. **A workspace tile shows a plain state word, never the internal
state identifier the snapshot carries.**

### 2.6 Empty / degraded / calm copy patterns (EN, with ZH notes)

Our estate's existing best sentence is already on the alerts page and should become the house
pattern: a source that failed to read is missing evidence, not zero alerts
(`templates/alerts.html.j2:270`, `:473`). Four states, four shapes:

**Calm** — the most common state, and the one to get right.
> EN: **Quiet.** Nothing in the money system moved enough to change the read today.
> ZH: **平静。** 今日货币体系未出现足以改变判断的变化。
> ZH note: use 平静 for the state word; avoid 无信号 ("no signal"), which reads as a system fault
> rather than a market condition. Never translate a calm state as 暂无数据.

**Empty (nothing to show yet, system healthy)**
> EN: No workspace has published today's read yet. The first arrives after the morning cut.
> ZH: 今日尚无工作区发布读数，早盘截数后出现首条。
> Shape: one sentence + when it will change. Never a shrug, never an apology.

**Degraded (partial read)**
> EN: Three of fourteen workspaces could not be read. We are not calling a stance today —
> a missing source must never make the market look calmer than it is.
> ZH: 十四个工作区中有三个无法读取。今日不给出总体立场 —— 数据缺失绝不能让市场显得更平静。
> Shape: count + the withheld thing + the reason, in that order. The withhold is a *feature
> sentence*, not an error.

**Absent single cell** — reuse the existing shell macro rather than inventing one: an em dash plus
a short "why" span (`templates/_macro_suite_shell.html.j2:43-47`). The em dash alone is banned; it
must always carry its reason.

**Refusal (the page cannot honestly render)** — the shell already has this section
(`templates/_macro_suite_shell.html.j2:712-714`). The command page reuses it: headline, one plain
paragraph, one link to what *is* readable. Never a stack trace, never a code.

Forbidden vocabulary on all four, per CLAUDE.md §Design: no falsifier/refutation language, no
证伪, no "thesis refuted". A window that closed is a window that closed.

### 2.7 Theme art direction — both directions named

**DARK (the command centre).** Deep instrument ground; panel surfaces raised by luminance, not by
borders; hairlines used only where two data regions genuinely abut; the semantic accent spent on
the stance word and exactly one primary action; direction carried by hue *plus* a glyph so it
survives colour-blindness; charts drawn on the panel surface with the grid one step above ground.
Restrained glow is allowed on the stance word only, as the page's single signature moment.

**LIGHT (the research workspace).** Cool paper canvas, white material panels, depth carried by a
soft shadow and a hairline — **not** by an inverted glow, which reads as smear on a light ground.
The stance word keeps its weight through *type scale and ink density*, not luminance. Chart grids
invert to a warm grey that stays below the ink; positive/negative hues shift to their higher-
chroma light-mode pairs so they clear text-contrast on white, which the dark pair does not.

**Mechanisms that intentionally differ:** (a) elevation — luminance step in dark, shadow + hairline
in light; (b) the emphasis mechanism on the stance word — glow in dark, weight/size in light;
(c) chart grid polarity; (d) chip fill — translucent tint in dark, tinted-solid with a border in
light, because translucency over white loses the direction hue. Everything else — IA, component
semantics, spacing/type scale, state meanings, actions, ordering, density budgets — is identical.

This section is a *specification for a future build*, not evidence. **Any packet that implements
§2 must ship both evidence sets (dark/light × EN/ZH × 1440 / 390) or be reported PARTIAL**, per
CLAUDE.md §Theme art direction. Token substitution alone will not be accepted as a light design.

### 2.8 Bilingual note

Every label is a paired `l-en`/`l-zh` span, as the suite shell already does
(`templates/_macro_suite_shell.html.j2:33-35`, macro `t()`). Two ZH-specific risks on this page:
the stance word must stay one or two characters so the hero does not reflow, and the ZH change
rows run ~20–30% shorter than EN — so the row grid must be defined by the **longer** language, not
tuned to EN and left to float in ZH. No translated text in `title=` attributes (CI-guarded).

### 2.9 Mobile 390 — declared reduction, not a squeeze

Order: context band (collapsed to region + newest reading) → stance word + one line → KPI strip as
a **two-row 3+2 grid**, never a horizontal scroller (a scroller hides the null tiles, which is
exactly the tile you must not be able to miss) → what changed (5 rows) → the fourteen tiles as
three labelled accordions, closed by default, group header showing "n of 5 moved" → watching next
→ what we could not see. The answer lands within one swipe
(`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:360`).

---

## 3. The same pattern inside the Terminal shell (F08 / F11 / F12 — half B)

### 3.1 What the shell already gives us

`charting-app` `terminal/components/chrome/AppShell.tsx` (read from `origin/master`) is the one
shared chrome for every non-chart workspace: it renders the `.app2` grid, `MobileNav`, a topbar of
brand-or-back + divider + page title + spacer + settings, then `AppNav`, then the page's
content-only subtree. Its `TITLE_MAP` already routes `/analysis`, `/discover`, `/options`,
`/scripts`, `/alerts`, `/portfolio`, `/admin`; the chart route is deliberately outside it.

Three consequences for us:

1. **F08/F11/F12 must not grow their own headers.** The shell's comment says it outright — views
   must not reintroduce chrome. Any alerts/thesis/settings design that ships a page-level title
   bar is wrong before it is reviewed.
2. **The page title is the only identity slot.** So the *first content element* has to carry the
   answer, exactly as on the macro command page.
3. **Identity is already in context** (`useShellIdentity`), so a team-scoped surface does not need
   to re-fetch or prop-drill an owner key.

### 3.2 F08 — the alerts cockpit (`/alerts`)

Archetype **G · `monitor`**, L1 budget 4, identity device the since-you-were-here change-log
timeline (`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:438`).

```
topbar: [brand] | Alerts                                    [settings]
────────────────────────────────────────────────────────────────────────
L1-1  SINCE YOU WERE HERE          2 new · 1 resolved · 1 still open
      ├ 09:41  Rates — steeper than your threshold        [open] [mute]
      ├ 08:12  Housing — could not be read                [why?]
      └ yesterday  Jobs — back inside range               [resolved]
────────────────────────────────────────────────────────────────────────
L1-2  WHAT WE'RE WATCHING FOR YOU  (your conditions, plain sentences)
────────────────────────────────────────────────────────────────────────
L1-3  ADD A WATCH                  (one control, one line of help)
────────────────────────────────────────────────────────────────────────
L1-4  WHAT WE COULD NOT WATCH TODAY (named source · plain reason)
```

Word budgets: timeline row = time + subject ≤ 3 words + verdict ≤ 8 words + ≤ 2 actions.
Group header = one integer only (the one-integer law,
`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:370-372`). Empty state:
> EN: No alerts since you were last here. We are still watching 6 conditions for you.
> ZH: 自上次访问以来没有新警报，仍在为你监控 6 项条件。
The count is the point: an empty monitor must prove it is still working.

Copy carried over from the existing macro Alert Command Center rather than re-invented: the
missing-evidence sentence (`templates/alerts.html.j2:270`) and the four explicit source outcomes —
read fine / read fine with nothing to say / no store yet / could not be read
(`templates/alerts.html.j2:473`). Those four are the honest-null vocabulary for the whole Terminal.
**Never a trade command**: a row says what changed and what to look at; it never says buy or sell.

### 3.3 F11 — the thesis workspace

Archetype **C-company · `instrument_analyzer`** — decision header + task tabset
(`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:434`). New `TITLE_MAP` row (`/thesis`, "Thesis").

```
topbar: [brand] | Thesis                                    [settings]
────────────────────────────────────────────────────────────────────────
DECISION HEADER
  Your view:  Rates stay high into Q1        Last edited 2 days ago
  What would change it:  jobs cool two months running   [edit]
────────────────────────────────────────────────────────────────────────
[ The view ] [ Evidence ] [ What would change it ] [ History ]
────────────────────────────────────────────────────────────────────────
  active tab body — one column, measure-limited
```

The decision header is the whole design. It states the user's own claim in their own words, and —
this is the borrowed principle from §1.7 — the **change-of-mind condition sits beside the claim,
not three screens away**. Budgets: claim ≤ 12 words; condition ≤ 14 words; tab bodies unbudgeted
(Tier 3). Empty state:
> EN: No thesis yet. Start from something you already believe about the market.
> ZH: 尚未建立观点。从你已有的市场判断开始。
Degraded: if the evidence a thesis leans on cannot be read, the header keeps the claim and prints
one line under it — "one of the readings behind this is missing today" — and does not silently
render a thinner evidence tab.

### 3.4 F12 — team settings

Archetype **I · `utility`**, single card, zero ambient
(`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md:440`). It lives in the existing settings panel
surface reached from `SettingsButton` in the shell topbar, not as a new nav destination — settings
is not a workspace.

```
Team
  Who is in this team      3 of 10 seats used
  ├ name · email · role                     [change role] [remove]
  └ [ Invite someone ]
What everyone can see      one sentence, plain
Billing                    plan · next charge · [manage]
```

Budgets: section head ≤ 3 words; each row one line; one explanatory sentence per section, maximum.
Every control names its outcome (doctrine writing law): the button says "Invite someone", and the
confirmation says "Invited" — the same verb through the flow. Empty state:
> EN: It's just you. Invite someone to share watches and theses.
> ZH: 目前只有你。邀请成员共享监控与观点。
Degraded: if the seat count cannot be read, print the roster and one line — "we could not check
your seat limit just now" — and disable invite rather than guessing a number.

---

## 4. Open questions for Meta-CEO A and B

1. **Re-run §1 authenticated.** Someone with the live session must record: the rail groups and
   their labels, the top product tabs and sub-tabs, the real KPI strip fields and their null
   forms, and — most important — **the calm state** (§1.5 gap). Until then §1.2 and §1.4 are
   partly inferred and this study must not be cited as a measured reference for the rail.
2. **True 390px evidence is missing** (§0.2). Our §2.9 reduction is designed from doctrine, not
   from their behaviour. Someone should measure at a real 390 viewport before we claim parity.
3. **Which half owns the macro command page?** §2 is macro-side (`templates/`, `_site_nav` family);
   §3 is Terminal-side. If A takes §2 and B takes §3, the shared artefacts are the stance
   vocabulary, the four source outcomes, and the null copy patterns — those must be written once
   and cited, not re-drafted per repo.
4. **Does "changed overnight" have a producer?** §2.4 assumes the R7 nightly artifact lane
   (PR #6849) can answer "which of the fourteen moved since yesterday". If it cannot compare two
   accepted snapshots, that KPI tile is not buildable and must be replaced, not faked.
5. **Do we adopt a density switch?** Their compact/detailed/briefing control is the cleanest
   answer to "too much text" I observed. It is also a new component, and §11.2 discipline forbids
   inventing components casually. Recommend: adopt it for the change list and the workspace grid
   only, as a two-state (brief / full) control, and take it to the specimen.
6. **`mockups/design_system/specimen.html` is not checked out in this sparse worktree** (it is in
   the `mockups/` tree omitted by the sparse selection). Any builder implementing §2/§3 must run
   `python3 scripts/worktree_sparse.py full` first and verify against the specimen — I could not.
7. **One art direction vs two.** The reference has no light mode. We do. Whoever builds this owes
   a light-mode argument on the merits (§2.7), not a token swap — and a packet without light
   evidence is PARTIAL by standing law, never PASS.

---

*Prepared 2026-09-06. Sources: direct observation of the public marketontology.com surfaces listed
in §0.1 (no authenticated view), and this repository's own design law. No third-party text, code,
or assets were copied.*

## 1.10 Authenticated dashboard pattern — from the Chairman's own screenshot (observed by Meta-CEO B, 2026-09-06)

The designer pass above could not sign in. The Chairman supplied one screenshot of the
signed-in "Capital Command" view; the structure below is described in our own words, pattern
only — no text, code, CSS, icons or data are reproduced.

- **Shell:** a fixed left rail (~260px) with the product name at top, a small-caps group label,
  a primary group of nine single-word verbs/nouns (command, decide, analyze, a morning edition,
  policy, transactions, stocks, evaluation, macro), a second group of three inbox-like items
  (inbox, pulse, desk), then settings and sign-out pinned at the bottom. One item is highlighted
  with a warm accent bar. Every rail label is one or two plain words; no counts, no badges.
- **Top bar:** five product-family tabs (capital, team, quant, decision tools, sector
  intelligence) as plain text with a thin active underline; on the right a search field with a
  keyboard hint, a progress chip ("2/6"-style completion), a region selector, a bell, a theme
  toggle. Nothing else.
- **Page header:** a two-word page title, then an eyebrow line "NEXT MOVES · 1 MODULES" (the
  active sub-tab and how many modules are showing), a "find a feature" search, one primary
  connect action (broker link), and a module filter pill.
- **KPI strip:** nine small-caps labels each with a one- or two-word value. Absent values are
  written as honest states, not dashes only: "Pending baseline", "Weekend", "Not supplied",
  "Not reconciled", "No source stamp", "Not evaluable". The strip therefore reads as a truthful
  status board even with zero data linked — this is exactly our "nulls printed in plain words"
  law, executed as a first-class design element.
- **Sub-tabs:** seven small-caps tabs (next moves, decision OS, today, portfolio, intelligence,
  decisions, workflows) with the active one filled; each is a module group, not a page.
- **Body empty state:** a section title, a one-line coverage label with a placeholder value, a
  single "Recompute" action, and one calm paragraph (~35 words) that explains WHY nothing is
  shown (recommendations require reconciled holdings, stated objectives and dated event
  records) and WHAT would change it (link a book). No apology, no jargon, no spinner.
- **Persona chip:** a bottom-right "ANALYST" pill suggests a role/mode switch that changes
  density and vocabulary without changing the page.
- **Density:** roughly 60 words visible above the fold excluding the rail; the largest text is
  the page title; the smallest is the KPI labels. Dark canvas, near-black, one warm accent.

**Implication for Mastermind:** our command page (§2) should carry (a) a nine-field-or-fewer
status strip whose empty values are honest states written as two-word sentences, (b) module
sub-tabs instead of fourteen pages, (c) one calm explanatory empty paragraph per module with a
single action, and (d) a rail of one-word verbs. Those four moves are what make the reference
read as "not too much text" — not smaller type or fewer features.
