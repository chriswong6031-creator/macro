# Unified Dashboard UX Pattern Brief
Date: 2026-09-06
Author: Meta-CEO B (Claude3 seat) — designer lane, opus
Audience: Meta-CEO A — owner of the macro unified dashboard (Chairman directive 2026-09-06)
This brief is ADDITIVE to `research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md` and must be read together with it.
This brief describes patterns abstractly; it contains no MarketOntology code, copy, data, or assets.

# Unified Dashboard — UX Pattern Brief (2026-09-06)

**For:** Meta-CEO A, as input to the Mastermind unified Market OS dashboard.
**From:** Meta-CEO B (session 7cd4fae1), ROUTE design.
**Authority:** Chairman 2026-09-06 — study MarketOntology's UX pattern; never copy their code,
text, data or assets.
**Status of this file:** scratchpad analysis. No repository file was edited, nothing was built,
nothing was posted, no screenshot was committed.

**Relationship to the existing study.** `research/MARKET_OS_UNIFIED_DASHBOARD_PATTERN_STUDY_2026-09-06.md`
(844 lines) already covers the marketing surfaces, the authenticated shell IA (§1.11), the module
empty states (§1.12), mobile at 375 (§1.13), and a first mapping proposal (§2.2). **This brief does
not restate it.** It adds what that study explicitly listed as unobserved or did not reach: the
*inside* of a populated analytical workspace, the *case document* archetype, the honest-null
promotion grammar, and a light-theme finding. Where this brief refines §2.2, it says so in §6.

---

## 0. What I actually opened, and what I could not see

Session was already signed in (the shell offered a sign-out control). I signed nothing in or out,
connected no brokerage, ran no recompute, saved no setting, and wrote no state.

| # | Surface | How reached | Width | What I captured |
|---|---|---|---|---|
| 1 | **Capital command home** (the signed-in root) | site root | 1440×1000 | a11y tree (interactive + full), page text, 2 screenshots |
| 2 | **Macro workspace** | direct route | 1440×1000 | full page text, 1 screenshot |
| 3 | **Inbox / threads list** (decision queue) | rail click | 1440×1000 | page text, a11y tree with real `href`s |
| 4 | **A single case document** (one thread, opened) | direct route to that case id | 1440×1000 | full page text, 1 screenshot |
| 5 | **Route-not-found state** | deliberately bad path | 1440×1000 | page text |

Six screenshots budgeted, six used (two of #1, one each of #2 and #4, one theme-toggle attempt,
one forced-light probe). None committed, none distributed.

**Could not see, and it matters:**

* **The populated calm state.** The account has no linked book, so the command home, next-moves and
  every portfolio-shaped module rendered *empty*. "Nothing much happened today, on a real book" —
  the state our users hit most — remains unobserved. This is the same gap the earlier study flagged
  and I did not close it.
* **The five top-strip product families' contents.** Clicking or hovering a family name never opened
  a menu in my session; it re-scopes the rail, and the rail did not re-scope for me. Item counts are
  measured (capital 9 / team 1 / quant 3 / decision tools 7 / sector intelligence 4 = 24) but the
  other four families' destination names are not.
* **Their supported light art direction.** The shell exposes a theme control; activating it did not
  change the rendering in my session (the document root stayed on its dark class, computed body
  ground unchanged). I then *locally* forced the root off its dark class in my own browser DOM — see
  §4.4 for what that showed and why it is evidence about our own risk, not a verdict on their
  product.
* **Any second locale.** No language control was exposed on the surfaces I opened; EN only.

---

## 1. The information architecture pattern (diagram-in-text)

Observed on the **capital command home** and confirmed unchanged on the **macro workspace**, the
**inbox** and the **case document** — the chrome is literally the same four regions on all four.

```
┌─ A · TOP STRIP ────────────────────────────────────────────── sticky ─┐
│ [family][family][family][family][family]   search⌘K  tour n/6         │
│  each family carries an item count          region▾  inbox  theme     │
├─────────┬─────────────────────────────────────────────────────────────┤
│ B ·RAIL │ C · CANVAS                                                  │
│ sticky  │                                                             │
│         │  C1  title  ·  eyebrow = "<active group> · N modules"       │
│ zone 1  │      right-aligned: find-a-feature · ONE primary · filter   │
│  home + │  C2  SCOPE LINE — what the lens is set to, before any data  │
│  8 one- │  C3  STATUS STRIP — 9 fields, one row, label over value     │
│  word   │      3 money · 1 period · 1 session · 4 EVIDENCE-QUALITY    │
│  work-  │  C4  SUB-TABS — 7 module groups; canvas swaps, chrome holds │
│  spaces │  ┌────────────────────────────────────────────────────────┐ │
│ ── gap  │  │ MODULE BAND                                            │ │
│ zone 2  │  │  head (small caps)              OPEN ▸    EXPAND ▸     │ │
│  inbox  │  │  ── collapsible read band: freshness · evidence-type · │ │
│  pulse  │  │     confidence · trace-receipt · send-to · share       │ │
│ ── gap  │  │  ── provenance strip: fetched | snapshot clock |       │ │
│ zone 3  │  │     source date | region | window | update             │ │
│  desk   │  │  ── KPI tiles (label · date · value · delta)           │ │
│  settngs│  │  ── in-module tabs: current/drivers/history/…          │ │
│  signout│  │  ┌── dominant visual ~2/3 ──┬── diagnostics rail 1/3 ─┐│ │
│         │  │  │  the one picture         │ ranked constraints      ││ │
│  active │  │  │                          │ ranked supports         ││ │
│  row =  │  │  └──────────────────────────┴─ observed moves (prose) ─┘│ │
│  accent │  │  ── what changed since last print: from → to · delta   │ │
│  edge   │  └────────────────────────────────────────────────────────┘ │
│  bar    │  … next module band … (macro workspace stacks ~14 of these) │
└─────────┴─────────────────────────────────────────────────────────────┘
                                                    ┌──────────────────┐
                                                    │ D · ANALYST pill │ sticky
                                                    │  bottom-right    │
                                                    └──────────────────┘
```

**What is sticky:** A (top strip), B (rail), D (analyst pill). Everything in C scrolls, including
the status strip and the sub-tabs. That is a deliberate trade — the *navigation* is permanent, the
*reading* is not — and it is the opposite of our estate's habit of pinning tape strips.

**Two facts about C worth naming for our build:**

1. **The eyebrow is state, not a breadcrumb.** On the command home it read as the active group plus
   how many modules that group is showing. One line does the job we currently spend a breadcrumb
   trail on, and it tells you *how much is on screen*, which a breadcrumb never does.
2. **The scope line comes before the numbers.** On the command home, two short phrases stated that
   no book was linked and that scope was none — *above* the money tiles. The page sizes its own lens
   before it shows you anything through it. Our alerts board already does the moral equivalent
   (withholding the overall stance when a source failed); this is the same idea promoted to a fixed
   region.

**The single most decisive finding for our 14-page question — the macro workspace.**
The whole macro domain is **one page**, with a horizontal chapter rail under the page title
carrying on the order of fourteen chapter names (regime, growth, activity, labour, inflation,
monetary, rates, conditions, liquidity, flows, structure, housing, consumer, debt). Each chapter is
one module band in a single vertical scroll; the chapter rail scrolls you to it. There is no
per-chapter route, no per-chapter chrome, and no separate page header per chapter. **Their answer to
"fourteen macro subjects" is one page with fourteen anchors, not fourteen destinations.** §6 works
out what we take from that and what our own density law will not let us take.

---

## 2. Glance → detail, and how receipts are surfaced

Three altitudes, and they are *materially different compositions*, not the same grid at three sizes.

### 2.1 Altitude 1 — the board row (inbox)

One table, four columns: a **state word**, the subject, a condition, an activity date. The state word
is a single word or two (act / no action) and it is the **leftmost** thing in the row. A reader scans
one column and knows the shape of the day before reading a single subject line. Everything else on
that row is identification, not analysis.

Below it, two more boards with the same discipline: a past-ideas board (date · subject · idea ·
sleeve · state · a plain-sentence read of how it compares to the prior record), and a self-critique
board with an instrument/direction/window/move/outcome table.

### 2.2 Altitude 2 — the module band (macro workspace)

Each band answers one question and carries its own complete evidence apparatus:

* **A prose consequence first**, three to four sentences, then everything numeric.
* **A read band** carrying, in one line: relative freshness ("updated <n>h ago"), what *kind* of
  evidence backs it (e.g. historical analogue), a confidence grade as a word, a **trace-into-the-
  model receipt link**, a send-to-my-book action, and a share action.
* **A provenance strip** that separates two things our estate routinely conflates: **when we fetched**
  (a wall-clock snapshot plus "just now") and **what date the underlying source is stamped**. Both are
  printed. A third field names the observation window.
* **The state is named in words and the rule that produced it is printed underneath it.** A quadrant
  label is followed by a plain sentence of the form "composite X above 50 and composite Y above 50".
  The classification rule is disclosed inline, at glance, in one sentence — not hidden behind a
  methodology link.
* **Every composite carries a direction gloss** ("higher = tighter", "higher = stronger support"), so
  a bare index number cannot be misread.
* **Distance-to-state-change is a first-class field**: a "nearest threshold" number with the caption
  "points to next boundary". That is a genuinely useful glance statistic and we do not have it.
* **What changed since last print**, as explicit `from → to` pairs with the delta, dated on both ends.
* **Ranked contributors split into two named lists** — what is constraining and what is supporting —
  each row a named driver, its level, and its contribution weight.
* **A prose closer**: three or four one-line sentences restating the move in ordinary English
  ("<driver> is the main rate-side constraint").

### 2.3 Altitude 3 — the case document (`/resolve/<case id>`)

This is the pattern I most want Meta-CEO A to see, and it is **not a dashboard**. It is a single
centred reading column, roughly 45% of the viewport wide, with the shell still around it. Order:

1. Back link to the board, plus three actions (send another, save, open the market view).
2. **Verdict word**, large, in the accent — then a version and confidence line.
3. Title, then a one-sentence "why this matters", then one paragraph of mechanism.
4. **The personalisation line**: how many of *your* positions sit on the modelled path and the
   estimated impact, plus an as-of stamp, your book size, and the model version.
5. **"Which capital is affected"** — a table of position · direction (as a plain word like
   *tailwind*) · weight · estimated impact · mechanism prose.
6. **A negative-coverage line naming what was NOT covered**: "no modelled path for: <the other
   positions>". Absence is printed as a value with the specific items named. This is the strongest
   honesty device on the whole product.
7. **The causal path**, as chained steps with a per-path confidence and an explicit arrow between
   hops — a chain, not a score.
8. **The eligible response**, phrased as an imperative a person owns, with one sentence of reason —
   *and immediately below it the rejected alternative with the reason it lost.* Showing the beaten
   option is what makes the recommendation legible rather than oracular.
9. **A commitment device before the priced recommendation is revealed.** The page asks what you
   would do right now — a row of plain verb chips plus an honest "not sure" — and states that your
   answer becomes the benchmark the recommendation is measured against. Only then does it compile.
   This is pre-registration, executed as UI, on the user's own prior.
10. **An unresolved condition you can arm**, which reopens the case as a new version when it changes.
    The detail page is therefore where alerts are *created*, not just where they land.
11. **Evidence, split into two hard-labelled lists**: factual claims, and — under an explicit
    "not established fact" heading — inferences. The invalidation conditions live in the inference
    list and are phrased forward ("invalidation requires transits to normalise"), never as a verdict
    about a dead thesis.
12. **A source footer** naming the origin and the capture timestamp.

**The receipts model in one sentence:** the *number* carries its meaning at glance, the *machinery*
(window, source date, confidence, model version, rejected alternative, inference-vs-fact split) is
printed further down the same document rather than hidden in a hover — which is linkable, printable
and survives touch. Our LENS hover tier should keep per-number receipts, but every working surface
should also carry one readable end-of-page evidence block.

---

## 3. Navigation model, and clicks to anything

Two levels of destination plus one level of in-page grouping. Measured on the command home.

| Level | Mechanism | Inventory |
|---|---|---|
| 0 | Search field with a keyboard hint (top strip) | everything, in 0 clicks + 1 keystroke |
| 1 | **Top strip: 5 product families**, each showing its item count | 24 destinations total |
| 2 | **Left rail: one column of one-word labels**, three zones separated by gaps — home + 8 workspaces / 2 inbox-shaped items / 3 bottom-pinned utilities | 9 visible for the active family |
| 3 | **Sub-tabs inside the canvas: 7 module groups** — the URL, the rail selection and the chrome all hold still | ~22 modules behind 7 groups |
| 4 | In-module tabs (current / drivers / history / scenario / alerts) and a per-band expand control | depth, not destinations |

**Click cost.** Destination in the active family: **1**. Destination in another family: **2**. A
specific module group on that page: **3**. Deeper reading inside a module: 4. A case document from
its board row: 1. Back to the board from a case: 1. Nothing in the product I reached cost more than
three clicks, and the search field makes any of the 24 a single keystroke away.

**The design act worth naming:** *the top strip chooses which nine things the rail offers; the rail
chooses the page; the sub-tabs choose which modules render.* Twenty-four destinations, never more
than about a dozen labels visible at once, and no flyout, mega-menu or nested dropdown anywhere.
Our estate currently spends three tiers of hover flyouts to expose a comparable inventory.

**Two rail details we should take:** every rail label is one word, and **there are no counts or
badges in the rail** — counts live in the top strip, where they describe an inventory, not in the
rail, where they would read as unread-item anxiety. The active row is marked by an accent bar on its
leading edge over a slightly raised ground, and nothing else in the rail is coloured at all.

---

## 4. Empty, degraded and absent states

### 4.1 The empty command home — the specimen worth studying

With no book linked, the home did **not** show zeros, placeholder charts, or a marketing upsell. It
showed:

* the scope line saying, in two short phrases, that no book is linked and the scope is none;
* the nine-field status strip **fully rendered, with a distinct null phrase per field** — the money
  fields showed a typographic dash, and the four evidence fields each carried their own reason
  ("pending baseline", "not supplied", "not reconciled", "no source stamp", "not evaluable"). The
  strip's *geometry never collapses*, so the reader learns the shape of the product from its empty
  state;
* one primary action (link a brokerage account) and nothing competing with it;
* a module-level empty sentence that states **why** there is nothing and **what would change it** —
  in substance: nothing is generated without reconciled holdings, stated objectives and dated event
  records, so recompute once a book is linked. Cause, then remedy, in one sentence, in the product's
  own voice. No apology, no exclamation, no telemetry.

**Four different null words for four different absences** is the transferable rule: "not supplied"
(you never gave it), "not reconciled" (we have it but cannot trust it), "no source stamp" (we cannot
date it), "not evaluable" (we cannot compute the answer at all). A single `—` for all four, which is
our estate's habit, destroys information the user needs.

### 4.2 The absent-path pattern (case document)

Covered in §2.3 item 6 and repeated here because it is the pattern: **name the items you could not
model, by name, inline.** Not a footnote, not a count.

### 4.3 The honest-null promotion rule (self-critique board)

The board that claims to tell you what you are systematically wrong about, when it has no basis,
prints three things instead of a number:

* the exact denominator decomposition (how many ideas have a scored window, how many are still
  inside their horizon, how many have no price coverage);
* a plain sentence saying no pattern holds yet;
* **the promotion rule itself, in ordinary English** — that a pattern is only stated once at least
  four ideas in the same bucket have a scored window *and* the bucket is losing more than it wins.

And each unscored row's outcome column reads "not scored" rather than a zero or a dash. This is our
own epistemics law — nulls printed, gauntlet at promotion, display-tier until proven — rendered as
consumer UI with no jargon in it. It is the single best argument that our doctrine is shippable to
retail users rather than a compliance tax.

### 4.4 Route-not-found, and the theme probe

The bad-route state is four elements: a code, a two-word description, the offending path in muted
mono, and exactly one action back to the dashboard. No prose. (The two-word description is machine
register — see §7 note 4.)

**Theme probe, stated precisely.** The shell exposes a theme control. Activating it produced no
change in my session; the document root remained on its dark class and the computed body ground was
unchanged. I then removed that dark class *locally in my own browser DOM* — a read-only probe of a
page already loaded, changing nothing on their side. The result was a half-migrated rendering: the
canvas went white while the rail stayed dark, the warm accent lost contrast against white, and the
module bands lost the luminance step that had been carrying their boundaries, so the card structure
disappeared. **This is not a finding about their product** — I never obtained a *supported* light
rendering, and their light direction remains genuinely unobserved. It is a finding about *the
mechanism*: an art direction that carries elevation by luminance step and emphasis by accent-on-dark
has no light behaviour to fall back on. That is exactly the failure our theme law names, and it is
the risk our own build inherits if anyone proposes to reach light by swapping tokens.

**Therefore, binding on whoever builds this (CLAUDE.md §Theme art direction):**

* **DARK — command centre.** Panels raised by luminance step, hairlines only where two data regions
  genuinely abut, the semantic accent spent on the stance word and one primary action, direction
  carried by hue *plus* glyph, restrained glow permitted on the stance word only as the page's single
  signature moment.
* **LIGHT — research workspace.** Cool paper canvas, white material panels, elevation by soft shadow
  plus hairline (never inverted glow, which smears on light), the stance word emphasised by **type
  scale and ink density instead of luminance**, chart grid inverted to a warm grey that stays below
  the ink, and chips rendered as tinted-solid-with-border rather than translucent tint, because
  translucency over white loses the direction hue.
* **Mechanisms that intentionally differ:** elevation, the stance-word emphasis mechanism, chart-grid
  polarity, chip fill. Everything else — IA, component semantics, spacing and type scale, state
  meanings, actions, ordering, density budgets, interaction — is identical.
* **Evidence gate:** the implementing packet ships dark/light × EN/ZH × 1440 / 390 or is reported
  `PARTIAL`. Token substitution is not proof of a light design.

---

## 5. Plain-language conventions observed (described abstractly)

Every convention below was read off the surfaces named in §0. None of their wording is reproduced.

1. **Destinations are named for the user's subject, not the producing engine.** One-word rail labels
   naming a domain a person already has a word for. No engine, pipeline or study name appeared in
   any label on any surface I opened.
2. **Actions are outcome verbs a person owns**, in the imperative, and the same verb survives the
   whole flow. Where the product wanted the user to commit before seeing a recommendation, it offered
   verb chips — hold / trim / close / add / hedge / roll — plus an honest "not sure". The escape hatch
   is a real option, not a dead control.
3. **A stance word is one or two words and sits leftmost**, in the accent, before any number.
4. **Every number arrives with its direction gloss or its meaning.** Composites carry "higher means
   X"; a state name is followed by the rule that produced it; deltas are printed as `from → to` with
   both dates. A bare index value with no gloss did not appear on the macro workspace.
5. **Absence is vocabulary, not punctuation.** Distinct phrases for not-supplied, not-reconciled,
   not-dated, not-evaluable, not-scored. Uncovered items are named individually.
6. **Uncertainty is graded in words at glance and in numbers below.** Confidence appears as a word
   in the read band; the decimal appears in the causal-path rows underneath.
7. **Refutation language is forward-tense.** Invalidation is written as a condition that would have
   to occur, filed under an explicitly labelled "not established fact" list — never as a claim that a
   thesis has been killed. This matches our own front-facing rule exactly and is worth pointing at
   when anyone argues our rule is unnatural.
8. **Facts and inferences are structurally separated**, under two headings, not blended into one
   confident paragraph.
9. **Time is stated twice, deliberately**: relative for the reader ("updated <n>h ago", "just now")
   and absolute for the record (snapshot clock, source date). They never substitute for each other.
10. **Register is small-caps utility labels over sentence-case values.** Labels are terse; the prose
    lines are ordinary complete sentences with verbs, not fragments.
11. **Prose is confined to the read band, the empty sentence, and the case document.** No working
    board carries a paragraph; no paragraph is longer than four sentences anywhere I looked.

---

## 6. Mapping proposal — our fourteen Market OS pages into ONE dashboard

The fourteen are the F01 macro-native suite pages (PRs #6836 → #6852), all built on
`templates/_macro_suite_shell.html.j2`, each already carrying its own in-page tabbar
(`role="tablist"` at `:221-234`, panels at `:666-682`).

### 6.1 The tension, stated honestly

Their macro workspace puts fourteen macro chapters on **one page with fourteen anchors** (§1). Our
density law caps a page at **7 L1 sections, default 5**
(`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` §9.3). Both cannot be satisfied by making each of our
fourteen an L1 section. The resolution is that **fourteen tiles are one L1 section**, and the
grouping is the design act. The prior study reached the same conclusion from different evidence;
this brief's contribution is the *chapter-rail* mechanism that makes the one-section version
navigable, and the finding that our fourteen URLs should survive.

### 6.2 The command page — five L1 sections

```
R0  CHROME            existing _site_nav family. NEVER a third header.        [sticky]
R1  CONTEXT BAND      region · market session · one-line newest reading.      [sticky, collapses
                      Collapses on scroll to a single line.                    to 1 line]
────────────────────────────────────────────────────────────────────────────────────────
L1-1  THE ANSWER      stance word (doctrine vocabulary) + ONE plain line.
      + EVIDENCE      Five tiles beneath it, NOT nine: two market/money,
        STRIP         three evidence-quality (freshness · coverage · integrity).
                      Geometry never collapses; each null has its own phrase (§4.1).
L1-2  WHAT CHANGED    ≤ 5 rows, each `from → to` with both dates and the delta.
                      One canonical count, printed once (§9.5 one-integer law).
L1-3  THE FOURTEEN    ONE section. Three labelled groups, 5 / 5 / 4. Group headers
                      carry "n of 5 moved". A sticky group rail of THREE (not
                      fourteen) is the chapter-rail mechanism, scaled to our law.
                      Each tile: state word · one plain line · freshness ·
                      an absence chip when that workspace could not read.
L1-4  WATCHING NEXT   the conditions that would change the answer, forward-tense,
                      each armable. Never falsifier / refuted / 证伪.
L1-5  WHAT WE COULD   named absences — which workspace could not read, and why.
      NOT SEE         Items named, never counted (§4.2).
────────────────────────────────────────────────────────────────────────────────────────
      RIGHT RAIL      1440 only: receipts + diagnostics. Demoted technicals live here.
      (not an L1)     Below 1280 it becomes an end-of-page evidence block (§2.3).
```

### 6.3 The fourteen → tiles

Groups named by **what a person is asking about**, never by data family or producer. Tile labels are
the plain-word question, not the template name.

| Group (sticky rail of 3) | Workspaces | Tile label — EN / ZH |
|---|---|---|
| **A · Money & policy** (5) | `macro_monetary_policy` | Policy setting / 政策取向 |
| | `macro_liquidity_central_banks` | Central-bank cash / 央行流动性 |
| | `macro_liquidity_regime` | Is money easy or tight / 松紧格局 |
| | `macro_rates_curves` | Rates and the curve / 利率与曲线 |
| | `macro_financial_conditions` | How easy it is to borrow / 融资环境 |
| **B · Prices, jobs, activity** (5) | `macro_inflation_system` | Prices / 物价 |
| | `macro_growth_real_economy` | Growth / 增长 |
| | `macro_labor_markets` | Jobs / 就业 |
| | `macro_business_activity` | What businesses are doing / 企业活动 |
| | `macro_consumer_payments` | What households are spending / 居民消费 |
| **C · Balance sheets & flows** (4) | `macro_capital_structure` | Who is borrowing / 融资结构 |
| | `macro_national_debt_liabilities` | Government debt / 政府债务 |
| | `macro_housing_real_estate` | Housing / 房地产 |
| | `macro_trade_flows` | Goods crossing borders / 跨境贸易 |

### 6.4 What each workspace keeps, and what the command page must NOT duplicate

**Keeps its own URL.** All fourteen stay addressable and stay in the sitemap. Their product's
chapters are anchors on one URL, and that is precisely why a chapter there cannot be linked,
crawled or bookmarked on its own. We should not import that cost — we already learned this in the
China subsector case, where a `#hash` was not a distinct URL to an index.

**Opens without a chrome change.** A tile activates its workspace with the header, rail, context
band and scroll position holding still (their sub-tab behaviour, §3). Address updates; chrome does
not blink. This is the half of their model that is pure gain.

**Demoted from the command page to the workspace** (present in full, one level down):

* every chart, heatmap and regime map — the command page carries state words and deltas, no charts;
* per-series provenance strips, windows and frequencies;
* in-module tabs (current / drivers / history / scenario / alerts);
* ranked contributor lists — the command page names at most the single largest mover per group.

**Dropped from the glance tier entirely** (Tier 2 hover or Tier 3 only, per doctrine §1):

* confidence decimals, composite index levels, threshold constants and z-scores;
* internal state enums, study identifiers, and any `n=` / window notation;
* model and version stamps — these belong in the workspace's evidence block, not on the board;
* raw tables. At L1, ≤ 8 rows with a counted "see all N", scrolling in their own container.

**Two things to ADD that we do not currently have**, both lifted as principles:

1. **Distance-to-next-state per tile** — the "nearest threshold" idea (§2.2). A tile that says a
   state *and* how close it is to changing is worth two tiles that say only the state.
2. **The classification rule printed under the state word**, one sentence, at glance. We currently
   put that behind a methodology link, which means nobody reads it.

### 6.5 Mobile 390 — declared reduction

Order: context band collapsed to region + newest reading → stance word + one line → evidence strip as
a **two-row 3+2 grid, never a horizontal scroller** (a scroller hides exactly the null tile you must
not be able to miss) → what changed (5 rows) → the fourteen as three labelled accordions, closed by
default, each header showing "n of 5 moved" → watching next → what we could not see. Answer within
one swipe.

### 6.6 Bilingual

Paired `l-en` / `l-zh` spans as the suite shell already does (`_macro_suite_shell.html.j2:33-35`).
Two ZH risks specific to this page: the stance word must stay one or two characters so the answer
band does not reflow, and ZH change-rows run ~20–30% shorter than EN, so the row grid must be
defined by the **longer** language rather than tuned to EN. No translated text in `title=` (CI-guarded).

---

## 7. Five "do not copy" notes — theirs, must be designed fresh

1. **Their art direction is theirs.** Near-black ground, a single warm gold accent, cool white text,
   hairline separators, letterspaced small-caps utility type. Do not sample a hex, a letterspacing
   value, or the gold-accent-as-only-colour policy. Ours extends `templates/theme.css` and nothing
   else; our brand mark and gradient family are already law in `_navlinks.html.j2`. The *principle*
   we take is "spend the accent on the stance word and one primary action" — not the colour.
2. **Their vocabulary is theirs.** Their state words, module names, verb set, family names, tile
   labels, column headers and empty-state sentences must not appear in our templates, our design
   docs, or a builder packet. Our stance vocabulary already exists and is law: *Act · Get ready ·
   Watch — don't chase · Protect gains · Stand aside · Ignore*. Write every string from that
   vocabulary and our own plain-word table (`docs/DESIGN_DOCTRINE.md` Law 2), never by translating
   theirs.
3. **The case-document layout and its commitment-device copy are theirs.** We take two abstract
   principles — *pre-register the user's own prior before revealing the recommendation*, and *show
   the alternative the recommendation beat* — and design our own composition, our own chip set, and
   our own gate. In particular our version must satisfy our epistemics law (LLM never originates an
   escalation), which theirs is not bound by, so it cannot be a re-skin.
4. **Their register in machine-adjacent states is theirs, and is a defect.** Their bad-route state
   uses routing vocabulary; their board columns expose an internal sleeve slug in a user-facing
   cell; the analyst affordance and some section heads read as system nouns. Our plain-language law
   bans exactly this class. Design our degraded states from our own `.mx-empty` family: loading =
   skeleton at true geometry with no words, empty = a full-weight market-facing sentence with a
   mandatory why, stale = behind-state plus one line, error = names what failed *and* what still
   works, with a retry.
5. **Their evidence apparatus is theirs, and ours must be independently derived.** Their confidence
   grades, evidence-type taxonomy, impact units, weights, path-confidence numbers and promotion
   thresholds are their model's outputs. We do not copy the taxonomy, the thresholds, or the units.
   What transfers is the *shape*: state the rule in plain words, print the denominator decomposition,
   name the third outcome ("not scored") rather than folding it into hit or miss, and name uncovered
   items individually.

**Two anti-patterns not to copy either** (they are theirs, and they are wrong):

* **A headline rate over a tiny denominator.** Their public record surface leads with a single
  hit-rate figure above hundreds of rows on a denominator of one measured case, with the denominator
  set smaller than the claim. Our Law 3 exists to stop precisely this: withhold the headline rather
  than publish a cheerful one — which our alerts board already does.
* **Arithmetically meaningless derived percentages.** The macro workspace's growth heatmap prints
  period-over-period percent changes on series that cross or approach zero, producing values in the
  hundreds and thousands of percent sitting beside honest single-digit rows. A number that cannot be
  true is a wrong number, and a wrong number is a design defect exactly like bad copy. Any heatmap we
  build states its transform and refuses the cell when the transform is undefined.
* **Button-only routing.** The signed-in shell exposed **zero** anchor elements on the command home
  — every destination is a button, so nothing is middle-clickable, copyable, crawlable, or reachable
  by a screen reader's link list. Our estate must keep real `href`s on every destination.

---

## 8. Acceptance checklist — Meta-CEO A can accept a build against this

**A · Information architecture**
- [ ] The command page has **five L1 sections**, and the fourteen workspaces occupy exactly one of
      them (`MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` §9.3: default 5, hard ceiling 7).
- [ ] Group names name the user's question, not a data family or an engine.
- [ ] All fourteen workspaces keep their own URL and stay in the sitemap; a tile opens one without a
      chrome change or a header blink.
- [ ] Chrome is the existing `_site_nav` family. **No third page header exists anywhere in the diff.**
- [ ] Sticky set is declared and minimal: chrome + context band only.

**B · Glance tier**
- [ ] The first content element answers the page's one declared primary question.
- [ ] Every tile carries a stance word from the doctrine vocabulary; none is a state with no stance.
- [ ] Title ≤ 4 words; subtitle ≤ 14; row ≤ 1 line; footer ≤ 1 sentence. Enforced at review.
- [ ] Every Tier-1 number passes all three parts of the Tier-1 statistic test (§9.4).
- [ ] No confidence decimals, composite levels, thresholds, `n=`, study IDs, state enums, model
      versions or raw slugs anywhere at rest on the command page.
- [ ] One as-of per panel; one page-level session stamp; no duplicate timestamps.

**C · Detail and receipts**
- [ ] Each workspace carries one end-of-page evidence block that reads straight through — linkable
      and printable, not hover-only.
- [ ] Fetch time and source date are printed as **two separate fields**, never merged.
- [ ] Where a state is classified, the rule that produced it is printed under it in one plain
      sentence at glance.
- [ ] Every composite number carries a direction gloss.
- [ ] Change rows are `from → to` with both dates and the delta.

**D · Empty, degraded, absent**
- [ ] Four distinct null phrases exist for not-supplied / not-reconciled / not-dated / not-evaluable.
      A bare `—` for an evidence field fails.
- [ ] The evidence strip's geometry does not collapse when empty.
- [ ] Uncovered workspaces are **named individually** in "what we could not see", never counted.
- [ ] Loading is a skeleton at true geometry with no words; empty is a market-facing sentence with a
      mandatory why; error names what failed *and* what still works, with retry. No pipeline
      telemetry in customer copy.
- [ ] Any honest null states its promotion rule in plain words and its denominator decomposition.

**E · Language**
- [ ] Zero occurrences of falsifier / refuted / 证伪 or any verdict-tense refutation on a user cycle
      surface. Conditions are forward-tense and armable.
- [ ] Facts and inferences are structurally separated wherever both appear.
- [ ] No MarketOntology string, label, column header, taxonomy term or empty-state sentence appears
      in the diff. (Grep the diff for their vocabulary before review.)

**F · Theme — both directions, or PARTIAL**
- [ ] The packet states the **dark** treatment and the **light** treatment separately, and names
      which mechanisms intentionally differ (elevation, stance-word emphasis, chart-grid polarity,
      chip fill) and why.
- [ ] Light does not rely on an inverted glow for elevation, and does not carry the stance word by
      luminance.
- [ ] Evidence set complete: **dark/light × EN/ZH × 1440 / 390** = 8 captures. Missing any → PARTIAL,
      never PASS. "Same CSS, tokens swap" is refused as a light design.

**G · Responsive and bilingual**
- [ ] At 390: the answer lands within one swipe; the evidence strip is a 3+2 grid, not a scroller;
      the fourteen are three closed accordions with "n of N moved" headers.
- [ ] Row grids are sized by the longer language; ZH stance word ≤ 2 characters.
- [ ] No horizontal page scroll at any viewport; wide content scrolls inside its own container.
- [ ] No translated text in `title=`.

**H · Repository law**
- [ ] Substantive styling lives in governed CSS, not in a runtime `style.textContent` inside page JS
      (`scripts/check_runtime_style_injection.py`).
- [ ] Every destination is a real `href`.
- [ ] Paired plain-copy assets are byte-synced (`python -m scripts.check_template_site_sync --fix`).
