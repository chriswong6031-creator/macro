"""Tests for the OFR Financial Stress Index collector (collectors/ofr.py).
Parse-only — the CSV is fed in directly so no network is required."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.ofr_fsi import OfrFsiAdapter  # noqa: E402

_CSV = (
    "Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,"
    "United States,Other advanced economies,Emerging markets\n"
    "2026-06-09,-2.311,-1.194,-0.554,-0.328,-0.133,-0.102,-1.161,-0.574,-0.575\n"
    "2026-06-10,-1.918,-1.201,-0.520,-0.316,-0.083,0.201,-1.005,-0.355,-0.558\n"
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


def test_ofr_parses_all_legs(monkeypatch) -> None:
    a = OfrFsiAdapter()
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp(_CSV))
    frames = a.fetch()
    assert set(frames) == {
        "fsi", "fsi_credit", "fsi_equity", "fsi_safe_assets", "fsi_funding",
        "fsi_volatility", "fsi_us", "fsi_oae", "fsi_em",
    }
    # level + a functional + a regional leg parsed with the right value
    assert abs(float(frames["fsi"].iloc[-1, 0]) - (-1.918)) < 1e-9
    assert abs(float(frames["fsi_volatility"].iloc[-1, 0]) - 0.201) < 1e-9
    assert abs(float(frames["fsi_em"].iloc[-1, 0]) - (-0.558)) < 1e-9
    # datetime index, sorted ascending
    s = frames["fsi"]
    assert str(s.index[-1].date()) == "2026-06-10"
    assert s.index.is_monotonic_increasing


def test_ofr_rejects_unexpected_payload(monkeypatch) -> None:
    a = OfrFsiAdapter()
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp("<html>error</html>"))
    try:
        a.fetch()
    except Exception:
        return
    raise AssertionError("expected a parse failure on a non-CSV payload")
