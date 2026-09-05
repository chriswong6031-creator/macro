"""Generated-page population receipts for the P0B stock-dashboard shell.

These assertions intentionally read checked-in ``site/**`` output and therefore
remain in the nightly ``gate: data`` lane.  The PR merge gate's hermetic source
contract lives in ``test_stock_dashboard_first_frame.py``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag


ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "hk": ROOT / "site" / "hk_stocks.html",
    "ca": ROOT / "site" / "canada_stocks.html",
}


def _soup(market: str) -> BeautifulSoup:
    path = PAGES[market]
    if not path.exists():
        pytest.skip(f"sparse checkout omits {path.relative_to(ROOT)}")
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _href_tickers(nodes: Iterable[Tag]) -> list[str]:
    return [str(node.get("href")).rsplit("#", 1)[-1].upper() for node in nodes]


def test_hk_generated_page_preserves_complete_candidate_action_population() -> None:
    """HK keeps its 39-name stage board plus a disjoint 8-name watch strip."""
    soup = _soup("hk")
    bar = soup.find(id="hk-stage-filter")
    assert bar is not None
    counts = {
        button.get("data-stagepick"): int(button.find(class_="pbf-n").get_text(strip=True))
        for button in bar.find_all("button", attrs={"data-stagepick": True})
    }
    assert counts == {
        "all": 39,
        "live": 2,
        "setting_up": 13,
        "ran": 12,
        "blocked": 12,
    }
    assert counts["all"] == sum(
        counts[key] for key in ("live", "setting_up", "ran", "blocked")
    )

    live_and_setting_cards = soup.select("#standouts .pvcard[href]")
    setting_rows = soup.select("#standouts .rip-card[href]")
    ran_rows = soup.select("#standouts .pbr[data-stage='ran'] a[href]")
    blocked_rows = soup.select("#standouts .pbv[data-stage='blocked'] a[href]")
    assert Counter(card.get("data-stage") for card in live_and_setting_cards) == {
        "live": 2,
        "setting_up": 1,
    }
    assert tuple(map(len, (live_and_setting_cards, setting_rows, ran_rows, blocked_rows))) == (
        3,
        12,
        12,
        12,
    )

    stage = _href_tickers(
        live_and_setting_cards + setting_rows + ran_rows + blocked_rows
    )
    watch = _href_tickers(soup.select("#standouts .watch-strip .watch-grid a[href]"))
    assert len(stage) == len(set(stage)) == 39
    assert len(watch) == len(set(watch)) == 8
    assert set(stage).isdisjoint(watch)
    assert len(set(stage) | set(watch)) == 47


def test_canada_generated_page_preserves_complete_candidate_action_population() -> None:
    """Canada keeps nine buy-board names plus a disjoint eight-name watch strip."""
    soup = _soup("ca")
    payload = soup.find("script", id="stocktable-data")
    assert payload is not None
    rows = json.loads(payload.string or "{}").get("rows", [])
    row_tickers = [str(row.get("ticker") or "").upper() for row in rows]
    card_tickers = [
        str(card.get("data-ticker") or "").upper()
        for card in soup.select("#standouts .pvcard[data-ticker]")
    ]
    watch = _href_tickers(soup.select("#standouts .watch-strip .watch-grid a[href]"))

    assert len(row_tickers) == len(set(row_tickers)) == 9
    assert card_tickers == row_tickers
    assert card_tickers[:5] == row_tickers[:5]
    assert len(watch) == len(set(watch)) == 8
    assert set(card_tickers).isdisjoint(watch)
    assert len(set(card_tickers) | set(watch)) == 17


@pytest.mark.parametrize("market", PAGES)
def test_generated_ids_remain_unique_after_static_composition(market: str) -> None:
    soup = _soup(market)
    ids = [node.get("id") for node in soup.find_all(attrs={"id": True})]
    duplicates = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
    assert not duplicates, f"{market}: duplicate generated ids: {duplicates}"
