# Macro Command — FROZEN design spec (F01, 2026-09-06)

One page: `site/macro_monetary.html` becomes **Macro Command**, the single customer interface for the
fourteen-workspace Macro & Monetary suite. Builders implement this file verbatim; it is not a sketch.

**Status:** FROZEN by ROUTE design after adjudication of two competing drafts (GUIDED-READING won 39/50;
the COMMAND draft's superior sections are grafted here by name). Every judge defect is fixed and logged in §11.

**Files this spec relies on** (cited by path; all suite files read on
`origin/claude/marketontology-f01-product-experience-hub-r1-20260905`, PR #6873):
`templates/_macro_suite_shell.html.j2`, `templates/_macro_suite_nav.html.j2`, `templates/macro_monetary.html.j2`,
`templates/macro_suite.css`, `lib/macro_suite_view.py`, `lib/macro_suite_labels.py`,
`scripts/build_macro_suite_pages.py`, `templates/mm_brain.js`, `templates/theme.js`, `templates/_navlinks.html.j2`,
`templates/_site_nav.html.j2` (global header — UNTOUCHED), `templates/theme.css` (token root),
`docs/DESIGN_DOCTRINE.md`, `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`, `mockups/design_system/specimen.html`.

## §0.0 BASE — this spec is pinned to an unmerged branch (red-team F1/F3/F6, applied)

**BASE:** this spec is written and cited against PR #6873
(`origin/claude/marketontology-f01-product-experience-hub-r1-20260905`), head **`bcddcca07186`**. It is buildable
**only** on that branch, or on `origin/main` after PR #6873 is squash-merged. Measured on `origin/main` @
`77e882864e4` (2026-09-06): `templates/macro_monetary.html.j2` and `site/macro_monetary.html` do not exist (only
the unrelated `macro_monetary_policy` workspace does), and `lib/macro_suite_view.py` exposes `build_view` /
`degraded_view`, never `build_hub_view` — `grep -rn "build_hub_view" lib/ scripts/ templates/` on main returns zero
hits. **No packet may build against a branch citation.** P1 does not open until #6873 is squash-merged onto
`origin/main`; if a builder is ready to start P1 and #6873 has not merged, the builder STOPS and escalates.

Every `file:line` citation in this spec (§3, §4, §5, §6.3) is **binding by string, advisory by line**: the string
and the file are the contract; the line number is a pointer that may have moved. P1's first act is to re-resolve
every citation against the merged `origin/main` and edit the corrected line numbers into this file before P2
opens — see gates **G15** and **G16** below.

---

## §0 Acceptance gates — "not done unless"

G0. **Ten-second test.** A reader who has never seen a yield curve opens `macro_monetary.html` and, without
scrolling and without hovering, reads one plain-word sentence saying what macro is saying today, plus the date it
is true as of. No slug, no internal state id, no untranslated stat name, no bare timestamp is on screen above the
fold in either theme or either language.

G1. **Two-minute test.** From that sentence the reader reaches any one of the twelve sections in one click (or one
keystroke), and the first three things in that section are: a stance line in plain words, a "New to this?"
30-second explainer, and one visual with a plain-word caption saying which direction is good and which is bad.
Technicals are reachable in exactly one more click and never before.

G2. **No machine text outside Details.** For every string in §5's left column: zero occurrences in the rendered
page outside a `<details class="mc-details">` subtree or a `class="mc-primer"` body. Enforced by
`scripts/check_macro_command_copy.py` + `tests/test_macro_command_copy_law.py`, which ship in **P1** and are green
in **every** packet (§9).

G2b. **No bare timestamp anywhere in the reading path.** *(Grafted from the COMMAND draft §0 G2 / §3 chip law.)*
No visible text may contain a `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` shape without an immediately preceding plain word.
Every as-of is prefixed in the visible text — **"Data to 3 Sep 2026" / "数据截至 2026年9月3日"** — while the machine
value lives only in `datetime=`. The copy guard carries the regex
`(?<![A-Za-z一-鿿][  ])\d{4}-\d{2}-\d{2}` for the visible-text extraction.

G3. **No fused composite.** The page publishes no page-level score, rank, grade or blended regime. Every chip and
every clause of The Read is a verbatim pass-through of ONE workspace's own reviewed label
(`DNR:KILL-FUSED-COMPOSITE`, `DNR:KILL-REGIME-SCORECARD`; the constraint is published in
`templates/macro_monetary.html.j2:8-14`). Sidebar order is a fixed reading order that never changes with the data.

G4. **Honest nulls.** No bare em dash is the only content of any cell, chip or panel. Every `—` is emitted by the
`nulled()` macro (§2.7) and therefore always carries an `.mq-sr` sentence. Every empty panel states what is
missing, why, what unlocks it, and when it refreshes — plain words, EN and ZH.

G5. **Two art directions.** Dark and light are judged as separate designs. `mc-panel`, `mc-chip`, `mc-stance`,
The Read's emphasis and the chart plot ground each use a DIFFERENT material mechanism per theme (§2.6).
"The tokens swap and it still renders" is an automatic FAIL.

G6. **Bilingual parity.** Every user-visible string is a `.l-en`/`.l-zh` pair; no ZH text in any `title=`
attribute; ZH line lengths do not break the 390 layout (checked in the §10 evidence matrix).

G7. **No third header.** `templates/_site_nav.html.j2` is byte-unchanged. The left rail is a page-level section nav
inside `<main>`, never a header. `templates/_macro_suite_nav.html.j2`'s suite bar stays the third *level* on the 14
deep-link pages, unchanged.

G8. **Payload budget met and measured.** The Overview panel renders with zero fragment requests. The three byte
ceilings in §6.1 are **provisional until P1 measures the current pages** and re-ratifies them in this file (§6.1,
P1 acceptance). No packet after P1 may cite an unmeasured ceiling.

G9. **No runtime style injection.** Zero `style.textContent`, zero style-element creation, zero palette literals in
`templates/macro_command.js`. All material decisions live in `templates/macro_command.css`.
`scripts/check_runtime_style_injection.py` green.

G10. **Tokens extend, never parallel.** Every `--mc-*` token is defined in one `:root` block in
`templates/macro_command.css` and its value is either a `var(--…)` reference to `templates/theme.css` /
`templates/macro_suite.css` or a geometry/duration literal. Zero raw hex in component rules. Tone **ink** is
inherited from `macro_suite.css` (`.mq-tone-*`, lines 88-91) and is never re-minted (§2.6, D5).

G11. **Evidence posted.** The §10 matrix — 20 frames (red-team F16 adds frame 17b) — is in the PR body of the final packet, and the
theme-relevant subset in each earlier packet. A packet whose light art direction has no crop is `PARTIAL`, never
`PASS`.

G12. **No horizontal page scroll.** *(Grafted from COMMAND §0 G12.)* `document.body` never scrolls horizontally at
1440, 768 and 390, in **both** languages and **both** themes. Wide content (workspace tables, wide figures)
scrolls inside its own `overflow-x:auto` container. Checked in every packet, not only at 390.

G13. **Deep links survive.** All 14 `macro_<slug>.html` URLs still return 200 and still carry the suite bar; each
gains one link into `macro_monetary.html#<section>` (keep + link, never redirect).

G14. **The stance line is a published reversal and is recorded.** *(Judge D10.)* `templates/macro_monetary.html.j2:168`
currently publishes that the hub "never tells you what to do". §4's stance line deliberately says what to do
(including "watch — don't chase"). The packet that ships the stance line (P3) MUST land
`agentos/decisions/DEC-MACRO-COMMAND-STANCE-IS-GUIDANCE.md` in the same PR: question, answer, rationale,
alternatives rejected, evidence, reversibility — and must keep the no-score / no-rank / no-fusion half of that
published sentence intact (§5 row 62). Shipping the stance line without that record is a blocker.

G15. **Citations are binding by string, advisory by line, until P1 re-resolves them.** *(Red-team F1.)* P1 MUST
re-resolve every §5 row against the merged `origin/main` shell and re-write the `file:line` column in this spec
before P2 opens; rows are cited by (string, file) and the line column is advisory. If PR #6873 has not merged when
P1 opens, P1 STOPS and escalates — no packet may build against a branch citation.

G16. **The data contract is gated on #6873's merge.** *(Red-team F3.)* This spec's data contract assumes PR #6873
is MERGED to `origin/main`. P1's first acceptance item is `git log origin/main --oneline -1 -- lib/macro_suite_view.py`
showing the #6873 squash, and a `grep -n 'def build_hub_view' lib/macro_suite_view.py` receipt. If absent, every
packet HOLDS.

---

## §1 Information architecture

### §1.1 Sidebar sections ↔ the 14 workspace slugs

Twelve sections cover fourteen workspaces. Section order is a fixed **reading order** — what a customer asks
first, then outward — and is a constant in the builder, never derived from data (G3). Three sections carry
sub-tabs.

**Section id = a bare token. The `#` is added by the template** (`href="#{{ s.id }}"`, `id="{{ s.id }}"`), never
stored in the value.

| # | Section id (bare token) | EN label | ZH label | workspace_id(s) → page | Sub-tabs |
|---|---|---|---|---|---|
| 0 | `overview` | Overview | 总览 | *(hub view itself)* | — |
| 1 | `money` | Money & liquidity | 资金与流动性 | **`liquidity_regime`** → `macro_liquidity_regime.html` (PRIMARY); `liquidity_central_banks` → `macro_liquidity_central_banks.html` | "How much money is around" 市场资金 / "What central banks are holding" 央行资产负债表 |
| 2 | `policy` | Policy rates | 政策利率 | `monetary_policy` → `macro_monetary_policy.html` | — |
| 3 | `rates` | Rates & the curve | 利率与收益率曲线 | `rates_curves` → `macro_rates_curves.html` | — |
| 4 | `inflation` | Inflation | 通胀 | `inflation_system` → `macro_inflation_system.html` | — |
| 5 | `growth` | Growth | 经济增长 | **`growth_real_economy`** → `macro_growth_real_economy.html` (PRIMARY); `business_activity` → `macro_business_activity.html` | "The whole economy" 整体经济 / "What companies are doing" 企业活动 |
| 6 | `jobs` | Jobs | 就业 | `labor_markets` → `macro_labor_markets.html` | — |
| 7 | `housing` | Housing | 房地产 | `housing_real_estate` → `macro_housing_real_estate.html` | — |
| 8 | `consumer` | Consumers | 消费者 | `consumer_payments` → `macro_consumer_payments.html` | — |
| 9 | `credit` | Borrowing costs | 融资环境 | **`financial_conditions`** → `macro_financial_conditions.html` (PRIMARY); `capital_structure` → `macro_capital_structure.html` | "How hard it is to borrow" 融资难易 / "How companies fund themselves" 企业融资结构 |
| 10 | `debt` | Government debt | 政府债务 | `national_debt_liabilities` → `macro_national_debt_liabilities.html` | — |
| 11 | `trade` | Trade | 贸易往来 | `trade_flows` → `macro_trade_flows.html` | — |

Slug list and page outputs verified in the fourteen `SuitePage` entries in `SUITE_PAGES`
(`scripts/build_macro_suite_pages.py:73-237`; same fix as red-team F7 — a "lines 76-226" range silently drops
`trade_flows`) (`workspace_id=` registry order: liquidity_regime, growth_real_economy, business_activity,
labor_markets, inflation_system, monetary_policy, financial_conditions, liquidity_central_banks, capital_structure,
housing_real_estate, consumer_payments, national_debt_liabilities, rates_curves, trade_flows).

**Why the reading order differs from the registry order.** The registry order is a producer law governing the hub's
*change list* and the suite bar (`templates/_macro_suite_nav.html.j2` header comment;
`templates/macro_monetary.html.j2:132` "Listed in the research suite's own fixed order…"). It is not a customer's
question order. The sidebar is a fixed constant (`SECTIONS` in `scripts/build_macro_suite_pages.py`), so it can
never re-sort with the data — the property `DNR:KILL-REGIME-SCORECARD` actually protects. The hub's
registry-ordered change list survives unchanged inside `overview`.

### §1.2 Route archetype

`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` §10 assigns an archetype per route. Macro Command binds to the
console/dashboard archetype defined there; P1 copies that archetype's exact name from §10 into the page's DS header
comment and obeys its density budget from §9 of that document. No new archetype is minted.

### §1.3 What guided reading changes about IA

A first-time subscriber does not know that "financial conditions" and "capital structure" are different questions.
So the section is named for the *question* ("Borrowing costs"), and the two workspaces become sub-tabs named for
the *answer* ("How hard it is to borrow" / "How companies fund themselves"). The workspace's own title still
appears — once, inside Details, as the deep link.

---

## §2 Page anatomy — art direction, exact markup, exact CSS

### §2.1 The design idea

The reference pattern for this product category is a KPI grid: eight tiles of numbers with coloured deltas. For a
customer who has never seen a yield curve, a KPI grid is a wall — it presents eight facts and teaches none of them.
This page inverts that: **the top of the page is a sentence, not a grid.**

**The signature: "The Read."** The command header renders one plain-word line — *"Money is ample and easing, policy
is on hold, rates are drifting lower, inflation is cooling slowly, growth is steady, jobs are still tight, and
borrowing is a little easier."* — set at display size, in the reading ink, with each **topic word** carrying the
semantic tone of the workspace it came from and acting as a jump link to that section. Below it the same seven
states also appear as a compact chip rail for the reader who already knows the vocabulary and wants to scan. The
sentence teaches; the rail serves the returning user. **The rail is never the primary reading.**

The Read is **not a judgment.** Each clause is a verbatim pass-through of one workspace's own reviewed state label
(§3), joined by fixed connectives. Nothing is fused, scored or ranked (G3).

Everything else on the page is deliberately quiet, because the boldness is spent here. One accessory removed:
there is no page-level sparkline row, no hero chart, and no animated counter.

### §2.2 Panel grammar (guided reading)

Every panel is a short card story in a fixed order — the order is the teaching device, so it never varies:

1. **Stance** — one line: what it says and what to do, including "watch — don't chase". ≤ 20 EN words / 34 ZH chars.
2. **Primer** — `<details class="mc-primer">`, summary "New to this? 30 seconds" / "第一次看？30 秒读懂". Two
   sentences, no numbers, no jargon. Built `open` for the first three sections only; not persisted, no storage.
3. **Visual** — the workspace's own dominant visual, restyled by the frame, not re-authored.
4. **Read-the-visual caption** — one line naming direction: *"Higher on this line means money is easier to get."*
5. **What we're watching** — 2–3 bullets, each a CONDITION, never a verdict, never falsifier vocabulary
   (`docs/DESIGN_DOCTRINE.md`; falsifier language is never front-facing).
6. **Details** — `<details class="mc-details">` holding everything the current shell puts in the reading path:
   clocks, coverage, method version, definition ids, owner refs, hashes, the evidence drawer, and the deep link.

### §2.3 Layout at 1440

```
┌ _site_nav.html.j2 (UNTOUCHED) ──────────────────────────────────────────────┐
├─────────────────────────────────────────────────────────────────────────────┤
│  RAIL 232px  │  CONTENT  max 1008px                            │  gutter    │
│  Overview    │  eyebrow: Macro & Monetary · Data to 3 Sep 2026              │
│  Money       │  H1 Macro Command                                            │
│  Policy      │  ── THE READ ────────────────────────────────────────────    │
│  Rates       │  Money is ample and easing, policy is on hold, rates are     │
│  Inflation   │  drifting lower, inflation is cooling slowly…                │
│  Growth      │  [chip][chip][chip][chip][chip][chip][chip][chip]            │
│  Jobs        │  ── PANEL: Overview ─────────────────────────────────────    │
│  Housing     │  stance / primer / visual / caption / watching / details     │
│  Consumers   │                                                              │
│  Borrowing   │                                                              │
│  Gov. debt   │                                                              │
│  Trade       │                                                              │
│  ───────     │                                                              │
│  [Ask the    │                                                              │
│   analyst]   │                                                              │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

At 768 the rail collapses to a horizontal chip rail pinned under the site nav; at 390 the rail scrolls
horizontally, The Read wraps and drops to `--fs-h2`, and the chip strip becomes a two-column grid.

### §2.4 DARK TREATMENT — command center

Ground is the deepest surface; nothing floats. Panels sit a **luminance step** above the page ground with a 1px
inner top highlight — the lit edge of an instrument bezel — and no side borders: depth comes from light, not from
lines. The Read sits directly on the page ground with **no card at all**, so it reads as something the product is
saying rather than a widget. Emphasis inside The Read is *tinted text plus a 12%-alpha radial wash behind the
word* — restrained glow, one per topic word, no bloom, painted on the element itself so it cannot fall behind the
canvas. The rail's active item is a luminance step plus a 2px left bar in the link ink. Charts plot on a plot
ground one step **darker** than the panel, gridlines at 8% ink, series strokes at full luminance: on dark, the
stroke is the brightest thing in the frame. **Shadows are not used in dark at all** — a shadow on a dark ground is
mud.

### §2.5 LIGHT TREATMENT — research workspace

Ground is a **cool paper canvas** (a desk, not a screen). Panels are **white material** with a hairline border and
a short, low downward shadow: separation comes from edge and elevation, because a luminance step on paper is
invisible. There is **no glow anywhere in light.** Emphasis inside The Read is *ink text plus a 2px semantic
underline rule* — a highlighter-style tint fill would read as marker scrawl on paper and cheapen the sentence, and
the tinted-text-plus-halo that reads as "lit" on black reads as "faded" on white. The rail's active item is a white
card with a hairline and the same 2px left bar. Charts plot on **white** — the plot ground does not step down,
because a grey plot well on paper reads as a disabled control; gridlines are 1px hairlines at 10% ink and the
series stroke is the **darkest** thing in the frame. Figure/ground is deliberately inverted between the themes.

### §2.6 Mechanisms that intentionally differ (and why)

| Element | Dark mechanism | Light mechanism | Why they cannot be the same |
|---|---|---|---|
| Panel separation | luminance step + 1px inner top highlight, no shadow | white fill + hairline border + `0 1px 2px` shadow | A luminance step is invisible on paper; a shadow on near-black is a smudge. |
| Read emphasis | tinted word + 12% radial wash painted on the word | ink word + 2px semantic underline | Halo needs a dark ground to read as light; an underline needs a light ground to read as a rule, not a scar. |
| Stance ribbon | 3px semantic left bar on the panel ground, `0%` wash | 3px left bar + `6%` semantic wash | A wash on dark pushes the text below the contrast floor; a bare bar on paper under-reads. |
| Chart plot ground | one step darker than the panel | identical to the panel (white) | Dark needs the well to make the stroke read as the brightest object; light needs no well or the chart reads disabled. |
| Chip | 1px border at 18% ink, transparent fill | 1px border at 14% ink, `--panel` fill | Filled chips on dark become buttons; unfilled chips on paper vanish into the canvas. |
| Focus ring | 2px link-ink ring, 2px offset | same ring plus a 1px white inner ring | On white material the ring needs a gap or it merges with the panel hairline. |

**Tone ink is inherited, never re-minted** *(judge D5).* `templates/macro_suite.css:88-91` already defines
`.mq-tone-ok / .mq-tone-warn / .mq-tone-bad / .mq-tone-neutral` using the **text-safe** inks (`--ink-ok`,
`--ink-warn`, `--ink-act`). This page uses those classes verbatim. It must NOT copy the FILL tokens
(`--mq-ok` / `--mq-bad`, `macro_suite.css:16-18`) into text colour: that is a contrast risk on the light canvas
and would put two diverging tone families on one page.

**Shared and non-negotiable across both themes:** information architecture, section order, component semantics,
spacing and type scales, state meanings, user actions, data contracts, ordering/density law, interaction
behaviour, and every string.

---

### §2.7 EXACT markup skeleton

Two Jinja helpers are assumed and must exist before P1 ships: `t(en, zh)` and `bl(pair)` render the existing
`.l-en` / `.l-zh` bilingual mechanism (no ZH ever in a `title=`), and **`nulled(reason_en, reason_zh)`** is the
single reusable null macro — *grafted from the COMMAND draft §2.2* — so that no site in the page hand-writes a
dash:

```jinja
{# templates/_macro_command_macros.html.j2 #}
{% macro nulled(en, zh) -%}
<span class="mq-dash" aria-hidden="true">—</span><span class="mq-sr">{{ t(en, zh) }}</span>
{%- endmacro %}
```

Every `—` on this page is emitted by `nulled()`. P1's test scans the **built** page for a `—` with no sibling
`.mq-sr` and fails the build (§9 P1).

```html
{# templates/macro_monetary.html.j2 — body of the Macro Command page #}
{% import "_macro_command_macros.html.j2" as m %}
<body class="mq-page mc-page">
{% include "_site_nav.html.j2" %}   {# UNTOUCHED — the only global header (G7) #}

<main class="mc-shell" id="mc-shell">

  <a class="mc-skip" href="#mc-content">{{ t("Skip to today's read", '跳到今日读数') }}</a>

  <nav class="mc-rail" id="mc-rail" aria-labelledby="mc-rail-label">
    <p class="mc-rail-label" id="mc-rail-label">{{ t('Sections', '板块') }}</p>
    <ul class="mc-rail-list">
      {%- for s in sections %}
      <li class="mc-rail-item">
        <a class="mc-rail-link{{ ' is-current' if s.first else '' }}"
           href="#{{ s.id }}" data-mc-section="{{ s.id }}"
           {%- if s.first %} aria-current="page"{% endif %}>
          <span class="mc-rail-bar" aria-hidden="true"></span>
          <span class="mc-rail-text">{{ bl(s.label) }}</span>
          {%- if s.tone %}<span class="mc-rail-dot mq-tone-{{ s.tone }}" aria-hidden="true"></span>{% endif %}
        </a>
      </li>
      {%- endfor %}
    </ul>

    {# ANALYST — mount the sitewide widget; the bare link is the degraded fallback only (§8) #}
    {%- if analyst.mountable %}
    <button type="button" class="mc-analyst" data-mc-analyst
            data-mc-analyst-label-en="Macro Command" data-mc-analyst-label-zh="宏观指挥台">
      <span class="mc-analyst-mark" aria-hidden="true">◈</span>
      <span class="mc-analyst-text">{{ t('Ask the analyst', '向分析师提问') }}</span>
    </button>
    {%- else %}
    <a class="mc-analyst" href="chat.html">
      <span class="mc-analyst-mark" aria-hidden="true">◈</span>
      <span class="mc-analyst-text">{{ t('Ask the analyst', '向分析师提问') }}</span>
    </a>
    {%- endif %}
  </nav>

  <div class="mc-content" id="mc-content">

    <header class="mc-command">
      <p class="mc-eyebrow">
        <span class="mc-eyebrow-suite">{{ t('Macro &amp; Monetary', '宏观与货币') }}</span>
        <span class="mc-eyebrow-sep" aria-hidden="true">·</span>
        {%- if read.as_of %}
        <span class="mc-eyebrow-asof">
          {# G2b: the plain word is INSIDE the visible text; the machine value is only in datetime= #}
          <span class="mc-asof-word">{{ t('Data to', '数据截至') }}</span>
          <time datetime="{{ read.as_of }}">{{ bl(read.as_of_display) }}</time>
        </span>
        {%- else %}
        <span class="mc-eyebrow-asof mc-absent">{{ t('No dated reading yet', '暂无带日期的读数') }}</span>
        {%- endif %}
      </p>
      <h1 class="mc-title">{{ t('Macro Command', '宏观指挥台') }}</h1>

      {# THE READ — one sentence, deterministic, single-workspace pass-through only (G3) #}
      {%- if read.clauses|length >= 3 %}
      <p class="mc-read" data-mc-read>
        {%- for clause in read.clauses %}
        <span class="mc-read-clause">
          <a class="mc-read-topic mq-tone-{{ clause.tone }}" href="#{{ clause.section }}">{{ bl(clause.topic) }}</a>
          <span class="mc-read-state">{{ bl(clause.predicate) }}</span>{{ clause.punct }}
        </span>
        {%- endfor %}
      </p>
      {%- if read.omitted %}
      <p class="mc-read-omitted">{{ t('Some readings are not available today — see the states below.',
                                       '部分读数今日不可用 — 见下方状态条。') }}</p>
      {%- endif %}
      {%- else %}
      <p class="mc-read-fallback">{{ t("Today's reading is incomplete. Here is what we do have.",
                                       '今日读数不完整。以下是我们已有的部分。') }}</p>
      {%- endif %}

      <ul class="mc-strip" data-mc-strip>
        {%- for chip in strip %}
        <li class="mc-chip mq-tone-{{ chip.tone }}{{ ' is-null' if chip.null else '' }}">
          <a class="mc-chip-link" href="#{{ chip.section }}" aria-describedby="{{ chip.id }}-help">
            <span class="mc-chip-label">{{ bl(chip.label) }}</span>
            <strong class="mc-chip-value">
              {%- if chip.null %}{{ t('Not available yet', '暂不可用') }}
              {%- else %}{{ bl(chip.value) }}{% endif -%}
            </strong>
            <span class="mc-chip-asof">
              {%- if chip.as_of %}
              <span class="mc-asof-word">{{ t('Data to', '数据截至') }}</span>
              <time datetime="{{ chip.as_of }}">{{ bl(chip.as_of_display) }}</time>
              {%- else %}{{ m.nulled('no dated reading for this topic', '该主题没有带日期的读数') }}{% endif -%}
              {%- if chip.freshness_note %}
              <span class="mc-chip-fresh">· {{ bl(chip.freshness_note) }}</span>
              {%- endif %}
            </span>
          </a>
          {# D13: always in the accessibility tree via aria-describedby, visually revealed on hover/focus #}
          <span class="mc-chip-help" id="{{ chip.id }}-help" role="note">{{ bl(chip.meaning) }}</span>
        </li>
        {%- endfor %}
      </ul>
    </header>

    {%- for s in sections %}
    <section class="mc-panel" id="{{ s.id }}" data-mc-panel="{{ s.id }}"
             aria-labelledby="{{ s.id }}-h" tabindex="-1">
      <div class="mc-panel-head">
        <h2 class="mc-panel-title" id="{{ s.id }}-h">{{ bl(s.label) }}</h2>
        <p class="mc-panel-question">{{ bl(s.question) }}</p>
      </div>

      <p class="mc-stance mq-tone-{{ s.stance.tone }}">
        <span class="mc-stance-bar" aria-hidden="true"></span>
        <span class="mq-sr">{{ t('What this means for you', '这对你意味着什么') }}: </span>
        <span class="mc-stance-text">{{ bl(s.stance.text) }}</span>
      </p>

      <details class="mc-primer"{{ ' open' if s.primer_open else '' }}>
        <summary>{{ t('New to this? 30 seconds', '第一次看？30 秒读懂') }}</summary>
        <div class="mc-primer-body">{{ bl(s.primer) }}</div>
      </details>

      {%- if s.subtabs %}
      <div class="mc-subtabs" role="tablist" aria-label="{{ s.subtab_group_en }}">
        {%- for tab in s.subtabs %}
        <button type="button" class="mc-subtab" role="tab" id="{{ tab.id }}-t"
                data-mc-subtab="{{ tab.id }}" aria-controls="{{ tab.id }}"
                aria-selected="{{ 'true' if tab.first else 'false' }}"
                tabindex="{{ '0' if tab.first else '-1' }}">{{ bl(tab.label) }}</button>
        {%- endfor %}
      </div>
      {%- endif %}

      <div class="mc-figure" data-mc-figure>
        {%- if s.first %}{{ s.figure_html }}
        {%- else %}
        {# D8: the DEFAULT (no-JS) content is an honest null with a real destination.
           The pending line is hidden in the document and unhidden by JS at boot. #}
        <p class="mc-figure-pending" hidden data-mc-pending>{{ t('Loading this section…', '正在载入本板块…') }}</p>
        <p class="mc-figure-offer" data-mc-offer>
          <a class="mc-deep" href="{{ s.deep_href }}">{{ t('The full chart for this section lives on its workspace page →',
                                                           '本板块的完整图表位于其工作区页面 →') }}</a>
        </p>
        {%- endif %}
      </div>
      <p class="mc-caption">{{ bl(s.caption) }}</p>

      <div class="mc-watch">
        <h3 class="mc-watch-title">{{ t("What we're watching", '我们在观察什么') }}</h3>
        <ul class="mc-watch-list">
          {%- for w in s.watching %}<li>{{ bl(w) }}</li>{% endfor %}
        </ul>
      </div>

      <details class="mc-details">
        <summary>{{ t('Details, methods and sources', '细节、方法与来源') }}</summary>
        <div class="mc-details-body">{{ s.details_html }}</div>
      </details>
    </section>
    {%- endfor %}
  </div>
</main>
<script src="macro_command.js" defer></script>
</body>
```

Notes the builder must not "clean up":
- `.mc-chip-help` is a `role="note"` span bound by `aria-describedby`, never a `title=` attribute — house law
  forbids translated text in `title=` (G6), and D13 requires the sentence to be announced even while visually hidden.
- No panel carries `hidden` in the served document. JS adds `hidden` to the non-current panels at boot (§6.2), so a
  no-JS reader gets one long, correctly ordered page.
- `s.first` is the only place SSR figure HTML is inlined; the other eleven figures arrive as fragments (§6).

### §2.8 EXACT CSS — `templates/macro_command.css`

Head load order: `theme.css` → `macro_suite.css` → `macro_command.css`. Dark is the `:root` default and light is
`html[data-theme="light"]`, matching `templates/theme.css` and `templates/macro_suite.css` (`:root` at line 8,
`html[data-theme="light"]` at line 23). The `--mq-*` family declared in `macro_suite.css` lines 9-28 is REUSED;
`--mc-*` is minted only for geometry and for the two mechanisms that have no existing token. **No `.mq-tone-*`
class is redefined here** (G10, D5).

```css
/* macro_command.css — Macro Command. Extends theme.css and macro_suite.css.
   No palette literal below this token block. Two art directions, one system. */

:root {
  /* geometry (theme-invariant) */
  --mc-rail-w: 232px;
  --mc-content-max: 1008px;
  --mc-gap: 28px;
  --mc-panel-pad: 24px;
  --mc-radius: var(--mq-radius);
  --mc-radius-sm: 10px;
  --mc-read-size: clamp(23px, 1.05rem + 1vw, 34px);
  --mc-read-lh: 1.42;
  --mc-dur: 160ms;

  /* DARK art direction: light, not lines */
  --mc-panel-bg: var(--mq-surface);
  --mc-panel-border: 1px solid transparent;
  --mc-panel-shadow: inset 0 1px 0 color-mix(in srgb, #fff 6%, transparent);
  --mc-plot-bg: color-mix(in srgb, var(--mq-ink) 6%, transparent);
  --mc-grid: color-mix(in srgb, var(--mq-ink) 8%, transparent);
  --mc-chip-bg: transparent;
  --mc-chip-border: color-mix(in srgb, var(--mq-ink) 18%, transparent);
  --mc-rail-active-bg: color-mix(in srgb, var(--mq-ink) 7%, transparent);
  --mc-rail-active-shadow: none;
  --mc-stance-wash: 0%;     /* D3: a PERCENTAGE, never `transparent` — see the note below */
  --mc-halo: 0.12;          /* radial wash behind a Read topic word — dark only */
  --mc-underline: 0px;      /* Read underline rule — light only */
  --mc-focus-inner: 0 0 0 0 transparent;
}

html[data-theme="light"] {
  /* LIGHT art direction: edge and elevation, never glow */
  --mc-panel-bg: var(--panel);
  --mc-panel-border: 1px solid var(--mq-line);
  --mc-panel-shadow: 0 1px 2px color-mix(in srgb, #1c2430 10%, transparent),
                     0 8px 24px -18px color-mix(in srgb, #1c2430 22%, transparent);
  --mc-plot-bg: var(--panel);
  --mc-grid: color-mix(in srgb, var(--mq-ink) 10%, transparent);
  --mc-chip-bg: var(--panel);
  --mc-chip-border: color-mix(in srgb, var(--mq-ink) 14%, transparent);
  --mc-rail-active-bg: var(--panel);
  --mc-rail-active-shadow: 0 1px 2px color-mix(in srgb, #1c2430 9%, transparent);
  --mc-stance-wash: 6%;
  --mc-halo: 0;
  --mc-underline: 2px;
  --mc-focus-inner: 0 0 0 1px var(--panel);
}

/* ── shell ───────────────────────────────────────────────────────────────── */
.mc-shell {
  display: grid;
  grid-template-columns: var(--mc-rail-w) minmax(0, 1fr);
  gap: var(--mc-gap);
  max-width: 1360px;
  margin: 0 auto;
  padding: 28px 32px 96px;
  align-items: start;
}
.mc-content { max-width: var(--mc-content-max); min-width: 0; }
.mc-skip { position: absolute; left: -9999px; }
.mc-skip:focus { position: static; display: inline-block; margin: 8px 0; }

/* ── left rail ───────────────────────────────────────────────────────────── */
.mc-rail { position: sticky; top: 84px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.mc-rail-label {
  margin: 0 0 8px 10px; font-size: var(--fs-micro, 11px);
  letter-spacing: .12em; text-transform: uppercase; color: var(--mq-muted);
}
.mc-rail-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.mc-rail-link {
  position: relative; display: flex; align-items: center; gap: 10px;
  padding: 9px 12px 9px 14px; border-radius: var(--mc-radius-sm);
  color: var(--mq-muted); text-decoration: none; font-size: 13.5px; line-height: 1.3;
  transition: background var(--mc-dur) ease, color var(--mc-dur) ease;
}
.mc-rail-link:hover { color: var(--mq-ink); background: color-mix(in srgb, var(--mq-ink) 5%, transparent); }
.mc-rail-link.is-current {
  color: var(--mq-ink); font-weight: 600;
  background: var(--mc-rail-active-bg);
  border: var(--mc-panel-border);
  box-shadow: var(--mc-rail-active-shadow);
}
.mc-rail-bar {
  position: absolute; left: 0; top: 8px; bottom: 8px; width: 2px; border-radius: 2px; background: transparent;
}
.mc-rail-link.is-current .mc-rail-bar { background: var(--mq-accent); }
.mc-rail-dot { width: 6px; height: 6px; border-radius: 50%; margin-left: auto; background: currentColor; }

.mc-analyst {
  font: inherit; font-size: 13px; text-align: left; cursor: pointer;
  margin-top: 18px; display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-radius: var(--mc-radius-sm);
  border: 1px solid var(--mq-line-strong); color: var(--mq-ink);
  text-decoration: none; background: var(--mc-chip-bg);
}
.mc-analyst:hover { border-color: var(--mq-accent); color: var(--mq-accent); }

/* ── command header + THE READ ───────────────────────────────────────────── */
.mc-eyebrow {
  margin: 0 0 6px; font-size: var(--fs-micro, 11px);
  letter-spacing: .08em; color: var(--mq-muted);
}
.mc-eyebrow time { font-family: var(--font-mono); }
.mc-asof-word { letter-spacing: 0; }
.mc-title {
  margin: 0 0 18px; font-size: var(--fs-h2, 22px); font-weight: 600;
  letter-spacing: -.01em; color: var(--mq-ink);
}
.mc-read {
  margin: 0 0 22px; max-width: 62ch;
  font-size: var(--mc-read-size); line-height: var(--mc-read-lh);
  font-weight: 450; letter-spacing: -.012em; color: var(--mq-ink);
  text-wrap: pretty;
}
.mc-read-clause { white-space: normal; }
.mc-read-topic {
  color: inherit; text-decoration: none; font-weight: 600;
  padding: 0 .08em 1px;
  border-bottom: var(--mc-underline) solid currentColor;
  /* D4: the halo is painted ON the element. A z-index:-1 pseudo would paint behind the page canvas. */
  background-image: radial-gradient(closest-side,
    color-mix(in srgb, currentColor calc(var(--mc-halo) * 100%), transparent), transparent);
  background-size: 100% 160%;
  background-position: center;
  background-repeat: no-repeat;
}
.mc-read-state { color: var(--mq-ink); }
.mc-read-omitted, .mc-read-fallback {
  margin: 0 0 22px; font-size: var(--fs-sm, 13px); line-height: 1.5; color: var(--mq-muted); max-width: 62ch;
}
.mc-read-fallback { font-size: 16px; color: var(--mq-ink); }

/* ── state strip ─────────────────────────────────────────────────────────── */
.mc-strip {
  list-style: none; margin: 0 0 32px; padding: 0;
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px;
}
.mc-chip {
  position: relative; border: 1px solid var(--mc-chip-border);
  background: var(--mc-chip-bg); border-radius: var(--mc-radius-sm);
  padding: 10px 12px; min-width: 0;
}
.mc-chip-link { display: grid; gap: 2px; text-decoration: none; color: inherit; }
.mc-chip-label { font-size: var(--fs-micro, 11px); letter-spacing: .06em; text-transform: uppercase; color: var(--mq-muted); }
.mc-chip-value { font-size: 14px; font-weight: 600; color: var(--mq-ink); overflow-wrap: anywhere; }
.mc-chip-asof { font-size: 10.5px; color: var(--mq-muted); }
.mc-chip-asof time { font-family: var(--font-mono); }
/* freshness is a plain word in muted ink — it never colours the chip (§3.4) */
.mc-chip-fresh { color: var(--mq-muted); font-style: normal; }
.mc-chip.is-null .mc-chip-value { color: var(--mq-muted); font-weight: 500; }
.mc-chip-help {
  position: absolute; left: 0; top: calc(100% + 6px); z-index: 5;
  width: max(220px, 100%); padding: 8px 10px; border-radius: 8px;
  border: var(--mc-panel-border); background: var(--mc-panel-bg);
  box-shadow: var(--mc-panel-shadow);
  font-size: 12px; line-height: 1.45; color: var(--mq-muted);
  opacity: 0; visibility: hidden; transition: opacity var(--mc-dur) ease;
}
.mc-chip:hover .mc-chip-help,
.mc-chip:focus-within .mc-chip-help { opacity: 1; visibility: visible; }

/* ── panel ───────────────────────────────────────────────────────────────── */
.mc-panel {
  background: var(--mc-panel-bg);
  border: var(--mc-panel-border);
  border-radius: var(--mc-radius);
  box-shadow: var(--mc-panel-shadow);
  padding: var(--mc-panel-pad);
  margin: 0 0 20px;
  scroll-margin-top: 88px;
  min-width: 0;
}
.mc-panel:focus-visible { outline: 2px solid var(--mq-accent); outline-offset: 3px; }
.mc-panel-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mc-panel-title { margin: 0; font-size: var(--fs-h3, 18px); font-weight: 600; color: var(--mq-ink); }
.mc-panel-question { margin: 0; font-size: var(--fs-sm, 13px); color: var(--mq-muted); }

.mc-stance {
  position: relative; margin: 0 0 14px; padding: 12px 14px 12px 18px;
  border-radius: var(--mc-radius-sm);
  background: color-mix(in srgb, currentColor var(--mc-stance-wash), transparent);
  font-size: 15px; line-height: 1.5;
}
.mc-stance-bar { position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px; border-radius: 3px; background: currentColor; }
.mc-stance-text { color: var(--mq-ink); }

.mc-primer { margin: 0 0 16px; }
.mc-primer > summary {
  cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 6px;
  font-size: 12.5px; color: var(--mq-accent);
  border-bottom: 1px dotted currentColor; padding-bottom: 1px;
}
.mc-primer > summary::-webkit-details-marker { display: none; }
.mc-primer-body { margin-top: 10px; max-width: 58ch; font-size: 14px; line-height: 1.6; color: var(--mq-muted); }

.mc-subtabs { display: flex; gap: 6px; margin: 0 0 14px; flex-wrap: wrap; }
.mc-subtab {
  font: inherit; font-size: 12.5px; cursor: pointer;
  padding: 6px 12px; border-radius: 999px;
  border: 1px solid var(--mc-chip-border); background: var(--mc-chip-bg); color: var(--mq-muted);
}
.mc-subtab[aria-selected="true"] { color: var(--mq-ink); border-color: var(--mq-accent); font-weight: 600; }

.mc-figure { background: var(--mc-plot-bg); border-radius: var(--mc-radius-sm); padding: 14px; overflow-x: auto; }
.mc-figure table { width: 100%; }
.mc-figure .mq-grid line,
.mc-figure svg .mc-gridline { stroke: var(--mc-grid); stroke-width: 1; }
.mc-figure-pending { margin: 0; color: var(--mq-muted); font-size: 13px; }
.mc-figure-offer { margin: 0; font-size: 13.5px; line-height: 1.5; }
.mc-figure-offer a { color: var(--mq-accent); }
.mc-caption { margin: 10px 0 18px; font-size: 13px; line-height: 1.55; color: var(--mq-muted); max-width: 62ch; }

.mc-watch { margin: 0 0 14px; }
.mc-watch-title { margin: 0 0 6px; font-size: var(--fs-micro, 11px); letter-spacing: .1em; text-transform: uppercase; color: var(--mq-muted); }
.mc-watch-list { margin: 0; padding-left: 18px; display: grid; gap: 5px; font-size: 14px; line-height: 1.5; color: var(--mq-ink); max-width: 62ch; }

.mc-details > summary { cursor: pointer; font-size: 12.5px; color: var(--mq-muted); }
.mc-details[open] > summary { color: var(--mq-ink); margin-bottom: 10px; }
.mc-details-body { border-top: 1px solid var(--mq-line); padding-top: 12px; overflow-x: auto; }

/* honest empty state */
.mc-empty { display: grid; gap: 8px; padding: 22px; border: 1px dashed var(--mq-line-strong); border-radius: var(--mc-radius-sm); }
.mc-empty-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--mq-ink); }
.mc-empty-why, .mc-empty-unlock, .mc-empty-next { margin: 0; font-size: 13.5px; line-height: 1.55; color: var(--mq-muted); max-width: 58ch; }
.mc-empty-cta { justify-self: start; margin-top: 4px; }

/* focus floor — light needs the inner ring against white material */
.mc-shell :focus-visible { outline: 2px solid var(--mq-accent); outline-offset: 2px; box-shadow: var(--mc-focus-inner); }

/* ── responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 1439px) {
  .mc-shell { max-width: 1120px; padding: 24px 24px 80px; --mc-rail-w: 208px; }
}
@media (max-width: 1023px) {
  .mc-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .mc-shell { grid-template-columns: minmax(0, 1fr); gap: 18px; padding: 18px 18px 72px; }
  .mc-rail {
    position: sticky; top: 60px; z-index: 4;
    flex-direction: row; align-items: center; gap: 8px;
    margin: 0 -18px; padding: 8px 18px;
    background: var(--bg); border-bottom: 1px solid var(--mq-line);
  }
  .mc-rail-label { display: none; }
  .mc-rail-list { flex-direction: row; overflow-x: auto; scrollbar-width: none; gap: 6px; }
  .mc-rail-list::-webkit-scrollbar { display: none; }
  .mc-rail-link { white-space: nowrap; padding: 7px 12px; border-radius: 999px; }
  .mc-rail-bar { display: none; }
  .mc-rail-link.is-current { border: 1px solid var(--mq-accent); }
  .mc-analyst { position: fixed; right: 16px; bottom: 16px; margin: 0; z-index: 6;
    background: var(--mc-panel-bg); box-shadow: var(--mc-panel-shadow); }
}
@media (max-width: 480px) {
  .mc-read { font-size: var(--fs-h2, 21px); line-height: 1.4; }
  .mc-title { font-size: var(--fs-h3, 18px); }
  .mc-panel { padding: 16px; border-radius: 12px; }
  .mc-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .mc-chip-help { position: static; opacity: 1; visibility: visible; margin-top: 6px; width: auto;
    border: 0; box-shadow: none; padding: 0; background: none; }
  .mc-figure { padding: 8px; margin: 0 -8px; }
}
html[data-lang="zh"] .mc-read { letter-spacing: 0; line-height: 1.55; font-size: calc(var(--mc-read-size) * .92); }
@media (prefers-reduced-motion: reduce) { .mc-rail-link, .mc-chip-help { transition: none; } }
```

Notes the builder must not "clean up":
- `--mc-stance-wash` is a **percentage in both themes** (`0%` dark, `6%` light). Writing `transparent` there makes
  `color-mix(in srgb, currentColor transparent, transparent)` invalid at computed-value time, which drops the whole
  declaration — a defined custom property always substitutes, so the `, 0%` fallback would never fire (D3).
- The Read's halo is a `background-image` on the anchor itself, not a `z-index:-1` pseudo-element (D4).
- `--mc-halo` / `--mc-underline` are the two theme-differing mechanisms expressed as tokens so one rule carries both
  art directions with no duplicated light/dark branch in JS (G9).
- `.mc-figure`, `.mc-details-body` and `.mc-content` keep `overflow-x:auto` / `min-width:0` at every width: the
  workspace tables are wide and the page body must never scroll horizontally (G12).

---

## §3 State strip contract

### §3.0 Chip law (binding on every chip)

1. **The value is a WORD, for chips 1-7.** *(Grafted from COMMAND §3 chip law bullet 1; red-team F11 applied.)* A
   chip value for chips 1-7 is never a number, never a state id, never a slug, never a percentage. Numbers live
   inside the panel. A producer-authored `state_label` that contains a digit is a build failure, not a rendering
   problem — P2's test asserts `re.search(r"\d", value)` is None for chips 1-7. **Chip 8 is the declared
   exception**: it is the instrument chip (§3.2), its value is a counted phrase, and P2's test asserts chip 8's
   value matches exactly `^\d+ of \d+ sections have today's data$` / `^\d+ 个板块中有 \d+ 个已更新今日数据$` and
   nothing else.
2. **Every as-of is prefixed** with a plain word in the visible text ("Data to" / "数据截至"); the machine value
   lives only in `datetime=` (G2b).
3. **One chip = one workspace.** No chip is computed from two workspaces (G3).
4. **A chip always explains itself.** `chip.meaning` renders whether the chip is null or not, and is bound to the
   chip link with `aria-describedby` so it is announced, not merely hoverable (D13).

### §3.1 The forbidden chip

The brief's example list opens with a "Regime" chip. **That chip may not be built.** A page-level regime value is a
fusion of the fourteen workspaces, which `templates/macro_monetary.html.j2:8-14` closes by name
(`DNR:KILL-FUSED-COMPOSITE`, `DNR:KILL-REGIME-SCORECARD`). Calling such a chip "composed, never scored" does not
clear it. Every chip below is a verbatim pass-through of ONE named workspace's own reviewed label, and the chip's
label says in plain words which workspace it came from, so the reader is never shown a state whose owner is unnamed.

### §3.2 The eight chips

| # | Chip label EN / ZH | Source workspace | Value + date (`lib/macro_suite_view.py`) | **Tone source** | Freshness marker | Jumps to |
|---|---|---|---|---|---|---|
| 1 | Money on the market / 市场资金 | `liquidity_regime` | `view.headline.state_label` (:290) + `view.headline.effective_date` (:295) | `STATE_TONE[view.headline.state_id]` (:289) | `L.label("freshness", state)` as a plain word | `money` |
| 2 | Central banks / 央行 | `monetary_policy` | same | same | same | `policy` |
| 3 | Rates / 利率 | `rates_curves` | same | same | same | `rates` |
| 4 | Inflation / 通胀 | `inflation_system` | same | same | same | `inflation` |
| 5 | The whole economy / 整体经济 | `growth_real_economy` | same | same | same | `growth` |
| 6 | Jobs / 就业 | `labor_markets` | same | same | same | `jobs` |
| 7 | How hard it is to borrow / 融资难易 | `financial_conditions` | same | same | same | `credit` |
| 8 | Data coverage / 数据覆盖 | hub | `view.coverage.sections_available` / `view.coverage.sections_total` — **NEW** integer fields emitted by `build_hub_view`, counted over the TWELVE rail sections defined in §1.1 (never over the fourteen workspaces; the denominator is the rail, not the `SUITE_PAGES` registry) — rendered as the counted phrase "11 of 12 sections have today's data" (§3.0 rule 1's chip-8 exception), plus the hub as-of (`templates/macro_monetary.html.j2` context block). `fmt_ratio_pct` output is display-only and is never parsed to derive this count (red-team F9). | `ok` when coverage is complete, else `warn` — this chip **is** an instrument chip and says so in its label | n/a | `overview` |

**Tone is a market tone, never a freshness tone (D1 — blocker fix).** The obvious wiring —
`view.context.state_tone` at `lib/macro_suite_view.py:136`, which is `L.tone("freshness", state)` — maps
`SOURCE_FAILED` → `bad` and `STALE_SOURCE` → `warn` (`lib/macro_suite_labels.py:51-60`). Painting a chip whose
*value* is a market state ("Ample", "Cooling") red because a data feed failed renders an instrument verdict as a
market verdict, which CLAUDE.md forbids by name. So:

- P2 adds a NEW reviewed `STATE_TONE: dict[str, str]` beside `FRESHNESS_TONE` in `lib/macro_suite_labels.py`,
  keyed on `state_id`, and chips 1-7 take their tone from it and from nothing else.
- Freshness moves to a separate, **non-colour** marker on the chip's as-of line (`.mc-chip-fresh`, muted ink, plain
  word: "not updated today" / "今日未更新"). It never sets a tone class.
- Chip 8 is the one chip whose subject *is* the instrument, and its label says so.

**Where `state_label` actually comes from (D7 fix).** `state_label` is **not** reviewed vocabulary from
`lib/macro_suite_labels.py`. `lib/macro_suite_view.py:290` builds it as `_bilingual(headline.get("state_label"))` —
it is producer snapshot text, already bilingual but not drawn from the labels module. Only the freshness, presence,
direction and unit vocabularies come from `labels.py`. Everything in §3.3 that needs reviewed copy is therefore
keyed on `state_id` (`lib/macro_suite_view.py:289`), never on the label string.

### §3.3 The Read Line contract

The Read is chips 1-7 rendered as prose. It needs each state to work as a **predicate**, which a producer-authored
noun phrase does not guarantee. Contract:

1. P2 adds one reviewed vocabulary to `lib/macro_suite_labels.py` — `PREDICATE_FORM: dict[state_id, {"en","zh"}]` —
   beside `FRESHNESS`, **keyed on `view.headline.state_id`** (`lib/macro_suite_view.py:289`), never on
   `state_label`. That module's docstring already declares it is *the* one place reviewed `{"en","zh"}` pairs live,
   so this extends the existing system rather than paralleling it.
2. `build_hub_view` emits `read.clauses` — one clause per chip that has BOTH a `state_id` and a `PREDICATE_FORM`
   entry, in chip order, carrying `topic` (our plain noun), `predicate`, `tone` (from `STATE_TONE`), `section`, and
   `punct` (`", "`, `", and "` before the last, `"."` on the last).
3. **An UNKNOWN `state_id` is treated as null for The Read** *(red-team F4 — supersedes the earlier "fails the
   build" language, which put a producer-controlled hard-fail on the nightly render path)*: the clause is omitted,
   `read.omitted` is set, the chip renders its own producer `state_label` with tone `neutral`, and the unknown
   token is appended to `unknown_tokens()`. **The BUILD does not raise; the page is still written.** Instead,
   `tests/test_macro_command_read.py` asserts `unknown_tokens()` is empty for the shipped artifact and CI fails on
   a non-empty result, and the nightly emits `::warning title=macro-command-unknown-state::<token>` (bare print,
   line-start, `flush=True`) per the standing GitHub-annotation law. A state that is genuinely null — no `state_id`
   at all — is handled identically: it is omitted, sets `read.omitted`, and renders the honest line already in
   §2.7's skeleton.
4. If fewer than three clauses survive, The Read is not rendered; the header falls back to `.mc-read-fallback`
   plus the strip: *"Today's reading is incomplete. Here is what we do have."* / "今日读数不完整。以下是我们已有的部分。"
5. `unknown_tokens()` (already in `lib/macro_suite_labels.py`) is asserted empty for the shipped hub artifact, so a
   contract extension can never leak a raw token into the sentence.

### §3.4 Null rules for a chip

- Null value → `is-null`; the value reads **"Not available yet" / "暂不可用"** — never `—`, never `0`, never blank.
- Null as-of → `m.nulled('no dated reading for this topic', '该主题没有带日期的读数')` (G4).
- The chip's note (`.mc-chip-help`, `role="note"` + `aria-describedby`, never `title=`) always renders. In the null
  case it reads: *"We show this once {workspace} publishes a dated reading. It refreshes with the nightly update."*
- **Tone for a null is `neutral`, never `bad`.** A missing input is not a market verdict.
- **A freshness state never sets a chip's tone.** `SOURCE_FAILED` renders the chip null-neutral with the E2 reason
  (§7), never red.

---

## §4 Panel contract

| Slot | Source | Rule |
|---|---|---|
| `s.label`, `s.question` | **NEW** reviewed copy `SECTION_COPY[section_id] = {"label": {en,zh}, "question": {en,zh}}` in `lib/macro_suite_labels.py`; `scripts/build_macro_suite_pages.py` gains only a NEW `SECTIONS` tuple of section ids + their workspace ids (ordering and wiring, zero prose). No customer-visible string is authored in a build script (red-team F8). | Plain nouns; the question is the customer's question — "Is money getting easier or harder to come by?" |
| `s.stance.text` | `view.implications.entries[0].text` (`lib/macro_suite_view.py:196`), rewritten under §5 to ≤ 20 EN words | Deterministic snapshot text, never a model. If `view.implications.absent` (:198) → the stance reads the reviewed `absence_text` (:199) recast in plain words, tone `neutral`. Never falsifier vocabulary. "Watch — don't chase" is a valid stance. Ships only with the G14 decision record. |
| `s.stance.tone` | `STATE_TONE[view.headline.state_id]` | Colour only, and market-tone only (§3.2). |
| `s.primer` | NEW reviewed copy `PRIMERS[section_id]` in `lib/macro_suite_labels.py` | Two sentences. No numbers, no stat names, no acronyms. Written for a reader who has never seen a yield curve. |
| `s.figure_html` | the workspace's existing dominant visual as rendered by `templates/_macro_suite_shell.html.j2` (headline band, regime map, change table, component metrics) | Restyled by `.mc-figure`; markup reused, never re-authored. |
| `s.caption` | NEW reviewed copy `CAPTIONS[section_id]` | One line naming direction: "Higher on this line means money is easier to get." Mandatory — a visual with no caption fails G1. |
| `s.watching` | `view.diagnostics` constraints + `view.headline.nearest_boundary` | 2-3 bullets, each a CONDITION ("if the gap between the two lines closes, the read changes"), never a verdict, never falsifier vocabulary, never 证伪. |
| `s.details_html` | everything else the shell renders: the context clocks, method receipts, lineage, evidence drawer, plus the deep link | Lives only inside `<details class="mc-details">`. |
| `s.deep_href` | `macro_<slug>.html` per the fourteen `SuitePage` entries in `SUITE_PAGES` (`scripts/build_macro_suite_pages.py:73-237`); the builder enumerates `SUITE_PAGES`, never a line range (red-team F7 — a "lines 76-226" range silently dropped `trade_flows`) | Rendered inside Details AND as the default no-JS figure offer (§2.7). |
| **Section with two workspaces** *(red-team F13 — closes a G3 exposure)* | The PRIMARY workspace is named in the §1.1 table (bolded) | `s.stance` and `s.stance.tone` come from the PRIMARY only, and the stance line's subject names it in plain words ("Money on the market:"). The SECOND workspace's stance renders inside its own sub-tab, never merged. A section never composes a stance from two workspaces (G3). |

Word budgets (hard, per `docs/DESIGN_DOCTRINE.md`): stance ≤ 20 EN words / 34 ZH chars; caption ≤ 18 EN words;
each watching bullet ≤ 16 EN words; primer ≤ 45 EN words total. Enforced in `tests/test_macro_command_panels.py`.

---

## §5 Copy law — machine text in the current suite → plain replacements

**The binding identity of every row is (string, file) — never the line number** (red-team F1; see §0.0 BASE, G15).
Citations were taken on `origin/claude/marketontology-f01-product-experience-hub-r1-20260905` (PR #6873), head
`bcddcca07186`; the `file:line` shown is advisory only. Rows 1-55 and 60-61 cite `templates/_macro_suite_shell.html.j2`
(the 948-line PR-branch shell — **not** the 726-line `origin/main` shell); rows 56-59 and 62 cite
`templates/macro_monetary.html.j2`. "→ Details" means the string is **moved** inside `<details class="mc-details">`
where a professional reader still gets it verbatim. Nothing is deleted. P1 re-resolves every row's line number
against the merged `origin/main` shell and edits the corrected numbers into this table before P2 opens (G15).

| # | Current string (cited) | Plain EN | Plain ZH | Placement |
|---|---|---|---|---|
| 1 | "Required-source availability" — `:83`, `:175` | Data we need today | 今天需要的数据 | Panel head chip |
| 2 | "Conservative over the required set — a degraded optional leg cannot turn this green." — `:85`, `:177` | *(removed from reading path)* | — | → Details |
| 3 | "Last accepted source cut" — `:89`, `:181` | Data goes up to | 数据截至 | → Details |
| 4 | "Calculation as-of" — `:91`, `:183` | Worked out on | 计算日期 | → Details |
| 5 | "Page built" — `:93`, `:185`, `:921` | Page refreshed | 页面更新于 | → Details |
| 6 | "Page build time is not an economic clock and never makes a source fresh…" — `:96`, `:188` | Updated once a night — not live. | 每晚更新一次 — 非实时。 | Panel foot, one line |
| 7 | "Required components and their source clocks" — `:107` | Where these numbers come from | 这些数字的来源 | → Details summary |
| 8 | "Component" (table head) — `:110`, `:641` | Input | 输入项 | → Details |
| 9 | "Presence" — `:111` | Do we have it? | 是否具备 | → Details |
| 10 | "Freshness" — `:112`, `:560` | How current | 是否最新 | → Details |
| 11 | "Source as-of" — `:113` | Data up to | 数据截至 | → Details |
| 12 | "Owner cadence, daily republish" — `:76`, `:190` | Updates when the source updates | 数据源更新时同步更新 | Chip note |
| 13 | "Latest accepted print" — `:77`, `:191` | Latest reading | 最新读数 | Chip note |
| 14 | "Effective" — `:146` | Data to | 数据截至 | Eyebrow |
| 15 | "Dates, coverage and source clocks" — `:171` | Dates and data coverage | 日期与数据覆盖 | → Details summary |
| 16 | "comparable" (denominator) — `:219` | we can compare | 可对比 | Panel foot |
| 17 | "What this state implies" — `:260` | What this means for you | 这对你意味着什么 | Stance heading (`.mq-sr`; the stance line itself carries it) |
| 18 | "Deterministic text from the accepted snapshot. No language model writes here." — `:261` | *(removed from reading path)* | — | → Details |
| 19 | "Confidence basis" — `:277` | How sure we are | 把握程度 | → Details |
| 20 | "Contradictions" — `:284` | Signals that disagree | 相互矛盾的信号 | Watching bullet |
| 21 | "Trace" + `<code>{{ item.trace_ref }}</code>` — `:287` | *(raw ref)* | — | → Details |
| 22 | "Method version" + `<code>` — `:317` | *(raw ref)* | — | → Details |
| 23 | "Prior accepted print" — `:318` | Last reading | 上次读数 | Panel body |
| 24 | "1-month vector" — `:334` | Where it moved this month | 本月的变化方向 | Caption |
| 25 | "Movement since the prior accepted print" — `:337` | Change since the last reading | 相对上次读数的变化 | Caption |
| 26 | "No vector is drawn: there is no method-comparable prior print to move from." — `:340` | We can't show the move yet — there is nothing comparable to measure it against. | 暂时无法显示变化 — 没有可对比的历史读数。 | Empty state E3 |
| 27 | "Nearest boundary" / "Score points to" — `:345`, `:347` | How close to a different reading | 距离另一种读数还有多远 | Caption |
| 28 | "Regime map" — `:371` | Where today sits | 今天落在哪里 | Figure title |
| 29 | "Two disclosed descriptive axes. The grid is a description of the current reading, not a forecast." — `:372` | This describes today. It is not a forecast. | 这是对今天的描述，不是预测。 | Caption |
| 30 | "Hysteresis band" / "Applied against the prior print" — `:433`, `:434` | How far it must move before we call it a change | 变化需超过多少才算改变 | → Details |
| 31 | "Not applied: no comparable prior print" — `:434` | No comparable earlier reading | 没有可对比的历史读数 | → Details |
| 32 | "Diagnostics" / "Constraints, missing components, source issues and method warnings." — `:448`, `:449` | Data problems | 数据问题 | → Details |
| 33 | "Current accepted snapshot against the prior accepted snapshot, under the same method version." — `:468` | Today against last time, measured the same way. | 以相同方法将今天与上次对比。 | Caption |
| 34 | "No numeric comparison is shown. A change table would have to invent a baseline that does not exist…" — `:498` | Nothing to compare against yet. | 暂无可对比的基准。 | Empty state E3 |
| 35 | "Component metrics" — `:508` | The numbers behind this | 背后的数字 | → Details summary |
| 36 | "Each cell carries its own unit, basis, direction and clocks — frequencies differ inside one band." — `:509` | *(removed from reading path)* | — | → Details |
| 37 | "Basis" / "Definition" + `<code>{{ metric.definition_id }}</code>` — `:526`, `:527` | *(raw ids)* | — | → Details |
| 38 | "Clocks and owner" / "Owner" `<code>{{ metric.owner_ref }}</code>` — `:530`, `:532` | *(raw refs)* | — | → Details |
| 39 | "Authority ceiling" — `:533`, `:637`, `:732`, `:738` | *(internal governance term)* | — | → Details |
| 40 | "Component histories" / "Owner projections with per-series clocks, units, basis and revision behaviour." — `:545`, `:546` | History | 历史走势 | Figure title |
| 41 | "This snapshot publishes no chart-ready history. An empty chart frame would read as a flat line at zero…" — `:551` | No chart yet — we don't have enough history for this one. | 暂无图表 — 该项历史数据不足。 | Empty state E1 |
| 42 | "Drivers" / "Signed push toward each axis high side. A driver is a disclosed contribution, not a cause." — `:582`, `:583` | What's pushing it | 推动因素 | Figure title (second sentence → Details) |
| 43 | "Push" (table head) — `:596` | Pushing toward | 推向 | → Details |
| 44 | "Axis method receipts" / "A composite may only be shown when its full composition law is disclosed." — `:622`, `:623` | How this is calculated | 计算方法 | → Details summary |
| 45 | "Weights law" / "Transformation" / "Frequency alignment" / "Revision behaviour" — `:630`–`:633` | *(method internals)* | — | → Details |
| 46 | "Standardized" / "Contribution" (table heads) — `:643`, `:645` | *(method internals)* | — | → Details |
| 47 | "Correction and method lineage" / "Predecessor generation" / "Changed fingerprints" — `:670`, `:674`, `:676` | *(build internals)* | — | → Details |
| 48 | "Declared but not offered" / "A tab that cannot do its job is a dead destination." — `:689`, `:690` | Not open yet | 尚未开放 | Empty state E4 title |
| 49 | "Source receipt" / "Evidence" — `:722`, `:723` | Sources | 数据来源 | → Details summary |
| 50 | "Artifact" `<code>{{ source.artifact_ref }}</code>` / "Transform" — `:753`, `:758` | *(raw refs)* | — | → Details |
| 51 | "Non-economic clocks" — `:766` | When the page was built | 页面生成时间 | → Details |
| 52 | "Publication receipt" / "Artifact path" / "Manifest path" / "Content hash" / "Bytes" / "Generation id" / "Producer" / "Producer code version" / "Client contract" — `:778`–`:787` | *(build receipts)* | — | → Details |
| 53 | "The page validated this artifact against the closed schema and recomputed its content hash before rendering…" — `:789` | *(removed from reading path)* | — | → Details |
| 54 | "Typed reason" — `:931` | Why | 原因 | Empty state |
| 55 | "Technical detail for whoever repairs this" — `:938` | Technical detail | 技术细节 | → Details |
| 56 | "That is every method-comparable change in this build." — `templates/macro_monetary.html.j2:95` | That's everything that changed today. | 这就是今天的全部变化。 | Overview panel |
| 57 | "Listed in the research suite's own fixed order…" — `macro_monetary.html.j2:132` | In the order the research suite publishes them — the order never changes with the data. | 按研究套件自身的固定顺序排列 — 顺序不随数据变化。 | Overview panel foot |
| 58 | "no state published" — `macro_monetary.html.j2:145` | No reading published yet | 尚未发布读数 | Empty state E1 (inline) |
| 59 | "Page built" (hub composition footer) — `macro_monetary.html.j2:169` | Page refreshed | 页面更新于 | → Details |
| 60 | "Macro & Monetary" as the only kicker — `_macro_suite_shell.html.j2:71`, `:140`, `:911` | keep as eyebrow, add the prefixed as-of beside it | 宏观与货币 | Eyebrow |
| 61 | Raw closed-vocabulary tokens named in `lib/macro_suite_labels.py` — `CURRENT`, `WARMUP`, `higher_tighter`, `USD_bn` | must never reach screen; `unknown_tokens()` asserted empty | 同左 | CI test |
| 62 | The composition footer — `macro_monetary.html.j2:168`: "This page composes what each workspace owner published. It produces no score and no ordering of its own, **and it never tells you what to do.**" | **This page shows what each workspace published. It produces no score and no ranking of its own.** *(The "never tells you what to do" clause is deliberately dropped — §4's stance line reverses it. G14 requires `agentos/decisions/DEC-MACRO-COMMAND-STANCE-IS-GUIDANCE.md` in the same PR. The no-score / no-ranking clause is kept verbatim in meaning and is load-bearing for G3.)* | 本页展示各工作区已发布的内容。它不产生自己的评分，也不做自己的排序。 | Overview panel foot |

**Banned-substring CI list** — `scripts/check_macro_command_copy.py` fails the build on any hit in the built
`site/macro_monetary.html` **outside** a `.mc-details` or `.mc-primer` subtree:
`accepted print`, `accepted snapshot`, `method version`, `method-comparable`, `hysteresis`, `axis`, `Axis`,
`authority ceiling`, `content hash`, `generation id`, `producer`, `artifact`, `manifest`, `trace_ref`,
`definition_id`, `owner_ref`, `standardized`, `Diagnostics`, `Vector`, `vector`, `snapshot`, `deterministic`,
`schema`, `Regime map`, `Freshness`, `Presence`, `coverage_ratio`, `null_reason`, every uppercase
closed-vocabulary token in `lib/macro_suite_labels.py`, **plus the bare-timestamp regex of G2b**
(`\d{4}-\d{2}-\d{2}` in visible text with no plain word immediately before it, and any `T\d{2}:\d{2}` at all).

---

## §6 Section switching and payload plan

### §6.1 Decision: SSR the shell + Overview, fetch the other eleven as fragments

**Chosen:** `scripts/build_macro_suite_pages.py` writes `site/macro_monetary.html` containing the rail, the command
header, and the FULL Overview panel; the other eleven panels' figures are emitted as
`site/macro/fragments/<section>.html` and fetched on first activation. Rejected: SSR-all-plus-`hidden`, because the
fourteen workspaces' tables and evidence drawers are the bulk of the current pages, and shipping all of them puts
the Overview's time-to-read behind markup the reader did not ask for — the failure the brief names.

**Provisional budget, to be re-ratified in this file by P1 (G8, judge D12).** Initial document ≤ 90 KB
uncompressed / ≤ 28 KB gzip; each fragment ≤ 60 KB uncompressed. These three numbers are estimates, not
measurements. P1's acceptance requires printing `wc -c` for the fourteen built `site/macro_<slug>.html` pages and
the current `site/macro_monetary.html`, and **editing these three numbers in this spec** against that measurement
before P3 opens. No later packet may cite an unmeasured ceiling, and no packet may quietly widen one.

Fragments are static files served by the same VPS pull as the rest of `site/`; no API, no auth path, no
cache-busting beyond the render lane's normal `?v=` stamping.

### §6.2 Behaviour (`templates/macro_command.js`, ~140 lines, no framework, no style injection)

1. **Hash grammar (two segments).** *(Grafted from COMMAND §6.2.)* `#<section>` or `#<section>/<subtab>` —
   e.g. `#rates`, `#credit/funding`. On load, parse both segments; an unknown or empty section → `overview`; an
   unknown sub-tab → that section's first tab. A shared link therefore lands on the selected sub-tab and survives a
   reload.
2. Activating a section: set `aria-current="page"` on the rail link, clear `hidden` on the target `<section>`, set
   `hidden` on the previous one, `history.replaceState` the hash (so Back leaves the page rather than walking
   sections), then `panel.focus()` (the panel carries `tabindex="-1"`).
3. First activation of a non-Overview section: `fetch('macro/fragments/<id>.html')` →
   `panel.querySelector('[data-mc-figure]').innerHTML = text`. Before the fetch, JS unhides `[data-mc-pending]` and
   hides `[data-mc-offer]`; on failure or after 8 s it restores the offer and renders the §7 E5 state, which always
   contains the deep link. Never a spinner that can spin forever.
4. Sub-tabs are a real `role="tablist"`: ←/→ move, Home/End jump, `aria-selected` and `tabindex` roving, and the
   selection writes the second hash segment. Both sub-tab bodies ship inside the same fragment (they are one
   section's payload).
5. `prefers-reduced-motion` is respected by having **no section transition at all** — sections swap instantly in
   both themes. There is no animation clock anywhere on this page, which also keeps browser verification
   deterministic.
6. **No-JS is a first-class reading, not a broken one (D8).** The served document ships every panel **visible and
   unhidden**, and every non-Overview figure's default content is the honest offer line
   *"The full chart for this section lives on its workspace page →"* / "本板块的完整图表位于其工作区页面 →",
   linking to `macro_<slug>.html`. The "Loading this section…" line is `hidden` in the document and is unhidden by
   JS at boot. A reader with JS off therefore gets one long, correctly ordered page with eleven real destinations —
   never eleven panels that read "Loading…" forever.
7. `macro_command.js` contains zero colour literals, zero `style.textContent`, zero created `<style>` elements
   (G9). The only style-adjacent DOM it touches is class names and the `hidden` property.
8. **No twelve-panel flash on JS load** *(red-team F15 — the no-JS-first document of item 6 otherwise guarantees a
   full twelve-panel paint-then-hide on every JS load).* A blocking inline `<script>` in `<head>` — the ONLY inline
   script on the page — sets `document.documentElement.classList.add('mc-js')` before first paint.
   `templates/macro_command.css` carries `.mc-js .mc-panel[data-mc-secondary]{display:none}` so the JS reading
   never paints eleven panels. This is a class toggle, not style injection (G9 untouched: no `style.textContent`,
   no created `<style>`, no colour literal). P1's acceptance adds: first paint under a throttled profile shows
   exactly one panel.

### §6.3 The 14 deep-link pages

**Keep + link** (the brief's preference; it also preserves fourteen indexed URLs whose `seo_title`s are already set
on the fourteen `SuitePage` entries in `SUITE_PAGES` (`scripts/build_macro_suite_pages.py:73-237`); the builder
enumerates `SUITE_PAGES`, never a line range (red-team F7)). Each `macro_<slug>.html` keeps its current shell and
suite bar and gains ONE line directly under `_macro_suite_nav.html.j2`'s bar:

> EN: "This workspace also appears inside Macro Command → *Money & liquidity*."
> ZH: "本工作区也出现在宏观指挥台的《资金与流动性》板块中。"

linking to `macro_monetary.html#money`. No redirect: a redirect would break a paying subscriber's saved link and
erase fourteen indexed pages.

---

## §7 Empty-state copy

Six typed empty states. Each answers: what is missing, why, what unlocks it, when it refreshes. Never a bare em
dash (G4). Every one renders in EN and ZH.

**E1 — no data yet for this section**
- Title: "We don't have this reading yet" / "该读数暂不可用"
- Why: "The source this section is built from has not published a dated reading." / "本板块所依据的数据源尚未发布带日期的读数。"
- Unlocks: "It appears here the first time that source publishes." / "该数据源首次发布后即会出现在此处。"
- Next: "Checked again in tonight's update." / "今晚的更新会再次检查。"

**E2 — the source failed or is stale** (freshness states `SOURCE_FAILED` / `STALE_SOURCE`,
`lib/macro_suite_labels.py:38-47`)
- Title: "Today's number didn't arrive" / "今天的数据未能送达"
- Why: "The data provider did not deliver in time. We show nothing rather than yesterday's number dressed as today's." / "数据提供方未能及时送达。我们宁可不显示，也不会把昨天的数字当作今天的。"
- Unlocks / Next: "It returns as soon as the provider publishes; checked every night." / "数据源恢复发布后即会显示；每晚检查。"
- The chip for this section renders null-neutral, never red (§3.4).

**E3 — nothing comparable to compare with** (replaces `_macro_suite_shell.html.j2:340`, `:498`)
- Title: "We can't show the change yet" / "暂时无法显示变化"
- Why: "There is no earlier reading measured the same way, so any arrow would be invented." / "不存在以相同方法测得的历史读数，任何箭头都会是臆造的。"
- Next: "The first comparable reading appears after the next publication." / "下一次发布后将出现首个可对比读数。"

**E4 — declared but not open** (replaces `:689`-`:690`)
- Title: "Not open yet" / "尚未开放"
- Why: "This part is built but not switched on for customers." / "该功能已建成，但尚未对客户开放。"
- Unlocks: "It appears here when it is turned on. There is nothing you need to do." / "开放后会自动出现，无需操作。"

**E5 — this section couldn't load** (fragment / network failure)
- Title: "This section didn't load" / "本板块未能载入"
- Why: "The page couldn't fetch it just now." / "页面此刻未能取回该板块。"
- Action: "Reload the page, or open the full workspace →" / "请重新载入页面，或打开完整工作区 →" *(deep link)*

**E6 — included in a higher plan** *(grafted from the COMMAND draft §7 row 5 — we are a fintech SaaS and the
suite has no entitlement null today)*
- Title: "Included in a higher plan" / "包含于更高级别方案"
- Why: "This section is part of {plan}." / "本板块属于{plan}。"
- Unlocks: "Upgrade to see it" / "升级后即可查看" — `.mc-empty-cta` links to the existing plans page. The link is
  the only call to action on the page that is not a jump within it.
- Next: *(none — an entitlement state does not refresh nightly, and saying it would be a lie.)*
- The chip for a gated section renders `is-null` with value "Included in a higher plan", tone `neutral`, and its
  note carries the same sentence. A paywall is never `bad` tone: it is not a market verdict and not a failure.

Every dash anywhere on the page is emitted by `nulled()` and therefore carries `aria-hidden="true"` plus an
`.mq-sr` sentence — the pattern already established in the suite shell.

---

## §8 Analyst entry

**Decision: mount the existing sitewide widget. Do not navigate the reader off this page.** *(Judge D6 — this
reverses the winning draft's "link, do not mount" and adopts the COMMAND draft's outcome on evidence the draft did
not cite.)*

The premise for linking was that mounting `mm_brain.js` would import a runtime-injected stylesheet into a new
surface. That is a real property — `templates/mm_brain.js:4` says "Self-contained: injects its own CSS + DOM" —
but it is **not new on this page**: `templates/theme.js:5151-5163` resolves and loads `mm_brain.js` as a shared
asset sitewide (`templates/_navlinks.html.j2:233` calls it "mm_brain.js, sitewide"), and this page already renders
`{% include "_site_nav.html.j2" %}` (`templates/macro_monetary.html.j2:47`), whose inventory is
`_navlinks.html.j2`. The widget is therefore already present on Macro Command. Mounting adds no injection the page
does not already carry, while a link sends the reader off the one page frozen decision 1 exists to create.

- The rail's persistent control is a `<button type="button" class="mc-analyst" data-mc-analyst>` that calls the
  widget's **existing open entry point** and passes a plain-word section label ("Macro Command", or the current
  section's plain EN/ZH label) as the opening context. No new endpoint string, no new query parameter, no second
  chat chrome.
- **The `chat.html?topic=…&section=…` parameter is deleted from this spec.** It was never verified that the chat
  page reads it, and shipping an ignored parameter is machine text that lies. A packet may reintroduce a parameter
  only after verifying it against `templates/chat.html`.
- **Degraded fallback only:** if the shared-asset loader is absent at build time, the builder emits
  `<a class="mc-analyst" href="chat.html">` instead (the `analyst.mountable` branch in §2.7). Bare `chat.html`,
  no parameters.
- Label: "Ask the analyst" / "向分析师提问". At ≤ 768 it becomes a fixed bottom-right pill (§2.8) that never
  overlaps the horizontal rail.
- **P1 test:** the built page contains **exactly one** analyst control, and **zero** new endpoint strings — no
  `?topic=`, no `&section=`, no `/api/` literal anywhere in `macro_command.js` or the built page's own markup.
- `scripts/check_runtime_style_injection.py` stays green because *this page's* assets inject nothing; the widget's
  own self-contained CSS is pre-existing sitewide behaviour and is not newly authored here.

---

## §9 Build packets — five, ordered, each ≤ 1 PR

**Standing build notes that apply to every packet.** `templates/macro_command.css` and `templates/macro_command.js`
are non-`.j2` page assets, so they are **paired plain-copy assets** — add them to `SHARED_ASSETS` in
`scripts/build_macro_suite_pages.py:52` (which is exactly `SHARED_ASSETS = (...)`) and run
`python -m scripts.check_template_site_sync --fix` in the same PR. **No packet edits `templates/theme.css`** (all
new tokens live in `macro_command.css`), which also avoids the `?v=` stamp cascade. Any packet touching `site/`
must first run `python3 scripts/worktree_sparse.py full`. **Every packet's acceptance includes the copy guard
(`scripts/check_macro_command_copy.py`) green against the page that packet builds** — the guard ships in P1, not at
the end, because a customer-visible page that is ungated against the FRONT-END CLARITY LAW cannot lawfully be
reviewed `PASS` (judge D2). Every packet posts the theme-relevant subset of §10, both themes; a packet whose light
art direction has no crop is `PARTIAL/BLOCKED`, never `PASS`.

### P1 — Shell, rail, routing, tokens, and the copy guard *(no content change)*
- **Owned files:** `templates/macro_command.css` (new), `templates/macro_command.js` (new),
  `templates/_macro_command_macros.html.j2` (new — `nulled()`), `templates/macro_monetary.html.j2` (rail,
  `.mc-shell` grid, panel stubs, analyst control), `scripts/build_macro_suite_pages.py` (NEW `SECTIONS` tuple —
  ids/wiring only, zero prose — `SHARED_ASSETS`), `lib/macro_suite_labels.py` (NEW `SECTION_COPY[section_id]`
  reviewed bilingual `label`/`question` pairs — red-team F8; added here because §4's `s.label`/`s.question` are
  built by P1's rail), `scripts/check_macro_command_copy.py` (new guard, seeded with §5's banned list + the G2b
  timestamp regex), `.github/ci/legacy-jobs.yml` (guard wiring), `site/macro_command.css`, `site/macro_command.js`
  (plain-copy pairs), `tests/test_macro_command_shell.py`, `tests/test_macro_command_copy_law.py` (new).
- **Builds:** the twelve-section rail; two-segment hash routing; focus management; the sub-tab keyboard model; all
  twelve panels rendered as E1 empty states; the analyst control.
- **Tests:** rail has exactly 12 links in the fixed order; every `href="#id"` has a matching bare `id` (this is the
  assertion that catches a `#` smuggled into a section key, judge D9); `_site_nav.html.j2` byte-unchanged; no
  `<style>` and no `style.textContent` in `macro_command.js`; every `--mc-*` value is a `var(--…)` or a literal
  length/duration/percentage; the CSS defines **both** `:root` and `html[data-theme="light"]` for every
  theme-differing token; **no built page contains a `—` that has no sibling `.mq-sr`** (page-wide scan, grafted
  from the COMMAND draft); exactly one analyst control and zero new endpoint strings (§8); the copy guard is green.
- **Acceptance:** the rail navigates with mouse and keyboard in both themes and both languages; with JS disabled
  all twelve sections render in order and no panel reads "Loading this section" / "正在载入本板块"; no horizontal
  body scroll at 1440, 768 or 390 in either language (G12); `wc -c` printed for the fourteen built
  `site/macro_<slug>.html` pages and the current `site/macro_monetary.html`, and **§6.1's three byte numbers
  re-ratified in this spec file** (G8/D12); **first paint under a throttled profile shows exactly one panel**
  (§6.2 item 8, red-team F15). Acceptance is judged against the FRONT-END CLARITY LAW:
  > "Plain words; one-line stance per module; technicals demoted to hover/details; no machine text (raw slugs,
  > internal state names, untranslated stat names, bare timestamps); no walls of text; honest nulls in plain
  > words; EN/ZH. A non-quant customer must be able to read any surface in ten seconds."

### P2 — Command header: The Read + the state strip
- **Owned files:** `lib/macro_suite_labels.py` (`PREDICATE_FORM`, `STATE_TONE`, chip `meaning` copy, `SECTION_COPY`
  — red-team F8), `lib/macro_suite_view.py` (`build_hub_view` → `read`, `strip`, `coverage.sections_available`,
  `coverage.sections_total` — subject to **G16**'s merge receipt), `templates/macro_monetary.html.j2` (header
  block), `templates/macro_command.css` (`.mc-read*`, `.mc-strip`, `.mc-chip*`),
  `tests/test_macro_command_read.py`.
- **Tests:** no chip or clause is computed from more than one workspace (G3); chip tone comes from `STATE_TONE`
  keyed on `state_id` and **never** from `L.tone("freshness", …)` — asserted by fixture: a `SOURCE_FAILED`
  workspace yields a `neutral` chip, never `bad` (judge D1); no chip value for chips 1-7 matches `\d`, and chip 8's
  value matches exactly `^\d+ of \d+ sections have today's data$` / `^\d+ 个板块中有 \d+ 个已更新今日数据$` and
  nothing else (§3.0, red-team F11); **an unknown `state_id` is treated as null** — the clause is omitted,
  `read.omitted` is set, the chip renders its own producer `state_label` with tone `neutral`, the token is appended
  to `unknown_tokens()`, and the page is still written; `unknown_tokens()` is asserted empty for the shipped
  artifact and CI fails via a line-start `::warning title=macro-command-unknown-state::<token>` (bare print, flush)
  (§3.3 step 3, red-team F4 — supersedes the earlier "raises and no page is written" language); a null `state_id`
  omits the clause and sets `read.omitted`; fewer than three clauses suppresses The Read entirely; every null chip
  reads "Not available yet", never `—` alone; every visible date is preceded by a plain word (G2b);
  `unknown_tokens()` empty; zero ZH in any `title=`.
- **Acceptance:** The Read reads as one grammatical sentence in EN and in ZH against a live artifact **and** a
  deliberately half-null fixture; topic words jump to their section; the copy guard is green on the built page.
  Judged against the clarity law: *"no machine text … bare timestamps … A non-quant customer must be able to read
  any surface in ten seconds."*

### P3 — Panel contract + Overview + the first five sections
- **Owned files:** `templates/_macro_suite_shell.html.j2` (extract the figure blocks into reusable macros — no
  behaviour change to the 14 pages; **additionally owns the §5 rows whose strings sit inside a FIGURE block —
  rows 24, 27, 28, 29, 32, 35, 36, 40, 42, 43, 44, 45, 46 — red-team F12: figure headings are renamed to their §5
  plain forms and their method sentences moved into `<details class="mc-details">` in this SAME packet, the same
  packet that first ships a fragment; this is a packet-ordering fix, not a redesign — moved out of P5 because the
  copy guard (standing note, every packet) cannot be green in P3/P4 while a shipped fragment still carries a
  banned figure-block string**), `templates/macro_monetary.html.j2`, `scripts/build_macro_suite_pages.py`
  (fragment writer → `site/macro/fragments/<id>.html`), `lib/macro_suite_labels.py` (`PRIMERS`, `CAPTIONS`,
  `STANCES` for overview, money, policy, rates, inflation), `templates/macro_command.css`,
  `agentos/decisions/DEC-MACRO-COMMAND-STANCE-IS-GUIDANCE.md` (**required by G14**),
  `tests/test_macro_command_panels.py`.
- **Tests:** every panel has stance, primer, figure, caption, watching, details in that DOM order; word budgets
  enforced (stance ≤ 20 EN words / 34 ZH chars, caption ≤ 18, bullets ≤ 16, primer ≤ 45); every non-Overview panel
  ships the honest offer line as its **default** figure content and the pending line is `hidden` in the document;
  **with JS disabled no built page contains "Loading this section" / "正在载入本板块"** (judge D8); the copy guard
  (`scripts/check_macro_command_copy.py`) is green against the built page **and** every emitted fragment, with
  zero allowlist — the §5 figure-block rows moved above are why this is achievable in P3 (red-team F12); fragment
  and page sizes within the re-ratified §6.1 ceilings; the DEC record exists and names the reversal.
- **Acceptance:** Overview reads top-to-bottom with zero fragment requests; the four content sections load on first
  activation and fall back to E5 when the fetch is blocked; a non-quant reader can state what each of the five
  sections is saying after ten seconds on it. Judged against the clarity law: *"one-line stance per module;
  technicals demoted to hover/details … no walls of text."*

### P4 — The remaining six sections, sub-tabs, empty states, deep-link banner
- **Owned files:** `lib/macro_suite_labels.py` (copy for growth, jobs, housing, consumer, credit, debt, trade),
  `templates/macro_monetary.html.j2`, `templates/_macro_suite_nav.html.j2` (the one-line "also appears inside
  Macro Command" banner), `templates/macro_command.css` (`.mc-empty*`, `.mc-subtabs`),
  `tests/test_macro_command_empty_states.py`.
- **Tests:** each of E1–E6 renders all of its sentences in EN and ZH; no bare `—`; every `—` has an `.mq-sr`
  sibling; the E6 entitlement state renders `neutral`, never `bad`, and carries exactly one plans link; the three
  sub-tabbed sections write and restore the second hash segment (`#credit/funding` survives a reload); all 14
  `macro_<slug>.html` still build and each contains exactly one link to `macro_monetary.html#<section>`.
- **Acceptance:** all twelve sections complete; sub-tabs keyboard-navigate per WAI-ARIA and are linkable; the 14
  deep links resolve 200. Judged against the clarity law: *"honest nulls in plain words; EN/ZH."*

### P5 — Copy-law sweep of the shell, analyst polish, evidence
- **Owned files:** `templates/_macro_suite_shell.html.j2` (the §5 relocations — moving strings into `<details>`,
  never deleting them — **only the non-figure rows**; the figure-block rows (24, 27, 28, 29, 32, 35, 36, 40, 42,
  43, 44, 45, 46) already moved in P3, red-team F12; P5 does not re-touch them and ships no expiring allowlist),
  `lib/macro_suite_labels.py`, `templates/macro_monetary.html.j2` (row 62's footer rewrite),
  `templates/macro_command.js` (analyst open-entry-point wiring), `tests/test_macro_command_copy_law.py`
  (extend to the fourteen deep-link pages).
- **Tests:** the banned list has zero hits on **all fifteen** built pages outside `.mc-details` / `.mc-primer`;
  `scripts/check_design_system.py --mode enforce-added`, `scripts/check_runtime_style_injection.py`,
  `scripts/check_ui_visual_evidence.py`, `scripts/check_template_site_sync.py` all green.
- **Acceptance:** the full §10 matrix is posted in the PR body; a non-quant reviewer confirms G0 and G1 against the
  crops. Judged against the clarity law in full, quoted above.

---

## §10 Evidence matrix the builder must post

Twenty frames minimum in the PR body of P5, and the theme-relevant subset in each earlier packet (red-team F16 —
frame 17b added because no prior frame proved the light-only "ink word + 2px semantic underline" mechanism at
readable magnification, the mechanism most likely to be silently skipped in light). **A packet
whose LIGHT art direction has no crop is `PARTIAL/BLOCKED`, never `PASS`** — both themes are judged as designs
(hierarchy, material depth, semantic colour, responsive composition, EN/ZH parity), and functional browser success
is necessary but never sufficient.

| # | Theme | Lang | Width | Frame |
|---|---|---|---|---|
| 1 | dark | EN | 1440 | Above the fold: eyebrow + H1 + The Read + full chip strip |
| 2 | dark | ZH | 1440 | same |
| 3 | light | EN | 1440 | same |
| 4 | light | ZH | 1440 | same |
| 5 | dark | EN | 1440 | `#rates` panel, full: stance → primer(open) → figure → caption → watching → details(closed) |
| 6 | dark | ZH | 1440 | same |
| 7 | light | EN | 1440 | same |
| 8 | light | ZH | 1440 | same |
| 9 | dark | EN | 390 | Header + horizontal rail + first panel |
| 10 | dark | ZH | 390 | same |
| 11 | light | EN | 390 | same |
| 12 | light | ZH | 390 | same |
| 13 | dark | EN | 768 | Rail collapsed to chip rail + a sub-tabbed section (`#credit/funding`) with **the URL bar visible showing the two-segment hash** *(grafted from COMMAND §10 crop 11)* |
| 14 | light | ZH | 768 | same |
| 15 | dark | EN | 1440 | **`<details class="mc-details">` OPEN** on `#rates` — the only frame that proves the §5 technical boundary holds: every relocated string is present and readable inside the disclosure *(grafted from COMMAND §10 crop 12)* |
| 16 | light | EN | 1440 | same, Details open |
| 17 | dark | EN | 1440 | Zoomed crop of ONE Read topic word, proving the radial halo renders on the word itself *(judge D4)* |
| 17b | light | EN | 1440 | Zoomed crop of the SAME Read topic word, proving the 2px semantic underline renders as a rule under the word and that no halo is present (§2.6 row 2) *(red-team F16)* |
| 18 | dark | EN | 1440 | Half-null fixture: The Read with `read.omitted`, two null chips, one E2 panel, one E6 entitlement panel |
| 19 | light | EN | 1440 | same half-null fixture |

Plus, not as crops: (a) the byte sizes of `site/macro_monetary.html` and the largest fragment, against the
re-ratified §6.1 ceilings; (b) `git diff --stat` proving `templates/_site_nav.html.j2` and `templates/theme.css`
unchanged; (c) the copy-guard output; (d) a keyboard-only walkthrough note (Tab → rail → Enter → panel focus →
sub-tab arrows → Details); (e) a screen-reader note confirming the chip's "what this means" sentence is announced
via `aria-describedby` at 1440 (D13).

**Capture method (house-verified).** Headless Chrome clamps `--window-size` below ~500 px, so a 390 screenshot
taken that way is a wider layout clipped to 390 — a fake CSS bug. Capture the 390 and 768 frames through a
same-width iframe harness. `--screenshot` writes the PNG and then does not exit: poll for the PNG's `IEND` chunk,
use one scratch profile per shot, and kill by profile path. Do not verify colours by computed style alone —
`color-mix()` values do not resolve to comparable literals; judge the crops.

---

## §11 Judge findings applied

This spec is the GUIDED-READING draft (winner, 39/50) plus the nine named grafts from the COMMAND draft, with all
two blockers, six majors and four minors fixed. Nothing from the loser's four blocker/major findings is imported.

### Defects fixed

| ID | Severity | Defect | Where it is fixed in this spec |
|---|---|---|---|
| D1 | BLOCKER | Chip tone taken from `view.context.state_tone` (= `L.tone("freshness", …)`, `lib/macro_suite_view.py:136`), so a failed feed painted a market chip red — an instrument verdict rendered as a market verdict. | §3.2 tone column now reads `STATE_TONE[view.headline.state_id]` (`:289`), a NEW reviewed dict beside `FRESHNESS_TONE`; freshness demoted to the non-colour `.mc-chip-fresh` marker (§2.7, §2.8); §3.4 adds "A freshness state never sets a chip's tone. `SOURCE_FAILED` renders the chip null-neutral with the E2 reason, never red."; P2 test asserts it by fixture. |
| D2 | BLOCKER | The copy-law guard landed only in P5, so P1–P4 each shipped a customer-visible page ungated against the clarity law. | §9: `scripts/check_macro_command_copy.py` + `tests/test_macro_command_copy_law.py` + the `.github/ci/legacy-jobs.yml` wiring move into **P1**; the standing-notes paragraph now requires the guard green in every packet; P5 keeps only the shell relocations and the fourteen-page sweep. |
| D3 | MAJOR | `--mc-stance-wash: transparent` substituted into `color-mix(in srgb, currentColor var(--mc-stance-wash, 0%), transparent)` is invalid at computed-value time; the declaration drops and the documented fallback never fires. | §2.8 dark block now `--mc-stance-wash: 0%;`, light stays `6%`; the rule drops the dead `, 0%` fallback; a builder note explains why it must stay a percentage. |
| D4 | MAJOR | The Read's dark halo was a `z-index:-1` pseudo on an element with no stacking context — it painted behind the page canvas and the signature element degraded to plain tinted text. | §2.8 `.mc-read-topic` paints the halo as a `background-image: radial-gradient(...)` on the element itself; the `::before` rule is deleted; §10 frame 17 is a zoomed dark crop proving it renders. |
| D5 | MAJOR | New `.mc-tone-*` classes duplicated `macro_suite.css:88-91`'s `.mq-tone-*` and substituted FILL tokens as text colour — a contrast risk on light and a second tone family on one page. | §2.8 mints no tone class; §2.7 uses `mq-tone-{{ … }}` at all four sites (rail dot, Read topic, chip, stance); §2.6 records that tone ink is inherited from `macro_suite.css`, never re-minted; G10 restates it. |
| D6 | MAJOR | "Link, do not mount" rested on an unproven premise and sent the reader off the one page the product decision creates; it also invented an unverified `chat.html?topic=&section=` parameter. | §8 rewritten to **mount the existing sitewide widget**, citing `templates/theme.js:5151-5163`, `templates/_navlinks.html.j2:233` and `templates/macro_monetary.html.j2:47`; the query parameter is deleted; bare `chat.html` survives only as the degraded build-time fallback; P1 test asserts exactly one analyst control and zero new endpoint strings. |
| D7 | MAJOR | "`state_label` … comes pre-reviewed out of `lib/macro_suite_labels.py`" is false — `lib/macro_suite_view.py:290` builds it from the producer snapshot; the whole `PREDICATE_FORM` plan was staked on it. | §3.2 closing paragraph now names the snapshot as the source and lists what labels.py actually owns; §3.3 step 1 keys `PREDICATE_FORM` on `view.headline.state_id` (`:289`); step 3 makes an UNKNOWN `state_id` **fail the build** rather than silently omit a clause. |
| D8 | MAJOR | Eleven panels shipped a visible "Loading this section…" that no-JS readers would read forever — a machine-shaped lie about state. | §2.7 renders the pending line `hidden data-mc-pending` and makes the **default** figure content the honest offer with a real deep link; §6.2 item 6 rewritten; P3 test: with JS disabled no built page contains "Loading this section" / "正在载入本板块". |
| D9 | MAJOR | §1.1 printed section ids as `#money` while the template renders `id="{{ s.id }}"` / `href="#{{ s.id }}"` — every section link and `:target` route dead. | §1.1's column is now "Section id (bare token)" with bare values and an explicit sentence that the template adds the `#`; P1's "every `href="#id"` has a matching `id`" assertion is called out as the test that catches a regression. |
| D10 | MINOR | Row 56 cited `~:118` for a string at `:95`; there was no row for the published composition footer at `:168`, whose "it never tells you what to do" clause the stance line reverses. | §5 row 56 corrected to `:95`; new rows 57 (`:132`), 58 (`:145`), 59 (`:169`) and 62 (`:168`, keeping the no-score/no-ranking clause and dropping the no-guidance clause); **G14** requires `agentos/decisions/DEC-MACRO-COMMAND-STANCE-IS-GUIDANCE.md` in P3, the packet that ships the stance line. |
| D11 | MINOR | E2 cited `lib/macro_suite_labels.py:44-45` for `SOURCE_FAILED` / `STALE_SOURCE`. | §7 E2 recited as `lib/macro_suite_labels.py:38-47`. |
| D12 | MINOR | Byte ceilings (90 KB / 28 KB gzip / 60 KB) and the SSR-all rejection rested on an uncited "~700 KB" estimate; nothing was measured. | §6.1 marks the three numbers **provisional**, drops the uncited estimate from the rejection rationale, and P1 acceptance requires printing `wc -c` for the fourteen built pages plus the current hub and **re-ratifying the numbers in this file before P3 opens**; G8 restates it. |
| D13 | MINOR | `.mc-chip-help` was `visibility:hidden` until hover, so the chip's explanation — the place a NULL chip explains itself — was out of the accessibility tree for a linear screen-reader read at ≥ 481 px. | §2.7 binds the note with `aria-describedby="{{ chip.id }}-help"` on `.mc-chip-link` and gives `.mc-chip-help` that id; the visual hide is unchanged; §3.0 chip law item 4 and §10 evidence item (e) pin it. |

### Grafts applied

| ID | Graft | Where |
|---|---|---|
| G1 | Bare-timestamp ban + plain-word as-of prefix ("Data to" / "数据截至", machine value only in `datetime=`) | Gate **G2b**; §2.7 eyebrow + chip as-of; §3.0 item 2; §5 banned-list regex |
| G2 | Entitlement null ("Included in a higher plan" / "包含于更高级别方案") | §7 **E6**, plus its chip rule and P4 test |
| G3 | Reusable `nulled(reason)` macro + the page-wide "`—` with no sibling `.mq-sr`" scan | §2.7 macro block; §9 **P1** test list (not P4/P5); G4 |
| G4 | Second hash segment for sub-tabs (`#credit/funding`) so a sub-tab is linkable and survives reload | §6.2 item 1 and item 4; P4 test; §10 frame 13 |
| G5 | Crops 11 and 12: the sub-tab hash frame and the **Details-open** frame | §10 frames 13/14 and 15/16 |
| G6 | Hub-side copy rows, corrected to the hub's real line numbers | §5 rows 56 (`:95`), 57 (`:132`), 58 (`:145`), 59 (`:169`), 62 (`:168`) |
| G7 | The MOUNT outcome for the analyst entry, re-argued on the loader evidence | §8 (see D6) |
| G8 | "The page never scrolls horizontally at 1440, 768, 390 in both languages" as a standing gate | Gate **G12**; §2.8 `min-width:0` / `overflow-x:auto` rules; P1 acceptance |
| G9 | "A chip value is a word, never a number, never a state id, never a slug" | §3.0 chip law item 1; P2 test asserting no digit in any chip value |

### Loser findings deliberately NOT imported

- **L1** — the "Rates: Falling · Flat · Rising" chip sourced from `view.headline.axes[0].direction`: `axes` is a
  top-level view key, not a child of `headline`, and `direction` is a legend vocabulary ("Higher = tighter
  funding"), never a rates direction. No chip in §3.2 reads an axis direction.
- **L2** — a chip note revealed only on `:hover` / `:focus-within` inside an `<li>` with nothing focusable. §2.7's
  chip contains a real `<a class="mc-chip-link">` **and** binds the note with `aria-describedby` (D13).
- **L3** — deferring the light art direction to a later packet. Every packet here ships both `:root` and
  `html[data-theme="light"]` and posts both themes (§9 standing notes, G11).
- **L4** — the fused "Regime" chip. Refused in §3.1 on `templates/macro_monetary.html.j2:8-14`.
- **L5** — asserting the brain widget mounts "exactly as on the dashboard" while leaving the self-injected-CSS
  conflict unnamed. §8 names the conflict and resolves it on the sitewide-loader evidence.

---

## §12 Open items the builder must close (not blockers to freezing)

1. **`PREDICATE_FORM` volume.** The reviewed EN/ZH predicate for every `state_id` the fourteen workspaces can emit
   needs a human writing pass. P2 must enumerate the state ids before it is sized. An unknown id is a printed null,
   never a build failure (§3.3 step 3, red-team F4) — `unknown_tokens()` surfaces every gap in CI, so the
   vocabulary cannot be shipped half-written and silently degrade without CI going red.
2. **The archetype name** in `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` §10 must be copied verbatim into the
   page's DS header comment by P1.
3. **`.mq-card` vs `.mc-panel`.** `templates/macro_suite.css` already carries a card system. P1 must decide
   explicitly whether `.mc-panel` supersedes `.mq-card` on this page or wraps it, and record the answer here — two
   card systems on one page is a named failure mode in the design system.
4. **Chart restyle depth.** This spec restyles the figure *frame* (`.mc-figure` plot ground, gridlines, caption).
   Whether the workspace SVGs need per-theme stroke tokens is a P3 finding; if they do, it is its own packet, never
   a silent widening of P3.

---

## Changelog v2 (red-team 2026-09-06)

An Opus red-team of this frozen spec on PR #6914 returned `FIX_SPEC_FIRST` (6 blocker-graded findings — F1/F3/F6
adjudicated as one root cause with three repairs, plus F4, F11, F12 — 6 major, 1 minor). Every finding is applied
below; nothing the red-team marked "not wrong" (the two art directions, D1's tone fix, the forbidden regime chip,
the §5 copy law instrument, `SHARED_ASSETS:52`, the 726-line shell, `macro_suite.css:88-91`/`:16-18`,
`unknown_tokens()` at `:368`, the 14-workspace registry order) was re-litigated or changed.

| Finding | Severity | Defect | Edit applied |
|---|---|---|---|
| F1 | BLOCKER | The whole spec is pinned to an unmerged branch (PR #6873) by `file:line` citations, with no statement that the lines are advisory. | New **§0.0 BASE** section; new **G15** (§0); §5 preamble rewritten to state the binding identity is (string, file), line numbers advisory, re-resolved by P1 before P2 opens. |
| F3 | BLOCKER | `build_hub_view` does not exist on `origin/main` — the spec names a producer no builder produces. | New **G16** (§0) requiring a merge + `grep -n 'def build_hub_view'` receipt before any packet opens; §9 P2 owned-files line cites the receipt gate. |
| F4 | BLOCKER | "An UNKNOWN `state_id` fails the build" puts a producer-controlled hard-fail on the nightly render path, deleting the flagship page over a missing translation. | §3.3 step 3 rewritten: unknown `state_id` is a printed null — clause omitted, `read.omitted` set, chip renders neutral, token appended to `unknown_tokens()`, page still written; CI fails via a line-start `::warning` on a non-empty `unknown_tokens()`. §9 P2 tests and §12 item 1 updated to match (removed the contradictory "raises" language). |
| F6 | BLOCKER | The page the spec converts (`templates/macro_monetary.html.j2`, `site/macro_monetary.html`) does not exist on `origin/main` — only a different workspace (`macro_monetary_policy`) does. | Folded into the new **§0.0 BASE** section: states the spec is buildable only on PR #6873's branch or on main after #6873 merges, names the exact missing files/symbols measured on main, and gates P1's start on the merge. |
| F7 | MAJOR | `s.deep_href` and §6.3 cite `scripts/build_macro_suite_pages.py` "lines 76-226", which silently excludes `trade_flows` (the 14th workspace, entry at :225-236). | Both citations replaced with "the fourteen `SuitePage` entries in `SUITE_PAGES` (`scripts/build_macro_suite_pages.py:73-237`); the builder enumerates `SUITE_PAGES`, never a line range." |
| F8 | MAJOR | §4 sources bilingual copy from a `SECTIONS` constant that does not exist, and would put customer-visible strings in a build script outside the reviewed-vocabulary module. | §4's `s.label`/`s.question` row rewritten to source `SECTION_COPY[section_id]` from `lib/macro_suite_labels.py`; `SECTIONS` in the builder is ids/wiring only. `lib/macro_suite_labels.py` added to P1's owned files. |
| F9 | MAJOR | Chip 8's `view.coverage.available`/`.total` has no producer; the real field is a formatted percentage string with no `available`/`total` integers. | §3.2 chip 8 row rewritten to `view.coverage.sections_available`/`.sections_total`, new integer fields counted over the twelve rail sections (never the fourteen-workspace registry); states `fmt_ratio_pct` output is display-only and never parsed. |
| F11 | BLOCKER | Chip 8's value contains digits, but P2's own required test forbids any digit in every chip value. | §3.0 rule 1 rewritten: digit ban scoped to chips 1-7; chip 8 is the declared exception, pinned by the exact counted-phrase regex `^\d+ of \d+ sections have today's data$` / `^\d+ 个板块中有 \d+ 个已更新今日数据$`. §9 P2 tests updated to match. |
| F12 | BLOCKER | The copy guard is required green in every packet, but P3/P4 ship fragments carrying figure-block strings the guard bans — the relocation that would fix it was scheduled for P5, after the guard must already be green. | §9 P3 owned files/tests: figure-block §5 rows (24, 27, 28, 29, 32, 35, 36, 40, 42, 43, 44, 45, 46) moved from P5 into P3, renamed/relocated in the same packet that first ships a fragment, zero expiring allowlist. §9 P5 owned files narrowed to the non-figure rows plus the fourteen deep-link pages. |
| F13 | MAJOR | Three sections (`money`, `growth`, `credit`) each own two workspaces, but §4's panel contract has only one `view` — the stance owner is undefined, risking a fused composite (G3 exposure). | §1.1 bolds the PRIMARY workspace in rows 1, 5, 9; new §4 row states the stance and its tone come from the PRIMARY only, named in plain words, and the second workspace's stance renders only in its own sub-tab. |
| F14 | MAJOR | §3.1's guarantee ("the chip's label says which workspace it came from") is violated by chips 1, 5, 7, whose labels are the two-workspace SECTION names, not the sourcing workspace's own name. | Chip labels renamed to the sourcing workspace's own plain name: chip 1 "Money on the market / 市场资金", chip 5 "The whole economy / 整体经济", chip 7 "How hard it is to borrow / 融资难易" (§3.2). |
| F15 | MAJOR | The no-JS-first document ships all twelve panels visible and unhidden, guaranteeing a full twelve-panel flash on every JS page load with no packet testing the transition. | New §6.2 item 8: a head-inline blocking `<script>` adds `mc-js` to `<html>` before first paint; `templates/macro_command.css` hides secondary panels under `.mc-js`; P1 acceptance gains "first paint under a throttled profile shows exactly one panel." |
| F16 | MINOR | The evidence matrix proves the dark-only radial-halo mechanism at zoom but never the light-only 2px-underline mechanism, leaving light art direction unjudgeable at that mechanism. | New frame **17b** (light, EN, 1440, zoomed) in §10; matrix renumbered from nineteen to twenty frames; G11 updated to twenty frames. |

