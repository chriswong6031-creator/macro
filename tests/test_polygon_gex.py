"""Polygon options-OI accrual: chain parsing, pagination, and the raw+summary store.

The collector is display/research-only; these tests pin the parse filters (OI>0,
strike/expiry window, NaN-iv preservation), the snapshot pagination + apiKey
re-attachment, and that accrue() writes the date-partitioned raw chain plus a
compute_gex summary — and is a clean no-op without a key.
"""
from __future__ import annotations

import pandas as pd
import pytest

from collectors.polygon_options import PolygonOptions, parse_chain
from lib import config

ASOF = pd.Timestamp("2026-06-15")


def _contract(strike, exp, ctype, oi, iv=0.25, gamma=0.01):
    out = {"details": {"strike_price": strike, "expiration_date": exp,
                       "contract_type": ctype, "ticker": f"O:X{ctype[0].upper()}{strike}"},
           "open_interest": oi, "day": {"volume": 7}}
    if iv is not None:
        out["implied_volatility"] = iv
    if gamma is not None:
        out["greeks"] = {"gamma": gamma, "delta": 0.5}
    return out


def test_parse_chain_filters():
    spot = 100.0
    results = [
        _contract(100, "2026-07-15", "call", 500),       # keep
        _contract(105, "2026-07-15", "put", 0),          # drop: OI 0
        _contract(140, "2026-07-15", "call", 100),       # drop: outside +/-30% window
        _contract(100, "2099-01-01", "call", 100),       # drop: beyond max_expiry_days
        _contract(100, "2026-01-01", "call", 100),       # drop: expired (before asof)
        _contract(98, "2026-07-15", "put", 300, iv=None, gamma=None),  # keep, NaN iv
    ]
    df = parse_chain(results, "X", spot, ASOF, window_pct=0.30, max_expiry_days=400)
    assert len(df) == 2
    assert set(df["K"]) == {100.0, 98.0}
    assert (df["oi"] > 0).all()
    assert df.loc[df["K"] == 98.0, "iv"].isna().all()         # wing NaN preserved
    assert df.loc[df["K"] == 100.0, "iv"].iloc[0] == 0.25
    for col in ("underlying", "expiry", "T", "is_call", "oi", "spot", "asof"):
        assert col in df.columns
    assert (df["T"] > 0).all()


def test_parse_chain_empty_guards():
    assert parse_chain([], "X", 100.0, ASOF, window_pct=0.3, max_expiry_days=400).empty
    assert parse_chain([_contract(100, "2026-07-15", "call", 10)], "X", 0.0, ASOF,
                       window_pct=0.3, max_expiry_days=400).empty


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_get_paginates_and_attaches_key(monkeypatch):
    client = PolygonOptions()
    client.key = "TESTKEY"
    calls = []

    pages = iter([
        _Resp({"results": [{"a": 1}], "next_url": "https://api.polygon.io/next?cursor=abc"}),
        _Resp({"results": [{"a": 2}]}),
    ])

    def fake_get(url, **kw):
        calls.append((url, kw.get("params", {})))
        return next(pages)

    monkeypatch.setattr(client, "http_get", fake_get)
    out = client._get("/v3/snapshot/options/SPY", {"limit": 250})
    assert [r["a"] for r in out] == [1, 2]
    # apiKey attached on the first call and re-attached on the cursor follow-up
    assert calls[0][1]["apiKey"] == "TESTKEY"
    assert calls[1][0] == "https://api.polygon.io/next?cursor=abc"
    assert calls[1][1] == {"apiKey": "TESTKEY"}


def _raw(symbols=("SPY",), spot=100.0):
    rows = []
    for sym in symbols:
        for k in range(80, 121, 2):
            for call in (True, False):
                rows.append(dict(underlying=sym, strike_ticker=f"O:{sym}{k}",
                                 expiry=ASOF + pd.Timedelta(days=30), K=float(k),
                                 T=30 / 365, is_call=call, oi=1000.0, iv=0.25,
                                 gamma=0.01, delta=0.5, volume=10.0, spot=spot, asof=ASOF))
    return pd.DataFrame(rows)


class _FakeClient:
    def __init__(self, raw, enabled=True):
        self._raw, self._enabled = raw, enabled

    def enabled(self):
        return self._enabled

    def snapshot(self, symbols, asof):
        return self._raw


def test_accrue_writes_raw_and_summary(tmp_path, monkeypatch):
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpg, "PolygonOptions", lambda: _FakeClient(_raw(("SPY", "QQQ"))))

    res = bpg.accrue(ASOF.to_pydatetime())
    assert res["status"] == "ok"
    assert res["underlyings"] == 2

    raw_file = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"
    assert raw_file.exists()
    back = pd.read_parquet(raw_file)
    assert set(back["underlying"]) == {"SPY", "QQQ"}

    summ = pd.read_parquet(tmp_path / "polygon_gex" / "summary_SPY.parquet")
    assert len(summ) == 1
    assert summ.index[0] == ASOF
    assert summ["gamma_regime"].iloc[0] in ("long", "short")
    assert summ["net_gex_bn"].iloc[0] is not None


def test_accrue_no_key_is_noop(tmp_path, monkeypatch):
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpg, "PolygonOptions", lambda: _FakeClient(_raw(), enabled=False))

    res = bpg.accrue(ASOF.to_pydatetime())
    assert res["status"] == "no_key"
    assert not (tmp_path / "polygon_gex").exists()
