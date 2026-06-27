"""Polygon intraday (4H chart data) collector — scripts/build_polygon_intraday.

The live aggregate fetch needs the entitled key (CI secret), so these pin the parts that
DON'T: the US class-share symbol mapping (Polygon uses a dot, our store a dash), the
curated universe (deep-history names + ETFs), and the load-bearing fail-safe — no key must
be a clean no-op so the daily collect run never breaks on the additive 4H step.
"""

from __future__ import annotations

from scripts import build_polygon_intraday as bpi


def test_poly_sym_maps_class_share_dash_to_dot():
    assert bpi._poly_sym("AAPL") == "AAPL"
    assert bpi._poly_sym("BRK-B") == "BRK.B"     # Polygon wants the dot form
    assert bpi._poly_sym("BF-B") == "BF.B"


def test_universe_is_curated_us_set():
    u = bpi._universe()
    assert isinstance(u, list) and len(u) > 50      # ~deep names + ETFs
    assert "AAPL" in u
    assert u == sorted(u)                            # deterministic
    assert all(not t.startswith("^") for t in u)     # no index symbols


def test_accrue_without_key_is_a_clean_noop(monkeypatch):
    # force the client to look key-less regardless of the local environment
    monkeypatch.setattr(bpi.PolygonOptions, "enabled", lambda self: False)
    out = bpi.accrue()
    assert out == {"status": "skipped", "rows": 0}


def _bars(*ms_close):
    """Synthetic Polygon /v2/aggs rows: (timestamp_ms, close) -> aggregate dicts."""
    return [{"t": t, "o": c, "h": c, "l": c, "c": c, "v": 100} for t, c in ms_close]


def test_accrue_is_incremental_append_and_key_deduped(monkeypatch, tmp_path):
    """Two runs over the same ticker must EXTEND the store (not overwrite) and de-dupe
    on the bar timestamp with last-write-wins — the append-only/key-dedup contract."""
    import pandas as pd

    monkeypatch.setattr(bpi.PolygonOptions, "enabled", lambda self: True)
    monkeypatch.setattr(bpi.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpi, "_universe", lambda: ["AAPL"])

    runs = iter([
        _bars((1_000, 10.0), (2_000, 11.0)),                 # run 1: two bars
        _bars((2_000, 99.0), (3_000, 12.0)),                 # run 2: dup ts=2000 (new value) + new bar
    ])
    monkeypatch.setattr(bpi.PolygonOptions, "_get",
                        lambda self, path, params=None: next(runs))

    out1 = bpi.accrue()
    assert out1["status"] == "ok" and out1["rows"] == 1
    assert out1["delayed_min"] == bpi.DELAYED_MIN == 15

    df1 = pd.read_parquet(tmp_path / "intraday" / "AAPL.parquet")
    assert len(df1) == 2

    out2 = bpi.accrue()
    df2 = pd.read_parquet(tmp_path / "intraday" / "AAPL.parquet")
    assert len(df2) == 3                                      # appended, not overwritten
    assert df2.index.is_monotonic_increasing
    # ts=2000 kept the LAST write (run 2's 99.0), not the original 10/11 series
    dup_close = float(df2.iloc[1]["close"])
    assert dup_close == 99.0


def test_accrue_stamps_delayed_meta_sidecar(monkeypatch, tmp_path):
    """The store carries an honest 15-min-delayed label (sidecar survives the parquet
    round-trip where DataFrame.attrs would not)."""
    import json

    monkeypatch.setattr(bpi.PolygonOptions, "enabled", lambda self: True)
    monkeypatch.setattr(bpi.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpi, "_universe", lambda: ["AAPL"])
    monkeypatch.setattr(bpi.PolygonOptions, "_get",
                        lambda self, path, params=None: _bars((1_000, 10.0)))

    bpi.accrue()
    meta = json.loads((tmp_path / "intraday" / "_meta.json").read_text())
    assert meta["delayed_min"] == 15
    assert meta["realtime"] is False
    assert meta["source"] == "polygon_standard"
