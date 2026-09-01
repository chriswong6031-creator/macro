# Prophet candidate "Added date" chip (`.pv-added`) — visual evidence + theme packet

PR #6719 · branch `claude/prophet-candidate-added-date-e2e-20260901`.
**Refreshed 2026-09-01 against repair commit `c14b54a0bbd6`** (all five markets rebuilt).

**Verdict: PASS.** Both blocking findings from the first pass are closed. F1 is repaired
and verified: **0 of 40 cells clip a zone price**, where before the US board clipped 3/3
and China 22/24 at 390 px. F2 was **wrong in my first pass** and is corrected below with
pixels: a board freshness date is visible in **40 of 40 cells**. Two non-blocking findings
are new or carried forward.

> **Correction notice.** The first pass reported "no visible freshness date on HK/CA".
> That was a false negative produced by my own probe, not by the product. It is retracted
> in §8/F2, with the mechanism of the error stated, because a wrong finding that reached
> the principal is worth more as a documented failure than as a silent edit.

---

## 1. How this evidence was made

Real pages, real committed data, real templates. No specimen page was authored; none of
the 195 PNGs is synthetic.

| Builder (`~/.cache/mm-venv-mac-builder-3/bin/python -m …`) | Result | Duration |
|---|---|---|
| `scripts.build_hk` | rc=0 | 68 s |
| `scripts.build_canada` | rc=0 | 82 s |
| `scripts.build_china` | rc=0 | 1345 s |
| `scripts.build_site` (US) | rc=0 | 1170 s |
| `scripts.build_intl` | rc=0 | 161 s |

The built `site/` tree was served over a local static server and driven with Chromium
(`capture.py`). Theme and language use **the site's own mechanism** — the `theme` / `lang`
`localStorage` keys `templates/theme.js` reads before first paint — and every cell asserts
the resulting `data-theme` / `data-lang` before screenshotting.

Three mechanics are load-bearing, each having previously produced a wrong result:

- These boards **mount client-side after load**; geometry is re-measured immediately
  before every screenshot and each page settles until `scrollHeight` stops moving.
- Clips are taken in **document** coordinates (`full_page=True`); a viewport-relative
  clip silently framed an entirely different panel.
- The freshness probe is **case-insensitive** and matches the *label plus a year*, not an
  ISO string — `intl.html.j2` emits a lowercase `data through`, and the shell chip renders
  `Board Aug 31, 2026`, not `2026-08-31`. A narrower matcher reports visible stamps as
  absent, which is exactly how the first-pass F2 error happened.

Capture is unauthenticated — the honest anonymous state, and the condition the F2 dispute
was about. On US that also means the tier-preview ghost is active (§6).

---

## 2. What the chip is, after the repair

```css
.pv-znr {font-weight:700;flex:none}                                  /* the PRICE: never shrinks */
.pv-added{margin-left:auto;color:var(--muted);flex:0 1 auto;min-width:0;
          overflow:hidden;text-overflow:ellipsis;font-size:9.5px;padding-left:5px}
@media (max-width:680px){ .pv-dt,.pv-added{max-width:32%} }           /* early, capped degradation */
```

`.pv-added` renders EN `Added <Mon D>` / ZH `入榜 <MM-DD>` at the right end of the zone row,
and renders **nothing** when the engine cannot prove a start date. There is still no
`html[data-theme="light"]` rule for it.

### Post-repair chip coverage (this is a large change)

| Board | zone rows | chips | distinct dates | note |
|---|---|---|---|---|
| `canada_stocks` | 10 | **10** | 5 (`08-25`…`08-31`) | full coverage; unaffected by the repair |
| `us_stocks` | 7 | **3** | 1 (`2026-08-31`) | 3 board cards, all dated |
| `hk_stocks` | 10 | **0** | — | launch-null **by design** (`HK_CA_REQUIRES_FULL_COVERAGE = {"hk": True, …}`) |
| `china_stocks` | 129 | **0** | — | was 24/129; the new dynamic coverage floor is only established by today's build |
| `intl_stocks` | 60 | **0** | — | unchanged all-null |

**Only CA and US display the chip at all today.** HK's null is the disclosed, intended
soundness floor pending a follow-up/Sol ruling. CN's fall from 24 to 0 is a side effect of
the same floor and was not flagged in the refresh commission — see §8/F7.

---

## 3. DARK TREATMENT — command centre

Unchanged by the repair. The card panel (`#1D232A`) sits above the page ground and the
zone row is cut **downward** out of it — `color-mix(--panel 55%, --bg)` → `#11141C`, darker
than the panel, so the footer reads as a recessed shelf. Nothing glows. The chip is
untinted ink on that shelf: no pill, no border, no fill.

| | ink | on `.pv-zn` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#8B93A1` 9.5 px **400** | `#11141C` | **5.93 : 1** |
| zone value `.pv-znr` | `#C8D0DC` 700 | `#11141C` | 11.80 : 1 |

Subordination **1.99×**. Clears the MPDS §14 floor (≥4.5:1 at ≤18 px) with room while
carrying half the presence of the number beside it. Because the row is *darker* than the
panel, mid-grey on it reads as a margin note — the recession does the demotion, so the chip
needs no decoration to stay quiet. Evidence: `canada_stocks_dark_en_1440_board.png`.

## 4. LIGHT TREATMENT — research workspace

The card is **pure white** (`#FFFFFF`) on a cool `#F7F8FA` canvas; the same `.pv-zn`
formula resolves to `#F5F6F9`, separated from the card by a hairline rather than a shadow.
Depth is white/grey step plus hairline; there is no bloom to translate.

| | ink | on `.pv-zn` | contrast |
|---|---|---|---|
| chip `.pv-added` | `#4C5A6C` 9.5 px **400** | `#F5F6F9` | **6.50 : 1** |
| zone value `.pv-znr` | `#2E3950` 700 | `#F5F6F9` | 10.68 : 1 |

Subordination **1.64×**.

This is the part token-substitution cannot argue for you. The identical declaration yields
a chip that is **absolutely stronger in light** (6.50 vs 5.93) and, because the value ink
also loses contrast on white (10.68 vs 11.80), **relatively louder** — 18 % less subordinate
than in dark. The mechanism still works for a reason that survives both luminance
environments: `.pv-zn` derives from `panel↔bg`, and in both themes the canvas sits further
from the card's text than the panel does, so the footer recedes either way. But the
*degree* of quiet is not preserved, and what keeps light acceptable is the 400/700 weight
step and right-edge alignment, not the colour. Evidence:
`canada_stocks_light_en_1440_board.png` beside its dark twin.

## 5. Which mechanisms intentionally differ

**None — verified, not assumed.** `.pv-added` still reuses `var(--muted)` exactly as
`.pv-dt` does; the repair changed only flex behaviour, identically in both themes, and
added no theme-conditional rule. Nothing this chip uses appears in the MPDS §12 translation
table: it is not a tinted status chip, not a glow, not an accent rail, not a heatmap cell.

What differs is **rendered, not authored**: the token pair resolves to different inks
against differently-derived surfaces, moving subordination from 1.99× to 1.64×. Recorded
here rather than waved through as "same CSS, tokens swap".

## 6. Theme-specific degraded states

- **Null.** Renders nothing — no placeholder, no dash, no reserved slot, no gap. Now the
  dominant state (HK, CN, Intl all-null): `hk_stocks_light_en_1440_board.png`,
  `hk_stocks_dark_en_1440_board.png`, `china_stocks_dark_en_1440_board.png`,
  `intl_stocks_light_en_1440_zone_null.png`.
- **Space-starved.** New post-repair state, US at 390: the chip shrinks and ellipsizes
  while the price stays whole — §8/F1.
- **Locked / tier-preview (US).** The chip ghosts with the rest of the card
  (`blur + saturate`, the light-safe treatment) and leaks nothing visually:
  `us_stocks_light_en_1440_board.png`, `us_stocks_dark_en_1440_board.png`. `data-added`
  remains in the DOM of ghosted cards — a pre-existing property of the blur-teaser idiom.
- **Tier-2 explanation.** Hover opens the LENS in all four theme × language combinations
  with plain-word copy, re-captured post-repair on CA (the only non-US board still carrying
  chips): `canada_stocks_{dark,light}_{en,zh}_1440_lens_hover.png`.

---

## 7. Design judgment

### Dark — PASS
On `canada_stocks_dark_en_1440_board.png` the eye order is sparkline → ticker → stance →
rank → zone → chip; the chip is last and reads as a margin note. Right-aligning it against
the left-aligned `ZONE` label makes the footer a two-end table row — the rhythm the removed
`.pv-dt` chip already established, so the card gains no new idiom. Type matches the card's
micro-tier (9.5 px, as `.pv-stl`). The chip takes no stance hue, so it never reads as signal.

### Light — PASS, with the §4 caveat
`canada_stocks_light_en_1440_board.png` reads as designed-for-light, not translated: white
cards on a perceptibly deeper canvas, forest-green stance ink from the light rungs, hairline
zone divider, no pastel stain where dark has depth. The caveat is the measured 1.64×
subordination — light is where this chip is closest to shouting, and any future increase in
its weight, size, or saturation must be judged in light first.

### EN / ZH parity — PASS at 1440, DEGRADED at 390 on US
`入榜 08-24` is a real translation, not a transliteration, and is narrower than the EN form.
`hk_stocks_dark_zh_390_board.png` shows the 红涨绿跌 flip intact with the chip unchanged —
correct, the chip carries no direction. The asymmetry has now **inverted**: post-repair, the
narrower ZH chip survives the squeeze far enough to render a meaningless stub, while the
wider EN chip collapses to nothing. See §8/F1a.

### Responsive — PASS, and the priority defect is fixed
`docW == winW` in **all 40 cells**: no horizontal page scroll at any viewport. Containment
is now achieved by degrading the metadata, not the price.

---

## 8. Findings

### F1 — **REPAIRED AND VERIFIED.** The price no longer clips.

The repair inverted the flex priority: `.pv-znr` is `flex:none`, `.pv-added` is
`flex:0 1 auto` with `min-width:0` + ellipsis, capped at `max-width:32%` under 680 px.

| board | 390 px | before (pass 1) | after (this pass) |
|---|---|---|---|
| `us_stocks` | prices clipped | **3 / 3** | **0 / 3** |
| `china_stocks` | prices clipped | **22 / 24** chipped | **0** (board is all-null now) |
| `canada_stocks` | prices clipped | 0 / 10 | **0 / 10** |
| **all 40 cells** | any zone value clipped (`.pv-znr` or `.pv-znm`) | — | **0** |

`.pv-znm` — the muted / re-add variant, which also carries numeric ranges and still keeps
`min-width:0` + ellipsis — was checked separately and clips **0/34** on CN and **0/3** on CA.
Not exposed in practice today, but it is the one value path the repair did not harden.

Crops: `us_stocks_dark_en_390_zonerow_zoom.png` — the exact card that previously rendered
`ZONE $...` now renders **`ZONE $145.50–$151.60` in full** (4× device scale, real card CDW).
Light twin `us_stocks_light_en_390_zonerow_zoom.png`. Board-level:
`us_stocks_{dark,light}_{en,zh}_390_zone_dated.png`. CA at 390 with the widest real zone
string on any board (`$3054.00–$3138.70`) plus a full chip:
`canada_stocks_dark_en_390_all_zone_dated.png`.

**Gate satisfied**: full zone price rendering, chip degrading.

The pre-repair crops that proved the defect (`*_zone_price_clipped_by_chip.png`, showing
`ZONE $...` and `ZONE 1…`) are **not** carried into this tree — the condition no longer
occurs, and stale "clipped" images sitting beside the fix would misread as current. They
remain in git at the first-pass commit `1e826c7ea114`, together with the pre-repair HK and
CN chipped-board cells this refresh supersedes.

### F1a — NEW, non-blocking. The chip's degradation is not graceful in ZH.

On US at 390 the chip is squeezed to a **5 px** box in EN and **22 px** in ZH (measured;
`capture_manifest.json` → `detail[].chipW`). At 5 px the EN chip renders as *nothing at all*
— clean, no artifact (`us_stocks_dark_en_390_zonerow_zoom.png`). At 22 px the ZH chip
renders **`入..`** — a truncated single CJK character plus ellipsis, which carries no
information and reads as a rendering bug
(`us_stocks_light_zh_390_zonerow_zoom.png`, 4× zoom).

The trade is now correct in priority but unfinished in form: below the width where the chip
can say anything, ellipsizing it is worse than hiding it. Not redesigned here.

### F2 — **RETRACTED AND CORRECTED. A freshness date IS visible.**

**Answer, unambiguously: YES.** A board vintage date is visible to the anonymous reader on
every board — **40 of 40 cells**, both themes, both languages, both viewports.

| board | what the user sees | source |
|---|---|---|
| `hk_stocks` | `Board Aug 31, 2026` / `榜单 2026年8月31日` | shell header chip |
| `canada_stocks` | `Board Aug 31, 2026` / `榜单 2026年8月31日` | shell header chip |
| `us_stocks` | `Data through 2026-08-31` / `数据截至 2026-08-31` | server `.stk-status` |
| `china_stocks` | `Data through 2026-08-31` / `数据截至 2026-08-31` | server |
| `intl_stocks` | `data through 2026-09-01 · built 2026-09-01 15:08 UTC` | server page stamp |

Crops: `hk_stocks_dark_en_1440_freshness_visible.png` — `Hong Kong Stocks` with a
`Board Aug 31, 2026` pill at the right of an always-visible page header.
`canada_stocks_dark_en_1440_freshness_visible.png` — `Canada Stocks` with
`Screen · evidence accruing` · **`Board Aug 31, 2026`** · `● LIVE · Sep 1, 2026`.
Both anonymous, dark EN, 1440. The HK board shot
`hk_stocks_light_en_1440_board.png` frames the chip and the null cards together.

**Why the first pass was wrong.** My probe searched only for a `<p>` whose text contained
the literal `Data through` / `数据截至`. The HK/CA shells render a `<span>` reading
`Board Aug 31, 2026` — different element, different label, and `boardDate()` formats
`en-US` month/day/year, so even an ISO-widened matcher would have missed it. My board crop
compounded it by framing the Prophet `<section>`, whose header genuinely has no date, rather
than the page `<header>` one level up that carries the chip. Two independent narrow
assumptions producing a confident wrong answer. The repair builder's account is correct.

**What remains true:** `#standouts` computes `display:none` on HK and CA, so the PR's *new*
server `Data through` paragraph is genuinely unreachable on those two boards. It is
**redundant, not load-bearing** — the shell chip already states the same `as_of` from the
same `#stocktable-data` payload. It still renders for readers whose shell never mounts, and
it is the visible stamp on CN/US/Intl. Downgraded from BLOCKING to a note.

### F3 — Non-blocking, carried forward. US chip is a per-row constant.

All three US chips read `Added Aug 31` (1 distinct date across 3 cards). Doctrine Law 4
forbids per-row repetition of a constant — the defect the removed `date` chip was cited for.
Data-dependent, not structural; CA carries 5 distinct dates across 10 cards and does not
have this problem. `us_stocks_light_en_1440_board.png`.

### F4 — Non-blocking, now much larger. Silence is doing work the null cannot support.

`engine/prophet_board_since.py` returns `None` when membership age is unprovable — the null
means *"we cannot prove when this joined"*, not *"this is new"*. Post-repair that null is
**three of five boards entirely** (HK 0/10, CN 0/129, Intl 0/60) and the reader has no chip
and no tip to read it from. The frozen spec requires the null to render nothing, so this is
recorded, not changed; doctrine Law 5 would want a plain-word Tier-1 form plus a Tier-2
receipt if it is ever revisited.

### F5 — Non-blocking, inherited. Tier-2 reachability on touch and keyboard.

Tapping the chip opens its LENS **and** triggers the card link's Terminal launcher, which
covers it. Re-confirmed post-repair on CA (`canada_stocks_touch_tap_new.png`:
`lensShown=True terminalOverlay=True navigated=False`). The parity half — the same gesture
on the SHIPPED `.pv-mk-i` chip, which is what makes this inherited rather than introduced —
could not be re-taken on CA (no CA card renders a marks chip), so it is carried forward from
the first pass on HK: `hk_stocks_touch_tap_new.png` / `hk_stocks_touch_tap_shipped.png`,
identical outcome for both chips. Neither is focusable, so neither tip is keyboard-reachable.
The card idiom's behaviour, not this chip's; untouched by the repair.

### F6 — Note. `.pv-dt + .pv-added` remains unexercised.

No caller passes both `date` and `added_date`, so the two-chip composition still has no
real-data instance. No specimen fabricated.

### F7 — NEW, for the principal. China silently lost all 24 chips.

CN went from **24/129 chips to 0/129** in this repair round. The commission described the
soundness floor as an HK matter; CN's dynamic floor (`cn_full_coverage_since`, the earliest
`more_actionable`-tagged fossil row) is only established by *this build*, so every absence
observed before today is pre-floor and resolves to `None`. This is defensible — it is the
floor doing exactly its job — but it means the CN board will show no dates until enough
post-floor history accrues, and it removed the only board where the chip appeared at
meaningful density. Flagging because it was not in the refresh brief and it changes what
"CN chip coverage" means for anyone reading the earlier evidence.

---

## 9. Screenshot index

195 PNGs. Naming `<page>_<theme>_<lang>_<viewport>[_all]_<subject>.png`; `_all` marks the
board's own "All candidates" view, opened as a user opens it.
`capture_manifest.json` holds the per-cell machine record: card/chip counts, distinct dates,
chip↔price gap, per-class clipping (`clipByClass`), chip width and ellipsis state, computed
inks, visible `freshness` entries, `docW`/`winW`.

All 40 cells are dark **and** light × EN **and** ZH × 1440 **and** 390 — 8 per board.

| board | state | per-cell shots |
|---|---|---|
| `hk_stocks` | 10 cards, **0 chips** (launch-null) | `_board` · `_card_longest` · `_zone_null` · `_freshness_visible` |
| `canada_stocks` | 10 cards, **10 chips**, 5 dates | `_board` · `_card_longest` · `_all_zone_dated` · `_all_card_longest` · `_freshness_visible` |
| `china_stocks` | 129 cards, **0 chips** | `_board` · `_card_longest` · `_all_zone_null` · `_all_card_longest` |
| `intl_stocks` | 60 cards, **0 chips** | `_board` · `_card_longest` · `_zone_null` |
| `us_stocks` | 3 cards, **3 chips**; card 1 unlocked, 2–3 ghosted | `_board` · `_card_longest` · `_zone_dated` · `_zonerow_zoom` (390, 4×) |

**F1 verification set** — `us_stocks_{dark,light}_{en,zh}_390_zonerow_zoom.png` (4× device
scale on the real CDW card, the exact card that previously rendered `ZONE $...`).

**F2 resolution set** — `hk_stocks_dark_en_1440_freshness_visible.png`,
`canada_stocks_dark_en_1440_freshness_visible.png`, plus a `_freshness_visible` crop in
every HK/CA cell.

**Tier-2 / interaction** — `canada_stocks_{dark,light}_{en,zh}_1440_lens_hover.png` and
`canada_stocks_touch_tap_new.png` (post-repair, current). `hk_stocks_touch_tap_new.png` /
`hk_stocks_touch_tap_shipped.png` are carried forward from the first pass as the
new-vs-shipped parity pair (see F5).

### CA chip receipt (from the built page, post-repair)

`site/canada_stocks.html`, from the 82 s `scripts.build_canada` run:

```html
<span class="pv-znl"><span class="l-en">Zone</span><span class="l-zh">买区</span></span>
<span class="pv-znr">$3054.00–$3138.70</span>
<span class="pv-added" data-added="2026-08-31"
      data-tip-en="On the Prophet board continuously since this date. If the name leaves and later returns, this date resets."
      data-tip-zh="自该日起持续在 Prophet 榜上；若离榜后重新上榜，此日期将重新计算。"
  ><span class="l-en">Added Aug 31</span><span class="l-zh">入榜 08-31</span></span>
```

---

## 10. Gaps

- **CN can no longer exercise the chip at all** (F7), so the CN half of the F1 regression
  has no real-data instance left. F1 is verified on US, which was the worse case (3/3 → 0/3).
- **The touch parity pair is first-pass (HK).** CA renders no `.pv-mk-i` marks chip, so the
  new-vs-shipped comparison could not be re-taken post-repair; the LENS/link code is
  untouched by the repair commit. Tier-2 hover itself is current, on CA.
- `.pv-dt + .pv-added` (F6) still has no real-data instance.
- `.pv-znm` clips 0/37 today but retains `min-width:0` + ellipsis — untested under a longer
  future note string.
- Captures are anonymous; only US gates its board, and that gated state is captured.
