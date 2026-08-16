# Topology observations (facts only)

- Prophet Stock Signals (`#us-standouts`) is a large surface inside the U.S. Stock Dashboard (`us_stocks.html`), not a standalone route.
- The U.S. security analyzer is entered through `stock.html#<ticker>` from multiple product surfaces (Prophet cards, search). Canada/Intl have sibling analyzer families.
- Navigation is geography-first (United States / China / Hong Kong / Canada / International / Other Assets) plus a Research mega-menu.
- The term “Stock Dashboard” is reused across US/China/HK/Canada/International with market-specific destinations.
- Two different numeric fields can appear as confidence-like values on the U.S. board: card “Priority” vs table `conviction_score` (see Prophet decision-data-map).
- `index.html` is the marketing landing; `start.html` is the signed-in home (brand `a.nav-brand` href).
- Options destinations other than `options.html` / `darkpool.html` / `market_structure.html` were collapsed into the options workspace (nav comments). Old URLs may still exist as redirects — record live final_url on samples.
- Thousands of generated instance pages exist under `site/stocks/` and are not separate route families.
- Strategy and fund profile HTML files are generated families, mostly source-discovered rather than primary-nav destinations.
