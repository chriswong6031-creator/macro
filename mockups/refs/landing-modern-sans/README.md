# Landing display type — Outfit

Operator, 2026-07-26: *"Update fonts on front page to utilize modern fonts. We're a
modern SaaS company. We should be using fonts like Poppins, San Francisco etc. that are
very modern and bold. A previous session pushed an update … that changed the fonts to
this weird serif font."*

The landing and the onboarding sheet now set **one** display face — **Outfit**, a
geometric sans — across every headline, every piece of chrome, and every figure. Body
copy stays **Inter**. Two faces were retired: **Archivo Expanded** (words) and
**Newsreader** (figures).

Open `beforeafter.html` for the side-by-side and `specimen.html` for the full head-to-head
at the page's real sizes. Both are dev-only and pull the retired faces from the Google
Fonts CDN — that is the only place they still exist — while loading Outfit from the real
shipped subset.

---

## What the previous change (#3655) got right, and what it missed

#3655 replaced Archivo Expanded's numerals with Newsreader ExtraBold because the operator
called them "kinda squashed". **The diagnosis was correct and the measurement holds**:
Archivo at `wdth 125` / weight 800 is wide *and* heavy, so its counters close up and its
figures set 21–35% wider than the alternatives at the same height.

The prescription is what missed. It read "more beautiful" as "serif", which:

- **left the cause in place.** The squashing came from an *expanded-width poster
  grotesque*. #3655 treated eight numerals and left that face on 105 other rules — every
  headline, the wordmark, and all the card chrome — so the thing actually producing the
  problem never moved.
- **split the page into two voices.** Grotesque words, editorial-serif figures, nothing
  tying them together. In situ the gauge score read like a magazine pull-quote dropped
  into a product UI.
- **pointed at the wrong category.** Editorial serif figures signal FT/Economist print.
  A market-intelligence SaaS product sits in the Linear/Stripe register.

Fixing the display face fixes the numerals *and* the headlines, and needs no second voice
to do it. That is the whole change.

---

## The measurements that decided it

Canvas/DOM measurement at the page's real sizes, EN, Chrome. `specimen.html` regenerates
the whole table live.

| Face | digit spread @48/800 | `tnum` fixes it? | `96,412` @26px | one variable file? |
|---|---|---|---|---|
| Archivo Expanded 800 *(retired)* | 0.04px — tabular | n/a | **89.6px** | yes, wght+wdth |
| Newsreader 800 *(retired)* | 0.00px — tabular | n/a | 92.3px | yes, wght+opsz |
| **Outfit 800 — shipped** | 13.50px | **yes → 0.00px** | **77.0px** | **yes, wght 100–900** |
| Poppins 800 | 14.59px | **NO — no `tnum` feature** | 83.3px | no — static weights |
| Plus Jakarta Sans 800 | 13.78px | yes → 0.00px | 84.4px | yes, wght 200–800 |
| Manrope 800 | 10.56px | yes → 0.00px | 84.1px | yes, wght 200–800 |
| Inter 800 | 12.03px | yes → 0.00px | 87.6px | already self-hosted |

**Poppins was named by the operator and is disqualified by measurement.** It ships no
`tnum` feature at all, so `font-variant-numeric:tabular-nums` is a **no-op** on it — the
digit spread stays 14.59px. The landing's gauge score counts up on load and every plan
card is a column of prices; on Poppins the score would visibly jitter and the columns
would go ragged, with no CSS able to fix it. It is also static-weight only, so the seven
weights the page drives (400/500/600/650/700/800/900) would mean ~7 files against
Outfit's one, and the interpolated 650 would be unavailable at any price.

**San Francisco cannot be shipped as a webfont.** Apple licenses it for use on Apple
platforms only; there is no self-hostable file. It survives in the stack as the
`system-ui, -apple-system` tier, where Apple devices get it for free and everyone else
falls to Segoe/Roboto — which is exactly where a display face must *not* be decided.
Inter is the libre face designed as an SF-alike, and it is already the body face here, so
that half of the brief was already satisfied.

**Why Outfit over Jakarta / Manrope / Inter.** It is the geometric register the operator
named (Poppins' family, not Poppins' engineering); it is the narrowest of the field, so it
answers the original "squashed" complaint by 14% against Archivo Expanded rather than
merely not making it worse; one 41.5KB file covers wght 100–900; and it carries a
double-storey `a`, which keeps it credible on a finance product where Poppins'
single-storey geometric `a` reads consumer. Jakarta sets punctuation on generous
sidebearings, which detaches the comma and the closing period in a 44px hero that has
both. Inter is the safe pick and the templated one — it would have left the page with no
display voice at all.

---

## Two properties this face depends on

**1. Figures are tabular BY DEFAULT, baked into the subset.** Outfit's stock figures are
proportional; Archivo's were tabular. Nothing in the CSS ever asked for tabular figures
because it never had to — so a plain swap would have silently started the gauge score
jittering and misaligned every price column. `build_outfit_subset.py` remaps the digit
codepoints onto Outfit's own `tnum` glyphs, so all ten share one advance (590 units) with
no CSS involvement. This is deliberately *not* solved with `font-variant-numeric` on ~80
rules: that can be forgotten on the one rule that matters. `pnum` still maps back to
proportional if it is ever wanted.

**2. The `wght` axis must stay a RANGE.** Five rules ask for the interpolated 650 — `.stg`
on the landing, and `.obm-cmp-cell` / `.obm-step-lbl` / `.obm-mini-lbl span` /
`.obm-sum-list li b` in the sheet. A static instance flattens all five to the nearest
shipped weight, silently. `instantiateVariableFont` is therefore passed a **tuple**
`{'wght': (400, 900)}` — partial instancing. A scalar would pin the axis.

Outfit has **no `wdth` and no `opsz` axis**, unlike both retired faces. All 16
`font-stretch:125%` declarations (7 in `landing.css`, 9 in `onboard.css`) and all 9
`font-variation-settings:'opsz' N` (6 + 3) are therefore deleted rather than left as dead
code — such declarations do not error, they are simply ignored, so the only symptom would
be type quietly rendering at the wrong width.
`tests/test_check_font_ui_defined.py::test_no_rule_asks_the_display_face_for_an_axis_it_lacks`
holds that line across `index.html`, `landing.css` and `onboard.css`.

---

## Regenerating the font

```bash
python3 mockups/refs/landing-modern-sans/build_outfit_subset.py
```

Writes `templates/fonts/Outfit-latin.woff2` and mirrors it to `site/fonts/` (both tracked;
`site/fonts/` is what ships). Requires `fonttools[woff]`, which is **not** a CI dependency
— see the note on the digest pin below.

The build is **reproducible**. fontTools stamps `head.modified` at save time, so before
this was pinned, three runs over identical input produced 41,480 / 41,568 / 41,652 bytes.
The script zeroes `head.created`/`head.modified` *and* sets `SOURCE_DATE_EPOCH=0` in
`os.environ` before fontTools is imported — the subsetter runs as a subprocess and re-saves
the font, so setting it only for that subprocess is not enough. Current output:

```
41,540 bytes   sha256 1cf8df7d11d7fcfb97779d2ea3f2aea3a54ee7e2ca82da50e88ab5ac6745593d
```

That digest is **pinned in `tests/test_check_font_ui_defined.py`**. It is the only
zero-dependency way to guard the tabular-figures property: the CI packs install minimal dep
sets (`pip install pytest pandas numpy`, etc.) rather than `requirements.txt`, so a
`pytest.importorskip("fontTools")` here would be a permanent silent skip rather than a
test. Rebuilt the font on purpose? Re-run the script — it asserts the ten advances are
still equal — and update the digest in the same commit.

**The subset range mirrors the retired Archivo file exactly.** Keeping the boundary
identical means the swap changes the display face and nothing else: `→ ⓘ ⚡ ✓ ✗` and all CJK
fall through to the system stack now just as they did before, so no symbol on the page
silently changes shape. `unicode-range` mirrors the subset, which is what keeps a bilingual
element from rendering CJK as tofu when it inherits this Latin-only face.

---

## Where the face is declared

Since **#3676** lifted the landing's inline CSS out of `index.html`, the type system spans
three files:

| File | Carries |
|---|---|
| `templates/onboard.css` | the Outfit `@font-face`, plus `--display` / `--fig`, plus the sheet's own display rules |
| `templates/landing.css` | `--display` / `--fig` again, the six Inter `@font-face` blocks, and all 69 landing display rules |
| `templates/index.html` | the `<link rel=preload>` for the font, both stamped `<link>`s, and one inline SVG that names the face directly (an SVG presentation attribute cannot read a CSS var) |

`@font-face` lives in **`onboard.css`**, not `landing.css`: that sheet is lazy-injected onto
macro pages carrying none of the landing's CSS (`theme.js _mmOpenOnboard` → `onboard.js
ensureAssets`), so it has to be the one to carry the face, and declaring it in a stylesheet
makes `url()` resolve relative to the sheet — correct at any page depth.

`--display` and `--fig` are declared in **both** `landing.css` and `onboard.css`, so neither
depends on the other's cascade. `--fig` is kept as an alias of `--display` rather than
removed: the eight figure rules using it are the ones most likely to be re-pointed at a
dedicated numeral face again, and an alias beats a find-and-replace.

All of these are **paired plain-copy assets** — each `templates/<name>` must byte-match
`site/<name>`. After any edit:

```bash
python -m scripts.check_template_site_sync --fix
```

...then **re-cut BOTH `?v=` stamps in BOTH `index.html` copies**, because the Caddyfile
serves versioned assets `immutable/max-age=1y` and a stale stamp pins returning visitors to
a stylesheet with no `@font-face` at all — that is exactly what happened to #3617, which sat
live at the origin while every returning browser kept the old sheet until #3624 hand-bumped
it. Currently `onboard.css?v=3dfad6b6` and `landing.css?v=82a676bb`, both enforced by
`test_landing_stylesheet_cache_stamps_are_current`. That test is parametrized over both
sheets because #3676 gave the page a second stamped stylesheet and left it unguarded.

⚠️ **Careful with `--fix` if the pair is stale on the templates/ side.** It heals
templates → site unconditionally, so on a pair whose *template* is the outdated copy it
silently clobbers correct site bytes — including live asset stamps. Check which side is
actually current before running it.

---

## Not in scope

`scripts/make_launch_card.py` still renders marketing social cards in Archivo Expanded,
pulled from the CDN. It is an off-render-path image generator with a layout hand-tuned to
Archivo's metrics, and it is not the front page — worth aligning to Outfit as a separate
change, with the card layout re-checked against the narrower face.
