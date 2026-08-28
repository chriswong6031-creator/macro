from __future__ import annotations

import pandas as pd

import collectors.china_stock_prices as china_stock_prices
import collectors.china_stock_tencent as tx


def _frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
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


def test_frame_from_payload_remaps_tencent_row_order():
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


def test_heal_extends_only_stale_name_on_compatible_overlap(monkeypatch):
    stale = _frame([("2026-08-20", 60.0), ("2026-08-21", 61.0)])
    current = _frame([("2026-08-26", 100.0), ("2026-08-27", 101.0)])
    repaired = _frame([
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
    # The already-current primary frame is not replaced by the secondary provider.
    pd.testing.assert_frame_equal(out["600519.SS"], current)


def test_heal_rejects_incompatible_adjustment_basis(monkeypatch):
    stale = _frame([("2026-08-20", 60.0), ("2026-08-21", 61.0)])
    incompatible = _frame([
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


def test_heal_does_not_invent_sessions_for_suspended_name(monkeypatch):
    suspended = _frame([("2026-08-14", 24.0)])
    frames = {"002155.SZ": suspended.copy()}
    monkeypatch.setattr(
        tx,
        "_probe_tencent_latest",
        lambda tickers, cfg: (pd.Timestamp("2026-08-27"), {}),
    )
    monkeypatch.setattr(tx, "fetch_tencent", lambda ticker, **kwargs: suspended.copy())

    out = tx.heal_adjusted_tails(frames, ["002155.SZ"], "china_stocks", {})
    pd.testing.assert_frame_equal(out["002155.SZ"], suspended)


def test_adapter_survives_total_yahoo_outage_when_repair_recovers(monkeypatch):
    recovered = {"600118.SS": _frame([("2026-08-26", 61.2), ("2026-08-27", 61.09)])}
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
