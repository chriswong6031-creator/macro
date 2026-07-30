"""The legacy SPX gex frame must carry a flip in the SHORT-gamma regime too.

Incident (2026-06-24 -> 07-28): ``data/cboe/gex.parquet`` shipped NaN
``flip_strike``/``spot_vs_flip_pct`` on every session whose net GEX ended negative
(22/22 net-positive days resolved a flip, 2/17 net-negative did) — so the dashboard
dealer-gamma banner went blank and ``latest['market_gamma']`` went null in exactly
the short-gamma regime the banner exists to flag. Root cause: the flip was the
zero-crossing of the CUMULATIVE-by-strike GEX profile, and when the profile ends
negative the cumsum never re-crosses zero, so the level is structurally undefined
(verified on the live chain: cumulative ran -0.34bn -> -102.94bn -> -55.03bn, zero
crossings anywhere = 0). The engine's ±25% grid reevaluation
(``engine.gex_engine._gamma_flip``) stays defined on that same chain and is what the
dealer-gamma board already renders — the two surfaces were CONTRADICTING each other
(2026-07-21/22: board long, banner short).

These tests pin the fix: the legacy frame's flip now carries the engine's grid value,
the net-GEX math is untouched, and a flip that genuinely cannot be resolved is LOUD
(a line-start ``::warning`` in the Actions summary), never silent.

Run: .venv/bin/python -m pytest tests/test_cboe_gex_flip.py -q
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from collectors.cboe import GexAdapter

GCFG = {"contract_multiplier": 100.0, "pct_move": 0.01,
        "strike_window_pct": 0.25, "max_expiry_days": 365}


def _adapter(gex_cfg: dict | None = None) -> GexAdapter:
    """GexAdapter with NO network and NO config.load() — __init__ would fetch both."""
    adapter = GexAdapter.__new__(GexAdapter)
    adapter.cfg = {"gex": dict(gex_cfg or GCFG)}
    return adapter


def _chain(spot: float = 7400.0) -> pd.DataFrame:
    """Synthetic per-strike frame shaped like ``GexAdapter._chain`` output
    [K, T, iv, oi, gamma, is_call, expiry], deliberately NET-NEGATIVE (put-heavy) so
    the cumulative-crossing flip is undefined — the incident's regime. All strikes sit
    inside the ±25% window and the single expiry inside the 365-day horizon."""
    expiry = pd.Timestamp(date.today()) + pd.Timedelta(days=30)
    rows = [
        # (strike offset from spot, oi, gamma, is_call)
        (-600.0, 30000.0, 0.0006, False),
        (-400.0, 25000.0, 0.0008, False),
        (-200.0, 20000.0, 0.0010, False),
        (+100.0, 3000.0, 0.0011, True),
        (+200.0, 2000.0, 0.0009, True),
    ]
    return pd.DataFrame({
        "K": [spot + off for off, _, _, _ in rows],
        "T": [30.0 / 365.0] * len(rows),
        "iv": [0.2] * len(rows),
        "oi": [oi for _, oi, _, _ in rows],
        "gamma": [g for _, _, g, _ in rows],
        "is_call": [cc for _, _, _, cc in rows],
        "expiry": [expiry] * len(rows),
    })


def test_short_regime_carries_engine_flip():
    """The incident regression: a net-NEGATIVE (short-gamma) day now carries a flip."""
    spot = 7400.0
    row = _adapter()._legacy_spx(_chain(spot), spot, GCFG, engine_flip=7431.44)
    assert row["net_gex_bn"].iloc[0] < 0, "fixture must be net-negative to pin the bug"
    assert row["flip_strike"].iloc[0] == pytest.approx(7431.44)
    assert row["spot_vs_flip_pct"].iloc[0] == pytest.approx((spot / 7431.44 - 1) * 100)


def test_missing_engine_flip_is_loud_not_silent(capsys):
    """No engine flip -> NaN flip (never fabricated) AND a line-START ``::warning``:
    a logger prefix would make GitHub drop the annotation entirely."""
    spot = 7400.0
    row = _adapter()._legacy_spx(_chain(spot), spot, GCFG, engine_flip=None)
    assert pd.isna(row["flip_strike"].iloc[0])
    assert pd.isna(row["spot_vs_flip_pct"].iloc[0])
    out = capsys.readouterr().out
    assert any(line.startswith("::warning ") for line in out.splitlines()), \
        f"NaN flip must emit a line-start ::warning, got: {out!r}"


def test_net_gex_math_unchanged():
    """The fix touched the FLIP only — net_gex_bn is still the same $ sum, so
    build_site, the gex_flip_cross alert and the archived history are unaffected."""
    spot = 7400.0
    chain = _chain(spot)
    # Hand-compute from the same fixture: sum of ±gamma·oi·100·spot²·0.01, +1 calls /
    # -1 puts, every strike inside the ±25% window and the expiry inside the horizon.
    mult = 100.0 * spot ** 2 * 0.01
    expected = 0.0
    for r in chain.itertuples():
        expected += (1.0 if r.is_call else -1.0) * r.gamma * r.oi * mult
    row = _adapter()._legacy_spx(chain, spot, GCFG, engine_flip=7431.44)
    assert row["net_gex_bn"].iloc[0] * 1e9 == pytest.approx(expected, rel=1e-9)


def test_fetch_wires_engine_flip_into_legacy_frame(monkeypatch):
    """fetch() must hand compute_gex's gamma_flip to _legacy_spx — the wiring is the
    fix; without it the legacy frame silently falls back to a NaN flip."""
    import engine.gex_engine as gex_engine
    from lib import nyse_calendar

    # fetch() is session-gated (collectors.cboe._session_gated): on a non-session
    # day it returns {} by design. Pin the session so this test asserts the wiring
    # on every day of the week — unpinned it passes Mon-Fri and fails every
    # weekend and market holiday.
    monkeypatch.setattr(nyse_calendar, "is_session", lambda d: True)

    spot = 7400.0
    chain = _chain(spot)
    adapter = _adapter({**GCFG, "symbols": ["_SPX"], "r": 0.043})
    monkeypatch.setattr(adapter, "_chain",
                        lambda symbol, retries=None: (chain, spot))
    monkeypatch.setattr(gex_engine, "compute_gex",
                        lambda *a, **k: {"tier": "full", "spot": spot,
                                         "net_gex_bn": -55.0, "gamma_flip": 7431.44,
                                         "dist_to_flip_pct": -0.42,
                                         "gamma_regime": "short", "n_strikes": 100})
    out = adapter.fetch()
    assert "gex" in out, "the legacy SPX frame must still be emitted"
    assert out["gex"]["flip_strike"].iloc[0] == pytest.approx(7431.44)
    assert out["gex"]["spot_vs_flip_pct"].iloc[0] < 0, "spot below flip -> dealers short"
    assert "gex_SPX" in out, "the per-symbol summary row must still be emitted"
