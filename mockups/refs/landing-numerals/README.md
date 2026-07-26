# Landing + onboarding numerals — the figure face

Reference for the display-figure typography on `templates/index.html` and
`templates/onboard.css`. Operator brief, 2026-07-26: *"i don't like the number fonts…
they're kinda squashed… can we try another bold font that is more beautiful than this?"*

## What shipped

Display figures — the live gold score, the proof stat, the dollar-index readout, and every
plan price — are set in **Newsreader ExtraBold (800)**. Words keep **Archivo Expanded**, so
the page now *pairs* a grotesque voice with serif figures instead of setting everything in
one face. Small inline data (tickers, percentages, price cells at 8–15px) deliberately stays
on Archivo, where a tight grotesque out-reads a serif.

Applied via a single `--fig` token, declared in both `index.html`'s `:root` and
`onboard.css` (the sheet is lazy-injected onto macro pages that have no landing CSS, so
neither file may depend on the other's cascade):

| Surface | Selector | Size / `opsz` |
|---|---|---|
| landing · live score | `.gz-num b` | 48px · 72 |
| landing · proof stat | `.fi-sum .big` | 27px · 34 |
| landing · dollar index | `.dxy .n` | 25px · 32 |
| landing · plan price | `.price` | 41px (37px mobile) · 72 / 56 |
| landing · struck price | `.price .was` | 16px · 16 |
| sheet · plan price | `.obm-plan-price` | 24px · 30 |
| sheet · struck price | `.obm-plan-price .obm-was` | 13px · 14 |
| sheet · order card | `.obm-order-price` | 21px · 26 |

## Why Archivo Expanded Black lost the figures

Archivo's black weight at `wdth 125` is both very wide and very heavy, so its counters
close up and the figures read short and blocky. Measured on `96,412` at a fixed 26px:
Archivo Expanded is **110.5px** wide against **81–92px** for every candidate below — 21–35%
wider at identical height. That ratio *is* the "squashed" complaint.

## The specimens

- `specimen.html` — round 1, seven faces across all three real contexts plus the full
  figure set, a tabular-alignment check, and the onboarding dark stage.
- `headtohead.html` — round 2, the finalists at 1:1 with a small-data survival test
  (15px / 10.5px), which is what eliminated the grotesques.

Open either through the repo-root preview server (they pull candidate faces from the Google
Fonts CDN — specimens only, never the shipped page):

```bash
python3 -m http.server 8899
```

### Round-2 verdict

| Face | Read |
|---|---|
| **Newsreader 800** ✅ | Tall, high-contrast, properly drawn bowls and tails. Holds at 10.5px *and* 48px. |
| Fraunces 800 wonk | Beautiful, but the `$` collides with the 4 and needs per-size spacing rescue. |
| Frank Ruhl Libre 900 | Close second; slightly narrower, straighter 9 tail. |
| Literata 800 | Sturdy but less refined; bad `$`/digit collision. |
| Schibsted Grotesk 800 | Cleanest grotesque, but `tnum` gives punctuation a full tabular advance — `$58.50` renders as `$58 . 50`. |
| Chivo 900 | Fine, but too close to Archivo's DNA to read as an upgrade. |
| Epilogue 800 | Tall and tight, but anonymous. |

Two properties settled it over the grotesques:

1. **Figures are fixed-width by default** — all ten digits share one advance (33.61px at
   48px/800), so the live-updating score (`#gz-score`) cannot jitter. `.tnum` is a harmless
   no-op on it.
2. **It carries an `opsz` axis**, so 13px and 48px each get their proper optical design
   rather than one drawing stretched across both.

## Regenerating `templates/fonts/Newsreader-figures.woff2`

Self-hosted for the same reason `theme.css` self-hosts Inter: `fonts.googleapis.com` is
blocked in mainland China, so a CDN face silently never arrives there. `/fonts/*` is already
allowlisted in `app/deploy/Caddyfile`, and `scripts/build_site.py` copies `templates/fonts/`
to `site/fonts/` wholesale — so the file needs no wiring beyond existing.

54KB for the whole variable family: subset to ASCII + currency/dash punctuation, with both
axes clipped to the ranges the CSS actually asks for (`wght` 600–800, `opsz` 14–72).

```bash
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' -o /tmp/nr-latin.woff2 "$(curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' 'https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,200..800' | awk '/\/\* latin \*\//{f=1} f&&/src: url\(/{gsub(/.*url\(|\).*/,"");print;exit}')"
```

```bash
python3 -c "from fontTools import ttLib; from fontTools.varLib import instancer; f=ttLib.TTFont('/tmp/nr-latin.woff2'); instancer.instantiateVariableFont(f,{'wght':(600,800),'opsz':(14,72)},inplace=True); f.flavor='woff2'; f.save('/tmp/nr-lim.woff2')"
```

```bash
pyftsubset /tmp/nr-lim.woff2 --output-file=templates/fonts/Newsreader-figures.woff2 --flavor=woff2 --unicodes='U+0020-007E,U+00A0,U+00A3,U+00A5,U+2013,U+2014,U+2018-201D,U+2212,U+20AC,U+2026' --layout-features='kern,liga,tnum,lnum,frac' --no-hinting --desubroutinize
```

The `@font-face` `unicode-range` in `onboard.css` mirrors that subset, so anything outside it
falls through to the serif stack instead of rendering as tofu. Newsreader is SIL Open Font
License 1.1 (Production Type) — subsetting and self-hosting are permitted.

**After editing `onboard.css`, re-stamp its cache-buster** in both paired copies of
`index.html` — `app/deploy/Caddyfile` serves versioned requests `immutable, max-age=1y`:

```bash
python3 -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('site/onboard.css').read_bytes()).hexdigest()[:8])"
```
