from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSER = (ROOT / "site" / "canada-stock-v36.js").read_text()
TEMPLATE_ICONS = (ROOT / "templates" / "dashboard-icons.js").read_text()
SITE_ICONS = (ROOT / "site" / "dashboard-icons.js").read_text()


def test_v36_is_canada_stock_page_only_progressive_enhancement():
    assert "canada_stocks\\.html$" in COMPOSER
    assert "page-canada" in COMPOSER
    assert "window.__mmCanadaStockV36" in COMPOSER
    assert "legacy page remains visible" in COMPOSER
    # Legacy panels are hidden only after the new composition mounts.
    assert "ca-v36-mounted" in COMPOSER
    assert 'document.body.classList.add("ca-v36-mounted")' in COMPOSER


def test_v36_reuses_existing_card_table_and_terminal_contracts():
    assert 'qsa(".pvcard", host)' in COMPOSER
    assert 'grid.insertBefore(card' in COMPOSER
    assert 'qs("#stocktable-wrap")' in COMPOSER
    # The composer never invents a new ticker destination; moved cards retain
    # canada_stock.html#TICKER and theme.js owns the Terminal bridge.
    assert "canada_stock.html#" not in COMPOSER
    assert "app.mastermind-x.com" not in COMPOSER


def test_v36_primary_task_language_matches_approved_reference():
    assert 'bi("Top Picks", "首选")' in COMPOSER
    assert 'bi("All Candidates", "全部候选")' in COMPOSER
    assert "Plans" not in COMPOSER
    assert "Why here" not in COMPOSER
    assert "Key caveat" not in COMPOSER
    assert COMPOSER.count('bi("Expand leadership", "展开领先排名")') == 1


def test_v36_top_picks_are_existing_board_order_not_a_new_ranker():
    assert 'card.classList.toggle("ca-v36-top-pick", i < 5)' in COMPOSER
    assert 'state.cards.slice(0, 5)' in COMPOSER
    assert "prophet_score" not in COMPOSER
    assert "conviction_score" not in COMPOSER
    assert "score_rank" not in COMPOSER


def test_v36_uses_existing_theme_and_sector_authorities():
    assert 'fetch("canadabasketdata/baskets.json"' in COMPOSER
    assert "theme_intel" in COMPOSER
    assert 'laneDefs = [' in COMPOSER
    assert '"#anv2-buy"' in COMPOSER
    assert '"#anv2-pull"' in COMPOSER
    assert '"#anv2-bot"' in COMPOSER
    assert '"#anv2-red"' in COMPOSER


def test_v36_ticker_price_and_change_are_human_scale_sf_ui():
    assert "--font-ui" in COMPOSER
    assert ".ca-v36-card-grid .pv-tk{font-family:" in COMPOSER
    assert ".ca-v36-card-grid .nb-px.pv-px" in COMPOSER
    assert ".ca-v36-card-grid .nb-chg.pv-chg" in COMPOSER
    # Canada keeps Western tape convention even if the language is Chinese.
    assert ".ca-v36 .nb-chg.up,.ca-v36-table .nb-chg.up{color:var(--ok)!important}" in COMPOSER
    assert ".ca-v36 .nb-chg.down,.ca-v36-table .nb-chg.down{color:var(--act)!important}" in COMPOSER


def test_v36_preserves_table_filters_and_adds_live_change_slots():
    assert "stf-row" in COMPOSER
    assert "stf-controls" in COMPOSER
    assert "enhanceTableQuotes" in COMPOSER
    assert 'data-mkt="ca"' in COMPOSER
    assert 'class="nb-chg' in COMPOSER


def test_v36_mobile_is_one_decision_card_wide():
    assert "@media(max-width:680px)" in COMPOSER
    assert ".ca-v36-card-grid{grid-template-columns:1fr" in COMPOSER


def test_v36_authority_and_live_status_are_not_conflated():
    assert 'bi("Screen · evidence accruing", "筛选 · 证据积累中")' in COMPOSER
    assert 'bi("Board " + boardDate.en, "榜单 " + boardDate.zh)' in COMPOSER
    assert "ca-v36-live-dot" in COMPOSER
    assert "<b>LIVE</b>" in COMPOSER


def test_canada_loader_is_strict_and_template_site_assets_match():
    marker = "Canada Stock Dashboard V3.6 progressive composer. Strict no-op elsewhere."
    assert marker in TEMPLATE_ICONS
    assert marker in SITE_ICONS
    assert "canada_stocks\\.html$" in TEMPLATE_ICONS
    assert 'script.src = "canada-stock-v36.js?v=20260823"' in TEMPLATE_ICONS
    assert TEMPLATE_ICONS == SITE_ICONS
