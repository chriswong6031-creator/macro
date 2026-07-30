# `mockups/refs/prophet_live/` — Prophet Live P1 reference mockups

Committed look-reference for the P1 us_stocks surfaces. **Spec:
`research/PROPHET_LIVE_P1_DESIGN_SPEC.md`** — that document is what the builder implements;
these files are what it must end up looking like.

| File | What it is |
|---|---|
| `strip.html` | The mockup itself. Self-contained: theme tokens copied verbatim from `templates/theme.css`, strip CSS verbatim from spec §3, prophet-card CSS verbatim from `_prophet_card.html.j2`'s `pv_css()` plus the new `.pv-live` chip (spec §5.3). **This file, not the PNGs, is the authoritative reference** — it carries the exact CSS. |
| `build_refs.py` | Playwright shot harness for the MOCKUP. `python3 mockups/refs/prophet_live/build_refs.py`. Also prints the height-invariance proof. |
| `shots/*.png` | 2× crops of the mockup: `{specimen}_{theme}_{lang}.png`, plus `_mobile_` at 375px. |
| **`verify_p1.py`** | **Acceptance harness for the SHIPPED build** (added with the P1 PR). Renders the real `dashboard.html.j2` with the real `us_standouts.json`, serves `site/` over loopback so the page's own `fetch('live/prophet_live.json')` resolves, freezes the ET clock per specimen, and drives the production JS path. Prints the five proofs and exits non-zero on any failure, so it doubles as a pre-push gate. |
| `p1_shots/*.png` | 2× crops from `verify_p1.py` — the shipped surface, not the mockup. Includes `strip_closed` and `strip_overflow`, which the mockup has no specimen for. |

## Which numbers to trust

The mockup's height numbers (231.25 / 233.25 / 284.34px) do **not** carry over: the real
page inherits `line-height:1.5` where the mockup inherited `normal`, so a baseline-aligned
row measures 26.06px there against 24.5px here. The shipped build therefore pins the row
height and derives the body reservation from it (`--plv-rh`), and the production numbers are
**243.25px** at 1180px (en and zh) and **336.34px** at 375px. `verify_p1.py` is the source
of truth for the shipped surface; re-run it, never quote the mockup.

## Specimens

| `data-shot` | Shows |
|---|---|
| `strip_live` | 2 forming + 1 holding-into-close, 15:41 ET (the brief's headline case) |
| `strip_faded` | 1 forming + `ran past` + `fell back` + the `+1 more` overflow button — the two `via` stories side by side, which must never share a word |
| `strip_quiet` | quiet tape: live, nothing crossing. The rail is the proof of life |
| `strip_dark` | data dark (`stale_pack`): rail greyed, cause named in plain words, board unaffected |
| `cards` | board panel with `◐ Below range` on a **Buy** card next to the nightly `⚡` (the hue exception, spec §5.1), `◐ Holding into close` on a Near card, and an untouched control card proving the reserved slot adds nothing |

Data is production-shaped: board rows (TPR / FAST / LEA, prices, zones, sectors, dates) come
from `site/factordata/us_standouts.json` `as_of 2026-07-28`. The strip's cross names
(ONTO / MLI / CRS) are real scored-universe names that are deliberately **not** on that
board — which is exactly what the strip exists to surface.

## Height invariance (spec §6.4 rule 1)

Measured on this mockup across all four modes (live / faded+overflow / quiet / dark):

| Width | Language | Height, every mode |
|---|---|---|
| 1180px | en | **231.25px** |
| 1180px | zh | **233.25px** |
| 375px | en | **284.34px** |

Three separate CSS rules earn that, and **each was added after a measurement caught it
failing** — the first draft was off by 10.5px (row height guessed at 21px, actually 24.5px),
then 2.5px (a short token shrank a wrapped header line), then 21px on mobile (the `+N more`
button jumped to a third header line the moment a 4th row appeared). Re-measure after any
change to the chip box, the header, or the row grid; do not take the number on trust.

## Rasterizer caveats in these PNGs

The PNGs in `shots/` were produced in an environment where Playwright and the Chrome CLI
could not launch, via `foreignObject` → canvas in the Browser pane. Two artifacts are
present in the committed crops and are **not** design decisions:

1. **Card sparklines are missing.** Nested `<svg>` inside `foreignObject` does not
   rasterize. The live browser render draws them normally.
2. **Crops narrower than 680px collapse chips to the bare `◐` glyph**, because the media
   query resolves against the crop width. This is why only panel-width crops are committed;
   per-card crops taken in isolation misrepresent the desktop design.

Re-running `build_refs.py` on any host with a working browser produces clean crops without
either artifact. The acceptance crops for the build PR (spec §7) come from the real page via
Playwright, not from this harness.
