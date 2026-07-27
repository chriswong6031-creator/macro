# Free Estate content contract (MKT-SEO-01..04 W1)

Binding contract for the public acquisition estate: `/products/` (platform
overview and honest product explainers), `/tools/` (Calculator Lab +
spreadsheets), `/learn/` (Learning Center), `/blog/` (Blog). Every builder,
designer and reviewer in this program codes against this file. Deviations
require a contract edit in the same PR.

Canonical host: `https://www.mastermind-x.com/` (import `lib.seo.SITE_BASE`).
All pages are static, off the nightly render path; `scripts/build_free_content.py`
renders `content/seo/` + `templates/seo_*.html.j2` → committed `site/` output.
Deterministic: same inputs ⇒ identical bytes (no build timestamps).

## 1. URL map (W1 — complete list)

```
/products/index.html                             Platform overview
/products/market-terminal.html                   Browser terminal explainer
/products/mastermind-ai.html                     AI analyst explainer
/products/market-dashboards.html                 Market dashboards explainer
/tools/index.html                                Tools hub
/tools/calculators/position-size.html            (designer-built exemplar)
/tools/calculators/risk-reward.html
/tools/calculators/trade-profit.html
/tools/calculators/compounding.html
/tools/calculators/cagr.html
/tools/calculators/drawdown-recovery.html
/tools/spreadsheets/trading-journal.html         spreadsheet landing page
/assets/downloads/mastermind-trading-journal.xlsx
/learn/index.html                                Learning Center hub
/learn/technical/52-week-highs.html
/learn/technical/rsi.html
/learn/technical/macd.html
/learn/technical/vwap-anchored-vwap.html
/learn/technical/market-breadth.html
/learn/risk/position-sizing.html
/learn/risk/risk-reward-expectancy.html
/learn/ownership/insider-filings-form-4.html
/blog/index.html                                 Blog hub
/blog/the-math-of-losing-streaks.html
/blog/why-a-50-percent-loss-needs-a-100-percent-gain.html
/blog/win-rate-is-overrated.html
/blog/congress-trades-are-not-realtime-signals.html
/blog/how-to-keep-a-trading-journal.html
/blog/compound-growth-for-traders.html
/blog/feed.xml                                   RSS 2.0, article items only
/about-research.html                             Mastermind Research entity page
```

`site/learn.html` (Gamma Weather field manual) is NOT touched; the Learn hub
links to it as the flagship options lesson. No page duplicates its content.

## 2. Source layout & file ownership

```
content/seo/
  CONTRACT.md            (this file)
  products/<slug>.md     product page frontmatter + HTML-fragment body
  blog/<slug>.md         B4 owns    frontmatter + HTML-fragment body
  learn/<track>/<slug>.md B5 owns   same format
  pages/about-research.md B4 owns   rendered with the article template
  tools/trading-journal.md B2 owns  spreadsheet landing page body
  calculators.yml        B3 owns    calculator registry (hub cards + meta)
scripts/build_free_content.py   B1 owns
scripts/build_trading_journal_xlsx.py  B2 owns
lib/seo.py (discovery extension only)  B1 owns
templates/llms.txt (new section only)  B1 owns
templates/seo_base.html.j2             D1 (designer) owns
templates/seo_products_index.html.j2   product overview hub
templates/seo_product.html.j2          product explainer layout
templates/seo_tools_index.html.j2      D1
templates/seo_learn_index.html.j2      D1
templates/seo_blog_index.html.j2       D1
templates/seo_article.html.j2          D1 (articles, lessons, plain pages)
templates/seo_calculator_base.html.j2  D1
templates/calculators/position_size.html.j2   D1 (the styled exemplar)
templates/calculators/<other 5>.html.j2       B3
tests/test_free_content.py             B1
tests/test_trading_journal_xlsx.py     B2
site/** rendered output                committed at assembly by the main loop
```

Nobody runs git commands. Nobody edits files outside their ownership list.

## 3. Frontmatter contract (`.md` sources)

YAML between `---` fences, then the body as a raw **HTML fragment** (no
markdown — the `markdown` package is not in the environment).

```yaml
---
slug: position-sizing            # must match filename
family: article | lesson | page | product
title: "Position Sizing: The Only Edge You Fully Control"   # ≤60 chars, search-intent phrased
description: "…"                 # 120–155 chars, plain, no clickbait
track: risk                      # lessons only: technical | risk | ownership
cluster: risk-management         # free-text topic key, used for related grouping
published: 2026-07-20
updated: 2026-07-20
related:
  calculators: [position-size]        # slugs from calculators.yml
  lessons: [risk/risk-reward-expectancy]
  articles: [the-math-of-losing-streaks]
  live:                               # existing site pages, root-relative
    - {href: /congress_trades.html, label: "Congressional trades tracker"}
cta: {href: /tools/calculators/position-size.html, label: "Try the position size calculator"}
---
<p>…body HTML fragment…</p>
```

Every `related` target must exist in the §1 URL map or the live site. Every
`cta` target must meet the same rule or exactly match one of the builder's
allowlisted `https://app.mastermind-x.com` application destinations. Arbitrary
external CTA hosts and unreviewed application paths fail validation.

Product pages additionally require:

```yaml
product_name: "Mastermind AI"
eyebrow: "AI market analyst"
order: 2
workflow:
  - "Ask a market question"
  - "Inspect the connected evidence"
  - "Continue into the relevant workspace"
```

`order` is a unique integer from 1 through 99 across product pages. `workflow`
contains exactly three short, visible steps. Product pages may use
`related.products` with product slugs from the §1 URL map.

## 4. Body fragment vocabulary (styled by seo_base)

Allowed elements/classes — nothing else:

- `<h2>`, `<h3>` (h2 sections get auto-anchors from the builder)
- `<p>`, `<ul>`, `<ol>`, `<li>`, `<strong>`, `<em>`, `<a href>`, `<code>`
- `<table class="data">` with `<th>`/`<td>`, numeric cells `class="num"`
- `<div class="callout lead|warn|key"><span class="co-h">Heading</span>…</div>`
- `<div class="formula">…</div>` display formula (plain text/HTML, no LaTeX)
- `<div class="worked"><span class="co-h">Worked example</span>…</div>`
- `<blockquote>`, `<figure>`/`<figcaption>` with inline `<svg>` only

Internal links: **root-relative** (`/tools/calculators/cagr.html`). External
links: full https URLs, only to primary sources (SEC, exchanges, official docs).
No external images; SVG inline only. No `<script>` in content bodies.

## 5. Template context contract (builder → templates)

All templates receive:
- `rel` — asset prefix to site root (`"../"`, `"../../"`); use for theme.css etc.
- `page` — dict: `slug, family, title, description, canonical, url_path,
  published, updated, breadcrumbs` (list of `{label, href}` root-relative,
  last item = current page, no href)
- `site` — dict: `base` (SITE_BASE)

Hubs additionally: `items` (list of entry dicts with `title, description,
url_path, published, track/cluster`), learn hub: `tracks` (ordered list of
`{key, label, lessons: [...]}` + a `flagship` entry for /learn.html).
Article/lesson/page: `body_html`, `related` (resolved to `{href, title}`
lists), `cta`, `toc` (list of `{id, label}` from h2s).
Product pages receive the same fields plus `page.product_name`,
`page.eyebrow`, and `page.workflow`; `related.products` resolves to public
product explainers. The product hub receives ordered `items` from product
frontmatter.
Calculator pages are templates themselves: they extend
`seo_calculator_base.html.j2` and fill blocks `calc_form`, `calc_script`,
`article_body`, plus set `page`-level vars per the base template's header
comment. The builder supplies calculator pages `section: "tools"`, a
`related` rail (the registry's `related_lesson`, resolved to href+title,
plus the trading-journal page) and a `cta` (the related lesson) — but no
`toc` (the explainer lives in the template, not parsed content). The registry `calculators.yml` provides hub metadata:

```yaml
- slug: position-size
  title: "Position Size Calculator"
  description: "…"        # 120–155 chars
  blurb: "Shares to buy from account size, risk % and stop."  # hub card, ≤90 chars
  cluster: risk-management
  related_lesson: risk/position-sizing
```

## 6. Calculator DOM + JS contract

Every calculator page:

```html
<section class="calc-card" id="calc" aria-label="Calculator">
  <div class="calc-in">
    <label class="ci"><span class="ci-l">Account size ($)</span>
      <input id="account" inputmode="decimal" autocomplete="off"></label>
    <!-- segmented toggle when needed: -->
    <div class="ci-seg" role="radiogroup" data-name="direction">
      <button class="on" data-v="long">Long</button><button data-v="short">Short</button>
    </div>
  </div>
  <div class="calc-out" aria-live="polite">
    <div class="co-main"><span id="out-main">—</span><span class="co-unit">shares</span></div>
    <p class="co-plain" id="out-plain">Fill in the fields to see your size.</p>
    <dl class="co-rows"><div><dt>Dollar risk</dt><dd id="out-risk">—</dd></div>…</dl>
  </div>
  <div class="calc-actions"><button class="gbtn" id="copy-result">Copy result</button></div>
</section>
```

Rules (all hook into the #3159 lesson — asset optimizer defers external JS):
- ALL JS inline in the page, wrapped in `DOMContentLoaded`. No external
  scripts, no network calls, no storage, no persistence of inputs.
- Pure function `compute(inputs)` returning an outputs object; DOM wiring
  separate. A `WORKED_EXAMPLES` const holds the §7 fixtures; on load, each is
  run through `compute` and mismatches `console.error` (silent when green).
- Invalid/empty input ⇒ plain-word message in `.co-plain` (e.g. "Your stop
  equals your entry — there's no risk per share to size against."), outputs
  show `—`. Never render NaN/Infinity. Inputs accept commas ("10,000").
- `#copy-result` copies a one-line plain-English result string.
- The result always carries a plain-word interpretation sentence (`.co-plain`)
  — a number never stands alone (design doctrine Law 3).

## 7. Calculator formulas & fixtures (canonical — do not re-derive)

**position-size** — inputs: account A, riskPct r, entry E, stop S.
`risk$ = A·r/100`; `perShare = |E−S|`; `shares = floor(risk$/perShare)`;
`position$ = shares·E`; `positionPct = 100·position$/A`. Direction inferred
(S<E long, S>E short) and stated in the plain line. Warn (not block) when
positionPct > 100 ("more than your account — this needs margin").
Fixtures: (A=10000, r=1, E=50, S=48) → shares=50, position$=2500, risk$=100;
(A=25000, r=0.5, E=12.40, S=13.10) → short, shares=178, risk$=125.

**risk-reward** — inputs: entry E, stop S, target T, optional winRate w%.
`RR = |T−E|/|E−S|`; `breakevenWin% = 100/(1+RR)`; if w:
`expectancyR = (w/100)·RR − (1−w/100)`. Validate: T and S on opposite sides
of E, else plain-word warning. Fixtures: (E=100,S=95,T=115) → RR=3.0,
breakeven=25%; (E=100,S=95,T=115,w=40) → expectancyR=0.6.

**trade-profit** — inputs: direction, entry E, exit X, qty Q, fees F (total),
optional open/close dates. Long `P/L=(X−E)·Q−F`; short `P/L=(E−X)·Q−F`;
`ret% = 100·P/L/(E·Q)`; if dates and days≥1:
`annualized% = 100·((1+ret)^{365/days}−1)`, labeled "if repeated at this pace
for a year". Fixtures: (long,E=50,X=55,Q=100,F=2) → P/L=498, ret=9.96%;
(short,E=200,X=210,Q=10,F=0) → P/L=−100, ret=−5%.

**compounding** — inputs: principal P, contribution c per period, freq f
(12/4/1), annualPct r, years n. `i=r/100/f`, `m=n·f`;
`FV = P·(1+i)^m + c·((1+i)^m−1)/i` (i=0 ⇒ `P+c·m`). Outputs: FV, total
contributed `P+c·m`, growth = FV−contributed, per-year table + inline SVG
curve (drawn by the page JS into a fixed-size viewBox — no libraries).
Fixture: (P=10000,c=500,f=12,r=7,n=10) → FV≈106,639 (assert ±1;
ordinary annuity — contributions at period end; exact 106,639.02).

**cagr** — inputs: begin V0, end V1, years n (or two dates → n=days/365.25).
`CAGR% = 100·((V1/V0)^{1/n}−1)`. V0≤0 or V1≤0 ⇒ error message; n<1 ⇒ result
plus warning "under a year — annualizing exaggerates short-term results".
Inverse mode (segmented toggle): V0, CAGR, n → `V1 = V0·(1+g)^n`.
Fixtures: (10000→19672, n=10) → 7.0% (±0.05); inverse (10000, 7%, 10) → 19,672.

**drawdown-recovery** — inputs: drawdown d% (or peak/current values), optional
assumed annual return g%. `requiredGain% = 100·d/(100−d)`; if g:
`years = ln(100/(100−d)) / ln(1+g/100)`. Static reference table in the article
body: d ∈ {5,10,15,20,25,30,40,50,60,70,80,90}. Fixtures: d=50 → +100%;
d=20 → +25%; (d=50,g=10) → 7.27 years (±0.05).

## 8. Copy laws (all prose, hard requirements)

- Educational voice. Never personalized advice; never "you should buy/sell X";
  the standing footer disclaimer (template-provided, once) is:
  "Educational content — not investment advice. Markets involve risk."
- The word "validated" is banned in user-facing text (CI-enforced repo-wide).
  Also banned: "guaranteed", "foolproof", "can't lose", hype adjectives.
- No invented statistics. Every number is either pure math (derivable from
  the formulas above), clearly hypothetical ("suppose a trader risks 1%…"),
  or cited to a named primary source with a link. No "studies show".
- Structure per page: one-sentence direct answer first; then depth; a
  "common trap" section; a "where this breaks / limits" section; internal
  links per the relation map; ONE exact continuation CTA.
- Product explainers replace the educational "common trap" requirement with
  a visible "What it does" workflow, but still require a candid limitations
  section, differentiated search intent, real internal destinations, and one
  continuation CTA. No persona or keyword page may ship without unique utility.
- Lessons additionally: a one-line learning objective at top and a 3-question
  self-check (details/summary) at the bottom.
- EN body copy for `.md` content; the template chrome carries the bilingual
  EN/ZH UI (W1 language ruling: no /zh/ URLs, no translated long-form `.md`
  bodies — chrome parity only, per D12A R3). Ratified exception (review
  2026-07-20): calculator-page explainer copy lives in templates and MAY
  carry full EN/ZH dual-DOM text via `t()` — calculators are product-tool
  surfaces on the same-URL dual-DOM house pattern, not a translated
  long-form estate.
- Inspiration workflow: TrendSpider Learning Center / blog articles may be
  read for topic selection and angle-mining ONLY. Output must be original
  prose, original structure, original examples — better and more honest than
  the source. Never copy sentences, tables, or example values.

## 9. SEO wiring (builder-implemented)

- `_seo_head`-equivalent meta emitted by `seo_base` for subdir depth: exactly
  one `<link rel=canonical>` (www host), description, OG/Twitter, favicons
  with `rel` prefix.
- JSON-LD: BreadcrumbList on every page; Article (headline, description,
  datePublished, dateModified, author = Organization "MastermindX Research",
  publisher = Organization "MastermindX", mainEntityOfPage) on blog/lesson
  pages only; WebPage with a
  visible SoftwareApplication main entity on product leaves. No ratings,
  reviews, offers, Course, or FAQ markup. Markup describes visible content only.
- Sitemap: extend `lib/seo.py` discovery to include `site/blog/`, `site/learn/`
  (one level of track subdirs), `site/tools/` (+ `calculators/`,
  `spreadsheets/`), and `site/products/` — hubs weekly 0.7, leaves monthly
  0.6. Single-file sitemap stays (D12A R2); `feed.xml`/non-HTML never listed.
- RSS 2.0 at `/blog/feed.xml`: canonical URLs, title, description, pubDate
  from frontmatter. Deterministic (no build-time timestamps).
- `templates/llms.txt`: add a "## Free tools & learning" section listing the
  three hubs + journal download.
