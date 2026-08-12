# WINNER HEALTH — W2b Surface Design Spec (three tiers)

**Status:** PINNED. This document extends `research/top_anatomy/W1_SURFACE_DESIGN_SPEC.md`
(still the **visual law** for everything it already pins) to the two W2 extension tiers.
`docs/DESIGN_DOCTRINE.md` is the **content law** and wins on every conflict.
**Mandate:** `reports/top-anatomy-w2.md` §7.1 (ratified) — Winner Health may widen to the
R63/ATRZ tiers ONLY with per-tier libraries and thresholds, honest no-analog states across
tiers, B2-family legs counted within the same display-tier language, and a cohort-honesty
banner on the ATRZ tier.
**Authored:** 2026-08-11, design lane (opus `designer`), after loading the doctrine and the
`frontend-design` skill, reading the W1 spec, and reading the live surface in dark + light +
ZH at 1360px against tonight's real artifact (122 rows, 18 themes).
**Scope:** SPEC ONLY. No page, engine, builder or test change ships with this document.
**Reference shots (committed — the look does not travel as prose):**
`mockups/refs/topa_w2b/shelf_dark.png` · `shelf_light.png` · `shelf_zh.png` ·
`shelf_mobile_390.png`, produced by `mockups/refs/topa_w2b/shelf_mock.html` (standalone, loads
the real `theme.css`, no build step). They show the hero shelf, a tier head, the mixed-group
banner, the wear ladder with its off-ladder line, a roll-up, two compact rows, an unreadable
row and the tier null band. **Build to the shots, not to the prose.**

**Standing law inherited unchanged:** display tier, zero scored authority — no rank, no
size, no gate, no probability, no exit rule, AVOID-not-SHORT (`DNR:KILL-DIRECTIONAL-SHORTING`).
The board-membership window stays **exactly 21 sessions on every tier**; admission-window
widening is a killed construction (`DNR:KILL-FRESH-TICKS-WINDOW`) and the tiers get their own
extension bars instead, which is a different act.

---

## §0 Acceptance gates (this delta is not done unless)

- **G-1 · No cross-tier threshold reuse, anywhere.** Every library-cut leg threshold, every
  analog library and every window is cut from the tier's own history. A leg whose threshold
  cannot be cut for a tier does not fire on that tier — it is never borrowed.
- **G-2 · The three counts are never summed.** No total-across-tiers number renders anywhere,
  in any state, including the small print. Overlap is disclosed in the hero.
- **G-3 · The primary board is byte-identical in behaviour.** Same four states, same stances,
  same sub-lines, same leg set, same order rule, same anchors, same row anatomy, same
  thresholds. Verified by rendering tonight's artifact before and after: the primary tier's
  section body diffs only by the added tier kicker on its group headers.
- **G-4 · No silently-computed reading.** A name the tier cannot evaluate is shown as
  unreadable, never as `Still running`. A tier whose library did not load renders a tier-level
  null, never a board of "nothing to do".
- **G-5 · Colour still means wear, and only wear.** Tiers carry no hue. The maturation ramp is
  not extended, not re-keyed, and does not flip under 红涨绿跌. The ATRZ row figure is
  **non-directional** and takes neutral ink.
- **G-6 · EN/ZH parity, ZH written as Chinese.** Every string in §4 present in both. No `t()`
  and no CJK in any attribute (`scripts/check_title_i18n.py`); tips ride `data-tip-en` /
  `data-tip-zh`.
- **G-7 · No banned vocabulary.** No `validated`, no falsifier/refutation framing, no study
  names (TOPA, W2, prereg, gauntlet, disjoint, arm, panel), no state enum keys, no raw slugs
  (`r63`, `atrz`, `B2`, `A4`, `RSI`, `ATR`, `MA200`), no bare statistics — **including inside
  hovers**. Checked family by family in §4.11.
- **G-8 · Scale without ranking.** New tiers sort A→Z by ticker. No "strength" order, no rank
  number, no top-N.
- **G-9 · Dark on `:root`, light designed.** Every new surface carries an explicit
  `html[data-theme="light"]` counterpart where a tint or shadow is load-bearing.
  Reduced-motion kill block names every new animated selector **and its pseudo-elements**.
- **G-10 · Weight budget.** The rendered page stays ≤ **400 KB gzipped** on real data
  (tonight's one-tier page is 73 KB). If real three-tier data exceeds it, **stop and return to
  the design lane** — the builder does not invent a cap.

---

## §1 What changes, and what does not

| | W1 (today) | W2b |
|---|---|---|
| Boards | one | three, stacked, narrowest bar first |
| Bar (who is on the board) | implicit, unstated | stated per tier in one plain sentence |
| Libraries / thresholds | one, frozen | one **per tier**, never shared |
| Hero | the wear ladder | **the shelf** (three tiers compared), ladder moves into each tier |
| States per tier | 4 | 4 + an off-ladder **unreadable** group when populated |
| Row figure | `+62%` six-month gain | per tier: six-month · three-month · distance above trend |
| In-group order | six-month gain desc | primary unchanged; new tiers **A→Z by ticker** |
| Scale | 122 rows | roll-up for oversized calm groups, compact rows for oversized aging groups |
| Theme tomography | page-level | unchanged content, relocated inside the primary tier |
| Signature | the high-water rule | **unchanged** — the one bold thing stays the one bold thing |

**Unchanged and not up for reinterpretation:** the H1, the kicker, the maturation ramp and its
four hues, the four state names and stances and sub-lines, the wear ladder's decaying rules,
the high-water sparkline and its rules, the wear marks, the leg copy library, the analog card
body, the backdrop line, the theme tomography markup and copy, the `warm` null hero, every
existing anchor.

---

## §2 The tier model

Three tiers are three answers to *"what counts as a winner?"* — not three severities and not
three confidence levels. The reader's own name lands in whichever bars it clears; it can clear
more than one, and the page says so before it shows a number.

### 2.1 Names and bars (PINNED)

| key | EN name | ZH name | EN bar sentence | ZH bar sentence |
|---|---|---|---|---|
| `primary` | **Big six-month gains** | **半年大涨** | Up 50% or more over six months. | 半年内上涨 50% 或以上。 |
| `r63` | **Fast three-month runs** | **三个月急涨** | Up 35% or more over the last three months. | 近三个月上涨 35% 或以上。 |
| `atrz` | **Far above trend** | **远高于自身均线** | At least six of its own typical daily moves above its 200-day average price. | 股价高出自身 200 日均价的幅度，至少相当于它自己 6 个交易日的正常波动。 |

The near-high condition is **common to all three** and therefore stated **once**, in the hero
(Law 4 — a constant belongs in one place):

> Every name here is within 10% of its highest close in the past year.
> 这里的每一只个股，收盘价都在过去一年最高收盘价的 10% 以内。

**Why these names.** Each names the *bar*, not the machinery, and each is something a holder
can check about their own stock without a calculator. "Far above trend" is the honest short
form of a distance measured in the name's own daily range; the sentence under it supplies the
unit once, so the row figure `7.2×` needs no second explanation. ZH uses 均线 (moving average)
because that is the everyday Chinese market word for the thing the bar is measured from; 乖离
was rejected — it names a specific percentage-based CN indicator this bar is not.

**Why no tier colour.** On this page colour means wear. A tier hue would be read as severity
within three seconds and would put two colour systems on one row. Tiers are distinguished by
**position, name and size** only.

**Order of tiers:** fixed, `primary → r63 → atrz`, narrowest bar first. It is the order in
which each bar admits more names, it is stated in the shelf by bar width, and it is not a
ranking. Never re-order by count, by wear share, or by anything nightly.

### 2.2 The ATRZ cohort-honesty banner (required by the mandate)

Renders directly under the `atrz` bar sentence, above its ladder, on every state of that tier
including its nulls. Never on the other two.

> **A mixed group.** The bar is set in each name's own trading range, so a slow, steady name
> can clear it without a big gain. Everything below reads a name against the others in this mix.
>
> **这是一个混合分组。** 门槛按每只个股自身的波动幅度来定，因此走势平稳、涨幅不大的个股也可能入选。下面的每一项判读，都是在这个混合分组内部相互比较得出的。

Hard budget: **two sentences, ≤ 35 EN words.** Quiet inset, neutral border and wash — it takes
no ramp hue, because a tinted banner reads as an alarm and this is a disclosure, not a warning.

---

## §3 Layout and navigation

**Decision: stacked tier sections on one page, with a shelf in the hero — not tabs, not three
pages.** Grounds, in order:

1. The page ships **no page JS** by law (W1 §7). Tabs would need JS or a `:target`/checkbox
   hack, and `:target` already belongs to the group anchors.
2. Three pages would triple the chrome, add three nav rows, and force the reader to guess
   which page their name is on. One page keeps one identity, one as-of, one backdrop, one
   footnote.
3. The overlap fact — *a name can be in more than one group* — is only legible when the three
   are visibly one board. On three pages it becomes a footnote nobody reads.
4. Length is handled by §3.3, which removes rows that carry no reading rather than hiding
   rows that do.

### 3.1 Page shape

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [ shared product nav — _site_nav.html.j2, verbatim include, no local header ] │
├──────────────────────────────────────────────────────────────────────────────┤
│ WINNER HEALTH                                            Priced 2026-07-02   │
│ Has your winner changed character?                    Re-read every night    │
│ US names near their highs, grouped by how the move is aging.                 │
│                                          Prices are 26 sessions behind  (·)  │
│                                                                              │
│ ╭─ HERO: THE SHELF ──────────────────────────────────────────────────────╮   │
│ │ Three kinds of winner, each read against its own history.  (?)         │   │
│ │ A name can be in more than one, so these counts do not add up.         │   │
│ │ Every name here is within 10% of its highest close in the past year.   │   │
│ │                                                                        │   │
│ │ Big six-month gains                                      122 names     │   │
│ │ Up 50% or more over six months                     86 of 122 aging     │   │
│ │ ▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒░▓▓▓▓▓▓▓                                                │   │
│ │ ─────────────────────────────────────────────────────────────────────  │   │
│ │ Fast three-month runs                                    295 names     │   │
│ │ Up 35% or more over the last three months         181 of 295 aging     │   │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒░░░░▓▓▓▓▓▓▓▓▓                              │   │
│ │ ─────────────────────────────────────────────────────────────────────  │   │
│ │ Far above trend                                          848 names     │   │
│ │ At least six of its own typical daily moves above    512 of 848 aging  │   │
│ │ its 200-day average price                                              │   │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒░░░░░▓▓▓▓▓▓▓▓▓ │   │
│ ╰───────────────────────────────────────────────────────────────────────╯   │
│                                                                              │
│ BACKDROP  the index is holding up while its leaders are being sold  (?)      │
│                                                                              │
│ ══ Big six-month gains ═════════════════════════════════════════ (?) ══      │
│ Up 50% or more over six months                                               │
│  36  Still running       ─────────────────────────  Nothing to do            │
│  42  Showing wear        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  Watch — don't chase      │
│   5  Thinning out        · · · · · · · · · · · · ·  Watch closely            │
│  39  Character changed   ──  ─   ──   ─  ──   ─ ──  Worth a review           │
│                                                                              │
│ How much of each theme is aging   Counts only — the bar width is the size…   │
│  AI Semiconductors  7 of 19   ▓▓▓▓▓▓▓▒▒▒░░▒                                  │
│                                                                              │
│ BIG SIX-MONTH GAINS · Still running ──────────────────────────  36 names ◄sticky
│ ● Nothing to do   Big gains, still close to their highs…                     │
│  NVDA  +62%  ╌╌╌╌╌  ▮▯▯  sitting at its high            41 like this         │
│  …                                                                           │
│                                                                              │
│ ══ Fast three-month runs ═══════════════════════════════════════ (?) ══      │
│ Up 35% or more over the last three months                                    │
│  [ladder]                                                                    │
│  … 4 groups, rows sorted A→Z, +41% / THREE MONTHS …                          │
│                                                                              │
│ ══ Far above trend ═════════════════════════════════════════════ (?) ══      │
│ At least six of its own typical daily moves above its 200-day average price  │
│ ┌ A mixed group. The bar is set in each name's own trading range, so a slow, │
│ │ steady name can clear it without a big gain. …                             │
│  [ladder]                                                                    │
│  ─────────────────────────────────────────────────────────────────           │
│   4  Not enough to compare  ───────────────────────  No read tonight  ◄off-ladder
│                                                                              │
│  FAR ABOVE TREND · Still running ──────────────────────────────  512 names   │
│  ● Nothing to do   Big gains, still close to their highs…                    │
│  Not listed one by one — nothing has slipped on any of them tonight.  ◄roll-up
│                                                                              │
│  FAR ABOVE TREND · Showing wear ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  284 names     │
│  ABBV  +9%  ▮▮▯  hotter than most like it · swings…      40 like this ◄compact
│                                                                              │
│ ──────────────────────────────────────────────────────────────────────────   │
│ US names only — the library counts are what similar past runs did …          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component hierarchy

```
body
├── _site_nav.html.j2                 (shared product family — never a local header)
├── lens.lens_css()
└── .wrap
    ├── .pghead                       kicker · h1 · sub · as-of (+ .lag chip)
    ├── .hero  |  .nullhero           THE SHELF  |  the `warm` null (page-level only)
    │   └── .shelf > a.sh-row × 3     name · count · bar sentence · summary · honest-width bar
    ├── .backdrop                     unchanged
    └── section.tier × 3              id="t-{tier}"
        ├── .tier-hd                  h2 name · lens(?)
        ├── .tier-def                 the bar sentence
        ├── .mixnote                  ATRZ only
        ├── .ladder                   4 rungs + optional off-ladder .rung.m0
        ├── .sec.themes               PRIMARY TIER ONLY (relocated, content unchanged)
        ├── .tnull                    when the tier is empty / clear / unread
        └── .sec.grp.m1…m4[, .m0] × N sticky header (with tier kicker) · stance · rows
            └── .row × N  |  .rollup
```

### 3.3 Scale, without ranking

**Order inside a group.** `primary` keeps six-month-gain-descending (frozen, disclosed as a
past fact). `r63` and `atrz` sort **A→Z by ticker**. Grounds: on a 500-row group the reader is
looking for *their* name, and alphabetical is the only order that finds it in seconds; and
"most stretched first" would make the top row a de-facto pick on a page that insists it ranks
nothing. Each tier states its own order in its `?` card.

**One number governs scale: 55 rows.**

| Group | ≤ 55 rows | > 55 rows |
|---|---|---|
| `Still running` (stance *Nothing to do*) | full rows, as today | **roll-up** — header, stance and count only, plus one line: *"Not listed one by one — nothing has slipped on any of them tonight."* No rows. |
| the three aging groups + `Not enough to compare` | full rows | **compact rows** — identical row, minus the sparkline cell only. Words, wear marks, hovers and the library card all stay. |

Why the calm group rolls up and the aging groups never do: absence from *Still running* is
itself the complete reading ("nothing has slipped on it"), so listing 500 such names adds a
picture and no information. Absence from *Character changed* is not a reading — a holder must
be able to find their name there, so those rows always render. The picture is what gets
dropped under load, never the reading.

On tonight's real primary board (36 / 42 / 5 / 39) **nothing changes** — every group is under
55. The rule only ever fires on the new tiers.

The dropped sparkline is disclosed once, in the tier `?` card (§4.3), never as a note beside
the rows.

### 3.4 Anchors

Existing anchors are a live contract (the hero rungs link to them; outside links may exist),
so the primary tier keeps them exactly:

| | tier section | groups |
|---|---|---|
| `primary` | `#t-six-month` | `#g-running` `#g-wear` `#g-thinning` `#g-changed` (**unchanged**), `#g-noread` |
| `r63` | `#t-three-month` | `#three-month-running` `#three-month-wear` `#three-month-thinning` `#three-month-changed` `#three-month-noread` |
| `atrz` | `#t-above-trend` | `#above-trend-running` … `#above-trend-noread` |

Shelf rows link to `#t-*`; each tier's rungs link to that tier's group ids.

### 3.5 Orientation inside a long page

Twelve sticky group headers stack down the page, so each one carries a **tier kicker** —
`FAR ABOVE TREND · Showing wear ─ ─ ─ ─ 284 names`. It is one token per group header (twelve
on the page), not per row, and it answers the only question a reader can lose while scrolling.
No second sticky band, no per-row tier badge, no cross-tier state badge on any row.

### 3.6 Responsive / motion / a11y

- **≤820px:** rows keep the existing card collapse. Compact rows drop the spark cell and the
  existing mobile placements continue to work unchanged (`.c-legs` row 2, `.c-lib` row 3).
- **Shelf on mobile:** name / count on line 1, bar sentence on line 2 (summary drops beneath
  it), honest-width bar spanning line 3. No horizontal scroll at 390px.
- **Motion:** no new animation. `.sh-row` has a background transition and therefore joins the
  reduced-motion kill block **with its pseudo-elements** (§7.6).
- **Keyboard:** shelf rows are `<a>` (natively focusable, visible `:focus-visible` ring);
  every `?` and hover term stays on the site LENS, which wires `tabindex`/`role`/`aria`.
- **Screen readers:** the honest-width bars are `aria-hidden` (the counts beside them carry the
  same fact); `aria-label`s stay static English (house allowance).

---

## §4 Copy — complete tables (this is binding; the builder writes no new user-facing string)

`t(en, zh)` is the page's dual-span macro. Tips ride `data-tip-en` / `data-tip-zh` or the LENS.
**No `t()` and no CJK in any attribute.**

### 4.1 Page furniture (deltas only — every other W1 §4.1 string is unchanged)

| Slot | EN | ZH |
|---|---|---|
| Sub (**revised**) | US names near their highs, grouped by how the move is aging. | 处于高位附近的美股，按行情老化的程度分组。 |
| Tape-lag chip | Prices are **{n}** sessions behind | 价格落后 **{n}** 个交易日 |
| Tape-lag tip (Tier 2) | The board reads the last complete price tape we have. It is {n} sessions behind the market, so tonight's read describes that tape, not today's prices. | 看板读取的是我们手上最后一份完整的行情数据，它比市场落后 {n} 个交易日；今晚的判读描述的是那份数据，而不是今天的价格。 |

The sub changed because the old one ("sitting on big gains near their highs") is now **false**
for two of the three groups — a steady name can be far above its own trend without a big gain.
This is the only line of W1 page furniture that had to move.

### 4.2 The hero shelf

| Slot | EN | ZH |
|---|---|---|
| Lede (bold) | Three kinds of winner, each read against its own history. | 三类赢家，各自对照自身历史来判读。 |
| Lede (quiet) | A name can be in more than one, so these counts do not add up to a total. | 同一只个股可能同时属于多类，因此这些数字不能相加。 |
| Shared bar clause | Every name here is within 10% of its highest close in the past year. | 这里的每一只个股，收盘价都在过去一年最高收盘价的 10% 以内。 |
| Row count | **{n}** names | **{n}** 只 |
| Row summary | **{mat}** of them aging | 其中 **{mat}** 只在老化 |
| Row summary — none aging | none aging tonight | 今晚没有在老化的 |
| Row summary — empty tier | none in this group tonight | 今晚该分组暂无个股 |
| Row summary — unread tier | not read tonight | 今晚未判读 |

"Aging" is the umbrella verb for *watch + thinning + changed* across the whole page (it is
already the page's own word — "how the move is aging"). W1's hero sentence used "showing wear"
as both the umbrella and a state name; the shelf retires that ambiguity, and `Showing wear`
now names one state and nothing else.

The summary is *"86 of them aging"*, not *"86 of 122 aging"*: the total sits on the same line,
two columns away, and repeating it reads as a stutter — visible the moment the shelf was
rendered. ZH follows the same logic with 其中.

**Hero `?` — LENS `define`, `ill=lens.ILL_LANES`**

| slot | EN | ZH |
|---|---|---|
| kick | How this board is built | 这块看板是怎么来的 |
| title | Three groups, one question | 三个分组，同一个问题 |
| row 1 *(info)* · Who is here | 谁在这里 | Every US name within 10% of its highest close in the past year that also clears one of the three bars. | 所有收盘价在过去一年最高收盘价 10% 以内、并且达到三道门槛之一的美股。 |
| row 2 *(info)* · Counted apart | 分开计数 | A name can clear more than one bar, so it can appear in more than one group. The counts are never added together. | 同一只个股可能同时达到多道门槛，因此可能出现在多个分组里。各组数字从不相加。 |
| row 3 *(warn)* · Not a call | 不是判断 | A group describes how a move is behaving today. It is not a call, a target, or a reason to do anything on its own. | 分组描述的是当下走势的状态。它不是判断、不是目标价，本身也不构成采取任何行动的理由。 |
| receipt | display only · no rank, gate or position size | 仅供展示 · 不参与排序、准入或仓位 |

### 4.3 Tier heading and its `?` card

Heading = the tier name (§2.1); the line under it = the tier's bar sentence (§2.1).

**Tier `?` — LENS `define`, `ill=lens.ILL_LANES`. Hard budget: 4 rows, ≤95 words total.**

| slot | EN | ZH |
|---|---|---|
| kick | About this group | 关于这个分组 |
| title | {tier EN name} | {tier ZH name} |
| row 1 *(info)* · The bar | 入选门槛 | *(primary)* Up 50% or more over six months, and within 10% of its highest close in the past year. | 半年内上涨 50% 或以上，且收盘价在过去一年最高收盘价的 10% 以内。 |
| | | *(r63)* Up 35% or more over the last three months, and within 10% of its highest close in the past year. | 近三个月上涨 35% 或以上，且收盘价在过去一年最高收盘价的 10% 以内。 |
| | | *(atrz)* At least six of its own typical daily moves above its 200-day average price, and within 10% of its highest close in the past year. | 股价高出自身 200 日均价的幅度至少相当于它自己 6 个交易日的正常波动，且收盘价在过去一年最高收盘价的 10% 以内。 |
| row 2 *(info)* · The order | 排列顺序 | *(primary)* Inside a group, the largest six-month gain comes first. That is a fact about the past — not a ranking. | 每组内部按半年涨幅从大到小排列。那只是关于过去的事实 —— 不是排名。 |
| | | *(r63 / atrz)* Inside a group, names run A to Z by ticker so you can find yours. That is not a ranking either. | 每组内部按代码 A 到 Z 排列，方便你找到自己的持仓。这同样不是排名。 |
| row 3 *(info)* · Its own history | 自己的历史 | Every mark here is cut from past runs that also cleared this group's bar — never from another group's. The same name can read differently in another group. | 这里的每一条标准，都取自同样达到本组门槛的历史行情 —— 绝不取自其他分组。同一只个股在另一个分组里，可能读出不同的结果。 |
| row 4 *(warn)* · What is not read here | 这里不看什么 | *(primary)* A few checks need a longer price history than some names have. Where a check cannot be made, it is not counted as clear — it is simply not counted. | 有几项检查需要较长的价格历史，部分个股并不具备。无法完成的检查不会被当作「没问题」，它只是没有计入。 |
| | | *(r63)* How much a name gained over the past year is left out here — in runs like these it is too weak to lean on. Where any other check cannot be made, it is not counted as clear either. | 个股过去一年的涨幅在这里不予采用 —— 在这类行情中它太弱，不足以依靠。其他检查若无法完成，同样不会被当作「没问题」。 |
| | | *(atrz)* How much a name gained over the past year is left out here — in runs like these it points the other way. Where any other check cannot be made, it is not counted as clear either. | 个股过去一年的涨幅在这里不予采用 —— 在这类行情中，它指向的方向是相反的。其他检查若无法完成，同样不会被当作「没问题」。 |
| body *(only when this tier has a compact group)* | In a very large group the small price chart is left off so the page stays quick — the words beside each name are the same. | 分组很大时，会略去名字旁边的小价格图，以保持页面轻快 —— 文字部分完全相同。 |
| receipt | display only · no rank, gate or position size | 仅供展示 · 不参与排序、准入或仓位 |

Row 4 **is** the mandate's "quiet receipt" for the excluded long-run-run-up check. It says what
is not read and why, in words a non-quant reads correctly, and it never names the check.

### 4.4 Groups

The four W1 states — names, ZH names, stances, sub-lines — are **unchanged on every tier**
(W1 §4.2 table stands verbatim). One group is added:

| contract key | EN name | ZH name | EN stance | ZH stance | EN sub-line | ZH sub-line |
|---|---|---|---|---|---|---|
| `no_read` | **Not enough to compare** | **无可比样本** | No read tonight | 今晚不作判读 | On the board, but with no similar past runs in this group to read them against. | 它们在看板上，但本分组内没有可供对照的相似历史行情。 |

| Slot | EN | ZH |
|---|---|---|
| Group header count | **{n}** names | **{n}** 只 |
| Group header tier kicker | {TIER NAME, uppercase} | {分组名} |
| Roll-up line | Not listed one by one — nothing has slipped on any of them tonight. | 不逐只列出 —— 今晚它们没有任何环节转弱。 |

### 4.5 Row cells

| Cell | primary | r63 | atrz |
|---|---|---|---|
| figure | `+62%` directional ink | `+41%` directional ink | `7.2×` **neutral ink** |
| caption EN | IN SIX MONTHS | THREE-MONTH | ABOVE TREND |
| caption ZH | 近六个月 | 近三个月 | 高于均线 |
| missing value | `—` (unchanged honest dash) | `—` | `—` |

**AMENDED 2026-08-11 (commissioning-session ruling).** The r63 caption was pinned as
`IN THREE MONTHS` and shipped that way in the W2b build, where it reproduced the very
defect §14.1 records: 15 characters wrap the 92px column, and the build measured the
caption at **31px (two lines) against primary's 16px**, taking the row from 64px to 79px.
Re-pinned to **`THREE MONTHS`** — 12 characters, inside §14.1's ≤13-char limit, and it
keeps the spelled-word family parallel with `IN SIX MONTHS` rather than abbreviating to
`IN 3 MONTHS`. Dropping the preposition is the smallest edit that fits the column; the
window is already unambiguous beside a figure. The ZH caption is unchanged — 近三个月 is
four glyphs and sets on one line (measured: 16px, row 64px).

**STILL WRAPS — the ≤13-character rule is the wrong proxy (measured 2026-08-11).**
`THREE MONTHS` renders **92px in a 92px column** and still breaks to two lines
(38px `THREE` + 51px `MONTHS`), so the r63 row stays 79px against primary's 64px. The
constraint is RENDERED WIDTH, not character count, and the two disagree exactly in the
range these captions occupy: `IN SIX MONTHS` is *13* characters but only **90px**
because `I` and `X` are narrow, while `THREE MONTHS` is *12* characters of uniformly
wide capitals. Any future caption for this cell must be measured, not counted.

Measured at 10px / 600 / 0.8px letter-spacing, uppercased, in the live cell — the
options that FIT, for the design lane to choose from (this builder did not pick one):

| candidate | px | fits 92px | keeps the spelled-word family |
|---|---|---|---|
| `3 MONTHS` | 62 | yes | no |
| `IN 3 MONTHS` | 78 | yes | no (keeps the preposition) |
| `THREE-MONTH` | 87 | yes | **yes** (hyphenated adjective form) |
| `3-MONTH GAIN` | 89 | yes | no |
| `THREE MONTHS` *(current pin)* | 92 | **no** | yes |
| `LAST 3 MONTHS` / `PAST 3 MONTHS` | 95 | no | no |
| `IN THREE MONTHS` *(original)* | 108 | no | yes |

Note also that `IN SIX MONTHS` clears by only **2px**, so the primary caption is itself
one font-stack change away from the same defect (recorded as a watch item in §14.6).

**AMENDMENT II — 2026-08-11 (commissioning-session ruling, supersedes the re-pin above).**
The r63 caption is **`THREE-MONTH`**, measured **87px** in the 92px column: single line,
caption 16px, row 64px, matching primary and atrz. Chosen from the measured table above as
the one fitting candidate that keeps the spelled-word family — the elided noun is standard
finance shorthand under a gain figure, and it holds the bar sentence's own three-month
vocabulary rather than introducing "quarter". `THREE MONTHS` (92px) is superseded and must
not be reinstated: it is *shorter in characters* than the caption that fits, which is
precisely the trap §14.5 records. ZH remains 近三个月, unchanged and single-line.

The trend distance is a **distance, not a direction** — it is ≥6 by construction, so directional
ink would print a permanent green (permanent red in ZH) that means nothing. Neutral ink,
tabular figures, one decimal. The caption is `ABOVE TREND`, not `ABOVE ITS TREND`: the longer
form wraps to two lines in the 92px figure column and breaks the row's baseline (measured —
§14.1). The unit ("its own typical daily moves") is supplied once by the tier's bar sentence,
so the short caption is complete.

| Slot | EN | ZH |
|---|---|---|
| No-legs fallback (unchanged) | sitting at its high · {x}% under its high | 正处于自身高点 · 低于自身高点 {x}% |
| Unreadable row, legs cell | no similar runs to compare | 没有可比的历史行情 |
| Unreadable row tip (Tier 2) | Only {k} of the {m} checks this group makes could be made on this name, so the board does not place it in a state. | 本分组的 {m} 项检查中，只有 {k} 项能在这只个股上完成，因此看板不给它归入任何状态。 |

An unreadable row renders **no wear marks at all**. Three empty outlined slots mean "measured
and clear" on this page (W1 §2.5) and would be a lie here; nothing measured, nothing drawn.
The sparkline still renders — it is a picture of price, not a reading.

### 4.6 Legs — deltas to the W1 §4.3 library

The ten existing legs keep their exact `words_*` and `tip_*` copy on every tier. Two additions:

**(a) One new leg, on the new tiers only.**

| key | `words_en` | `words_zh` |
|---|---|---|
| `running_hot` | hotter than most like it | 热度高于同类多数 |

| | Tier-2 tip |
|---|---|
| EN | Its recent buying pressure sits above the level nine in ten days reached in past runs here that kept going. In this group's history, runs that later topped out ran hotter than those that carried on — history, not a forecast. |
| ZH | 它近期的买盘热度，高于本分组历史行情中「后来继续上行」那一批十分之九的交易日。在本分组的历史里，后来见顶回落的行情，热度普遍高于继续上行的行情 —— 这是历史，不是预测。 |

**(b) A provenance sentence appended to every leg tip**, because the mandate requires each
receipt to name its own tier's library:

| case | EN suffix | ZH suffix |
|---|---|---|
| library-cut legs (`rs_peak_lag`, `rs_decel`, `effort_result`, `updown_volume`, `vol_asymmetry`, `late_verticality`, `episode_age`, `running_hot`) | Cut from past runs in **{tier name}** only — never from another group's history. | 这一标准只取自「{tier ZH name}」分组内的历史行情 —— 不使用其他分组的历史。 |
| fixed-rule legs (`dip_unreclaimed`, `below_50d`, `drawdown_from_high`) | This is a fixed rule, the same in every group. | 这是一条固定规则，各分组通用。 |

The second row matters as much as the first: three legs are fixed rules cut from no library at
all, so they are not a cross-tier threshold reuse — and the surface says which is which rather
than letting a reader assume.

**Leg key order.** The frozen W1 order is unchanged for the ten shared legs. On `r63` and
`atrz`, `running_hot` is inserted **first**, ahead of them. This is a display order, not a
severity ranking — the same reasoning as the W1 `breaking` lead-leg amendment: it is the one
check these groups' own history actually speaks to, and appended last it would be cut by the
three-leg cap on every busy row, which is a check made and never shown. `MAX_LEGS` stays 3;
the `breaking` lead pair still leads on `breaking` rows.

### 4.7 Analog card

Body, honest-N floor, `no match` and receipt are unchanged (W1 §4.4). Two deltas:

| Slot | EN | ZH |
|---|---|---|
| Note, appended (prose, `.lensx-note` — **never** the nowrap receipt) | Matched only against past runs that also cleared this group's bar. | 只与同样达到本组门槛的历史行情做匹配。 |
| `no match` tip (**revised**) | No past run in this group's library is close enough in shape and age to show a count. | 本分组的资料库里，没有在形态和运行时长上足够接近的历史行情，因此不显示次数。 |

`library.window_start` / `window_end` in the receipt come from **that tier's** library, so the
`WINDOW` row is already per-tier once the contract nests it (§8). W1 §9.3 stands: the receipt
takes short tokens only — the tier disclosure is prose.

### 4.8 Tier-level states

Each tier independently resolves to one of: `board` · `clear` · `none` · `unread`. The
page-level `warm` hero (no artifact at all) is unchanged and pre-empts all of them.

| mode | trigger | Eyebrow | Heading EN / ZH | Body EN / ZH | Stance EN / ZH |
|---|---|---|---|---|---|
| `clear` | names present, `watch+thinning+breaking+no_read == 0` | {tier name} | Nothing is aging in this group tonight / 今晚该分组没有行情走向老化 | All **{n}** names here still look the way they did. An empty list is a reading, not a gap. / 这里的 **{n}** 只个股仍与此前一样。列表为空本身就是一个判读结果，不是数据缺失。 | **Nothing to do** — a name moves down this list on its own, the night something slips. / **无需动作** —— 一旦某只个股出现转弱，它当晚就会自己出现在下面。 |
| `none` | tier has zero names | {tier name} | No name is in this group tonight / 今晚该分组没有个股 | Out of **{universe_n}** US names screened, none clears this group's bar tonight. / 在筛查的 **{universe_n}** 只美股中，今晚没有一只达到该分组的门槛。 | **Nothing to watch** — names appear here on their own, the night they qualify. / **暂无可观察对象** —— 一旦有个股符合条件，它当晚就会自己出现在这里。 |
| `unread` | `readable == false` | {tier name} | This group was not read tonight / 今晚未对该分组作判读 | The history this group is measured against did not load, so nothing is shown for it. Nothing is being withheld, and the other groups are unaffected. / 该分组所对照的历史资料本次未能载入，因此这里不显示任何内容。没有任何内容被隐藏，其他分组不受影响。 | **Nothing to read here tonight** / **今晚此处无可判读** |

`clear` still renders that tier's `Still running` group below the band, so a quiet tier is
never blank. **The page-scale flatline signature renders only when all three tiers are clear**
— once per page at most, so the quiet-night picture stays rare and stays memorable.

### 4.9 Small print — ONE merged line (revised)

| | |
|---|---|
| EN | US names only — the library counts are what similar past runs did, history rather than forecasts, and nothing on this page ranks, gates or sizes anything. Each group is measured only against its own history, and the counts never add up to a total. Tonight: **{universe_n}** US names screened, read **{asof}**. A name that has just left a group stays listed there only while we read the change; a name you cannot find anywhere on this page did not clear any of the three bars. |
| ZH | 仅限美股 —— 资料库中的次数是历史上相似行情走过的路，属于历史而非预测；本页任何内容都不参与排序、准入或仓位。每个分组只对照自己的历史来衡量，各组数字不能相加。今晚：筛查 **{universe_n}** 只美股，判读日期 **{asof}**。刚离开某个分组的个股，仅在我们判读这一变化期间保留在该组；在本页任何地方都找不到的个股，说明它今晚没有达到这三道门槛中的任何一道。 |

`extended_n` leaves the small print — it is now per tier and lives on the shelf. The
board-membership sentence is re-scoped from "the extended band" to "a group" because each tier
has its own band; the 21-session window itself is untouched.

### 4.10 States enumerated (the complete matrix a reviewer checks)

| # | State | Where it renders |
|---|---|---|
| 1 | page `warm` — no artifact / stale artifact | existing `.nullhero`, unchanged, pre-empts everything |
| 2 | tier `board` — populated | ladder + groups |
| 3 | tier `clear` — names, none aging | `.tnull` + `Still running` group |
| 4 | tier `none` — zero names | `.tnull` only |
| 5 | tier `unread` — library did not load | `.tnull` only; other tiers unaffected |
| 6 | group populated ≤55 | full rows |
| 7 | group `Still running` >55 | roll-up line |
| 8 | group aging >55 | compact rows |
| 9 | row unreadable | `no_read` group, no wear marks, plain-word cell + tip |
| 10 | row with no analog | `no match` + revised tip |
| 11 | row with thin library (n<12) | unchanged honest-N floor copy |
| 12 | row with no history (<3 closes) | unchanged `no history` |
| 13 | recently-EXT, breaking-only | renders as any `breaking` row; disclosed once in the small print; `{x}% off its high` is its own receipt |
| 14 | stale tape | `.lag` chip in the as-of block + tip |
| 15 | ATRZ mixed-cohort banner | every state of that tier, including 3/4/5 |
| 16 | all three tiers clear | page-scale flatline, once |

### 4.11 Banned-vocabulary check log

Every new string in §4 was read against the doctrine Law-2 families, the W1 §0 G-G list, and
the hover-specific list (hovers get their own pass — a receipt is not a licence).

| Family | Verdict on the new copy |
|---|---|
| Internal study / program names (TOPA, W2, prereg, gauntlet, arm, panel, disjoint, roster, lobe, organ) | **Absent everywhere**, including all hovers. The mandate's own vocabulary never reaches the page: "arms" became *groups*, "disjoint panel" became *this group's history*, "cohort" became *mix*. |
| Feature / state enum keys and raw slugs (`r63`, `atrz`, `B2`, `A4`, `C6`, `D1`, `D3`, `F1`, `extended_healthy`, `no_read`, `running_hot`) | **Absent from all rendered text.** They exist only as contract keys and CSS/anchor slugs. Anchors use plain words (`#t-three-month`, `#above-trend-wear`). |
| Untranslated statistics (RSI, ATR, MA200, z-score, P90, n=, CI, q≤, base rates as bare percentages) | **Absent.** "P90 of matched-continued days" became *"above the level nine in ten days reached in past runs here that kept going"*; "(c−MA200)/ATR63 ≥ 6" became *"at least six of its own typical daily moves above its 200-day average price"*. The one surviving indicator name is **50-day line** in the frozen W1 leg, which the doctrine already sanctions as ordinary market English. |
| Falsifier / refutation framing (falsified, refuted, 证伪, "the thesis failed", "did not replicate", "reversed") | **Absent front-facing.** The reversal that drives the ATRZ exclusion is stated as *"in runs like these it points the other way"* — a description of the check, not a verdict, and never the word *reversed*. |
| `validated` (CI-guarded) | **Absent.** No new string claims validation, calibration, prediction, or research status; the new leg's tip ends *"history, not a forecast"*. |
| Authority / promotion language (registered, calibrated, discriminator, researched, predictive, edge, signal) | **Absent from all rendered text.** The primary board's registered-discriminator status is deliberately NOT surfaced on the new tiers (§5) — and it is not surfaced on the primary tier either, which is unchanged. |
| Imperative trade language (buy, sell, short, trim, exit, target, size) | **Absent.** Stances stay in the sanctioned set plus W1's `Worth a review`; the two new stances (`No read tonight`, `Nothing to read here tonight`) claim nothing. |
| Spin vocabulary (giveback, dead-cat, bounce, breakdown, collapse, panic) | **Absent.** |
| Numbers without meaning (Law 3) | Every new figure arrives with its interpretation: `7.2×` carries `ABOVE ITS TREND` plus a bar sentence that supplies the unit once; `{k} of {m} checks` is a sentence, not a ratio; `{mat} of {n} aging` is a sentence; the shelf bar is width-honest and `aria-hidden`. |
| Word budgets (Law 4) | Tier names ≤4 words. Bar sentences one sentence. Group sub-lines ≤16 words. Banner ≤35 words, two sentences. Tier `?` ≤4 rows / ≤95 words. One as-of, one lag chip, one footnote, one tomography, one flatline. No constant repeated per row: the tier name appears on group headers (12×), never on rows. |
| ZH shape (English-shaped translation is a defect) | Written as Chinese, not mapped word-for-word: 半年大涨 / 三个月急涨 / 远高于自身均线 use CN market vernacular; 均线 not a coined term for "trend"; 乖离 deliberately rejected as a different, percentage-based indicator; 判读 / 看板 / 分组 / 门槛 reuse the page's established ZH vocabulary rather than inventing a second word per concept. |
| 红涨绿跌 | The only new figure is non-directional and takes neutral ink, so nothing new participates in the swap; the ramp is untouched. |

---

## §5 Leg ruling table (leg × tier)

Counting rule unchanged: 1 counting leg → *Showing wear*; 3 → *Thinning out*; the two
structural legs together → *Character changed*. `episode_age` never counts, on any tier.

| Leg (as the reader sees it) | primary | r63 | atrz | Grounds (one line) |
|---|---|---|---|---|
| lagging the market for {n} sessions | counted · frozen threshold | counted · **tier-cut** | counted · **tier-cut** | descriptive fact about the name's own behaviour; no cross-tier claim is made or needed, and its threshold is re-cut from this group's history |
| leadership fading | counted · frozen | counted · tier-cut | counted · tier-cut | same |
| more volume, less progress | counted · frozen | counted · tier-cut | counted · tier-cut | same |
| selling days now heavier | counted · frozen | counted · tier-cut | counted · tier-cut | the one registered discriminator on the primary board; on both new tiers the widened cohorts could not resolve it either way (their intervals still contain the original effect) — power-limited, **not** shown absent, so it keeps counting at each tier's own threshold and its hover carries no registered-discriminator language |
| swings getting wider | counted · frozen | counted · tier-cut | counted · tier-cut | descriptive; the differently-defined range ratio that failed to confirm on the wide tier is not this measure and licenses no claim here |
| went vertical late | counted · frozen | counted · tier-cut | counted · tier-cut | descriptive; its forward excess on the widened cohorts is negative-to-flat, which is consistent with the page's AVOID-tier reading and adds no authority |
| dip not bought back | counted · **fixed rule** | counted · fixed rule | counted · fixed rule | a fixed rule, cut from no library — not a reused threshold. Its family's coverage is thin on the widened cohorts, so where it cannot be measured it is **not** counted as clear (disclosed in the tier `?`) |
| lost its 50-day line | counted · fixed rule | counted · fixed rule | counted · fixed rule | fixed rule (3 sessions), no threshold to reuse; structural half of the terminal state |
| {x}% off its high | counted · fixed rule | counted · fixed rule | counted · fixed rule | fixed rule (−10%), no threshold to reuse; structural half of the terminal state |
| running {n} months | **context only** · frozen | **context only** · tier-cut | **context only** · tier-cut | never counts (W1 law). Its typical size differs by roughly eightfold between the two new cohorts, so its threshold MUST be re-cut per tier or the sentence would be wrong; and its mechanical counter-explanation is undischarged, a second reason it never counts |
| **hotter than most like it** *(new)* | **not rendered** | **counted** · tier-cut | **counted** · tier-cut | the only check the widened cohorts confirmed on both, at their own thresholds. Absent from the primary tier because that board is frozen by the no-regression constraint — a difference the tier `?` discloses ("the same name can read differently in another group") |
| **long-run run-up** *(candidate)* | not a leg | **NOT introduced** | **NOT introduced** | ATRZ: it **reverses** in this cohort — a leg pointing the other way would print a false reading. R63: it attenuates past the point of leaning on it. Excluded with the plain-word receipt in the tier `?` row 4. |
| **short-range ratio · volume-z** *(candidates)* | not legs | **NOT introduced** | **NOT introduced** | power-limited non-confirmations. A null that could not be resolved is not a licence to add a new mark to a reader's row; the surface adds a leg only where the tier's own history speaks. |

**The single hardest rule, restated:** no threshold crosses a tier boundary. A leg that cannot
have its threshold cut for a tier does not fire on that tier — it is never borrowed from
another, and its silence contributes to the unreadable rule in §6, never to a clean reading.

---

## §6 No-analog and unreadable states — exact rules

Three distinct absences, three distinct treatments. They are not interchangeable and the
builder may not collapse them.

| # | Absence | Today | W2b |
|---|---|---|---|
| A | **The library has no close match for this name** (analog vector not finite, or no neighbour close enough) | `no match` on the row, state still assigned | unchanged, tip revised to name the group (§4.7) |
| B | **The tier cannot evaluate this name** | *(does not exist — `classify` silently returns "Still running")* | the row goes to the `no_read` group: no wear marks, plain-word cell, Tier-2 tip with {k} of {m} |
| C | **The tier's own library/thresholds did not load** | *(does not exist — every name would read "Still running")* | the whole tier renders `unread` (§4.8). No ladder, no groups, no rows. |

**Rule for B (PINNED):** a name is unreadable on a tier when that tier could evaluate **fewer
than a majority of its counting checks** for it — `checks_evaluated < ceil(checks_total / 2)` —
or when the tier has no threshold for a check the name would otherwise have fired. The engine
lane may raise that floor with evidence; it may never lower it, and it may never route an
unevaluated name into a wear state.

**Why B needs to exist at all:** the current engine returns `{}` for missing thresholds and
`classify([])` returns `extended_healthy`. A tier with a half-loaded library would today print
a confident board of *"Still running · Nothing to do"* for names nobody measured. That is the
exact failure the doctrine's Law 5 exists to prevent, and it is the reason G-4 is an acceptance
gate rather than a nice-to-have.

**Note on scope.** B and C are new mechanisms and they can therefore fire on the primary tier
too. That is a deliberate, argued exception to the no-regression constraint: they only ever
fire in a case where today's page is **wrong**, they change nothing when the read is healthy,
and tonight's artifact produces zero rows in either. Flagged here so the commissioning session
can veto it explicitly rather than discover it.

---

## §7 Markup and CSS — exact deltas

The page is SSR'd by `scripts/build_winner_health_page.py` from
`templates/winner_health.html.j2`; page CSS stays in that template's `<style>` block. There is
no paired `site/` asset and therefore no `check_template_site_sync` obligation.

### 7.1 The shelf

```jinja
<section class="hero rise d1" aria-label="Tonight's groups">
  <div class="hero-lede">
    <span class="l-en"><b>Three kinds of winner, each read against its own history.</b>
      <span class="q">A name can be in more than one, so these counts do not add up to a total.
      Every name here is within 10% of its highest close in the past year.</span></span>
    <span class="l-zh">…</span>
    {{ lens.lens(kind='define', ill=lens.ILL_LANES, kick=…, title=…, rows=[…], receipt=…) }}
  </div>
  <div class="shelf">
    {%- for T in TIERS %}
    <a class="sh-row" href="#t-{{ T.slug }}">
      <span class="sh-nm">{{ t(T.en, T.zh) }}</span>
      <span class="sh-n"><span class="l-en"><b>{{ T.n }}</b> names</span><span class="l-zh"><b>{{ T.n }}</b> 只</span></span>
      <span class="sh-def">{{ t(T.def_en, T.def_zh) }}</span>
      <span class="sh-sum">…{{ T.mat }} of {{ T.n }} aging…</span>
      <span class="sh-bar" aria-hidden="true">
        <span class="bar" style="width:{{ T.w }}%">
          {%- if T.c1 %}<i class="b1" style="flex:{{ T.c1 }}"></i>{% endif %}
          {%- if T.c2 %}<i class="b2" style="flex:{{ T.c2 }}"></i>{% endif %}
          {%- if T.c3 %}<i class="b3" style="flex:{{ T.c3 }}"></i>{% endif %}
          {%- if T.c4 %}<i class="b4" style="flex:{{ T.c4 }}"></i>{% endif %}
        </span>
      </span>
    </a>
    {%- endfor %}
  </div>
</section>
```

`T.w = round(100 * T.n / max(T.n over tiers), 1)`. The honest-width rule from the theme
tomography, one scope up: a 122-name group can never be drawn the width of an 848-name one.
The `no_read` count is **not** a bar segment (it is not a wear state) — it is excluded from the
segments and from `mat`.

```css
/* ── THE SHELF — three kinds of winner, compared honestly ─────────────────── */
.shelf{display:grid;margin:20px 0 0}
.sh-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 20px;
  align-items:baseline;padding:14px 6px 16px;border-top:1px solid var(--hair);
  text-decoration:none;color:inherit;border-radius:10px;transition:background .16s}
.sh-row:first-child{border-top:none;padding-top:4px}
.sh-row:hover{background:color-mix(in srgb,var(--text) 4%,transparent)}
.sh-row:focus-visible{outline:2px solid color-mix(in srgb,var(--link) 70%,transparent);
  outline-offset:2px}
.sh-nm{font-size:15px;font-weight:750;letter-spacing:-.016em;color:var(--text)}
.sh-n{font-size:12px;font-weight:700;color:var(--muted-strong);white-space:nowrap}
.sh-n b{font-variant-numeric:tabular-nums}
.sh-def{font-size:12.5px;color:var(--muted-strong);min-width:0}
.sh-sum{font-size:12px;color:var(--muted);white-space:nowrap}
.sh-sum b{font-variant-numeric:tabular-nums;color:var(--muted-strong);font-weight:650}
.sh-bar{grid-column:1 / -1;margin-top:10px}
.sh-bar .bar{height:10px;border-radius:3px}
@media(max-width:620px){
  .sh-row{grid-template-columns:minmax(0,1fr) auto}
  .sh-sum{grid-column:1;justify-self:start;margin-top:2px}
}
```

### 7.2 Tier section

```jinja
<section class="tier" id="t-{{ T.slug }}" aria-label="{{ T.en }}">
  <div class="tier-hd"><h2>{{ t(T.en, T.zh) }}</h2>{{ lens.lens(…tier card…) }}</div>
  <p class="tier-def">{{ t(T.def_en, T.def_zh) }}</p>
  {%- if T.key == 'atrz' %}<div class="mixnote">…</div>{% endif %}
  …ladder | .tnull…
  {%- if T.key == 'primary' %}…theme tomography, unchanged…{% endif %}
  …groups…
</section>
```

```css
/* ── TIER SECTION — position, name and size distinguish a tier. Never a hue:
      on this page colour means wear, and a tier is not a severity. ────────── */
.tier{margin:48px 0 0;scroll-margin-top:12px}
.tier-hd{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
  border-top:1px solid var(--line);padding-top:20px}
.tier-hd h2{margin:0;font-size:21px;font-weight:800;letter-spacing:-.026em;color:var(--text)}
.tier-def{margin:6px 0 0;font-size:13px;color:var(--muted-strong);max-width:64ch}
.tier .ladder{margin-top:18px}
/* the OFF-LADDER line. The ramp is a wear sequence; "not enough to compare" sits
   outside it, so it takes no ramp hue and no decaying rule — a neutral hairline. */
.rung.m0{--mc:var(--muted);margin-top:8px;padding-top:12px;border-top:1px solid var(--hair);
  border-radius:0 0 9px 9px}
.rung.m0 .rule{background:var(--hair);opacity:1;background-image:none}
/* the mixed-cohort disclosure: quiet inset, NO state tint — a tinted banner reads
   as an alarm, and this is a disclosure. */
.mixnote{margin:16px 0 0;padding:12px 15px;border-radius:11px;max-width:80ch;
  border:1px solid color-mix(in srgb,var(--text) 10%,transparent);
  background:color-mix(in srgb,var(--text) 3.5%,transparent);
  font-size:12.5px;line-height:1.58;color:var(--muted-strong)}
.mixnote b{color:var(--text);font-weight:750}
html[data-theme="light"] .mixnote{background:color-mix(in srgb,var(--text) 4.5%,transparent);
  border-color:color-mix(in srgb,var(--text) 14%,transparent)}
/* tier-level null band — quieter than the page hero, which outranks it */
.tnull{margin:18px 0 0;border:1px solid var(--line);border-radius:14px;padding:20px 22px;
  background:color-mix(in srgb,var(--panel) 72%,transparent)}
.tnull h3{margin:0;font-size:17px;font-weight:750;letter-spacing:-.02em;color:var(--text)}
.tnull p{margin:9px 0 0;font-size:13px;line-height:1.6;color:var(--muted-strong);max-width:62ch}
.tnull p b{color:var(--text);font-weight:700;font-variant-numeric:tabular-nums}
html[data-theme="light"] .tnull{background:var(--panel);
  box-shadow:0 1px 2px rgba(20,32,64,.05),0 10px 26px -18px rgba(20,32,64,.28)}
```

### 7.3 Group header tier kicker · roll-up · compact rows

```css
.grp-hd .tkick{font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  color:var(--muted);white-space:nowrap}
.grp-hd .tkick::after{content:"·";margin-left:9px;color:var(--line)}
/* the m0 group's rule is a neutral hairline — it is NOT a fifth rung on the ramp */
.grp.m0 .grp-hd .rule{background:var(--hair);opacity:1;background-image:none}
/* REQUIRED (measured — §14.2): the tier kicker overflows the sticky header at
   390px. It takes its own line there, and drops its separator with it. Without
   this block the page side-scrolls on a phone. */
@media(max-width:620px){
  .grp-hd{flex-wrap:wrap;gap:5px 12px;padding-bottom:8px}
  .grp-hd .tkick{flex:0 0 100%;order:-1}
  .grp-hd .tkick::after{content:none}
  .grp-hd h2{white-space:normal;font-size:16px}
  .grp-hd .cnt{margin-left:auto}
}
.rollup{margin:8px 0 0;padding:13px 6px 15px;font-size:12.5px;line-height:1.5;
  color:var(--muted);border-bottom:1px solid var(--hair)}
/* compact rows: the sparkline cell is the only thing that leaves. Words, wear
   marks, hovers and the library card all stay — the picture is what gets dropped
   under load, never the reading. */
.grp.compact .row{grid-template-columns:minmax(150px,1.15fr) 92px minmax(220px,2.1fr) auto}
@media(max-width:820px){.grp.compact .row{grid-template-columns:minmax(0,1fr) auto}}
/* the trend distance is a DISTANCE, not a direction — permanent green (permanent
   red in ZH) would be a false directional cue. */
.c-gain .fig.neutral{color:var(--text)}
/* stale tape */
.asof .lag{display:block;margin-top:4px;color:var(--muted);cursor:help;
  border-bottom:1px dotted color-mix(in srgb,var(--text) 22%,transparent)}
.asof .lag b{color:var(--muted-strong);font-weight:650}
```

### 7.4 The `m0` accent

```css
.m0{--mc:var(--muted)}
```
Added beside the existing `.m1…m4` bindings. It is not a fifth rung on the ramp; it is the
absence of a rung, and it must never be given a hue.

### 7.5 Anchors and the ladder

Each tier's rungs link to that tier's group ids (§3.4). The off-ladder `no_read` line renders
only when that list is non-empty.

### 7.6 Reduced motion (kill block — extended, pseudo-elements named)

```css
@media(prefers-reduced-motion:reduce){
  .rise,.rise.d1,.rise.d2,.rise.d3,
  .rise::before,.rise::after,
  .rung,.rung::before,.rung::after,
  .sh-row,.sh-row::before,.sh-row::after,
  .row,.row::before,.row::after,
  .grp-hd::before,.grp-hd::after,
  .tier-hd::before,.tier-hd::after,
  .mixnote::before,.mixnote::after,
  .rollup::before,.rollup::after,
  .tnull::before,.tnull::after,
  .thm::before,.thm::after{animation:none!important;transition:none!important}
}
```

`.sh-row` carries a background transition and **must** be in this block. No new keyframes, no
new stagger: three tier sections with entrance animations would be three waves of movement on
a page whose subject is settled data.

---

## §8 Context contract — `winner_health.v2`

```jsonc
{
  "schema": "winner_health.v2",
  "asof": "2026-08-11",
  "data_last_day": "2026-07-02",
  "tape_lag_sessions": 26,          // NEW · int|null — completed US sessions between
                                    // data_last_day and the last completed session.
                                    // null (or <=5) -> the chip does not render.
  "universe_n": 20764,
  "null_state": false,              // page-level `warm` only; unchanged meaning
  "macro_backdrop": { … },          // page-level, unchanged

  "tiers": [                        // NEW · ORDERED, narrowest bar first. Exactly
                                    // these three keys, in this order.
    {
      "key": "primary",             // "primary" | "r63" | "atrz"
      "readable": true,             // NEW · false -> the tier renders `unread`
      "extended_n": 122,            // == sum of this tier's five lists
      "figure": "r126",             // "r126" | "r63" | "atr_x" — which row field
                                    // this tier prints. The TEMPLATE owns the
                                    // caption and the ink rule for each value.
      "library": { "track":"W", "window_start":"2022-07", "window_end":"2026-07",
                   "horizon_td":63, "drawdown_pct":20 },   // THIS TIER'S library
      "theme_counts": [ … ],        // PRIMARY ONLY; omitted on the other two
      "states": {
        "extended_healthy": [ … ], "extended_watch": [ … ],
        "thinning": [ … ], "breaking": [ … ],
        "no_read": [ … ]            // NEW
      }
    }
  ]
}
```

**Row** — W1's row plus three fields:

```jsonc
{ …W1 row unchanged…,
  "r63":   0.41,        // NEW · required when the tier's `figure` is "r63"
  "atr_x": 7.2,         // NEW · required when the tier's `figure` is "atr_x"; a
                        // positive distance, never signed, never a return
  "checks": {"evaluated": 3, "total": 9}   // NEW · required on `no_read` rows only
}
```

**Contract notes the builder must honour**

1. **A top-level `states` with no `tiers` renders as the primary tier alone.** This keeps the
   existing design-freeze fixtures valid and means a half-migrated builder degrades to today's
   page rather than to a blank one. Mandatory, not optional.
2. **Never emit a cross-tier total.** No `extended_n` at the top level, no union count, no
   "names on the board tonight". A name in two tiers is two rows and the page says so.
3. Sort `primary` lists by `r126` desc (unchanged). Sort `r63` and `atrz` lists **A→Z by
   ticker**. The template renders in the order given and never re-sorts.
4. Each tier's `library` and every leg threshold behind it are cut from **that tier's** history.
   A tier whose library or thresholds did not load sets `readable: false` — it never ships a
   populated `states` block built on another tier's numbers.
5. `atr_x` is a distance in the name's own typical daily move. It is ≥ the bar by construction;
   the template prints it neutral and to one decimal.
6. `no_read` rows still carry `spark` and `episode_high` (the picture is not a reading) and
   carry **no** `legs`.
7. `theme_counts` ships on the primary tier only. One tomography on the page.
8. `tape_lag_sessions` counts **completed US sessions**, not calendar days.

---

## §9 Design-freeze delta — `tests/test_winner_health_design_freeze.py`

The builder updates this file **deliberately**. Exactly these aspects change; anything else
changing means the delta went wider than the spec.

**Unchanged and must still pass verbatim:**
- all five existing `wh` fixtures, including `None`, `{"null_state": True}` and the two
  top-level-`states` fixtures — guaranteed by contract note 1;
- `"Winner Health" in html`; `"winner_health.v1" not in html`;
- `test_honest_dash…` for a row with no `r126`;
- `test_the_surface_is_wired_and_not_inert`.

**Changed:**
1. `"winner_health.v1" not in html` becomes a schema-family assertion — neither `v1` nor `v2`
   (nor any future `winner_health.v*`) may appear in the rendered page. Pin the family, not the
   version, or the next bump silently un-guards it.

**Added (each is a design gate, not a smoke test):**
2. Three-tier fixture renders; all three tier names appear; **no cross-tier total appears**
   (assert the string forms of `n1+n2+n3` are absent).
3. A tier with `readable: false` renders the `unread` band and **zero** `.row` elements for that
   tier, while the other tiers still render their boards.
4. A tier with all five lists empty renders the `none` band.
5. A tier with a populated `no_read` list renders the off-ladder rung and rows that contain
   **no** `class="wear"` element.
6. A `Still running` group of 56 rows renders the roll-up line and **zero** rows; a 55-row one
   renders 55 rows.
7. A `Showing wear` group of 56 rows renders 56 rows and **zero** `<svg class="sp"` elements
   (compact), while a 55-row one renders 55 sparklines.
8. The `atrz` tier's figure renders neutral (`class="fig neutral"`), carries the trend caption,
   and prints `—` when `atr_x` is missing — the honest-dash guarantee extended to the new figure.
9. `tape_lag_sessions: 26` renders the chip; `null` and `4` do not.
10. Every ATRZ state (board / clear / none / unread) renders the mixed-group banner exactly once.
11. Leg-tip provenance: a library-cut leg's tip contains the tier's own name; a fixed-rule leg's
    tip contains the fixed-rule sentence. Guards the mandate's no-reuse receipt.
12. ZH parity on the new strings: rendering with the ZH span present, no literal `None` appears
    in the page (see §10).

**Also touched, by other guards:** `scripts/check_title_i18n.py` (no CJK in attributes — the new
tips must use `data-tip-en`/`data-tip-zh`), and `tests/test_top_maturation.py` for the engine
lane's own leg-order and state rules. The nav row and `config/dag.yml` are unchanged: this is
the same page at the same path.

---

## §10 Pre-existing defect found while reading the live surface — fix it in this PR

**`name_zh: null` prints the literal string `None` on every ZH row.** `namerow` uses
`{{ r.name_zh | default(r.name | default(r.ticker)) }}`; Jinja's `default` substitutes only for
*undefined*, not for `None`, and the artifact ships `"name_zh": null` on most rows. Verified on
the live page: MRNA, VSTS, ATEN, PBF and VIRT all render `None` under their tickers in ZH.

Fix — pass the boolean flag on both filters, in `namerow` (the macro all three tiers use):

```jinja
{{ r.name_zh | default(r.name | default(r.ticker, true), true) }}
```

It belongs in this PR because W2b triples the number of rows this bug prints on, and because a
ZH-parity assertion (§9 item 12) is already being added.

---

## §11 What the builder must NOT decide

Everything in this list is pinned above. A change to any of it is a design change and comes
back to the design lane.

1. **Tier names, ZH tier names, bar sentences, and the shared near-high clause** (§2.1).
2. **That tiers carry no colour**, and that the maturation ramp is not extended or re-keyed (§2).
3. **Stacked sections + hero shelf** — not tabs, not three pages, not a JS switcher (§3).
4. **Tier order** (`primary → r63 → atrz`) and that it is never re-ordered nightly (§2.1).
5. **The honest-width shelf bar**, its width rule, and the exclusion of `no_read` from its
   segments and from the aging count (§7.1).
6. **In-group order per tier** — primary unchanged, new tiers A→Z (§3.3).
7. **The number 55**, and which side of it rolls up versus goes compact, and that the sparkline
   is the only thing a compact row loses (§3.3).
8. **That aging groups always render every row**, however many (§3.3).
9. **Every string in §4**, EN and ZH, including all stances, all null bodies, the banner, the
   roll-up line, the tape-lag chip and its tip, and the revised sub and small print.
10. **The row figure and caption per tier**, and that the trend distance takes neutral ink (§4.5).
11. **The new leg's words and tip**, and that it leads the key order on the new tiers only (§4.6).
12. **The provenance suffixes** and the library-cut / fixed-rule split they encode (§4.6).
13. **The full leg × tier ruling table** (§5) — including that the long-run-run-up check is not
    introduced on any tier, and that the two power-limited candidates are not introduced either.
14. **The three-absence taxonomy** and the majority-of-checks rule for unreadable rows (§6).
15. **Anchors** — the primary tier's four group anchors do not change (§3.4).
16. **That the theme tomography stays single and lives on the primary tier** (§3.2).
17. **That the page-scale flatline renders only when all three tiers are clear** (§4.8).
18. **The contract's back-compatibility clause** (§8 note 1) and the no-cross-tier-total rule
    (§8 note 2).
19. **The freeze-delta list** (§9) — add those guards, do not rewrite the file.
20. **The weight budget and its escalation** (§0 G-10): if real data blows 400 KB gzipped, stop
    and come back. Do not invent a cap, a top-N, or a "load more".

---

## §12 Out of scope for W2b (do not add)

Any hazard rate, probability, calibrated warning or forward-looking claim; any composite or
blended score; any rank number or top-N; any gate, size or escalation; any sell/short/trim/exit
instruction; any falsifier or refutation language; a fourth tier; a cross-tier state badge on a
row; a cross-tier total anywhere; per-tier theme tomography; tier colour-coding; client-side
tabs, filters, search or sort; a chart library; a second page header; any widening of the
21-session membership window; CN or non-US names.

---

## §13 Doctrine tensions hit, and how they were resolved

1. **"No regression on the primary board" vs "B2 counted everywhere."** The one W2-confirmed
   check cannot be added to the frozen primary board without changing its states. Resolved: the
   new check counts on the two new tiers only, and the resulting cross-tier disagreement is
   disclosed in plain words in every tier's `?` ("the same name can read differently in another
   group"). The alternative — adding it everywhere — would silently re-state the primary board
   the night W2b ships.
2. **"Neutral sort keys only" vs the frozen primary sort.** The primary tier's
   gain-descending order is frozen; the new tiers get A→Z. Resolved by making the difference
   *stated* rather than hidden: each tier's `?` names its own order, and the alphabetical choice
   is defended on findability, not only on compliance.
3. **Honest completeness vs page weight.** Listing every name in an 848-row group is honest and
   unreadable; capping is readable and dishonest. Resolved by dropping the *picture* rather than
   the *reading* (compact rows), rolling up only the group whose absence is itself the complete
   reading, and making the weight budget an escalation to the design lane rather than a decision
   the builder makes under pressure.
4. **Adding honest-null machinery to a frozen surface (§6 B and C).** These can fire on the
   primary tier. Named explicitly as an argued exception rather than smuggled in, because they
   only ever fire where today's page is wrong.
5. **Word budgets vs the mandated cohort banner.** The ATRZ disclosure cannot be said honestly
   in fourteen words. Resolved with a hard, stated budget (two sentences, ≤35 EN words) and a
   quiet, untinted treatment, so it discloses without shouting.

---

## §14 Traps found while designing this delta (record them, do not re-discover them)

This design was rendered before it was pinned — a standalone mockup of the shelf, a tier head,
the banner, the off-ladder rung, the roll-up, a compact row, the unreadable row and the tier
null band, against the real `theme.css`, at 1360px in dark + light + ZH and at 390px. Three
defects were found by looking that reading could not have found.

1. **`ABOVE ITS TREND` wraps the 92px figure column** and breaks the row baseline, so the
   caption is `ABOVE TREND`. Measured: caption height 32px (two lines) → 16px (one line).
   Any future caption for this cell must be verified at ≤13 characters in that column.
2. **The tier kicker overflows the sticky group header at 390px** — `tkick · h2 · rule · cnt`
   is 40px too wide, and the page side-scrolls. The header must wrap the kicker onto its own
   line below 620px (§7.3). This is the one place where the new orientation device costs
   layout, and it is invisible on desktop.
3. **The `m0` group header inherits `.grp-hd`'s `--mc`-tinted border and rule** unless it is
   given the neutral hairline explicitly — an unread group would otherwise draw a muted-grey
   version of the ramp and read as a fifth wear stage.
4. **`atr_x` is NOT ≥ the bar for the off-band arm — the dash is the ruled form.** §8 note 5
   says the trend distance is ≥6 by construction. That holds for a name EXT *today*; it does
   not hold for the recently-EXT arm, which is on the board precisely *because* it broke.
   Measured on the real tape: **79 of 532 ATRZ rows sit below the bar and 14 are negative**.
   The engine therefore emits `atr_x` only when the name is genuinely above its trend, and
   the cell falls back to the honest dash of §4.5 otherwise — a negative or below-bar
   multiple printed under a caption reading `ABOVE TREND` is a false sentence, not merely an
   odd number, and those rows already carry their own receipt in the give-back leg (§4.10
   row 13). **RULED 2026-08-11 (commissioning session): confirmed as shipped.** Recorded here
   so a later lane does not "restore" the raw value and re-introduce the false reading.
5. **The r63 figure caption wrapped twice, and §14.1's own ≤13-character rule caught
   neither.** `IN THREE MONTHS` (15 chars, 108px) measured 31px tall against primary's 16px.
   Re-pinned to `THREE MONTHS` — 12 characters, *inside* the stated budget, and it **still
   wrapped** at 92px in a 92px column. RESOLVED to **`THREE-MONTH`** (11 chars, 87px, one
   line) by §4.5 amendment II.

   **Why the character proxy failed, so no later lane reinstates it.** The caption is
   uppercased at 10px with 0.8px letter-spacing, where glyph widths vary by roughly 2:1
   between `I`/`X` and `M`/`O`/`W`. Character count and rendered width therefore rank
   captions *differently* in exactly the band these strings occupy: `IN SIX MONTHS` is the
   LONGEST of the three at 13 characters and fits (90px), while `THREE MONTHS` is shorter
   at 12 and does not (92px). A budget that admits the wrapping string and would reject the
   fitting one is not a loose rule — it is an inverted one. **Measure this cell in a
   browser; never count it.**

   The design-freeze guard follows from that: it FREEZES the three exact strings with their
   measured widths instead of asserting a budget. The character-budget version was written
   first and was VACUOUS — it passed `THREE MONTHS` while the built page wrapped, i.e. it
   gave false confidence about the one defect it existed to catch. A Jinja unit test has no
   layout engine and cannot do better, so the freeze forces a human re-measure on any
   change. Mutation-checked in both directions when it was written.

6. **WATCH ITEM — `IN SIX MONTHS` clears the column by only 2px** (90px of 92px). It is
   NOT changed here: the primary board is frozen and has no current defect. But it sits one
   font-stack substitution, letter-spacing tweak or column-width change away from the same
   two-line break. Any change to `--font-display`, to `.c-gain .cap`'s size/tracking, or to
   the 92px figure column must **re-measure all three captions** against the column before
   shipping — not re-count them.

Also re-confirmed from W1 §9 and still binding here: anything hosting `lens()` must be a
`<div>`; interpolated attribute *fragments* ship escaped; `.lens-receipt .r-i` is `nowrap`, so
the per-tier library disclosure is prose, never a receipt item.
