# WINNER HEALTH — W1 Surface Design Spec

**Status:** PINNED. This document is the **visual law** for `templates/winner_health.html.j2`;
`docs/DESIGN_DOCTRINE.md` is the **content law** and wins on every conflict.
**Program:** `research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md` §5-W1 (display gate declared there
before this surface existed — G0.7).
**Authored:** 2026-08-10, design lane (opus `designer`), after loading the doctrine and the
`frontend-design` skill. Verified visually in dark + light + ZH + mobile + all three null
states before pinning.
**Template:** `/templates/winner_health.html.j2` — complete, self-contained, renders against
any subset of the contract. Page CSS lives in the template's `<style>` block, the house
pattern (`templates/stage_analysis.html.j2`); there is **no** paired `site/` asset and
therefore no `check_template_site_sync` obligation.

---

## §0 Acceptance gates (this surface is not done unless)

- **G-A** Every element is one of: a present-tense descriptive fact, an episode-library base
  rate with honest N and named track, or an explicit null. No hazard, no probability, no
  calibrated warning, no composite score, no rank number. (Masterplan W1 display gate.)
- **G-B** The four states are **groups**, never a ranking. Inside a group the order is
  trailing six-month gain — a fact about the past, disclosed as such in the board `?`.
- **G-C** Three honest-null states are **designed pages**, not empty tables: nothing maturing,
  nothing extended, read not landed. Each carries a stance (Law 1).
- **G-D** EN/ZH parity; ZH is idiomatic Chinese market vernacular, not English-shaped. No
  translated text in `title=`/`aria-label` (CI: `scripts/check_title_i18n.py` — **passes**).
- **G-E** Dark plane keyed on `:root`, light on `html[data-theme="light"]`; every state ink
  measured ≥4.5:1 in both themes including the hard "hue printed on its own tint" case.
- **G-F** Directional colour (gains, drops) flows through `--ink-up`/`--ink-down` so
  红涨绿跌 flips it; the maturation ramp is non-directional and must **not** flip.
- **G-G** No banned vocabulary anywhere: `validated`, `falsified`, `refuted`, `证伪`,
  falsifier/refutation framing, internal study names (TOPA, prereg, gauntlet, race labels),
  state enum keys, raw slugs, bare statistics. No imperative sell/short/trim/exit copy.
- **G-H** Responsive to 390px (board collapses to cards, no horizontal scroll);
  reduced-motion kill block names its pseudo-elements; sparklines are inline SSR SVG with
  no JS library and no animation.

---

## §1 What this surface is

**Winner Health** — a nightly board of US names that are **extended** (large trailing
six-month gain, still close to their 252-day high), organised by **how the move is aging**.

It answers the one question the house has nothing for: *"has my winner changed character?"*
The stack has bottom radars, turn watch, ignition and reversal cohorts — all entry-side.
Nothing watches a winner age.

Its philosophical mirror is `engine/us_turn_watch.py`: **the operator is the second-stage
filter.** A row here is not a pick, a plan or a call — it is a name printed next to enough
context that a human decides in seconds whether to look harder. Most rows go nowhere. That
is the design, and the surface says so.

**Voice:** the physician's chart room. Calm, clinical, zero alarm theatre. Maturation is
rendered as **wear**, not as sirens.

---

## §2 The design system

### 2.1 Palette — the maturation ramp (page-local, layers over theme.css, never redefines)

An **oxidation ramp**, not a siren ramp. Four page-local accents:

| Token | State | Dark | Light | Reading |
|---|---|---|---|---|
| `--m1` | Still running | `#6ba2b2` | `#3a6d7e` | clear slate-teal |
| `--m2` | Showing wear | `#c1954f` | `#83601f` | brass — first oxidation |
| `--m3` | Thinning out | `#c47a45` | `#8a4c1f` | ochre — further worn |
| `--m4` | Character changed | `#9a8cb8` | `#645786` | violet ash — left the heat |

**Why it ends cool.** The obvious ramp is green→amber→orange→red. That is the siren, and
this page is explicitly not one. The ramp ends on a low-chroma violet because a winner that
has changed character is no longer *hot* — the heat has left the move. Two consequences,
both deliberate:

1. **The loudest colour on the page is never the worst state.** The honest stance for
   `breaking` is "worth a review", not "panic". Colour that shouts would be a copy violation
   painted instead of written. Severity is carried by the **wear-mark count** and the
   **broken rule**, which are non-verbal and non-alarming.
2. **Ending on violet keeps the ramp out of the directional vocabulary.** A rust/rose
   terminus would read as red — and in ZH mode red means *up*. A "Character changed" chip
   that reads bullish to a Chinese user is a correctness bug, not a taste one.

**The ramp is non-directional by construction** — it encodes health/wear, exactly as
theme.css treats `--ok`/`--warn`/`--act`, which it deliberately excludes from the
红涨绿跌 swap. It must never be rebound under `html[data-lang="zh"]`.

**Directional ink is a separate system.** Gains, drops, and the library card's
kept-going / when-they-fell rows use `var(--ink-up)` / `var(--ink-down)`, which flip in ZH
automatically. **Verified:** `+62%` renders green in EN and red in ZH; the library card's
"kept going" row flips green→red and "when they fell" red→green.

**Contrast (measured, sRGB, against `--panel` / `--panel2` / `--bg`):** every rung clears
4.5:1 as text in both themes. Hard case — the rung printed as ink on a 15% tint of its own
hue, mixed 88%-toward-`--text` (dark) / 78% (light): worst is dark `--m3` at **4.69:1**.

### 2.2 Type

No new families. The house face (`-apple-system` / SF Pro Display / self-hosted Inter) with
four **roles**, differentiated by weight, size and tracking rather than by family:

| Role | Spec | Used for |
|---|---|---|
| Display | 800, −.028em, 27px / 24px / 17px | H1, null-hero H2, group names |
| Ladder figure | 700, −.03em, 23px, tabular | the four hero counts |
| Utility | 700, .14–.19em, uppercase, 10–10.5px, `--muted` | kicker, `IN SIX MONTHS`, `BACKDROP`, lens keys |
| Body / figure | 450–650, 12.5–15.5px, 1.45–1.6; `tabular-nums` on figures only | rows, legs, prose |

House law honoured: **tabular figures for numbers, never for words.**

### 2.3 Signature — **the high-water rule**

Every row's 104×30 sparkline is measured against **the run's own highest close**:

- a **dashed rule** at that level, in the state's hue;
- a **state-tinted underwater area** filling everything between the rule and the price,
  starting at *the session the high was set* (not the left edge);
- the **price line in neutral ink** over it;
- a **still end dot** — settled data never pulses (`docs/ILLUSTRATIONS.md` animation law).

The picture *is* the page's thesis: a healthy name shows a sliver you cannot see; one that
has changed character shows a wide wedge. Four states, one picture, four readings.

**Why the fill starts at the high, not at the left edge.** Every extended name is by
definition far below its eventual high early in the window — shading the run-up made all
143 names look equally worn and destroyed the signal. Before the high, the name had not got
there yet; that is not "underwater". When the run's high *predates* the visible window, the
fill correctly starts at 0 — the whole window is under it, which is itself the reading.

**Why the price line is neutral.** Direction is already stated by the gain figure beside it
(which flips in ZH). A directional stroke would put two colour systems inside 104px.

**The fill is not a shared-scale magnitude bar** and must never be read as one: each spark
is normalised to its own y-range. The comparable number lives in words in the row
("21% off its high") and in the analog card. This is the honest-bar rule applied to a chart.

### 2.4 Second structural device — the wear ladder

The four states are a **sequence of wear**, so the line that carries them wears out. Each
group header is one continuous typographic rule from the state's name to its count, and the
rule's stroke decays down the ladder:

```
7  Still running       ────────────────────────────────────  Nothing to do
4  Showing wear        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   Watch — don't chase
3  Thinning out        · · · · · · · · · · · · · · · · · ·   Watch closely
2  Character changed   ──  ─   ──  ─    ──   ─  ──   ─  ──   Worth a review
```

`solid → dashed → dotted → broken`, via `repeating-linear-gradient`. The same four strokes
reappear on the sticky group headers down the board, so the reader always knows which rung
they are on without a chip on every row. Structure encoding content, not decorating it.

### 2.5 What was deliberately removed

- **The per-row state chip.** Inside a group the state is a constant, and a constant repeated
  down 96 rows is a Law-4 violation. The **sticky group rule-line** carries it once.
- **The per-group `?` explainer.** Four identical cards is the same defect. One board-level
  `?` sits in the hero.
- **A per-row "nothing has slipped" for healthy names** — a repeated constant. Replaced with
  the one thing that still varies and that the spark is drawing: *"sitting at its high"* /
  *"6% under its high"*, computed from data already on the row so it can never disagree with
  the picture.

---

## §3 Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [ shared product nav — _site_nav.html.j2, verbatim include, no local header ] │
├──────────────────────────────────────────────────────────────────────────────┤
│ WINNER HEALTH                                            Priced 2026-08-08   │
│ Has your winner changed character?                    Re-read every night    │
│ The US names sitting on big gains near their highs, grouped by how the       │
│ move is aging.                                                               │
│                                                                              │
│ ╭─ HERO: THE WEAR LADDER ────────────────────────────────────────────────╮   │
│ │ 9 of tonight's 143 extended names are showing wear.  (?)               │   │
│ │  7  Still running       ─────────────────────────  Nothing to do       │   │
│ │  4  Showing wear        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  Watch — don't chase │   │
│ │  3  Thinning out        · · · · · · · · · · · · ·  Watch closely       │   │
│ │  2  Character changed   ──  ─   ──   ─  ──   ─ ──  Worth a review      │   │
│ ╰───────────────────────────────────────────────────────────────────────╯   │
│                                                                              │
│ BACKDROP  the index is holding up while its leaders are being sold  ·        │
│           37 US names already read as topping  (?)                           │
│                                                                              │
│ How much of each theme is aging   Counts only — the bar width is the size…   │
│  AI Semiconductors      7 of 19   Power & Grid Buildout      4 of 14   …     │
│  ▓▓▓▓▓▓▓▓▓▓▒▒▒▒░░▒                ▓▓▓▓▓▓▓▓▒▒▒▒░                              │
│                                                                              │
│ Still running ───────────────────────────────────────────────── 7 names  ◄ sticky
│ ● Nothing to do   Big gains, still close to their highs. Nothing here…       │
│  NVDA    +62%    ╌╌╌╌╌╌╌╌╌╌╌   ▮▯▯  sitting at its high        41 like this  │
│  NVIDIA  IN SIX      ╱‾‾                                          ▲ Tier 2   │
│          MONTHS                                                              │
│  AVGO    +54%    …                                                           │
│                                                                              │
│ Showing wear ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  4 names     │
│ ● Watch — don't chase   Still up, but one or two things have started…       │
│  MU      +71%    ╌╌╌╌▓▓▓▓  ▮▮▯  lagging the market for 12 sessions ·         │
│  Micron  IN SIX     ╱‾╲▁       more volume, less progress      41 like this  │
│                                                                              │
│ Thinning out · · · · · · · · · · · · · · · · · · · · · · · · ·  3 names     │
│ Character changed ──  ─   ──   ─  ──   ─ ──   ─  ──  ─  ── ──   2 names     │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────    │
│ US names only — the library counts are what similar past runs did, history   │
│ rather than forecasts, and nothing on this page ranks, gates or sizes        │
│ anything. Tonight: 143 extended out of 20,764 US names screened, read …      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Row anatomy (desktop grid `minmax(150px,1.15fr) 92px 104px minmax(220px,2.1fr) auto`)

| Cell | Content | Tier |
|---|---|---|
| `.c-tk` | ticker (link when `href`) + company name | 1 |
| `.c-gain` | `+62%` in directional ink, `IN SIX MONTHS` under it | 1 |
| `.c-sp` | the high-water sparkline | 1 |
| `.c-legs` | wear marks (0–3) + up to 3 plain-word legs, each a hover | 1 → 2 |
| `.c-lib` | `41 like this` — opens the analog memory card | 1 → 2 |

**Mobile (≤820px):** the grid becomes a two-column card — ticker/gain on line 1, legs/spark
on line 2, library link on line 3. Legs wrap; nothing truncates; no horizontal scroll.
**Verified at 390px.**

### Component hierarchy

```
body
├── _site_nav.html.j2                (shared product family — never a local header)
├── lens.lens_css()                  (rich-LENS row grid, injected once)
└── .wrap
    ├── .pghead                      kicker · h1 · sub · as-of
    ├── .hero  |  .nullhero          wear ladder  |  one of 3 designed null states
    ├── .backdrop                    one quiet line + lens(read)
    ├── .sec.themes                  theme tomography (counts only)
    ├── .sec.grp.m1…m4  × 4          sticky rule-line header · stance · rows
    │   └── .row × N
    │       └── spark() · wear() · legs · analog()
    └── .smallprint                  ONE merged line
```

---

## §4 Copy (authored here — this is the binding table)

### 4.1 Page furniture

| Slot | EN | ZH |
|---|---|---|
| `<title>` (plain, no `t()`) | `Winner Health — Has Your Winner Changed Character?` | — |
| Kicker | Winner Health | 持仓健康度 |
| H1 | Has your winner changed character? | 你的赢家，性质变了吗？ |
| Sub (14 words) | The US names sitting on big gains near their highs, grouped by how the move is aging. | 美股中涨幅可观、仍在高位附近的个股，按行情老化的程度分组。 |
| As-of | Priced **{data_last_day}** | 价格截至 **{data_last_day}** |
| As-of line 2 | Re-read every night | 每晚重新判读 |
| Hero lede | **{maturing}** of tonight's **{extended}** extended names are showing wear. *The rest are running the way they were.* | 今晚 **{extended}** 只高位强势股中，有 **{maturing}** 只出现转弱迹象。*其余仍按原来的样子运行。* |
| Themes h2 | How much of each theme is aging | 各主题老化到什么程度 |
| Themes note | Counts only — the bar width is the size of the theme, so a small group can never look like a big one. | 只是计数 —— 条形的宽度代表主题的大小，小主题不会被画得跟大主题一样。 |
| Small print (ONE line) | US names only — the library counts are what similar past runs did, history rather than forecasts, and nothing on this page ranks, gates or sizes anything. Tonight: **{extended_n}** extended out of **{universe_n}** US names screened, read **{asof}**. A name that has just left the extended band stays listed only while we evaluate the change. | 仅限美股 —— 资料库中的次数是历史上相似行情走过的路，属于历史而非预测；本页任何内容都不参与排序、准入或仓位。今晚：筛查 **{universe_n}** 只美股，其中 **{extended_n}** 只处于高位强势，判读日期 **{asof}**。刚离开高位强势区间的个股，仅在我们判读这一变化期间保留在看板上。 |

The closing sentence is the **board-membership disclosure** (design authority, 2026-08-10),
added when the membership ruling widened the board to names with an EXT day inside the
trailing 21 sessions. It is what keeps the word *extended* honest in the count beside it: on
the measured tape 39 of 122 rows were names that had just left the band. ZH uses the page's
own vocabulary — 高位强势 (extended, as in 处于高位强势), 个股, 判读 (the nightly read), 看板 —
rather than a second term for each; and 离开 not 跌出, because a name can leave the band by its
six-month gain maturing out without falling at all.

### 4.2 The four states — **named, never explained on the surface**

| Contract key | EN name | ZH name | EN stance | ZH stance | Group sub-line EN | Group sub-line ZH |
|---|---|---|---|---|---|---|
| `extended_healthy` | **Still running** | 仍在延续 | Nothing to do | 无需动作 | Big gains, still close to their highs. Nothing here has slipped yet. | 涨幅可观，仍在高点附近。目前没有任何环节转弱。 |
| `extended_watch` | **Showing wear** | 势头转弱 | Watch — don't chase | 观察 —— 别追高 | Still up, but one or two things have started to slip. | 仍在上行，但已有一两个环节开始转弱。 |
| `thinning` | **Thinning out** | 买盘转薄 | Watch closely | 密切观察 | The move is still up, but fewer buyers are carrying it. | 行情仍在上行，但承接的买盘明显变少。 |
| `breaking` | **Character changed** | 走势已变 | Worth a review | 值得复核 | These no longer behave the way they did on the way up. | 这些个股的走法，已不同于此前上行时的样子。 |

Notes binding the builder:
- The **name is the label** (tiers-named-never-explained law). Mechanics never appear beside
  the chip; the one board-level `?` carries how the groups are built.
- `Character changed` is the operator's own framing of the product question. It is the
  terminal state's name precisely because it makes no prediction — it describes behaviour.
- **`Worth a review` is the sanctioned terminal stance.** `Protect gains` is in the doctrine's
  stance vocabulary but implies a forward claim, which the W1 display gate forbids; a
  review-tier stance is the turn-watch mirror ("the operator is the second-stage filter").

### 4.3 Leg copy library (EN ≤6 words; ZH idiomatic; the number goes on the hover)

Builder substitutes the numbers and emits both the glance words and the hover sentence.

| key | `words_en` | `words_zh` | `tip_en` (Tier 2) | `tip_zh` |
|---|---|---|---|---|
| `rs_peak_lag` | lagging the market for {n} sessions | 已跑输大盘 {n} 个交易日 | Its strength versus the market peaked {n} sessions ago — the price kept rising through {m} of them. | 它相对大盘的强度在 {n} 个交易日前见顶 —— 其中有 {m} 天股价仍在上涨。 |
| `rs_decel` | leadership fading | 领涨地位减弱 | Its edge over the market is still positive but shrinking — about {x} of the peak edge is left. | 它相对大盘仍有优势，但正在收窄 —— 目前只剩下峰值优势的约 {x}。 |
| `effort_result` | more volume, less progress | 量增价滞 | Volume is running {x}% above its own three-month average while the price gained {y}% — buyers are working harder for less. | 成交量比自身三个月均量高出 {x}%，但股价只涨了 {y}% —— 买方付出更多，换来的却更少。 |
| `updown_volume` | selling days now heavier | 下跌日成交更重 | Down-day volume has outweighed up-day volume in {n} of the last {m} sessions. | 最近 {m} 个交易日中，有 {n} 天的下跌日成交量超过了上涨日。 |
| `vol_asymmetry` | swings getting wider | 波动明显放大 | The daily range is {x}× its own three-month normal, and the widening is happening on down days. | 日内波幅是自身三个月常态的 {x} 倍，而且放大主要发生在下跌日。 |
| `late_verticality` | went vertical late | 末段加速拉升 | Gained {x}% in {n} sessions — about {y}× the pace it kept for the rest of this run. | {n} 个交易日内上涨 {x}% —— 约为本轮行情其余时间节奏的 {y} 倍。 |
| `dip_unreclaimed` | dip not bought back | 回调未被买回 | Fell {x}% {n} sessions ago and has not regained that level; earlier dips in this run were recovered within {m} sessions. | {n} 个交易日前下跌 {x}%，至今未收复该位置；本轮之前的每次回调都在 {m} 个交易日内被买回。 |
| `below_50d` | lost its 50-day line | 跌破 50 日均线 | Closed below its 50-day average for {n} straight sessions — the first such stretch in this run. | 已连续 {n} 个交易日收于 50 日均线之下 —— 本轮行情中首次出现。 |
| `drawdown_from_high` | {x}% off its high | 距高点回落 {x}% | Down {x}% from the closing high set on {d}, against a typical pullback of {y}% during this run. | 较 {d} 的收盘高点回落 {x}%，而本轮行情期间的典型回调幅度为 {y}%。 |
| `episode_age` | running {n} months | 已运行 {n} 个月 | This run started {d}, {m} sessions ago — longer than {p} in 10 runs of this kind in the library. | 本轮行情起于 {d}，至今 {m} 个交易日 —— 比资料库中十分之 {p} 的同类行情都长。 |

**Leg ordering is the fixed key order of this table**, not a severity ranking. The same two
legs must always read in the same order on every row and every night. Max 3 rendered.

**AMENDMENT (design authority, 2026-08-10) — breaking rows lead with their state-defining
legs.** *The state's evidence may never be truncated off its own row.* When
`state == breaking`, the legs line renders `below_50d` first, then `drawdown_from_high`, and
fills any remaining slot from the frozen key order above. `MAX_LEGS` stays 3; every other
state keeps the pure frozen order, unchanged.

Why: those two keys are 8th and 9th of ten, and they are exactly the pair `classify` requires
for the terminal state — so the cap cut them off the very rows they had just defined. Measured
on the real tape (2026-07-02, 122 rows): **all 39 breaking rows** rendered three legs and not
one of them was the give-back or the lost 50-day line. `VIAV` printed
`lagging the market for 40 sessions · selling days now heavier · lost its 50-day line` with
no give-back at all. This is a **display order only** — `classify`, the counting set and the
state taxonomy are untouched, and the order *inside* the lead pair is the order `classify`
reads them in, not a ranking between them. Builder: `engine.top_maturation.order_legs`
(applied before the cap); guarded by `tests/test_top_maturation.py`
`test_breaking_row_leads_with_its_own_evidence_and_never_truncates_it`.

**No-legs fallback (template-computed, do not send):** `sitting at its high` / 正处于自身高点
when within 1% of `episode_high`; otherwise `{x}% under its high` / 低于自身高点 {x}%.

### 4.4 Analog memory card (LENS `record` tier)

Trigger: `{n} like this` / `{n} 例相似` (dotted, focusable). Card, ≤80 words body:

| Row | EN | ZH |
|---|---|---|
| kick / title | In the library / **{n} past runs shaped like this** | 历史资料库 / **资料库中 {n} 段形态相似的行情** |
| Fell back hard *(warn)* | **{k} of {n}** dropped {D}% or more from their high within three months — about 1 in {round(n/k)}. | **{n} 段里有 {k} 段**在三个月内从高点回落 {D}% 或更多 —— 大约每 {round(n/k)} 段有 1 段。 |
| Kept going *(up ink)* | The other **{n−k}** carried on — a typical further gain of **{+g}**. | 其余 **{n−k}** 段继续上行，典型的后续涨幅为 **{+g}**。 |
| When they fell *(down ink)* | The typical drop from the high was **{−d}**. | 从高点回落的典型幅度是 **{−d}**。 |
| Note | This is what those runs did — history, not a forecast. Runs are matched on shape and age, never on the company or its industry. **+ track sentence.** | 这是那些行情当年走过的路 —— 是历史，不是预测。匹配只看走势形态和运行时长，与公司本身或所属行业无关。**+ 样本说明。** |
| Track sentence — `W` | The record includes names that later delisted. | 这份记录包含了后来退市的个股。 |
| Track sentence — `D` | It draws only on names with long price history, so runs that ended in a delisting are under-represented. | 它只取有长期价格历史的个股，因此以退市收场的行情在样本中偏少。 |
| Receipt | `N {n} episodes` · `WINDOW {start} → {end}` · `NAMES whole US market \| curated` | `N {n} 段行情` · `区间 …` · `样本 全市场 \| 精选池` |

**Honest-N floor — `n < 12` replaces the whole body:**
> Only {n} past runs match this one closely enough to count — too few to read as a pattern.
> The count is shown so you know how thin the record is, not so you can lean on it.
> 与本次行情足够相似的历史样本只有 {n} 段 —— 太少，不足以当作规律来看。这里把次数写出来，是为了让你知道记录有多薄，而不是让你据此下判断。

**No analog:** `no match` / 无相似样本, with a plain `data-tip` explaining why.

**The survivorship disclosure (G0.2) belongs in the wrapping note, never the receipt** —
receipt items are `white-space:nowrap` and a sentence-length value is silently clipped
there. (Found and fixed during design; see §9.)

### 4.5 Macro backdrop — froth quadrant, plain-worded

Engine slugs from `engine/froth_fragility.py` `_QUAD_LABELS`. Those labels are Tier-2 grade
("distribution top risk", 派发); this page maps them at render, the house
`STANCE_ZH`/`BAND_ZH` pattern. Unknown slug → the line is simply omitted (never printed raw).

| slug | EN | ZH |
|---|---|---|
| `euphoric_fragile` | the market is hot and running on few names | 市场情绪偏热，且只靠少数个股支撑 |
| `narrowing_top` | the index is holding up while its leaders are being sold | 指数还稳，但领涨股正被卖出 |
| `stealth_primed` | early, unclear signs under a calm surface | 平静表面下出现早期、尚不明朗的迹象 |
| `distribution_in_progress` | large holders have been selling into strength | 大资金正在借强势派货 |
| `euphoric_extended` | the market is hot, but still broad | 市场偏热，但参与面仍然广泛 |
| `visible_stress` | the strain is already out in the open | 压力已经摆在明面上 |
| `benign` | calm and broad | 平静且广泛 |

Second clause: `**{stage3_count}** US names already read as topping` / 已有 **{n}** 只美股被判为见顶阶段.

### 4.6 The three honest-null states (each a designed page — G-C)

| Mode | Trigger | Eyebrow | Heading | Body | Stance |
|---|---|---|---|---|---|
| `warm` | `wh` absent or `null_state: true` | Warming up / 正在预热 | Tonight's read has not landed yet / 今晚的判读尚未生成 | This board is rebuilt after every US close. It fills in as soon as the nightly read finishes — nothing is being withheld. | — |
| `none` | every state list empty | Tonight / 今晚 | No US name is extended right now / 当前没有美股处于高位强势 | Out of **{universe_n}** US names, none is sitting on a large six-month gain close to its high. There is no winner here to age. | **Nothing to watch** — names appear here on their own, the night they qualify. |
| `clear` | names extended, `watch+thinning+breaking == 0` | Tonight / 今晚 | Nothing is maturing tonight / 今晚没有行情走向成熟 | All **{n}** extended US names still look the way they did — none of them has started to slip. An empty board is a reading, not a gap. | **Nothing to do** — a name moves down this page on its own, the night something slips. |

`clear` additionally renders **the signature at page scale**: one long dashed high-water rule
with the price riding it and no gap underneath, captioned *"the shape this board is watching
for."* A quiet night gets the most memorable picture on the page. It then still renders the
`Still running` group below, so the board is never blank.

---

## §5 Context contract — `winner_health.v1`

The template receives exactly one variable, `wh`. Every field is optional at render time
(the page degrades, never crashes); the list below is what the builder **must** produce for
the surface to be complete.

```jsonc
{
  "asof":          "2026-08-10",   // read date (nightly run)
  "data_last_day": "2026-08-08",   // last bar priced — the ONE visible as-of stamp
  "universe_n":    20764,          // US names screened
  "extended_n":    143,            // == sum of the four state lists (see note)
  "null_state":    false,          // TRUE ONLY when the nightly read did not produce

  "macro_backdrop": {
    "froth_quadrant": "narrowing_top",   // slug from engine/froth_fragility.py
    "stage3_count":   37                 // int | null
  },

  "library": {                     // page-level constants — Law 4: once, not per row
    "track":        "W",           // dominant track, informational
    "window_start": "2021-07",
    "window_end":   "2026-08",
    "horizon_td":   63,            // the race horizon, in trading days
    "drawdown_pct": 20             // the X% drop that defines "fell back hard"
  },

  "states": {
    "extended_healthy": [ /* row */ ],
    "extended_watch":   [ /* row */ ],
    "thinning":         [ /* row */ ],
    "breaking":         [ /* row */ ]
  },

  "theme_counts": [
    { "basket": "AI Semiconductors", "basket_zh": "人工智能半导体",
      "extended": 19,               // TOTAL extended in the theme (healthy included)
      "watch": 4, "thinning": 2, "breaking": 1 }
  ]
}
```

### Row

```jsonc
{
  "ticker": "NVDA",
  "name":   "NVIDIA",
  "name_zh": null,                 // optional; falls back to `name`
  "href":   "stock_NVDA.html",     // optional; ticker becomes a link when present
  "r126":   0.62,                  // trailing six-month return, decimal — the ONE row figure
  "r21":    0.08,                  // one-month return — NOT rendered; reserve for Tier 2
  "days_in_episode": 88,           // NOT rendered directly; surfaces via the episode_age leg
  "state":  "extended_healthy",    // key must match its list; never rendered

  "spark":  [ /* last 63 CLOSES, oldest → newest, floats */ ],
  "episode_high": 142.87,          // the EPISODE's highest close, same units as `spark`

  "legs": [
    { "key": "rs_peak_lag",
      "words_en": "lagging the market for 12 sessions",  // ≤6 words, numbers substituted
      "words_zh": "已跑输大盘 12 个交易日",
      "tip_en":   "Its strength versus the market peaked 12 sessions ago — …",
      "tip_zh":   "它相对大盘的强度在 12 个交易日前见顶 —— …" }
  ],

  "analog": {                      // null when no episode matches closely enough
    "n": 41,                       // honest N — DISTINCT EPISODES, never fires or ticker-days
    "topped_63td": 14,             // of n, how many dropped ≥ library.drawdown_pct within horizon
    "median_further_gain":  0.11,  // median further gain across the CONTINUED arm
    "median_drop_from_high": -0.24,// median drop from peak across the TOPPED arm (negative)
    "track": "W"                   // "W" whole-market | "D" curated — drives the disclosure
  }
}
```

**Contract notes the builder must honour**

1. **Every extended name lands in exactly one state list.** No capping, no truncation. The
   hero derives its counts from the lists (so the headline can never describe a board that
   is not there); `extended_n` appears only in the small print. If the two disagree, the
   surface is honest but the artifact is wrong.
2. **Sort each list by `r126` descending.** The template renders in the order given and never
   re-sorts — a template that sorts is a template that ranks.
3. `spark` must be **closes only**, ≥3 points; fewer renders the `no history` null.
4. `episode_high` is the **episode's** high, not the window's. Supply it even when it predates
   the 63-session window — the template then shades the whole window, which is correct.
5. `median_drop_from_high` is **negative**. (Renamed from `median_giveback`: "giveback" is on
   the vetoed-vocabulary list from ruling #2208, and the field name should not carry a banned
   word into a file that ships to users.)
6. `analog.n` is **episode-level honest N** (G0.3). Below 12 the card prints the thin-library
   copy instead of a rate — do not suppress the field, let the design handle it.
7. `theme_counts[].extended` is the **total**; the template derives
   `clean = extended − (watch + thinning + breaking)`. Send negative-free counts.
8. `null_state` is for a **failed/absent read only**. "Zero extended names" and "nothing
   maturing" are data findings and are derived from the state lists.

---

## §6 Interaction

| Element | Trigger | Behaviour |
|---|---|---|
| Hero rung | click / Enter | anchors to `#g-{state_key}` |
| Hero `?` | hover · focus · tap | LENS `define` card — how the board is built, the order rule, "not a call" |
| Backdrop `?` | hover · focus · tap | LENS `read` card — where the mood line and topping count come from |
| Leg word | hover · focus · tap | LENS string tier from `data-tip-en/zh` — the sentence with the number |
| `{n} like this` | hover · focus · tap | LENS `record` card — the analog memory (§4.4) |
| `no match` | hover · tap | plain tip explaining the absence |
| Group header | scroll | sticky at `top:0` — the state stays visible without a per-row chip |
| Row | hover | 5% state-tint wash |

Everything Tier-2 goes through the **site LENS** (`theme.js`) — no bespoke popover. Desktop
hover-intent, mobile bottom sheet, Esc to close, `aria-describedby` wired, all free.

**Keyboard:** `.lens-term` carries `tabindex="0"` + `role="button"`; rungs and ticker links
are natively focusable; every interactive element has a visible `:focus-visible` ring.
**Screen readers:** sparklines and wear marks are `aria-hidden` (the words beside them carry
the same fact); `aria-label`s are static English (house allowance — never translated).

---

## §7 Mechanics

- **Dark plane on `:root`.** `html[data-theme="dark"]` matches nothing on a first visit (no
  attribute is set until a theme is saved) — the defect that shipped dead on 36 pages. Light
  overrides on `html[data-theme="light"]`.
- **Light is a design target.** Explicit light counterparts for: panel shadow (panel ≈ canvas
  is the flatness bug), underwater fill opacity (.15 → .23), wear-mark outline, theme-bar
  track border, leg underline. A 15% tint that reads on near-black vanishes on white.
- **Bilingual:** page-local `t(en, zh)` dual-span, the house mechanism copied from
  `stage_analysis.html.j2`. No CJK and no `t()` in any attribute
  (`scripts/check_title_i18n.py` passes). `<title>` is a plain English string.
- **Motion:** one 460ms entrance stagger, nothing else. No ambient loop, no pulsing dot —
  settled data never fakes liveness. The `prefers-reduced-motion` block names its
  pseudo-elements (`.rise::before/::after`, `.rung::before/::after`, `.row::before/::after`,
  `.grp-hd::before/::after`, `.thm::before/::after`) and uses `!important` on both
  `animation` and `transition`.
- **Charting:** row micro-sparks are inline SSR SVG (house macro idiom —
  `dashboard.html.j2` `bcspark`/`sg_leg_spark`). `lib/illus.py` (ilx) is the standard for
  **panel-scale** display charts; this page ships none in W1. Any future full-width chart
  here must use ilx. No Plotly, no client chart library, no page JS at all.
- **Render cost:** pure SSR, one template, zero fetches. Page weight scales with row count
  (~1 KB/row incl. the 63-point path).

---

## §8 Builder handoff — exactly what W1 must feed and wire

**Do not modify the template's markup or CSS to fit the data. Produce the contract.**

1. **`engine/top_maturation.py`** — nightly per-name states. Emits `states`, per-row `legs`
   (with `words_*` **and** `tip_*` already substituted, in the §4.3 key order, ≤3),
   `spark` (63 closes), `episode_high`, `analog`, `r126`, `r21`, `days_in_episode`.
   Sort each list by `r126` desc. State keys exactly: `extended_healthy`, `extended_watch`,
   `thinning`, `breaking` (masterplan §3 namespace fence — `mat_*` prefix internally, these
   four keys on the wire).
2. **`scripts/build_winner_health_page.py`** — mirror `scripts/build_stage_analysis_page.py`:
   - load the committed artifact, fail-open to `{"null_state": True}` on **any** failure;
   - `Environment(FileSystemLoader(templates), autoescape=True, undefined=Undefined)`;
   - **wire `td`/`tr` globals from `engine.i18n`** with the same try/except fallback — the
     included partials use them and a missing global crashes the build;
   - render with `tpl.render(wh=ctx)`;
   - write **only** via `lib.pages.write_page` (the raw-write fallback loses the data-base
     shim — the regression called out in the stage-analysis builder).
3. **Nav registration** — add the page to `templates/_navlinks.html.j2` (the shared
   authenticated/product inventory). **Never** add a local header; the template already
   includes `_site_nav.html.j2` verbatim. Guarded by `tests/test_product_chrome.py`.
4. **Pipeline** — one entry in the `daily.yml` parallel band + `config/dag.yml` parity, the
   same two places `build_stage_analysis_page` appears. Render budget target <60s.
5. **Forward log** — `data/top_maturation_log/`, `ignition_audit.py` mechanics (append-only
   JSONL, idempotent by `(asof, ticker)`), so any future promotion has grades. Not rendered.
6. **Synapse registration** — `tier: display`, `external_consumers: [mastermind:context]`;
   regenerate `docs/SIGNAL_BUS.md`.
7. **Tests** — render the template against: full board, `clear`, `none`, `warm`, a row with
   no `analog`, a row with `n < 12`, a row with a 2-point `spark`, and a row whose
   `episode_high` exceeds `max(spark)`. All eight must render without raising.
8. **Ship evidence** — per doctrine §5.8, the PR body carries screenshots of **dark + light +
   ZH**, plus the honest-null hero. A fixture harness that produces all of these already
   exists in this session's scratchpad and is trivial to reproduce from §5.

**Not the builder's to decide:** palette, type, layout, state names, stances, leg wording,
null-state copy, small print. Those are pinned above. A change to any of them is a design
change and comes back to the design lane.

---

## §9 Traps found while building this surface (record them, do not re-discover them)

1. **`lens()` inside a `<p>` silently explodes the page.** `_lens.html.j2` emits block-level
   `<div>`s inside its trigger span, and a `<div>` start tag **auto-closes an open `<p>`** —
   so the parser terminates the paragraph, the `.lens-src` span closes with it, and the
   hidden Tier-2 card renders **inline and unhidden** under every group header. `hidden` was
   present and `getComputedStyle` on the first (now empty) span reported `display:none`,
   which makes the bug look impossible from the console. **Any element hosting `lens()` must
   be a `<div>`.**
2. **`{{ ' class="on"' if cond else '' }}` ships `&#34;on&#34;`.** Under autoescape an
   interpolated attribute *fragment* is escaped, so the class never applies and the element
   silently renders in its default state. Build the value **inside** the attribute:
   `class="{{ 'on' if cond else 'off' }}"`. (`stage_analysis.html.j2` has the same shape for
   `selected` — it survives only because that string contains no quotes.)
3. **`.lens-receipt .r-i` is `white-space:nowrap`.** A sentence-length receipt value is
   clipped by the 300px card with no overflow indicator. Receipts take short tokens; prose
   disclosures go in `.lensx-note`.
4. **An underwater fill anchored at the left edge destroys the signal.** Every extended name
   is far below its eventual high early in the window, so the fill must start at the session
   the high was set.

---

## §10 Explicitly out of scope for W1 (do not add)

Any hazard rate, probability, calibrated warning, or forward-looking claim; any composite or
blended score; any rank number; any gate, size or escalation; any sell/short/trim/exit
instruction; any falsifier or refutation language, front-facing or otherwise; CN or non-US
names; a client-side fetch or chart library; a second page header. Tomography beyond counts
(propagation order, theme-level state machines) is Wave 2 and reads existing basket organs —
it is never re-derived here.
