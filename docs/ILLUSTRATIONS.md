# ilx / "Signal Ink" — the house illustration format

Status: **house standard** for illustrative / display-tier charting. Replaces inline
Plotly fragments on dashboard surfaces.

## The law

- **All future illustrative / display charting uses ilx.** New display panels (macro
  internals, regime context, sentiment gauges, flow tapes, drawdown fills) render
  through `lib.illus.illus()`. Do not add new Plotly fragments to dashboard pages.
- **ilx is NOT for real charting.** Interactive candle / OHLC charts, anything a user
  zooms, pans, or hovers a crosshair over, stays on the trading stack
  (`lightweight-charts`, the Terminal). ilx is a *sparkline-grade illustration*: a
  small, animated, glance-tier picture of one series (or 2-3 compared), read at the
  size it renders. No axes, no zoom, no tooltips.
- **Honesty in motion (Design Doctrine Law 5).** Settled data is drawn once and lands
  with a *static* glow — never a looping pulse that fakes liveness. An empty or too-
  short series renders an honest null (`No history yet` / `暂无历史`), never a
  fabricated chart. This is the "nulls printed" law applied to pictures.

## Why (vs Plotly)

Plotly shipped ~267 KB of inline chart fragments **plus** a 3.5 MB deferred library on
`china.html` for ten static display charts. ilx renders the same charts as ~2-4 KB of
SSR SVG + HTML each, animated by ~5 KB of shared CSS/JS, theme-aware and bilingual with
no client library. See the China conversion (`scripts/build_china.py`).

## API

```python
from lib import illus

illus(series, *, kind="line", accent=None, height=190, unit_en="", unit_zh=None,
      baseline=None, reference=None, bands=None, value_fmt="{:,.1f}",
      max_points=220, aria_en="", aria_zh=None) -> str  # HTML <figure> fragment
```

| Param | Meaning |
|---|---|
| `series` | single-series kinds: `{"dates":[iso...], "vals":[float...]}`. `kind="multi"`: a list of `{"label_en","label_zh","color","dates","vals"}` (2-3 series). |
| `kind` | `line` · `area` · `bars` · `baseline` · `drawdown` · `multi` (see gallery). |
| `accent` | any CSS color string (`"var(--info)"`, `"#c08bd8"`). Set as `color:` on the figure root; **all single-series ink uses `currentColor`**, so a theme flip / ZH swap flows through. |
| `height` | figure height in px (viewBox is 560×height, x-stretched to the container). |
| `unit_en` / `unit_zh` | end-value tag unit; emitted as paired `l-en`/`l-zh` spans. |
| `baseline` | value of the waterline. `baseline` kind splits up/down tint here; `bars` kind becomes sign-colored around it. |
| `reference` | a reference level (e.g. `100` for NBS-neutral, `10000` for ¥1T) drawn as a faint dashed rule + a muted HTML caption. |
| `bands` | list of soft zone tints: `{"hi","lo","tint","label_en","label_zh","pos"}` (`pos` = `top`/`bottom`). Used for the fear↔euphoria gauge. |
| `value_fmt` | Python format string for the end value (default `"{:,.1f}"`). |
| `max_points` | downsample threshold (default 220). |
| `aria_en` / `aria_zh` | `aria-label` text. **aria-label is plain EN only** (it is an attribute — no bilingual span markup or CI-guarded translated `title=`/`aria`). |

Returns an HTML string; never raises on bad data.

## Variant gallery

| kind | Picture | Use for |
|---|---|---|
| `line` | single ink stroke + end dot + end-value tag | most series (margin, turnover, yields, climate, construction) |
| `area` | line + gradient veil from the curve to the floor | series where magnitude-vs-floor matters |
| `bars` | staggered rising bars; **sign-colored** (`--up`/`--down`) when `baseline` set | discrete/monthly series (credit impulse, M1−M2 scissors, net-rising-cities breadth) |
| `baseline` | **the signature** — line + area dual-tinted `--up` above / `--down` below the waterline, split by two clipPaths, dashed waterline | anything read as above/below zero (southbound cumulative flow) |
| `drawdown` | 0 pinned at the top, underwater fill in `--down` downward to the curve | drawdown-from-high series (property-ETF) |
| `multi` | 2-3 overlaid lines, per-series colors, HTML end-chips naming each line (no legend box) | comparisons (growth vs inflation) |

## Animation contract

Keyed on the `.ilx-in` class (added by `illus.js` via IntersectionObserver, threshold
~0.25). In-page charts animate once; dialog charts replay on each open (the page calls
`ilxReveal(dialogEl)` after the panel entrance settles).

1. **Draw** — the ink is laid down left→right (stroke-dasharray → 0), ~950 ms
   `cubic-bezier(.33,.62,.26,1)`, 120 ms in. `--ilx-len` (computed path length) is set
   inline so the dash reveal is exact.
2. **Veil** — the gradient fill fades in *under* the ink (~600 ms, ~550 ms delay).
3. **Settle dot** — the end point lands with an overshoot
   `cubic-bezier(.34,1.28,.5,1)` and a **static** glow (no pulse).
4. **Bars** — rise from the baseline (`scaleY`), staggered
   `delay = 120ms + i*9ms`, total ≤ ~700 ms.
5. **Labels** — corners / end-tag / band / reference captions fade in after the draw.
6. `@media (prefers-reduced-motion: reduce)` → everything at final state, no transitions.

## Accent guidance

- Bind to theme vars where the semantics fit: `var(--info)` (neutral/flow),
  `var(--warn)` (heat/turnover/yields), `var(--orange)` (activity/climate),
  `var(--up)`/`var(--down)` (dual-tint kinds — **always** these two so the ZH
  red/green swap is automatic).
- A page-accent hex is fine for a *signature* series (China sentiment uses `#c08bd8`
  plum). Prefer a var when one carries the right meaning.
- The dual-tint kinds (`baseline`, `drawdown`, signed `bars`) ignore `accent` for their
  fills and use `--up`/`--down` directly — that is what makes the ZH swap flip red↔green
  with no re-render.

## Files

- `lib/illus.py` — the SSR renderer (pure stdlib, no deps).
- `templates/illus.css` + `site/illus.css` — layout + reveal choreography (byte-paired).
- `templates/illus.js` + `site/illus.js` — IntersectionObserver trigger + `ilxReveal`.
- `tests/test_illus.py` — downsampling / null / baseline-split / unique-id / multi tests.

Paired copies (`templates/` ↔ `site/`) must byte-match; `python -m
scripts.check_template_site_sync --fix` heals them.
