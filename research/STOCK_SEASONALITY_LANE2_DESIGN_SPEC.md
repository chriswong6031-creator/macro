# Stock Seasonality (Calendar Clock) — Lane 2 design spec

**Status:** PINNED. Authored in the Fable main loop after loading
`docs/DESIGN_DOCTRINE.md` + the `frontend-design:frontend-design` skill, per
CLAUDE.md §Model routing Design lane. A builder implements this **exactly**; the
choice of palette, type, layout, geometry and copy is already made here and is
not a builder decision.

**Parent docket:** `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md`
(Lane 2 — Truthful calendar explorer).

### Revision log — where each contested decision landed

This spec was revised four times while the build lanes ran, each time because a
measurement or a render contradicted it. Where an early section and a later one
disagree, **the later one wins**; the table below is the authority.

| Decision | Current state | Why | Recorded in |
|---|---|---|---|
| Family null | **Independent** circular year-shift | a synchronized shift relocates a real effect instead of removing it | §11 |
| Window grid | 2,645 windows; never wraps the year; leap day folds into Feb 28 | keeps "one year = one observation" clean | §4, §9 |
| Verdict | **Graded**, not pass/fail | after correction nearly every symbol fails; a binary page has one answer forever | §3, §12 |
| Default window | the symbol's **own strongest**, not a preset | so opening a symbol answers something that varies | §9, §12 |
| Chip 4 | **four-state**, incl. `The market's pattern` | most calendar structure is inherited from the market, not name-specific | §3, §12.6 |
| Market-neutral leg | **required**, scanner + its own null run on both panels | it is the discriminator, not a display option | §9, §12.6 |
| Signature | the **window fan** in §5 — *not* lit strands inside the year field | rendered, in-gate lighting is illegible at the year's y-scale | §5, §13 |
| Dot row | **removed** — the fan's end-dot column replaces it | same fact, better picture, one fewer element | §5, §13 |
| Entity storage | **gitignored + R2**, fetched via `DATA_BASE`; default symbol tracked | ~28 MB/night in git otherwise | §9, §14 |
| Page + artifacts | **public** | no forecast, no ranking, and search visibility is the point | §10 |
| Year-cohort filters | **none** (no election / bull-bear presets) | standing kill, and post-hoc cohorts spend unaccounted budget | §11 |

Committed reference renders: `mockups/refs/stock_seasonality/` — `window_fan.html`
is the thing to build; `variants.html` records what failed.

---

## §0 ACCEPTANCE GATES (not done unless)

1. `site/stock_seasonality.html` renders from `templates/stock_seasonality.html.j2`
   and is reachable from the shared nav (`templates/_navlinks.html.j2`, Research ▸
   Find the Edge). No third page-header family is created (CLAUDE.md §Navigation).
2. Dragging the window gate updates every statistic **client-side, exactly**, with
   no network round-trip, from the per-year cumulative arrays in the entity JSON.
3. A dragged (non-preset) window shows the **exploratory** badge; a dragged window
   can never display an evidence tier.
4. The independent year count `n_years` is visible **beside the headline**, always.
5. No score, no rank, no cross-name ordering anywhere on the page.
6. EN/ZH parity: every user-visible string is a `l-en`/`l-zh` pair. No translated
   text in `title=` or `aria-label` (CI-guarded). SVG carries **no** translated
   text — bilingual labels are HTML overlays.
7. `prefers-reduced-motion: reduce` → all elements at final state, no transitions.
   Gate handles are keyboard-operable with a visible focus ring.
8. Mobile (375px) **recomposes** per §7 — it does not horizontally scroll, and the
   years table becomes cards.
9. Light + dark + ZH screenshots of the full page and of the gate-selected state
   are posted in the PR body.
10. Honesty strip (§8) is present and truthful: adjustment vintage, survivorship,
    "no screener yet", and the plain-word null.

---

## §1 The brief, restated

**Subject.** Recurring calendar structure in one instrument's own price history.
**Audience.** Serious traders and analysts; desktop-first; dark default; EN/ZH.
**The page's single job:** answer *"is this instrument's calendar pattern real
enough to act on?"* — and make the honest answer, including "no", legible in five
seconds.

**The competitive thesis.** The incumbent (Seasonax) draws a confident smooth
curve from ~10 annual observations and sells the curve. We sell the *sample*. The
differentiator is one sentence a user can act on: **what your window is worth
after paying for the search that found it.**

---

## §2 Design plan

### Color — 4 named values on top of the house theme

The page adds exactly two tokens; everything else is existing `theme.css`.

| Token | Dark | Light | Role |
|---|---|---|---|
| `--sx-ink` | `#8a7fd4` | `#6a5cc0` | median path, gate rules, gate fill, page accent, section eyebrows |
| `--sx-now` | `var(--warn)` `#e0a030` | same | current (incomplete) year thread + today marker |
| `--up` / `--down` | existing | existing | per-year window outcomes — **auto-flips for ZH 红涨绿跌** |
| `--muted` / `--line` | existing | existing | strands at rest, month rules, axis |

**Why indigo, not turquoise.** Turquoise is the incumbent's identity — avoided for
clean-room optics and for identity. Indigo is the ink of star charts, tide tables
and ephemerides, which is the actual vernacular of "what does this time of year
usually do". It is direction-neutral (so it never competes with the green/red
outcome semantics), it does not collide with `--info` blue (flow), `--warn` amber
(caution) or the China page's plum, and it sits next to the brand gradient's
`#7c5cff` so the page reads as this product rather than a bolt-on.

### Type — no new webfont

Adding a face costs a self-hosted-font 3-file change and China-serving weight
(`theme.css` §fonts). Personality comes from scale, weight and case instead.

| Role | Spec |
|---|---|
| Verdict (display) | `var(--font-ui)` 800, `clamp(21px, 2.5vw, 33px)`, `letter-spacing:-.02em`, `line-height:1.18`, `max-width:34ch` |
| H1 entity | 700, 19px, `letter-spacing:-.01em`; ticker in `var(--font-mono)` 600 at .82em, `var(--muted)` |
| Eyebrow / axis / chip labels | 600, 10.5px, `text-transform:uppercase`, `letter-spacing:.14em`, `var(--muted)` |
| Body / hover copy | 400, 13.5px, `line-height:1.55` |
| **Every figure** | `var(--font-mono)`, `font-variant-numeric: tabular-nums` — house law: mono numerals are for figures, never words |

### Layout concept

One column of decreasing commitment: the answer, then the evidence that produced
it, then the machinery. The chart is not the hero — **the verdict is**, and the
chart is the first proof under it.

```
┌ shared _site_nav ───────────────────────────────────────────────┐
├─────────────────────────────────────────────────────────────────┤
│ CALENDAR CLOCK · 日历时钟                     [symbol search]    │
│ SPDR S&P 500 ETF  SPY                                            │
│                                                                   │
│ Late-summer strength here is really the                          │
│ market's calendar. Watch, don't chase.                           │
│                                                                   │
│ [Aug 3 → Sep 11] [15 years] [9 of 15 up] [The market's pattern]  │
│ [Through Jul 31]                                                  │
├─────────────────────────────────────────────────────────────────┤
│  THE YEAR FIELD — when in the year, and what shape               │
│  J    F    M    A    M    J    J    A    S    O    N    D        │
│  ╎    ╎    ╎    ╎    ╎    ╎    ╎  ┌─────┐ ╎    ╎    ╎    ╎        │
│  ~~~~~~~~~~~~~~ 15 year strands, never dimmed ~~~~~~│▲today      │
│  ━━━━━ median ink ━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━        │
│  ╎    ╎    ╎    ╎    ╎    ╎    ╎  └──╫──┘ ╎    ╎    ╎    ╎        │
│                                   [▮]   [▮]  ← drag handles      │
│  [Median|Mean]  [Raw|Vs market|Detrended]  [10y|15y|25y|Max]     │
├───────────────────────────┬─────────────────────────────────────┤
│ THIS WINDOW               │ THE YEARS                            │
│   +2.1%  typical year     │  2011  +3.14%  ▬▬▬▬▬▬                │
│                           │  2012  −1.02%  ▬▬                    │
│   THE WINDOW FAN ⟵ signature                                     │
│   every year from zero    │  …                                   │
│      ╱╱╱⟋⟋⟋⟋⟋⟋⟋⟋⟋⟋⟋ ●●●●● │                                      │
│   ───────────────────────●●│  ← end-dot column, countable        │
│      ╲╲╲╲⟍⟍⟍⟍⟍⟍⟍⟍⟍⟍⟍ ●●●● │                                      │
│   "We shuffled SPY's history 2,000 times…"  ?                    │
│   ▁▁▂▂▃▃▄▄▅▅▆▆▇▇█ ╎  ← chance track                              │
├───────────────────────────┴─────────────────────────────────────┤
│ BY MONTH · BY WEEKDAY · BY TRADING DAY  (small multiples)        │
├─────────────────────────────────────────────────────────────────┤
│ HOW THIS IS COMPUTED  (honesty strip + methodology.json link)    │
└─────────────────────────────────────────────────────────────────┘
```

### Signature — the year field and the window fan

**Every other seasonality product draws one smooth average curve. We draw all the
threads it was made from, and put the average on top.**

The sample-size illusion (docket §red-team 1) is the incumbent's central defect: a
366-point line implies 366 confirmations when there are ~15. The fix is not a
disclaimer under the chart — it is *drawing the fifteen*. The user does not read
"n=15"; they see fifteen threads, few enough to count, fanning apart wherever the
"pattern" is weak.

The **gate** is the interaction that makes it pay off — but the payoff renders in
the **window fan** (§5), not in the year field. Selecting a window re-anchors
every year to zero at the window's first day and draws them at the window's own
scale, coloured by that year's outcome. "9 of 15 years were up" stops being a
statistic and becomes nine green threads ending above a line and six red below,
in a column you can count. §13 records why this had to be a second picture rather
than lighting inside the first.

**The risk I am taking, and why it is right:** our chart will look noisier than
every competitor's. That noise is the honest magnitude of the uncertainty. A
product that hides the fan is selling false precision, and hiding it is exactly
what we are building against. The median ink still gives the clean read for anyone
who only wants the shape.

**Restraint.** Boldness is spent here and nowhere else. No hero gradient, no
counter animation, no second chart type above the fold, no 10–90 band (the strands
*are* the dispersion — a second band would encode the same fact twice). Everything
around the strand field is house furniture.

---

## §3 Copy (pinned, both languages)

### Verdict sentence — three states, chosen by the engine

| State | EN (≤14 words, ends in a doctrine stance) | ZH |
|---|---|---|
| `own` | `Late-summer strength here is this name's own, not the market's. Get ready.` | `夏末走强源自该股自身，而非大盘。做好准备。` |
| `market` | `Late-summer strength here is really the market's calendar. Watch, don't chase.` | `夏末走强其实来自大盘日历，而非该股。观察，不要追。` |
| `fails` | `Looks strong, but not after counting every window tried. Stand aside.` | `看似强势，但计入所有测试窗口后并不成立。建议观望。` |
| `thin` | `Only 6 years of history — too few to call. Watch, don't chase.` | `仅 6 年历史，样本太少，暂无结论。观察，不要追。` |

The season phrase (`Late-summer strength`) is generated from the selected window's
months and sign, from a fixed lookup table the builder implements (no LLM, no
free text). Table: `Jan–Feb 深冬 / Mar–Apr 早春 / May–Jun 初夏 / Jul–Aug 盛夏 /
Sep–Oct 秋季 / Nov–Dec 年末`, × `strength 走强 / weakness 走弱`.

### Chip strip — exactly five, in this order

| # | EN | ZH | Note |
|---|---|---|---|
| 1 | `Aug 3 → Sep 11` | `8月3日 → 9月11日` | the window; dates only, no jargon |
| 2 | `15 years` | `15 年` | independent sample — **required beside the headline** |
| 3 | `9 of 15 up` | `15 年中 9 年上涨` | agreement |
| 4 | four states, see below | four states, see below | **the differentiator chip** |
| 5 | `Through Jul 31` | `截至 7月31日` | freshness |

**Chip 4 is four-state, not binary** (revised — see §12.6). It reads the
strongest *true* claim available, which requires running the scanner on both the
raw and the market-neutral panel:

| Raw | Vs market | Chip 4 EN | Chip 4 ZH | Tint |
|---|---|---|---|---|
| clears | clears | `Its own pattern` | `该股自身的规律` | `--up` |
| clears | does not | `The market's pattern` | `跟随大盘的规律` | `--info` |
| does not | — | `Doesn't hold up` | `不成立` | `--muted` |
| fewer than 6 years | — | `Not enough years` | `年数不足` | `--muted`, dashed border |

`fails` is `--muted`, **never** `--down`: a failed test is not a bearish signal,
and painting it red would be a lie. `The market's pattern` gets `--info` because
it is a real finding, just not a name-specific one.

**Banned from Tier 1 on this page** (doctrine Law 2, plus this page's own list):
`p-value`, `maxT`, `familywise`, `FDR`, `BY`, `q≤`, `n=`, `t-stat`, `bootstrap`,
`null distribution`, `multiplicity`, `in-sample`, `OOS`, `detrend` as a bare verb,
`significance`, `证伪`, `falsifier`, `refuted`, and the spin words `fade`,
`giveback`, `bounce`, `dead-cat`. Every one of these has a Tier-2 home.

### The after-search line — GRADED, never binary (revised 2026-08-01, see §12)

A main-loop probe on real data showed the pass/fail verdict is `fails` for almost
every symbol. A page whose only possible answer is "no" is a constant, not
information. So the sentence carries the **graded** comparison, and it is the same
sentence in every state — only the number moves:

> EN `We shuffled SPY's history 2,000 times. A window this strong turned up by chance in {pct}% of them.`
> ZH `我们把 SPY 的历史打乱了 2,000 次。像这样强的窗口在其中 {pct}% 里纯属偶然出现。`

Followed by one clause keyed to the state:

| State | EN clause | ZH clause |
|---|---|---|
| `fails` | `— often enough that this one doesn't stand out.` | `——出现得够频繁，因此这一个并不突出。` |
| `holds` | `— rare enough that this one does stand out.` | `——出现得够罕见，因此这一个确实突出。` |

`pct` = `100 × (1 − percentile_of(observed |t|) in the null-max distribution)`,
shipped by the server as `null_max_exceedance_pct`, rounded to a whole number and
floored at 1 (never print `0%` — with B=2,000 the honest floor is "under 1%", so
render `<1%` / `<1%` in that case).

**The chance track.** Directly under the sentence, a 4px-tall, full-width track
renders where chance concentrates and where this window sits: a soft
`--sx-ink` gradient ramp for the null-max distribution and one 2px `--sx-ink` tick
at the observed statistic. No axes, no labels, no numbers — the sentence above
already carries them. This exists because the graded fact is what makes the page
informative on a symbol whose verdict is "doesn't hold up", and a position on a
track is read faster than a percentage.

Tier 2 (`?` help tip on the line, ≤80 words, label: value form):

> `Family: 366 start days × 8 lengths = 2,928 windows on this symbol.`
> `Your window: |t| 2.41. Chance-alone 95th percentile of the best window in the family: |t| 3.06 (2,000 synchronized year-shift resamples).`
> `Method: joint maxT, Westfall–Young style, dependence preserved by shifting whole years.`
> `Unit of evidence: one complete year, not one day.`

### Exploratory badge (dragged windows)

`Your window · exploratory` / `自选窗口 · 探索性`, `--muted` outline chip placed
immediately after chip 1. Tier-2 tip: `A window you chose after seeing the chart
spends testing budget that is not counted here. Presets are counted.`

### Empty / thin / missing states

| Case | EN | ZH |
|---|---|---|
| <6 complete years | `Not enough history to say anything yet.` | `历史数据不足，暂时无法判断。` |
| symbol not in set | `We don't cover that symbol yet.` + `See what we cover →` | `暂未覆盖该代码。` + `查看覆盖范围 →` |
| artifact unreachable | `Seasonality data didn't load. Reload the page.` | `季节性数据未能加载，请重新载入页面。` |

Errors state what happened and what to do; they do not apologise and are never
vague.

---

## §4 The strand field — exact geometry

Root: `<svg class="sxf" viewBox="0 0 960 372" preserveAspectRatio="none"
role="img" aria-label="Seasonal year strands">`, CSS `width:100%;height:320px`
(mobile `height:260px`). **Every** stroked element carries
`vector-effect="non-scaling-stroke"` so x-stretch does not distort line weight.

Plot box: `x ∈ [44, 940]` (896px over 366 day slots → `2.4481 px/day`),
`y ∈ [16, 296]`. Axis band `y ∈ [296, 330]`. Handle rail `y = 330`.

Y scale: linear over `[min(p05_all_years) − pad, max(p95_all_years) + pad]` of the
rebased cumulative paths, `pad = 4%` of range, clamped so `100` is always inside.

**Two pictures, two scales — see §13 for why.** The year field below shows *when
in the year* and the year's shape. It does **not** try to show the window's own
outcomes: the window's signal is roughly an order of magnitude smaller than the
year's range, so at this y-scale it can only ever be a smudge. The countable
per-year outcome lives in the **window fan** (§5), at its own scale.

| Layer (paint order) | Spec |
|---|---|
| 1 · month rules | `x` at each month start; `stroke:var(--line); stroke-opacity:.55; stroke-width:1` |
| 2 · zero baseline | dashed `4 4`, `stroke:var(--line); stroke-opacity:.9` |
| 3 · 20–80 band | `fill:var(--sx-ink); fill-opacity:.12`, no stroke |
| 4 · year strands | one `<path>` per complete year; `fill:none; stroke:currentColor; stroke-opacity:.14; stroke-width:1`. **No dim/undim state** — strands do not change when the gate moves |
| 5 · gate fill | `fill:var(--sx-ink); fill-opacity:.07` between the two rules |
| 6 · median ink | `fill:none; stroke:var(--sx-ink); stroke-width:2.6; stroke-linejoin:round; stroke-linecap:round` |
| 7 · current-year thread | `stroke:var(--sx-now); stroke-opacity:.62; stroke-width:1.3`, drawn only to today |
| 8 · gate rules | `stroke:var(--sx-ink); stroke-width:1; stroke-dasharray:3 3; stroke-opacity:.75` |
| 9 · today rule | `stroke:var(--sx-now); stroke-width:1; stroke-opacity:.55` |

**Strands are capped at 25** and each is downsampled to ≤183 points (every second
calendar day) before serialization. If a lookback would exceed 25 complete years,
keep the 25 most recent and say so in the freshness chip's Tier-2 tip.

### Handles, keyboard, touch

Two handles at `y=330`: visible `rect` 11×22 `rx=3` `fill:var(--sx-ink)`, plus a
transparent 30×40 hit rect (mobile: 44×48). Each is
`role="slider" tabindex="0" aria-label="Window start"` / `"Window end"` (plain EN
only — it is an attribute), with `aria-valuemin/max/now` in day-of-year and
`aria-valuetext` set to the ISO `MM-DD`. `←/→` ±1 day, `Shift+←/→` ±7,
`Home/End` jump to month bounds. Focus ring:
`outline:2px solid var(--sx-ink); outline-offset:2px`. Dragging the band between
the rules translates the whole window. Minimum window 5 days, maximum 120.

### Motion

1. strands fade in, staggered `i*12ms`, 260ms — the fan assembles;
2. 20–80 band veil 420ms at 200ms;
3. median ink draws left→right via `stroke-dasharray` → 0, 900ms
   `cubic-bezier(.33,.62,.26,1)` at 240ms;
4. gate rules + handles fade/slide 240ms at 900ms;
5. chips fade in 200ms staggered `i*40ms` at 300ms.

Re-selection is **not** re-animated (only opacity/lighting transitions at 120ms) —
motion narrates arrival, never interaction.
`@media (prefers-reduced-motion:reduce)` → every rule above collapses to the final
state with `transition:none; animation:none`.

### Rendering split

The template **server-renders** the default view (default symbol, default 15y
lookback, the registered default window) so first paint is honest and indexable,
then `stock_seasonality.js` fetches `seasonalitydata/entities/<SYM>.json` and
takes over all interaction and symbol switching. On fetch failure the SSR view
stays on screen and the error chip from §3 appears — never a blank chart.

Not `lib/illus.py`: this is an interactive Tier-3 study chart with drag and
keyboard selection, which `docs/ILLUSTRATIONS.md` explicitly excludes from ilx
("ilx is NOT for real charting"). It is also not Plotly (banned on dashboards) and
not the trading stack (no candles/crosshair). It is purpose-built SSR SVG in the
ilx *visual* vocabulary: house tokens, draw-on-reveal ink, honest nulls,
theme/ZH-aware via CSS vars, no client chart library.

---

## §5 Below the gate

**This window** (left column, `--panel`, `border-radius:12px`, `padding:18px 20px`):
median return as the display figure (mono, 30px, `--up`/`--down` tinted, sign
always shown), plain label `typical year` / `典型年份` under it.

Then **the window fan — this is the signature**, verified against real data in
`mockups/refs/stock_seasonality/window_fan.html` (committed; open it before
building). Its own `<svg>`, `viewBox="0 0 460 190"`, `max-width:480px`, 10px pad:

- every complete year re-anchored to **zero at the window's first day**, so all
  threads start from one point and the picture's y-scale is the *window's* range
  (`min/max × 1.08`), not the year's;
- one path per year, `fill:none; stroke-width:1.25; stroke-opacity:.5`,
  `--up` if that year's window return > 0 else `--down`;
- the median of the re-anchored threads over the top in `--sx-ink`, 2.2px;
- a dashed `--line` zero rule;
- an **end-dot column** at the right edge, one 2.1px circle per year at its final
  value — this stacks into a countable column of greens above and reds below and
  **replaces the dot row**; do not build both;
- each path carries a `<title>` with `year: ±x.xx%` (plain, no bilingual markup —
  it is inside SVG).

Caption under it, plain: `Each thread is one year, starting from zero on {date}.
{k} of {n} finished above the line.` / `每条线是一年，从 {date} 起算为零。{n} 年中
{k} 年收在零线之上。`

Then the after-search sentence, the chance track, and the `?` tip from §3.

**The years** (right column): a ruled table, `year | return | bar`. Chronological
order only — sorting by return is the flattering-presentation trap and is not
offered. Bars share one scale across all rows (honest magnitude), `--up`/`--down`.
Returns in mono tabular numerals, 2dp, signed. Header row in the eyebrow style.
Max height `320px` with internal `overflow-y:auto` on desktop.

**Small multiples** (full width, three panels): by month (12 bars), by weekday
(5), by trading day of month (≤23). Same bar idiom as the years table, `--up`
/`--down` around a zero rule, month/weekday initials in the axis style. Each panel
gets a one-line plain caption and a `?` tip carrying `mean · median · share up ·
years counted`. On mobile these collapse into a single `<details>` labelled
`More views` / `更多视角`.

**Controls** (a single row under the chart, house `gbtn` pills):
`Median | Mean` · `Raw | Vs market | Detrended` · `10y | 15y | 25y | Max`.
Copy: `Vs market` / `相对大盘` (not "beta-neutral"), `Detrended` / `去趋势` keeps
a `?` tip explaining it in plain words. Each control is a real `<button>` with
`aria-pressed`.

---

## §6 Symbol switching

A single search input in the header (`role="combobox"`, `aria-expanded`,
`aria-controls`) filtering `seasonalitydata/index.json` client-side on ticker and
name. Results list shows `TICKER · Name · N years`; **N years is shown in the
picker** so a user never opens a name expecting depth it does not have. Selecting
updates the URL via `history.replaceState` to `?symbol=XBI` (deep-linkable) and
re-renders from the fetched entity JSON. `Esc` closes, `↑/↓` move, `Enter`
selects. Below the input, a one-row shortcut strip: `SPY · QQQ · XBI · IBB · XLV`.

---

## §7 Mobile (375px) — recompose, never squeeze

1. eyebrow + entity + verdict (verdict clamps to 21px);
2. chip strip wraps to two rows — **no horizontal scroll**;
3. strand field at 260px, handles at 44×48 touch targets, `touch-action:none` on
   the handle rail only so vertical page scroll still works everywhere else;
4. controls become two wrapped rows of pills;
5. **This window** panel, full width;
6. **The years** as cards (`year · return · bar`), 2 per row, not a table;
7. small multiples inside `<details>`;
8. honesty strip last.

---

## §8 Honesty strip — `How this is computed`

Tier-3, always present, plain words, each line with a `?` tip for the technical
form. Non-negotiable content:

- **What a year means here.** `One complete year is one piece of evidence — not one
  trading day. Fifteen years of history is fifteen pieces.` /
  `一个完整年份 = 一条证据，而不是一个交易日。15 年历史 = 15 条证据。`
- **Prices.** `Split- and dividend-adjusted closing prices from our daily vendor
  feed.` Tier-2: `Adjustment is the vendor's current vintage, re-applied to all
  history — it is not a frozen point-in-time adjustment, so a very old year can
  read slightly differently than it did at the time.`
- **Which names.** `We cover N symbols with at least 15 complete years.` Tier-2:
  `The list is built from today's index membership, so names that were delisted or
  acquired are not in it. That makes the covered set look healthier than the real
  historical market. This page never ranks names against each other, so that bias
  does not enter any number on it.`
- **No screener yet.** `We don't rank symbols against each other yet. When we do,
  it will carry its own selection accounting.` /
  `我们暂不对个股互相排名。推出时会附带独立的选择校正。`
- **Windows you drag.** `Presets are counted in the search budget. A window you
  draw after seeing the chart is not — it's marked exploratory.`
- Link: `Full method (JSON) →` `seasonalitydata/methodology.json`.

The word `validated` must not appear (CI-guarded,
`scripts/check_validated_claims.py`).

---

## §9 Entity artifact contract (the page's only input)

`site/seasonalitydata/entities/<SYMBOL>.json`:

```json
{
  "schema": "biopharma_seasonality.entity.v1",
  "symbol": "SPY",
  "name": "SPDR S&P 500 ETF Trust",
  "asof": "2026-07-31",
  "generated_at": "2026-08-02T04:10:00Z",
  "price_source": {
    "vendor": "yahoo",
    "adjustment": "vendor_current_vintage",
    "is_pit_adjustment": false,
    "field": "close_adjusted"
  },
  "coverage": {
    "n_years_complete": 15,
    "first_year": 2011,
    "last_complete_year": 2025,
    "n_years_available": 32,
    "years_capped_at": 25,
    "complete_year_rule": "first session <= Jan 10 and last session >= Dec 20",
    "missing_session_policy": "non_trading_days_carry_zero_log_return",
    "leap_policy": "02-29_log_return_added_into_02-28_slot"
  },
  "calendar": { "basis": "calendar_day", "n_slots": 365, "labels": ["01-01", "…", "12-31"] },
  "years": [
    { "year": 2011, "cum": [0.0, 0.0031, "…366 values, log-cum, 5dp"] }
  ],
  "current_year": { "year": 2026, "last_index": 211, "cum": ["…"] },
  "aggregate": { "median": ["…366"], "p20": ["…"], "p80": ["…"], "mean_log": ["…"] },
  "views": {
    "month":  [{ "k": 1, "mean": 0.0, "median": 0.0, "up_share": 0.0, "n": 15 }],
    "weekday": [{ "k": 0, "…": "…" }],
    "trading_day_of_month": [{ "k": 1, "…": "…" }]
  },
  "family": {
    "n_candidates": 2645,
    "start_days": "1..365, restricted so start + horizon <= 365 (windows never wrap the year)",
    "horizons_days": [5, 10, 15, 20, 30, 45, 60, 90],
    "statistic": "abs_t_of_mean_window_log_return_across_years",
    "null": {
      "method": "independent_circular_year_shift",
      "B": 2000,
      "max_abs_t_quantiles": { "0.90": 2.81, "0.95": 3.06, "0.99": 3.55 }
    }
  },
  "default_window": {
    "start_doy": 215, "end_doy": 254, "source": "symbol_best",
    "abs_t": 5.9, "null_max_exceedance_pct": 9.0,
    "state": "market",
    "raw_clears": true, "neutral_clears": false,
    "stability": {
      "shifts_days": [-5, -2, 2, 5],
      "abs_t": [4.1, 5.4, 5.6, 3.9],
      "sign_stable": true,
      "survives": true
    }
  },
  "neutral": {
    "market": {
      "benchmark": "SPY",
      "beta_source": "pit_trailing_252d_shifted_one_session",
      "years": ["…same shape as years"],
      "family": { "…": "same shape as the raw family block, incl. its own null" }
    }
  }
}
```

`site/seasonalitydata/index.json`:

```json
{
  "schema": "biopharma_seasonality.index.v1",
  "as_of": "2026-08-01",
  "default_symbol": "SPY",
  "n_entities": 0,
  "entities": [
    { "symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "group": "index",
      "sector": "Index", "n_years": 32, "first_year": 1994 }
  ]
}
```

### Storage and fetch path (revised — see §14)

Per-entity payloads are ~100 KB each once the market-neutral panel is included;
at ~256 symbols that is ~28 MB rewritten nightly, which git must not carry. They
follow the repo's established idiom for heavy per-ticker artifacts (the Odds
Desk — `site/odds.js`, the `site/oddsmatrix/` block in `.gitignore`):

| Artifact | Storage |
|---|---|
| `seasonalitydata/methodology.json` | git-tracked |
| `seasonalitydata/index.json` | git-tracked (small) |
| `seasonalitydata/entities/<SYM>.json` | **gitignored + R2**, via `publish_r2 --dirs seasonality_entities` |
| `seasonalitydata/entities/<default>.json` | git-tracked as a `.gitignore` negation, so SSR first paint and search indexing have real data |

The page therefore fetches entities from
`(window.DATA_BASE || '') + 'seasonalitydata/entities/<SYM>.json'`, and only
`index.json` + the one tracked default entity need a Caddy public entry alongside
the existing methodology path. A cross-origin fetch has more failure modes than a
same-origin one (CORS, `DATA_BASE` unset in a local render, R2 not yet populated
for a new symbol), so failure is a first-class state: on initial load the SSR view
stays with the §3 error copy; on a symbol switch the previously loaded symbol
stays on screen. Never a blank chart, never a fabricated one.

### What the client computes, and what it must not

The client computes **exactly**, for any window `[a, b]`, from `years[].cum`:
per-year window log return `cum[b] − cum[a]`, then mean, median, share up,
standard deviation, and `|t| = |mean| / (sd / sqrt(n))`. It renders `holds` when
`|t| ≥ max_abs_t_quantiles["0.95"]`, `fails` when below, and `thin` when
`n_years_complete < 6`.

The client must **not** compute a null distribution, invent a p-value, or display
any number the server did not either ship or make exactly derivable by the formula
above. If `family.null` is absent, chip 4 reads `Not enough years` and the
after-search sentence is replaced by
`We haven't finished the search accounting for this symbol yet.` /
`该代码的搜索校正尚未完成。`

---

## §10 Files

| File | Change |
|---|---|
| `templates/stock_seasonality.html.j2` | new page |
| `templates/stock_seasonality.css` + `site/stock_seasonality.css` | new, **byte-paired** (`python -m scripts.check_template_site_sync --fix`) |
| `templates/stock_seasonality.js` + `site/stock_seasonality.js` | new, byte-paired |
| `templates/_navlinks.html.j2` | one entry, Research ▸ Find the Edge |
| build script | renders the page; registered in the render lane |
| `tests/test_stock_seasonality_page.py` | new |

Nav entry copy: `Stock Seasonality` / `个股季节性`, desc
`Which calendar windows actually repeat` / `哪些日历窗口真的会重演`.
It links `stock_seasonality.html`. The existing `seasonality.html` (Ken French
factor climate) is **untouched** — different page, different job.

New public assets are a three-file change and the site-assets serving posture is
default-DENY on two prefixes: the CSS/JS must be added to the served allowlist in
the same PR, exactly as the last new asset did.

---

## §11 Standing constraints this page is designed around

**The null, stated precisely.** The family null is **independent** circular
year-shift: each year's daily log-return series is rolled by its own random
offset, which destroys calendar alignment both within and across years while
preserving each year's return distribution and short-horizon autocorrelation.
A *synchronized* shift (one offset for all years) would be the wrong null here —
it relocates a real seasonal effect rather than removing it, so the null maximum
would inherit the very structure the test is meant to price. Dependence *between
hypotheses* is preserved the way Westfall–Young requires: every resample
recomputes the entire window grid and only then takes the maximum.

**No election-year or presidential-cycle cohort filter.** The incumbent ships
these as year-filter presets. `research/DO_NOT_REBUILD.md` carries
`Election / midterm cycle as standalone signal — REFUTED — survives only as a
US-only Risk-Radar modulator`. Building the preset would re-propose a killed
topic and hand users a filter our own research says is empty. Bull/bear year
cohorts are also **not** offered: choosing a favourable cohort after seeing the
chart spends testing budget the family accounting does not know about, which is
the exact defect §3's after-search line exists to expose.

**No risk-channel wiring.** `DO_NOT_REBUILD.md` forbids calendar/event-window
gated risk-radar legs ("laundered pre-event conviction dampener; event/OPEX
windows are display context only"). Nothing on this page feeds a risk channel,
a gross-exposure state, or Prophet. It is display tier reading its own artifact.

**Neural Web.** The birth authority for this program is fixed in code at
`tier=shadow`, `is_context_only=true` (`engine/seasonality/contracts.py`, all
authority booleans fail closed). This page emits no Neural Web state at all in
this tranche; it renders an artifact.

**Live collision.** PR #4227 (`claude/biocatalyst-b1b-*`, the BioCatalyst B1b
lane) is open and edits `config/site_access.yml` and `app/deploy/Caddyfile` —
the same two files this work must touch for its serving boundary. Expect a
textual conflict there and rebase on `origin/main` before merging; do not edit
any `biocatalyst.*` file, `engine/biocatalyst/`, `collectors/biocatalyst/`,
`contracts/biocatalyst/`, or `config/biocatalyst_*.yml` — that program is owned
by another session.

---

## §12 What a real-data probe changed (main loop, 2026-08-01)

Before the builders shipped, the main loop independently implemented this spec's
math over `data/yahoo/` to check that the product thesis survives contact with
real prices. Three results, each of which moved a design decision:

**1 · The null is correctly calibrated.** Fed 40 pure-noise panels (15 years ×
365 slots, iid), the test fired 2/40 = **5.0%** — exactly nominal for a 95%
familywise threshold. The correction is real, not decorative.

**2 · The uncorrected test over-fires massively, which is the incumbent's
defect, quantified.** On real symbols, **6–17% of the 2,645 windows** clear a
naive |t| ≥ 1.96. A product that ranks by in-sample return therefore has
hundreds of "significant" windows per symbol to choose its headline from. After
the family correction, essentially none survive: SPY 2 of 2,645, and XBI, IBB,
XLV, LLY, AMGN, QQQ, XLE **zero**.

| symbol | complete yrs | max abs t | null 95th | verdict |
|---|---:|---:|---:|---|
| SPY | 25 | 7.25 | 6.52 | holds |
| XBI | 19 | 5.90 | 6.27 | fails (close) |
| QQQ | 25 | 5.10 | 6.03 | fails |
| XLV | 25 | 5.15 | 6.53 | fails |
| LLY | 25 | 4.57 | 5.23 | fails |
| AMGN | 25 | 4.31 | 5.12 | fails |
| IBB | 24 | 4.52 | 5.70 | fails |
| XLE | 25 | 4.77 | 5.17 | fails |

Note the null threshold itself varies from 5.12 to 6.53 across symbols — the
correction is adapting to each symbol's own autocorrelation and volatility
structure, which is the whole reason it is computed per symbol rather than
assumed.

**3 · Therefore the verdict must be graded, and the default window must be the
symbol's own best.** A binary pass/fail reads "no" on essentially every symbol; a
user learns nothing and leaves after three lookups. Two changes:

- **Default window = the symbol's own strongest window** (`source: "symbol_best"`),
  not a fixed preset. Opening a symbol then answers a question that genuinely
  varies: *what is the strongest calendar structure in this name, and does it
  beat chance here?*
- **The after-search line is graded** (§3): the same sentence every time with a
  moving number, so XBI's "9% of shuffles" is visibly different from a name's
  "61% of shuffles" even though both verdicts read `Doesn't hold up`.

**4 · Coverage is larger than assumed.** Of 726 symbols in `data/yahoo/`, **256
clear ≥15 complete years** (297 clear ≥10, 157 clear ≥25). The store is bimodal —
267 symbols have exactly 2 complete years because they were added recently — so
the universe must be built by **measuring** complete years, never by hand-listing
tickers that look established. `GILD` and `BIIB`, for instance, have too little
history in this store despite being decades-old companies.

**5 · The null can be cached for a year.** It depends only on the complete-year
panel, which changes once per calendar year. Recompute `family.null` only when
`coverage.last_complete_year` advances; otherwise reuse it. This is what makes a
256-symbol nightly affordable — without it, B=2,000 resamples × 2,645 windows ×
256 symbols is a 15–35 minute job every single night for a result that is
identical 364 days out of 365.

### §12.6 The finding that gave the page its best feature

A second probe asked whether the corrected test fires more often on real symbols
than on noise, across a random sample of 59–60 eligible names (B=400):

| Panel | Symbols firing | Rate | vs chance |
|---|---:|---:|---:|
| Raw | 10 / 59 | **16.9%** | 3.4× |
| Market-neutral residual | 6 / 59 | **10.2%** | 2.0× |
| Pure noise (control) | 2 / 40 | 5.0% | 1.0× |

Two things follow, and both are load-bearing.

**There is real calendar structure in the cross-section.** Firing at 3.4× the
chance rate is not an artifact of a broken null — the same null returns exactly
5.0% on noise. So the page will not be a constant "no", and it should not be
built as though it will.

**Most of it is the market's calendar, not the name's.** Removing a
point-in-time trailing-beta market leg drops the fire rate from 16.9% to 10.2%.
Six of the ten firing symbols (`AEIS`, `EMB`, `EWS`, `EZA`, `SOXX`, `VGK` —
mostly sector and international ETFs) fire **raw only**: their "seasonality" is
inherited. Four (`CL`, `FMBM`, `MU`, `ZW_F`) fire in **both**: they carry calendar
structure of their own.

This is what makes `Raw | Vs market | Detrended` (§5) the most important control
on the page rather than a cosmetic option, and it is why chip 4 is four-state
(§3). A user who sees "this stock is strong every August" and acts on it, when
the truth is "August is strong for everything and this stock has a beta of 1.1",
has learned nothing and taken a position for the wrong reason. Naming that
difference on the glance tier is the single most useful thing this page does, and
no incumbent surfaces it.

**Across-symbol multiplicity is disclosed, not corrected away.** Browsing N
symbols runs N familywise tests, so ~5% fire by chance regardless. A naive
Benjamini–Yekutieli across the 59 per-symbol p-values leaves **zero** survivors
(smallest `q_BY` ≈ 0.47) — but BY treats 59 heavily correlated equity symbols as
59 independent hypotheses, so it is far too conservative here and must not be
presented as the verdict. The honest handling is the honesty strip (§8): state
the program-level fire rate against the 5% chance expectation and let the
per-symbol page make the per-symbol claim. **Compute those rates over the real
universe at B=2,000 and ship them — never hardcode the probe numbers above,
which came from a 59-symbol sample at B=400 and are indicative only.**

---

## §13 What building the mockup changed (main loop, 2026-08-01)

The design was rendered from real SPY data before any builder shipped it, because
a geometry spec is not evidence that a picture works. Three renders are committed
under `mockups/refs/stock_seasonality/` — **open them before building**:

| File | What it shows |
|---|---|
| `strand_field.html` | the first full-page render (superseded, kept as the record) |
| `variants.html` | four strand treatments compared side by side |
| `window_fan.html` | **the resolution — build this** |

**What failed.** The original §4 lit the in-window strand segments inside the year
field, on the assumption that a user could count them. Rendered, they could not:
cumulative-from-Jan-1 paths converge to a single point in January and tangle by
December, so the field reads as a haze rather than fifteen threads. Re-anchoring
the lit segments to a common origin *inside* the gate (the "lens" variant) fixed
the origin but not the scale — a window's returns span a few percent while the
year spans tens of percent, so the fan collapsed into a coloured smudge roughly a
tenth of the plot's height.

**The diagnosis.** One y-scale cannot serve both jobs. The year's shape and the
window's outcomes differ by about an order of magnitude, and any single chart that
tries to carry both will render one of them illegibly.

**The resolution — two pictures, each at its own scale.**

- **The year field** (§4) answers *when in the year, and what shape*. It keeps
  every strand in place at full-year scale, marks the window with the gate, and
  drops the in-gate lighting entirely.
- **The window fan** (§5) answers *how much, how consistently, and how many*. Its
  y-scale is the window's own range, so fifteen threads diverge visibly from one
  origin and their end dots stack into a countable column.

This is a net *removal*: the year field loses the lit-segment layer and its
dim/undim state machine, and the separate dot row disappears into the fan's end
dots. Two elements out, one in — and the one that remains is the one that actually
delivers the thesis.

**Also corrected by looking:** strand opacity `.13` was too faint at full page
width (raised to `.14` with no dim state), the 20–80 band was invisible under the
strands (`.08` → `.12`), and the current-year thread at `1.75px / .9` dominated
the median ink it is supposed to sit beneath (now `1.3px / .62`).

---

## §14 Storage arithmetic (main loop, 2026-08-01)

The contract in §9 ships, per symbol, up to 25 years × 365 daily cumulative
values — and §12.6 doubled that by adding the market-neutral panel with its own
family and null. Quantized to integers in 1e-5 units that is roughly **100 KB per
entity**, and across ~256 covered symbols roughly **28 MB rewritten every night**.

Committing that to git would be a slow-motion repository failure: near-zero delta
compression (every value changes when the vendor re-adjusts), a nightly commit
larger than most of the site, and a VPS pull that grows without bound.

The repo already solved this. The Odds Desk ships heavy per-ticker JSON
gitignored and R2-published, fetched client-side through `DATA_BASE`, while its
small catalog stays git-tracked — see `scripts/publish_r2.py` `DEFAULT_DIRS`, the
`site/oddsmatrix/` block in `.gitignore`, and the fetch in `site/odds.js`. This
program adopts that idiom unchanged, with one addition: the **default symbol's
entity file stays git-tracked** via a `.gitignore` negation, because a page whose
first paint depends on a cross-origin fetch has no honest server-rendered state
and nothing for a search engine to index — and search visibility is most of the
reason this page is public at all (§10, §8).

A useful side effect: R2-served files never pass through Caddy, so the
default-deny public allowlist needs only `index.json` and that one default entity
beside the existing methodology entry. No broad prefix, and the existing
`test_methodology_manifest_is_in_reviewed_public_boundary` assertion stands
untouched.

---

## §15 The short-window artifact, and the one check that catches it

A plausibility probe over the winning windows found two things.

**The statistic finds real seasons.** The best window for SPY, QQQ and XLK is all
three times `Oct 12 → Dec 11` (60 days, 88% / 80% / 84% of years up) — the
canonical Q4 rally. XLV and LLY land on the same late-year stretch, XLE on the
spring energy window. These are recognised seasonal periods, arrived at from
price alone. The scanner is not producing noise.

**But short windows dominate the winners.** Across 60 sampled symbols, the
horizon of the best window was:

| horizon | 5d | 10d | 15d | 20d | 30d | 45d | 60d | 90d |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| winners | **23** | 8 | 5 | 7 | 3 | 4 | 9 | 1 |

and some of those are transparently not seasons: `MU May 23 → May 28` at +4.7%
mean over five calendar days, `IBB Nov 21 → Nov 26` (Thanksgiving week). A five-
day calendar window that recurs is usually pinned to a **recurring corporate
event** — an earnings date, an expiry, an index rebalance — not to the season.
That is real structure, but it is a different claim, and the docket's own kill
list forbids an effect that "depends on one issuer/year/cluster".

### The discriminator: neighbouring-window stability

A genuine seasonal survives being nudged; a date artifact does not. The docket
already requires this in Lanes 2 and 4 ("start/end perturbation ±2 and ±5 trading
days", "survives neighbouring windows") — this spec omitted it, which was a gap.

**Backend:** for the default window and every registered panel window, recompute
`|t|` with the whole window shifted by −5, −2, +2, +5 days and ship the
`stability` block in §9. `survives` is true when the sign is unchanged at all four
shifts **and** the median shifted `|t|` is at least 60% of the unshifted `|t|`.

**Frontend:** one plain sentence in the **This window** panel, right after the
after-search line:

| | EN | ZH |
|---|---|---|
| `survives` | `Nudging the window a few days either way keeps this.` | `把窗口前后挪几天，这个规律仍然成立。` |
| not | `Nudging the window a few days either way loses it — this looks like a recurring date, not a season.` | `把窗口前后挪几天就消失了——这更像是一个固定日期，而不是季节性规律。` |

No new chip, no new furniture, no jargon — one sentence that changes what a reader
does. It is the cheapest honest defence against the largest remaining failure mode
on this page, and the incumbent ships nothing like it.
