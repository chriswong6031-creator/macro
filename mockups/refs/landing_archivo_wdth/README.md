# Landing + onboarding display face — Archivo Expanded, self-hosted

Reference for the display typography on `templates/index.html` and
`templates/onboard.css`, and the regeneration recipe for
`templates/fonts/Archivo-latin.woff2`.

The PNGs beside this file are the visual reference for the `wdth` axis work: the
hero and section titles at desktop/mobile, EN and ZH, and the onboarding sheet's
stage and steps. Every headline in them is Archivo at `font-stretch:125%` — if a
change makes those read narrower, the width axis has been lost.

## Why it is self-hosted

`fonts.googleapis.com` is blocked in mainland China. The landing used to pull
Archivo from the CDN with a `<link>` in `index.html`, and `onboard.js`
`ensureAssets()` injected the same URL when the sheet opened on a non-landing
page. Neither request completes in China, and a font that never arrives raises no
error — the page simply rendered every `.display`, `.sec-title`, `.feat-title`,
`.cov-copy h1`, `.tier h3`, `.kicker` and `.brand` in system sans. Same reasoning
as `theme.css` self-hosting Inter. `/fonts/*` is already allowlisted in all three
`app/deploy/Caddyfile` path sets and `scripts/build_site.py` copies
`templates/fonts/` to `site/fonts/` wholesale, so the file needs no new wiring.

## The axes are load-bearing — do not ship static instances

Archivo's latin variable file carries a real `wdth` axis (62–125) and `wght`
(100–900). Both must stay live:

- 21 rules across the two files set `font-stretch:125%`. Without the `wdth` axis
  there is no 125% instance to select and every headline silently renders at
  normal width.
- `font-weight:650` is used by `.stg` (index.html) — an interpolated value that
  only a live `wght` axis can produce.

`fontTools.varLib.instancer.instantiateVariableFont` with **tuple** limits does
partial instancing: it clips each axis to a range and keeps it variable. Passing
scalars instead would pin the axes and produce exactly the broken static build.

## Regenerating `templates/fonts/Archivo-latin.woff2`

**1 — fetch the upstream latin variable file** (the `wdth,wght@…` query is what
makes Google serve the two-axis variable font rather than a static instance):

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'; curl -sS -A "$UA" -o /tmp/archivo-latin.woff2 "$(curl -sS -A "$UA" 'https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62.5..125,100..900' | awk '/\/\* latin \*\//{f=1} f&&/src: url\(/{gsub(/.*url\(|\).*/,"");print;exit}')"
```

**2 — clip both axes to the ranges the CSS actually asks for**, keeping them
variable (`wght` 400–900, `wdth` 100–125):

```bash
python3 -c "from fontTools import ttLib; from fontTools.varLib import instancer; f=ttLib.TTFont('/tmp/archivo-latin.woff2'); instancer.instantiateVariableFont(f,{'wght':(400,900),'wdth':(100,125)},inplace=True); f.flavor='woff2'; f.save('/tmp/archivo-clipped.woff2')"
```

**3 — subset to latin.** Unlike the figure-only faces, this one carries WORDS, so
it keeps the whole latin range rather than narrowing to ASCII. `--layout-features='*'`
is deliberate: Archivo ships `rvrn` (Required Variation Alternates), which a
variable font needs in order to swap glyphs correctly across the axes — dropping
it breaks rendering at the extremes.

```bash
pyftsubset /tmp/archivo-clipped.woff2 --output-file=templates/fonts/Archivo-latin.woff2 --flavor=woff2 --unicodes='U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD' --layout-features='*' --no-hinting
```

Result: **57KB**, 286 glyphs, 224 codepoints, both axes live. The
`unicode-range` on the `@font-face` in `onboard.css` mirrors that subset exactly,
so CJK and anything else outside it falls through to the stack instead of tofu.
Copy the result to `site/fonts/` as well — `site/fonts/` is tracked, and both
copies belong in the same commit.

Archivo is SIL Open Font License 1.1 (Omnibus-Type); subsetting and self-hosting
are permitted.

## Verifying a regenerated file

Metric equivalence against the CDN build is the acceptance test — render the same
strings in both faces across the weight × stretch matrix and diff the widths.
When this was cut, weights 600–900 (every headline surface) matched the CDN
byte-exactly at 0.0000px across 70 comparisons; weights 400/500 differ by at most
0.45px (0.038%), which is `avar` re-segmentation from moving the `wght` floor
100→400 and is invisible at any real size.

Two things to assert, because both fail silently:

- the face actually applied — compare a probe against the same string in
  `sans-serif`; if the widths match, the webfont did not load and any
  "0 mismatches" result is vacuous;
- measure with a `Range` over the text (or an `inline-block` probe). A block-level
  headline's `getBoundingClientRect().width` is its container's width, so every
  measurement comes back identical and the comparison passes vacuously.

**After editing `onboard.css`, re-cut its cache-buster** in both paired copies of
`index.html` — `app/deploy/Caddyfile` serves versioned requests
`immutable, max-age=1y`, so a stale stamp pins returning visitors to the old CSS:

```bash
python3 -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('site/onboard.css').read_bytes()).hexdigest()[:8])"
```
