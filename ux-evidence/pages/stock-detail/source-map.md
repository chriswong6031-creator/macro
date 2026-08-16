# Source map — Prophet detail (`/stock.html#TICKER`)

## Route entry

- Live URL captured: `https://www.mastermind-x.com/stock.html#ONTO`
- Template: `templates/stock.html.j2` → `site/stock.html`
- Hash routing: ticker in `location.hash` (cards link `stock.html#ONTO`)
- Browser title stays generic: `Stock analyzer — cycle & momentum` (does not include ticker)

## Primary view / children

- Header identity + decision strip: `templates/stock.html.j2`
- Chart + timeframe/indicator chips: stock page scripts (`templates/stockview.js`, `templates/stockdata.js`)
- Cycle & timing disclosure: native `<details>` (“Cycle & timing detail”)
- Shared shell nav: same market mega-menu as other site pages (included from dashboard/nav partials)
- Gate/lock row exists in template (`.lock-cta`) but was **not present** on this anonymous ONTO load

## Data

- Per-name library records produced by `scripts/build_stock_library.py`
- GEX / levels comments in `build_stock_library.py` describe keys `stock.html` reads
- Visible as-of on captured page: “data through 2026-08-14”

## Styles

- `templates/theme.css`
- Large inline `<style>` in `stock.html.j2` (decision boxes, lock row, cycle box)
- `templates/stock_seasonality.css` if seasonality module present

## Strings

- Dual `l-en` / `l-zh` spans; many headings dump both languages into `innerText` when both CSS copies remain in the accessibility/text tree

## Evidence notes

- First extracted “H2” items are mega-menu column titles (United States / China / …), not page section titles
- Real page H1: “Onto Innovation (ONTO)”
