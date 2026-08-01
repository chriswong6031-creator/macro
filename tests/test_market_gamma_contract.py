"""The dealer-gamma (GEX) verdict must reach the machine-readable contract
(data/regime/latest.json -> latest['market_gamma']) AS A STRUCTURED FIELD, from the
SAME deriver that renders the dashboard banner — so the two can never drift, and a
downstream bot reads the regime without parsing the episodic gex_flip_cross alert."""
import pandas as pd

from engine import market_gamma


def _gex(net_gex_bn, flip, spot, spot_vs_flip_pct, asof="2026-06-20"):
    return pd.DataFrame(
        {"net_gex_bn": [net_gex_bn], "flip_strike": [flip], "spot": [spot],
         "spot_vs_flip_pct": [spot_vs_flip_pct]},
        index=pd.to_datetime([asof]))


def test_snapshot_populates_structured_contract_field(monkeypatch):
    """engine.run writes latest['market_gamma'] = market_gamma.snapshot(); assert that,
    fed a stubbed cboe/gex read, it carries every field the contract promises."""
    monkeypatch.setattr(market_gamma.store, "read",
                        lambda group, name: _gex(6.8, 8300, 7500.58, -9.63))
    mg = market_gamma.snapshot()
    assert mg is not None
    for k in ("regime", "gamma_flip", "net_gex_bn", "spot_vs_flip_pct", "spot", "asof"):
        assert k in mg, f"contract field {k!r} missing"
    assert mg["regime"] == "short"          # spot below flip -> dealers SHORT gamma
    assert mg["gamma_flip"] == 8300 and mg["spot"] == 7501
    assert mg["spot_vs_flip_pct"] == -9.6
    assert mg["asof"] == "2026-06-20"


def test_steady_state_no_crossing_still_emits_regime(monkeypatch):
    """Unlike the gex_flip_cross alert (fires only on a sign change), the verdict is
    standing: a frame with NO recent crossing still yields a structured regime."""
    monkeypatch.setattr(market_gamma.store, "read",
                        lambda group, name: _gex(20.0, 5000, 4700.0, -6.0))
    mg = market_gamma.snapshot()
    assert mg is not None and mg["regime"] == "short"


def test_snapshot_degrades_to_none_when_store_absent(monkeypatch):
    monkeypatch.setattr(market_gamma.store, "read", lambda group, name: None)
    assert market_gamma.snapshot() is None


def test_nan_flip_returns_none_and_annotates(monkeypatch, capsys):
    """A PRESENT row with a NaN flip (the 2026-06-24 -> 07-28 short-gamma incident:
    net GEX computed, flip unresolved) still degrades to None — but no longer SILENTLY.
    The blank banner + null contract field must announce themselves in the Actions
    summary, and the annotation must START its line or GitHub drops it."""
    monkeypatch.setattr(market_gamma.store, "read",
                        lambda group, name: _gex(-37.7, float("nan"), 7408.30,
                                                 float("nan"), asof="2026-07-23"))
    assert market_gamma.snapshot() is None
    out = capsys.readouterr().out
    assert any(line.startswith("::warning ") for line in out.splitlines()), \
        f"NaN flip must emit a line-start ::warning, got: {out!r}"


def test_fe_banner_and_contract_share_one_deriver():
    """The build_site banner var and the engine contract must be the SAME function
    object — the structural guarantee that they can never drift."""
    from scripts.build_site import market_gamma_view
    assert market_gamma_view is market_gamma.view
