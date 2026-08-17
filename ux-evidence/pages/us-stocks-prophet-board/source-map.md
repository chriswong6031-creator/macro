# Source map — Prophet board (`/us_stocks.html`)

- Live URL: `https://www.mastermind-x.com/us_stocks.html`
- Generator: `scripts/build_site.py` → `dashboard.html.j2` `mode="stocks"` → `site/us_stocks.html`
- **Parity:** VERIFIED byte-identical to live (see `source-parity.json`)
- Cards: `templates/_prophet_card.html.j2` (`.pvcard`, verb, trigger, Priority/edge)
- Stage filter: `#us-stage-filter` + CSS `#us-standouts[data-stagef=…]`
- Table: `USStockTable._setView` / `#us-standouts.st-table-mode`
- Track record: `#trd-btn` / `#trd-dlg` / `factordata/us_track_ledger.json`
- Gate helper (not active this run): `templates/tier_preview.js`
