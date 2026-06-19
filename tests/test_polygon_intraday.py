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
