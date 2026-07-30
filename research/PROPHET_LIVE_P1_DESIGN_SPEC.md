# PROPHET LIVE P1 — us_stocks surface design spec

**Program:** `prophet_live` P1 (masterplan §4.4) · **Author:** designer lane (Opus) · **Date:** 2026-07-29
**Binds:** `docs/DESIGN_DOCTRINE.md` (content law, wins on conflict) + frontend-design skill (visual bar)
**Payload:** `prophet_live.states/v1` — `engine/prophet_live/live_states.py` (branch `claude/prophet-live-p0`)
**Refs:** `mockups/refs/prophet_live/` (committed HTML + light/dark/zh PNG crops)

This document is the **fully specified design** the P1 builder implements. Markup, selectors,
tokens, copy (EN+ZH) and the JS behaviour contract are decided here; the builder assembles them.
Choices are not open for re-litigation by the build lane — a genuine blocker comes back to the
commissioning session.

---

## §0 THESIS — why this surface does not look like a ticker

The thing being surfaced is **a signal that has not happened yet**. Its entire epistemic content is
*"the same test tonight will apply already passes at this price — and only the close makes it real."*
Every default live-data idiom lies about that:

| Default idiom | Why it is banned here |
|---|---|
| Green pulsing "LIVE" dot | Architecturally unreachable on this plane (15-min vendor floor) **and** it encodes certainty. The brief forbids designing one. |
| Red/green price ticker | Makes a pending verdict read as a tape. The strip is not a tape. |
| Big number + label + gradient | The templated answer; says nothing about provisionality. |
| Board-green chips | Green is the nightly confirmer's property. Green before the close overclaims. |

**Three decisions carry the design:**

1. **Blue means provisional; green is reserved for the close.** The lane gets its own hue (`--plv`),
   deliberately unlike `--link` (so a chip never reads clickable), unlike `--up`/`--down` (so it never
   reads directional, in either language), and unlike every `--pv-*` verb hue (so it never reads as a
   nightly verdict). Escalation to the strongest moment (`confirming_into_close`) is carried by
   **weight and fill, not hue** — one hue for the whole live family.
2. **The signature is a settle rail, not a pulse.** One hairline session rail in the strip header,
   filled left-to-right from 09:30 to the 16:00 close, with a "now" tick that advances on a local
   60-second clock. It encodes the only variable that actually converts *forming* into *confirmed*:
   remaining tape. It is also the honest **proof of life** — the strip visibly moves between passes
   without any new data and without claiming freshness it does not have. This is why the component
   needs no status dot anywhere; that absence is deliberate.
3. **The two surfaces have disjoint jobs.** The strip speaks **only** for names that crossed today
   and are not on last night's board (`entered:"cross"`). Names already on the board get a **card
   chip** and never a strip row. A strip that also listed the ~44 holding board names would be a
   state dump, not news, and the board below already says it.

---

## §1 Surface inventory

| # | Surface | File | New selectors | Render path |
|---|---|---|---|---|
| 1 | "Forming today" strip | `templates/dashboard.html.j2` | `#prophet-live`, `.plv-*` | markup SSR (empty shell) + inline `<style>` + inline JS; body filled client-side |
| 2 | Live chip on Prophet cards | `templates/_prophet_card.html.j2` | `.pv-live`, `.pv-live--*` | reserved empty `hidden` span in the overlay; filled by the strip's JS |

**No `templates/theme.css`, `templates/live.js` or `templates/theme.js` edits.** All CSS/JS for this
feature is page-inline in `dashboard.html.j2` (the idiom `.dash-tw-strip` / `.sbx-*` / the TS-U3 JS
block already use) plus the `pv_css()` macro. This is deliberate: those three files are on the
Caddyfile `immutable` list, and touching them drags in the surgical `?v=` re-stamp discipline and the
unsubscribe-parity asset-hash trap for zero design benefit (masterplan §7).

### 1.1 Insertion point

```jinja
  </div>{# /panel — What to act on now #}
    {% set _su = us_standouts if (us_standouts and us_standouts.buy) else None %}
    {{ pv.pv_css() }}
+   {% if mode == 'stocks' %}{{ plv_strip() }}{% endif %}   {# ← NEW, own panel, before #us-standouts #}
    {% if _su or action_board.notable %}
    <div class="panel span12 notable" id="us-standouts">
```

`{% if mode == 'stocks' %}` is the same guard the Turn Watch strip uses (`dashboard.html.j2:14373`).

**It is its own `panel span12`, not a block inside `#us-standouts`.** Doctrine Law 4 allows one as-of
stamp per panel, and the two clocks in play are genuinely different objects: the board panel is
stamped with the nightly close vintage; the strip is stamped with an intraday quote age. Two clocks =
two panels. Merging them would force one stamp to lie about the other.

---

## §2 Strip — markup

SSR emits the shell only. Every text node marked `[js]` is written client-side.

```html
<div class="panel span12 plv" id="prophet-live" hidden>
  <div class="plv-hd">
    <h2 class="plv-title">◐ <span class="l-en">Forming today</span><span class="l-zh">今日正在形成</span></h2>
    {{ help('<Tier-2 EN, §4.6>', '<Tier-2 ZH, §4.6>') }}
    <span class="plv-token" id="plv-token"></span>              <!-- [js] state token -->
    <button class="plv-more" id="plv-more" type="button" aria-expanded="false" hidden></button>
    <span class="plv-asof" id="plv-asof"></span>                <!-- [js] one as-of -->
  </div>
  <div class="plv-sub" id="plv-sub"></div>                      <!-- [js] stance line -->

  <!-- SIGNATURE: settle rail. aria-hidden — the as-of text and the end-cap label carry it in words. -->
  <div class="plv-rail" aria-hidden="true">
    <div class="plv-rail-track"><i class="plv-rail-fill" id="plv-rail-fill"></i><i class="plv-rail-now" id="plv-rail-now"></i></div>
    <div class="plv-rail-lbl"><span class="l-en">settles 4:00 pm ET</span><span class="l-zh">美东 16:00 结算</span></div>
  </div>

  <div class="plv-cols" id="plv-cols">
    <span class="plv-c1"></span>
    <span class="plv-c2"><span class="l-en">Now</span><span class="l-zh">当前</span></span>
    <span class="plv-c3"><span class="l-en">Cross level</span><span class="l-zh">上穿价位</span></span>
    <span class="plv-c4"><span class="l-en">Since</span><span class="l-zh">起始</span></span>
  </div>
  <div class="plv-body" id="plv-body"></div>                    <!-- [js] rows / empty line -->
  <div class="plv-fn" id="plv-fn"></div>                        <!-- [js] one footer sentence -->
</div>
```

Row template written by JS (keyed on `data-plv-tk`, patched in place — never `innerHTML =` on the body):

```html
<a class="plv-row" data-plv-tk="ONTO" href="stock.html#ONTO">
  <span class="plv-chip plv-chip--forming" data-tip-en="…" data-tip-zh="…">◐ <span class="l-en">Forming</span><span class="l-zh">正在形成</span></span>
  <span class="plv-tk">ONTO</span>
  <span class="plv-nm">Onto Innovation</span>
  <span class="plv-now">$224.60</span>
  <span class="plv-lvl">$222.85</span>
  <span class="plv-since">10:55</span>
</a>
```

`.plv-cols` labels the three figure columns **once**, so no row repeats a constant (Doctrine Law 4 —
the defect the old Turn Watch strip shipped). Every figure is then self-labelled (Law 3) with no
per-row prose.

### 2.1 Empty / dark body (same box, same height)

```html
<!-- quiet tape -->
<div class="plv-none"><span class="l-en">Nothing crossing yet — last checked 11:20 am ET.</span><span class="l-zh">尚无新的上穿 — 最近一次检查 美东 11:20。</span></div>
<!-- data dark: reason line + optional last-good-read line, both inside .plv-none -->
<div class="plv-none plv-none--dark"><span class="l-en">…reason, §4.4…</span><span class="l-zh">…</span>
  <span class="plv-last"><span class="l-en">Last clear read 11:20 am ET.</span><span class="l-zh">最近一次有效判读 美东 11:20。</span></span></div>
```

---

## §3 Strip — CSS (page-inline in `dashboard.html.j2`, alongside `.dash-tw-strip`)

```css
/* ── PROPHET LIVE strip (P1) ──────────────────────────────────────────────────
   Provisional hue is the lane's OWN token, chosen against three neighbours:
     · not --link / --info  → a chip must never read as clickable
     · not --up / --down    → must never read directional (and must not flip under
                              html[data-lang="zh"] 红涨绿跌)
     · not any --pv-*       → must never read as a nightly verdict (green = confirmed,
                              and only the nightly build confirms)
   Scoped to the component so no global token is added and theme.css stays untouched. */
#prophet-live { --plv: #62a0e8; display:none; }
html[data-theme="light"] #prophet-live { --plv: #2f6fd0; }
#prophet-live.visible { display:block; }

/* Every header item takes the token pill's line box, so a SHORTER token ("READ PAUSED")
   cannot yield a shorter wrapped line than a longer one. Measured: it did, by 2.5px. */
.plv-hd { display:flex; align-items:center; gap:8px; row-gap:4px; flex-wrap:wrap; }
.plv-hd > * { min-height:17px; display:inline-flex; align-items:center; }
/* gap, not a literal space: `.plv-hd > *` makes this an inline-flex box, and flex layout
   discards the whitespace-only text node between the ◐ glyph and the label. */
.plv-title { margin:0; gap:6px; font-size:12px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:var(--plv); }
.plv-token { font-size:9.5px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--plv);
             border:1px solid color-mix(in srgb,var(--plv) 34%,transparent);
             background:color-mix(in srgb,var(--plv) 9%,transparent); border-radius:999px; padding:1.5px 8px; white-space:nowrap; }
.plv-token.is-dark   { color:var(--muted); border-color:color-mix(in srgb,var(--muted) 30%,transparent); background:color-mix(in srgb,var(--muted) 7%,transparent); }
.plv-token.is-closed { color:var(--pv-hold); border-color:color-mix(in srgb,var(--pv-hold) 34%,transparent); background:transparent; }
.plv-more { font-size:10.5px; color:var(--muted); }
.plv-asof { margin-left:auto; font-size:10.5px; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }
.plv-sub  { font-size:11.5px; line-height:1.45; color:var(--text); opacity:.82; margin:5px 0 0; min-height:17px; }

/* SIGNATURE — settle rail. Fixed height; the only inline style JS writes is the fill width. */
.plv-rail { display:flex; align-items:center; gap:8px; margin:9px 0 7px; height:14px; }
.plv-rail-track { position:relative; flex:1; height:3px; border-radius:2px; background:var(--line); overflow:visible; }
.plv-rail-fill  { position:absolute; inset:0 auto 0 0; width:0; height:3px; border-radius:2px;
                  background:color-mix(in srgb,var(--plv) 38%,transparent); }
.plv-rail-now   { position:absolute; top:-3px; left:0; width:1.5px; height:9px; border-radius:1px; background:var(--plv); }
.plv-rail-lbl   { flex:none; font-size:9.5px; color:var(--muted); white-space:nowrap; }
#prophet-live.is-dark .plv-rail { opacity:.45; }
#prophet-live.is-dark .plv-rail-fill, #prophet-live.is-dark .plv-rail-now { display:none; }
#prophet-live.is-closed .plv-rail-now { display:none; }
#prophet-live.is-closed .plv-rail-fill { width:100% !important; background:color-mix(in srgb,var(--pv-hold) 30%,transparent); }

/* rows: dtp-column discipline — one header, pure figures per row */
.plv-cols, .plv-row { display:grid; grid-template-columns:minmax(96px,auto) 46px 1fr 74px 74px 52px; align-items:baseline; gap:0 10px; }
.plv-cols { font-size:9.5px; font-weight:700; letter-spacing:.07em; text-transform:uppercase; color:var(--muted);
            border-bottom:1px solid var(--line); padding-bottom:4px; }
.plv-c2, .plv-c3, .plv-c4 { text-align:right; }
.plv-c2 { grid-column:4; } .plv-c3 { grid-column:5; } .plv-c4 { grid-column:6; }
/* empty modes keep the hairline rule (height invariance) but drop labels for rows that
   are not there — dead column headings over an empty box read as a broken panel. */
#prophet-live.is-empty .plv-cols > span { visibility:hidden; }
/* THE height contract: 3 slots × .plv-row min-height (24.5px) + 2px pad. Measured, not
   assumed — the row is as tall as the chip box (10px × 1.35 + 4px pad + 2px border), and
   the first draft of this rule guessed 21px and broke invariance by 10.5px. Re-run the
   §7.10 proof if the chip box ever changes. */
.plv-body { min-height:75.5px; display:flex; flex-direction:column; padding-top:2px; }
.plv-row { padding:2.5px 0; min-height:24.5px; font-size:12.5px; text-decoration:none; color:inherit; }
.plv-row:hover .plv-nm, .plv-row:hover .plv-tk { color:var(--link); }
.plv-tk  { font-weight:800; letter-spacing:.01em; white-space:nowrap; }
.plv-nm  { color:var(--muted); font-size:11px; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.plv-now, .plv-lvl, .plv-since { text-align:right; font-variant-numeric:tabular-nums; font-family:var(--font-mono,monospace); white-space:nowrap; }
.plv-now   { font-weight:700; }
.plv-lvl   { color:var(--muted); }
.plv-since { color:var(--muted); font-size:11px; }

.plv-chip { display:inline-flex; align-items:center; gap:4px; justify-self:start; font-size:10px; font-weight:800;
            letter-spacing:.04em; text-transform:uppercase; line-height:1.35; padding:2px 8px; border-radius:999px; white-space:nowrap;
            background:color-mix(in srgb,var(--plv) 10%,transparent); color:var(--plv);
            border:1px solid color-mix(in srgb,var(--plv) 42%,transparent); }
/* the strongest moment escalates by FILL + WEIGHT, never by hue */
.plv-chip--close  { background:var(--plv); color:#fff; border-color:transparent; }
.plv-chip--drop   { background:color-mix(in srgb,var(--pv-hold) 10%,transparent); color:var(--pv-hold);
                    border-color:color-mix(in srgb,var(--pv-hold) 32%,transparent); }
.plv-chip--over   { background:color-mix(in srgb,var(--pv-wait) 11%,transparent); color:var(--pv-wait);
                    border-color:color-mix(in srgb,var(--pv-wait) 40%,transparent); }
.plv-row.is-past .plv-tk, .plv-row.is-past .plv-now { opacity:.72; }   /* fell back / ran past = quieter row */

.plv-none { flex:1; display:flex; flex-direction:column; justify-content:center; gap:3px;
            font-size:12px; color:var(--muted); }   /* fills .plv-body — never its own height */
.plv-last { font-size:10.5px; opacity:.8; }
.plv-fn   { border-top:1px solid var(--line); margin-top:7px; padding-top:7px; font-size:10.5px; line-height:1.5; color:var(--muted); }
.plv-fig  { font-variant-numeric:tabular-nums; font-weight:700; color:var(--text); }   /* figures mono, words never */

.plv-row.is-new { animation:plv-in .2s ease-out; }
@keyframes plv-in { from { opacity:0 } to { opacity:1 } }
@media (prefers-reduced-motion:reduce) { .plv-row.is-new { animation:none } }

@media (max-width:680px) {
  /* Header pinned to a deterministic TWO lines: [title help +N] / [token as-of]. Without
     the reorder the 44px +N button landed on a third line the moment a 4th row appeared —
     a 21px shove of the whole board, every 5 minutes. Measured, then fixed. */
  .plv-more { order:1; margin-left:auto; }
  .plv-token { order:2; }
  .plv-asof { order:3; margin-left:auto; }
  .plv-cols, .plv-row { grid-template-columns:minmax(84px,auto) 44px 1fr 68px 68px 0; }
  .plv-c4, .plv-since { display:none; }          /* SINCE demoted; it survives in the row tip */
}
@media (max-width:560px) {
  .plv-cols, .plv-row { grid-template-columns:minmax(78px,auto) 44px 0 66px 66px 0; }
  .plv-c3, .plv-nm { display:none; }             /* ticker is the identity; company name demoted */
}
```

**Height contract:** `.plv-body` reserves 3 slots (`75.5px`) and `.plv-none` fills it with `flex:1`,
so the panel's outer height is **identical** in live / quiet / dark / closed and at every row count
0–3. Nothing below the strip ever moves when the counts change. Mobile reserves the same 75.5px, so
there is no responsive height arithmetic. Measured on the committed mockup, all four modes
(live / faded+overflow / quiet / dark): **231.75px at 1180px**, **284.34px at 375px**, **234.75px at
1180px in zh**. Three separate rules earn that number and each was added after a measurement caught
it failing: `.plv-cols` labels **hide** rather than collapse in the empty modes; `.plv-hd > *` share
one line box so a short token cannot shrink a wrapped line; and the mobile header re-order keeps the
`+N` button off a third line. Never take the invariance on trust — re-measure (§7.10).

---

## §4 Copy — EN + ZH, every state

House rules applied throughout: figures are `tabular-nums`/mono, **words never mono**; no translated
text in any `title=` (use `data-tip-en`/`data-tip-zh`, which the delegated LENS engine in `theme.js`
picks up on client-rendered nodes); company names ship EN-only in both languages (existing card norm).

### 4.1 Title / columns (static, SSR)

| Slot | EN | ZH |
|---|---|---|
| Title (≤4 words) | `◐ Forming today` | `◐ 今日正在形成` |
| Column 2 | `Now` | `当前` |
| Column 3 | `Cross level` | `上穿价位` |
| Column 4 | `Since` | `起始` |
| Rail end-cap | `settles 4:00 pm ET` | `美东 16:00 结算` |

### 4.2 State token (`#plv-token`) — the self-labelling freshness form

| Mode | EN | ZH |
|---|---|---|
| rth | `INTRADAY · 15-MIN DELAYED` | `盘中 · 15分钟延迟` |
| preopen | `PRE-OPEN · 15-MIN DELAYED` | `盘前 · 15分钟延迟` |
| dark | `READ PAUSED` | `判读暂停` |
| closed | `CLOSED · SETTLES TONIGHT` | `已收盘 · 今晚结算` |

The delay figure is `meta.delay_min` (house `delayMin` convention = the **vendor floor**, not a
measured latency). If `delay_min` is null, print `DELAYED` with no number — never guess 15.

### 4.3 Stance subtitle (`#plv-sub`, ≤14 words) — a function of MODE only

Keyed to mode, never to the row set: a subtitle that rewrites itself every 5 minutes is its own kind
of noise, and holding it stable is also a no-thrash rule.

| Mode | EN | ZH |
|---|---|---|
| live | `Crossing now — nothing is settled until tonight's close. Get ready; don't chase.` | `正在上穿 — 今晚收盘才算数。做好准备，勿追高。` |
| quiet | `Nothing crossing right now. Tonight's board below is the plan.` | `当前没有新的上穿。下方的看板即为今日计划。` |
| dark | `The intraday read is paused. The board below is unaffected.` | `盘中判读暂停。下方看板不受影响。` |
| closed | `These crossed today — tonight's close settles which ones count.` | `这些今日已上穿 — 今晚收盘决定哪些成立。` |

Stance vocabulary check (Doctrine Law 1): live = **Get ready**; quiet/closed = work the board (stand
aside); dark = the board is unaffected (direction, not an apology — an error state tells the reader
what to do instead).

### 4.4 Rows and empty forms

| Payload | Chip EN | Chip ZH | Chip class | Row class |
|---|---|---|---|---|
| `forming`, `entered:"cross"` | `Forming` | `正在形成` | `plv-chip--forming` | — |
| `confirming_into_close:true` | `Holding into close` | `收盘前仍成立` | `plv-chip--close` | — |
| `faded`, `via:"drop"` | `Fell back` | `回落` | `plv-chip--drop` | `is-past` |
| `faded`, `via:"overrun"` | `Ran past` | `越过` | `plv-chip--over` | `is-past` |

**`via` selects the word, and the word "faded" is only ever shown for `via:"drop"`.** An overrun ran
*past* the price range the gate still admits — the opposite trade from falling through it. Calling
that "faded" would lie about direction and pollute the very axis the P0 ledger measures. (The word
*faded* itself is anchored in the Tier-2 tip so the house vocabulary still appears.)

Row hover tips (`data-tip-en/zh`, ≤80 words each — Tier 2):

- **forming** — EN: `The same admission test tonight's build will run already passes at today's price, and has held for two checks in a row. Nothing is confirmed: tonight's close decides, and a board seat is settled only by the nightly build. Price is intraday, 15-minute delayed.`
  ZH: `今晚生成时要跑的同一套准入判定，在今日价格下已经通过，并且连续两次检查都成立。但这不是确认：今晚收盘才决定，看板席位只由夜间生成敲定。价格为盘中数据，延迟 15 分钟。`
- **holding into close** — EN: `Still passing with under half an hour of tape left, so today's close is unlikely to move it — but tonight's build is what settles it, and the seat comes with it. Price is intraday, 15-minute delayed.`
  ZH: `距收盘不足半小时仍然通过，今日收盘价大概率不会推翻它 — 但真正结算的是今晚的生成，席位也随之而定。价格为盘中数据，延迟 15 分钟。`
- **fell back** — EN: `It crossed earlier today and has since traded back below the cross level, so it faded. Nothing to do; if it crosses again it reappears here after two checks.`
  ZH: `今日早前曾上穿，随后回落至上穿价位之下，判读已消退。无需操作；若再次上穿，连续两次检查后会重新出现。`
- **ran past** — EN: `It crossed and then ran above the range where the setup is still admitted — it ran past the entry rather than falling through it. Watch — don't chase.`
  ZH: `上穿后继续冲高，已越过该形态仍被接受的价格区间 — 属于越过入场区，而非跌破。观察为主 — 勿追高。`

Empty / dark body lines:

| Mode / `reason` | EN | ZH |
|---|---|---|
| quiet | `Nothing crossing yet — last checked {hh:mm} am/pm ET.` | `尚无新的上穿 — 最近一次检查 美东 {hh:mm}。` |
| `no_pack` | `Today's watch list hasn't loaded, so nothing is being checked.` | `今日的追踪清单尚未载入，暂无判读。` |
| `stale_pack` | `The watch list is out of date, so the intraday read is paused.` | `追踪清单已过期，盘中判读暂停。` |
| quote-side (`read_paused`, majority-dark, all-`no_quote`/`stale_quote`) | `Prices aren't updating right now, so the intraday read is paused.` | `价格暂未更新，盘中判读暂停。` |
| any dark, optional 2nd line | `Last clear read {hh:mm} am/pm ET.` | `最近一次有效判读 美东 {hh:mm}。` |

The dark forms name the cause in plain words with no internal vocabulary — "arming pack",
"stale_pack", "out_of_band" and every other machine reason stays out of Tier 1. The reason **is**
disclosed; it is disclosed in the reader's language.

### 4.5 Footer (`#plv-fn`) — one sentence, one footnote, once

EN: `Only the <b class="plv-fig">{evaluated_n}</b> names sitting near a decision are checked intraday — every read here settles at tonight's close.`
ZH: `盘中仅检查接近临界的 <b class="plv-fig">{evaluated_n}</b> 只 — 此处所有判读均以今晚收盘为准。`

`{evaluated_n}` = `meta.evaluated_n` (names this pass can actually speak about). This one line owns
the coverage bound: the ~1.5k names the pack never armed are **out of coverage, not dormant**, and the
strip never implies otherwise. If `meta.unprobed_n` is null/absent the sentence still holds. In
`closed` mode the tense stays correct as written.

### 4.6 `?` help on the title (Tier 2 receipt, ≤80 words)

EN: `Forming means the same admission test tonight's build will run already passes at today's price — re-checked every 5 minutes on a 15-minute-delayed quote. A level must hold two checks in a row (about 10 minutes) before it appears here. Tonight's build is the only thing that confirms a signal or hands out a board seat. {evaluated_n} of {universe} scored names were armed tonight; the rest sit too far from a decision.`

ZH: `「正在形成」的含义是：今晚生成时要跑的同一套准入判定，在今日价格下已经通过 — 每 5 分钟用延迟 15 分钟的报价重跑一次。某个价位必须连续两次检查都成立（约 10 分钟）才会出现在这里。只有今晚的生成才能确认信号、才能给出看板席位。今晚共备妥 {evaluated_n} 只（全部评分股票 {universe} 只），其余距离临界太远。`

`{universe}` from the board payload (`us_standouts.universe`, currently 1,578) — SSR-baked, since it
does not change intraday. This is the sanctioned home for the debounce mechanic, the delay mechanic,
the coverage receipt, and the **seat honesty** clause (masterplan §7: a forming name qualifies on its
own signal; seating settles only at the nightly build — copy must never promise a seat).

---

## §5 Card chip — surface 2

### 5.1 The one-hue-law exception (read this before reviewing it as a violation)

`_prophet_card.html.j2` states the one-hue law: every element on a card follows the verb hue `--pvh`,
and the ⚡ trigger chip obeys it. **The live chip is the single deliberate exception.** The card's hue
encodes *the nightly verdict*; the live chip belongs to *today's tape*. Painting an `at_risk` chip
with `--pvh` would render it **green on a Buy card** — i.e. it would say "this live state is part of
the confirmed verdict", which is precisely the false claim this whole program exists to avoid. So:

- the ⚡ nightly trigger chip keeps `--pvh` — unchanged, no edits;
- the ◐ live chip carries `--plv` (provisional) or `--pv-wait` (ran-past / below-range caution);
- the two are distinguishable by glyph (⚡ nightly vs ◐ live) as well as hue.

Amend the macro's header comment with this exception and its reason, so the next reader does not
"repair" it.

### 5.2 Markup — a reserved, always-present, empty slot

The card is server-rendered nightly and the live state arrives every 5 minutes, so this chip **cannot
be SSR'd**. Add one always-present empty span to the overlay, ordered after the trigger chip and
before ⚠N, and let the JS fill it. Absent state ⇒ `hidden` ⇒ zero width, zero layout change, and the
SSR HTML is byte-identical in meaning to today's.

```jinja
      {%- if cx.get('trigger') %}…existing ⚡ chip, untouched…{%- endif %}
+     <span class="pv-live" hidden></span>          {# [js] prophet_live chip — see §5 of the P1 spec #}
      {%- if cx.get('flags') %}…existing ⚠N…{%- endif %}
```

Filled shape (written by JS):

```html
<span class="pv-live pv-live--over" data-tip-en="…" data-tip-zh="…">◐ <span class="l-en">Ran past</span><span class="l-zh">越过区间</span></span>
```

JS targets cards by the attribute the macro **already** emits: `.pvcard[data-ticker="TPR"]`.

### 5.3 CSS — appended inside `pv_css()`

```css
.pv-live{display:inline-flex;align-items:center;gap:3px;font-size:10px;font-weight:800;letter-spacing:.04em;
  text-transform:uppercase;line-height:1.35;padding:2px 8px;border-radius:999px;white-space:nowrap;
  /* NOT --pvh: this chip is today's tape, not the nightly verdict (see spec §5.1) */
  --plvc:#62a0e8;background:color-mix(in srgb,var(--plvc) 12%,var(--panel));color:var(--plvc);
  border:1px solid color-mix(in srgb,var(--plvc) 44%,transparent)}
/* MUST be present: a class `display` out-specifies the UA [hidden] rule, so without this
   every card on the board grows an empty mystery pill. Verified on the mockup. */
.pv-live[hidden]{display:none}
html[data-theme="light"] .pv-live{--plvc:#2f6fd0}
/* NOT solid-filled, unlike the strip's .plv-chip--close: a solid pill out-weighs an outlined
   verb chip, and the card's verb must stay its ruling stance (macro law). The fill escalation
   lives on the strip, where a cross is news and has no verb to outrank. */
.pv-live--close{background:color-mix(in srgb,var(--plvc) 18%,var(--panel));
  border-color:color-mix(in srgb,var(--plvc) 70%,transparent)}
.pv-live--drop,.pv-live--over{--plvc:var(--pv-wait)}
@media (max-width:680px){
  /* same collapse-to-glyph rule the trigger chip uses at narrow widths */
  .pv-live .l-en,.pv-live .l-zh{display:none!important}
  .pv-live{padding:2px 5px;gap:0}
}
```

**One existing rule must be promoted** (same `pv_css()` macro): the overlay has to wrap at every
width, not only ≤680px.

```css
-  /* today: only inside @media (max-width:680px) */
-  .pv-ov.pv-ovl{flex-wrap:wrap;row-gap:3px}
+  .pv-ov.pv-ovl{flex-wrap:wrap;row-gap:3px}     /* at ALL widths */
```

Verb + `⚡` + `◐` + `⚠N` exceeds `.pv-ov{max-width:70%}` on a 246px card, and today the excess
clips **behind** the price pill — a pre-existing latent bug that the live chip would have made
routine. Reproduced and fixed on the mockup; the wrapped second chip row sits over the
sparkline, which costs nothing (the overlay is absolutely positioned, so card height and the
grid are untouched).

### 5.4 Copy — card chip variants

| Payload | Chip EN | Chip ZH | class |
|---|---|---|---|
| `at_risk`, `via:"drop"` | `◐ Below range` | `◐ 低于区间` | `pv-live--drop` |
| `at_risk`, `via:"overrun"` | `◐ Ran past` | `◐ 越过区间` | `pv-live--over` |
| `confirming_into_close`, `entered:"board"` | `◐ Holding into close` | `◐ 收盘前仍成立` | `pv-live--close` |

**Why "Below range" and not "At risk".** `at_risk` is an internal state name, and every verdict-flavoured
phrasing of it ("at risk", "may drop off", "losing its seat") invites the reader to hear a sell call
on an un-graded, provisional read — which the operator's watch-don't-chase law forbids. "Below range"
is an unimpeachable statement about the tape, it composes with the buy-zone footer already on the
card, and it puts the caution where cautions belong: the hue and the tip.

Tips (Tier 2, ≤80 words):

- **below range** — EN: `Trading below the price range where tonight's close would still admit this setup. Nothing on the board has changed yet — the verdict re-settles at tonight's close and this card updates with it. Watch — don't chase. This is not a sell call. Intraday price, 15-minute delayed.`
  ZH: `当前价格低于「今晚收盘仍会接受该形态」的价格区间。看板尚未发生任何变化 — 判定将在今晚收盘重新结算，本卡片届时随之更新。观察为主 — 勿追高。这不是卖出建议。盘中价格，延迟 15 分钟。`
- **ran past** — EN: `Trading above the range where this setup is still admitted — it ran past the entry rather than falling through it. Tonight's close re-settles the verdict. Don't chase; nothing here says sell. Intraday price, 15-minute delayed.`
  ZH: `当前价格高于该形态仍被接受的区间 — 属于越过入场区，而非跌破。今晚收盘会重新结算判定。勿追高；此处并未建议卖出。盘中价格，延迟 15 分钟。`
- **holding into close** — EN: `Still passing tonight's admission test with under half an hour of tape left, so today's close is unlikely to change it — but tonight's build is what settles it. Intraday price, 15-minute delayed.`
  ZH: `距收盘不足半小时仍通过今晚的准入判定，今日收盘价大概率不会改变它 — 但真正结算的是今晚的生成。盘中价格，延迟 15 分钟。`

---

## §6 JS behaviour contract

Lives in the existing TS-U3 inline IIFE region of `dashboard.html.j2` (reuse its `fetchJson`, `L(en,zh)`,
`esc`, `isZh` helpers). `mode == 'stocks'` only.

### 6.1 Source and cadence

- **Fetch** `live/prophet_live.json` — same relative-path family as `live/basket_pulse.json`. Delivery
  (R2 → `live-data` orphan branch → the published `live/` prefix) is P0/plumbing, not design; if the
  path differs, only this constant changes.
- **First fetch is unconditional.** Never gate the initial paint on `document.hidden` — the preview
  pane renders with `visibility:hidden`, so a visibility-gated first fetch produces a permanently
  empty strip in every verification screenshot (house trap: `preview-pane-is-visibility-hidden`).
- **Repeat** every **120 s** (producer writes every ~5 min; 120 s bounds staleness at ~2 min for ~2.5
  fetches per artifact). Skip the network call while `document.hidden`; re-fetch immediately on
  `visibilitychange → visible`, floored at 30 s since the last fetch.
- **Rail tick** advances on its own 60 s local clock with **no fetch** — the strip is visibly alive
  between passes without claiming freshness it does not have.
- Absent file / non-200 / bad JSON ⇒ strip stays `hidden` on first load (graceful-absent, FT-R8), and
  keeps the last good render on a later failure until the age gate below trips.

### 6.2 Mode resolution (in order — first match wins)

1. ET clock outside `[09:20, 16:20]` on a weekday, or a weekend/holiday ⇒ **hide the strip entirely**
   (`display:none`). "Forming today" has nothing to say overnight.
2. `meta.session_et` ≠ today's ET date ⇒ **dark** (`stale_pack` copy). A frozen file must never present
   as today.
3. ET clock past 16:20 and `meta.session_et` == today ⇒ **closed**: rows frozen with their last labels,
   `SINCE` keeps the cross time, rail 100 % and grey, no age-based dark. *Without this rule the age
   gate below fires every single evening and the strip lies "prices aren't updating" after every close.*
4. `status:"dark"` ⇒ **dark**, reason mapped per §4.4 (`no_pack` / `stale_pack` / else quote-side).
5. `Date.now() - pass_ts > 15 min` (3 missed passes) ⇒ **dark** (quote-side copy).
6. `sum(meta.dark_counts) / meta.evaluated_n ≥ 0.5` ⇒ **dark** (quote-side copy). Speaking a confident
   "quiet tape" while more than half the armed names are unreadable is degraded-ships-confident.
7. Otherwise ⇒ **live** if any row qualifies, else **quiet**. `meta.session_phase == "preopen"` selects
   the pre-open token; the mode is otherwise unchanged.

### 6.3 Row selection and ordering

**Include** (this is the editorial fence — it is not a display of `states`):

- `state:"forming"` with `entered == "cross"`;
- any state carrying `confirming_into_close:true` with `entered == "cross"`;
- `state:"faded"` with `entered == "cross"` (both `via` kinds).

**Exclude:** everything `entered == "board"` (the board below already says it — those get card chips),
every `dormant` / `near` / `dark` name (a dark name has nothing to say; it is counted in the footer's
coverage sentence, not listed).

**Order** — deterministic, stable, recomputed identically on every pass:

1. `confirming_into_close` first, then `forming`, then `faded`;
2. within a group, `since_ts` ascending (the longest-held first — it is the most settled);
3. ties broken by ticker, so ordering never depends on dict iteration order.

**Cap** — 3 slots, and **a `faded` row is never the silent cut**:

- if any `faded` row qualifies, the **last slot is reserved** for the most recent one and active rows
  fill the first two;
- otherwise active rows fill all three.

A reader who saw a name forming twenty minutes ago must not find it silently deleted; "one of these
stopped holding" outranks the third concurrent cross. Overflow renders `+{n} more` in the header
`#plv-more` **button** (`aria-expanded`, house `.lst-more`/`#dtp-more` idiom): collapsed height is
constant, and clicking it drops the cap and grows the body — a user-initiated reflow, which is the
only kind allowed. `+N` counts every row that passed the include filter and is not shown.

### 6.4 No-thrash rules (hard)

1. The panel's outer height is **constant** across every mode and row count (§3 height contract).
   A reviewer measures this: `getBoundingClientRect().height` identical for live/quiet/dark/closed.
2. **Keyed reconciliation, never `innerHTML =` on `#plv-body`.** Patch existing rows in place by
   `data-plv-tk`; append/remove only the delta. Wholesale replacement flashes the rows and kills an
   open hover tip mid-read.
3. The only inline style JS writes anywhere is `#plv-rail-fill.style.width`.
4. No CSS transition on height, position, or grid columns. The single motion is a 200 ms opacity
   fade-in on a genuinely new row, disabled under `prefers-reduced-motion`.
5. `#plv-sub` text changes only on a **mode** change, never on a row change.

### 6.5 Presentation-tier fence (G0.4 at the DOM level)

The JS may write to exactly two places: `#prophet-live` (its own panel) and `.pvcard > .pv-chart >
.pv-ov.pv-ovl > .pv-live`. It must **never** touch card ordering, card membership, the `pv-*` hue
class, `.pv-chip` (verb), `.pv-edn` (Edge), `.pv-stp`/`.pv-stl` (stage), `.pv-zn` (zone), `.pv-trg`
(nightly ⚡), the table view, or any lane/count in the board. Recommended test: apply a fixture
payload to a rendered board and assert every mutated node is inside those two subtrees.

### 6.6 Payload dependency — one field to add in P0 (`since_ts`)

The `SINCE` column and the "held for" story need the timestamp at which the current public state was
established. The `v1` state carries `passes`, not a time, and `passes × 5 min` is **not** a lawful
substitute: GitHub cron lands minutes late, so a derived duration would understate elapsed time and
print a number the lane cannot stand behind (and for `entered:"board"` names `passes` counts passes
since the day's first evaluation, not since a cross).

**SHIPPED (PR #4076) — this is no longer an ask; consume it, do not re-derive it.** Each per-name
state carries `since_ts` (ISO-Z): the `pass_ts` of the pass that established the current public state,
carried forward byte-identical while that state persists (banking a debounce pass, gaining an
`internal` marker, or raising `confirming_into_close` do NOT reset it) and re-stamped on a
public-state change, `near`->`forming` included. A DARK row publishes no `since_ts` and instead
chains `prior_public`/`prior_since_ts`, so a name whose quote goes missing for a pass or two and
returns to the SAME public state keeps the time it actually entered that state.

**Degradation, if it is not there:** the `SINCE` cell renders `—`, the column header stays, the tips
drop their timing clause, and nothing else changes. The strip ships either way; it just says less.

---

## §7 Acceptance crops for the build PR (G0.7)

Production-shaped render, not fixtures-in-isolation: the us_stocks board page with a fixture payload
applied through the real JS path.

1. `strip_live_dark_en` — 2 forming + 1 holding-into-close, dark theme, EN.
2. `strip_live_light_en` — same payload, light theme.
3. `strip_live_dark_zh` — same payload, `data-lang="zh"` (verify: no state hue flipped, ZH chips fit).
4. `strip_quiet_dark_en` + `strip_quiet_light_en` — quiet tape.
5. `strip_dark_dark_en` — data-dark (`stale_pack`), rail greyed, reason line in plain words.
6. `card_at_risk_dark_en` + `card_at_risk_light_en` — a **Buy** card carrying `◐ Below range`
   (proves the hue exception: amber chip on a green card). Crop the **board panel region**, not
   the card alone — a sub-680px crop re-triggers the component's own mobile media queries and
   collapses the chip to a bare glyph.
7. `card_confirming_dark_en` + `..._zh` — a card carrying `◐ Holding into close`.
7b. A card with **no** live state, in the same crop — proving the reserved `.pv-live` slot adds
   no width and no mystery pill (`.pv-live[hidden]` must beat the class `display`).
8. `strip_closed_dark_en` — post-16:20 closed mode (the rule in §6.2.3; the one that otherwise lies
   every evening).
9. `strip_mobile_dark_en` — 375 px wide, showing the `SINCE`/name demotions.
10. **Height-invariance proof** — `getBoundingClientRect().height` of `#prophet-live` printed for
    live / quiet / dark / closed, all equal.
11. **Fence proof** — the §6.5 DOM-diff assertion output.

---

## §8 Doctrine self-check (Doctrine §5 builder checklist)

| Check | Verdict |
|---|---|
| 5-second test | Title says the state, subtitle says the stance, the rail says how long until it is real. |
| Stance on every panel (Law 1) | Yes, per mode — including "the board below is unaffected" on the error state. |
| No banned Tier-1 vocabulary (Law 2) | No `at_risk`/`dark`/`stale_pack`/`out_of_band`/`armed pack`/`debounce`/`pass`; no bare stats; tickers are identity, not slugs. |
| Numbers carry meaning (Law 3) | Every figure sits under a labelled column; the cushion `%` was **deleted** rather than shipped unlabelled. |
| Word budgets, one as-of, one footnote (Law 4) | Title 2 words, subtitles ≤12, footer 1 sentence, one as-of, one footnote, zero per-row constants. |
| Honesty survives translation (Law 5) | Coverage bound in plain words on Tier 1, receipt on Tier 2; nulls surface as named dark forms; no "validated", no falsifier vocabulary, no "fired/confirmed/triggered". |
| Bilingual parity | Every string has a real ZH twin; no EN state names dropped into ZH; no translated text in `title=`. |
| zh 红涨绿跌 | Complied **by construction**: the component uses no directional encoding at all. State hues come from the direction-stable `--plv`/`--pv-*` family; fade direction is carried by words + story hue (grey "fell back" vs amber "ran past"), never by up/down colour. Do not "fix" this by adding `--up`/`--down`. |

### 8.1 One adjacent-copy tension, flagged and deliberately not fixed here

The existing nightly trigger chip reads **`⚡ Triggered` / `⚡ 已触发`** (`_prophet_card.html.j2`), and
`triggered` as a past fact is exactly the word G0.6 bans. On its own terms the chip is defensible —
it describes a signal the nightly build *did* confirm, which is a settled fact, not a provisional
claim. But after P1 it sits **one chip away** from `◐ Below range` on the same card, and a reader
scanning two adjacent chips will not naturally infer that one is a settled verdict and the other is
an unsettled read.

Not fixed here, on purpose: it is graded-board copy, outside this commission, and re-wording a
ratified chip mid-flight would collide with the Top-setups presentation merge. Mitigations already in
this design: different glyph (⚡ nightly vs ◐ live), different hue family, and the live chip's tip
always naming tonight's close. **Recommendation for the orchestrator:** consider a small follow-up
that re-words the nightly chip to a settled-tense phrase (e.g. `⚡ Entry signal` / `⚡ 入场信号`),
adjudicated with the Top-setups owner rather than folded into P1.

---

## §9 What this spec deliberately does NOT design (scope fences for the builder)

1. **The Terminal rail** (`/api/hub/prophet_live`, ProphetView cadence chip) — a separate later
   commission; nothing here is a contract for it.
2. **Any alert, email, push, or toast** (P2). No notification affordance, no bell, no "notify me".
3. **The table view of the board** — `USStockTable` gets no live chip in P1. The strip carries the news.
4. **Sector / lane / basket roll-ups of live state** — no "3 forming in Industrials" aggregation.
5. **A per-row sparkline, intraday chart, or price-vs-trigger magnitude bar.** No intraday chart plane
   exists (post charts are daily-bars-only), and a fake magnitude bar is a vetoed idiom.
6. **Volume context** ("cumulative vs ADV") — masterplan §4.2 marks it display-only and it is not
   needed for the glance tier; it would be a fourth figure per row.
7. **A cushion percentage** (price vs cross level as a `%`) — deleted deliberately: it cannot be
   labelled inside the row budget without a per-row repeated constant, and unlabelled it reads as a
   session change.
8. **`dormant` / `near` / per-name `dark` rows**, and any "N names watched, M dormant" state census.
   The footer's one sentence is the whole coverage disclosure.
9. **Board-entered `forming` rows in the strip** — deliberately excluded (§6.3); board names live on
   their cards.
10. **Any change to graded board rows, membership, ordering, lanes, counts, verb, Edge, stage, or
    zone** — DNR §1 standing kill, fenced in §6.5.
11. **A live/green pulse dot, anywhere** — architecturally unreachable and epistemically false; the
    rail is the sanctioned proof of life.
12. **`theme.css` / `live.js` / `theme.js` edits**, and therefore any `?v=` re-stamp work.
13. **New global CSS tokens.** `--plv` is component-scoped on purpose.
14. **prophet.html, the landing showcase, and the Top-setups presentation** — untouched (masterplan
    §4.4: the delayed-winners contract stays).
