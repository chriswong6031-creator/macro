"""Guard the China A-Share search-universe manual-add hook and OHLC repair boundary.

`china.search_universe.extra_tickers`/`extra_names` (config) + the seed/union in
`collectors.china_universe` keep individual A-shares searchable even when they sit
BELOW the Sina top-800 / CSI-1000 cutoff. The seeded name_en/name_zh/sector must win
over (and skip) the flaky yfinance get_info that mislabels small caps — without ever
touching the calibrated breadth/regime universe (china.constituents).

This suite is also the existing merge-bound China/yfinance source lane, so the focused
A-share daily-OHLC repair contract lives here rather than in a dark standalone pytest
file: Tencent symbol/schema normalization, completed-session law, adjustment-basis
refusal, suspension behavior, and total-primary-outage recovery are all offline/mocked.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import china_universe as cu  # noqa: E402
import collectors.china_stock_prices as china_stock_prices  # noqa: E402
import collectors.china_stock_tencent as tx  # noqa: E402
from lib import config  # noqa: E402

# The names wired in 2026-06-25 (seven sub-cutoff A-shares: 旗天科技 + the user's
# six-name watchlist) that the Sina top-800 / CSI universe never reaches, plus
# 002716.SZ 湖南白银 (2026-08-04), whose mktcap rank STRADDLES the top-800 cutoff.
EXPECTED = ["300061.SZ", "301531.SZ", "688508.SS", "300580.SZ",
            "688049.SS", "300470.SZ", "688609.SS", "002716.SZ"]


class _CountingTicker:
    """yfinance.Ticker stand-in that records every lookup and returns no info, so a
    test can assert the seeded names are NEVER looked up (and never hit the network)."""
    calls: list[str] = []

    def __init__(self, ticker: str) -> None:
        _CountingTicker.calls.append(ticker)

    def get_info(self) -> dict:
        return {}


def _no_network(monkeypatch):
    _CountingTicker.calls = []
    monkeypatch.setattr(cu.yf, "Ticker", _CountingTicker)


def test_config_extras_wired():
    sv = config.load()["china"]["search_universe"]
    tickers = sv.get("extra_tickers") or []
    names = sv.get("extra_names") or {}
    for t in EXPECTED:
        assert t in tickers, f"{t} missing from extra_tickers"
        assert t in names, f"{t} missing from extra_names"
        assert str(names[t].get("name_en") or "").strip(), f"{t} has no seeded name_en"
        assert str(names[t].get("sector") or "").strip(), f"{t} has no seeded sector"


def test_enrich_seed_fills_new_name_without_lookup(monkeypatch):
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    uni = pd.DataFrame({"name_zh": [""], "mktcap_yi": [108.0]},
                       index=pd.Index(["688508.SS"], name="ticker"))
    seed = {"688508.SS": {"name_en": "Wuxi Chipown Micro-electronics",
                          "name_zh": "芯朋微", "sector": "Technology"}}
    out = ad._enrich(uni, prev=None, seed=seed)
    assert out.at["688508.SS", "name_en"] == "Wuxi Chipown Micro-electronics"
    assert out.at["688508.SS", "sector"] == "Technology"
    # name_zh was empty -> seed fills it; combined display is "English / 中文"
    assert out.at["688508.SS", "name"] == "Wuxi Chipown Micro-electronics / 芯朋微"
    # both fields seeded -> the name never enters the get_info queue
    assert _CountingTicker.calls == []


def test_enrich_seed_only_if_empty(monkeypatch):
    """Seed must not clobber an already-cached value (only-if-empty) — it removes the
    name from the lookup queue, it does not overwrite prior enrichment."""
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    uni = pd.DataFrame({"name_zh": ["芯朋微"], "mktcap_yi": [108.0]},
                       index=pd.Index(["688508.SS"], name="ticker"))
    prev = pd.DataFrame({"name_en": ["Cached EN"], "sector": ["Financial Services"]},
                        index=pd.Index(["688508.SS"], name="ticker"))
    out = ad._enrich(uni, prev=prev, seed={"688508.SS": {"name_en": "Seed EN", "sector": "Technology"}})
    assert out.at["688508.SS", "name_en"] == "Cached EN"
    assert out.at["688508.SS", "sector"] == "Financial Services"
    assert _CountingTicker.calls == []


def test_fetch_unions_extra_tickers(monkeypatch, tmp_path):
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    # Redirect EVERY path attr — a missed one (dropped_path, historically) makes
    # fetch() write the repo's real data/china_search/ tree (MM_DATA_GUARD).
    ad.dir, ad.closes_path, ad.members_path, ad.dropped_path = (
        tmp_path, tmp_path / "closes.parquet", tmp_path / "members.parquet",
        tmp_path / "dropped.parquet")

    sina = pd.DataFrame({"name_zh": ["Big A", "Big B"], "mktcap_yi": [1000.0, 900.0]},
                        index=pd.Index(["600000.SS", "000001.SZ"], name="ticker"))
    monkeypatch.setattr(ad, "_sina_universe", lambda: sina)
    monkeypatch.setattr(ad, "_index_constituents", lambda syms: [])

    cols = list(sina.index) + ad.extra_tickers
    idx = pd.bdate_range("2020-01-01", periods=400)
    closes = pd.DataFrame(1.0, index=idx, columns=cols).cumsum()
    monkeypatch.setattr(ad, "_download_closes",
                        lambda tickers, period: closes[[t for t in tickers if t in closes.columns]])

    ad.fetch()
    mb = pd.read_parquet(ad.members_path)
    cl = pd.read_parquet(ad.closes_path)
    for t in ad.extra_tickers:
        assert t in mb.index, f"{t} not unioned into members"
        assert t in cl.columns, f"{t} not unioned into closes"
    # the seeded curation survives the full fetch() path
    assert mb.at["688508.SS", "sector"] == "Technology"
    assert mb.at["688508.SS", "name_en"] == "Wuxi Chipown Micro-electronics"


# ---------------------------------------------------------------------------
# A-share daily OHLC primary/fallback contract — all network paths mocked.
# ---------------------------------------------------------------------------

def _ohlc_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([d for d, _ in rows])
    close = [c for _, c in rows]
    return pd.DataFrame(
        {
            "open": close,
            "close": close,
            "high": [c + 0.2 for c in close],
            "low": [c - 0.2 for c in close],
            "volume": [1000.0] * len(close),
        },
        index=idx,
    )


def test_tencent_code_maps_a_share_suffixes_only():
    assert tx.tencent_code("600118.SS") == "sh600118"
    assert tx.tencent_code("000001.SZ") == "sz000001"
    assert tx.tencent_code("0700.HK") is None
    assert tx.tencent_code("AAPL") is None


def test_tencent_frame_remaps_row_order_and_lots_to_shares():
    payload = {
        "code": 0,
        "data": {
            "sh600118": {
                "qfqday": [
                    ["2026-08-26", "60.10", "61.20", "61.70", "59.80", "12345"],
                    ["2026-08-27", "61.28", "61.09", "61.71", "60.80", "23456"],
                ]
            }
        },
    }
    df = tx.frame_from_payload("600118.SS", payload)
    assert df is not None
    assert list(df.columns) == ["open", "close", "high", "low", "volume"]
    assert df.loc[pd.Timestamp("2026-08-27"), "open"] == 61.28
    assert df.loc[pd.Timestamp("2026-08-27"), "close"] == 61.09
    assert df.loc[pd.Timestamp("2026-08-27"), "high"] == 61.71
    assert df.loc[pd.Timestamp("2026-08-27"), "low"] == 60.80
    assert df.loc[pd.Timestamp("2026-08-27"), "volume"] == 2_345_600.0


def test_completed_session_guard_drops_intraday_partial_bar():
    frame = _ohlc_frame([("2026-08-27", 61.09), ("2026-08-28", 62.00)])
    during_session = dt.datetime(2026, 8, 28, 9, 40, tzinfo=tx._SHANGHAI)
    after_finalization = dt.datetime(2026, 8, 28, 16, 10, tzinfo=tx._SHANGHAI)

    during = tx.keep_completed_sessions(frame, during_session)
    assert during.index.max() == pd.Timestamp("2026-08-27")

    after = tx.keep_completed_sessions(frame, after_finalization)
    assert after.index.max() == pd.Timestamp("2026-08-28")


def test_stock_price_adapter_caps_primary_plane_before_repair(monkeypatch):
    primary = {"600118.SS": _ohlc_frame([("2026-08-27", 61.09), ("2026-08-28", 62.00)])}
    monkeypatch.setattr(china_stock_prices, "fetch_ohlc", lambda *args, **kwargs: primary)
    monkeypatch.setattr(
        china_stock_prices,
        "keep_completed_sessions",
        lambda frame: frame.loc[frame.index <= pd.Timestamp("2026-08-27")],
    )

    seen: dict[str, pd.DataFrame] = {}

    def _repair(frames, tickers, group, cfg):
        seen.update(frames)
        return frames

    monkeypatch.setattr(china_stock_prices, "heal_adjusted_tails", _repair)
    adapter = china_stock_prices.ChinaStockPriceAdapter.__new__(china_stock_prices.ChinaStockPriceAdapter)
    adapter.cfg = {}
    out = adapter.fetch(tickers=["600118.SS"])
    assert out["600118.SS"].index.max() == pd.Timestamp("2026-08-27")
    assert seen["600118.SS"].index.max() == pd.Timestamp("2026-08-27")


def test_tencent_repair_extends_only_stale_name_on_compatible_overlap(monkeypatch):
    stale = _ohlc_frame([("2026-08-20", 60.0), ("2026-08-21", 61.0)])
    current = _ohlc_frame([("2026-08-26", 100.0), ("2026-08-27", 101.0)])
    repaired = _ohlc_frame([
        ("2026-08-20", 60.0),
        ("2026-08-21", 61.0),
        ("2026-08-24", 62.0),
        ("2026-08-25", 63.0),
        ("2026-08-26", 64.0),
        ("2026-08-27", 65.0),
    ])
    frames = {"600118.SS": stale.copy(), "600519.SS": current.copy()}

    monkeypatch.setattr(
        tx,
        "_probe_tencent_latest",
        lambda tickers, cfg: (pd.Timestamp("2026-08-27"), {"600519.SS": current}),
    )
    monkeypatch.setattr(tx, "fetch_tencent", lambda ticker, **kwargs: repaired if ticker == "600118.SS" else None)

    out = tx.heal_adjusted_tails(frames, list(frames), "china_stocks", {})
    assert out["600118.SS"].index.max() == pd.Timestamp("2026-08-27")
    assert out["600118.SS"].loc[pd.Timestamp("2026-08-27"), "close"] == 65.0
    pd.testing.assert_frame_equal(out["600519.SS"], current)


def test_tencent_repair_rejects_incompatible_adjustment_basis(monkeypatch):
    stale = _ohlc_frame([("2026-08-20", 60.0), ("2026-08-21", 61.0)])
    incompatible = _ohlc_frame([
        ("2026-08-20", 66.0),
        ("2026-08-21", 67.1),
        ("2026-08-27", 70.0),
    ])
    frames = {"600118.SS": stale.copy()}
    monkeypatch.setattr(
        tx,
        "_probe_tencent_latest",
        lambda tickers, cfg: (pd.Timestamp("2026-08-27"), {}),
    )
    monkeypatch.setattr(tx, "fetch_tencent", lambda ticker, **kwargs: incompatible)

    out = tx.heal_adjusted_tails(frames, ["600118.SS"], "china_stocks", {"tencent_basis_tol": 0.005})
    pd.testing.assert_frame_equal(out["600118.SS"], stale)


def test_tencent_repair_does_not_invent_sessions_for_suspended_name(monkeypatch):
    suspended = _ohlc_frame([("2026-08-14", 24.0)])
    frames = {"002155.SZ": suspended.copy()}
    monkeypatch.setattr(
        tx,
        "_probe_tencent_latest",
        lambda tickers, cfg: (pd.Timestamp("2026-08-27"), {}),
    )
    monkeypatch.setattr(tx, "fetch_tencent", lambda ticker, **kwargs: suspended.copy())

    out = tx.heal_adjusted_tails(frames, ["002155.SZ"], "china_stocks", {})
    pd.testing.assert_frame_equal(out["002155.SZ"], suspended)


def test_stock_price_adapter_survives_total_yahoo_outage_when_repair_recovers(monkeypatch):
    recovered = {"600118.SS": _ohlc_frame([("2026-08-26", 61.2), ("2026-08-27", 61.09)])}
    monkeypatch.setattr(
        china_stock_prices,
        "fetch_ohlc",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("0/1 tickers returned data")),
    )
    monkeypatch.setattr(
        china_stock_prices,
        "heal_adjusted_tails",
        lambda frames, tickers, group, cfg: recovered,
    )
    adapter = china_stock_prices.ChinaStockPriceAdapter.__new__(china_stock_prices.ChinaStockPriceAdapter)
    adapter.cfg = {}
    assert adapter.fetch(tickers=["600118.SS"]) == recovered
