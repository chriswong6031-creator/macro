# Workflow map

Edges come from contextual/card/CTA links, not the global menu.

Atomic edges: 5769

- `W.board_card_to_detail` **OBSERVED_BROWSER** (HIGH): Board card to security analyzer. a.pvcard href=stock.html#TICKER
- `W.search_to_analyzer` **OBSERVED_SOURCE** (HIGH): Global search to owning analyzer. templates/_site_nav.html.j2 search + theme.js routes picks
- `W.detail_to_watchlist` **INFERRED** (LOW): Security analyzer to watchlist / portfolio. No contextual control from stock.html to watchlist was observed in Phase 0.1.
