# XPV2-SC-R3B — Sector Central R3 Design System Spec

**Wave:** `XPV2-SC-R3B` · **Seat:** Principal Design Lead (ROUTE design)
**Binds:** lanes **D1** (Overview + Confluence), **D2** (Map + Moving), **D3** (Money + Explore), and the QA responsive/a11y attack lane.
**Executable proof:** `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/shell_specimen.html`
**Evidence:** `./lead_crops/` (15 captures, §14)

**Precedence.** `docs/DESIGN_DOCTRINE.md` (content law) > `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` (visual/composition law) > this spec (workspace law) > the shell specimen (worked example). Nothing here forks a token root, mints a font stack, or invents a parallel design language. Where this spec adds a value, it is a **derivation of a theme.css token** or a value already shipped by production Sector Central, and it says so.

**Scope.** The global system: page grammar, typography, geometry, colour/surface, authority weight, view navigation, component vocabulary, density, EN/ZH, responsive, light/dark. It does **not** compose the six views — that is the lanes' work, §13.

---

## 0. The design thesis — Quiet Conviction, made structural

The R2 candidate was blocked because *every view looked like an action board*. A label saying "context only" does not fix that; a reader absorbs weight before words. So authority tier here is **spatial and reserved at token level**, not annotated:

1. **The State Ledge is the tier signal.** Overview and Confluence open with a five-cell graded board directly under the answer. The four context views have **nothing in that slot** — the answer flows straight into the dominant object. Presence/absence of the ledge is read pre-linguistically, in one glance, at every width.
2. **Colour is rationed by tier.** Solid `--fill-*` chips, state ink above `--fs-sm`, and the 3px state rail are **reserved to Action views**. A context view is achromatic apart from signed directional numbers at ≤12.5px.
3. **Names outrank verdicts on context views.** The heaviest ink on Map/Moving/Money/Explore is the *name of the object*, never a state word. Full-name emphasis is a north-star requirement and this is where it is spent.
4. **The Answer Thread.** A 3px `--r3-thread` left rail marks exactly two things on the whole product — the active rail item and the view answer. It is wayfinding, identical on all six views, and it rhymes navigation with content. Lineage: production already draws it on `.si-view-read` (`sector_central.html.j2:1162`); R3 completes the idea rather than inventing one.

**The one deliberate risk, and its justification.** In a dense institutional table, convention compresses names and protects numbers. This system inverts it: **a primary name never ellipsizes — it wraps; numbers are what compress.** `overflow-wrap:anywhere` on `.r3-name`, no `text-overflow` anywhere on a primary name. Cost: taller rows. Return: "Semiconductors & Semiconductor Equipment" is legible at 320px in both languages, which is the whole point of "stronger names".

---

## 1. Type

One family. `--font-ui` (San Francisco leads, Inter is the self-hosted carrier). `--font-mono` for figures, tickers, timestamps, axis ticks — **never for words**. No second face, no Google Fonts. Institutional signature = weight contrast + tabular numerals, per master design system §1.

The shipped 11-step ramp is the whole ramp. **No new size is minted.**

| Role | Token / px | Weight | Tracking | Notes |
|---|---|---|---|---|
| View answer line | `--fs-num-lg` **22px** | 500 | −.01em | ≤62ch EN · ≤34em ZH · line-height 1.36 (ZH 1.55) |
| Page h1 (chrome) | `--fs-md` **15px** | 800 | +.02em, caps | one h1 per document; ≤767px → `--fs-body` |
| Panel title h2 | `--fs-h2` **17px** | 700 | −.01em | |
| View-name h2 (eyebrow-styled) | `--fs-label` **11px** | 700 | +.09em, caps | the sanctioned `h2.band-label` idiom |
| Section eyebrow | `--fs-label` **11px** | 600 | +.08em, caps | `--muted` |
| Primary name (row/watch/rail) | `--fs-md` **15px** | 700 | −.008em | **never ellipsized** |
| Figure in a row | `--fs-md` **15px** | 700 | −.01em | `.tnum`, right-aligned |
| Ledge state name | `--fs-label` **11px** | 700 | +.055em, caps | wraps to 2 lines, never clipped |
| Ledge count | `--fs-num-lg` **22px** | 800 | −.02em | `.tnum`; ≤767px → `--fs-md` |
| Body / clause | `--fs-body` **14px** / `--fs-sm` **12.5px** | 400–600 | 0 | reason clauses at 12.5 `--muted` |
| Column legend, tag, table head | `--fs-micro` **10px** | 600–700 | +.05–.08em, caps | |
| As-of / provenance | `--fs-micro` **10px** | 400 | +.05em | `--font-mono`, `.tnum` |

Mobile answer step-down: 22 → **19px** (≤767) → **17.5px** (≤359). Those are the only responsive type changes in the system; everything else holds its size and reflows instead.

**The `--fs-display` 46px verdict word is NOT used on this workspace.** Sector Central has six answers, not one verdict; a 46px word on view 1 would make views 2–6 look broken. Recorded as a deliberate divergence from archetype-D practice.

---

## 2. Space, geometry, elevation

**Spacing** = the promoted step scale, no off-scale layout gaps:
`--sp-1:4 --sp-2:8 --sp-3:12 --sp-4:16 --sp-5:20 --sp-6:24 --sp-7:32 --sp-8:44`; `--gap-grid:18px` for grids; panel padding `16px 18px` (named legacy constant).

**Skeleton**

| Element | Value |
|---|---|
| `.si-shell` | `max-width:1440px`, `grid-template-columns: var(--si-rail-w,200px) minmax(0,1fr)` |
| `--si-rail-w` | **200px** (production value, unchanged) · **172px** ≤1100px · grid switcher ≤767px |
| `.si-stage` padding | `24px 32px 44px 24px` · `20px` all round ≤1100 · `20px 16px 44px` ≤767 · `16px 12px 32px` ≤359 |
| L1 section gap | **32px** action tier · **44px** context tier |
| Answer → first section | **24px** action · **32px** context |
| Row min-height | **58px** desktop · **64px** ≤640 |
| Ledge cell min-height | **82px** desktop · **56px** ≤767 |

**Radius** — the five stops only: `--r-ctl:8` (chips/inputs/tags) · `--r-btn:10` (buttons, read slot) · `--r-card:12` (nested cards, disclosure) · `--r-panel:14` (panels, board, list) · `--r-pill:999` (chips). Rail items keep production's 9px.

**Elevation** — nesting depth ≤2, per master §2.2. `--bg` canvas → `--panel` E1 (board, list, panel, rail) → `--panel2` E2 (selected ledge cell, row hover, tile) → glass E3 (LENS popovers only). **Nothing nests inside `--panel2`.** Dark builds depth by luminance; light builds it by **surface + hairline**, never by heavier shadow — see §4.

**Motion** — `--t-fast .16s` state, `--t-med .2s` lift, easings `--ease-std` / `--ease-lift`. Rules: tabs and toggles never move; hover lift only on clickable containers; **zero breathing/pulse elements on this workspace** (nothing here is live-ticking); `prefers-reduced-motion` kills all of it by name, pseudos included.

---

## 3. Colour + surface

Tokens are a **verbatim mirror** of `templates/theme.css` — `:root`, `html[data-theme="light"]`, `html[data-lang="zh"]`, `html[data-theme="light"][data-lang="zh"]`, the `--ink-mix-*`/`--ink-*` rungs, the `--fill-*` rungs. Reserved-hue law (master §1) binds: colour appears only for direction, health, wayfinding, provisional tier, or lock. Everything else is achromatic.

**Two workspace derivations, both bound to theme tokens, neither a new root:**

```
--r3-thread : var(--link)                                        /* dark  */
--r3-thread : color-mix(in srgb, var(--link) 74%, var(--line))   /* light */
```

The light softening is art direction, not decoration: a 3px `#285fff` rail is the loudest mark on a `#f7f8fa` canvas and reads as a web app. Light earns depth with structure.

**The five graded-call inks — RESERVED.** Bound only inside `.r3-board` (ledge cell + board top rail) and an Action-view row stance:

```
.st-buy   { --c: var(--ink-up)   }   .st-soon { --c: var(--ink-info) }
.st-run   { --c: var(--ink-link) }   .st-trim { --c: var(--ink-warn) }
.st-aside { --c: var(--muted)    }
```

`--ink-up`/`--ink-down` flip under `html[data-lang="zh"]` (红涨绿跌) by construction — the ZH crops show the Buy ledge turning red with no second palette. `--ink-warn` (health) never flips. No literal green/red hex appears anywhere in the system.

---

## 4. Light mode as a design (doctrine §5.8)

Judged as a design, not as "does it render". Three rules that the specimen implements and the lanes inherit:

| | Dark | Light |
|---|---|---|
| Rail (`.si-side`) | `--panel` on `--bg` — luminance separates it | **tinted paper**: `color-mix(--panel2 62%, --panel)`. A white rail on `#f7f8fa` is the flatness bug — panels are the white surfaces, the rail is not |
| Dominant object edge | 1px `--line` + `--card-shadow` | **firmer hairline** `color-mix(--text 9%, --line)`; no heavier shadow — a printed note, not a floating card |
| Accent | `--link` at full strength | `--r3-thread` softened 74% toward `--line` |
| Selected ledge cell | `color-mix(--c 8%, --panel2)` | same formula, ≤8% — under the highlighter-smear ceiling |
| State rail on the board | 3px `--c` | 3px `--c` |

**Trap recorded from this build:** the light hairline rule was first written as `border-color:` — a **four-side shorthand** — which silently repainted the board's 3px state rail as a hairline in light only. Any light-mode edge override must restore `border-top-color` by name. Verified in `1440-light-EN-confluence.png`.

---

## 5. Page grammar (commission §6.2)

Every view, in this order, and nothing else at L1:

```
1  VIEW ANSWER        .r3-answer      — eyebrow-h2 + one sentence + meta row
2  [STATE LEDGE]      .r3-board       — ACTION TIER ONLY; absent on context views
3  DOMINANT OBJECT    board rows | chart mount | table
4  EVIDENCE           .r3-rail (2-col) or a following band
5  DEEPER PATH        .r3-more (text + chevron) — one per view
```

### 5.1 One answer per view, one voice

**The nightly composed read IS the answer line.** `.si-view-read` is placed *inside* `.r3-answer` and styled as the 22px sentence — no panel, no border, no second box. A static fallback `<p class="r3-answer-line">` sits after it and is hidden by a pure-CSS sibling rule whenever the read is present:

```css
.r3-answer .si-view-read:not([hidden]) ~ .r3-answer-line{ display:none; }
```

Rationale, and it is load-bearing: production hides its own read on Overview (`sector_central.html.j2:1620`) precisely because a hero already said the same thing — i.e. the composed read is **dead on the most important view today**. Stacking a hero over a read would re-create that. Merging them retires it, keeps one canonical answer per view (one-integer law), and guarantees a view is never answerless when the composer returns null. Confluence has **no read slot** by contract, so it uses the static line as its normal path.

Fallback copy is the sanctioned "read being updated" register (#3821): *"Tonight's read is being updated. The graded lanes below are today's board."* Never falsifier/refutation vocabulary.

### 5.2 The State Ledge — `.r3-board`

One object: five fixed cells → a foot row → the selected lane's rows. A separate section header under a ledge cell of the same name is the same answer printed twice; **the ledge is the header.**

- Grid `repeat(5, minmax(0,1fr))` — equal, **never proportional** (Sol amendment §13). Text labels and counts are never scaled by population.
- Cell: name (11/700/caps, wraps to 2 lines, never clipped) over count (22/800/`.tnum`). Both always legible in every state.
- Selected: `color-mix(--c 8%, --panel2)` fill + `inset 0 -3px 0 var(--c)` + name in `--c`. The board's `border-top:3px` takes `--c` — the one place a state hue goes full-width, and it is a hairline.
- Foot row: lane subcopy (producer verbatim) + `?` receipt + right-aligned honest count (`3 of 3 shown`).
- Column legend `.r3-cols`: a figure column may never be unlabelled (doctrine Law 3).
- `role="tablist"` / `role="tab"` / `aria-selected`, rows in `role="tabpanel"`. Real tab semantics — never faked (§17).
- An **optional** secondary proportional visualisation may sit below the cells. It may never replace or resize the text cells.

**Producer vocabulary, verbatim (EN / ZH) — lanes may not re-word:**

| key(s) | EN | ZH |
|---|---|---|
| `buy_now` | Buy now | 立即买入 |
| `buy_soon` | Almost ready | 接近就绪 |
| `on_the_run` | In favour — don't chase | 看好 — 勿追高 |
| `take_profits` | Take profits | 止盈 |
| `hold` + `avoid` | Stand aside | 观望 |
| watch strip (not a lane) | Bottoming watch | 筑底观察 |

Source: `templates/_us_act_now_board.html.j2` via `research/reference_integrity/mastermind-xpv2-sector-r3/archaeology/lane_A_action_overview.md` §2. Confluence's state vocabulary comes from the R3A binding pack; the specimen's Entry now / Forming / Tailwind / Late / Headwind cells are **shape-only placeholders** — D1 binds the exact strings (§15 GAP-1).

### 5.3 Bottoming Watch — `.r3-watch`

Full-width strip **under** the board, never a sixth cell. Three equal cells of name + one plain clause, then one merged foot line. **No state ink, no count cell, no filled control, no entry verb.** `signal` and `timing_state` are never rendered. Watch vocabulary only.

### 5.4 Resource list — `.r3-row`

`grid-template-columns: minmax(0,1.6fr) 74px minmax(0,1.25fr) 16px`, gap 16px: **name · figure · why · chevron**. ≤640px it becomes `minmax(0,1fr) auto` with the why clause on its own full-width line and the chevron dropped (the whole row is the target). Name wraps; figure is `.tnum` right-aligned; why is one 12.5px `--muted` clause. A constant never repeats per row.

### 5.5 Deeper path

Context views: `.r3-more` only — 44px-tall text link, `--ink-link`, hairline chevron. **Zero filled buttons on a context view.** Action views may additionally use one `.r3-cta`; the workspace budget is **one filled control per view, maximum two on the page**.

---

## 6. Authority-weight system (commission §7) — the token-level law

This is the section that answers last cycle's #1 kill reason. It is written as rules a reviewer can check by grepping the CSS.

**Action tier** = Overview (Act-Now board) and Confluence, and nothing else.

| Channel | Action tier | Context tier (Map · Moving · Money · Explore) |
|---|---|---|
| State ledge | required | **forbidden** |
| Solid `--fill-*` chip with white text | permitted | **forbidden** |
| State ink (`--ink-up/down/warn/ok/act/info/link`) as text | any size | **only ≤`--fs-sm` 12.5px**, only on a signed numeric move, always with a sign character |
| ≥10% state tint on a surface | permitted (ledge cell, 8%) | **forbidden** |
| 3px state rail | permitted (board top, selected cell) | **forbidden** |
| Filled control (`.r3-cta`) | **one** per view | **zero** |
| Heaviest ink on the page | the graded call (22/800 count) | the **object name** (15/700) |
| L1 section budget | 5 | 4 |
| L1 section gap | 32px | 44px |

**Reserved-token rule, stated for the ratchet:** `--fill-*`, `.st-*`, `.r3-board`, `.r3-cta` may appear only inside a `.r3-view--action` section. `.r3-view--context` sections carry `--ink-up`/`--ink-down` at ≤12.5px and otherwise achromatic text. A grep that finds `.st-` or `--fill-` inside a context view is a design defect, not a preference.

**The Map's `reco` tags — deliberately tertiary (`.r3-tag`).** Recorded CONFLICT capability, preserved, never amplified:

```css
.r3-tag{ font-size:var(--fs-micro);   /* 10px — smallest step on the ramp */
         font-weight:600; border:1px solid var(--line); color:var(--muted);
         border-radius:var(--r-ctl); padding:1px 7px; }
```

No hue, no fill, no pill, no icon. It sits in the **last** table column, and the plain-word disclaimer sits **after** the table in DOM order. Lanes may not enlarge it, colour it, relocate it out from under its disclaimer, or give it a CTA. It is deliberately below even the context baseline.

**Overview dual-read (§7.3).** Leadership context and the Act-Now board are structurally independent. The reference draws **no arrow, no shared hue, no causal prose** between them. They are separated by the ledge's own border and by the answer's neutral `--r3-thread` rail (wayfinding, identical on all six views, therefore not a link between the two systems).

---

## 7. View navigation

**Desktop ≥1101px** — vertical rail, 200px, sticky at `top:var(--r3-chrome-h)`, `height:calc(100vh - var(--r3-chrome-h))`. `VIEWS` eyebrow, six items (icon 17px + 13px/600 label), rail footer carrying `#si-side-asof` and `#si-side-grade`. Active: `--panel` tint + `--r3-thread` 3px left rail + weight 700.

**768–1100px** — rail narrows to **172px, labels stay**. This is a **deliberate divergence from production**, which collapses to a 56px icon rail with `data-tip` tooltips (`sector_central.html.j2:1177-1184`). An icon-only rail is a hover-only affordance (master §14 forbids hover-only paths) and its tooltips are unusable at 200% zoom. Labels wrap to two lines rather than disappear.

**≤767px** — a sticky **3 × 2 grid**, icon over label, cell `min-height:52px`, all six destinations visible, **no horizontal scroll**. This is the second deliberate divergence: production ships `overflow-x:auto` on a six-tab strip (`:1189-1191`), which at 320–390px pushes **Explore and Confluence off the right edge** — and Confluence is an *Action* view, so that is a hidden capability, not a layout nicety. It is the same defect class the Sol amendment prohibits for the Overview state selector.

**≤359px** — the grid becomes **2 × 3**. Nothing is removed; the reduction is a re-composition.

**Scroll-offset law (§14) — the whole repair is one property.** `si_workspace.js` lands legacy anchors with `scrollIntoView({block:'start'})`, which honours `scroll-margin-top`. Therefore:

```css
.si-view [id], .si-view[id]{
  scroll-margin-top: calc(var(--r3-chrome-h) + var(--r3-mnav-h) + 16px);
}
:root{ --r3-mnav-h:0px }
@media (max-width:767px){ :root{ --r3-mnav-h:104px } }
@media (max-width:359px){ :root{ --r3-mnav-h:158px } }
```

A hash landing therefore never buries the view answer under sticky chrome, at any width. Lanes must keep every legacy-anchor target inside `.si-view` so the selector reaches it.

---

## 8. The `si_workspace.js` DOM contract (verbatim-accurate)

`templates/si_workspace.js` (328 lines) is reused **verbatim** — production and the R3 reference load the same file. The shell must satisfy every item below. Line refs are to that file.

| # | Contract | Ref |
|---|---|---|
| 1 | `VIEWS = ['overview','map','moving','money','explore','confluence']` — ids and order fixed | :17 |
| 2 | `document.querySelectorAll('.si-view')`; each carries `data-view="<id>"`; router toggles `.on`. CSS must supply `.si-view{display:none}` / `.si-view.on{display:block}` | :275-276 |
| 3 | `document.querySelectorAll('.si-view-btn')`; each carries `data-view="<id>"`; router toggles `.on` and sets/removes `aria-current="page"`. They are `<a href="#<view>">` — **never `href="#"`** | :277-281 |
| 4 | Read slots `#si-read-overview|map|moving|money|explore`. **No `#si-read-confluence`** — Confluence's own hero is its read | :219, :12-16 |
| 5 | Router writes into the slot: `<span class="si-vr-g <GLYPH>">` + `<span class="si-vr-t">` + `<span class="si-vr-q" data-tip-t-en/-zh data-tip-en/-zh>?</span>`, then `el.hidden=false`. CSS must style `.si-view-read`, `.si-view-read[hidden]{display:none}`, `.si-vr-g`, `.si-vr-t`, `.si-vr-q` | :222-226 |
| 6 | Slot attributes the composer reads: overview `data-from-en` `data-to-en` `data-from-zh` `data-to-zh`; money `data-regime` | :142-143, :190 |
| 7 | Rail footer spans `#si-side-asof`, `#si-side-grade` — `innerHTML` written as `.l-en`/`.l-zh` pairs | :230-244 |
| 8 | `L(en,zh)` emits `<span class="l-en">…</span><span class="l-zh">…</span>`. CSS must hide `.l-zh` by default and `.l-en` under `html[data-lang="zh"]` | :126 |
| 9 | `isZh()` reads `document.documentElement.getAttribute('data-lang')==='zh'` | :123 |
| 10 | Glyph classes must resolve: overview `dash-icon submenu-icon-intelligence` · map `dash-icon dash-icon-compass` · moving `dash-icon submenu-icon-rotation` · money `dash-icon submenu-icon-flow` · explore `dash-icon dash-icon-search` · confluence `dash-icon submenu-icon-confluence` | :24-30 |
| 11 | `BASE_TITLE = document.title.split(' · ')[0]` then `BASE_TITLE + ' · ' + TITLES[view][isZh()?1:0]`. **The `<title>` must not already contain `' · '`** or the base is truncated | :271, :282 |
| 12 | 21 `LEGACY_ANCHORS`, each `[view, targetId]`; `activate()` calls `getElementById(target).scrollIntoView({block:'start'})`; a missing target falls back to `history.replaceState('#'+view)` | :40-64, :304-308 |
| 13 | `#read-<id>` → `pendingTrace`; `openTrace()` needs `#actnow` containing `.rvx-trow[data-mlc-bid="<id>"]` and a truthy `window.__siTrace`; it calls `row.click()` then `scrollIntoView({block:'center'})` | :261-268, :314 |
| 14 | `#theme-<id>` → `activate('overview',null)` and returns; the inline `resolveThemeHash()` (`sector_central.html.j2:2813-2818`) owns navigation and must not be reimplemented | :313 |
| 15 | Unknown/empty hash → overview; empty hash gets `replaceState('#overview')` | :317-318 |
| 16 | Lazy mount on **first** activation: `map:['@cycles']` · `moving:[subsector_rotation.js, rotation_events.js, desk_watch.js]` · `money:[heatmap.js]` · `explore:[subsector_rotation.js, time_machine.js]` · `confluence:[subsectors.js]`. It forces reflow via `sec.offsetHeight`, fires `window resize`, then dispatches `document` CustomEvent `si:view` with `detail:view` | :76-86, :291-302 |
| 17 | Payload globals the reads consume: `window.BASKETS` (`.theme_intel`, `.baskets`, `.as_of`), `window.SECTOR_CENTRAL.grader`, `window.__siRvxData()` | :127-128, :166, :233 |
| 18 | Exports `window.__siViewReads`, `window.__siRoute`; listens on `window hashchange` and `document langchange` | :321-326 |
| 19 | The router carries **no breakpoint** — the ≤767px behaviour is CSS-only (`sector_central.html.j2:1187`). Mobile may recompose freely | — |

### 8.1 The mount-width law — binding on D2 and D3

Item 16 has a design consequence the lanes must obey. Width-measuring organs size themselves from `clientWidth` **at activation**: `heatmap.js` from `tm.clientWidth || wrap.clientWidth`, `subsector_rotation.js` from `container.clientWidth`, and lightweight-charts binds `autoSize` at creation. A chart created zero-wide **never recovers**.

> **No chart container may be inside a closed `<details>`, a `display:none` wrapper, or an unmounted tab at the moment its view activates.** The commission permits the phone Map to put the full map "behind an explicit disclosure" (§9) — implement that with `height`/`visibility`/`clip`, or mount at activation and collapse afterwards, **never** with `display:none`. Same rule for the Money treemap and the Explore chart.

Production already encodes the twin of this rule for the Explore chart's deferred mount (`:2731-2740`), which is a RETAIN capability.

---

## 9. Component vocabulary

Reuse the canonical `.mx-*` anatomies from `mockups/design_system/specimen.html` where they apply. Reference-scoped components carry the `.r3-*` prefix (never `.mx-*`, never bare names — the namespace law and the 11 known collisions). At production migration each maps to an `.mx-*` or `si-*` name; that mapping is R3C's, not the lanes'.

| Component | Class | Rule |
|---|---|---|
| View answer | `.r3-answer` | §5.1. One per view. The only element besides the active rail item allowed a 3px `--r3-thread` rail |
| State ledge / board | `.r3-board`, `.r3-ledge-grid`, `.r3-ledge-cell` | §5.2. Action tier only |
| Column legend | `.r3-cols` | mirrors `.r3-row`'s grid; hidden ≤640 |
| Resource row | `.r3-row` | §5.4. The default for ≤8 items with a name and a reason |
| Table | `.r3-tbl` inside `.r3-tblbox` | th 10/700/caps · td 12.5 `.tnum` · first cell 14/700 · `min-width:420px`, **the box scrolls, the page never does** · ≤8 rows at L1 + counted "Show all N" |
| Watch strip | `.r3-watch` | §5.3 |
| Evidence rail | `.r3-rail` in `.r3-stagegrid` (`1.85fr / minmax(268px,.85fr)`) | collapses to one column ≤1100 |
| Quadrant tiles | `.r3-quads` / `.r3-quad` | 2×2, 1px `--line` gaps, `min-height:88px` |
| Chip | `.r3-chip` | 11/700/caps pill, `--c` 11% fill / 34% border |
| Tertiary tag | `.r3-tag` | §6. The reco treatment. No hue |
| Callout | `.r3-callout` | 3px `--c` rail + ≤8% tint. The light-safe highlight idiom |
| Disclosure | `.r3-disc` | styled `<details>`; summary ≥44px and must state **what is inside and why to open it** |
| Segmented filter | `.r3-seg` | `role="group"` + `aria-pressed`; 40px, **44px ≤767** |
| Task tabs | `.r3-tabs` | `role="tablist"`/`role="tab"`/`aria-selected`; 44px; selected writes the URL hash |
| Empty | `.r3-empty` + `.r3-empty-why` | mandatory why. "an empty lane, not a missing one" — never a bare `—`, never pipeline telemetry |
| Loading | `.r3-mount` | §9.1 |
| Stale | `.r3-stale` on the as-of + one plain line | never a banner |
| Visually hidden | `.r3-vh` | the bilingual home for an accessible name. **Never `title=`** (CI-guarded), never a single-language `aria-label` |

### 9.1 Loading is skeleton-free

Sector Central is server-rendered: content arrives baked, so there is no loading state for it. The only true loading is the lazy organ mount. Its lawful state is **reserved geometry + one quiet line naming what is mounting** — a dashed hairline box at the organ's real height, no shimmer.

This reconciles two sources and the reconciliation is deliberate: master design system §9.12 prescribes "skeleton at true geometry", the commission requires "skeleton-free loading per production law". Both agree on *geometry*; the animation is what is dropped, because motion is a status channel and an element may only animate if it encodes a live/ongoing fact (master §7) — a 60 ms script injection is not one.

### 9.2 Chip budget — a number, not a preference

**≤2 chip-class elements visible per L1 section at rest; ≤6 per view.** A constant never repeats per row (doctrine Law 4) — it belongs in the section foot, once. One as-of per panel, one page-level stamp in chrome, one merged footnote per panel.

### 9.3 Iconography — the lawful set, named

Only the estate's masked monoline family: `.dash-icon` base (`templates/dashboard-icons.css:5-23`) plus a mask class from `templates/dashboard-icons.css` or `templates/product-nav-icons.css`. Masks tint from `currentColor`, so theme and ZH flips are free and an icon never sets its own fill.

Sanctioned on this workspace: the six view glyphs pinned by `si_workspace.js:24-30` (`submenu-icon-intelligence`, `dash-icon-compass`, `submenu-icon-rotation`, `submenu-icon-flow`, `dash-icon-search`, `submenu-icon-confluence`), plus `dash-icon-table`, `dash-icon-info`, `dash-icon-search`, `dash-icon-check`, `dash-icon-close`, `dash-icon-star`, `dash-icon-shield`, `dash-icon-compass`, `dash-icon-balance`, `dash-icon-person`, `dash-icon-drop`, `dash-icon-ripening`, `dash-icon-finish`, `dash-icon-prohibited`, `dash-icon-pause`, `dash-icon-profit`, `dash-icon-dot`. Country flags via `.dash-flag` where house law permits.

**Forbidden:** every Unicode star/arrow/lightning, every emoji, every improvised glyph, and any new mask that is not added to `dashboard-icons.css`. Chevrons are CSS borders, not characters. A lane needing an icon the set lacks escalates — it does not draw one.

---

## 10. Density budgets by archetype

| Tier | Views | L1 budget | Section gap | Row height | Panel padding | Mobile reduction |
|---|---|---|---|---|---|---|
| **Action** | Overview, Confluence | 5 | 32px | 58px | 18px 20px | answer + ledge + selected list in one swipe; supporting bands below |
| **Context** | Map, Moving | 4 | 44px | 58px | 16px 18px | answer + concise summary + accessible list; the chart is reachable in the same view |
| **Dense research** | Money, Explore | 5 | 32px | 52px | 14px 16px | answer + filters + table (in-container scroll only); research organs behind `.r3-disc` |

**Calm is bought with air, not with fewer words.** Context views hold fewer sections at a wider gap; dense views hold tighter rows at fewer sections. Neither is allowed to become "the desktop stack, squeezed".

**Above-fold budget at 1440×900:** chrome + the answer + at most two supporting modules. **At 390:** the answer within one swipe.

---

## 11. EN / ZH

- Every Tier-1 string ships an EN and a **native-shaped** ZH twin via `.l-en`/`.l-zh` dual-emit. Never machine-flipped, never an EN state name inside ZH copy.
- **The bilingual switch needs specificity, and this is a measured trap from this build.** A bare `.l-zh{display:none}` is (0,1,0) and loses to any layout rule shaped `.block span{display:block}` (0,1,1) — which prints the ZH twin next to the EN one on that component only. It happened here on the watch strip. Two defences, both required:

```css
html[data-lang]      .l-zh{ display:none; }    /* (0,2,1) */
html[data-lang="zh"] .l-en{ display:none; }
html[data-lang="zh"] .l-zh{ display:inline; }
```
  …**and** scope every layout rule to direct children (`.r3-watch-cell > span`, not `.r3-watch-cell span`) so it cannot reach a language span at all.
- ZH typography: CJK stack leads under `html[data-lang="zh"]`; `letter-spacing:0` and `text-transform:none` on `h1,h2,h3`, every eyebrow, every caps label and the ledge state name — **uppercase mangles mixed CJK/Latin and does nothing for hanzi; weight 700 is the substitute emphasis**. The −.02/−.03em display tracking is EN-only.
- **Size cells to the ZH label, not the EN one.** CJK carries no word spaces and offers no wrap opportunities, so a 5-hanzi label at 11px is a hard 55px block. ZH caps-slot tracking drops from .08em to 0 for exactly this reason.
- ZH measure: the answer line is capped at 34em (not 62ch) and leads at 1.55.
- Budgets are counted in **characters**, separately from EN: Tier-1 view name ≤8 hanzi; answer line ≤30 hanzi; row reason clause ≤20 hanzi.
- ZH parity extends to generated rows, buttons, placeholders, empty/error states, accessible names, dialog labels, chart text alternatives and every as-of stamp. **No translated text in `title=`** (CI-guarded) — `data-tip-en`/`data-tip-zh` is the hover home, `.r3-vh` is the accessible-name home.

---

## 12. Responsive + accessibility floor

**Breakpoints:** 1440 (shell max) · 1100 (rail 172px, evidence rail collapses) · 767 (grid switcher, ledge 2-col) · 640 (row reflow, column legend drops) · 359 (nav 2×3, ledge 1-col). **390 is the design floor; 320 must not overflow.**

- `minmax(0,…)` / `min-width:0` on every grid child. Wide content scrolls **inside its container**; the page never scrolls horizontally at any width.
- Repeated/primary mobile targets **≥44 CSS px**: rail cells 52, ledge cells 56, tabs 44, filters 44, `.r3-more` 44, `.r3-disc summary` 44, rows 64.
- Focus-visible ring on every interactive element via a low-specificity `:where(...)` rule: 2px `color-mix(--link 70%)`, offset 2.
- Semantics: exactly **one `<h1>`** for the document (the page header); every view heads with an `<h2>`; every band has a real heading element. Tabs use real tab semantics; filters use `role="group"` + `aria-pressed`; the rail uses link semantics with `aria-current="page"` (set by the router).
- Hover is never the only path: LENS opens on tap, nothing is tooltip-only. This is why the 768–1100 icon-only rail was dropped (§7).
- `prefers-reduced-motion` disables all transitions/animations, pseudos named.
- Contrast: text ≤18px ≥4.5:1 **on its actual painted surface** — a hue printed on its own tint is a harder pair than the same hue on `--panel`. Never bypass an `--ink-*` rung with a literal.
- Chart accessibility (mandatory, §17): every customer-relevant chart carries an accessible name, a concise textual takeaway, **and** a table/list equivalent driven from the *same producer fields* — no alternate scoring, no new rank. Map → the `window.SECTOR_CYCLES` list. Money → the `marketdata/sp500_heatmap.json` table.

---

## 13. Per-lane authority — what D1 / D2 / D3 may and may not decide

**All three lanes, binding:** no new token, no new `:root`, no font stack, no radius outside the five stops, no hue outside theme.css, no icon outside §9.3, no `href="#"`, no falsifier/refutation vocabulary, no client-side recompute of rank, lane assignment, counts, state classification or producer ordering (R3 design brief §8), no editing of `si_workspace.js`, no third page header.

### D1 — Overview + Confluence (Action)
**May decide:** which supporting modules earn an L1 slot within the budget of 5; row anatomy inside `.r3-row`'s grid; the optional secondary proportional visualisation under the ledge cells; gated-preview presentation within `access_hydration_contract.md`; the mobile order of everything **below** the ledge; Confluence's universe-tab labels' typographic treatment; group/member/stock detail composition.
**May not decide:** the state vocabulary or its EN/ZH twins; the ledge's fixed-cell law (no proportional labels, ever); that solid fills and >12.5px state ink are Action-only; adding a sixth lane; promoting Bottoming Watch out of the watch strip or surfacing `signal`/`timing_state`; inventing a Baskets thin/coverage disclosure; inventing a correction/revision affordance; inventing a Confluence freshness threshold; mixing rows across universes.

### D2 — Map + Moving (Context)
**May decide:** the chart's composition, quadrant labelling and annotation restraint; the selected-object detail layout; the event/transition row anatomy; which columns the accessible cycle-list carries (from the same fields); the phone Map's reduction — concise answer → quadrant summary → selected object → ranked list, with the full map reachable in the same view.
**May not decide:** any solid state fill, any state ink above 12.5px, any state tint, any filled CTA; enlarging, colouring, re-pilling or relocating `reco` out from under its disclaimer, or re-authoring its semantics; introducing action vocabulary on either view; sourcing Moving from anything other than its five artifacts (`rotation_events`, `sector_fragmentation`, `subsector_rotation`, `oracle_turn_desk`, `oracle_tape_onset`) — `si_handoff.json` is **not** a Moving source; putting a chart container behind `display:none` at activation (§8.1).

### D3 — Money & Breadth + Explore (Dense research)
**May decide:** list vs table per organ; column priority and which columns drop first; the selected-detail/performance layout; filter and search chrome within `.r3-seg`; how Time Machine, Forming Narratives and Track Record group behind `.r3-disc`; the heatmap's table equivalent columns; mobile row-card vs reduced-column treatment.
**May not decide:** fusing organs into a new health/flow/action composite score; adding a filled CTA; exceeding the chip budget; letting a table scroll the page instead of its own box; changing Explore's top-8/bottom-8 + "Show all" default or Time Machine's fetch-on-first-open; labelling the whole Forming Narratives panel as AI — **only `ai_watch` carries "Model analysis / 模型分析"**, and the deterministic rank/score must not.

### QA lane
Owns the design-stage attack at 320/360/390/430/768/820/1024/1280/1440, 200% zoom at 320/390/768/820, EN and ZH, target size, chart alternatives and keyboard semantics. It is **not** a final RIG critic seat.

---

## 14. Evidence — `./lead_crops/`

Captured at devicePixelRatio 2 against the shell specimen served over `http://127.0.0.1`. State is reproducible from the URL: `?theme=light|dark&lang=en|zh#<view>`.

| File | Shows |
|---|---|
| `1440-dark-EN-overview.png` | The reference frame. Action tier: answer thread → State Ledge fused with its selected list into one dominant object → watch strip → single text deeper path. Three L1 sections on the first screen |
| `1440-light-EN-overview.png` | Light as a design: tinted paper rail, firmer hairline on the dominant object, softened thread |
| `1440-light-EN-confluence.png` | Second Action view. Universe tabs + ledge + fused list; the 3px state rail surviving the light hairline override; the empty-lane state under its own "Late" heading |
| `1440-dark-EN-map.png` | **Context tier, side by side with Overview: no ledge, no state hue, no filled control.** Chart mount at reserved geometry, evidence rail, accessible list, and the `reco` tags as 10px hairline `.r3-tag`s under their disclaimer |
| `1440-dark-EN-money.png` | Context/dense: four quadrant reads including a "read being updated" stale state, and the heatmap's table equivalent behind `.r3-disc` |
| `1440-dark-EN-moving.png` | Context tier: the transition-row pattern for D2, with the source→destination mark drawn in CSS — no Unicode arrow anywhere in the system |
| `1440-dark-ZH-overview.png` | ZH at desktop: native-shaped copy, no tracking/uppercase mangling, and **红涨绿跌 flipping the Buy ledge to red with no second palette** |
| `390-dark-EN-overview.png` | Phone recomposition: 3×2 view grid (all six destinations, no horizontal scroll), 2-column ledge with Stand aside spanning, names wrapping not truncating |
| `390-dark-ZH-overview.png` | The same phone composition in ZH — cells sized to the ZH label, direction ink flipped |
| `390-light-ZH-confluence.png` | Phone × light × ZH × Action tier — the hardest quadrant of the four |
| `390-dark-EN-map.png` | Phone context tier: no ledge, chart reduction |
| `320-dark-EN-overview.png` | 320px: no overflow, one-column ledge, all five labels and counts legible |
| `320-dark-ZH-confluence.png` | 320 × ZH × Action: four universes on one row, five states legible one-up, no clipped label |
| `195-dark-EN-overview-zoom200.png` | 390 at 200% browser zoom: 2×3 nav, no overflow, nothing clipped |
| `820-light-EN-explore.png` | Tablet dense research: filters, table, "Model analysis" scoped to `ai_watch` only, text-link deeper path |

**Programmatic checks run against the live shell (they supplement, never replace, the crops).**
Swept as **6 views × 4 quadrants (dark/light × EN/ZH)** at **1440, 390 and 320**, plus all six views at 820 and 195:

| Probe | Result |
|---|---|
| `documentElement.scrollWidth === innerWidth` | **pass**, 1440 / 820 / 390 / 320 / 195 |
| Elements whose `getBoundingClientRect().right` exceeds the viewport | **0**, every view × quadrant × width |
| Language leak (`.l-zh` visible under EN, `.l-en` visible under ZH) | **0** — it was **12** before the §11 specificity fix |
| Interactive elements under 44px inside the active view | **0** at 1440 and 390 |
| Six nav destinations fully on-screen at ≥44px | **6 / 6** at 390 and 320, all four quadrants |
| Every ledge label **and** count unclipped (`scrollWidth ≤ clientWidth`) | **pass** at 320, all four quadrants |
| `a[href="#"]` | **0** |
| `[title]` attributes | **0** (bilingual accessible names go through `.r3-vh`) |
| Router: `.si-view.on` count per route | exactly **1**; `document.title` tracks `BASE_TITLE · <view title>`; `aria-current="page"` follows the active `.si-view-btn` |

At an effective 160px (320 at 200% browser zoom) no element overflows; `scrollWidth` reports 164 vs `innerWidth` 160, which is the scrollbar gutter, not a layout overflow (see GAP-5).

---

## 15. Open questions for the orchestrator

**GAP-1 — Confluence state vocabulary (blocks D1).** The Overview lane labels are quoted verbatim from `_us_act_now_board.html.j2` via lane A's archaeology. I found **no equivalent verbatim EN/ZH table for the Confluence class buckets** (`entry_now/forming/tailwind/neutral/late/headwind`) in the R3A pack files I read. The specimen's Entry now / Forming / Tailwind / Late / Headwind cells are shape-only. **D1 must bind these from the fixture/binding matrix before drawing.** They must not be authored.

**GAP-2 — ZH display names for groups.** The specimen prints GICS-style taxonomy names in both languages because I did not open the fixture's name map. Production ships ZH twins for display names. Lanes bind them; the type system already assumes ZH names may be shorter and denser than EN.

**GAP-3 — `--fs-lead` (18px).** I considered minting an 18px "lead" step for the answer line and rejected it, using the on-ramp `--fs-num-lg` 22px at weight 500 instead. If a later surface genuinely needs 18px, it is a DS-PR-0 ramp question, not a workspace-local token. Flagging so nobody quietly adds it.

**GAP-4 — Two deliberate divergences from production chrome** (§7): labels kept on the 768–1100 rail instead of the icon-only collapse, and the ≤767 six-tab horizontal scroller replaced by a 3×2 grid. Both are UX-defect repairs with stated reasons, both are CSS-only, and both are inside "R3 owns the mobile layout decision" (R3 design brief §5). They nonetheless change chrome the R3A pack recorded as-is, so I am surfacing them rather than absorbing them.

**GAP-5 — 200% zoom semantics.** I tested browser-zoom semantics (viewport halved: 195px for 390, 160px for 320). At 195 the layout is clean. At 160 no element overflows but `scrollWidth` reports 164 vs `innerWidth` 160 — a scrollbar-gutter artifact, not a layout overflow. If the QA lane's suite uses **text-only** zoom instead, the px-based ramp will not scale and the meaningful assertion becomes "no fixed heights clip text", which this system satisfies (`min-height` everywhere, no `height` on a text box). Worth pinning the suite's definition before QA runs.

**GAP-6 — `.r3-*` → `.mx-*` promotion.** Reference-scoped names are deliberate. Which of `.r3-answer`, `.r3-board`, `.r3-row`, `.r3-watch`, `.r3-tag` graduate into `theme.css` as `.mx-*` primitives is an R3C migration question, and at least `.r3-board` and `.r3-row` look estate-general rather than Sector-Central-specific.

---

## 16. Commission §25 acceptance — the system-level answer

| Dimension | System answer |
|---|---|
| First-screen hierarchy | One answer at 22/500, then exactly one dominant object. Page title demoted to 15px chrome so the first screen belongs to the answer. Measured: 3 L1 sections visible at 1440×900 |
| Panel count | L1 budget 5 (action) / 4 (context), hard ceiling 7. The ledge and its selected list are **one** object, not two |
| Whitespace | 32px action / 44px context between L1 sections; 24/32px answer→first section; 62ch answer measure. Calm is bought with air |
| Full-name readability | 15/700/−.008em, `overflow-wrap:anywhere`, **no ellipsis on any primary name, at any width, in either language**. Names get the flexible column; numbers get the fixed one |
| Chart prominence | The chart is the dominant object on Map only. Everywhere else it sits in a reserved-geometry mount inside its section, never full-bleed, never bordered inside a panel |
| Repeated caveats | One as-of per panel, one page stamp, one merged footnote per panel. A constant never repeats per row. The watch strip's disclosure appears once, in its foot |
| Excessive chips | ≤2 chip-class elements per L1 section at rest, ≤6 per view. The `reco` treatment is a 10px hairline tag, not a chip |
| Authority-weight differentiation | §6: the ledge's presence/absence, plus a token-level reservation table (fills, ink size, tints, rails, filled controls, heaviest-ink rule) that a reviewer can grep |
| Mobile independence | The phone recomposes: 3×2 view grid (production scrolls six tabs off-screen), 2-column ledge with Stand aside spanning, rows reflowing to name+figure over clause. Not one desktop grid is merely narrowed |
| Dark / light quality | Two art directions, not a token swap: dark separates by luminance, light by tinted rail + firmer hairline + softened accent. §4, with the `border-color` shorthand trap recorded |
| Institutional vs playful | One family across an extreme weight range, tabular figures everywhere, achromatic by default with hue rationed to five meanings, zero breathing elements, zero emoji, CSS-drawn chevrons, no gradients, no glow. Confidence comes from restraint and precision |
