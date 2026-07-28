# Round-2 build specs — locked copy + composition per concept

Governed by `research/AD_MASTER_PAPER.md` (§0 gates). Copy below is **locked** — builders
may not reword headlines, sublines, offer cells, or micro lines. Composition recipes give
placement intent; pixel positions are tuned by rendering (`python3 render.py --only <slug>`)
and **looking at the PNG**, minimum two rounds.

**Reference implementation (copy its patterns exactly):**
`ads/desk--1080x1350.html` · `ads/desk--1080x1080.html` · `ads/desk--1200x628.html`

## Build traps (each of these cost the exemplar an iteration — do not re-learn them)

1. **Vertical budget.** `.stage` is `flex:none`; if brand+headline+sub+stage+chips+offer+micro
   exceeds the canvas, the bottom clips. Tune `--stageh` (inline on `.stage`) until the render
   fits with air. 4:5 default 470px; square ~356px works with the standard skeleton.
2. **Headline width.** ~0.55em avg glyph at weight 800: chars × 0.55 × px ≤ 952 (1080 canvas,
   64px pads) / ≤ ~620 for the landscape left column. Break lines with explicit `<br>` — never
   let auto-wrap choose. Squares use `--hl:86px`; 4:5 92px; landscape ~58px inline.
3. **Chips wrap.** ONE full row, or TWO balanced rows (3+3, or founding's 2×2) — never a
   widow chip alone on row 2. 4:5 fits 6 (as 3+3) or 3–4 on one row; square 3; landscape 3.
   If it breaks unevenly, cut chips (prefer features already visible in the stage).
4. **Occlusion law.** Cards cut at ATOMIC boundaries. Amputating a row label mid-word reads
   broken; hiding a right-hand number column or bleeding off-canvas reads deliberate. The
   front card covers side cards' right columns, never their identity column (left).
5. **Transforms.** Combine as `transform:rotate(Xdeg) scale(Y);transform-origin:top left`.
6. **`demo` tag** (`.demo-tag` or kick `.asof`) on every widget with a specific ticker+number.
7. **Tokens only.** No new hex values, no new fonts, no shadows outside `--sh-*`.
8. **Offer bar markup is copied verbatim** from the exemplar; only the `.d` lines and CTA text
   vary where a spec says so. Micro line verbatim per spec.
9. **Verify like the renderer**: run render.py (exit 0 = sizes exact + Inter loaded), then view
   your PNG at full size AND squinted/thumbnail before calling it done.
10. **Dark ads** (`.ad--dark`): white cards pop on the plate — keep them; the candle field
    (`.candle-field` + `assets/candle_field.svg` as `<img>`) sits behind content, never
    behind the offer bar text zone (the mask handles fade; don't fight it).

Asset files (inline via `<img src="../assets/….svg" style="width:100%;display:block">`):
`candle_field.svg` (dark backdrop), `entry_chart.svg` (900×520 zone/stop chart),
`term_chart.svg` (620×300 terminal candles).

---

## signals — paper · 1080x1350 · 1080x1080 · 1200x628

- pill: `● NIGHTLY SIGNAL ENGINE`
- H: `Institutional-grade<br>stock signals.`
- sub: `Every setup staged — <b>Base, Turn, Ready, Trend</b> — scored, with the entry zone drawn.`
- chips (4:5): `Entry zones(g) · EDGE scores(blue) · Nightly rebuild(gold) · Free terminal(t)`;
  square: first 3; landscape: Entry zones · EDGE scores · Free terminal.
- stage: THREE prophet cards. Front-center: VCTR (copy from exemplar, scale 1.0–1.05).
  Behind-left: ENOV — pill NEAR + `⚠ 1` gold warn pill beside it, chg `+5.0%`, tk ENOV,
  nm Enovis, sector Health Care, EDGE 75, Ready on, ZONE `$23.29 – $25.22`, dt Jul 8,
  spark path B below. Behind-right: IVZ — NEAR, chg `+3.3%`, tk IVZ, nm Invesco, sector
  Financials, EDGE 90, Ready on, ZONE `$27.66 – $28.61`, dt Jul 9, spark path C.
  Warn pill markup: `<span class="pill pill--warn">⚠ 1</span>` (font-size 24, padding 8 16).
- spark path B: `M4 50 L20 42 L34 48 L50 36 L64 44 L80 30 L94 38 L110 24 L126 32 L142 20 L158 27 L174 14 L196 18`
- spark path C: `M4 40 L20 44 L34 34 L50 40 L64 28 L80 35 L94 22 L110 30 L126 16 L142 24 L158 12 L174 19 L196 8`
  (area fills: same pattern as exemplar `gv` gradient, unique ids per card).
- offer/micro: standard (copy exemplar).

## price — paper+violet · 1080x1350 · 1080x1080

- pill: `● THE VALUE CASE`
- H: `A $24,000 desk.<br><span class="grad">Yours: $2.50 a day.</span>`
- sub: `Signals, 13F flow, options tape, terminal and AI analyst — the full desk, $75 a month.`
- stage: LEFT behind (tilt-l): dark compare card (`.card` with inline
  `background:var(--plate);color:#fff;border-color:#26324e`, width 430): kick (inline
  `color:#8fa0bd`) `A TYPICAL INSTITUTIONAL DESK`; big figure `$24,000/yr` (64px, 800);
  three faint rows (26px, #93a1ba): `Terminal & data` / `Research desk` / `Flow & filings`;
  footnote row (22px, #6b7893): `typical institutional list price`.
  FRONT right-of-center: `w-founding` card copied from the founding spec below (meter included).
- chips: `Stock signals(g) · 13F & insiders(v) · Options flow(t) · AI analyst(r)` (square: 3).
- offer: standard. micro: `$900 billed annually · 2,000 founding memberships · mastermind-x.com`

## risk — paper · 1080x1350 · 1080x1080

- pill: `● MARKET RISK SCORE`
- H: `Know when the market<br>has your back.`
- sub: `One 0–100 score for the whole tape — regime, breadth, cross-asset — read fresh every night.`
- stage: FRONT: `w-read` GREEN state — regime pill `Goldilocks · shifting`, arc stroke
  `#1f8b41` dasharray `119.6 200`, needle `rotate(32.4deg)`, needle tip circle fill
  `#1f8b41`, `num green` `68` / `Risk-on`, stance `<b>GREEN — trend-following supported.</b>
  Adding on strength is supported.`
  BEHIND-right: compact `w-read` RED contrast card (width 400, scale .82): kick
  `SAME DIAL · ROUGH TAPE`, arc `#c12f2f` dasharray `42.2 200`, needle `rotate(-46.8deg)`,
  `num` with inline `color:var(--q-red)` `24` / `Risk-off`, stance `<b>RED — defence first.</b>
  Smaller size, wider stops.` (This shows the dial MOVES — the product's range.)
  BEHIND-left: `w-heat` sliver (copy exemplar heat card).
- chips: `Stock signals(g) · Theme rotation(blue) · Options flow(t) · AI analyst(r)` (square 3).
- offer/micro: standard.

## rotation — paper · 1080x1350 · 1080x1080

- pill: `● THEME ROTATION`
- H (3-line staircase): `See the rotation<br>before your<br>watchlist does.`
- sub: `34 themes across four plain lanes — watch money change lanes as leadership turns.`
- stage: FRONT: wide lanes board (`w-lanes` variant, width 640, lanes in 2×2 grid via inline
  `display:grid;grid-template-columns:1fr 1fr;gap:4px 22px` on a wrapper): BUY NOW: Big
  Pharma 69 / US Energy 71 · ALMOST READY: Industrials 58 / Payments 64 · TAKE PROFITS:
  Defensives 57 · STAND ASIDE: Cybersecurity 72. Kick `WHAT TO ACT ON NOW · demo`.
  THE SIGNATURE: a duplicate `Payments 64` row-chip floating ABOVE the board (z3, shadow
  `--sh-lift`, slight rotate −2°), positioned between the ALMOST READY column and BUY NOW
  column, with a blue arrow (SVG path with arrowhead, stroke `var(--blue)` 5px) from its
  origin slot toward BUY NOW, and two ghost copies (opacity .25/.12) trailing behind it.
  BEHIND-left: prophet sliver (exemplar VCTR, mostly occluded is fine).
- chips: `Stock signals(g) · 13F & insiders(v) · AI analyst(r) · Free terminal(t)` (square 3).
- offer/micro: standard.

## knife — paper · 1080x1350 · 1080x1080

- pill: `● STAGED ENTRIES`
- H: `Don't be the one<br>catching the knife.`
- sub: `The engines wait for the turn — <b>Base, Turn, Ready</b> — so you buy strength, not the fall.`
- stage: TWO cards, same name five weeks apart. LEFT behind (tilt-l, saturate .95):
  prophet variant — top pills: `<span class="pill" style="background:var(--red-wash);
  color:var(--q-red);border:1.5px solid #ecc9c6">FALLING</span>` + demo + chg pill red
  (`background:var(--q-red)`) `−6.2%`; RED spark path D (falling):
  `M4 10 L20 16 L34 12 L50 24 L64 20 L80 32 L94 28 L110 40 L126 36 L142 46 L158 42 L174 50 L196 47`
  with red area fill (`#c12f2f` at .12); tk REZI, nm Resideo, sector Industrials, NO edge;
  stages with **Base** on (`.stg.on` recolored inline `color:var(--q-gold)`, dot
  `background:var(--q-gold);border-color:var(--q-gold)`); zone row replaced by:
  `<div class="zone" style="color:var(--q-gold)">WAIT <b style="color:var(--muted)">no entry
  signal</b><span class="dt">Jun 3</span></div>`. (Jun 3 → Jul 8 = 35 days, so the
  "five weeks apart" caption is exact — R2 review #2.) Headline apostrophe is curly (’).
  RIGHT front (larger, z2): REZI again — NEAR pill, chg `+1.8%`, green spark path B (from
  signals), EDGE 76, **Ready** on, ZONE `$29.83 – $31.04`, dt Jul 8.
  Between/below the two cards: a small caption strip (28px, muted, 600):
  `same stock · five weeks apart · demo`.
- chips: `Stock signals(g) · Risk score(gold) · AI analyst(r)` (square: same 3).
- offer/micro: standard.

## entry — DARK · 1080x1350 · 1080x1080

- `.ad--dark`, candle field behind (`<div class="candle-field"><img src="../assets/candle_field.svg" …></div>` first child).
- pill: `● ENTRY ZONES & STOPS`
- H: `Time the entry.<br>Keep the stop.`
- sub: `Entry zones and invalidation levels, drawn on the chart before you click buy.`
- stage: ONE hero card, dark chart panel (width ~940, centered, inline
  `background:#0d1526;border:1px solid #26324e;border-radius:20px;padding:26px 28px;color:#dfe8f8`):
  header row: `NVDA · 1D` (28px, 800) + `<span class="demo-tag" style="color:#6b7893">demo</span>`
  + right `207.29` in a green tag (`background:#123324;color:#37d67a;border-radius:8px;
  padding:6px 14px;font-weight:800`). Chart: `<img src="../assets/entry_chart.svg">`.
  Overlaid labels (absolute over the img): `ENTRY 199–203` chip (green tag idiom, left ~24,
  at the band's height ~62% down) and `STOP 191` chip (red: `background:#331616;color:#ff7a76`)
  near the dashed line ~86% down. Under-chart row (26px, #9db0d0):
  `Zone drawn nightly · invalidation = the 191 swing low`.
- chips (dark): `Stock signals(g) · Options flow(t) · AI analyst(r) · Free terminal(blue)` (square 3).
- offer: standard. micro: `Research tools — not investment advice · 2,000 founding memberships · mastermind-x.com`

## ai-no — paper · 1080x1350 · 1080x1080 · 1200x628

- pill: `● MASTERMIND AI`
- H: `Finally — an AI<br>that says “not yet.”`
- sub: `It reads every desk before it answers — signals, flow, regime — and tells you when <b>not</b> to chase.`
- stage: FRONT: `w-chat` (width 620 on 4:5): hd `● MASTERMIND AI` + demo tag right;
  user bubble `Is NVDA a buy right now?`; status `● reading the boards — regime · Prophet ·
  options flow`; answer bold `Not yet — watch, don't chase.`; answer soft `Uptrend intact,
  but the entry gate has been shut since Jul 14.`; answer soft `If it reopens: entry
  199–203, stop at the 191 swing low.`
  BEHIND-left: prophet sliver. BEHIND-right: read sliver (both mostly occluded/bleeding).
- chips: `Reads the chart(blue) · Knows every desk(v) · Watches risk(gold) · Drives the Terminal(t)`
  (square: first 3; landscape: first 3).
- offer/micro: standard.

## filings — paper · 1080x1350 · 1080x1080

- pill: `● SMART MONEY`
- H: `Follow the filings,<br>not the feed.`
- sub: `356 tracked funds, insider and Congress trades — mapped onto your names as they land.`
- stage: FRONT-left: `w-13f`, kick `13F INSTITUTIONAL FLOWS <span class="asof">latest
  quarter · demo</span>`, rows: Appaloosa / bar g 62% / `NVDA +2.1M sh` g · Bridgewater /
  bar r 45% / `AAPL −1.4M sh` r · Coatue / bar g 55% / `CRDO new stake` g · Millennium /
  bar g 82% / `XLE +3.8M sh` g · Tiger Global / bar r 38% / `META −600K sh` r.
  (bar width via inline `style="width:62%"` on `i`.)
  BEHIND-right: `w-insider` (exemplar rows) bleeding off right edge.
- chips: `13F flows(v) · Insider & Congress(g) · Stock signals(blue) · AI analyst(r)` (square 3).
- offer/micro: standard.

## flow — DARK · 1080x1350 · 1080x1080

- `.ad--dark` + candle field.
- pill: `● LIVE OPTIONS FLOW`
- H: `See the size<br>hit the tape.`
- sub: `Intraday options flow, decoded — sweeps, blocks, and which side the money leans.`
- stage: FRONT: `w-flow` (width 640), kick `OPTIONS TAPE · INTRADAY <span class="asof">demo</span>`,
  rows: `[C SWEEP] NVDA · 210C 08/15 · $4.8M ask` prem g · `[P BLOCK] SPY · 630P 09/19 ·
  $2.2M bid` prem r · `[C SWEEP] AVGO · 300C 08/08 · $1.9M ask` prem g · `[P SWEEP] TSLA ·
  290P 08/01 · $1.1M ask` prem r. (side chip = `.side.c`/`.side.p`; ct = middle text.)
  BEHIND-right: white `w-read` card (small, scale .8) as contrast pop — gauge 57 Mixed
  (copy exemplar) with kick `TODAY'S READ · US`.
- chips (dark): `Sweeps & blocks(t) · Side & size(g) · Stock signals(blue) · AI analyst(r)` (square 3).
- offer/micro: standard.

## terminal — DARK · 1080x1350 · 1080x1080 · 1200x628

- `.ad--dark` + candle field.
- pill: `● THE TERMINAL`
- H: `A real terminal,<br>in your browser. Free.` — set `font-size:84px` inline on the headline for 4:5/square (22-char line 2 needs it).
- sub: `Institutional-grade charting with an AI analyst on call — nothing to install.`
- stage: ONE hero: `w-term` frame (width 960 on 4:5, centered): mac dots bar + url pill
  `app.mastermind-x.com/terminal`; inside body a 2-col flex: LEFT (flex 1): stat strip
  (28px): `NVDA <b style="color:#37d67a">211.10 +1.84%</b> · VOL 103.5M ·
  <span style="color:#37d67a">● LIVE</span>` then `<img src="../assets/term_chart.svg">`;
  RIGHT (width 220, border-left #22304d, padding 16, font 24): watchlist rows tk+px+chg:
  `BTC-USD 63,462 <r>−0.38%</r>` / `NVDA 211.10 <g>+1.84%</g>` / `AAPL 325.48 <r>−0.70%</r>` /
  `MSFT 387.50 <r>−2.58%</r>` (g=#37d67a, r=#ff7a76, chg 22px).
  Under the frame, small line (26px, #9db0d0): `Golden Oracle: “Uptrend — no entry signal.” · demo`
- chips (dark): `Live charting(blue) · AI analyst(r) · Signals overlay(g)` (3 on every size —
  a 4th wraps; "Watchlists" cut 2026-07-28, the frame's watchlist column already shows it).
- offer: cell1 t `FREE FOREVER` d `NOTHING TO INSTALL` (the word TERMINAL lives in the pill +
  headline; the long cell overflowed the CTA off-canvas); cell2 t `<was>$149</was>$75/mo`
  d `PRO 50% OFF · 7-DAY TRIAL` (AG-6: the trial appears on every ad — R2 review #4);
  CTA `Open the Terminal`; `style="--offer:30px"` on `.offer` (4:5/square).
  micro: standard.

## founding — paper+violet · 1080x1350 · 1080x1080 · 1200x628

- pill: `● FOUNDING RATE` with inline `background:var(--violet)`.
- H (3-line staircase — 2 lines cannot fit at 92px): `Founding rate:<br>50% off, locked in<br>while you stay.` Use `--stageh:390px` on 4:5; the 4 chips may sit as a 2×2 grid (two rows is correct here).
- sub: `The whole Pro desk at the Insider price — $75/mo, billed $900 a year.`
- stage: FRONT-center: `w-founding` (width 560 on 4:5): frate pill `FOUNDING RATE`; plan `Pro`;
  price: was `$109` → now `$75` + per `/mo billed annually` (the card mirrors the LANDING's
  annual anchor so `SAVE $408 A YEAR` is computable inside one frame — $109×12−$900=$408;
  the OFFER BAR keeps the $149-struck monthly anchor for the 50%-off claim. Never mix the
  two anchors in one element — R2 review #1, the round's only blocker); save badge `SAVE $408 A YEAR`;
  meter: l1 `FOUNDING MEMBERSHIPS` + span `2,000 total — first come, first served`; track
  fill 12%; l2 `The allotment shrinks daily · $900/yr locked in for as long as you stay.`
  BEHIND-left: read sliver; BEHIND-right: prophet sliver.
- chips: `Everything in Insider(v) · 50 AI deep dives / mo(blue) · Mastermind research(g) ·
  Bot Portfolios — soon(gold)` (square: first 3 with `--chip:27px;gap:12px` on `.chips`;
  the `/ mo` is load-bearing — the landing grants 50 per month, not 50 ever — R2 review #10).
- offer: cell1 t `7-DAY FREE TRIAL` d `FULL PRO ACCESS`; cell2 t was/`$75/mo` d `50% OFF · ANNUAL`;
  CTA `Try Pro free`. micro: standard.

## read — paper · 1080x1350 · 1080x1080

- pill: `● REBUILT NIGHTLY`
- H: `Wake up to a market<br>already read.`
- sub: `Overnight the engines rebuild every board — regime, signals, rotation — so your 7am glance is enough.`
- stage: FRONT: `w-read` scaled 1.06 (the exemplar card, gauge 57 Mixed).
  BEHIND-left `w-lanes` markup:
  ```html
  <div class="card w-lanes behind tilt-l" style="left:…;top:…">
    <p class="kick">WHAT TO ACT ON NOW <span class="asof">demo</span></p>
    <div class="lane buy"><h4><i></i>BUY NOW</h4>
      <div class="row">Big Pharma<span class="sc">69</span></div>
      <div class="row">US Energy<span class="sc">71</span></div></div>
    <div class="lane soon"><h4><i></i>ALMOST READY</h4>
      <div class="row">Industrials<span class="sc">58</span></div></div>
  </div>
  ```
  BEHIND-right: prophet sliver.
- chips: `Today's read(gold) · Stock signals(g) · Theme rotation(blue) · AI analyst(r)` (square 3).
- offer/micro: standard.
