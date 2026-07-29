# Landing "Instrument-Grade" Redesign — Pinned Direction (Fable, 2026-07-29)

Benchmark study: attio.com (refs in `src/attio-*.png`). Our before: `src/ours-*.png`.
This document is the **single source of design truth** for all build waves. Builders do
not invent design decisions; ambiguities resolve HERE or bounce back to the main session.
DESIGN_DOCTRINE.md is content law and wins on conflict. frontend-design skill sets the bar.

---

## §0 ACCEPTANCE GATES — every wave, "not done unless"

1. **Shots posted**: full-section screenshots at 1440px (EN + ZH) and 390px (EN), with
   `?still`, of every touched section — rendered from the local `site/` server, saved to
   `mockups/refs/landing-agentic-2026-07/shots/w<N>/`, and listed in the wave report.
   Playwright: Python API, `p.chromium.launch(channel="chrome")` (the cached chromium
   build is broken on this Mac — `channel="chrome"` is mandatory; launch requires the
   Bash sandbox disabled). Serve with:
   `python3 -c "import functools,http.server;h=functools.partial(http.server.SimpleHTTPRequestHandler,directory='site');http.server.ThreadingHTTPServer(('127.0.0.1',8848),h).serve_forever()"`
2. **Tests green** (run from repo root, this exact set):
   `python3 -m pytest tests/test_landing_navigation.py tests/test_public_chrome.py tests/test_onboard_compare_matrix.py tests/test_landing_pricing_cta.py tests/test_prophet_showcase.py tests/test_check_font_ui_defined.py tests/test_marketing_ad_plane_o.py tests/test_asset_stamp_lane_order.py -q`
3. **Pairs synced**: `python3 -m scripts.check_template_site_sync --fix` run after edits;
   `templates/index.html`≡`site/index.html`, `templates/landing.css`≡`site/landing.css`.
4. **Console clean**: zero JS errors on load (capture via Playwright console listener).
5. **Motion honesty**: `prefers-reduced-motion` AND `?still` render fully static; every
   NEW JS animation loop early-returns on the existing `CALM || STILL` gates.
6. **Bilingual parity**: every touched EN string has its `data-zh` twin updated, equally
   plain (no raw EN state names inside ZH). ZH shots prove it.
7. **No new bytes of font**; no external requests added; `landing.css` stays under
   100KB raw; no `fonts.googleapis.com` anywhere.
8. **Contracts untouched** (§9 list). Diffs to those DOM structures are defects.
9. **Honesty labels survive**: every `demo` / `PREVIEW` / `free` kicker, the delayed-
   winners tag + foot line, "rebuilt nightly", founding-meter truth — all still visible,
   now *designed* rather than apologetic (see §6 receipt-bar pattern). No "validated",
   no falsifier/refuted language anywhere.

---

## §1 The gap, in one paragraph

Attio beats us on **finish, not substance**: four stroke weights where we have one, seven
stacked shadow layers at 1–7% alpha where we have flat single shadows, textures (hairline
curtains, dot-grid paper, arc line-art) where we have blank fields, two-tone ink/slate
headlines where we have a dated gradient word, mono "instrument" micro-labels where we
have generic small-caps, product vignettes that fill their bands where ours float small
in dead whitespace, and easing curves with taste (extreme-decel) where ours pop. Our
substance — real regime gauge, real terminal, honest delayed-winners belt, real filings —
is BETTER raw material than their fictional Basepoint. The job: keep every section, every
contract, every honesty label; raise the finish to their level and past it.

## §2 Token system upgrade (`landing.css` `:root`)

Keep existing palette identities (`--bg #f7f8fa`, `--panel #fff`, `--ink #1c2430`,
`--muted #5d6b7e`, `--blue #285fff`, washes, verb hues). ADD:

```css
/* stroke tiers — border weight is information */
--hair-weak:#f0f2f5;   /* inner dividers inside cards */
/* --hair:#eaecf0 stays = subtle/default card edge */
/* --hair-2:#dfe3e9 stays = defined edge (inputs, chips) */
--hair-strong:#cfd6df; /* emphasis edge: hovered/active cards, stage frames */

/* layered shadows — always UNDER a 1px stroke, never instead of one */
--sh-1:0 1px 2px rgba(16,24,40,.03);
--sh-2:0 2px 4px -1px rgba(16,24,40,.04);
--sh-3:0 4px 10px -2px rgba(16,24,40,.05);
--sh-4:0 12px 24px -6px rgba(16,24,40,.07);
--sh-5:0 24px 48px -12px rgba(16,24,40,.09);
--sh-card:var(--sh-1),var(--sh-2);
--sh-lift:var(--sh-1),var(--sh-2),var(--sh-3);
--sh-float:var(--sh-2),var(--sh-3),var(--sh-4);
--sh-stage:var(--sh-3),var(--sh-4),var(--sh-5);

/* radius */ --r-xl:20px;      /* stage windows (hero center card, terminal frame) */

/* type */
--mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;
--hl-muted:#8b95a6;    /* two-tone headline continuation */

/* motion */
--ease-out:cubic-bezier(0,0,0,1);        /* extreme decel — reveals, hovers */
--ease-emph:cubic-bezier(.2,0,0,1);      /* stage moves */
--dur-micro:.15s; --dur-rev:.7s; --dur-stage:.9s;
```

Existing `--sh-card/--sh-lift/--sh-deep/--sh-plate` uses: migrate every consumer to the
new compositions (`--sh-deep`→`--sh-stage`, `--sh-plate` keep for dark band). Do not
leave both systems live.

## §3 Type devices

- **⚠ OPERATOR RULING 2026-07-29 (supersedes the two-tone plan):** the hero's
  three-line headline WITH the gradient "Institutional-grade." line and the dark
  `LIVE · MARKET READ` pill are HOUSE IDENTITY — they stay, byte-faithful, through
  any redesign. `.hd-mut` is a **reserved** utility (registered in CSS, unused).
  Section h2s stay plain `--ink` — do NOT apply two-tone or gradients to them.
- **Display scale**: hero h1 `clamp(44px,6vw,76px)`, weight 800, tracking `-.022em`,
  line-height 1.0. Section h2 `clamp(34px,3.6vw,52px)`, weight 800, tracking `-.018em`,
  line-height 1.04. Sub/lede 17–18px, `--muted`, max-width 56ch.
- **Mono kicker utility** `.mk`: `font:500 11px/1 var(--mono); letter-spacing:.08em;
  text-transform:uppercase; color:var(--faint);` → replaces the sans small-caps kickers
  on section eyebrows, card kickers, as-of stamps, ZONE/EDGE labels, receipt bars.
  Numbers inside `.mk` inherit mono = instrument feel. (System mono = zero font bytes,
  consistent with the locked system-face law.)
- Blue all-caps section eyebrows keep their blue but move to `.mk` sizing/tracking.
- `tabular-nums` discipline: every mono numeric cell keeps/gains `.tnum` semantics.

## §4 Texture library (new, shared)

All textures are CSS-only utilities; all sit behind content (`z-index` discipline);
all are static (no animation) so CALM/STILL costs nothing.

1. **`.tx-curtain`** (hero field + light bands that need ground): vertical hairline
   curtain — `repeating-linear-gradient(90deg, rgba(255,255,255,.85) 0 1px, transparent
   1px 8px)` laid OVER a soft radial wash `radial-gradient(120% 90% at 50% 112%,
   var(--field-tint,#dbe4ff) 0%, #eef2ff 42%, rgba(238,242,255,0) 78%)`. Bottom-anchored,
   height ~55% of band, edge-faded with a mask.
2. **`.tx-paper`** (belt band): dot grid `radial-gradient(rgba(28,36,48,.05) 1px,
   transparent 1.1px)` / `background-size:12px 12px`, with a radial mask fading to
   nothing at the edges. Paper, not graph paper: dots, not lines.
3. **`.tx-arcs`** (dark bands): one shared inline SVG (or CSS radial ring) drawing 2–3
   huge concentric hairline arcs, `stroke:rgba(255,255,255,.05)`, off-center. Terminal
   band + closing band.
4. **Edge fade masks** for the prophet belt crop:
   `mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent)`.
5. **Dark curtain** (closing band): same curtain at `rgba(255,255,255,.045)` lines.

## §5 Card anatomy law (every vignette)

`background:var(--panel); border:1px solid var(--hair-2); border-radius:var(--r) [stage:
var(--r-xl)]; box-shadow: tier per role` — elevation tiers: **card** (list rows, inner
tiles: `--sh-card`) → **lift** (standard vignettes: `--sh-lift`) → **float** (hero wings,
belt cards: `--sh-float`) → **stage** (hero center, terminal frame, AI window:
`--sh-stage`). Inner structure divided by `--hair-weak` hairlines, never spacing alone.
Kickers `.mk`. Interactive cards hover: `translateY(-1px)` + one shadow tier up +
`border-color:var(--hair-strong)`, `transition:transform var(--dur-micro) var(--ease-out),
box-shadow var(--dur-micro) var(--ease-out)`. Focus-visible: 2px `--blue` ring, 2px offset.

**Receipt bar** (formalized honesty, replaces scattered footnote text INSIDE vignettes):
a bottom strip inside the card, `border-top:1px solid var(--hair-weak)`, `.mk` type,
carrying exactly: state tag (`DEMO` / `PREVIEW` / `LIVE` / `FREE` / `DELAYED`) · one
honest sentence · one as-of. One per card max (Law 4: one footnote). The existing kicker
badges stay where tests/copy pin them; visual home just gets consistent.

## §6 Section-by-section

### 6.1 Hero (`header.cover`)
- **⚠ SUPERSEDED BY OPERATOR RULING 2026-07-29 — the copy block is FROZEN:** the
  original three-line h1 (`Your personal<br>market intelligence desk.<br><span
  class="dim">Institutional-grade.</span>`, ZH `你的专属/市场情报台。/机构级标准。`),
  the gradient `.dim` treatment, the ORIGINAL sub sentence, and the DARK live-pill
  are restored verbatim and stay. No wave touches the hero copy block again.
  (History: W1 briefly shipped a two-tone/white-pill hero per the original §6.1;
  the operator vetoed it on sight — "I loved our gradient header, and the live
  market read — restore those." Identity wins over benchmark mimicry.)
- CTAs unchanged (blue primary, quiet secondary) but secondary gets `1px var(--hair-2)`
  + `--sh-1` + hover lift; primary gets `--sh-2` + hover brightness.
- Collage re-choreography (the 5 `.pcard`s keep ids/classes/JS hooks):
  center `pp3` (Today's Read) = **stage**: scale 1.0, `--r-xl`, `--sh-stage`, z5;
  inner wings `pp2`,`pp4` = **float**: scale .93, z3; outer wings `pp1`,`pp5` = **lift**:
  scale .87, opacity .94, z2. Deeper negative-margin overlap than today (wings tuck
  ~48px under their neighbor). No blur.
- Field: `.tx-curtain` behind/below the collage (band-wide), plus `--field-tint`
  signature (§8). Cards' internals get §5 anatomy + `.mk` kickers.
- Entrance: center card rises first (`--d:0`), inner wings `--d:.09s`, outer `--d:.16s`,
  copy block staggers above (pill 0 → h1 .05 → sub .12 → CTAs .18).

### 6.2 Terminal band (`#f-terminal`)
- Environment: band keeps `--plate`-family dark bg; add `.tx-arcs` + a barely-visible
  40px grid (existing pattern ok); Safari frame gets `1px solid rgba(255,255,255,.09)`,
  `--r-xl`, `--sh-stage`, and a soft under-glow `0 40px 120px -40px rgba(40,95,255,.25)`.
- Headline two-tone (white + slate `#9aa6b8`). Logo row: normalize logo heights, gray →
  `opacity .55`, hover 1; spacing on the 8px grid.
- Inside the mock: no structural change (JS draws it) — CSS polish only: hairline tiers
  on panel dividers, `.mk` for rail labels where classes already exist.

### 6.3 Prophet belt (`.psec#f-prophet`)
- Band: `.tx-paper` + top/bottom `1px var(--hair)` section borders (§7 draw-in).
- Cards: §5 float tier; verb hue system stays; stage dots (`.psc-stages`, aria pinned)
  get 1px hair ring + active fill; receipts (`ZONE …`, date) → `.mk`.
- Belt crop gets the §4 edge-fade mask. `phDrift 95s` + mobile `60s` UNTOUCHED (test).
- Headline two-tone; the honest tag `REAL CALLS · 2-WEEK DELAYED · BOARD OF <date>`
  becomes a designed mono chip (dark ink pill, white text) — same words, prouder.

### 6.4 Feature bands ×4 (`#f-rotations`, `#f-filings`, `#f-sits`, `#f-funds`)
- Re-proportion `.feat-grid`: vignette column 58%, copy 42% (flip alternates as today);
  vignette fills the band (min-height ~440px desktop), copy column vertically centered.
- Band padding unified: `clamp(96px,11vw,148px)` top/bottom; every band separated by
  `1px var(--hair)` full-bleed rule (the §7 draw-in element).
- Vignettes get §5 anatomy + receipt bar; internal rows get `--hair-weak` dividers,
  hover states where rows already animate (JS loops unchanged).
- Copy column: eyebrow `.mk` blue; h2 plain `--ink` (operator ruling — no two-tone);
  lede ≤2 lines; the 3 dash-bullets → 3px round-tick bullets (blue), lead-in bold ink,
  rest muted; arrow link keeps hover nudge. PREVIEW badges keep position (top-right of
  vignette) restyled as §5 receipts.
- Copy budget sweep within existing meaning — NO new claims, `data-zh` twins updated.

### 6.5 Beyond band (`#f-beyond`) — same §6.4 treatment; the three asset cards align to
one shared height; cycle arc gets a draw-on-reveal (§7; CALM-static).

### 6.6 Mastermind AI (`#ai`)
- Chat becomes a **stage window**: top bar with three traffic dots (decorative), title
  "Mastermind AI", right side `.mk` tag `SCRIPTED DEMO` (honesty formalized — EN/ZH).
  `--r-xl`, `--sh-stage`, hair border.
- Tool/receipt moments in the script get chip styling (`.mk` chips with `--hair-2`
  borders): they exist in the flow already; visual only. Composer caret keeps blink.
- Capability chips row → §5 card chips with hover.

### 6.7 Pricing (`#pricing`)
- Tier cards: §5 anatomy; featured Pro card border `--blue` at 1px (not 2px) + `--sh-float`
  + a `.mk` "MOST POPULAR"-equivalent only if one exists today (do NOT invent copy).
  Founding meter: keep exact mechanics/truth; restyle track to `--hair-weak` w/ blue fill.
- Matrix: DOM/rows PINNED (tests). Visual only: group header rows `.mk` blue, row hover
  `#fafbfc`, check/✗ sizing consistent, sticky header NO (don't touch structure).
- Toggle: segmented control restyle (§5 chip, active white + `--sh-1`).

### 6.8 Closing band (`.cband`) + footer
- `.cband`: dark curtain + `.tx-arcs`; benefit pills get dark-tier anatomy
  (`rgba(255,255,255,.06)` bg, `.08` border); headline stays.
- Footer: structure/anchors PINNED — visual polish only: column label rows `.mk`,
  link hover ink shift, spacing to 8px grid.

## §7 Motion doctrine

- `.rv` upgrade: `translateY(14px)`, `--dur-rev` `--ease-out`; stage elements variant
  `.rv-stage` 22px/`--dur-stage` `--ease-emph`. Stagger via existing `--d` inline vars,
  steps of .07s, max .28s per cluster.
- **Draw-in rules**: full-bleed section hairlines are `scaleX(0)→1`, origin left,
  `--dur-stage` `--ease-emph`, when the band enters (reuse the `.rv` IntersectionObserver
  by adding the class to observed set — do NOT add a second observer).
- Existing loops (heat jitter, lane FLIP, filings feed, sits swap, funds bars, chat
  script, belt drift) KEEP their logic; only re-time entrances to the new easings where
  CSS classes already control them.
- Hover physics per §5. Links: arrow `translateX(2px)`.
- Every new CSS animation/transition must appear inside the THREE existing kill blocks:
  the global reduced-motion block, the `?still` block, and (if JS-driven) behind
  `CALM || STILL`. The §8 tint transition included.

## §8 Signature — "the page reads the tape"

One aesthetic risk, quiet and honest: the hero curtain's wash tint follows the demo
regime cycle that ALREADY drives the gauge (`WORD` in the pyramid IIFE). JS sets
`document.body.dataset.regime = goldilocks|reflation|deflation|stagflation` at the same
moment it updates the gauge; CSS maps it:

```css
body{--field-tint:#dbe4ff}                       /* default / goldilocks */
body[data-regime="reflation"]{--field-tint:#d9eede}
body[data-regime="deflation"]{--field-tint:#e2e6ee}
body[data-regime="stagflation"]{--field-tint:#f0e7d4}
.cover .tx-curtain{transition:--field-tint 1.2s var(--ease-emph)}  /* via bg transition */
```

(Implement the fade by transitioning `background` on the wash layer — custom-property
transitions don't interpolate without `@property`; registering `@property --field-tint`
with `syntax:'<color>'` is the clean path — do that, with the fallback being no
transition.) Amplitude stays whisper-quiet: the four tints are near-neighbors, never
saturated. Under CALM/STILL: attribute never changes (the cycle loop is already gated),
so the field is static default — nothing extra to do. The gauge card already labels the
cycle `demo`; the atmosphere claims nothing.

## §9 DO-NOT-TOUCH contracts (from the census; breaking any = wave rejected)

1. `<nav class="nav">` DOM: 3 `.nav-trigger` disclosures + ids (`nav-login`, `nav-cta`,
   `gear-btn`, `gear-pop`, `gp-*` mount points) + the literal
   `matchMedia('(max-width: 900px)')` string in nav JS. CSS restyle allowed.
2. Footer anchor SET (hrefs+text) — byte-parity with `_public_footer.html.j2` rendering.
   Visual CSS only.
3. `#pricing-matrix` group headings, feature label strings, row order (mirrors
   `onboard.js` COMPARE). `applyPricing()` pinned substrings.
4. `#mm-adtest` JSON + `adtest.js` untouched; `data-adtest-slot` attributes stay on the
   same h1/p nodes.
5. `#ph-data` island; `prophet.showcase/v2` handling; `.psc-stages` with
   `aria-label="Setup stage: Ready"`; `phDrift 95s` desktop + faster inside the 640px
   block; belt card derivation staying in sync with `cardHTML()`.
6. Live-quote selectors: `.lvp/.lvd/.lv/.cn[data-sym]`, `.twl-r[data-w]`,
   `window.__twlLive`.
7. `LANG` inline IIFE + `LANG.apply(LANG.cur())` position AFTER all component IIFEs;
   dynamic spans stay SIBLINGS of `data-zh` nodes (never children).
8. Head: no new external requests; the two stamped `<link>`s; LANG boot + dbase shim
   blocks; JSON-LD.
9. `onboard.js`/`onboard.css`/`adtest.js` files untouched this program.
10. The 6 client-logo `<img>`s keep their files; no new raster assets without approval.

## §10 Wave plan

- **W1 — Foundation + Hero**: §2 §3 §4 §5 tokens/utilities/textures; §6.1 hero; §8
  signature; nav CSS polish. (Touches: `templates/landing.css`, `templates/index.html`
  hero region + pyramid JS one-liner for `data-regime`.)
- **W2 — Proof bands**: §6.2 terminal, §6.3 belt, §6.4 rotations+filings.
- **W3 — Story bands**: §6.4 sits+funds, §6.5 beyond, §6.6 AI, §6.7 pricing, §6.8 close.
- **W4 — Motion & micro-detail sweep**: §7 everywhere, hover/focus audit, receipt-bar
  consistency, spacing-grid audit, copy-budget trim pass.
- Each wave: build → self-verify against §0 → report with shots → Fable audit → fixes →
  next wave. No self-merge; the main session ships at the end.
