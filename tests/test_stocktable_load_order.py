"""Regression coverage for the stock-dashboard Grid/Table bootstrap.

The asset optimizer marks local JavaScript ``defer``. An inline initializer
placed immediately after ``stocktable.js`` therefore runs before the library
unless it waits for DOMContentLoaded, which fires after deferred scripts.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

PAGES = {
    "us": ("templates/dashboard.html.j2", "site/us_stocks.html", "USStockTable._setView"),
    "cn": ("templates/china.html.j2", "site/china_stocks.html", "StockTable._setView"),
    "hk": ("templates/hk.html.j2", "site/hk_stocks.html", "StockTable._setView"),
    "ca": ("templates/canada.html.j2", "site/canada_stocks.html", "StockTable._setView"),
}


def _stocktable_init_block(text: str) -> str:
    marker = "StockTable init — standout board table view"
    start = text.index(marker)
    end = text.index("</script>", start)
    return text[start:end]


@pytest.mark.parametrize("market", PAGES)
def test_template_waits_for_deferred_stocktable(market):
    template, _page, setter = PAGES[market]
    text = (ROOT / template).read_text()
    block = _stocktable_init_block(text)

    assert "function initStockTableView()" in block
    assert "if (!window.StockTable) return;" in block
    assert (
        "document.addEventListener('DOMContentLoaded', initStockTableView, { once: true });"
        in block
    )
    assert setter in text


@pytest.mark.parametrize("market", PAGES)
def test_shipped_page_boots_after_deferred_stocktable(market):
    _template, page, setter = PAGES[market]
    text = (ROOT / page).read_text()
    block = _stocktable_init_block(text)

    script_pos = text.index('src="stocktable.js?')
    init_pos = text.index("StockTable init — standout board table view")
    script_tag = text[script_pos : text.index("</script>", script_pos)]

    assert script_pos < init_pos
    assert " defer" in script_tag
    assert "function initStockTableView()" in block
    assert (
        "document.addEventListener('DOMContentLoaded', initStockTableView, { once: true });"
        in block
    )
    assert setter in text
