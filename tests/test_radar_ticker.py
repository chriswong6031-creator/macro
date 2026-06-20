"""Pure-function tests for engine/radar_ticker.py — no network, no real disk I/O.

Covers:
  - _state(act, pr): boundary cases for all four states + QUIET.
  - build(): schema, tickers list shape, edge_score range, note non-empty,
             MSFT → POSITIVE_DIVERGENCE, n / n_divergences, sort order.

All assertions use plain assert. All I/O is monkeypatched via radar_plus._load
and radar_plus._regime. No conftest, no fixtures, no network.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.radar_ticker as rt   # noqa: E402
import engine.radar_plus as rp     # noqa: E402

_TODAY = date(2026, 6, 20)

# ============================================================================ #
# _state boundary cases
# ============================================================================ #

def test_state_positive_divergence_high_act_low_pr():
    # act >= 0.5 and pr <= 0.15  → POSITIVE_DIVERGENCE
    state, lifecycle = rt._state(0.5, 0.1)
    assert state == "POSITIVE_DIVERGENCE"


def test_state_positive_divergence_lifecycle_forming():
    # pr >= -0.3 → forming
    state, lifecycle = rt._state(0.6, 0.0)
    assert state == "POSITIVE_DIVERGENCE"
    assert lifecycle == "forming"


def test_state_positive_divergence_lifecycle_emerging():
    # pr < -0.3 → emerging
    state, lifecycle = rt._state(0.8, -0.5)
    assert state == "POSITIVE_DIVERGENCE"
    assert lifecycle == "emerging"


def test_state_confirmed_up():
    # act >= 0.4 and pr >= 0.5  → CONFIRMED_UP
    state, lifecycle = rt._state(0.4, 0.5)
    assert state == "CONFIRMED_UP"
    assert lifecycle == "mature"


def test_state_confirmed_up_boundary_exact():
    state, lifecycle = rt._state(0.4, 0.5)
    assert state == "CONFIRMED_UP"


def test_state_negative_divergence():
    # act <= -0.25 and pr >= 0.5  → NEGATIVE_DIVERGENCE
    state, lifecycle = rt._state(-0.25, 0.5)
    assert state == "NEGATIVE_DIVERGENCE"
    assert lifecycle == "fading"


def test_state_confirmed_down():
    # act <= -0.25 and pr <= -0.25  → CONFIRMED_DOWN
    state, lifecycle = rt._state(-0.5, -0.5)
    assert state == "CONFIRMED_DOWN"
    assert lifecycle == "fading"


def test_state_quiet_zero_zero():
    state, lifecycle = rt._state(0.0, 0.0)
    assert state == "QUIET"
    assert lifecycle == "quiet"


def test_state_quiet_mid_range():
    # Neither threshold satisfied → QUIET
    state, lifecycle = rt._state(0.3, 0.3)
    assert state == "QUIET"


def test_state_positive_divergence_boundary_at_exactly_0_5():
    # act = 0.5 exactly, pr = 0.0 exactly → POSITIVE_DIVERGENCE
    state, _ = rt._state(0.5, 0.0)
    assert state == "POSITIVE_DIVERGENCE"


def test_state_positive_divergence_boundary_pr_at_0_15():
    # pr = 0.15 exactly is still <= 0.15 → POSITIVE_DIVERGENCE
    state, _ = rt._state(0.5, 0.15)
    assert state == "POSITIVE_DIVERGENCE"


def test_state_not_positive_pr_above_0_15():
    # pr = 0.16 → no longer POSITIVE_DIVERGENCE (unless CONFIRMED_UP)
    state, _ = rt._state(0.5, 0.16)
    # act=0.5 >= 0.4 and pr=0.16 < 0.5 → QUIET
    assert state == "QUIET"


# ============================================================================ #
# build() — synthetic mastermind
# ============================================================================ #

_SYNTH_MASTERMIND = {
    "signals": [
        {
            "ticker": "MSFT",
            "signal_score": 79,          # act = (79-50)/25 = 1.16 → high
            "rs_vs_spy_60d": -12.3,      # pr = -12.3/8 = -1.5375 → low → POSITIVE_DIVERGENCE
            "action": "WATCH",
            "conviction": "MEDIUM",
            "extended": False,
            "channels": ["congress"],
            "affiliations": [],
        },
        {
            "ticker": "AMD",
            "signal_score": 41,          # act = (41-50)/25 = -0.36 → low
            "rs_vs_spy_60d": 147.3,      # pr = 147.3/8 = 18.4 → high → NEGATIVE_DIVERGENCE
            "action": "REDUCE",
            "conviction": "LOW",
            "extended": True,
            "channels": [],
            "affiliations": [],
        },
    ]
}


def _fake_load(rel):
    """Return synthetic data for any path radar_ticker.build() reads."""
    rel = str(rel)
    if "mastermind" in rel:
        return _SYNTH_MASTERMIND
    if "by_ticker" in rel:
        return {"tickers": {}}
    if "fund_flows" in rel:
        return {}
    if "gex" in rel:
        return None
    return {}


def test_build_schema(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["schema"] == rt.SCHEMA
    assert out["schema"] == "radar_ticker.v1"


def test_build_is_context_only(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["is_context_only"] is True


def test_build_as_of(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["as_of"] == _TODAY.isoformat()


def test_build_tickers_list(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert isinstance(out["tickers"], list)
    assert len(out["tickers"]) == 2


def test_build_n(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["n"] == 2


def test_build_n_divergences(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    # MSFT → POSITIVE_DIVERGENCE, AMD → NEGATIVE_DIVERGENCE → both are divergences
    assert out["n_divergences"] == 2


def test_build_msft_positive_divergence(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    msft = next(r for r in out["tickers"] if r["ticker"] == "MSFT")
    assert msft["state"] == "POSITIVE_DIVERGENCE"


def test_build_amd_negative_divergence(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    amd = next(r for r in out["tickers"] if r["ticker"] == "AMD")
    assert amd["state"] == "NEGATIVE_DIVERGENCE"


def test_build_edge_score_range(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    for row in out["tickers"]:
        es = row["edge_score"]
        assert isinstance(es, int), f"edge_score must be int, got {type(es)}"
        assert 0 <= es <= 100, f"edge_score {es} out of range for {row['ticker']}"


def test_build_note_non_empty(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    for row in out["tickers"]:
        assert isinstance(row["note"], str)
        assert len(row["note"]) > 0, f"note is empty for {row['ticker']}"


def test_build_sort_divergences_first(monkeypatch):
    """Non-QUIET states must come before QUIET in the sorted output."""
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    states = [r["state"] for r in out["tickers"]]
    # Once we see QUIET, no non-QUIET should follow
    seen_quiet = False
    for s in states:
        if s == "QUIET":
            seen_quiet = True
        if seen_quiet:
            assert s == "QUIET", "Non-QUIET state appeared after QUIET in sorted output"


def test_build_required_fields(monkeypatch):
    monkeypatch.setattr(rp, "_load", _fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    required_top = {"schema", "is_context_only", "as_of", "regime", "n", "n_divergences", "tickers", "disclaimer"}
    for key in required_top:
        assert key in out, f"Missing top-level key: {key}"

    required_row = {"ticker", "state", "lifecycle", "edge_score", "signal_score", "rs_vs_spy_60d",
                    "action", "conviction", "extended", "channels", "affiliations",
                    "activity", "price", "flows", "options", "crowd", "note"}
    for row in out["tickers"]:
        for key in required_row:
            assert key in row, f"Missing row key: {key} in {row.get('ticker')}"


def test_build_empty_signals(monkeypatch):
    monkeypatch.setattr(rp, "_load", lambda _: {})
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["n"] == 0
    assert out["n_divergences"] == 0
    assert out["tickers"] == []


def test_build_skips_ticker_without_signal_score(monkeypatch):
    mm = {"signals": [{"ticker": "AAPL", "rs_vs_spy_60d": 5.0}]}  # no signal_score
    monkeypatch.setattr(rp, "_load", lambda _: mm)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["n"] == 0


def test_build_uppercase_ticker(monkeypatch):
    """Ticker field gets uppercased in output."""
    mm = {"signals": [{"ticker": "msft", "signal_score": 79, "rs_vs_spy_60d": -12.3}]}
    monkeypatch.setattr(rp, "_load", lambda _: mm)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["tickers"][0]["ticker"] == "MSFT"


def test_build_rs_none_does_not_raise(monkeypatch):
    """Missing rs_vs_spy_60d should not raise (treated as 0)."""
    mm = {"signals": [{"ticker": "XYZ", "signal_score": 60, "rs_vs_spy_60d": None}]}
    monkeypatch.setattr(rp, "_load", lambda _: mm)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out = rt.build(today=_TODAY)
    assert out["n"] == 1
    assert out["tickers"][0]["rs_vs_spy_60d"] is None


def test_build_regime_mult_affects_edge(monkeypatch):
    """A lower regime mult should produce a lower edge score."""
    mm = _SYNTH_MASTERMIND

    def load_with_gex(rel):
        return mm if "mastermind" in str(rel) else {}

    monkeypatch.setattr(rp, "_load", load_with_gex)

    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    out_full = rt.build(today=_TODAY)

    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 0.8, "quad": None, "quad_name": None, "liquidity": None})
    out_low = rt.build(today=_TODAY)

    msft_full = next(r["edge_score"] for r in out_full["tickers"] if r["ticker"] == "MSFT")
    msft_low = next(r["edge_score"] for r in out_low["tickers"] if r["ticker"] == "MSFT")
    assert msft_full >= msft_low


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
