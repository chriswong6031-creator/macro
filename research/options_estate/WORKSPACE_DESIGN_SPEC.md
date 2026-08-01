# OEU — Options workspace design spec (`options.html`)

Status: **PINNED DESIGN** for lane M-CMD. Authored by the design lane 2026-07-25.
Implements `OEU_MASTERPLAN.md` §2 — the IA (4 modes, section order, payload law, nav
regroup) is **adjudicated and closed**; this document specifies only the visual system,
markup, tokens, copy, and interactions that realise it.

**Reference implementation: [`mockups/oeu_workspace/options_mockup.html`](../../mockups/oeu_workspace/options_mockup.html)**
— a self-contained static mockup with all four modes, EN/ZH, light/dark, hand-baked
fixtures. **Copy markup and CSS from that file verbatim.** Crops in
`mockups/oeu_workspace/crops/`. Where this document and the mockup disagree, the mockup
is the source of truth for *markup*; this document is the source of truth for *why* and
for the copy tables.

Binding inputs: `docs/DESIGN_DOCTRINE.md` (content law — wins on conflict) and the
`frontend-design` skill (visual bar).

---

## §0 THE BUILDER MUST NOT DECIDE THESE

Every item below is already decided. Changing one is a design change and must come back
to the design lane, not be resolved in the build.

**Colour**
1. Workspace accent `--oew-accent`: `#8e97c8` dark / `#4c55a8` light. Structure only.
2. Record ink `--oew-stamp`: `#b49256` dark / `#8a6a2e` light. Allowed on exactly three
   things: the session date stamp block, as-of / vintage micro-labels, the coverage label
   on the close line. Nowhere else.
3. The accent is **never** used to encode data or direction, and the stamp is **never**
   used as a chip fill.
4. Stance chips use the `--oew-st-*` ramp (§2.3). They are **direction-stable** and must
   **not** be added to the `html[data-lang="zh"]` flip block — same rationale as the
   existing `--pv-*` prophet tokens (`theme.css:47-51`).
5. Only `--up` / `--down` may flip in zh. Never hardcode a directional rgba.

**Type**
6. The type role law: **machine-recorded facts are monospaced (`var(--font-mono)`), human
   interpretation is not (`var(--font-ui)`).** Numbers, tickers, levels, dates, K/N → mono.
   Sentences, stance words, state words, labels → UI face.
7. Never put Hanzi inside a `.mono` element (CJK falls back to a mismatched face).
8. Never hand-roll a `"SF Mono"`-first stack (renders **serif** in Chrome — #3371). Use
   the `--font-mono` token, which already leads with `ui-monospace`.
9. Type scale is fixed in §2.4. Do not introduce sizes outside it.

**Layout**
10. Spacing scale `--s1…--s8` = 4/8/12/16/20/24/32/44 px. Do not introduce other values.
11. Radius: pill `999px`, control `8px`, panel `14px`. (The house has **no** `--radius`
    token; 14px matches `theme.css .panel`.)
12. The close-line fill width is **exactly the coverage share** from the payload. Do not
    add a floor, a minimum, a threshold colour change, or a "looks better" rounding. If
    coverage is 61%, the line is 61% filled and the page should look wrong — that is the
    feature.
13. No threshold logic anywhere in the chrome. The quality word comes from the payload as
    a word; the builder does not compute bands.

**Copy**
14. All fixed labels are pinned EN+ZH in §5. Do not translate, re-word, or "improve" them.
15. Stance vocabulary is closed: `Act · Get ready · Watch — don't chase · Protect gains ·
    Stand aside · Ignore`. No new stance words.
16. **Word budget is a CEILING, not a mandate.** A panel carries *at most* one stance
    chip, *at most* one footnote, and one as-of stamp. A panel with zero stance chips
    meets this budget exactly as well as one with a single chip.

    This item once read "every panel carries exactly one stance chip," and that wording
    was taken as a per-panel *requirement* — which is how the identical "Watch — don't
    chase" chip came to stack down one page until a reader learned to skip it, the
    opposite of a decision element. **How many stance chips a page may show is governed
    by the verdict law, not by this budget** (`OIP_MASTERPLAN.md` §3): *"Each surface
    keeps exactly one decision element (the stance chip row of its hero/footer). New
    shelves add facts, never verdicts — machine-checkable: one `data-verdict-surface`
    marker per page; CI greps for duplicates."* `W1_DESIGN_SPEC.md` §0.13 states the
    same correction for the panels that wave introduced.

    Doctrine Law 1 ("stance or it doesn't ship") is satisfied either way: a panel
    answers "so what do I do?" with a chip **or** with its plain caveat sentence. The
    chip is one presentation of a stance, not the only sanctioned one. Pinned by
    `tests/test_build_options_command.py::test_every_panel_answers_so_what_do_i_do`.

    **Where this page's one decision element lives.** Ticker mode's name-header row —
    the `.oew-ic-foot` holding the stance chip and the expected range — carries the bare
    boolean attribute `data-verdict-surface`, and is the only element on the page that
    does (markup pinned by `W1_DESIGN_SPEC.md` §5.1). Two pieces of persistent chrome
    that predate that ruling used to render a second and third chip and no longer do:

    - the `.oew-nofuse` banner — it rides the header on **all four** mode tabs, so its
      chip repeated the read's verdict everywhere; and
    - the "Today's measured flow" footer — it sits below the name header that already
      carries the marker.

    Both keep their sentence verbatim in EN and ZH, and their as-of stamp where they
    have one; the sentences were always the valuable half. Neither is a verdict: one
    says how the four readings are *presented*, the other how far the measured numbers
    can be *trusted*. Pinned by `test_exactly_one_verdict_surface` and
    `test_chrome_caveats_keep_the_sentence_and_drop_the_chip`.

**House-contract traps (each one verified on main 2026-07-25)**
17. **No `prefers-color-scheme`.** The house has zero such rules (`theme.css`, `theme.js`).
    Theme comes from the copy-pasted no-flash boot `<script>` reading `localStorage.theme`,
    plus theme.js's time-of-day `themeAuto`. The mockup uses a media query **only** so it
    can be opened standalone — production must not.
18. **`.soft-contrast` is real and load-bearing.** theme.js adds it to `<html>` for every
    visitor and re-tunes `--bg/--panel/--panel2/--text/--muted/--line`. Production inherits
    it automatically; the builder must **not** re-declare it. The hexes users actually see
    are in §2.1.
19. The screener table wrapper **must** carry `.tbl-scroll`. theme.js `wrapTables()`
    auto-wraps any `<table>` not already inside one; a double wrap breaks the sticky header.
20. **`theme.js` must be the last body script.** `market_structure.html.j2` omits it and
    its theme/lang toggles are consequently inert — do not copy that page's head/foot.
21. `t()` must be **copy-pasted into the template**, not imported — `{% include %}` does
    not import parent macros (`_navlinks.html.j2:11-12`).
22. `td()` is a Python global (`engine/i18n.py`) backed by the ~500-entry `LEX` glossary.
    Use it **only** for dynamic labels already in `LEX` (sector names, state enums). It
    renders English-only for anything else. Hand-written strings use `t(en, zh)`.
23. `.act-pop-src` **does not exist** as a class (the doctrine names it, but it was
    retired). The live tooltip system is LENS: `data-tip-en` / `data-tip-zh`, with optional
    `data-tip-rc-en` / `data-tip-rc-zh` for the receipt line.
24. No translated text in `title=` (CI-guarded).

---

## §1 The visual system

### 1.1 What this page is

The estate's front door. Its subject is **the settled close** — the moment the tape stops
and the day's positioning becomes a fixed, countable fact. That is also the product
boundary the masterplan ratifies: *Terminal explains what is changing now; Macro explains
what settled.* The design makes that boundary structural rather than stated.

### 1.2 The thesis — the fill-track

Every quantity on this page is drawn as **a bounded track with a visible denominator and
a filled portion**. A bare number never appears without its scale. Four scales of one idea:

| Element | Track | Denominator |
|---|---|---|
| **The close line** (signature) | page-width rule | every name we track |
| **Pip strip** | 5 segments | the reading's full scale |
| **Dot-ladder** | 8 or 7 segments | conditions checked |
| **Sector bar** | shared-scale bar | the largest sector |

This is not invented for this page — it *generalises* the ladder idiom the house already
ratified in #3224 (`flow_leaders`), and names it so the estate can inherit it.

**The denominator must always be visible.** An unfilled pip/segment is a filled grey tile,
never an empty outline. When "off" is invisible, `6/8` reads as a random pattern and the
honesty of the scale is lost. This is the single most common way to break the system.

### 1.3 The signature — the close line

A full-width rule marking the boundary between *what settled* (above: identity, stamp,
posture) and *what you do about it* (below: mode tabs and the working surface). The mode
tabs sit directly beneath it; the active tab caps it in the accent.

**Its filled portion is the coverage number.** The page's most structural element carries
its most important honesty fact. When coverage is complete the signature is nearly silent;
when data degrades, the hatched remainder grows and the page visibly changes. It is an
instrument, not an ornament — which is why §0.12 forbids softening it.

The unfilled remainder is drawn as an explicit hatch
(`repeating-linear-gradient(90deg, var(--line) 0 3px, transparent 3px 6px)`) so missing
coverage reads as an *absence*, not as styling.

### 1.4 Why these two accents

The workspace is chromatically **quieter** than its siblings, deliberately: the four modes
each import strongly-coloured material (ladder tints, sector bars, up/down chips), so the
chrome must be near-silent or the page becomes a fruit salad. Authority comes from
typography and rule-work, not colour. That restraint is the risk this design takes.

- **Slate-indigo (structure).** Non-directional by construction — it must be unmistakable
  for `--up` or `--down` in *both* languages, which rules out green, red, coral and
  amber-red. Also distinct from every sibling: gex = coral `--act`, flow_desk /
  flow_leaders = teal `#33c9bf`, market_structure = aurora violet.
- **Brass (the record).** The warm ink of a settlement stamp against cold structural
  rules — the visual language of a printed financial document. Deliberately darker and
  browner than `--warn #e0a030` so a vintage mark can never be misread as a warning, and
  confined to three uses (§0.2) so it stays a signature rather than decoration.

### 1.5 Section-header idiom

Inherited from gex.html: an all-caps, letter-spaced, muted eyebrow, often framed as the
question the section answers ("THE TAPE — CALM OR JUMPY?"). Panel titles are sentence-case
and plain. In zh, uppercase and wide tracking are dropped (Hanzi does not take either) —
`html[data-lang="zh"] .oew-eyebrow { letter-spacing:.02em; text-transform:none; }`.

---

## §2 Token table

### 2.1 Inherited house tokens (do not redefine)

Link `theme.css`. Dark is the bare `:root` default; light is `html[data-theme="light"]`.

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0f1115` | `#f7f8fa` |
| `--panel` | `#181b21` | `#ffffff` |
| `--panel2` | `#1e222a` | `#eef1f6` |
| `--text` | `#d7dce3` | `#1c2430` |
| `--muted` | `#8b93a1` | `#5d6b7e` |
| `--line` | `#2a2f3a` | `#eaecf0` |
| `--up` | `#45b873` | `#1f9a55` |
| `--down` | `#e06464` | `#cf4040` |
| `--warn` | `#e0a030` | `#b9791a` |
| `--orange` | `#e08b45` | `#c4781f` |
| `--info` / `--link` | `#5b9bf0` / `#7aa7e0` | `#285fff` |

**What users actually see** — theme.js applies `.soft-contrast` to every visitor:

| Token | Dark (soft-contrast) | Light (soft-contrast) |
|---|---|---|
| `--bg` | `#0d1018` | `#eceef1` |
| `--panel` | `#151820` | `#f5f5f7` |
| `--panel2` | `#1b1f28` | `#e8eaed` |
| `--text` | `#c8d0dc` | `#2e3950` |
| `--muted` | (unchanged) | `#4c5a6c` |
| `--line` | `#262c38` | `#d0d4db` |

zh flip (`html[data-lang="zh"]`): `--up:#e06464; --down:#45b873`.
zh + light: `--up:#cf4040; --down:#1f9a55`.

### 2.2 Workspace tokens (new — declare on `.oew`)

```css
.oew{
  --oew-accent:#8e97c8;   /* structure only  */
  --oew-stamp:#b49256;    /* record ink only */
  --hair: color-mix(in srgb, var(--line) 72%, transparent);
  --tile: color-mix(in srgb, var(--panel2) 86%, var(--panel));
  --ink-2: color-mix(in srgb, var(--text) 66%, transparent);
  --ink-3: var(--muted);
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:20px; --s6:24px; --s7:32px; --s8:44px;
  --r-pill:999px; --r-ctl:8px; --r-panel:14px; --r-shell:14px;
}
html[data-theme="light"] .oew{
  --oew-accent:#4c55a8;
  --oew-stamp:#8a6a2e;
  --hair: color-mix(in srgb, var(--line) 92%, transparent);
  --ink-2: color-mix(in srgb, var(--text) 72%, transparent);
}
```

### 2.3 Stance ramp — one hue, intensity = urgency

Direction-stable. **Not** zh-flipped. `--warn` is permitted for *Protect gains* because
house law already treats `--warn` as health/danger rather than price direction and leaves
it un-flipped in zh.

| Stance | Class | Treatment |
|---|---|---|
| Act | `.st-act` | filled accent, white text |
| Get ready | `.st-ready` | accent text, 55% accent border, 13% accent fill |
| Watch — don't chase | `.st-watch` | `--ink-2` text, hairline border, tile fill |
| Protect gains | `.st-protect` | `--warn` text, 45% warn border, 10% warn fill |
| Stand aside | `.st-aside` | muted text, hairline border, transparent, .85 opacity |
| Ignore | `.st-ignore` | muted text, no border, transparent, .7 opacity |

*Act* is deliberately the loudest and rarest. On an EOD surface the honest common answers
are *Watch — don't chase* and *Stand aside*, and the ramp is calm on purpose.

### 2.4 Type scale

| Role | Size | Weight | Face | Used for |
|---|---|---|---|---|
| eyebrow | 10.5px | 700 | UI, `.09em`, uppercase | console labels, section heads, table `th` |
| micro | 10px | 400–600 | UI / mono | as-of, coverage label, card sub-keys |
| receipt | 11px | 400–600 | UI | stamp rows, supporting lines |
| body-sm | 12px–12.5px | 400 | UI | panel prose, table cells |
| body | 13.5px | 400 | UI | base |
| chip | 11.5px | 700 | UI | stance + preset chips |
| panel title | 14px | 700 | UI | `.oew-ph-title` |
| reading value | 15px | 650 | UI | posture console state word |
| index symbol | 15px | 700 | mono | SPX/SPY/QQQ/IWM |
| read value | 18px | 700 | UI | the three reads |
| regime headline | 19px | 700 | UI | Ticker mode headline |
| page title | 22px | 700 | UI | "Options" |
| last close | 24px | 700 | mono | Ticker price |
| **session date** | **27px** | **700** | **mono** | the stamp — the type signature |
| ticker symbol | 30px | 700 | mono | Ticker mode |

---

## §3 Component tree and class inventory

Prefix: **`.oew-`** (house convention is a short per-page prefix — `.gx-`, `.fd-`, `.fl-`).

```
.oew                                   workspace token scope
└ .oew-wrap                            max-width 1240, padding 0 20 44
  ├ header.oew-chrome                  ── PERSISTENT (all 4 modes) ──
  │ ├ .oew-idrow
  │ │ ├ h1.oew-title > .sub
  │ │ └ .oew-idrow-tools > .oew-tool ×2      (prod: house .theme-switch/.lang-toggle)
  │ ├ .oew-receipt                     grid 232px | 1fr  (1-col ≤900px)
  │ │ ├ .oew-stampblock                brass left rail via ::before
  │ │ │ ├ .oew-stamp-k / .oew-stamp-date(.mono) / .oew-stamp-closed
  │ │ │ └ .oew-stamp-rows > .oew-stamp-row > .k + .v[.brass]
  │ │ └ .oew-console > .oew-console-grid      4 cols (2 cols ≤760px)
  │ │   └ .oew-read ×4
  │ │     ├ .oew-read-k > .oew-eyebrow [+ .oew-vetted]
  │ │     ├ .oew-read-v                      plain state word
  │ │     ├ .oew-pips > .oew-pip[.on|.nul] ×5
  │ │     └ .oew-read-n                      supporting figure
  │ ├ .oew-nofuse > sentence              (no stance chip — §0.16: rides all 4 tabs)
  │ ├ ★ .oew-closeline[style="--oew-cov:NN%"]
  │ │   ├ .oew-cov-tick
  │ │   └ .oew-cov-label
  │ └ nav.oew-tabs[role=tablist] > .oew-tab[role=tab] ×4 > .cnt
  ├ section.oew-mode#mode-brief   [.active]
  ├ section.oew-mode#mode-scanner
  ├ section.oew-mode#mode-ticker
  └ section.oew-mode#mode-leaders
```

**Shared panel shell** (every panel, every mode):

```
.oew-panel
├ .oew-phead  > h2.oew-ph-title + .oew-ph-sub + .oew-ph-right > .oew-help
├ .oew-pbody
└ .oew-pfoot  > [.oew-stance] + sentence + .oew-asof
```

The stance chip is **optional** (`[…]`) and capped at one; the sentence is not. Only the
one panel that is the read's decision element carries a chip — see §0.16.

**Per-mode blocks**

| Mode | Classes |
|---|---|
| Brief | `.oew-chips`/`.oew-chg`; `.oew-idx`/`.oew-ic*`; `.oew-sect`/`.oew-sr*`; `.oew-bets`/`.oew-bet*`; `.oew-rail`/`.oew-rg*`/`.oew-tkchips`/`.oew-tkchip`; `.oew-handoff`/`.oew-ho-*`/`.oew-cta` |
| Scanner | `.oew-sc-bar`, `.oew-preset`, `.oew-seg`, `.tbl-scroll.oew-tblwrap`, `table.oew-tbl`, `.oew-sc-tk`, `.oew-sec`, `.oew-age`, col classes `.c-ovr/.c-flow/.c-pos`, `.hide-sm` |
| Ticker | `.oew-tk-*`, `.oew-lad*`, `.oew-lvl`/`.oew-lvrow`/`.oew-lv-*`, `.oew-reads`, `.oew-rd-*`, `.oew-metrics`/`.oew-mt`, `.oew-shelf` |
| Leaders | `.oew-ld`, `.oew-ldrow`, `.oew-ld-tk`, `.oew-ld-state` + `.ld-lining/.ld-crowd/.ld-radar`, `.oew-ladder`, `.oew-lseg[.on/.off/.nul]`, `.oew-ld-kn`, `.oew-ld-right`, `.oew-ld-ctx`, `.cau`/`.cau-warn`, `.oew-etf`/`.oew-etfc` |

> ⚠ **Class collision — already hit and fixed once.** The ladder segment is `.oew-lseg`,
> **not** `.oew-seg`. `.oew-seg` is the Scanner's segmented-control container; a second
> `.oew-seg` rule wins on source order and squashes that control to **7px wide**. Verified
> live during design. Same failure class as the `.obm-done` collision (#3470).

---

## §4 The persistent chrome

The masterplan lists the close-receipt band and posture chips as Daily Brief's opening two
sections. **They live in the chrome, above the mode surface** — which satisfies the ruling's
section order for Brief (they render above it) *and* makes Scanner / Ticker / Leaders
inherit the session receipt. That inheritance is the entire argument for a workspace rather
than four pages. Do not move them into the Brief surface.

### 4.1 Session stamp

Four facts, in this order, never more: session date (27px mono) · weekday + close time ·
then a ruled key/value list: positions counted (OI vintage, brass) · names covered
(`403 / 431`, mono) · data quality (a **word** from the payload, with a hover receipt).

### 4.2 Posture console — four readings, never fused

The masterplan requires these four to be **co-displayed, never fused into a score**. The
design makes the refusal legible: four equal cells, hairline-divided, no arithmetic between
them, each with its own label / plain state word / 5-pip position / supporting figure.
Below the console, one sentence states the non-fusion in plain words and gives the read.

Cell 1 carries a `✓` glyph (`.oew-vetted`) for the reading with a published track record.
**The glyph is the whole visible affordance** — the explanation is on hover. Do not print
the word "validated" as new user copy; it is CI-guarded (`scripts/check_validated_claims.py`)
and the masterplan (§0.5) permits it only where already sanctioned. If the existing Market
Weather badge has an approved visible string, reuse that exact string; otherwise ship the
glyph alone.

### 4.3 Close line

```html
<div class="oew-closeline" style="--oew-cov:93.5%" role="img"
     data-tip-en="…" data-tip-zh="…">
  <span class="oew-cov-tick"></span>
  <span class="oew-cov-label">…</span>
</div>
```

`--oew-cov` = `covered / universe * 100`, one decimal. The label rides the fill boundary
(`left:var(--oew-cov); transform:translateX(-100%)`) so it always sits just inside the
filled portion.

### 4.4 Mode tabs

`role="tablist"`, four `role="tab"` buttons with `aria-selected`. Horizontally scrollable
(`overflow-x:auto`, scrollbar hidden) — at 375px they become a swipeable strip, which is
the ratified mobile answer for the tab bar. Each tab may carry one `.cnt` mono figure
(`403`, `SPY`, `2`). Active tab: `--text` colour + 2px accent top border that caps the
close line.

---

## §5 Per-mode specs and pinned copy

Word budgets (doctrine §1): panel title ≤4 words · subtitle ≤14 words · row ≤1 line ·
footer ≤1 sentence.

### 5.0 Fixed chrome copy

| Slot | EN | ZH |
|---|---|---|
| Page title | Options | 期权工作台 |
| Page subtitle | One workspace for the settled close — brief, scanner, per-name, leaders. | 收盘后的统一工作台 — 简报、筛选、个股、领头股。 |
| Stamp eyebrow | Session closed | 收盘场次 |
| Stamp rows | Positions counted / Names covered / Data quality | 持仓统计 / 覆盖标的 / 数据质量 |
| Quality value | Complete | 完整 |
| Console labels | Whole market / S&P dealers / Today's tape / Same-day bets | 整体市场 / 标普做市商 / 今日盘面 / 当日到期押注 |
| Non-fusion line | Four readings, shown side by side and never averaged into one score. | 四项读数并列呈现，不会合成单一评分。 |
| Coverage label | covered **403**/431 names | 已覆盖 **403**/431 个标的 |
| Tabs | Daily Brief / Scanner / Ticker / Leaders | 每日简报 / 筛选 / 个股 / 领头股 |

**Stance chips (closed vocabulary).** ZH is **not free-choice** — three of the six already
have canonical strings in the site-wide glossary `engine/i18n.py` (`LEX`, lines 530-532),
which is what `td()` resolves through. Diverging would make this page inconsistent with
every other surface *and* with `td()` output.

| EN | ZH | Source |
|---|---|---|
| Act | 立即行动 | **not in LEX — add** |
| Get ready | 做好准备 | LEX `i18n.py:531` |
| Watch — don't chase | 观察—勿追高 | LEX `i18n.py:530` (note: no spaces around the dash) |
| Protect gains | 保护利润 | LEX `i18n.py:532` |
| Stand aside | 暂时观望 | **not in LEX — add** (dominant existing house usage) |
| Ignore | 忽略 | **not in LEX — add** |

**Builder task:** add the three missing stances to `LEX` in the same block (it is commented
"stances (doctrine six — the ones this page uses)"), so the full doctrine six resolve
through `td()` for this and every future surface. Use exactly the strings above.

### 5.1 Daily Brief

Order (from the ruling): what-changed chips → index close row → sector concentration bars
→ biggest bets → names-for-tomorrow rail → Terminal handoff.

**What changed** — max 5 chips, ≤5 words each, one arrow glyph (`▲` up / `▼` down /
`▬` flat) coloured by `--up`/`--down`/`--muted`. The number lives on hover, never on the
chip. Pinned examples: *Tape got heavier / 盘面更重* · *Downside cover costs more /
下行保护更贵* · *Money left Consumer Disc. / 资金流出非必需消费* · *SPY flip level moved
up / SPY 翻转位上移* · *Fewer same-day bets / 当日押注减少*.
Footer stance **Watch — don't chase**: "Nothing here is a trade on its own — these are the
day's deltas, not signals." / "这些只是当日变化，本身并不构成交易信号。"

**Index close row** — 4 cards (SPX/SPY/QQQ/IWM), 4→2→1 col at 1000/560px. Each card:
symbol + close (both mono) · regime headline (plain words, e.g. *Jumpy — moves get
amplified* / *剧烈 — 波动被放大*) · one line ≤14 words placing price against the flip ·
three levels `Floor / Flip / Ceiling` (`下方墙 / 翻转位 / 上方墙`) · stance chip + expected
move. Level keys are uppercase eyebrows in EN, plain in zh.
Footer: "Levels are measured from this close and hold until tomorrow's data run. A move
through one intraday does not count until it closes there." / "水位以本次收盘计算，在明日
数据更新前有效。盘中穿越某一水位，须以收盘站稳为准。"

**Sector bars** — shared scale. **The bar is a pure length encoding; the value lives in its
own right-aligned mono column.** (Putting the value inside the fill breaks on short bars —
the label overflows onto the track and fights the fill for contrast. Verified during design.)
Tone chip right: *buying ~ / 买入 ~*, *selling ~ / 卖出 ~*, *mixed / 混合*. The `~` prefix is
the house honesty mark for approximate direction.
Footer stance **Watch — don't chase**: "Two sectors took 61% of today's premium. This is a
picture of where money went, not a forecast of where it goes next." / "两个板块占据今日
61% 的权利金。这是资金去向的记录，而非对后续走向的预测。"

**Biggest bets** — ticker (mono) · net premium (mono, `--up`/`--down`) · tone words ·
optional caution chip. Same-day share as a right-aligned chip where notable.
Footer stance **Watch — don't chase**: "Big premium marks attention, not conviction. A
single large trade can be one desk hedging." / "大额权利金代表关注度，而非信心。单笔大单
可能只是某个交易台在对冲。"

**Names for tomorrow** — three groups, each a plain-word heading + ≤14-word explainer +
4–6 mono ticker chips that deep-link into Ticker mode:

| Group | EN | ZH |
|---|---|---|
| A | Money keeps showing up | 资金反复出现 |
| B | Turned back up after a washout | 洗盘后重新转强 |
| C | Sitting near a flip level | 接近翻转位 |

Panel subtitle: "a research list, not a buy list" / "研究清单，非买入清单".
Footer stance **Get ready**: "Tap a name to open its workbench. These are starting points
for your own work." / "点击标的可打开其工作台。这些只是你自行研究的起点。"

**Terminal handoff** — title "This page is the settled close" / "本页呈现的是已结算的收盘";
body explains that levels hold until tomorrow's run and the Terminal is the live surface;
a brass stopped-clock line "closed 16:00 ET · next open in 11h 48m" / "美东 16:00 收盘 ·
距下次开盘 11 小时 48 分" makes the cadence boundary structural (estate failure #3).
CTA: "Open the Terminal ↗" / "打开交易终端 ↗".

### 5.2 Scanner

Preset chips (single-select, `aria-pressed`), then the panel with a segmented column-view
control in its header.

| Preset EN | ZH |
|---|---|
| Premium leaders | 权利金居前 |
| Volume surge | 成交激增 |
| Expensive options | 期权偏贵 |
| Same-day heavy | 当日到期为主 |
| Downside cover bid | 下行保护受追捧 |
| Near a flip level | 接近翻转位 |

Views: Overview / Flow / Positioning → 总览 / 资金 / 持仓结构. Implemented as column
visibility classes on the table (`data-view` attribute + `.c-ovr/.c-flow/.c-pos`), the same
technique the current screener uses.

Column headers (EN → ZH): Name 标的 · Spot 现价 · IV 30d 30日隐波 · IV rank 隐波分位 ·
Expected move 预期波幅 · Put/call OI 认沽认购持仓比 · Volume 成交量 · Premium 权利金 ·
Net premium 净权利金 · Same-day share 当日到期占比 · From flip 距翻转位 · Ceiling 上方墙 ·
Floor 下方墙 · Behaviour 表现 · Tone 方向 · **Data age 数据新鲜度**.

**Row age** (new column, required by the ruling): a 3-pip freshness track + mono day count.
`0d` = 3 pips; `1–3d` = 2 pips; `>3d` = 1 pip **and** the count in `--warn`. Hover gives the
plain-word staleness sentence.

**Doctrine fix:** the current page's ~100-word always-visible "Coverage & data provenance"
block is Tier-3 content on a Tier-1 surface. It moves **into the panel-header `?`** as a
single LENS tip. It must not be reproduced as visible prose.

Deep link: the ticker cell is an anchor to Ticker mode with a hover-revealed `→`.
Footer stance **Stand aside**: "A screen is a starting list, not a ranking. Nothing here is
scored or ordered by expected return." / "筛选结果是起始清单，而非排名。此处没有任何内容
按预期收益评分或排序。"

### 5.3 Ticker

The gex.html workbench re-homed inside the chrome. **The price ladder is #3341's ratified
signature — port it, do not redesign it.** What changes: spacing moves to the workspace
rhythm, wall-strength dots become the workspace `.oew-pips` so the estate has one
non-verbal vocabulary, and the section sits inside `.oew-panel`.

Order: name header → regime headline + stance + expected range → the map (ladder band + 4
level rows) → three reads → measured flow → raw shelf (`<details>`, closed) → Terminal CTA.

Level row copy (pinned): *Ceiling — call wall / 上方墙 — 看涨墙* · *Flip — the regime line /
翻转位 — 状态分界* · *Magnet — max pain / 磁吸位 — 最大痛点* · *Floor — put wall /
下方墙 — 看跌墙*.

Three reads (eyebrow, question-framed): *The tape — calm or jumpy? / 盘面 — 平静还是剧烈？*
· *The mood — what options cost / 情绪 — 期权价格* · *The lean — direction by time window /
倾向 — 分时间窗口的方向*.

**Mobile:** below 640px the ladder band is hidden entirely (`.oew-lad{display:none}`). Its
four labels collide below that width, and the band is decorative restatement — the four
level *rows* carry the same numbers plus their plain-word meaning. Drop the band, never the
rows.

The band gradient uses `--up`/`--down` and therefore flips in zh. That is correct: it
encodes price direction (put wall low / call wall high).

### 5.4 Leaders

Two boards + the ETF strip (its single home now).

**The confluence ladder.** The masterplan records `flow_leaders` as shipping banned-vocab
slug chips (`FlowZ`, `TSBrd`, `NotTrap`). **That finding describes the deployed page, not
the template** — see §7. The template has been compliant since #3224 and already carries a
dot-ladder plus plain-word EN/ZH leg names. **This spec adopts that ratified idiom rather
than inventing a replacement**, retinted to the workspace accent and renamed `.oew-lseg`.

Row anatomy: rank (mono) · ticker + sector · state chip · **ladder + `K/N` (mono)** ·
context line · caution chips.

The bare `K/N` beside N visible segments is self-labeling, not jargon — the denominator is
on screen. It is not the banned "K-of-N" *vocabulary*, which the doctrine bans as an
unexplained construction.

State chips (survive per the ruling): *Lining up / 信号齐备* · *Crowding in / 资金涌入* ·
*On the radar / 雷达关注*.

Leg names — **reuse the existing `A_LEGS` / `B_LEGS` arrays from
`templates/flow_leaders.html.j2:41-58` verbatim.** Nothing new is written:

| Board A (8) | ZH |
|---|---|
| Money keeps showing up | 资金反复出现 |
| Unusually heavy premium | 权利金异常放大 |
| New positions opened | 建立新仓位 |
| Spread across expirations | 多个到期日铺开 |
| Price is leading | 价格领先 |
| Near 52-week high | 接近52周高点 |
| Volume confirms | 成交量确认 |
| Not a failed breakout | 非假突破 |

| Board B (7) | ZH |
|---|---|
| Recently washed out | 近期洗盘 |
| Oversold | 超卖 |
| Turn signal is on | 拐点信号已亮 |
| Money flipped positive | 资金转为流入 |
| New positions opened | 建立新仓位 |
| Volume confirms | 成交量确认 |
| Not a failed breakout | 非假突破 |

**Hover is per-LADDER, not per-dot** — a deliberate deviation from the lane brief's "plain-
word hover per dot". Each segment is 8px wide; eight individual hover targets are far below
the 44px touch minimum and would be unusable on phones, and eight separate popovers to read
one row is worse than one. The single ladder tip names *every* leg, split into confirming
and not-yet, which delivers the same information in one gesture and works on touch. This is
also what #3224 shipped, so adopting it keeps one idiom across the estate.

Ladder hover text is composed exactly as the #3224 macro does — "N of M signs confirming ·
<lit list>. Not yet — <missing list>" / "M 项信号中 N 项确认：<…>。尚缺：<…>".

Segment states: `.on` accent · `.off` grey tile (**visible**) · `.nul` dotted, excluded
from the denominator (data not in).

Caution chips: *Earnings soon / 临近财报* (`--warn`) · *Same-day heavy / 当日到期为主* ·
*Both sides / 双向押注* · *Looks hedged / 疑似对冲* · *Fragile tape / 盘面脆弱*.

Board footers — A, stance **Watch — don't chase**: "Repeated buying marks where attention
is, not where the edge is. Names here are a place to start reading, not a queue to buy." /
"反复买入标记的是关注度所在，而非优势所在。此处的标的是研究的起点，而非买入队列。"
B, stance **Get ready**: "A turn this fresh can fail. Wait for it to hold rather than buying
the first green day." / "如此新近的转向可能失败。应等待其站稳，而非在第一个上涨日买入。"
ETF strip, stance **Ignore**: "These are estimates from share-count changes, not reported
fund flows. Useful as a background check, not as a signal." / "这些是根据份额变动推算的估算
值，而非公布的基金流量。可作背景参考，不构成信号。"

---

## §6 Payload fetch map

Per the ruling's payload law: **Brief context baked inline; Scanner / Ticker / Leaders
lazy-fetched on mode activation via plain `fetch()`.** No JS-injected `<script>` loaders —
they bypass asset stamping (#3372).

| Mode | When | Source | Cache |
|---|---|---|---|
| Brief | baked inline at render | `site/flow_desk.json`, `data/market_structure/latest.json`, `site/vol/regime.json`, `site/gex/{SPX,SPY,QQQ,IWM}.json`, `site/flowleaders/leaders.json` | n/a |
| Scanner | first activation | `site/screenerdata/rows.json` (new, M-XP c) | session |
| Ticker | first activation + on ticker change | `site/gex/<T>.json` + `site/flow/<T>.json` | per ticker |
| Leaders | first activation | `site/flowleaders/leaders.json` | session |

The chrome is **always inline** — the session receipt, posture console and close line must
never depend on a fetch, or the page's honesty layer flashes empty.

Routing: `#brief` / `#scanner` / `#ticker` / `#leaders`, with `?t=<TICKER>` for Ticker.

---

## §7 Finding for the orchestrator — the masterplan's §1.4 is a stale render

Verified on fresh `origin/main`, 2026-07-25:

```
grep -c "Money keeps showing up"           site/flow_leaders.html  → 0
grep -o "TSBrd\|NotTrap\|PriceOK"          site/flow_leaders.html  → NotTrap 50, PriceOK 25, TSBrd 25
grep -o "Lining up\|Crowding in"           site/flow_leaders.html  → 0
grep -c 'class="ladder"'                   site/flow_leaders.html  → 0
```

The template (`templates/flow_leaders.html.j2`) has carried the compliant dot-ladder,
plain-word leg names and plain-word state chips since **#3224** (`68464189bab`). The baked
`site/flow_leaders.html` is a **pre-#3224 render** and still ships the banned-vocab slug
wall on the live page.

So the masterplan's "one page violates doctrine" is a **render-lane staleness bug**, not a
template defect. Recent commits touching `site/flow_leaders.html` are nav-icon sweeps
(#3484/#3473/#3462), which appear to be surgical edits to baked files rather than full
re-renders — that masked the staleness. **Other pages may be stale the same way.** Tracked
as a separate task; M-CMD should not attempt a vocabulary "fix" that already exists.

---

## §8 Interaction inventory

| Trigger | Element | Behaviour |
|---|---|---|
| click | `.oew-tab` | set `aria-selected`, swap `.oew-mode.active`, lazy-fetch on first activation, update hash |
| click | `.oew-tkchip`, `.oew-sc-tk` | activate Ticker mode with that symbol |
| click | `.oew-preset` | single-select, `aria-pressed`, re-filter rows |
| click | `.oew-seg button` | set `data-view` on the table → column visibility |
| click | `.oew-cta` | open Terminal (new tab, `rel="noopener"`) |
| toggle | `.oew-shelf` `<summary>` | expand raw structure (closed by default) |
| hover / focus | `[data-tip-en]` | LENS popover (theme.js). Covers: quality value, all pips, close line, ladder, `?` helps, caution chips, what-changed chips, row-age cells |
| hover | `table tbody tr` | row tint + reveal `→` on the ticker |
| keyboard | all controls | visible focus ring `2px solid var(--oew-accent)`; `?` and shelf summary are focusable |

`prefers-reduced-motion: reduce` disables all animation and transition.

---

## §9 States

**Loading** (Scanner/Ticker/Leaders, first activation): the chrome renders fully; the mode
surface shows `.oew-skel` — 4 muted bars plus a plain-word line ("Loading the screener
table for this close… / 正在加载本次收盘的筛选表…"). No spinner, no shimmer under reduced
motion.

**Stale**: `.oew-banner` (warn-tinted) above the surface, stating the vintage in plain
words and that it is shown anyway — e.g. "Scanner data is from 2026-07-23, two sessions
old. Showing it anyway — treat the levels as stale." / "筛选数据来自 2026-07-23，已过去两
个交易日。仍予显示 — 请将水位视为陈旧。" The close line independently narrows, so staleness
is signalled twice by construction.

**Empty**: plain sentence + what would fill it, never a bare "no data".

**Anon**: this family is open — **no regwall, no gating, no blur**. The Terminal CTA is the
only destination that may require an account, and it must not render as gated on this page.

---

## §10 Responsive

| Breakpoint | Change |
|---|---|
| ≤1000px | index cards 4 → 2 col |
| ≤900px | receipt grid → 1 col (stamp above console); `.hide-sm` table columns drop; Ticker three-reads → 1 col |
| ≤860px | names-for-tomorrow rail → 1 col |
| ≤820px | Leaders row → 3-area grid (`t s` / `l l` / `r r`), rank hidden |
| ≤760px | posture console 4 → 2 col |
| ≤640px | Ticker ladder band hidden (rows retained); level rows → 2 col |
| ≤560px | index cards → 1 col; sector rows drop the tone column to its own line; **screener table → row cards** via `td::before { content:attr(data-k) }`, zh via `attr(data-k-zh)` |

Mode tabs are a horizontally scrollable strip at every width.

**The table→card collapse is new.** The house has no such pattern (verified: no
`data-label`/`attr()` technique anywhere). The existing answer is horizontal scroll +
sticky first column + column hiding, which is miserable for a 10-column table at 375px.
Every `<td>` therefore carries both `data-k` and `data-k-zh`.

---

## §11 Doctrine compliance

| Law | How this design satisfies it |
|---|---|
| Tier 1 = state + stance | Every panel states its state and the reader's stance toward it in plain words — as a chip from the closed vocabulary on the one panel that is the read's decision element, and as its own caveat sentence everywhere else (§0.16). Word budgets held as ceilings. |
| Verdict law (`OIP_MASTERPLAN.md` §3) | Exactly one decision element per page: Ticker mode's name-header `.oew-ic-foot`, the sole `data-verdict-surface`. The `.oew-nofuse` banner and the "Today's measured flow" footer state facts and cast no second verdict (§0.16). |
| Plain words | No internal state names, study IDs, or raw slugs in visible copy. Sector names via `td()` display names. |
| Numbers carry meaning | Every figure sits in a fill-track with a visible denominator, or arrives with an interpreting clause. |
| Word budgets | Titles ≤4 words, subtitles ≤14, one footer sentence, one as-of per panel. |
| Honesty survives translation | ZH copy is independently plain — no EN state names dropped into ZH. Approximation marked with `~` in both. |
| Nulls in plain words | `.nul` ladder segments excluded from the denominator; stale banner states vintage plainly; receipts on hover. |
| Technicals demoted | Provenance walls, mechanics, and receipts all live in LENS tips and the collapsed raw shelf. |

**Banned-vocab self-check (run, not asserted).** Method: strip `<style>`, `<script>`,
comments, and every `data-tip-*` / `aria-label` value from the mockup, then strip all tags
— leaving only text a user can see — and grep 40 banned terms (`IGNITION`,
`UPTURN_CONFIRMED`, `slow reco`, `expected-null`, `forward meter`, `display-tier`,
`K-of-N`, `confluence`, `gauntlet`, `prereg`, `Oracle P`, `organ`, `lobe`, `kernel`,
`FlowZ`, `TSBrd`, `NotTrap`, `PriceOK`, `NearHigh`, `VolOK`, `Recur`, `TurnOrg`, `Inflect`,
`n=`, `FDR`, `z-score`, `t-stat`, `rank-IC`, `cross-sectional`, `multi-timeframe`,
`validated`, `us_sector`, `yCaution`, `BothSides`, `EarnWin`, `H52`, `y:long`, `y:short`,
`pain_dist`, `median_depth`, `wilson_`).

**Result: 1 match, adjudicated not a violation.** The word *washout* appears in
"Turned back up after a washout / 洗盘后重新转强". That is ordinary market English with a
plain ZH pair, not the machine slug `B1_washout_recent` or the old `Washout` chip — the
doctrine bans internal vocabulary, untranslated statistics and raw slugs, none of which
this is. Every other term: zero hits. "Validated" does not appear in visible copy (§4.2).

**Bilingual parity check:** 202 `.l-en` spans / 202 `.l-zh` spans (exact parity), 24
`data-tip-en` / 24 `data-tip-zh` (exact parity), and **0** `title=` attributes containing
non-ASCII (the CI-guarded rule).

---

## §12 Verification performed

- Mockup opens from `file://` and from a local server with **zero console errors** (all 8
  crop captures ran clean under Playwright).
- All four modes switch, lazy-load, and cache.
- EN ⇄ ZH toggle verified: `--up` → `#e06464`, `--down` → `#45b873`; `.l-en` hidden,
  `.l-zh` shown; accent and stamp correctly do **not** flip.
- Light ⇄ dark verified under `.soft-contrast`.
- 375px: no horizontal overflow (`scrollWidth == innerWidth`); table collapses to cards.
- Two bugs found and fixed during design: the `.oew-seg` collision (squashed the Scanner
  view control to 7px) and invisible unfilled pips/segments (destroyed the denominator).

Crops: `mockups/oeu_workspace/crops/01_brief_en_dark.png`, `02_scanner_en_dark.png`,
`03_ticker_en_dark.png`, `04_leaders_en_dark.png`, `05_brief_zh_dark.png`,
`06_brief_en_light.png`, `07_brief_mobile_375.png`, `08_scanner_mobile_375.png`.
