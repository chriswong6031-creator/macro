"""Current-source owner/render identity receipts for the stock dashboards.

These assertions intentionally read checked-in ``site/**`` output and the exact
checked-in owner inputs that produced it, so they remain in the nightly
``gate: data`` lane. Counts are derived from those moving inputs: no historical
9/17 or 39/47 population is promoted into a production constant. Candidate
composition is proven separately with frozen, content-addressed fixtures in
``test_stock_dashboard_first_frame.py``.
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
OWNER_INPUTS = {
    "hk": ROOT / "site" / "factordata" / "hk_standouts.json",
    "ca": ROOT / "site" / "factordata" / "canada_standouts.json",
}


def _soup(market: str) -> BeautifulSoup:
    path = PAGES[market]
    if not path.exists():
        pytest.skip(f"sparse checkout omits {path.relative_to(ROOT)}")
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _href_tickers(nodes: Iterable[Tag]) -> list[str]:
    return [str(node.get("href")).rsplit("#", 1)[-1].upper() for node in nodes]


def _owner(market: str) -> dict[str, object]:
    path = OWNER_INPUTS[market]
    if not path.exists():
        pytest.skip(f"sparse checkout omits {path.relative_to(ROOT)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{market}: owner input root is not an object"
    return payload


def _lane_tickers(owner: dict[str, object], lane: str) -> list[str]:
    rows = owner.get(lane)
    assert isinstance(rows, list), f"{lane}: current owner lane is not a list"
    tickers = [
        str(row.get("ticker") or "").strip().upper()
        for row in rows
        if isinstance(row, dict)
    ]
    assert len(tickers) == len(rows), f"{lane}: owner row is not an object"
    assert all(tickers), f"{lane}: owner identity is empty"
    assert len(tickers) == len(set(tickers)), f"{lane}: duplicate owner identity"
    return tickers


def test_hk_generated_page_preserves_complete_candidate_action_population() -> None:
    """HK rendered identities equal the exact current owner lanes without duplicates."""
    owner = _owner("hk")
    soup = _soup("hk")
    bar = soup.find(id="hk-stage-filter")
    assert bar is not None
    counts = {
        button.get("data-stagepick"): int(button.find(class_="pbf-n").get_text(strip=True))
        for button in bar.find_all("button", attrs={"data-stagepick": True})
    }
    buy = _lane_tickers(owner, "buy")
    ripening = _lane_tickers(owner, "ripening")
    ran = _lane_tickers(owner, "ran")
    vetoed = _lane_tickers(owner, "vetoed")
    watch_owner = _lane_tickers(owner, "watch")
    buy_rows = owner["buy"]
    assert isinstance(buy_rows, list)
    buy_stage_counts = Counter(str(row.get("stage")) for row in buy_rows)
    stage_counts = {
        "live": buy_stage_counts["live"],
        "setting_up": buy_stage_counts["setting_up"] + len(ripening),
        "ran": buy_stage_counts["ran"] + len(ran),
        "basing": buy_stage_counts["basing"],
        "blocked": buy_stage_counts["blocked"] + len(vetoed),
    }
    expected_counts = {
        "all": len(buy) + len(ripening) + len(ran) + len(vetoed),
        **{stage: count for stage, count in stage_counts.items() if count},
    }
    assert counts == expected_counts
    assert counts["all"] == sum(
        count for stage, count in counts.items() if stage != "all"
    )

    buy_cards = soup.select("#standouts .pvcard[href]")
    setting_rows = soup.select("#standouts .rip-card[href]")
    ran_rows = soup.select("#standouts .pbr[data-stage='ran'] a[href]")
    blocked_rows = soup.select("#standouts .pbv[data-stage='blocked'] a[href]")
    assert Counter(card.get("data-stage") for card in buy_cards) == Counter(
        str(row.get("stage")) for row in buy_rows
    )
    assert tuple(map(len, (buy_cards, setting_rows, ran_rows, blocked_rows))) == (
        len(buy),
        len(ripening),
        len(ran),
        len(vetoed),
    )

    stage = _href_tickers(
        buy_cards + setting_rows + ran_rows + blocked_rows
    )
    watch = _href_tickers(soup.select("#standouts .watch-strip .watch-grid a[href]"))
    expected_stage = buy + ripening + ran + vetoed
    assert len(stage) == len(set(stage))
    assert set(stage) == set(expected_stage)
    assert len(watch) == len(set(watch))
    assert watch == watch_owner
    intersection = set(stage) & set(watch)
    assert not intersection, f"hk: board/watch owner overlap: {sorted(intersection)}"
    assert len(set(stage) | set(watch)) == len(stage) + len(watch)


def test_canada_generated_page_preserves_complete_candidate_action_population() -> None:
    """Canada rendered identities equal the exact current owner lanes."""
    owner = _owner("ca")
    board_owner = _lane_tickers(owner, "buy")
    watch_owner = _lane_tickers(owner, "watch")
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

    assert len(row_tickers) == len(set(row_tickers))
    assert row_tickers == board_owner
    assert card_tickers == row_tickers
    assert card_tickers[:5] == row_tickers[:5]
    assert len(watch) == len(set(watch))
    assert watch == watch_owner
    intersection = set(card_tickers) & set(watch)
    assert not intersection, f"ca: board/watch owner overlap: {sorted(intersection)}"
    assert len(set(card_tickers) | set(watch)) == len(card_tickers) + len(watch)


@pytest.mark.parametrize("market", PAGES)
def test_legacy_generated_ids_remain_unique_before_p0b_composition(market: str) -> None:
    """Population-only guard; the P0B candidate duplicate-id proof is elsewhere."""
    soup = _soup(market)
    ids = [node.get("id") for node in soup.find_all(attrs={"id": True})]
    duplicates = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
    assert not duplicates, f"{market}: duplicate generated ids: {duplicates}"
