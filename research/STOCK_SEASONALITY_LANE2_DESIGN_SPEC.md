# Stock Seasonality (Calendar Clock) — Lane 2 design spec

**Status:** PINNED. Authored in the Fable main loop after loading
`docs/DESIGN_DOCTRINE.md` + the `frontend-design:frontend-design` skill, per
CLAUDE.md §Model routing Design lane. A builder implements this **exactly**; the
choice of palette, type, layout, geometry and copy is already made here and is
not a builder decision.

**Parent docket:** `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md`
(Lane 2 — Truthful calendar explorer).

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
│ Looks strong, but not after counting every                       │
│ window tried. Stand aside.                                       │
│                                                                   │
│ [Aug 3 → Sep 11] [15 years] [9 of 15 up] [doesn't hold up] [thru │
│                                                       Jul 31]     │
├─────────────────────────────────────────────────────────────────┤
│  J    F    M    A    M    J    J    A    S    O    N    D        │
│  ╎    ╎    ╎    ╎    ╎    ╎    ╎  ┌─────┐ ╎    ╎    ╎    ╎        │
│  ~~~~~~~~~~~~~~~~ 15 faint year strands ~~~~~~│▲today            │
│  ━━━━━ median ink ━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━        │
│  ╎    ╎    ╎    ╎    ╎    ╎    ╎  └──╫──┘ ╎    ╎    ╎    ╎        │
│                                   [▮]   [▮]  ← drag handles      │
│  [Median|Mean]  [Raw|Vs market|Detrended]  [10y|15y|25y|Max]     │
├───────────────────────────┬─────────────────────────────────────┤
│ THIS WINDOW               │ THE YEARS                            │
│   +2.1%  typical year     │  2011  +3.14%  ▬▬▬▬▬▬                │
│   ●●●○●●●●○●●○●●  9 of 15 │  2012  −1.02%  ▬▬                    │
│   ⓘ doesn't hold up …  ?  │  …                                   │
├───────────────────────────┴─────────────────────────────────────┤
│ BY MONTH · BY WEEKDAY · BY TRADING DAY  (small multiples)        │
├─────────────────────────────────────────────────────────────────┤
│ HOW THIS IS COMPUTED  (honesty strip + methodology.json link)    │
└─────────────────────────────────────────────────────────────────┘
```

### Signature — the strand field and its gate

**Every other seasonality product draws one smooth average curve. We draw all the
threads it was made from, and put the average on top.**

The sample-size illusion (docket §red-team 1) is the incumbent's central defect: a
366-point line implies 366 confirmations when there are ~15. The fix is not a
disclaimer under the chart — it is *drawing the fifteen*. The user does not read
"n=15"; they see fifteen threads, few enough to count, fanning apart wherever the
"pattern" is weak.

The **gate** is the interaction that makes it pay off. When a window is selected,
the strands outside it fall away to near-nothing, and inside it each strand
re-lights by *its own* outcome — warm if that year ended the window up, cool if
down. "9 of 15 years were up" stops being a statistic and becomes nine lit
threads you can count against six dark ones.

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
| `holds` | `Late-summer strength holds up after counting every window tried. Get ready.` | `夏末走强，在计入所有测试窗口后依然成立。做好准备。` |
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
| 4 | `Doesn't hold up` / `Holds up` / `Not enough years` | `不成立` / `成立` / `年数不足` | **the differentiator chip** |
| 5 | `Through Jul 31` | `截至 7月31日` | freshness |

Chip 4 tints: `holds` → `--up` tint; `fails` → `--muted` (**not** `--down`; a
failed test is not a bearish signal, and painting it red would be a lie);
`thin` → `--muted` with a dashed border.

**Banned from Tier 1 on this page** (doctrine Law 2, plus this page's own list):
`p-value`, `maxT`, `familywise`, `FDR`, `BY`, `q≤`, `n=`, `t-stat`, `bootstrap`,
`null distribution`, `multiplicity`, `in-sample`, `OOS`, `detrend` as a bare verb,
`significance`, `证伪`, `falsifier`, `refuted`, and the spin words `fade`,
`giveback`, `bounce`, `dead-cat`. Every one of these has a Tier-2 home.

### The after-search line (Tier 1 sentence + Tier 2 receipt)

Tier 1, under the dot row:

> EN `Across every start date and length we tried on SPY, a run this good shows up by chance often enough that this one doesn't stand out.`
> ZH `在 SPY 上尝试过的所有起点与长度中，这种表现纯属偶然出现的频率已经足够高，因此这一个并不突出。`

`holds` variant:

> EN `Even after counting every start date and length we tried on SPY, a run this good is rare by chance.`
> ZH `即使计入在 SPY 上尝试过的所有起点与长度，这种表现纯属偶然也很罕见。`

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

| Layer (paint order) | Spec |
|---|---|
| 1 · month rules | `x` at each month start; `stroke:var(--line); stroke-opacity:.55; stroke-width:1` |
| 2 · 100 baseline | dashed `4 4`, `stroke:var(--line); stroke-opacity:.9` |
| 3 · 20–80 band | `fill:var(--sx-ink); fill-opacity:.08`, no stroke |
| 4 · year strands | one `<path>` per complete year; `fill:none; stroke:currentColor; stroke-opacity:.13; stroke-width:1` |
| 5 · gate fill | `fill:var(--sx-ink); fill-opacity:.07` between the two rules |
| 6 · lit strand segments | per year, the in-window sub-path only; `stroke:var(--up)` if that year's window return > 0 else `var(--down)`; `stroke-opacity:.55; stroke-width:1.4` |
| 7 · median ink | `fill:none; stroke:var(--sx-ink); stroke-width:2.6; stroke-linejoin:round; stroke-linecap:round` |
| 8 · current-year thread | `stroke:var(--sx-now); stroke-opacity:.9; stroke-width:1.75`, drawn only to today |
| 9 · gate rules | `stroke:var(--sx-ink); stroke-width:1; stroke-dasharray:3 3; stroke-opacity:.75` |
| 10 · today rule | `stroke:var(--sx-now); stroke-width:1; stroke-opacity:.55` |

When the gate is active, layer-4 strands drop to `stroke-opacity:.055`.

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
always shown), plain label `typical year` / `典型年份` under it. Then the **dot
row**: one dot per year in chronological order, 9px, filled `--up`/`--down`,
current year hollow with a `--sx-now` ring; the row is the same fact as the lit
strands, restated where the eye lands after reading the figure. Then the
after-search sentence + `?` tip from §3.

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
  "default_window": { "start_doy": 215, "end_doy": 254, "source": "registered" },
  "neutral": {
    "market": { "benchmark": "SPY", "beta_source": "pit_trailing_252d", "years": ["…same shape as years"] }
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
