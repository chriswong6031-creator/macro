"""Contract tests for engine.market_heatmap (CN / HK / CA flat sector→stock map)."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import market_heatmap as mh


def _closes():
    idx = pd.bdate_range("2024-01-01", periods=400)
    # three names with distinct trends so 1D..1Y all compute
    data = {
        "601398.SS": [100 + i * 0.10 for i in range(400)],
        "600519.SS": [200 - i * 0.05 for i in range(400)],
        "000001.SZ": [50 + (i % 7) for i in range(400)],
    }
    return pd.DataFrame(data, index=idx)


def _constituents():
    return pd.DataFrame(
        {"name": ["ICBC", "Moutai", "PA Bank"],
         "sector": ["Financial Services", "Consumer Defensive", "Financial Services"]},
        index=pd.Index(["601398.SS", "600519.SS", "000001.SZ"], name="ticker"),
    )


def test_china_contract_and_marketcap_sizing():
    caps = {"601398.SS": 2.5e12, "600519.SS": 2.1e12, "000001.SZ": 2.0e11}
    names_zh = {"601398.SS": "工商银行", "600519.SS": "贵州茅台", "000001.SZ": "平安银行"}
    p = mh.build_market_heatmap("china", _constituents(), _closes(), caps=caps, names_zh=names_zh)

    assert p["market"] == "china"
    assert p["map_type"] == "stocks"
    assert p["currency"] == "CNY"
    assert p["stockdata_dir"] == "chinastockdata"
    assert p["stock_url"] == "https://app.mastermind-x.com/terminal?symbol="
    assert p["size_label_zh"] == "市值"
    assert p["size_basis"] == "marketcap"
    assert p["tile_label"] == "name"        # tiles labelled by company name, not the code
    assert p["n_tiles"] == 3

    # market cap drives tile size
    sizes = {t["t"]: t["size"] for t in p["tiles"]}
    assert sizes["601398.SS"] > sizes["000001.SZ"]

    # bilingual name only where it differs from the English name
    icbc = next(t for t in p["tiles"] if t["t"] == "601398.SS")
    assert icbc["name_zh"] == "工商银行"

    # sectors are deduped + bilingual via the China map
    fin = next(s for s in p["sectors"] if s["key"] == "Financial Services")
    assert fin["zh"] == "金融"

    # daily timeframes available; intraday/session not
    avail = {tf["key"]: tf["available"] for tf in p["timeframes"]}
    assert avail["1D"] and avail["1Y"]
    assert not avail["5M"] and not avail["AH"]


def test_weight_proxy_then_equal_fallback():
    cons, closes = _constituents(), _closes()
    # no caps -> weight proxy
    p = mh.build_market_heatmap("canada", cons, closes,
                                weights={"601398.SS": 8.0, "600519.SS": 4.0, "000001.SZ": 2.0})
    assert p["size_basis"] == "weight_proxy"
    assert p["tile_label"] == "ticker"      # Canada keeps the ticker (no opt-in)
    sizes = {t["t"]: t["size"] for t in p["tiles"]}
    assert sizes["601398.SS"] > sizes["000001.SZ"]

    # neither caps nor weights -> equal
    p2 = mh.build_market_heatmap("canada", cons, closes)
    assert p2["size_basis"] == "equal"
    s2 = {t["t"]: t["size"] for t in p2["tiles"]}
    assert s2["601398.SS"] == s2["000001.SZ"] == 1.0


def test_missing_caps_are_floored_not_dropped():
    # one name has no cap -> floored (half the smallest positive), never zero/dropped
    caps = {"601398.SS": 1e12, "600519.SS": 1e11}  # 000001.SZ missing
    p = mh.build_market_heatmap("china", _constituents(), _closes(), caps=caps)
    assert p["n_tiles"] == 3
    sizes = {t["t"]: t["size"] for t in p["tiles"]}
    assert sizes["000001.SZ"] > 0
    assert sizes["000001.SZ"] <= min(sizes["601398.SS"], sizes["600519.SS"])


def test_hk_size_label_is_turnover():
    p = mh.build_market_heatmap("hk", _constituents(), _closes(),
                                caps={"601398.SS": 1e10, "600519.SS": 5e9, "000001.SZ": 1e9})
    assert p["currency"] == "HKD"
    assert p["stockdata_dir"] == "hkstockdata"
    assert p["size_label_en"] == "Avg turnover"
    assert p["tile_label"] == "name"


def test_empty_constituents_returns_empty_payload():
    p = mh.build_market_heatmap("china", pd.DataFrame(), _closes())
    assert p["n_tiles"] == 0
    assert p["tiles"] == []
    assert p["map_type"] == "stocks"
    assert all(not tf["available"] for tf in p["timeframes"])


def test_unknown_market_raises():
    with pytest.raises(KeyError):
        mh.build_market_heatmap("japan", _constituents(), _closes())


def test_hk_name_zh_map_wellformed():
    import re
    m = mh.HK_NAME_ZH
    # spot-check the marquee names
    assert m["0700.HK"] == "腾讯控股"
    assert m["9988.HK"] == "阿里巴巴"
    assert m["1398.HK"] == "工商银行"
    # every key is a padded 4-digit .HK code; every value is non-empty Chinese
    for t, nm in m.items():
        assert re.fullmatch(r"\d{4}\.HK", t), t
        assert nm and any("一" <= ch <= "鿿" for ch in nm), (t, nm)


def test_hk_names_zh_applied_to_tiles():
    # the engine copies a supplied zh name onto the tile when it differs from EN
    names_zh = {"601398.SS": "工商银行"}
    p = mh.build_market_heatmap("hk", _constituents(), _closes(), names_zh=names_zh)
    icbc = next(t for t in p["tiles"] if t["t"] == "601398.SS")
    assert icbc["name_zh"] == "工商银行"


# --------------------------------------------------------------------------- #
#  Whole-board breadth block (the 涨跌家数 the card quotes)
# --------------------------------------------------------------------------- #
def _board_row(**over):
    """A well-formed whole-board row for the session _closes() ends on."""
    row = {"date": "2025-07-11", "n": 5197, "adv": 534, "dec": 4631,
           "med_pct": -2.805, "source": "sina"}
    row.update(over)
    return row


def _asof_of(payload):
    return payload["asof"]


def test_board_breadth_emitted_when_session_matches():
    p0 = mh.build_market_heatmap("china", _constituents(), _closes())
    p = mh.build_market_heatmap("china", _constituents(), _closes(),
                                board_breadth=_board_row(date=_asof_of(p0)))
    b = p["board_breadth"]
    assert (b["n"], b["adv"], b["dec"]) == (5197, 534, 4631)
    assert b["flat"] == 5197 - 534 - 4631
    assert b["pct_up"] == round(100 * 534 / 5197, 2)
    assert b["med_pct"] == -2.81                 # rounded for display
    assert b["scope_zh"] == "沪深全市场"
    assert b["source"] == "sina"
    # the block NEVER replaces the tiles — per-name detail still comes from the map
    assert p["n_tiles"] == 3


def test_board_breadth_dropped_when_session_is_stale():
    """A board count from another session beside a fresh map would silently mix two
    days; the front-end's tile-derived count is at least internally consistent."""
    p = mh.build_market_heatmap("china", _constituents(), _closes(),
                                board_breadth=_board_row(date="1999-01-04"))
    assert "board_breadth" not in p


def test_board_breadth_dropped_when_malformed_or_absent():
    asof = _asof_of(mh.build_market_heatmap("china", _constituents(), _closes()))
    for bad in (None, {}, _board_row(date=asof, n=0),
                _board_row(date=asof, adv=4000, dec=4000),   # adv+dec > n
                _board_row(date=asof, n="many"),
                {"date": asof, "adv": 1}):                   # missing n/dec
        p = mh.build_market_heatmap("china", _constituents(), _closes(), board_breadth=bad)
        assert "board_breadth" not in p, bad


def test_board_breadth_is_china_only():
    """HK/CA carry no whole-board feed — a row must not leak a China scope label onto them."""
    asof = _asof_of(mh.build_market_heatmap("hk", _constituents(), _closes()))
    for mkt in ("hk", "canada"):
        p = mh.build_market_heatmap(mkt, _constituents(), _closes(),
                                    board_breadth=_board_row(date=asof))
        assert "board_breadth" not in p


def test_board_breadth_absent_by_default():
    """Every existing caller passes nothing — the payload must be unchanged for them."""
    p = mh.build_market_heatmap("china", _constituents(), _closes())
    assert "board_breadth" not in p
