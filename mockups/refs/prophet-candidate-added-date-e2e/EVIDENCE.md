# Prophet candidate "Added date" chip (`.pv-added`) — visual evidence + theme packet

PR #6719 · branch `claude/prophet-candidate-added-date-e2e-20260901` · captured 2026-09-01.

**Verdict: PARTIAL.** The chip's material treatment is right in both themes and the
null state is clean everywhere. Two findings block a `PASS`, both evidenced below and
both reported rather than fixed (the chip's copy and null behaviour are FROZEN for this
pass): at 390 px the chip truncates the buy-zone price it sits beside — **3 of 3 US
cards and 22 of 24 chipped China cards** — and the PR's new "Data through" board
header **does not render on any shipped board**.

---

## 1. How this evidence was made

Real pages, real committed data, real templates. No specimen page was authored, and
none of the 164 PNGs below is synthetic.

| Builder | Result | Duration |
|---|---|---|
| `~/.cache/mm-venv-mac-builder-3/bin/python -m scripts.build_hk` | rc=0 | 101 s |
| `… -m scripts.build_canada` | rc=0 | 83 s |
| `… -m scripts.build_intl` | rc=0 | 191 s |
| `… -m scripts.build_china` | rc=0 | 1466 s |
| `… -m scripts.build_site` (US) | rc=0 | 1278 s |

The built `site/` tree was served over a local static server and driven with Chromium
(`capture.py`, committed here). Theme and language are exercised through **the site's
own mechanism** — the `theme` / `lang` `localStorage` keys that `templates/theme.js`
reads before first paint — and every cell asserts the resulting `data-theme` /
`data-lang` before it screenshots, so no cell can be silently mislabelled.

Two mechanics are worth stating because they invalidated an earlier pass:

- These boards **mount client-side after load**. Geometry is re-measured immediately
  before every screenshot, and each page is settled until `scrollHeight` stops moving.
- The screenshot clip is taken in **document** coordinates (`full_page=True`). A
  viewport-relative clip framed an entirely different panel and looked plausible.

The Prophet board on every market is the `*_stocks.html` "Stock Dashboard" nav
destination (`templates/_navlinks.html.j2`), not the market overview page — the
overview pages carry no `pv_card` at all.

Capture was unauthenticated, which is the honest anonymous state: on US that means the
tier-preview ghost is active and is itself part of the evidence (§8).

---

## 2. What the chip is

```
.pv-dt   {margin-left:auto;color:var(--muted);flex:none;font-size:9.5px;padding-left:5px}
.pv-added{margin-left:auto;color:var(--muted);flex:none;font-size:9.5px;padding-left:5px}
```

`.pv-added` is a byte-for-byte twin of the shipped `.pv-dt` chip apart from its class
name. It renders EN `Added <Mon D>` / ZH `入榜 <MM-DD>` at the right end of the card's
zone row, and renders **nothing at all** when the engine cannot prove a start date
(`engine/prophet_board_since.py` returns `None` on left-censored history). There is no
`html[data-theme="light"]` rule for either class anywhere in `templates/`.

---

## 3. DARK TREATMENT — command centre

Dark is a luminance-depth composition: the card panel (`#1D232A`) sits above the page
ground, and the zone row is cut **downward** out of it — `color-mix(--panel 55%, --bg)`
resolves to `#11141C`, darker than the panel, so the footer reads as a recessed shelf.
Nothing glows. The chip is untinted ink on that shelf: no pill, no border, no fill.

Measured on the live page (`*_dark_en_1440_board.png`):

| | ink | on `.pv-zn` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#8B93A1` 9.5 px **400** | `#11141C` | **5.93 : 1** |
| zone value `.pv-znr` | `#C8D0DC` 700 | `#11141C` | 11.80 : 1 |

Subordination ratio **1.99×**. The chip clears the MPDS §14 floor (≥4.5:1 at ≤18 px)
with room, while carrying half the presence of the number beside it. Weight does most
of the work: 400 against 700 separates the two even before colour.

The dark shelf is the correct home for this chip. Because the row is *darker* than the
panel, a mid-grey printed on it reads as a margin note rather than as content — the
recession is doing the demotion, so the chip needed no decoration to be quiet.

## 4. LIGHT TREATMENT — research workspace

Light inverts the material logic rather than the values. The card is **pure white**
(`#FFFFFF`) on a cool `#F7F8FA` canvas, and the zone row is now a *tint step upward in
value but downward in purity* — `#F5F6F9`, the same formula resolving to a faintly
cool grey that is separated from the card by a hairline, not by a shadow. Depth comes
from the hairline plus the white/grey step; there is no bloom to translate.

| | ink | on `.pv-zn` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#4C5A6C` 9.5 px **400** | `#F5F6F9` | **6.50 : 1** |
| zone value `.pv-znr` | `#2E3950` 700 | `#F5F6F9` | 10.68 : 1 |

Subordination ratio **1.64×**.

This is the part a token swap cannot argue for you. The same declaration produces a
chip that is **absolutely stronger in light** (6.50 vs 5.93) and, because the value ink
also loses contrast on white (10.68 vs 11.80), **relatively louder** — the chip is 18 %
less subordinate in light than in dark. The mechanism still works, and it works for a
reason that survives both luminance environments: `.pv-zn` derives from `panel↔bg`, and
in both themes the canvas is further from the card's text than the panel is, so the
footer recedes either way. But the *degree* of quiet is not preserved, and the reason
light stays acceptable is the 400/700 weight step and the right-edge alignment, not the
colour. Evidence: `hk_stocks_light_en_1440_board.png` beside
`hk_stocks_dark_en_1440_board.png`.

## 5. Which mechanisms intentionally differ

**None — and that claim is verified, not assumed.** `.pv-added` reuses `var(--muted)`
exactly as `.pv-dt` does; there is no light-specific override for either class, and no
tint, border, shadow, or glow that would need a light counterpart. The MPDS §12
translation table lists nothing this chip uses: it is not a tinted status chip, not a
glow, not an accent rail, not a heatmap cell.

What differs is **rendered, not authored**: the token pair resolves to different inks
against differently-derived surfaces, moving the subordination ratio from 1.99× to
1.64× (§3/§4). That is a real theme-direction consequence and it is recorded here
rather than waved through as "same CSS, tokens swap".

## 6. Theme-specific degraded states

- **Null (no provable start date).** Renders nothing: no placeholder, no dash, no
  reserved slot, no residual gap. Identical in both themes.
  Dark: `hk_stocks_dark_en_1440_all_zone_dated_vs_null.png` — `RE-ADD 50.49–50.56` and
  `ZONE 0.92` both simply end. Light twin:
  `hk_stocks_light_en_1440_all_zone_dated_vs_null.png`.
  Board-scale null: `china_stocks_dark_en_1440_board.png` (five consecutive
  chip-less cards), `intl_stocks_light_en_1440_zone_null.png` (three consecutive
  `Momentum screen — no entry zone` rows, no artifact).
- **Locked / tier-preview (US only).** The chip ghosts with the rest of the card
  (`blur + saturate`, the light-safe treatment — not a smudge) and leaks nothing
  visually. `us_stocks_light_en_1440_board.png`, `us_stocks_dark_en_1440_board.png`.
  Note: `data-added` remains in the DOM of ghosted cards, which is a pre-existing
  property of the blur-teaser idiom, not of this chip.
- **Tier-2 explanation.** Hover opens the LENS popover in all four theme × language
  combinations with plain-word copy and no jargon
  (`hk_stocks_{dark,light}_{en,zh}_1440_lens_hover.png`).

---

## 7. Design judgment

### Dark — PASS as a design

Hierarchy is correct and the chip does not compete. On
`hk_stocks_dark_en_1440_board.png` the eye order is sparkline → ticker → `BUY` →
priority → zone → chip; the chip is last and reads as a margin note. Right-aligning it
against the left-aligned `ZONE` label turns the footer into a two-end table row, which
is the same rhythm the removed `.pv-dt` chip established, so the card gains no new
idiom. Type is consistent with the card's own micro-tier (9.5 px, matching `.pv-stl`).
Semantic colour is respected: the chip takes no stance hue, so it never reads as
signal.

### Light — PASS as a design, with the caveat in §4

`hk_stocks_light_en_1440_board.png` reads as designed-for-light, not translated: white
cards on a perceptibly deeper canvas, forest-green stance ink from the light rungs,
hairline zone divider, no pastel stain where dark has depth. The chip's slate grey sits
correctly inside that palette. The caveat is the measured 1.64× subordination — light
is the theme where this chip is closest to shouting, and any future increase in its
weight, size, or saturation should be judged in light first.

### EN / ZH parity — PASS

`入榜 08-24` is a real translation ("entered the board"), not a transliteration, and it
is *narrower* than the EN form, so ZH is the easier layout in every cell.
`hk_stocks_dark_zh_390_board.png` shows the 红涨绿跌 flip intact with the chip unchanged
— correct, since the chip carries no direction. ZH LENS copy is equally plain
(`hk_stocks_light_zh_1440_lens_hover.png`). One asymmetry, and it is not cosmetic: at
390 px the wider EN chip truncates more of the zone price than the ZH chip does
(`us_stocks_dark_en_390_zone_price_clipped_by_chip.png` shows `ZONE $...`;
`us_stocks_light_zh_390_zone_price_clipped_by_chip.png` still shows `$145.50…`). EN is
the worse case — see §8.

### Responsive — PASS on containment, FAIL on priority

`docW == winW` in all 40 cells: **no horizontal page scroll at any viewport**. The zone
row never wraps and the card never overflows. But containment is achieved by
truncating the wrong element — §8.

---

## 8. Findings for the principal

### F1 — BLOCKING. At 390 px the chip truncates the buy-zone price.

`.pv-added` is `flex:none`; `.pv-znr` carries `min-width:0` + `text-overflow:ellipsis`.
When the row runs out of room the **price** yields and the metadata survives. Measured
on the live boards, with a clean within-page control:

| board | 390 px min gap chip↔price | chipped cards with clipped price | un-chipped cards with clipped price |
|---|---|---|---|
| `us_stocks` | 5 px | **3 / 3** | — (no un-chipped cards) |
| `china_stocks` | 5 px | **22 / 24** | **0 / 105** |
| `canada_stocks` | 58 px | 0 / 10 | — |
| `hk_stocks` | 106 px | 0 / 8 | 0 / 2 |

The China row is the proof: same page, same viewport, same instant — every clipped
price belongs to a card that has a chip, and not one of the 105 chip-less cards clips.

Crops:
- `us_stocks_dark_en_390_zone_price_clipped_by_chip.png` — the entire zone reads
  **`ZONE $...`** while `Added Aug 31` renders in full. This is the whole US board.
- `china_stocks_dark_en_390_all_zone_price_clipped_by_chip.png` — a chipped card
  showing `ZONE 1…  Added Aug 31` directly beside an un-chipped card showing
  `ZONE 31.72–32.31` in full.
- Light twins: `us_stocks_light_en_390_…`, `china_stocks_light_en_390_all_…`.

Both themes, both languages. The buy zone is the one number on this card that decides
what a user does today; quiet metadata is outranking it. Per the frozen constraints I
have not redesigned it — but flex priority is the mechanism to look at, not the copy.

At 1440 px US already sits at a 15 px gap (EN), so this is not exclusively a mobile
problem; it is a US-board problem that mobile makes total.

### F2 — BLOCKING. The new "Data through" board header renders on no shipped board.

The PR adds a board-level vintage stamp to HK, CA and Intl to replace the removed
per-card `date` chip. Across all 40 captured cells, **not one** contains a visible
"Data through" stamp above the board.

Cause, measured: HK and CA hand their cards to a client shell (`#hk-v37-prophet` /
`#ca-v36-prophet`), which empties the legacy `#standouts` panel and sets it to
`display:none`. The cards carry the chip with them; the new `<p>` stays behind in the
hidden panel. On HK the stamp exists in the HTML as `Data through 2026-08-31` and
computes `display:none`. Intl renders nothing at all, because the stamp is guarded on
`setups.as_of`, which is null upstream — that guard is honest, but the result is the
same absence.

Net effect on HK and CA: the board previously showed a date in the zone row and now
shows none, and the replacement disclosure is unreachable. The visible board headers
say only `PROPHET · 4 shown · 10 on board`
(`hk_stocks_dark_en_1440_board.png`, `canada_stocks_light_en_1440_board.png`).

### F3 — NON-BLOCKING. On the US board today the chip is a per-row constant.

Distinct dates per board: HK 6 across 8 chips, CA 5 across 10, CN 3 across 24, **US 1
across 3** (all `2026-08-31`). Doctrine Law 4 forbids "per-row repetition of a
constant" — the exact defect the removed `date` chip was cited for. This is
data-dependent, not structural, and it will resolve as the US board ages; but today the
US board pays the F1 truncation to print the same date three times.
`us_stocks_light_en_1440_board.png`.

### F4 — NON-BLOCKING. Silence is doing work the null cannot support.

`engine/prophet_board_since.py` returns `None` when history is left-censored — the null
means *"we cannot prove when this joined"*, not *"this is new"*. With no chip and no
tip, the only reading available to a user is the wrong one. At CN's density (105 of 129
cards silent) and Intl's (all 60), silence is the dominant state and the dated cards
read as specially marked. The frozen spec requires the null to render nothing, so this
is recorded, not changed; if it is ever revisited, doctrine Law 5 wants a plain-word
Tier-1 form plus a Tier-2 receipt, and the null cards currently have neither.

### F5 — NON-BLOCKING, inherited. Tier-2 reachability on touch and keyboard.

Tapping the chip opens its LENS **and** triggers the card link's Terminal launcher,
which covers it. Tapping the shipped `.pv-mk-i` chip on the same card does exactly the
same thing — verified side by side (`hk_stocks_touch_tap_new.png`,
`hk_stocks_touch_tap_shipped.png`). Neither chip is focusable, so neither tip is
keyboard-reachable (`theme.js` LENS binds `pointerover` + `click`, no `focusin`). This
is the card idiom's behaviour, not this chip's; the chip neither introduces nor worsens
it.

### F6 — NOTE. `.pv-dt + .pv-added` is unexercised.

No caller passes both `date` and `added_date` (`_us_prophet_plan_cards` passes only
`date`; board callers pass only `added_date`), so the two-chip composition has no
real-data instance on any page. Not evidenced here; a specimen was deliberately not
fabricated for it.

---

## 9. Screenshot index

164 PNGs. Naming: `<page>_<theme>_<lang>_<viewport>[_all]_<subject>.png`, where `_all`
marks the board's own "All candidates" view — opened the way a user opens it, because
the default Top-Picks view holds only dated names on HK/CA and the null cases live in
the full board. `capture_manifest.json` carries the per-cell machine record (card
counts, chip counts, distinct dates, chip↔price gap in px, ellipsis flags, computed
inks, `docW`/`winW`).

Every cell below is dark **and** light × EN **and** ZH × 1440 **and** 390 — 8 cells per
board, 40 in total.

**`hk_stocks`** — 10 cards, 8 chips, 6 distinct dates, oldest `2026-08-10` (the older
continuing candidate), 2 nulls.
`…_board.png` · `…_card_longest.png` · `…_all_zone_dated_vs_null.png` (1440) ·
`…_all_zone_dated.png` + `…_all_zone_null.png` (390, cards stack) ·
`…_all_card_longest.png`

**`canada_stocks`** — 10 cards, 10 chips, 5 distinct dates. Widest real zone string on
any board (`$3054.00–$3138.70`).
`…_board.png` · `…_card_longest.png` · `…_all_zone_dated.png` · `…_all_card_longest.png`

**`china_stocks`** — 129 cards, 24 chips, 3 distinct dates, 105 nulls. Carries the
F1 collision crop at 390.
`…_board.png` · `…_card_longest.png` · `…_all_zone_dated.png` · `…_all_zone_null.png` ·
`…_all_zone_price_clipped_by_chip.png` (EN 390) · `…_all_card_longest.png`

**`intl_stocks`** — 60 cards, **0 chips**: the all-null market, and the correct
null-state evidence.
`…_board.png` · `…_card_longest.png` · `…_zone_null.png`

**`us_stocks`** — 3 cards, 3 chips, 1 distinct date; card 1 unlocked, cards 2–3 ghosted
tier preview.
`…_board.png` (locked shell + unlocked payload in one frame) · `…_card_longest.png` ·
`…_zone_dated.png` · `…_zone_price_clipped_by_chip.png` (390)

**Tier-2 / interaction** (HK, `capture_lens.py`)
`hk_stocks_{dark,light}_{en,zh}_1440_lens_hover.png` — LENS open, both themes, both
languages.
`hk_stocks_touch_tap_new.png` / `hk_stocks_touch_tap_shipped.png` — F5 parity receipt.

### CN chip receipt (from the built page)

`site/china_stocks.html`, produced by the 1466 s `scripts.build_china` run:

```html
<span class="pv-znl"><span class="l-en">Zone</span><span class="l-zh">买区</span></span>
<span class="pv-znr">16.70–17.20</span>
<span class="pv-added" data-added="2026-08-31"
      data-tip-en="On the Prophet board continuously since this date. If the name leaves and later returns, this date resets."
      data-tip-zh="自该日起持续在 Prophet 榜上；若离榜后重新上榜，此日期将重新计算。"
  ><span class="l-en">Added Aug 31</span><span class="l-zh">入榜 08-31</span></span>
```

---

## 10. Gaps

- **CN ZH × 390** has no chipped card in its default view (the ZH "all candidates"
  control is not matched by the capture's expand heuristic), so that one cell has no
  collision crop. The geometry is proven for ZH by `us_stocks_*_zh_390_…` and for CN by
  the EN cell.
- **`.pv-dt + .pv-added`** (F6) has no real-data instance and is not evidenced.
- Captures are anonymous. Only US gates its board, and that gated state is captured;
  an authenticated US board would show the two ghosted cards unblurred.
