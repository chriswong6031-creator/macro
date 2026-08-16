# Workflow map (draft, Phase 0)

Observed vs inferred are separated.

- `W.board_to_detail` **OBSERVED** (HIGH): RF.us.stock_dashboard card → RF.us.stock_detail. Evidence: a.pvcard[data-ticker] href=stock.html#TICKER on us_stocks.html
- `W.search_to_detail` **OBSERVED_SOURCE** (HIGH): global nav search → stock analyzer. Evidence: templates/_site_nav.html.j2 search + theme.js routes picks to the owning analyzer
- `W.nav_geo_to_dashboard` **OBSERVED** (HIGH): geo mega-nav → market or stock dashboard. Evidence: PRIMARY_NAV hrefs in _navlinks.html.j2
- `W.detail_to_monitoring` **INFERRED** (LOW): stock detail → watchlist/portfolio. Evidence: No direct contextual control from stock.html to watchlist was exercised. Inferred only from both existing as product surfaces.
