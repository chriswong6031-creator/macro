# Prophet candidate "Added date" chip (`.pv-added`) — visual evidence + theme packet

PR #6719 · branch `claude/prophet-candidate-added-date-e2e-20260901`.
**Reshot 2026-09-01 against head `becf409188ce`** (repair round 3 = `d21837f5f5c2`).
Supersedes the 2026-09-01 refresh at `c14b54a0bbd6`; every claim below names its PNG.

**Verdict: PASS.** Round 3 changed two evidenced behaviours and both are re-evidenced
here from fresh builds off this head:

1. **Canada flipped to the same soundness floor as HK** (R1). CA's name-visible
   `setups.laggards` grid is unfossiled, so CA now stamps `None` on every
   absence-anchored candidate. **CA went 10/10 chips → 0/10.** That is the honest
   state, and it is what the CA cells now show.
2. **`pv_css` degradation was tightened** (R4/R5). `.pv-znr` gained its own bounded
   overflow; the ≤680 px 32 % cap was scoped to `.pv-added` alone. On US — the only
   board that still renders the chip — every measured cell is **byte-identical** to
   the pre-round-3 pass, so the delta is provably inert on real content, and no zone
   value clips anywhere.

> **What this reshoot cost the packet.** CA was the board carrying the chip at
> density (10 cards, 5 distinct dates) and the board the Tier-2 hover was shot on.
> After R1 it carries none, so the chip's ink, hover, touch and EN/ZH evidence all
> move to **US**, whose light card material is *not* the same as CA's. That forced a
> re-measurement of §3/§4 rather than a re-crop, and it surfaced F9.

---

## 1. How this evidence was made

Real pages, real committed data, real templates. No specimen page was authored; none of
the 196 PNGs is synthetic. Capture tooling is `capture.py` next to this file (unchanged).

| Builder (`~/.cache/mm-venv-mac-builder-3/bin/python -m …`) | Result | Duration | Head |
|---|---|---|---|
| `scripts.build_canada` | rc=0 | 73 s | **`becf409188ce` (this pass)** |
| `scripts.build_site` (US) | rc=0 | 1069 s | **`becf409188ce` (this pass)** |
| `scripts.build_hk` | rc=0 | 68 s | `c14b54a0bbd6` (carried — see §10) |
| `scripts.build_china` | rc=0 | 1345 s | `c14b54a0bbd6` (carried — see §10) |
| `scripts.build_intl` | rc=0 | 161 s | `c14b54a0bbd6` (carried — see §10) |

The built `site/` tree was served over a local static server and driven with Chromium.
Theme and language use **the site's own mechanism** — the `theme` / `lang`
`localStorage` keys `templates/theme.js` reads before first paint — and every cell
asserts the resulting `data-theme` / `data-lang` before screenshotting.

Both rebuilt pages were confirmed to carry the round-3 CSS before any shot was taken:

```
site/canada_stocks.html, site/us_stocks.html:
  .pv-znr{font-weight:700;flex:none;max-width:100%;overflow:hidden;text-overflow:ellipsis}
  @media (max-width:680px){ .pv-added{max-width:32%} }      /* .pv-dt no longer capped */
```

Four mechanics are load-bearing, each having previously produced a wrong result:

- These boards **mount client-side after load**; geometry is re-measured immediately
  before every screenshot and each page settles until `scrollHeight` stops moving.
- Board clips are taken in **document** coordinates (`full_page=True`); a
  viewport-relative clip silently framed an entirely different panel.
- **The LENS popover is `position:fixed`**, so the opposite is true for it: a
  document-space clip (rect + `scrollY`) frames it in the wrong place. The hover cells
  are therefore shot `full_page=False` in viewport coordinates. The first attempt this
  pass got this wrong and produced a half-cropped popover; the shipped shots are the
  corrected ones.
- The freshness probe is **case-insensitive** and matches the *label plus a year*, not
  an ISO string — `intl.html.j2` emits a lowercase `data through`, and the shell chip
  renders `Board Aug 31, 2026`, not `2026-08-31`.

Capture is unauthenticated — the honest anonymous state. On US that also means the
tier-preview ghost is active (§6).

---

## 2. What the chip is, after round 3

```css
.pv-znr {font-weight:700;flex:none;                                  /* the PRICE: never shrinks */
         max-width:100%;overflow:hidden;text-overflow:ellipsis}      /* R4: bounded far-edge overflow */
.pv-added{margin-left:auto;color:var(--muted);flex:0 1 auto;min-width:0;
          overflow:hidden;text-overflow:ellipsis;font-size:9.5px;padding-left:5px}
@media (max-width:680px){ .pv-added{max-width:32%} }                 /* R5: scoped off .pv-dt */
```

`.pv-added` renders EN `Added <Mon D>` / ZH `入榜 <MM-DD>` at the right end of the zone row,
and renders **nothing** when the engine cannot prove a start date. There is still no
`html[data-theme="light"]` rule for it.

### Chip coverage on this head

| Board | zone rows | chips | distinct dates | shot at head |
|---|---|---|---|---|
| `us_stocks` | 3 | **3** | 1 (`2026-08-31`) | `becf409188ce` |
| `canada_stocks` | 10 | **0** | — | `becf409188ce` — **was 10/10, see F8** |
| `hk_stocks` | 10 | **0** | — | `c14b54a0bbd6` |
| `china_stocks` | 129 | **0** | — | `c14b54a0bbd6` |
| `intl_stocks` | 60 | **0** | — | `c14b54a0bbd6` |

**US is now the only board that renders the chip at all.** Every other board is null.

### Launch state — what a reader meets the day this merges

| Board | day one | why | mechanism |
|---|---|---|---|
| `us_stocks` | **chips, immediately** | `snapshots.jsonl` fossilises board membership back to 2026-06-15, so continuous-membership start is provable today | `stamp_us_board_since` |
| `hk_stocks` | **null, accrues after merge** | the name-visible `setups.laggards` grid is not persisted in `hk_board.parquet`, so an absence cannot be distinguished from an unrecorded lane; dates accrue only from post-merge fossils | `HK_CA_REQUIRES_FULL_COVERAGE["hk"]=True` |
| `canada_stocks` | **null, accrues after merge** | same defect class, ratified in round 3 — `canada.html.j2` renders `setups.laggards` names that `ca_board.parquet` never persists | `HK_CA_REQUIRES_FULL_COVERAGE["ca"]=True` |
| `china_stocks` | **null, accrues after merge** | the dynamic floor `cn_full_coverage_since` is the earliest `more_actionable`-tagged fossil row, and is only established by a post-merge build; every earlier absence is pre-floor and resolves to `None` | `cn_full_coverage_since` |
| `intl_stocks` | **null until a real `as_of`** | `setups.as_of` is null upstream today, so nothing may be minted; existing dates carry forward, new names get `None`. The frozen spec calls this "expected and correct" | `stamp_intl_board_since` |

Four of five boards are silent on day one, and each silence has a different cause. That
is the honest state of the feature, not a defect of this evidence — but it is the reason
F4 is now the largest open design question in this packet.

---

## 3. DARK TREATMENT — command centre

**Re-measured on `us_stocks` this pass** (CA can no longer supply it). Values are read
from the live DOM, not from the stylesheet.

The card (`--panel2` → `#1B1F28`) sits above the page ground (`--bg` `#0D1018`). The zone
row is cut **downward** out of it — `color-mix(--panel 55%, --bg)` → `#11141C` — so the
footer reads as a recessed shelf sitting between the canvas and the card. Nothing glows.
The chip is untinted ink on that shelf: no pill, no border, no fill.

| | ink | on `.pv-zn` `#11141C` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#8B93A1` 9.5 px **400** | | **5.95 : 1** |
| zone value `.pv-znr` | `#C8D0DC` 700 | | 11.85 : 1 |

Subordination **1.99×**. Clears the MPDS §14 floor (≥4.5:1 at ≤18 px) with room while
carrying half the presence of the number beside it.

Luminance order, measured: canvas `0.0052` < shelf `0.0070` < card `0.0137`. The shelf is
**−0.0066** relative luminance below the card — genuinely recessed, so mid-grey on it
reads as a margin note and the chip needs no decoration to stay quiet.

Evidence: `us_stocks_dark_en_1440_board.png`, `us_stocks_dark_en_1440_zone_dated.png`,
`us_stocks_dark_en_1440_lens_hover.png`. Null twin: `canada_stocks_dark_en_1440_board.png`.

## 4. LIGHT TREATMENT — research workspace

The canvas is a cool `#E8EBF1`; the zone shelf resolves to `#F5F6F9`; separation from the
card is a hairline (`--line` `#C0C4CD`), not a shadow — `box-shadow` computes to `none` on
these cards. There is no bloom to translate, and none was invented.

| | ink | on `.pv-zn` `#F5F6F9` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#4C5A6C` 9.5 px **400** | | **6.51 : 1** |
| zone value `.pv-znr` | `#2E3950` 700 | | 10.69 : 1 |

Subordination **1.64×**.

**This is the part token substitution cannot argue for you, and this pass found a second
reason why.** The identical declaration yields a chip that is *absolutely stronger* in
light (6.51 vs 5.95) and, because the value ink also loses contrast on white
(10.69 vs 11.85), *relatively louder* — 18 % less subordinate than in dark. That was
already recorded. What is new is that **the recession mechanism itself inverts** on the
board the chip now lives on:

| light, measured | card | shelf | step | shelf reads as |
|---|---|---|---|---|
| `canada_stocks` | `#FFFFFF` | `#F5F6F9` | **−0.0784** | recessed ✓ |
| `us_stocks` | `#EEF1F6` | `#F5F6F9` | **+0.0442** | **advanced ✗** |

The card paints from `--panel2`; the shelf paints from `color-mix(--panel 55%, --bg)`.
In dark, `--panel` (`#151820`) is darker than `--panel2` (`#1B1F28`), so the shelf always
recedes. In light, `--panel` is `#FFFFFF` — *lighter* than `--panel2` `#EEF1F6` — so on a
card that paints at `--panel2` the shelf comes out **lighter than the card it sits in**.
CA escapes this only because its client shell paints its cards pure white.

So on `us_stocks` in light, the depth cue that §3 credits with doing the demotion for free
is not merely weaker — it points the wrong way. What keeps the chip quiet there is the
400/700 weight step, the 9.5 px size, and right-edge alignment against a left-aligned
`ZONE` label. That is enough today (F9 is non-blocking), but it means the chip has **no
material margin left in light**: any future increase in its weight, size, or saturation
must be judged in light, on US, first.

Evidence: `us_stocks_light_en_1440_board.png`, `us_stocks_light_en_1440_lens_hover.png`
(the popover, painted `#FFF`-ward, is visibly whiter than the card behind it — the
inversion is legible in that one crop). Null twin: `canada_stocks_light_en_1440_board.png`.

## 5. Which mechanisms intentionally differ

**None are authored to differ — verified, not assumed.** `.pv-added` reuses `var(--muted)`
exactly as `.pv-dt` does; round 3 changed only flex/overflow behaviour, identically in both
themes, and added no theme-conditional rule. Nothing this chip uses appears in the MPDS §12
translation table: it is not a tinted status chip, not a glow, not an accent rail, not a
heatmap cell.

What differs is **rendered, not authored**, and there are now two such differences, both
measured and both recorded rather than waved through as "same CSS, tokens swap":

1. the token pair resolves to different inks against differently-derived surfaces, moving
   subordination from 1.99× to 1.64× (§3/§4);
2. the card↔shelf depth step **reverses sign** in light on `us_stocks` (§4, F9).

Neither is a defect this PR introduced. Both are properties this PR's chip now depends on,
so both are stated.

## 6. Theme-specific degraded states

- **Null — now the dominant state.** Renders nothing: no placeholder, no dash, no reserved
  slot, no gap, no artifact where the chip used to be. The card simply ends at the price.
  Proven on the rebuilt CA board in all four theme × language combinations at both
  viewports: `canada_stocks_{dark,light}_{en,zh}_{1440,390}_all_zone_null.png`. The 1440 EN
  pair frames three consecutive zone rows side by side so the absence reads as a pattern,
  not a one-card accident. Carried null cells: `hk_stocks_*_zone_null.png`,
  `china_stocks_*_all_zone_null.png`, `intl_stocks_*_zone_null.png`.
- **Space-starved (the chip yields).** US at 390: the chip shrinks and ellipsizes while the
  price stays whole — §8/F1, `us_stocks_{dark,light}_{en,zh}_390_zonerow_zoom.png` at 4×.
- **Zone-value far-edge overflow (R4) — present, correctly computed, UNEXERCISED.**
  `.pv-znr` now carries its own `max-width:100%;overflow:hidden;text-overflow:ellipsis`, so
  a zone string wider than its whole row would ellipsize instead of hard-clipping
  mid-character. The declarations were confirmed live (`maxWidth 100%`, `overflow hidden`,
  `textOverflow ellipsis`, `flex 0 0 auto`), but **no real content reaches the condition**.
  Driving the widest real zone string in the product — `$3054.00–$3138.70` (CSU.TO, CA) —
  down through 390 / 360 / 320 / 300 / 280 / 260 / **240 px**, the value box measured
  `scrollWidth == clientWidth == 127 px` at every width, `ellipsized=False` throughout, and
  `docW == winW` throughout. Because `.pv-znr` is `flex:none`, `max-width:100%` only caps it
  at the row width, and the row never gets narrower than the string. **No ellipsis
  screenshot exists because the state never occurred; none was fabricated.** The
  by-product is worth keeping: CA's widest real price renders whole at **240 px**, 150 px
  below the matrix floor, with no horizontal page scroll.
- **Locked / tier-preview (US).** The chip ghosts with the rest of the card
  (`blur + saturate`, the light-safe treatment) and leaks nothing visually:
  `us_stocks_light_en_1440_board.png`, `us_stocks_dark_en_1440_board.png`. `data-added`
  remains in the DOM of ghosted cards — a pre-existing property of the blur-teaser idiom.
- **Tier-2 explanation.** Hover opens the LENS in all four theme × language combinations
  with plain-word copy, now shot on US (the only board that can still exercise it):
  `us_stocks_{dark,light}_{en,zh}_1440_lens_hover.png`. Copy verified in the DOM, EN and ZH:
  *"On the Prophet board continuously since this date. If the name leaves and later
  returns, this date resets."* / *「自该日起持续在 Prophet 榜上；若离榜后重新上榜，此日期将重新计算。」*

---

## 7. Design judgment

### Dark — PASS
On `us_stocks_dark_en_1440_board.png` the eye order is sparkline → ticker → stance →
priority → zone → chip; the chip is last and reads as a margin note. Right-aligning it
against the left-aligned `ZONE` label makes the footer a two-end table row — the rhythm the
removed `.pv-dt` chip already established, so the card gains no new idiom. Type matches the
card's micro-tier (9.5 px, as `.pv-stl`). The chip takes no stance hue, so it never reads as
signal. `canada_stocks_dark_en_1440_all_zone_null.png` shows the same footer with the chip
absent: the row still terminates cleanly on the price, with no orphaned separator, no
collapsed padding and no reserved gap.

### Light — PASS, with the §4 mechanism caveat now quantified
`us_stocks_light_en_1440_board.png` reads as designed-for-light, not translated: light cards
on a perceptibly deeper canvas, forest-green stance ink from the light rungs, hairline zone
divider, no pastel stain where dark has depth. Two caveats, both measured, neither blocking:
the 1.64× subordination, and the **+0.0442 inverted card→shelf step** (F9) that removes the
recession cue entirely on this board. Light is where this chip is closest to shouting.
`canada_stocks_light_en_1440_all_zone_null.png` confirms the null is as clean in light as in
dark — on white cards, where the shelf does recede.

### EN / ZH parity — PASS at 1440, DEGRADED at 390
`入榜 08-31` is a real translation, not a transliteration, and is narrower than the EN form
(chip 55 px vs 71 px at 1440). The ZH LENS copy is a full, idiomatic sentence, not a gloss:
`us_stocks_dark_zh_1440_lens_hover.png`. `canada_stocks_{dark,light}_zh_390_all_zone_null.png`
shows the 红涨绿跌 flip intact with the chip absent — correct, the chip carries no direction.
The asymmetry at 390 is unchanged by round 3: the narrower ZH chip survives the squeeze far
enough to render a meaningless stub, while the wider EN chip collapses to nothing. See F1a.

### Responsive — PASS
`docW == winW` in **all 40 matrix cells**: no horizontal page scroll at any viewport, and
(§6) none at 240 px either. Containment is achieved by degrading the metadata, never the
price: `valuesClipped = 0` in every cell of every board.

---

## 8. Findings

### F1 — **RE-VERIFIED under round 3.** The price does not clip, anywhere.

`.pv-znr` is `flex:none` (plus its own R4 ceiling); `.pv-added` is `flex:0 1 auto` with
`min-width:0` + ellipsis, capped at `max-width:32%` under 680 px.

| board | 390 px | pass 1 | this pass |
|---|---|---|---|
| `us_stocks` | zone prices clipped | **3 / 3** | **0 / 3** |
| `canada_stocks` | zone prices clipped | 0 / 10 | **0 / 10** |
| `china_stocks` | zone prices clipped | **22 / 24** chipped | **0** (board all-null) |
| **all matrix cells** | any zone value clipped (`.pv-znr` or `.pv-znm`) | — | **0** |

`.pv-znm` — the muted variant, which also carries numeric ranges and keeps `min-width:0` +
ellipsis — was the one value path the F1 repair did not harden. It now has **real CA
instances** (3 of CA's 10 rows: LUN.TO, EFR.TO, T.TO) and clips **0/3** at both
viewports, both themes: `canada_stocks_dark_en_1440_all_zone_null.png` frames a `.pv-znm`
row (`$35.58–$36.35`, amber `ZONE` label) beside two `.pv-znr` rows.

Crops: `us_stocks_dark_en_390_zonerow_zoom.png` — the exact card that once rendered
`ZONE $...` renders **`ZONE $145.50–$151.60` in full** (4× device scale, real CDW card).
Light twin `us_stocks_light_en_390_zonerow_zoom.png`. CA at 390 with the widest real zone
string on any board: `canada_stocks_dark_en_390_all_zone_null.png`.

**Machine confirmation that round 3 did not regress US — two independent forms:**

1. Every US cell's `cards / chips / valuesClipped / chipsEllipsized / minGapPx /
   rowsOverflowing / clipByClass` is **identical** to the pre-round-3 manifest.
2. Stronger, and found only because the reshoot was done rather than reasoned about: all
   **36 US matrix PNGs plus the 4 zonerow zooms were re-rendered** from the fresh
   `becf409188ce` build and came out **byte-identical** to the `c14b54a0bbd6` files —
   `git status` reports zero modified among them. The US board renders pixel-for-pixel the
   same before and after round 3.

The R4 ceiling never engages (§6) and the R5 de-scoping is invisible because US board cards
carry no `.pv-dt`. Measured, not reasoned. (The four `_lens_hover` and two `_touch_tap`
files ARE new — they did not exist for US before this pass.)

**Gate satisfied**: full zone price rendering, chip degrading.

The pre-repair crops that proved the original defect are **not** carried into this tree —
the condition no longer occurs, and stale "clipped" images beside the fix would misread as
current. They remain in git at the first-pass commit `1e826c7ea114`.

### F1a — Carried forward, non-blocking. The chip's degradation is not graceful in ZH.

Unchanged by round 3, re-measured on the fresh US build. At 390 the chip is squeezed to
**5 px** in EN (11 px on URBN) and **22 px** in ZH (18–29 px). At 5 px the EN chip renders
as *nothing at all* — clean, no artifact (`us_stocks_dark_en_390_zonerow_zoom.png`). At
22 px the ZH chip renders **`入..`** — a truncated single CJK character plus ellipsis, which
carries no information and reads as a rendering bug
(`us_stocks_light_zh_390_zonerow_zoom.png`, 4× zoom).

Below the width where the chip can say anything, ellipsizing it is worse than hiding it.
The priority is now correct; the form is unfinished. Not redesigned here — chip copy and the
null-renders-nothing rule are frozen for this packet.

Related measurement, for whoever picks this up: in the EN 390 cells `rowsOverflowing = 2`
of 3 — `.pv-zn`'s own `scrollWidth` exceeds its box while the price stays whole. That is the
same squeeze, seen from the row rather than the chip; it is contained by `.pv-zn`'s
`overflow:hidden` and produces no visible artifact (the EN chip is what disappears into it).

### F2 — Stands. A freshness date IS visible.

A board vintage date is visible to the anonymous reader on every board, both themes, both
languages, both viewports. Re-confirmed on both boards rebuilt this pass.

| board | what the user sees | source |
|---|---|---|
| `us_stocks` | `Data through 2026-08-31` / `数据截至 2026-08-31` | server `.stk-status` |
| `canada_stocks` | `Board Aug 31, 2026` / `榜单 2026年8月31日` | shell header chip |
| `hk_stocks` | `Board Aug 31, 2026` / `榜单 2026年8月31日` | shell header chip |
| `china_stocks` | `Data through 2026-08-31` / `数据截至 2026-08-31` | server |
| `intl_stocks` | `data through 2026-09-01 · built 2026-09-01 15:08 UTC` | server page stamp |

Crops: `canada_stocks_dark_en_1440_freshness_visible.png` — `Canada Stocks` with
`Screen · evidence accruing` · **`Board Aug 31, 2026`** · `● LIVE · Sep 1, 2026`. The CA
freshness crops came out **byte-identical to the previous pass** across all eight cells,
which is itself the proof that R1 changed the chip and nothing else in that header.
`us_stocks_dark_en_1440_freshness_visible.png` for the server-stamp form.

The first pass's "no visible freshness date on HK/CA" was a false negative produced by a
`<p>`-only, case-sensitive probe; it was retracted at `c14b54a0bbd6` and the retraction
stands. **What remains true:** `#standouts` computes `display:none` on HK and CA, so this
PR's *new* server `Data through` paragraph is genuinely unreachable on those two boards. It
is **redundant, not load-bearing** — the shell chip states the same `as_of` from the same
`#stocktable-data` payload — and it is the visible stamp on CN/US/Intl.

### F3 — Non-blocking, carried forward, now unavoidable. The US chip is a per-row constant.

All three US chips read `Added Aug 31` (1 distinct date across 3 cards). Doctrine Law 4
forbids per-row repetition of a constant — the defect the removed `date` chip was cited for.
This was previously mitigated by CA, which carried 5 distinct dates across 10 cards and read
correctly. **After R1 that counter-example is gone**: US is the only board rendering the
chip, and on US the chip is currently a constant on every card. Data-dependent, not
structural — US dates will spread as membership turns over — but on day one the only board
showing the feature shows it in its least defensible form.
`us_stocks_light_en_1440_board.png`.

### F4 — Non-blocking, now near-total. Silence is doing work the null cannot support.

`engine/prophet_board_since.py` returns `None` when membership age is unprovable — the null
means *"we cannot prove when this joined"*, not *"this is new"*. Post-round-3 that null is
**four of five boards** (CA 0/10, HK 0/10, CN 0/129, Intl 0/60) and the reader has no chip
and no tip to read it from. The frozen spec requires the null to render nothing, so this is
recorded, not changed; doctrine Law 5 would want a plain-word Tier-1 form plus a Tier-2
receipt if it is ever revisited. §2's launch-state table is the material a reviewer needs to
decide whether four silent boards is the right shipping posture.

### F5 — Non-blocking, inherited. Tier-2 reachability on touch and keyboard.

Tapping the chip opens its LENS **and** triggers the card link's Terminal launcher, which
covers it. **Both halves of the parity pair are now current and on one board** (previously
the shipped half had to be carried from HK, because CA rendered no `.pv-mk-i`):

| gesture, US at 390, dark EN | LENS opened | navigated | launcher overlay |
|---|---|---|---|
| tap `.pv-added` (new) | yes — the added-date copy | no | **yes** |
| tap `.pv-mk-i` (shipped) | yes — the setup-shape copy | no | **yes** |

`us_stocks_touch_tap_new.png` / `us_stocks_touch_tap_shipped.png`. Identical outcome for
both chips confirms this is the card idiom's behaviour, not this chip's, and it is untouched
by round 3. Neither element is focusable, so neither tip is keyboard-reachable.

### F6 — Note. `.pv-dt + .pv-added` remains unexercised.

No caller passes both `date` and `added_date`, so the two-chip composition still has no
real-data instance. No specimen fabricated. R5 deliberately left `.pv-dt` out of the ≤680 px
cap, so if that composition ever ships, the two chips will degrade under *different* rules —
worth a look at that point, not now.

### F7 — Carried forward. China silently lost all 24 chips.

CN went from 24/129 chips to 0/129 at `c14b54a0bbd6`. CN's dynamic floor
(`cn_full_coverage_since`) is only established by a post-merge build, so every absence
observed before then is pre-floor and resolves to `None`. Defensible — the floor doing its
job — but it removed the board where the chip appeared at meaningful density.

### F8 — **NEW this pass, expected, ratified.** Canada lost all 10 chips.

R1 flipped `HK_CA_REQUIRES_FULL_COVERAGE["ca"]` to `True` because `canada.html.j2` renders
`setups.laggards` names that `ca_board.parquet` never persists — the same defect class as
HK's. CA therefore stamps `None` on every absence-anchored candidate rather than a
confidently wrong date. **10/10 → 0/10, verified on the fresh build:** `added_date` does not
appear in the CA payload at all, and all eight CA cells probe `chips = 0` over 10 cards.

This is the correct outcome and the commissioned one. It is recorded as a finding only
because it invalidates a large block of previously-shipped evidence (§9) and because,
combined with F7, it means **the chip's density evidence no longer exists anywhere**: the
feature ships showing three identical dates on one board.

### F9 — **NEW this pass, non-blocking, inherited (not introduced by this PR).** In light, the zone shelf sits *above* the card on `us_stocks`.

Measured: the card paints from `--panel2`, the shelf from `color-mix(--panel 55%, --bg)`.
In light `--panel` (`#FFFFFF`) is lighter than `--panel2` (`#EEF1F6`), so the shelf
(`#F5F6F9`) comes out **+0.0442 relative luminance above** the card it sits in — it advances
where it is meant to recede. In dark the same expression yields **−0.0066** (recedes), and
on CA the inversion does not occur because that board's shell paints its cards pure white
(**−0.0784**). Neither card is `pv-featured`; this is the base material, not a state.

Consequence for this packet: the "recession does the demotion" argument in §3 is a
**dark-only guarantee**. On the one board still rendering the chip, in light, the chip's
quiet rests entirely on weight, size and alignment. It holds — 6.51:1 with a 1.64× step —
but with no material margin. Reported, not fixed: this is a pre-existing token-architecture
property affecting every `.pv-zn` on every Prophet card, far outside this packet's scope.
Legible in `us_stocks_light_en_1440_lens_hover.png`, where the `#FFF`-ward popover is
visibly whiter than the card behind it.

### F10 — Note on the touch evidence. All four tap PNGs are byte-identical.

`us_stocks_touch_tap_{new,shipped}.png` and the carried
`hk_stocks_touch_tap_{new,shipped}.png` share one MD5 (`5a39f1d6…`). That is not a capture
error — it is F5 stated in pixels: the Terminal launcher overlay covers the entire viewport,
so the screenshot after *any* of the four gestures is the same opaque
`MASTERMIND TERMINAL / Opening your live market workspace…` panel, with no board content and
no LENS visible. The images prove the **occlusion**; the discrimination between the two
chips comes from the DOM probe recorded in F5's table. Stated here so no reader mistakes
four identical files for four independent observations.

---

## 9. Screenshot index

196 PNGs. Naming `<page>_<theme>_<lang>_<viewport>[_all]_<subject>.png`; `_all` marks the
board's own "All candidates" view, opened as a user opens it. `capture_manifest.json` holds
the per-cell machine record: card/chip counts, distinct dates, chip↔price gap, per-class
clipping (`clipByClass`), chip width and ellipsis state, computed inks, visible `freshness`
entries, `docW`/`winW`.

All 40 cells are dark **and** light × EN **and** ZH × 1440 **and** 390 — 8 per board.

| board | state | head | per-cell shots |
|---|---|---|---|
| `us_stocks` | 3 cards, **3 chips**; card 1 unlocked, 2–3 ghosted | `becf409188ce` | `_board` · `_card_longest` · `_zone_dated` · `_freshness_visible` · `_zonerow_zoom` (390, 4×) · `_lens_hover` (1440) |
| `canada_stocks` | 10 cards, **0 chips** (null) | `becf409188ce` | `_board` · `_card_longest` · `_all_zone_null` · `_all_card_longest` · `_freshness_visible` |
| `hk_stocks` | 10 cards, **0 chips** (null) | `c14b54a0bbd6` | `_board` · `_card_longest` · `_zone_null` · `_freshness_visible` |
| `china_stocks` | 129 cards, **0 chips** | `c14b54a0bbd6` | `_board` · `_card_longest` · `_all_zone_null` · `_all_card_longest` |
| `intl_stocks` | 60 cards, **0 chips** | `c14b54a0bbd6` | `_board` · `_card_longest` · `_zone_null` |

**F1 verification set** — `us_stocks_{dark,light}_{en,zh}_390_zonerow_zoom.png` (4× device
scale on the real CDW card) and `canada_stocks_{dark,light}_{en,zh}_390_all_zone_null.png`
(widest real zone string in the product).

**Null-state set (mandatory)** — `canada_stocks_{dark,light}_{en,zh}_{1440,390}_all_zone_null.png`.

**Tier-2 / interaction** — `us_stocks_{dark,light}_{en,zh}_1440_lens_hover.png`,
`us_stocks_touch_tap_{new,shipped}.png` (see F10).

### Superseded cells — removed from this tree at `becf409188ce`

Recoverable from git at `c14b54a0bbd6`. Removed rather than left in place because a shot
labelled "current" that shows a chip CA no longer renders is worse than no shot.

| removed | count | superseded by | why |
|---|---|---|---|
| `canada_stocks_{dark,light}_{en,zh}_{1440,390}_all_zone_dated.png` | 8 | `…_all_zone_null.png` | CA renders no dated zone row (F8) |
| `canada_stocks_{dark,light}_{en,zh}_1440_lens_hover.png` | 4 | `us_stocks_…_1440_lens_hover.png` | no `.pv-added` on CA to hover (F8) |
| `canada_stocks_touch_tap_new.png` | 1 | `us_stocks_touch_tap_new.png` | no `.pv-added` on CA to tap (F8) |

**Superseded in meaning, not deleted** — these files still exist and are still accurate as
*images*, but the claims attached to them in the `c14b54a0bbd6` write-up no longer hold:

| cell | claim then | status now |
|---|---|---|
| `canada_stocks_*_board.png`, `*_card_longest.png` (24 files) | CA board **with** `Added <Mon D>` chips, 5 distinct dates | **re-shot at `becf409188ce`**; same filenames, chip-free content |
| §2 coverage row "`canada_stocks` 10/10 chips, 5 distinct dates" | CA is the density case | **superseded** — CA is 0/10 (F8) |
| §3/§4 ink tables sourced from `canada_stocks_*_1440_board.png` | CA supplies the chip inks | **superseded** — re-measured on `us_stocks` (§3/§4) |
| §7 "Dark — PASS" / "Light — PASS" read on CA boards | CA is the design reference | **superseded** — judged on US; CA now evidences the null |
| §10 "the touch parity pair is first-pass (HK)" | parity could not be re-taken post-repair | **closed** — both halves re-taken on US (F5) |

### CA null receipt (from the built page, post-round-3)

`site/canada_stocks.html`, from the 73 s `scripts.build_canada` run at `becf409188ce`:
the string `added_date` does not occur in the CA payload, and `data-added` does not occur
in the document. The rendered zone row terminates at the price:

```html
<span class="pv-znl"><span class="l-en">Zone</span><span class="l-zh">买区</span></span>
<span class="pv-znr">$3054.00–$3138.70</span>
```

### US chip receipt (from the built page, post-round-3)

`site/us_stocks.html`, from the 1069 s `scripts.build_site` run at `becf409188ce`
(3 × `data-added="2026-08-31"`):

```html
<span class="pv-znr">$145.50–$151.60</span>
<span class="pv-added" data-added="2026-08-31"
      data-tip-en="On the Prophet board continuously since this date. If the name leaves and later returns, this date resets."
      data-tip-zh="自该日起持续在 Prophet 榜上；若离榜后重新上榜，此日期将重新计算。"
  ><span class="l-en">Added Aug 31</span><span class="l-zh">入榜 08-31</span></span>
```

---

## 10. Gaps

- **HK / CN / Intl cells were shot at `c14b54a0bbd6`, not at this head.** Judgment: they
  **stand**. All three are all-null, so the `.pv-added` 32 % cap has nothing to act on, and
  `.pv-znr`'s R4 ceiling is inert on real content at every width tested down to 240 px (§6)
  — the same CSS, verified on CA, which carries the widest real zone string in the product.
  One bounded exception is flagged rather than hidden: round 3's **R3** also changed
  `scripts/build_china_library.py` (the `_more_actionable` append guard). That guard only
  fires on a zero-featured night, so it is unlikely to have moved today's CN board — but it
  *could* change which cards a fresh CN build renders. The CN **chip** state (all-null) is
  unaffected either way, because the null comes from the coverage floor, not from R3. A CN
  rebuild is ~22 min and was out of this commission's scope.
- **The chip has no density instance anywhere** (F7 + F8). US ships three cards carrying one
  identical date, so F3 has no counter-example on any board. The 5-distinct-dates CA
  evidence exists only in git at `c14b54a0bbd6`, against superseded engine behaviour.
- **The R4 far-edge ellipsis is unexercised** (§6). Present and correctly computed, never
  triggered by real content at any width down to 240 px. Verifying the glyph itself would
  require a fabricated zone string; none was made.
- **`.pv-dt + .pv-added`** (F6) still has no real-data instance, and R5 now gives the two
  chips different narrow-viewport rules.
- **Keyboard reachability of the Tier-2 tip** is unresolved (F5) and inherited.
- Captures are anonymous; only US gates its board, and that gated state is captured.

---
---

# ADDENDUM — 2026-09-02: the zone shelf FOLDS (Chairman visibility repair)

Branch `claude/prophet-added-date-cn-dates-visibility-20260902`, base head
`dd033837c02efca06d8fc35cfaa11082f5e2eba7`. **Design lane, CSS only** —
`pv_card()`'s markup is byte-unchanged and
`test_pv_card_is_byte_identical_across_representative_non_us_calls` proves it
independently. Chip copy, the null-renders-nothing rule, the strict-ISO gate,
the `data-tip-en/zh` + `data-added` mechanism and the SHA-256 parity-pin
mechanism are all untouched; the pv_css pin is **recomputed**, not relaxed.

The Chairman reported the chip "crowded and spaced out of view" on the live US
board — `Added A…`, `Adde…`. Everything below names its PNG or its number.

---

## A. The defect, re-measured on the live board

The zone shelf was a single **unwrappable** flex line — `.pv-zn{display:flex;
white-space:nowrap;overflow:hidden}` — carrying `[ZONE][value] …… [Added Aug 31]`.
`.pv-znr` was `flex:none` (F1: the price never shrinks) and `.pv-added` was the
row's **only shrinkable child**. So under pressure the chip did not yield space,
it **dissolved**: `flex:0 1 auto;min-width:0` has no floor, and the ≤680 px
`max-width:32%` cap made the dissolving start early on purpose.

Measured on the real committed `site/us_stocks.html`, at the board's own 2-up
narrow grid (**154 px cards** — this is the dense multi-column grid on a phone,
not a hypothetical):

| cell | card | zone value | chip needs | chip **got** | renders as |
|---|---|---|---|---|---|
| dark/light EN 390 | CDW 154 px | `$145.50–$151.60` | 71 px | **5 px** | *nothing* |
| dark/light EN 390 | FICO 154 px | `$1111.10–$1147.20` | 71 px | **5 px** | *nothing* |
| dark/light EN 390 | URBN 154 px | `$77.59–$80.69` | 71 px | **10.5 px** | `Adde…` → blank |
| dark/light ZH 390 | CDW / FICO / URBN | — | 55 px | **22 / 18.1 / 29.2 px** | `入..` |

`chipTruncated = true` on **3/3 cards, all four theme × language cells**.

**A second, worse fault the previous pass's instrumentation could not see.**
`.pv-zn`'s own `overflow:hidden` was silently clipping the row, and on the
widest card that clip reached the **price**:

| cell | `rowOverflows` | `valClippedByShelf` | `chipClipped` |
|---|---|---|---|
| `head` dark EN 390 | CDW ✓, FICO ✓ | **FICO ✓** | CDW ✓, FICO ✓ |
| `head` light EN 390 | CDW ✓, FICO ✓ | **FICO ✓** | CDW ✓, FICO ✓ |
| `fold` (all cells, both themes, EN+ZH) | 0 | **0** | 0 |

F1's earlier `valuesClipped = 0` was measured as *the element's own*
`scrollWidth > clientWidth`, which cannot see a child clipped by its **parent's**
box. `fold_us_before_dark_en_390_shelf.png` is the receipt: `ZONE $145.50–$151.60`
and **no date at all**. Its twin `fold_us_after_dark_en_390_shelf.png` shows the
same card with `Added Aug 31` in full on a folded line.

**On desktop the defect did NOT reproduce here, and that is stated rather than
papered over.** Swept 1600 → 680 px in 20 px steps, both languages: card width
never falls below **256.4 px**, the shelf stays one line, `chipTruncated = 0` and
`valClippedByShelf = 0` at every width. At the shipped grid rule's `minmax(246px,
1fr)` **floor**, however, the arithmetic is a coin flip: `.pv-zn` offers 224 px of
content and the widest real US string needs `29.6 + 5 + 114.2 + 5 + 70.6 =
**224.4 px**`. A font stack 3 % wider than headless Chromium's — an ordinary
difference between a real macOS browser and this harness — truncates. That is the
most likely origin of the Chairman's desktop `Adde…`, and the fix removes the
dependence on font metrics entirely instead of buying a few pixels against it.

---

## B. The treatment — and the two that were rejected

**Chosen: the shelf folds, it never truncates.**

```css
.pv-zn   { display:flex; flex-wrap:wrap; align-items:center; gap:2px 5px; … }   /* may become two lines */
.pv-znr  { font-weight:700; flex:none; max-width:100%; overflow:hidden; text-overflow:ellipsis }
.pv-znm  { color:var(--muted); flex:none; max-width:100%; overflow:hidden; text-overflow:ellipsis }
.pv-dt   { …unchanged… flex:0 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; padding-left:5px }
.pv-added{ margin-left:auto; color:var(--muted); flex:0 0 auto; font-size:9.5px; line-height:1.3 }
@media (max-width:680px){ /* the .pv-added{max-width:32%} cap is GONE */ }
```

Four decisions, each load-bearing:

1. **`flex-wrap:wrap` on the shelf.** The price keeps first claim on line one;
   when the line cannot hold both, the chip drops to its own line, still hard
   against the right edge, and renders whole. Truncating a 12-character date is
   worse than not printing it — `Added A…` states a fact the reader cannot use
   and reads as a rendering fault, and this card already has an honest vocabulary
   for "we cannot say": the null renders **nothing**.
2. **`.pv-added{flex:0 0 auto}` with NO `overflow`/`text-overflow`.** These are two
   halves of one decision. A flex item whose `overflow` is not `visible` resolves
   `min-width:auto` to **0**, so keeping `overflow:hidden` would have quietly
   defeated `flex:0 0 auto` and collapsed the chip to 5 px again instead of
   wrapping. The chip now has **no truncated state left to render**. The test
   pins this with that reason written out, because it is the one way this repair
   can be silently undone by a later "tidy-up".
3. **`.pv-znm` hardened to `.pv-znr`'s contract.** F1 named `.pv-znm` the one
   value path its repair never covered. The fold makes closing it *necessary*
   rather than tidy: with the chip no longer shrinkable, a `min-width:0` value
   slot becomes the sole absorber of the squeeze, so a card carrying a muted
   range or a stance sentence (`No zone — stand aside`) plus a chip would have
   started clipping the **stance** to protect the metadata — exactly inverted.
4. **`padding-left:5px` dropped from the chip.** `margin-left:auto` already pins
   it to the far right and the shelf's own 5 px column-gap is the same separation
   `.pv-znl ↔ .pv-znr` use, so the extra 5 px was belt-and-braces that cost
   precisely the room the fold was being triggered by. It buys ~4.6 px of headroom
   at the 246 px desktop floor — enough that the widest real US string now fits on
   one line there **with margin** instead of on a coin flip.

**Rejected — (a) relocate the chip to the badge/marks row.** Four reasons, in
descending weight. *Semantics:* `.pv-mk` is a taxonomy of signal-bearing marks —
rank (`★ Featured`), recency (`New`), a context event that just turned, setup
shape/theme — and the partial's own header says the row must read as a taxonomy
rather than chip spam. `Added <date>` is **provenance**, and it would sit inches
from `New`, which is the same fact at a coarser resolution: two chips for one
fact, the defect `.pv-mk-adj`'s comment already warns about in a different guise.
*The user job:* the brief requires the date not to compete with actionability —
and the marks row *is* the actionability row. *Structure:* `.pv-mk` exists only
when a caller passes `marks`, i.e. US only; four of five boards have no such row,
so the chip would need two homes or those boards would grow one. *Density:* the
row already wraps, so on a card carrying `★ Featured` + a theme name a 66 px chip
would wrap anyway — the same fold, but now shoving the **signal** chips around.

**Rejected — (c-variant) hide the chip below a legibility floor.** Clean, costs
zero height, and matches the null's semantics — but it fails the user job. The
Chairman asked to *read* the date on a crowded board; vanishing is a correct
degradation, not a fix. It stays available as the behaviour of last resort only
because the shelf's `overflow:hidden` still bounds a pathological case.

---

## C. DARK TREATMENT — command centre

Measured live on both boards (`fold_theme_measurements.txt`), not read off the
stylesheet.

| dark | value | |
|---|---|---|
| canvas | `#000000` ground behind `--bg` | |
| card `--panel2` | `#1b1f28` | lum **0.0137** |
| shelf `color-mix(--panel 55%, --bg)` | `#11141c` | lum **0.0072** |
| card → shelf step | **−0.0064** | **recessed ✓** |
| chip `.pv-added` | `#8b93a1` · 9.5 px · **400** | **5.93 : 1** |
| zone value `.pv-znr` | `#c8d0dc` · **700** | **11.80 : 1** |
| subordination | **1.99×** | unchanged by this PR |

The shelf is a **well cut downward out of the card**. When the chip folds, the
second line lands *inside that well*, on a black canvas: a mid-grey 400-weight
line at the bottom of a darker trough reads as a margin note without any
additional demotion. Dark therefore needs **no extra mechanism for the folded
line**, and it is where the 2 px row-gap is spent — a dark trough absorbs air
without the fold reading as a gap.

Evidence: `fold_us_after_dark_{en,zh}_{1440,390}_{cards,shelf}.png`,
`fold_ca_realbuild_dark_{en,zh}_{1440,390}_{cards,shelf}.png`.

## D. LIGHT TREATMENT — research workspace

Light is judged **first** for anything that could add presence, per F9. It is not
the dark design with swapped tokens, and this pass found the reason stated
precisely.

| light | `us_stocks` | `canada_stocks` |
|---|---|---|
| card | `#eef1f6` (lum 0.8774) | `#ffffff` (lum 1.0000) |
| shelf | `#f5f6f9` (lum 0.9208) | `#f5f6f9` (lum 0.9208) |
| card → shelf step | **+0.0434 — ADVANCED ✗** | **−0.0792 — recessed ✓** |
| chip `#4c5a6c` 400 on shelf | **6.50 : 1** | 6.50 : 1 |
| value `#2e3950` 700 on shelf | **10.68 : 1** | 10.68 : 1 |
| subordination | **1.64×** | 1.64× |

Three light-specific facts, all measured:

1. **F9's inversion is confirmed, unchanged, and it is the material this repair
   lands on.** The card paints from `--panel2`; the shelf paints from
   `color-mix(--panel 55%, --bg)`. In dark `--panel` is *darker* than `--panel2`,
   so the shelf always recedes. In light `--panel` is `#ffffff` — *lighter* — so
   on a board whose cards paint at `--panel2` the shelf comes out **lighter than
   the card containing it**. `us_stocks` is such a board. `canada_stocks` escapes
   it only because its client shell paints cards pure white.
2. **In light the chip is absolutely stronger (6.50 vs 5.93) and relatively
   louder (1.64× vs 1.99×).** Same declaration, different luminance environment.
3. **In light, and only in light, the fold's second line therefore enlarges an
   *advancing* plate**, where in dark it deepens a receding well. That is the one
   genuine risk this change carries, and it is a light-only risk.

**The light-first judgment.** The fold changes **position**, not ink, weight, size
or saturation, so subordination is measured **identical before and after** in both
themes (1.64× light / 1.99× dark). And the position it moves to is a *demotion* in
reading order, not a promotion: it removes the chip from the value's own line —
the only line the eye reads for the number. The residual light cost is that the
shelf grows (29.8 → 43.3 px at 390). The reason that does not bite is measured,
not asserted: **the fold never fires on the light desktop board.** Swept
680 → 1600 px, both languages, the US shelf stays 29.8 px with zero folds, so the
advancing plate never grows at reading density. Where it does fire — the 2-up
phone grid at 154 px cards — the shelf spans the whole card width regardless, and
the alternative there is an illegible date.

**A light-only ink rule was considered and refused.** Stepping the folded line's
ink down in light would restore ~1.9× subordination on the advancing plate. It was
not shipped: F9's standing caution is against *increasing* the chip's weight, size
or saturation in light, and none of those increase here; a second ink token for one
9.5 px chip is an accessory, and the estate already pays for every extra
theme-conditional rule in the pv_css shared block that all five boards render.
Chanel's rule applies — the mechanism that would be added is smaller than the
inconsistency it would introduce. Recorded as a decision, not an oversight.

Evidence: `fold_us_after_light_{en,zh}_{1440,390}_{cards,shelf}.png`,
`fold_ca_realbuild_light_{en,zh}_{1440,390}_{cards,shelf}.png`.
`fold_ca_realbuild_light_en_1440_cards.png` is the clearest read of the light art
direction as a design: white cards on a perceptibly deeper cool canvas, forest-green
stance ink, a hairline shelf divider, and the chip sitting quietly at the right
edge of a two-end table row.

## E. Which mechanisms intentionally differ

**None are authored to differ, and that is a finding rather than a default.**
`.pv-added` reuses `var(--muted)` exactly as `.pv-dt` does; the fold adds no
theme-conditional rule; nothing this chip uses appears in the MPDS §12 translation
table (it is not a tinted status chip, not a glow, not an accent rail, not a
heatmap cell).

What differs is **rendered, not authored**, and this pass records three such
differences rather than waving the shared CSS through:

1. the token pair resolves to different inks against differently-derived surfaces,
   moving subordination 1.99× → 1.64× (§C/§D);
2. the card ↔ shelf depth step **reverses sign** in light on `us_stocks` (+0.0434
   vs −0.0064 dark), so the fold lands in a receding well in dark and on an
   advancing plate in light (§D, F9);
3. **light is additionally heterogeneous board-to-board in a way dark is not**:
   the same fold lands on a *recessed* shelf on CA (`#ffffff` cards, −0.0792) and
   on an *advanced* shelf on US (`#eef1f6` cards, +0.0434), while dark's step is
   −0.0064 on both. Light is the theme where "the same shelf" is not the same
   material.

Because the mechanism is shared, the argument that it works in both luminance
environments is made above from measurements (§D) rather than from the fact that
the CSS still renders once the tokens swap.

## F. Degraded states, per theme

- **Null — unchanged, and proven unchanged.** A card with no `added_date` renders
  no `.pv-added` element at all, so the shelf has nothing to wrap and
  `flex-wrap:wrap` cannot fire. Measured on `hk_stocks` (all-null) under **both**
  stylesheets, dark + light, EN + ZH at 390: shelf height **42.0 px identically**,
  `rowOverflows = false`, `valClippedByShelf = false` in every cell.
  `fold_hk_null_before_*_shelf.png` and `fold_hk_null_after_*_shelf.png` are
  pixel-comparable pairs. The markup half is proven separately and more strongly:
  `pv_card()` is byte-identical to the merge-base macro across all six
  representative non-US cx variants.
- **Folded (two-line shelf).** Fires only where the line genuinely cannot hold
  both. Measured US 390: 29.8 → **43.3 px**, chip at its full 65.6 px EN / 50.2 px
  ZH, `chipTruncated = 0`, `chipClipped = 0`, `valClippedByShelf = 0`, in all four
  theme × language cells.
- **Stacked (three-line shelf) — new, bounded, disclosed.** When the *label plus
  value* alone exceed the row, the value takes its own line too and the shelf
  reads `ZONE` / `$1111.10–$1147.20` / `Added Aug 31` (US FICO, EN only, 390:
  **59.6 px**; the ZH label is narrower and stays at 43.3 px). This is the same
  over-capacity condition that previously **hard-clipped the price** (§A) — it is
  now a legible stacked micro-block instead of a silent cut. It is the least
  elegant state this design produces and it is named as such rather than hidden.
- **Zone-value far-edge overflow (R4/`.pv-znm` extension).** Both value variants
  keep `max-width:100%` + ellipsis. Still **unexercised** on real content; no
  ellipsis screenshot exists because the state never occurred and none was
  fabricated.
- **Locked / tier-preview (US).** The chip ghosts with the rest of the card and
  leaks nothing — visible in every `fold_us_*_390_cards.png`, where only the first
  card is unghosted.
- **Tier-2 explanation.** `data-tip-en` / `data-tip-zh` and `data-added` are
  unchanged and untouched by this PR.

## G. How this evidence was made

| what | mechanism |
|---|---|
| `canada_stocks` | **REAL BUILD.** `~/.cache/mm-venv-mac-builder-3/bin/python -m scripts.build_canada`, rc=0. The built page carries the fold CSS inline. |
| `us_stocks`, `hk_stocks` | the **real committed built pages**, served locally, with only the shared pv_css asset (`site/assets/css/3f6de652.css`) swapped for the current template's `pv_css()` render. |

**Why US was not rebuilt, stated plainly.** At the time these builds ran, a
concurrent session was mid-edit on `engine/prophet_board_since.py` in this same
worktree (`git status`: ` M`); that work has since landed as
`dd033837c02e` — *"prophet_board_since: Chairman-directed acceptance lights
CN/HK/CA dates"* — which is this branch's base head. A 1 069 s
`scripts.build_site` run at that moment would have (a) rendered the US board
through a half-finished engine and (b) written across `data/` underneath that
session. The swap was used instead, and the substitution is **proved, not
asserted**:

- the real `build_canada` output's inline pv_css block is **byte-identical**
  (SHA-256 `72ed9b13…`) to `pv_css()`'s render from the template on disk; and
- the rule set injected into the US/HK pages is **rule-for-rule equal** to that
  real build's pv rules (97/97 identical).

So the US and HK crops render exactly the CSS a real US build would ship. The
board content, data, markup and every other stylesheet are the genuine built
artefacts. Reproduce with `capture_fold.py` / `measure_fold.py` next to this file.

Theme and language use the site's own `theme` / `lang` `localStorage` mechanism
and every cell asserts the resulting `data-theme` / `data-lang` before shooting.
Captures are anonymous, so the US tier-preview ghost is active — the honest
anonymous state, as in the original pass.

**One CA note, disclosed.** The rebuilt CA board renders **5 chips** where the
pre-`dd033837c02e` tree rendered 0 (the §2 table above, "CA went 10/10 → 0/10").
That change is `dd033837c02e`'s, not this PR's — it is the sibling engine work
lighting CN/HK/CA dates, and it is now part of this branch's base rather than an
uncommitted edit. The CA cells are used here as a *layout and material* receipt —
a real build carrying the fold CSS with real chips at real widths — and never as
evidence about which dates CA should stamp. It does mean the launch-state table in
§2 above is superseded for CA by `dd033837c02e`.

## H. Design judgment

### Dark — PASS
`fold_us_after_dark_en_1440_cards.png`: the desktop shelf is unchanged, one line,
`ZONE $145.50–$151.60 …… Added Aug 31`, eye order sparkline → ticker → stance →
priority → zone → chip with the chip last. `fold_us_after_dark_en_390_shelf.png`:
folded, the date whole, right-aligned under the number, the two-end table rhythm
preserved on both lines. Nothing gained a hue, a fill or a border. The null twin
(`fold_hk_null_after_dark_en_390_shelf.png`) terminates cleanly on the value with
no orphaned separator, no collapsed padding, no reserved gap.

### Light — PASS
`fold_ca_realbuild_light_en_1440_cards.png` and `fold_us_after_light_en_1440_shelf.png`
read as designed-for-light rather than translated. The two caveats are the
measured ones and both are quantified: 1.64× subordination, and the +0.0442-class
inverted card→shelf step on `us_stocks` (F9) that removes the recession cue on
that board. Neither is introduced by this PR; both are properties the fold now
sits on, so both are stated, and the fold is the one change here that could have
made them worse — measured, it does not (§D).

### EN / ZH parity — PASS at every width, which is new
This is the parity result the previous pass could not report. `入榜 08-31` is a real
translation and is narrower than the EN form (50.2 px vs 65.6 px). The 390 px
asymmetry that produced `入..` in ZH while EN vanished entirely is **gone**: both
render in full on a folded line. Compare `fold_us_before_light_zh_390_shelf.png`
(`入..`) with `fold_us_after_light_zh_390_shelf.png` (`入榜 08-31`).

### Responsive — PASS
`docW == winW` in every cell of every board, both stylesheets. Containment is
achieved by folding the metadata, never by degrading the price:
`valClippedByShelf = 0` and `chipTruncated = 0` in all 24 post-fold cells.

### Density budget — PASS
Desktop cost is **zero**: swept 680 → 1600 px in both languages, the shelf stays
29.8 px and no card folds. Chip-less cards are unchanged at every width and in
every theme. The only height cost is +13.5 px on a chip-carrying card at the 2-up
phone grid, where the alternative is a date the reader cannot read.

## I. Findings

- **F11 — NEW, fixed here.** `.pv-zn`'s `overflow:hidden` was clipping the zone
  **price** on the widest US card at 390 px in EN (`valClippedByShelf` true for
  FICO, both themes). F1's `valuesClipped` probe measured only each element's own
  overflow and could not see a child clipped by its parent's box. Now 0 everywhere.
- **F12 — NEW, open, bounded.** The three-line stacked shelf (§F). Cosmetic, EN-only
  on today's data, phone-only, and strictly better than the clip it replaces. Not
  fixable in CSS alone without a wrapper element, which would break `pv_card()`'s
  byte-identity guarantee — deliberately not attempted in this packet.
- **F1a — CLOSED.** "Below the width where the chip can say anything, ellipsizing it
  is worse than hiding it. The priority is now correct; the form is unfinished."
  The form is now finished, in the third direction: neither ellipsize nor hide —
  fold.
- **F9 — carried, re-measured, unchanged** (+0.0434 on `us_stocks` light). Now with
  the added observation that light, unlike dark, is heterogeneous board-to-board
  (§E.3).
- **F3 / F4 / F5 / F6 / F7 / F8 — carried unchanged.** This packet changes layout
  behaviour only; it does not touch which boards can stamp a date, the meaning of
  the null, or the tip's keyboard reachability.

## J. Screenshot index (56 PNGs, all `fold_*`)

| family | cells | files |
|---|---|---|
| `fold_us_before_*` | dark/light × EN/ZH × 1440/390 | `_cards` + `_shelf` (16) |
| `fold_us_after_*` | dark/light × EN/ZH × 1440/390 | `_cards` + `_shelf` (16) |
| `fold_ca_realbuild_*` | dark/light × EN/ZH × 1440/390 | `_cards` + `_shelf` (16) |
| `fold_hk_null_{before,after}_*` | dark/light × EN/ZH × 390 | `_shelf` (8) |

Machine receipts: `fold_measurements.json` (every cell's per-card geometry,
clipping flags and computed inks) and `fold_theme_measurements.txt` (the §C/§D
luminance and contrast table). Tooling: `capture_fold.py`, `measure_fold.py`.

## K. Gaps

- **US was not rebuilt** (§G) — mechanism disclosed and the CSS substitution proved
  byte-equal to a real build's output. A US rebuild remains the stronger receipt if
  the concurrent engine work lands first.
- **The desktop `Adde…` did not reproduce in this harness** at any width
  680 → 1600 px. The arithmetic at the `minmax(246px,1fr)` floor (224.4 px needed
  vs 224 px available) explains it as a font-metric coin flip, and the fold removes
  the dependence — but the specific rendering the Chairman saw is inferred, not
  photographed.
- **F12** (three-line stacked shelf) is open by choice.
- **CN / Intl were not rebuilt or reshot.** Both are all-null today, so the fold has
  nothing to act on there; the null-identity proof on HK covers the same code path.
- **`.pv-dt + .pv-added`** (F6) still has no real-data instance; the two chips now
  have deliberately different degradation (shrink vs fold), which is stated in the
  partial and pinned by test.
