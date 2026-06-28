"""Stooq daily-close fallback (lib.stooq) + YahooAdapter wiring.

Yahoo intermittently 404s live large-caps (Marsh MMC, Fiserv FI — served only
under stale symbols), which then drop out of the searchable library. lib.stooq
fills the gap from Stooq's free CSV; the YahooAdapter retries refused
extra_tickers through it. Pure tests — the network call is monkeypatched, so the
CSV parsing, the IP-block guard, and the fallback wiring are all exercised offline.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import stooq  # noqa: E402

_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-06-16,200.0,202.0,199.0,201.5,1000000\n"
    "2026-06-17,201.5,205.0,201.0,204.0,1200000\n"
    "2026-06-18,204.0,206.0,203.0,205.25,900000\n"
)
_BLOCK = "<!DOCTYPE html><html><head><meta charset='utf-8'>blocked</head></html>"


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


def _patch_get(monkeypatch, resp):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: resp)


def test_stooq_parses_csv(monkeypatch):
    _patch_get(monkeypatch, _Resp(_CSV))
    df = stooq.stooq_daily("MMC")
    assert df is not None
    assert list(df.columns) == ["close", "volume"]
    assert len(df) == 3
    assert df["close"].iloc[-1] == 205.25
    assert df.index.tz is None              # tz-naive, store-compatible
    assert df.index.is_monotonic_increasing


def test_stooq_block_page_returns_none(monkeypatch):
    _patch_get(monkeypatch, _Resp(_BLOCK))   # IP block -> HTML, not CSV
    assert stooq.stooq_daily("MMC") is None


def test_stooq_http_error_returns_none(monkeypatch):
    _patch_get(monkeypatch, _Resp("Not Found", status=404))
    assert stooq.stooq_daily("FI") is None


def test_stooq_network_exception_returns_none(monkeypatch):
    import requests

    def _boom(*a, **k):
        raise requests.RequestException("dns")

    monkeypatch.setattr(requests, "get", _boom)
    assert stooq.stooq_daily("FI") is None


def _frame():
    idx = pd.to_datetime(["2026-06-17", "2026-06-18"])
    return pd.DataFrame({"close": [10.0, 11.0], "volume": [1, 2]}, index=idx)


def test_yahoo_fallback_fills_refused_extras(monkeypatch):
    from collectors.yahoo import YahooAdapter
    a = YahooAdapter()
    frames = {"AAPL": _frame()}
    # Stooq serves MMC but not the bogus ZZZZ
    monkeypatch.setattr(stooq, "stooq_daily",
                        lambda t: _frame() if t == "MMC" else None)
    a._fill_missing_extras(frames, ["AAPL", "MMC", "ZZZZ", "^VIX"])
    assert "MMC" in frames          # recovered via Stooq
    assert "ZZZZ" not in frames     # Stooq returned None
    assert "^VIX" not in frames     # index symbols skipped (not a .us equity)
    assert "AAPL" in frames         # already present, untouched
