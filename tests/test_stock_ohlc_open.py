"""collectors/_stock_ohlc: the Open column (CN-1 masterplan §W6-CN).

Open was added to ``_OHLC`` so the china_standout_track ledger can grade a true T+1-open fill.
Pins: (1) Open is extracted and renamed to lower-case ``open``; (2) a response missing Open still
keeps the name (Open is preferred, not required) as long as Close is present.
"""
import pandas as pd
import pytest

from collectors import _stock_ohlc as so


def _single_frame(with_open=True):
    idx = pd.bdate_range("2026-01-01", periods=4)
    data = {"Close": [1.0, 2, 3, 4], "High": [1, 2, 3, 4.0],
            "Low": [1, 2, 3, 4.0], "Volume": [9, 9, 9, 9.0]}
    if with_open:
        data = {"Open": [0.9, 1.9, 2.9, 3.9], **data}
    return pd.DataFrame(data, index=idx)


def test_open_is_extracted_and_lowercased(monkeypatch):
    monkeypatch.setattr(so, "_download", lambda *a, **k: _single_frame(with_open=True))
    frames = so.fetch_ohlc(["600000.SS"], "china_stocks", {"batch_size": 50, "sleep_s": 0},
                           full_history=True)
    df = frames["600000.SS"]
    assert list(df.columns) == ["open", "close", "high", "low", "volume"]
    assert df["open"].tolist() == [0.9, 1.9, 2.9, 3.9]


def test_missing_open_keeps_the_name(monkeypatch):
    """A legacy/edge response with no Open must NOT drop the name — Open is optional, Close required."""
    monkeypatch.setattr(so, "_download", lambda *a, **k: _single_frame(with_open=False))
    frames = so.fetch_ohlc(["600000.SS"], "china_stocks", {"batch_size": 50, "sleep_s": 0},
                           full_history=True)
    df = frames["600000.SS"]
    assert "open" not in df.columns and "close" in df.columns and not df.empty


def test_open_in_ohlc_constant():
    """The store schema now leads with Open (backward-compatible additive column)."""
    assert so._OHLC[0] == "Open" and so._REN["Open"] == "open"


def test_extract_drops_only_zero_volume_flat_non_trading_rows():
    """A Yahoo suspension placeholder is not a session; traded/missing-volume rows remain."""
    idx = pd.to_datetime(["2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"])
    source = pd.DataFrame(
        {
            "Open": [24.34, 24.56, 25.00, 26.00],
            "Close": [24.56, 24.56, 25.00, 26.00],
            "High": [25.39, 24.56, 25.00, 26.00],
            "Low": [24.20, 24.56, 25.00, 26.00],
            "Volume": [47_735_572.0, 0.0, 10_000.0, float("nan")],
        },
        index=idx,
    )

    extracted = so._extract(source, "002155.SZ", "china_stocks")

    assert extracted is not None
    assert extracted.index.strftime("%Y-%m-%d").tolist() == [
        "2026-08-19",
        "2026-08-21",
        "2026-08-24",
    ]
    assert extracted.loc["2026-08-21", "volume"] == 10_000.0
    assert pd.isna(extracted.loc["2026-08-24", "volume"])
