# Display-grid blast radius — era `display-grid-abs-session-2026-08-06`

Generated 2026-08-07T00:22Z · ruling `research/DISPLAY_GRID_ALIGNMENT_ADJUDICATION_BY_FABLE.md` (DG-R7).

Universe: `data/stocks`, 238 names, 1300-bar payload window.

## A. Client grid — the shipped surface

The payload window advances one session per night, so the retired `floor(i/3)`
grid re-phases with it. **The pooled figure may not be read without the phase
split** (DT-R16 family): on the aligned night almost nothing moves, on the other
two almost everything does.

| window phase | markers in window | on a wrong candle (today) | names | still wrong with TRIM only | names |
|---|---:|---:|---:|---:|---:|
| tonight (aligned) | 8,317 | 154 (1.9%) | 6/235 | 68 (0.8%) | 4/235 |
| −1 session | 8,319 | 8,272 (99.4%) | 233/235 | 0 (0.0%) | 0/235 |
| −2 session | 8,334 | 8,287 (99.4%) | 233/235 | 44 (0.5%) | 1/235 |

The last two columns decompose the repair honestly. **DG-R4's trim alone**
lands the window on a bucket open, and from there row arithmetic reproduces the
session grid *for a name that trades every session in its window* — which is why
the trim carries the common case. **DG-R3's `b3`** is what covers the rest: the
7 names the trim cannot reach, where no window
start can rescue row arithmetic. It also keeps the client correct without
trusting the emitter's trim. Those names, by cause:

  - **gap in window** — 2: EA, SATS
  - **short history (no row precedes the window)** — 5: CEG, GEV, HOOD, KVUE, SNDK

Worst names (phase 0): [('EA', 43), ('SATS', 43), ('HOOD', 24), ('CEG', 23), ('KVUE', 12), ('GEV', 9)]

Skipped, with reasons (no silent caps): {'no committed §7 payload': 9}

## B. Engine grid — `bar_derive`

- names probed: **238**
- 3D bucket count changed by the anchor: **238**
- 2D bucket count changed: **238**
- holiday mis-split buckets healed: **79568**
- k-drop invariance violations under the NEW grid: **0** (must be 0)

## C. Payload weight

- `b3` block: **1835 B raw**, **904 B gzipped**, against a ~50 KB payload (~7.5% of the ~12 KB gzipped file)
- DG-R4 trim distribution (rows dropped): {'0': 236, '1': 1, '2': 1}

## D. Coverage

- **ships the anchor:** site/ohlc (US), site/chinaohlc (CN), site/canadaohlc (CA), site/intlohlc (intl), site/hkohlc + hk_lookup inline (HK), site/subsectorohlc + CN concept desk
- **consumes it:** site/chart.js resample() 3D buckets, site/chart.js mapMarkers() snap-forward (exact under the shared grid)
- **not applicable:** 4H (epoch-absolute), 1W/1M (calendar-absolute)
