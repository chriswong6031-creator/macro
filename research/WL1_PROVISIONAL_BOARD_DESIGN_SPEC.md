# W-L1 — provisional close-pass board · PINNED DESIGN SPEC

Status: **design spec, pinned.** Surface layer for Breathing Platform W-L1
(`research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` §3-2, §4 W-L1).

Everything in §3–§7 is **decided**. The builder implements it; the builder does
not re-choose palette, copy, wording, hue, chip shape, or which state gets which
treatment. §8 lists the decisions most likely to get "cleaned up" by accident and
why each one is the way it is. Open questions are in §9 and route back to the
commissioning session, not to a builder's judgment.

Reference crops (the look travels as files, never as prose):
`mockups/refs/breathing-platform/wl1_<state>_<lang>_<theme>.png` —
16 crops = 4 states × {en, zh} × {dark, light}.
Regenerate: `python3 mockups/refs/breathing-platform/gen_wl1.py`
Verify: `python3 mockups/refs/breathing-platform/shoot_wl1.py`

---

## §0 ACCEPTANCE GATES — "not done unless"

The W-L1 surface PR is not done unless every line below is true and evidenced in
the PR body.

1. **Per-state visual crops in the PR body**, taken from the real page (not the
   mockup), for all four states × light + dark + zh. A rendered artifact, not a
   description. Compare each against the matching
   `mockups/refs/breathing-platform/wl1_*.png`.
2. **The stamp is derived from the payload that produced the cards.** A board
   showing last night's cards can never render the "tonight's picks" stamp. Pin
   this with a test that feeds a stale/missing provisional payload and asserts
   the `ahead` stamp is absent. This is the one failure that would actively lie
   to the reader, and its whole failure class is already in the house's history
   (frozen boards reading as fresh).
3. **Computed-style verification in both themes**, not eyeballing: every new
   ink/fill pair ≥ 4.5:1 measured after compositing. Reuse
   `mockups/refs/breathing-platform/shoot_wl1.py`'s contrast routine — note its
   `_rgb` `color(srgb …)` branch, without which every `color-mix` pair measures a
   phantom 1.00:1.
4. **Header height invariance**: `.nbgrid`'s offset from the panel top is within
   **4px** across all four states, at desktop and at 680px, in en and zh. The
   provisional→confirmed flip happens under a reader who may be looking at the
   board; it must not shove the grid.
5. **Exactly one stamp, never two**, and **no stamp at all** on the confirmed
   board. Absence is a state (§3), so assert absence.
6. **Bilingual from birth.** Every string in §5 ships `l-en` + `l-zh`. No
   translated text in any `title=` attribute (CI-guarded). If a string is emitted
   from a builder/JS rather than the template, the zh twin ships in that same
   place — zh copy lives in templates **and** builders.
7. **No banned vocabulary on the glance tier.** The words "close-pass", "W-L1",
   "provisional" (as UI copy), "armed", "reconciler", "admission", any study or
   pack ID, and any untranslated statistic appear nowhere a reader can see
   without hovering. Tier-2 copy has its own register and leaks no internals
   either (§6).
8. **No falsifier/refutation vocabulary anywhere front-facing** — nothing
   "failed", "refuted", "invalidated", "证伪". A night that did not produce a
   board is described by what the reader gets, not by what the system did.
9. **No new page, no new header family, no third page chrome.** This is an
   extension of the existing `#us-standouts` panel and the shared
   `_prophet_card.html.j2`.
10. **No `data/` writes** from anything on this surface path, and no live-plane
    read that can reorder, re-rank, or re-admit a card. The surface displays the
    delta; it never computes it (A7 — the presentation tier never originates a
    signal).

---

## §1 The rule the whole design comes from

> **The stamp appears only when the board is not the current nightly board of
> record.** Ahead of the record → provisional blue, dashed. Behind it → muted,
> solid. Level with it → no stamp at all.

One axis, asked once. It means a reader never reads a badge to learn that
nothing is unusual, and the two abnormal states are opposite directions on the
same axis rather than two unrelated banners — so the vocabulary is learned once
and never competes with the card system underneath.

Everything else follows: the perforated panel edge is "not countersigned yet";
the per-card `Adjusted` mark is the receipt of a name that moved when the
countersignature landed; the confirmed board carries no ornament because it is
the ordinary state.

---

## §2 What is new, in full

Three additions. Nothing else changes.

| # | Element | Where | Lives in |
|---|---|---|---|
| A | Board-state **stamp** | inline in the `#us-standouts` header, after the `<h2>` | `dashboard.html.j2` |
| B | Board-state **note line** (one line, one slot, mutually exclusive contents) | directly under the header row | `dashboard.html.j2` |
| C | Per-card **`Adjusted`** mark | one new `k` value in the existing `marks` row | `_prophet_card.html.j2` (CSS only) |

There is **no** new panel, no new grid, no second footnote, no new page, no new
timestamp, and no animation.

---

## §3 The four states

### State 1 — Evening provisional (~17:30–18:30 ET, until the nightly lands)

- Panel: `data-boardstate="ahead"` → perforated top edge.
- Stamp: `.pbs .pbs-ahead`, text `◐ Tonight's picks` / `◐ 今晚选股`.
- Note: stance-led, `Get ready — set from today's close, confirmed by morning.`
- Cards: tonight's provisional picks. **No per-card marks are added** — the whole
  board is provisional and the stamp says so once. A per-card provisional chip on
  every card is the vetoed "constant repeated on every row" defect (doctrine
  Law 4).
- Crops: `wl1_provisional_{en,zh}_{dark,light}.png`

### State 2 — Post-nightly confirmation (next morning)

- Panel: **no** `data-boardstate` attribute → no edge.
- Stamp: **none.** The board is the record.
- Note: the receipt —
  `13 of 15 confirmed overnight · 1 adjusted, 1 left the board`, figures in
  tabular numerals, words never.
- Cards:
  - **confirmed** → no mark. This is N−1 of the board; the constant lives in the
    receipt line once.
  - **adjusted** → one `Adjusted` / `已调整` mark (§5), with the Tier-2 tip.
  - **dropped** → the card is **not rendered.** A name that no longer meets the
    bar cannot sit inside a grid whose meaning is "these are the picks" — that
    would be a false claim by placement. It is named in the receipt's Tier-2 list
    instead, with the plain-word "this is not a sell instruction" clause (§6).
  - **added overnight** → the existing `new` mark already means "new to the
    board". Do not invent a fifth kind.
- Lifecycle: the receipt shows only while it describes the most recent
  confirmation, i.e. until the next evening board replaces it. It is not a
  permanent footnote.
- Crops: `wl1_confirmed_{en,zh}_{dark,light}.png`

### State 3 — The early update did not land

- Panel: `data-boardstate="behind"` → no edge (the edge means "ahead" only).
- Stamp: `.pbs .pbs-behind`, `Last confirmed · Aug 7` / `上次确认 · 08-07`.
  The date is mandatory — it is what makes a stale board impossible to mistake
  for a fresh one.
- Note: `Tonight's early update isn't in — these are last night's confirmed
  picks. Check a live quote before you act.`
- Cards: the last confirmed nightly board, **carrying that night's as-of dates**
  (a card dated today under a "last confirmed Aug 7" stamp is a contradiction the
  reader will catch).
- **No amber, no red, no banner fill, no border.** This is quiet honesty, not a
  caution. Deliberately *not* `.nb-stale-note`'s amber-on-tint treatment.
- Crops: `wl1_stale_{en,zh}_{dark,light}.png`

### State 4 — Weekend / holiday

- Identical treatment to State 3 — same class, same stamp, same date.
- Note differs, and the difference is the honesty: `Markets are closed — these
  are the last confirmed picks. The board updates after the next session's
  close.`
- It does **not** say "check a live quote" (there is no live quote on a Saturday)
  and it does **not** imply something is being repaired. Nothing is wrong; the
  market is shut.
- Crops: `wl1_closed_{en,zh}_{dark,light}.png`

### Transition rules

| From → To | Trigger | What flips |
|---|---|---|
| confirmed → **ahead** | evening board publishes | add `data-boardstate="ahead"`, stamp in, note → provisional |
| **ahead** → confirmed | nightly board of record publishes | remove attribute, stamp out, note → receipt, `adjusted` marks painted, dropped cards gone |
| confirmed → **behind** | evening board did not publish by its deadline | add `data-boardstate="behind"`, stamp in with the last confirmed date, note → state 3 |
| **behind** → confirmed | the nightly lands normally | remove attribute; **no receipt line** (there was no provisional board to reconcile against) |
| any → **behind** (closed) | non-session day | stamp as state 3, note → state 4 |

Between 16:15 and the evening publish the board is simply the previous nightly
board **with no stamp** — it is still the record, and nothing provisional exists
to declare. Do not invent a "computing" state.

---

## §4 Exact CSS

### 4.1 Tokens — add to `templates/theme.css`

Two tokens, following the file's own `--ink-*` convention: `--prov` is the
fill-grade hue (tints, rules, borders); `--prov-ink` is the text-grade one. Dark
keeps ink ≡ raw so dark renders byte-identical to a single-token version; light
deepens toward `--text`.

```css
/* W-L1 provisional plane. Same hue as the P1 .pv-live chip's local --plvc, and
   that is the point: the ◐ strip and the ◐ board stamp name the SAME epistemic
   tier — settled by the tape, not yet by the record. Direction-neutral, so
   红涨绿跌 holds by construction; never derive it from --up/--down. */
:root { --prov: #62a0e8; --prov-ink: var(--prov); }
html[data-theme="light"] { --prov: #2f6fd0;
  --prov-ink: color-mix(in srgb, var(--prov) 82%, var(--text)); }
```

Measured after this split: **5.35:1 dark / 5.21:1 light** for the stamp ink. The
fill-grade blue used directly as type measured **4.22:1** on light — under AA,
and invisible to anyone who only ever looked at the dark shot.

`templates/theme.css` is a paired plain-copy asset: ship the byte-matching
`site/theme.css` in the same PR (`python -m scripts.check_template_site_sync --fix`).

**Recommended follow-on (not required for W-L1):** repoint `_prophet_card.html.j2`'s
local `--plvc: #62a0e8` / `html[data-theme="light"] .pv-live{--plvc:#2f6fd0}` at
`var(--prov)` so the two provisional surfaces cannot drift apart. Do it as its
own change with its own visual proof, not folded into this one.

### 4.2 Stamp + note — add to `dashboard.html.j2`'s prophet-board CSS block

```css
/* ═══ W-L1 BOARD STATE STAMP ═══════════════════════════════════════════════
   ONE axis: where does this board stand relative to the nightly board of record?
     data-boardstate="ahead"   provisional blue, DASHED — built from today's
                               close; the overnight pass has not countersigned it
     data-boardstate="behind"  muted, SOLID            — the record did not
                               arrive (or the market is shut); this is the last
                               confirmed board
     attribute ABSENT          no stamp at all         — the board IS the record
   Absence is the third state and it is load-bearing: a reader never has to read
   a badge to learn that nothing is unusual.
   Dashed=pending is not invented here — .pv-trg-soon already ships it for the
   'imminent' trigger chip. */
.pbs{display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:800;
  letter-spacing:.06em;text-transform:uppercase;line-height:1.35;padding:2.5px 9px;
  border-radius:6px;white-space:nowrap;flex:none}
/* squarer than the board's 999px pills on purpose: this is a stamp on the whole
   board, not another chip in the chip row. 6px matches the .pv-mk marks family. */
.pbs-ahead{color:var(--prov-ink);background:color-mix(in srgb,var(--prov) 11%,transparent);
  border:1px dashed color-mix(in srgb,var(--prov) 62%,transparent)}
.pbs-behind{color:var(--muted);background:color-mix(in srgb,var(--muted) 9%,transparent);
  border:1px solid color-mix(in srgb,var(--muted) 34%,transparent)}
.pbs-dt{font-variant-numeric:tabular-nums}

/* THE UNSEALED EDGE — the one place this design spends boldness.
   A board-level state has to survive a full-page scroll-past, and the house has
   already measured that a rim treatment ALONE does not (see the .pv-featured
   note in _prophet_card.html.j2). So the panel's own top edge goes perforated
   while the board is uncountersigned. Long dash (15/9), never a fine dot — a
   fine dotted line reads as a broken border, a long dash reads as a deliberate
   perforation. Costs zero height: it rides the existing 1px border.
   Static by choice: 15 cards and a strip that already animates its rows in are
   enough movement on this page, so there is no animation here and therefore no
   prefers-reduced-motion kill block to keep in sync (the strongest form of that
   compliance is having nothing to disable). If you ever add motion here, the
   kill block must name ::before explicitly. */
.panel[data-boardstate]{position:relative}
.panel[data-boardstate="ahead"]::before{content:"";position:absolute;left:-1px;right:-1px;top:-1px;
  height:2px;border-radius:14px 14px 0 0;pointer-events:none;
  background:repeating-linear-gradient(90deg,
    color-mix(in srgb,var(--prov) 78%,transparent) 0 15px,transparent 15px 24px)}

/* SLOT B — one line under the header. Three mutually exclusive contents
   (provisional stance / confirmation receipt / last-confirmed stance), never two
   at once, so the header height moves by at most a rounding wobble and the board
   below never shoves. NOT a second footnote: .pb-fn stays the panel's single
   permanent methodology note (doctrine Law 4).
   Deliberately NOT .nb-stale-note's amber-on-tint banner: quiet honesty, not a
   caution — no fill, no border, muted ink.
   text-wrap:pretty is load-bearing, not polish: without it the trailing `?` help
   icon wrapped alone onto a second line on the two longest notes, and that
   ALSO cost 18.8px of header height on those states — measured 18.8px spread
   before, 1.5px after. */
.pbs-note{font-size:11.5px;line-height:1.5;margin:7px 0 1px;color:var(--muted);
  max-width:94ch;text-wrap:pretty}
.pbs-note b{font-weight:700;color:var(--text)}
.pbs-fig{font-variant-numeric:tabular-nums;font-weight:700;color:var(--text)}
.pbs-note .help{margin-left:5px;vertical-align:1px}

@media (max-width:680px){
  .pbs{font-size:9.5px;padding:2px 7px}
  .pbs-note{font-size:11px}
}
```

### 4.3 The one card change — `templates/_prophet_card.html.j2`

**Insertion point:** inside `pv_css()`, immediately after the `.pv-mk-blow` rule
and before the `.pv-mk-i[data-tip-en]` rule. CSS only — no markup change: the
macro already renders `pv-mk-{{ _mkk }}` for whatever `k` the caller passes, so
`{'k':'adj', …}` works with no template edit.

```diff
 .pv-mk-blow{font-weight:800;letter-spacing:.04em;text-transform:uppercase;
   color:var(--ink-warn,var(--warn));
   background:color-mix(in srgb,var(--warn) 8%,var(--panel));
   border-color:color-mix(in srgb,var(--ink-warn,var(--warn)) 50%,transparent)}
+{# 'adj' — the overnight pass moved something on this name after the evening
+   board. DESATURATED ON PURPOSE, and this is the whole point of the rule: at
+   the marks row's normal formula — color-mix(<hue> 58%, --text) on a 12% tint —
+   it came out the same blue as .pv-mk-new, which sits inches away on the same
+   board and means something completely different ("new to the board" is a
+   signal; "adjusted" is a receipt). Two meanings in one hue is a defect no
+   amount of wording fixes. The fix is WEIGHT, not hue: 'adjusted' resolves
+   toward --muted so it reads as the quietest thing in the row while 'new' keeps
+   the saturated --info. That also matches what the mark is worth to the reader
+   — the honest answer to "so what do I do" here is nothing; the card already
+   shows the updated numbers. Measured 4.83:1 dark / 4.67:1 light. #}
+.pv-mk-adj{font-weight:700;letter-spacing:.04em;text-transform:uppercase;
+  color:color-mix(in srgb,var(--prov-ink) 42%,var(--muted));
+  background:color-mix(in srgb,var(--prov) 7%,transparent);
+  border-color:color-mix(in srgb,var(--prov) 30%,transparent)}
 {# a marks chip carrying a data-tip is a hover target, not a link — say so #}
 .pv-mk-i[data-tip-en]{cursor:help}
```

Caller passes, on an adjusted name only:

```jinja
{'k': 'adj', 'en': 'Adjusted', 'zh': '已调整',
 'tip_en': '…', 'tip_zh': '…'}   {# tip text: §6.4 #}
```

`adj` is **not** in the macro's `_MK_NOTIP` tuple, so its tip renders — correct:
unlike `feat`/`new`, this mark names something the reader cannot infer.

---

## §5 Markup + the complete copy table

### 5.1 Header insertion — `templates/dashboard.html.j2`

Into the `#us-standouts` header flex row, after the `<h2>` and before the
existing `.muted` subtitle span. `_bs` is the board-state dict (§7).

```jinja
<div class="panel span12 notable" id="us-standouts"
     {%- if _bs and _bs.get('rel') %} data-boardstate="{{ _bs.rel }}"{% endif %}>
  <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
    <h2 style="margin:0">{{ t('Prophet Stock Signals', '先知选股') }}</h2>
    {%- if _bs and _bs.rel == 'ahead' %}
    <span class="pbs pbs-ahead">{{ t("◐ Tonight's picks", '◐ 今晚选股') }}</span>
    {%- elif _bs and _bs.rel == 'behind' %}
    <span class="pbs pbs-behind">{{ t('Last confirmed', '上次确认') }}
      · <span class="pbs-dt">{{ _bs.confirmed_label }}</span></span>
    {%- endif %}
    … existing view toggle + subtitle span, unchanged …
  </div>
  {%- if _bs and _bs.get('note') %}
  <div class="pbs-note">{{ … per §5.2 … }}<span class="help">?<span class="tip tip-wide">…</span></span></div>
  {%- endif %}
  … existing board, unchanged …
```

`confirmed_label` is pre-formatted by the caller in the card partial's own date
idiom — EN `Aug 7`, ZH `08-07` — so the stamp reuses the format the reader
already sees on every card's zone row.

### 5.2 Copy table — every string, EN + ZH

Glance tier. Nothing here may be paraphrased at build time.

| Key | EN | ZH |
|---|---|---|
| `stamp.ahead` | `◐ Tonight's picks` | `◐ 今晚选股` |
| `stamp.behind` | `Last confirmed · <date>` | `上次确认 · <date>` |
| `note.ahead` | `**Get ready** — set from today's close, confirmed by morning.` | `**可以开始准备** — 依今日收盘价选出，明早完成确认。` |
| `note.confirmed` | `<b>N</b> of <b>M</b> confirmed overnight · <b>a</b> adjusted, <b>d</b> left the board` | `<b>M</b> 只中 <b>N</b> 只隔夜确认 · 调整 <b>a</b> 只，离榜 <b>d</b> 只` |
| `note.behind` | `Tonight's early update isn't in — these are last night's confirmed picks. Check a live quote before you act.` | `今晚的提前更新未到位，以下为昨晚确认的选股名单。操作前请先看一下实时报价。` |
| `note.closed` | `Markets are closed — these are the last confirmed picks. The board updates after the next session's close.` | `休市中，以下为最近一次确认的选股名单。下一个交易日收盘后更新。` |
| `mark.adj` | `Adjusted` | `已调整` |

Copy notes that are decisions, not suggestions:

- **`note.confirmed` clause order in ZH is deliberately not the EN order.**
  `调整 1 只，离榜 1 只` (verb-first counting) rather than a literal
  `1 只有调整` — which reads as "**only** 1" (只有 = only) and is a genuine
  mis-parse, not a style preference.
- **`note.behind` reuses the ratified `.nb-stale-note` stance verbatim** in both
  languages (`Check a live quote before you act.` /
  `操作前请先看一下实时报价。`). Do not reword ratified copy.
- **`note.closed` deliberately drops the live-quote advice** and promises a
  refresh time instead. Telling someone to check a live quote on a Saturday is
  advice that cannot be followed.
- The stance word in `note.ahead` is bolded (`.pbs-note b`) because it is the
  answer to "so what do I do" and it must survive a two-second glance. `Get
  ready` is from the doctrine's fixed stance vocabulary — not a phrase to
  improve on.
- Figures in `note.confirmed` are wrapped in `.pbs-fig` (tabular numerals).
  Numerals only — never the surrounding words.

---

## §6 Tier-2 copy (hover / `?` receipts)

Its own register: state the mechanism in plain words, leak no internals. None of
these strings may contain a program name, a pack name, a study ID, a file path,
a bare statistic, or the words "close-pass" / "admission" / "armed".

### 6.1 Provisional `?` (state 1)

**EN** — The board is rebuilt from the day's closing prices as soon as the
session ends, so tonight's picks are up within a couple of hours of the close
instead of overnight. What makes the board is decided the same way the overnight
pass decides it — but a few inputs only arrive later at night, so a name can
still be adjusted or leave the board before morning. The overnight board stays
the one of record; whatever changes is marked the next morning.

**ZH** — 收盘后，系统会用当日收盘价重算整个榜单，因此今晚的选股在收盘后一两个小时内就能看到，不必等到半夜。入选标准与隔夜复核完全一致，只是有几项数据要到深夜才到位 —— 所以个别股票在明早之前仍可能被调整或移出榜单。隔夜榜单仍是最终依据，凡有变动，第二天早上都会标出来。

### 6.2 Confirmation receipt `?` (state 2)

Must also render the dropped names, by ticker, in this popover — that is where
the per-name delta is honest without polluting the pick grid.

**EN** — Last evening's board was built from the day's closes; the overnight pass
then rebuilt it with the inputs that only arrive at night. Confirmed means the
name came through unchanged. Adjusted means its entry range, stage or place in
the order moved — the card shows the current numbers. Left the board means it no
longer meets the bar; that is not a sell instruction for a position you already
hold. *(then: `Left the board: TSLA`)*

**ZH** — 昨晚的榜单是按当日收盘价生成的；隔夜复核会用深夜才到位的数据重算一遍。「确认」表示这只股票原样通过；「已调整」表示入场区间、阶段或排序位置有变动，卡片上显示的是最新数值；「已离榜」表示它不再达标 —— 这不是让你卖出已有仓位的指令。*(then: `已离榜：TSLA`)*

### 6.3 Last-confirmed `?` (states 3 and 4)

**EN (state 3)** — Tonight's early rebuild didn't publish, so the board still
shows the picks the overnight pass confirmed on the date stamped above. The
overnight pass runs regardless and will refresh the board tonight. Prices on the
cards are from that date, not from today.

**ZH (state 3)** — 今晚的提前重算没有发布，所以榜单显示的仍是上方日期那一晚确认的选股。隔夜复核照常运行，今晚会刷新榜单。卡片上的价格来自那一天，不是今天。

**EN (state 4)** — Markets were closed today, so there is nothing new to add. The
board shows the picks confirmed after the last session, and it refreshes after
the next one closes.

**ZH (state 4)** — 今天休市，没有新的内容。榜单显示的是上一个交易日之后确认的选股，下一个交易日收盘后会刷新。

### 6.4 `Adjusted` mark tip (per card)

**EN** — The overnight pass changed something on this name after last evening's
board — most often the entry range or where it sits in the order. The card
already shows the updated numbers.

**ZH** — 隔夜复核后，这只股票有变动 —— 多为入场区间或排序位置。卡片上显示的已是更新后的数值。

---

## §7 Data contract

The surface consumes one small object. Name it `_bs` in the template.

| Field | Type | Meaning |
|---|---|---|
| `rel` | `'ahead'` \| `'behind'` \| `None` | position vs. the nightly board of record. `None` → no stamp, no attribute. |
| `note` | `'ahead'` \| `'confirmed'` \| `'behind'` \| `'closed'` \| `None` | which note-line content renders. `None` → no note line. |
| `confirmed_label` | str | pre-formatted as-of of the last confirmed board (EN `Aug 7` / ZH `08-07`). Required when `rel == 'behind'`. |
| `n_confirmed` `n_total` `n_adjusted` `n_dropped` | int | the receipt counts. Required when `note == 'confirmed'`. |
| `dropped` | list[str] | tickers named in the Tier-2 receipt (§6.2). |

Per-card: the builder passes `{'k':'adj', …}` into the card's existing `marks`
list for adjusted names only.

**Invariants the builder must enforce:**

- `rel == 'ahead'` **only** when the rendered cards came from the evening board.
  Never derive it from a clock. (Gate §0-2.)
- `note == 'confirmed'` only while it describes the most recent confirmation.
- `note == 'confirmed'` is impossible after a `behind` night — there was no
  provisional board to reconcile against, so no receipt is emitted.
- `n_confirmed + n_adjusted + n_dropped == n_total`. Print the arithmetic
  honestly; if the numbers do not reconcile, emit no receipt rather than a
  wrong one.
- The `adj` mark never renders without the receipt line — they are published
  together or not at all.
- Nothing on this path writes `data/`, and nothing here reorders or re-ranks a
  card.

**Publication mechanism is the builder's call, not this spec's** — whether the
evening board arrives as a re-rendered page or as a live-plane payload hydrated
client-side. Either is compatible. What the spec fixes is the constraint: if it
hydrates, the stamp and note slots must be reserved so the board does not shove
when the payload lands (the `.plv-body` height-contract discipline), and the
stamp must not paint before the cards it describes.

---

## §8 Do not re-decide these

Each of these looks like something to tidy up. Each is deliberate.

1. **Two `◐` on one page** (the live strip and this stamp). They name the same
   epistemic tier — settled by the tape, not yet by the record. Teaching a second
   glyph for one idea is a tax on the reader. Not a bug.
2. **The confirmed board has no badge.** Absence is the third state (§1). Adding
   a green "Confirmed" stamp puts a badge on the ordinary case and stamps a
   constant N times.
3. **`Adjusted` is desaturated, not full-strength blue.** At the marks row's
   normal formula it collided with `new`. See the §4.3 comment.
4. **Dropped names are not rendered as ghost cards.** A card inside the pick grid
   claims to be a pick. The receipt names them instead.
5. **The stale state is muted, not amber.** It is not a caution. `.nb-stale-note`'s
   amber treatment is for a different fact (prices behind the market) and can
   still fire independently.
6. **No animation anywhere in this surface**, therefore no reduced-motion kill
   block. If motion is ever added, the kill block must name `::before`
   explicitly.
7. **The perforated edge is on `::before` of the panel, not a border-top.** A
   dashed `border-top` cannot be independently coloured or rounded against the
   panel's own border and would double the hairline.
8. **`text-wrap:pretty` on `.pbs-note` is functional** — it was worth 17px of
   header-height stability (§4.2 comment). Do not drop it as decoration.
9. **`Adjusted` (EN) vs `已调整` (ZH) are not the same length.** Each is the
   natural chip form in its own language. Do not pad the EN to match.
10. **At 390px the four states do NOT share one height, and that is the ruling —
    not an omission** (commissioning session, 2026-08-09, answering §9's escalation
    from the build). Measured: 1280 and 680 hold **0.00px** across all four states
    in both languages, comfortably inside §0-4's 4px budget. At 390px zh the spread
    is **47.31px**, and it falls **between the pairs** `ahead`/`confirmed` and
    `behind`/`closed`, because the two long notes wrap further.

    §0-4 exists so that a flip landing under a reader who is looking at the board
    does not shove the grid. **The only pair that can flip under a live reader is
    `ahead`→`confirmed`, and those two are height-equal at 390px.** `behind` is a
    state you *load into* when the evening update did not land, and `closed` changes
    at session boundaries days apart — neither transitions into the other while
    someone watches. Holding all four to one height would reserve the longest note's
    box on every phone view, permanently, to prevent a shove nobody experiences.

    So the gate's real content is **"states that can transition under a live reader
    must be height-equal at every supported width"**, which this surface satisfies.
    **If the note copy ever changes, re-run the harness at 390 and confirm the
    `ahead`/`confirmed` pair is still equal** — that pair, not the four-way spread,
    is the invariant. Widening `note.confirmed` is the realistic way to break it.

---

## §9 Open questions for the commissioning session

1. **Publication mechanism** (§7) — re-render vs. live-plane hydration is an
   architecture call with a design consequence (whether the card grid can shift
   under the reader). The spec is compatible with both and pins the constraint,
   but the choice should be made deliberately before the builder starts.
2. **Cross-market reuse.** The stamp/note system is market-agnostic and the card
   partial is shared by the US / China / HK / Canada / International boards.
   W-L3 brings CN same-day. Nothing here blocks that reuse, but no non-US board
   should adopt the stamp until its own evening cadence actually exists —
   otherwise the stamp becomes decoration.
3. **`--plvc` → `--prov` consolidation** (§4.1) — worth doing, deliberately out
   of scope here so it carries its own visual proof.

---

## §10 The provisional CARD contract (W-L1d) — added 2026-08-09

§3 State 1 says "Cards: tonight's provisional picks" and §2 says "nothing else
changes". Those cannot both hold, and the identity gate (§0-2) is what exposed it:
the close pass publishes **131** tickers, the rendered grid holds the nightly's
**79**, so the stamp correctly refuses to paint and **no reader has ever seen an
evening board.** This section resolves it. It is the commissioning side's ruling,
answering §9 question 1.

### 10.1 Publication mechanism — SETTLED: client-side render off the live plane

Not a preference — the alternative is closed by measurement already on disk:

- **Server-side re-render is closed.** `closing-bell.yml` is the only evening render
  lane. Its own header measures it at **109 minutes behind an 81-minute spine,
  landing ~17:55 ET against an 18:30 SLA** — 35 minutes of margin — and it
  deliberately excludes `build_prophet`. `close-pass.yml`'s header already reasons
  this out: "Bolting the board onto the end of that spine would spend the whole
  margin to publish the thing the spine does not compute."
- **The live plane is already gated.** Verified three independent ways, because
  this is the claim the whole architecture rests on and getting it wrong would
  publish the paid board:
  1. `app/deploy/Caddyfile:193`'s `@vps_public_live` allowlist is exactly
     `/live/quotes.json /live/breadth.json /live/release_publications.json
     /live/staleness.json` — `prophet_live.json` is not on it.
  2. It is likewise absent from the `@reg_asset` `not path` exemption list
     (`PUBLIC-BOUNDARY-START`, ~line 338), so it falls **inside** `@reg_asset`.
     That block's own security comment states the consequence: "Every other
     `/live/*` artifact … remain inside `@reg_asset` below and therefore pass
     registration + paywall checks before the external file is considered."
  3. `prophet_live.json` appears **nowhere** in the Caddyfile — there is no
     third rule granting it a path.

  So it is served behind the same registration + paywall gate as the dashboard
  page that fetches it, and enriching it exposes nothing the rendered page does
  not already show that same reader. This retires #3391 ("the real board is not
  free content") **for this path only**. The full `us_board_provisional.json`
  stays non-public; it is not what the client reads. **If a future change adds a
  top-level `/live/*` file_server, this reasoning dies with it** — the Caddyfile
  already warns "Never add a top-level `/live/*` file_server", and this surface is
  now one more reason why.
- **One artifact, one poll, one client** is preserved: the rows ride the existing
  `board_state` key on the artifact `_plvFetch()` already polls.

### 10.2 The score slot — no number, ever

The evening board scores **40 of 100 weight points** (`signal` 30 + `runway` 10;
`entry` 25, `edge` 25, `quality` 10 omitted). The nightly card's most prominent
figure is a score on the 100 scale. **A provisional card must not put a number in
that slot.** Showing 40-scale points invites a comparison against yesterday's
numbers where every comparison is wrong, and renormalising 40→100 fabricates the
authority the lane explicitly disclaims (`"renormalised": False` is a pinned
payload invariant).

The card partial already supports this with no new markup: `cx.edge` is checked
`is not none`, with `cx.edge_txt` as a string fallback. So the contract is
**`edge=None` + `edge_txt` carrying a plain-word stance**, with the label overridden
via `edge_label_en`/`edge_label_zh`. Zero markup change, zero CSS change.

### 10.3 Field-by-field — fill what is proven, omit the rest, impute nothing

| Field | Ruling |
|---|---|
| `tk` `sym` `mkt` `href` `date` | **Fill.** Ticker, `'us'`, the nightly's own ticker-page URL pattern, `as_of`. |
| `name` `name_zh` `sec` `sec_zh` | **Fill if a static per-ticker lookup exists** — a sector *label* is a mapping, not the sector-neutralised `edge` leg. Do not conflate them. If no lookup is reachable from this lane, omit; do not derive one. |
| `price_txt` | **Fill** from the session close the pass already holds. |
| `spark` | **Fill if** the sparkline generator is reachable without new inputs; else omit. |
| `edge` | **NULL, always.** §10.2. |
| `edge_txt` + labels | **Fill** — designer-owned copy, §10.4. |
| `zone_*` | **OMIT** (`zone_kind='none'`). The buy zone *is* the entry ladder, which is the omitted `entry` leg. A zone here would be invented. |
| `stage` `stage_key` | **OMIT.** Lane assignment is a nightly curation output. Consequence: the stage-filter bar must be hidden while the provisional board is mounted — a filter over absent buckets is a broken control. |
| `trigger` | **OMIT.** Lives in the separate `top_setups` nightly artifact. |
| `marks` | **OMIT — pass `none`, not `[]`.** §3 State 1 bans per-card marks here, and `[]` still reserves 18px of row height. |
| `featured` `triage` | **OMIT.** Curation. |
| `flags` | **OMIT** unless provably close-derivable. |
| `verb` | **Constrained, not fixed** — see §10.4. |

### 10.4 Designer-owned, inside a fixed boundary

Exact copy and the verb mapping are **not** settled here, deliberately: copy pinned
without being rendered is how this program has burned itself before. A `designer`
renders these and posts crops before the wiring lands. The boundary they work
inside is fixed:

1. **No number anywhere on the card that reads on the 100 scale** (§10.2).
2. **The verb must not be a uniform constant across the board.** Every card
   carrying the same chip is doctrine Law 4's "constant repeated on every row" —
   the same defect §3 State 1 already vetoes for marks. `verb='buy'` on all
   admitted names is additionally *measurably* false: admission over-admits
   **1.7×** and ~45% of these names are dropped by morning.
3. **Any per-card discriminator must be derivable from `signal` and `runway`
   alone** — those are the only two legs this lane owns. `runway` is the
   decision-relevant one (`1 − clip01(ext_z/2)`: room left before the name is
   extended) and maps naturally onto doctrine's "watch — don't chase".
4. **Tier-2 hover carries the receipt**: which legs are in, which are out, and that
   the ranking lands with the nightly. Plain words; no leg slugs, no raw stats.

### 10.5 Invariants the renderer must not break

- **Gate §0-2 must stay meaningful.** Today identity holds because the client
  refuses when payload ≠ DOM. Once the client *renders* the cards, that check
  becomes trivially true and stops protecting anything. Replace it, do not delete
  it: the renderer paints only after a successful qualify, and re-verifies the
  painted `data-ticker` order against the payload **after** mounting, tearing the
  board down on mismatch. A stamp must never outlive the cards it describes.
- **The nightly board is never mutated in place.** The provisional grid replaces
  the grid's contents as a unit and restores on invalidation/staleness.
- **Nothing on this path writes `data/`**, reorders, or re-ranks (§7, unchanged).
- **`note == 'confirmed'` stays server-side only.** The client still never paints a
  receipt (`_bsQualify` refuses it by construction); that is unchanged here.
- **Height contract holds** (§0-4): reserved slots, no shove when the payload lands.
