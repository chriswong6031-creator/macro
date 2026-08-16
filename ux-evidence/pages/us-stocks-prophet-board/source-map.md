# Source map — Prophet board (`/us_stocks.html`)

Generated 2026-08-16. Paths relative to repo root `macro-main`.

## Route entry

- Live URL: `https://www.mastermind-x.com/us_stocks.html`
- Generator: `scripts/build_site.py` writes `site/us_stocks.html` via

```
env.get_template("dashboard.html.j2").render(**vm, mode="stocks")
```

- Template: `templates/dashboard.html.j2` (`mode="stocks"`)
- Built artifact inspected: `site/us_stocks.html` (1.1 MB)

## Primary view

- Board panel: `#us-standouts` in `templates/dashboard.html.j2`
- Stage filter: `#us-stage-filter` buttons `data-stagepick=all|live|setting_up|ran|basing|blocked`
- Filter mechanism: CSS attribute on `#us-standouts[data-stagef=...]` hides non-matching `[data-stage]` cards (`dashboard.html.j2` ~839–849). URL does not change.
- Grid/table: `#us-st-view-toggle` / `USStockTable._setView` — table mode class `#us-standouts.st-table-mode`

## Card component

- `templates/_prophet_card.html.j2` — `.pvcard` contract (verb / Edge / stage tracker / zone / featured)
- Callers pass `cx.href` → live cards use `stock.html#TICKER`
- Hover: `transform:translateY(-2px)` + shadow, 120ms (`_prophet_card.html.j2`)

## Related data / runtime

- Board JSON island: `#us-stocktable-data` in generated `site/us_stocks.html`
- Live quotes: `templates/live.js` binds `.nb-px[data-sym]`
- Prophet live strip: `#prophet-live` (`hidden` at load), `data-universe="1596"`
- Track record dialog: `#trd-btn` / `#trd-dlg`, data `factordata/us_track_ledger.json`
- Gate/paywall helper: `templates/tier_preview.js` (`#us-standouts` → key `"prophet"`)
- Ranking / featured: `engine/us_board_rank.py` (referenced from card comments)
- Nightly board build: `scripts/build_prophet.py` (data), `scripts/build_site.py` (HTML)

## Styles / tokens

- Shared: `templates/theme.css` / generated `site/theme.css` (`--pv-buy`, `--panel2`, `--line`)
- Board-specific CSS inlined / extracted from `dashboard.html.j2` into hashed `site/assets/css/*.css`
- Card CSS macro: `_prophet_card.html.j2` `pv_css()`

## Strings / i18n

- Dual-span pattern: `<span class="l-en">` / `<span class="l-zh">` in templates
- Language: `html[data-lang=zh]` via `localStorage.lang` (set in page head script)
- No separate locale JSON for this board; copy is baked into the template

## Tests / E2E

- Visual/CSS contract helpers: `mockups/refs/breathing-platform/verify_wl1.py`, `shoot_wl1d.py`
- Engine tests exist around prophet ranking/rescue; not a browser E2E of this UI

## Evidence ID → source (board, 1440 default)

| ID | Visible | Source |
|---|---|---|
| E043 | `#us-standouts` panel | `templates/dashboard.html.j2` |
| E044 | “Prophet Stock Signals” h2 | `dashboard.html.j2` |
| E045–E047 | Grid / Table toggle | `dashboard.html.j2` + stock table JS |
| E048 | “69 shown · 77 setups…” | `#us-board-sub` |
| E049 | overnight confirmation note | `.pbs-note` |
| E050–E051 | Track record | `#trd-btn` / `#trd-dlg` |
| E3xx | `.pvcard` | `_prophet_card.html.j2` |
| stage pills | `#us-stage-filter` | `dashboard.html.j2` ~4194 |
