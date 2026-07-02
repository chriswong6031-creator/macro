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
