# Hong Kong · Canada · International — Dashboard Overhaul

The US ([macro#331](https://github.com/chriswong6031-creator/macro/pull/331)) and China
([macro#340](https://github.com/chriswong6031-creator/macro/pull/340)) overhauls put the deep
work in the **shared** engine (`engine/stock_score.py`): the entry-axis dilution fix, the bounded
technical confirmer tilts, the anticipation risk-shape tilt, the quality-durability fix, and the
honesty notes all fire for **every** market via `conviction_profile(rec, market)`. So overhauling
HK / Canada / International is a matter of **populating the fields** each build was missing — the
same close-only enrichment the China build received.

## Applied to all three builds
* **Rich close-only technicals** — `engine.stock_technicals.snapshot` (momentum, 52-week-high
  proximity, BBWP, HVP, RSI, MA regime) replaces the thin `engine.technicals.snapshot` (try/except
  fallback so a thin/odd series never breaks the build).
* **Volatility black hole** — `engine.vol_squeeze.assess(close)` (close-only) → the "Coiled"/Firing
  chip + the bounded squeeze tilt.
* **Forward anticipation cone** — `engine.anticipation.anticipate(close, bench=<market index>)`
  (gate hoisted once) → the risk-shape entry tilt + the favourable-cone honesty note.
* **Page chips** — the `.nb-vf`/`.nb-vchip` vol-squeeze chip + the `.nb-note` honesty notes on each
  standout card, self-contained per page (matching china.html).

## Market-specific notes
* **Hong Kong** (`build_hk_library`, `hk.html`) — HK already carries its honest structural edges
  (southbound smart-money flow + A/H value + global-beta, fused into the selection slot); this adds
  the technical/vol/cone layer on top. Benchmark: `^HSI`. 78/78 names populated.
* **Canada** (`build_canada_library`, `canada.html`) — TSX has no event feeds (residual-momentum
  prior, honestly tiered "context"); the cone + vol black hole add a risk-shape read it lacked.
  Benchmark: `^GSPTSE`. 234/234 names populated; the honesty notes fire on 36.
* **International** (`build_intl_library`, `intl.html`) — the intl board is an **alpha-led setups
  board** with no per-name Conviction profile, so the vol-squeeze chip + favourable-cone note are
  attached directly to the standout rows (a faithful equivalent of the conviction-block render); the
  per-stock JSON fields are populated so the shared tilts fire wherever a profile is computed.
  Benchmark: each name's own-market index (`^N225`/`^KS11`/`^TWII`/`^NSEI`/`^AXJO`/`^FTSE`/`^STOXX`).
  992/992 names populated.

## Honest constraints
All four ex-US markets are **close-only** per stock → no ATR/ADX/volume/Donchian/TTM-squeeze and
no single-stock options GEX. The vol black hole uses the close-only BBWP+HVP gate; GEX has no analog
outside the US (China substitutes the QVIX market vol-regime). No new validated alpha is claimed —
these are confirmers + a risk-shape read layered on each market's existing validated edge.
