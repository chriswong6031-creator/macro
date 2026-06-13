"""Commodity Vector alert-engine + news-layer tests — no network.

Run: .venv/bin/python -m tests.test_commodity_alerts
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_alerts as A  # noqa: E402
from engine import commodity_news as N  # noqa: E402
from lib import config  # noqa: E402

ACFG = config.load()["commodities"]["alerts"]


def _hourly(n=400, seed=1, spikes=None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.002, n))), index=idx)
    for at, mult in (spikes or []):
        close.iloc[at:] *= mult  # a sustained step (shock)
    return pd.DataFrame({"close": close})


def test_shock_machine_symmetric() -> None:
    # an UP spike (oil/war) and a DOWN flush (gold) must both enter 'shock'
    up = A.shock_states(_hourly(spikes=[(200, 1.12)], seed=2), "oil", ACFG)
    dn = A.shock_states(_hourly(spikes=[(200, 0.90)], seed=3), "gold", ACFG)
    assert set(up.unique()) <= {"normal", "shock", "extended", "stabilizing"}
    assert (up.iloc[200:230] != "normal").any(), "up-spike should trigger a shock"
    assert (dn.iloc[200:230] != "normal").any(), "down-flush should trigger a shock"


def test_shock_machine_quiet_stays_normal() -> None:
    s = A.shock_states(_hourly(seed=4), "copper", ACFG)  # no spike
    assert (s == "normal").mean() > 0.9


def test_shock_states_causal() -> None:
    h = _hourly(n=400, spikes=[(150, 1.12)], seed=5)
    full = A.shock_states(h, "oil", ACFG)
    trunc = A.shock_states(h.iloc[:300], "oil", ACFG)
    overlap = full.iloc[100:295]
    assert (overlap.values == trunc.reindex(overlap.index).values).all()


def test_event_schema_and_ids_unique() -> None:
    h = _hourly(spikes=[(200, 1.12)], seed=6)
    evs = A.shock_events(h, "oil", ACFG)
    assert evs, "expected at least one shock event"
    for e in evs:
        assert {"id", "ts", "source", "asset", "type", "severity", "headline",
                "detail", "context"} <= set(e)
        assert e["source"] == "commodity" and e["asset"] == "oil"
        assert e["severity"] in ("high", "medium", "info")
    assert len(evs) == len({e["id"] for e in evs}), "event ids must be unique"


def test_daily_events_from_signals() -> None:
    # minimal synthetic per-asset frame with a couple of state flips
    idx = pd.date_range("2026-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "close": np.linspace(2000, 2100, 10),
        "shock_state": ["normal"] * 5 + ["exogenous_bid"] * 5,
        "shock_z": [0.5] * 5 + [2.1] * 5,
        "risk_regime": ["low_risk"] * 10,
        "driver_state": ["neutral"] * 10,
        "ts_trend": ["up"] * 10,
        "alloc_optimal": [0.0] * 5 + [1.0] * 5,
    }, index=idx)
    evs = A._asset_events("gold", df)
    types = {e["type"] for e in evs}
    assert "residual_shock" in types and "allocation" in types
    shock = [e for e in evs if e["type"] == "residual_shock"][0]
    assert "exogenous bid" in shock["headline"].lower()


def test_news_gated_off_by_default() -> None:
    assert N.enabled() is False
    assert N.annotate_event("gold", dt.date(2026, 6, 10), "test") is None


def test_news_outside_window_degrades() -> None:
    # force-enable via a patched config read so we don't hit the network for old dates
    import lib.config as cfgmod
    orig = cfgmod.load
    cfgmod.load = lambda: {**orig(), "commodity_news": {**orig().get("commodity_news", {}), "enabled": True}}
    try:
        ann = N.annotate_event("gold", dt.date(2000, 1, 1), "old")  # >90d -> no network
        assert ann is not None and ann["degraded_reason"] == "outside_gdelt_window"
        assert ann["is_context_only"] is True and ann["headlines"] == []
    finally:
        cfgmod.load = orig


def test_upcoming_catalysts() -> None:
    cats = N.upcoming_catalysts(today=dt.date(2026, 6, 13), horizon_days=14)
    assert cats, "expected FOMC/EIA catalysts in mid-June 2026"
    types = {c["type"] for c in cats}
    assert "FOMC" in types and "EIA_WPSR" in types
    for c in cats:
        assert c["is_context_only"] is True
        assert dt.date.fromisoformat(c["date"]) >= dt.date(2026, 6, 13)


if __name__ == "__main__":
    for fn in [test_shock_machine_symmetric, test_shock_machine_quiet_stays_normal,
               test_shock_states_causal, test_event_schema_and_ids_unique,
               test_daily_events_from_signals, test_news_gated_off_by_default,
               test_news_outside_window_degrades, test_upcoming_catalysts]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all commodity alert/news tests passed")
