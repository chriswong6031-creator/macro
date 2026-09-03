# Flow Observatory V2 — W1 visual evidence

Captured via headless Chromium (Playwright, node_modules under the worker-browser
runtime) against `site/flow_velocity.html` served statically
(`python3 -m http.server --directory site`, `.claude/launch.json` config
`site-static`). `reducedMotion: 'reduce'` is set so the page's own
`.fv-reveal` scroll-reveal sections render immediately for a full-page capture
(matches the CSS's own `@media (prefers-reduced-motion: reduce)` fallback —
no test-only code path).

## flow_velocity.html — dark/light × EN/ZH × desktop(1440)/mobile(390)

| file | theme | lang | viewport |
|---|---|---|---|
| `fv_dark_en_1440.png` | dark | EN | 1440 |
| `fv_dark_zh_1440.png` | dark | ZH | 1440 |
| `fv_light_en_1440.png` | light | EN | 1440 |
| `fv_light_zh_1440.png` | light | ZH | 1440 |
| `fv_dark_en_390.png` | dark | EN | 390 |
| `fv_dark_zh_390.png` | dark | ZH | 390 |
| `fv_light_en_390.png` | light | EN | 390 |
| `fv_light_zh_390.png` | light | ZH | 390 |

All eight are full-page captures (Playwright `fullPage: true`, `deviceScaleFactor: 2`).
Console errors captured per file in `console_errors.json` — all eight are `[]`.
Image width in every capture equals `viewport_width * 2` exactly (2880 for desktop,
780 for mobile), which is only possible if the page never forced horizontal
overflow — confirms no horizontal page scroll at 390px.

Visible in every capture: trust strip (`#sources`, 5 source chips: A-share
large-order flow, Southbound aggregate, Northbound aggregate, HK southbound
holdings, Dragon-Tiger institutional seats), "What changed today" (`#changed`,
first-run state on this checkout — no `data/flow_observatory/state_log.jsonl`
exists yet locally), the abs×rel quadrant board (`#quadrant`) with the Autos
theme correctly placed in "still selling, pressure easing" (abs −0.9% / rel
+2.6σ — the mission's motivating defect, reproduced from real data and now
resolved), the evolved theme flow board (`#groups`, abs/rel/quadrant/rank-Δ
columns, momentum + confluence collapsed into `<details>`), and cross-border
channels (`#channels`, Southbound card showing its own quadrant chip
"still buying, pace fading").

## china_stocks.html theme-tape consumer passthrough

`china_stocks.html` itself could not be rebuilt in this checkout — `scripts/build_china.py`
raises `ModuleNotFoundError: No module named 'yfinance'` (and separately
`hmmlearn`), both pre-existing environment gaps unrelated to this change (verified:
`git status` showed no changes to `scripts/build_china.py` or its collectors before
this was hit). Rather than ship stale evidence (the last COMMITTED
`site/china_stocks.html` was built before this PR and still shows the pre-W1
vocabulary), `theme_tape_isolated_{dark,light}.png` render
`templates/_cn_theme_tape.html.j2` standalone against the REAL committed CN
artifacts (`data/baskets_china/membership.json`,
`data/china_sector_cycles/forward_log.parquet`,
`data/china_prophet_rank/candidates.parquet`) joined with the REAL rebuilt
`site/flowdata/desk.json` (this PR's `flow_observatory.v2` output). The flow
chip on every row (e.g. "Autos & NEV Makers … above norm, cooling / 高于常态·降温")
carries the new vocabulary end to end — proving the consumer-sweep passthrough
(`engine/cn_theme_tape.py` :465-466 relays `flow_en`/`flow_zh` verbatim;
`templates/_cn_theme_tape.html.j2` :364 prints it as-is) at the template layer.
`_theme_tape_isolated.html` is the source page these two screenshots were taken
from (self-documenting note banner explains the substitution). This same
passthrough is also pinned by
`tests/test_cn_theme_tape.py::test_the_rendered_flow_chip_carries_the_v2_vocabulary_verbatim`.
