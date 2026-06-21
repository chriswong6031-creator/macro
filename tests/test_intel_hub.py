"""Pure-function tests for engine/intel_hub.py — the 5-desk fusion + 2nd/3rd-order analysis.

The intelligence bundle is built through engine.intelligence.build() so the per-ticker
`brain` blocks are real. Velocity I/O is monkeypatched off so no ledger is written.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from engine import intel_hub as H  # noqa: E402
from engine import intelligence as I  # noqa: E402

_TODAY = date(2026, 6, 20)


@pytest.fixture(autouse=True)
def _no_velocity(monkeypatch):
    # default: no velocity history (quiet-news tests rely on n_recent only)
    monkeypatch.setattr(H, "load_velocity", lambda tickers, today, persist=True: {})


def _news(lean="pos", n=3, sectors=None, score=None):
    sc = score if score is not None else {"pos": 0.6, "neg": -0.6}.get(lean, 0.0)
    return {"n_recent": n, "sentiment_lean": lean, "sentiment_score": sc,
            "sentiment_strength": min(1.0, n / 6.0), "baskets": [], "sectors": sectors or ["XLK"]}


def _sig(t, score, action="WATCH", **kw):
    return {"ticker": t, "signal_score": score, "action": action,
            "channels": kw.get("channels", ["insider"]), **kw}


def _bundle(news=None, alt=None, radar=None, standout=None):
    return I.build(news, alt, None, radar, standout, today=_TODAY)


# --------------------------------------------------------------------------- #
# 1. policy index — subject ticker → dir; proxy ETF → sector
# --------------------------------------------------------------------------- #
def test_policy_index():
    pol = {"theses": [
        {"subject": "NVDA", "lean": "overweight", "conviction": "high", "actor": "admin", "thesis": "chips"},
        {"subject": "XLF", "lean": "underweight", "conviction": "low", "actor": "fed", "thesis": "banks"},
        {"subject": "BIL", "lean": "overweight", "conviction": "low"}],
        "regime_context": "low real yields"}
    idx = H.build_policy_index(pol)
    assert idx["by_ticker"]["NVDA"]["dir"] == 1
    assert idx["by_ticker"]["XLF"]["dir"] == -1
    assert idx["by_sector"]["XLF"]["dir"] == -1     # XLF proxy → XLF sector
    assert "BIL" not in idx["by_sector"]            # BIL maps to None sector
    assert idx["regime"] == "low real yields"


def test_policy_for_direct_and_sector():
    idx = H.build_policy_index({"theses": [
        {"subject": "AAPL", "lean": "add"}, {"subject": "XLK", "lean": "overweight"}]})
    assert H._policy_for("AAPL", ["XLK"], idx)["via"] == "direct"
    assert H._policy_for("MSFT", ["XLK"], idx)["via"] == "sector"   # no direct → sector tilt
    assert H._policy_for("ZZZ", ["XLE"], idx) is None


# --------------------------------------------------------------------------- #
# 2. composite conviction — confirmation bonus + falsifier penalty
# --------------------------------------------------------------------------- #
def test_confirmation_lifts_conviction():
    # NVDA: 4 facets all bullish + policy tailwind → high composite, confirmed_trend
    b = _bundle({"NVDA": _news("pos")},
                [_sig("NVDA", 85, channels=["insider", "congress"])],
                [{"ticker": "NVDA", "state": "CONFIRMED_UP", "edge_score": 80}],
                [{"ticker": "NVDA", "label": "UPTREND", "conviction": 0.8}])
    pol = {"theses": [{"subject": "NVDA", "lean": "overweight"}]}
    hub = H.build(b, pol, {}, today=_TODAY)
    nvda = next(d for d in hub["command"] if d["ticker"] == "NVDA")
    assert nvda["n_confirm"] >= 4
    assert nvda["composite_conviction"] >= 80
    assert "confirmed_trend" in nvda["flags"] and "policy_aligned" in nvda["flags"]
    assert nvda["directions"]["policy"] == 1


def test_falsifier_penalty_docks_conviction():
    base = _bundle({"AAPL": _news("pos")}, [_sig("AAPL", 85)],
                   [{"ticker": "AAPL", "state": "CONFIRMED_UP", "edge_score": 80}])
    withf = _bundle({"AAPL": _news("pos")},
                    [_sig("AAPL", 85, falsifier="insider buys reverse")],
                    [{"ticker": "AAPL", "state": "CONFIRMED_UP", "edge_score": 80}])
    c0 = H.build(base, None, {}, today=_TODAY)["command"][0]["composite_conviction"]
    c1 = H.build(withf, None, {}, today=_TODAY)["command"][0]["composite_conviction"]
    assert c1 < c0                                   # falsifier present → lower conviction


# --------------------------------------------------------------------------- #
# 3. 2nd/3rd-order flags
# --------------------------------------------------------------------------- #
def test_early_edge_flag():
    # alt bullish + radar POSITIVE_DIVERGENCE + quiet news + policy tailwind → early_edge/stealth
    b = _bundle({"X": _news("neutral", n=0)},
                [_sig("X", 80)],
                [{"ticker": "X", "state": "POSITIVE_DIVERGENCE", "edge_score": 70}])
    pol = {"theses": [{"subject": "X", "lean": "overweight"}]}
    d = H.build(b, pol, {}, today=_TODAY)["command"][0]
    assert "stealth_accumulation" in d["flags"] or "early_edge" in d["flags"]
    assert d["ticker"] in [x["ticker"] for x in H.build(b, pol, {}, today=_TODAY)["divergence_alerts"]["early_edge"]]


def test_crowded_top_flag(monkeypatch):
    # loud bullish tape (spike) + smart-money AVOID + radar NEGATIVE → crowded_top
    monkeypatch.setattr(H, "load_velocity", lambda tickers, today, persist=True:
                        {"TSLA": {"n_recent": 6, "prior_avg": 1, "accel": 5.0, "spike": True}})
    b = _bundle({"TSLA": _news("pos", n=6)},
                [_sig("TSLA", 20, action="AVOID")],
                [{"ticker": "TSLA", "state": "NEGATIVE_DIVERGENCE", "edge_score": 60}])
    hub = H.build(b, None, {}, today=_TODAY)
    d = next(x for x in hub["command"] if x["ticker"] == "TSLA")
    assert "crowded_top" in d["flags"]
    assert "TSLA" in [x["ticker"] for x in hub["divergence_alerts"]["crowded_top"]]


def test_early_edge_and_stealth_never_coexist():
    # policy present → early_edge (the superset); stealth must NOT also list
    b = _bundle({"X": _news("neutral", n=0)}, [_sig("X", 80)],
                [{"ticker": "X", "state": "POSITIVE_DIVERGENCE", "edge_score": 70}])
    d = H.build(b, {"theses": [{"subject": "X", "lean": "overweight"}]}, {}, today=_TODAY)["command"][0]
    assert "early_edge" in d["flags"] and "stealth_accumulation" not in d["flags"]
    # no policy → stealth_accumulation, not early_edge
    d2 = H.build(b, None, {}, today=_TODAY)["command"][0]
    assert "stealth_accumulation" in d2["flags"] and "early_edge" not in d2["flags"]


def test_dissent_erodes_conviction_and_caps_bonus():
    # a dissenting desk (alt bearish vs the rest bullish) lowers conviction vs full agreement
    agree = _bundle({"A": _news("pos")}, [_sig("A", 85)],
                    [{"ticker": "A", "state": "CONFIRMED_UP", "edge_score": 80}],
                    [{"ticker": "A", "label": "UPTREND", "conviction": 0.8}])
    split = _bundle({"A": _news("pos")}, [_sig("A", 20, action="AVOID")],   # alt dissents
                    [{"ticker": "A", "state": "CONFIRMED_UP", "edge_score": 80}],
                    [{"ticker": "A", "label": "UPTREND", "conviction": 0.8}])
    c_agree = H.build(agree, None, {}, today=_TODAY)["command"][0]
    c_split = H.build(split, None, {}, today=_TODAY)["command"][0]
    assert c_agree["n_dissent"] == 0 and c_split["n_dissent"] >= 1
    assert c_split["composite_conviction"] < c_agree["composite_conviction"]


def test_policy_conflict_flag():
    # desks bullish but policy bearish → policy_conflict
    b = _bundle({"BANK": _news("pos", sectors=["XLF"])}, [_sig("BANK", 80)])
    pol = {"theses": [{"subject": "XLF", "lean": "underweight"}]}
    d = next(x for x in H.build(b, pol, {}, today=_TODAY)["command"] if x["ticker"] == "BANK")
    assert d["directions"]["policy"] == -1
    assert "policy_conflict" in d["flags"]


# --------------------------------------------------------------------------- #
# 4. sector heat + command structure + degrade
# --------------------------------------------------------------------------- #
def test_peer_confirmation_theme_wide_vs_isolated():
    # three bullish high-conviction names in the same basket → theme_wide; a lone one → isolated
    def n_bask(b):
        d = _news("pos"); d["baskets"] = [b]; return d
    b = _bundle({"AAA": n_bask("semis"), "BBB": n_bask("semis"), "CCC": n_bask("semis"),
                 "LONE": n_bask("solo_theme")},
                [_sig(t, 85) for t in ["AAA", "BBB", "CCC", "LONE"]],
                [{"ticker": t, "state": "CONFIRMED_UP", "edge_score": 80} for t in ["AAA", "BBB", "CCC", "LONE"]])
    hub = H.build(b, None, {}, today=_TODAY)
    aaa = next(d for d in hub["command"] if d["ticker"] == "AAA")
    lone = next(d for d in hub["command"] if d["ticker"] == "LONE")
    assert aaa["peer_confirm"] >= 2 and "theme_wide" in aaa["flags"]
    assert lone["peer_confirm"] == 0 and "isolated" in lone["flags"]
    assert hub["counts"]["theme_wide"] >= 3


def test_sentiment_magnitude_gates_loud_bull():
    # a lone 1-pos headline (lean pos but weak score) must NOT trigger crowded_top even at volume
    weak = _bundle({"X": _news("pos", n=6, score=0.1)}, [_sig("X", 20, action="AVOID")],
                   [{"ticker": "X", "state": "NEGATIVE_DIVERGENCE", "edge_score": 60}])
    d = next(x for x in H.build(weak, None, {}, today=_TODAY)["command"] if x["ticker"] == "X")
    assert "crowded_top" not in d["flags"]          # weak sentiment magnitude → not loud-bull


def test_sector_heat_and_command():
    b = _bundle({"NVDA": _news("pos", sectors=["XLK"]), "AMD": _news("pos", sectors=["XLK"])},
                [_sig("NVDA", 80), _sig("AMD", 75)],
                [{"ticker": "NVDA", "state": "CONFIRMED_UP", "edge_score": 70}])
    pol = {"theses": [{"subject": "XLK", "lean": "overweight"}]}
    hub = H.build(b, pol, {"regime": "Goldilocks"}, today=_TODAY)
    assert hub["schema"] == H.SCHEMA
    xlk = next(s for s in hub["sector_heat"] if s["etf"] == "XLK")
    assert xlk["n"] == 2 and xlk["policy_tilt"] == 1 and xlk["mean_conviction"] > 0
    assert hub["desks"]["policy"]["live"] is True
    assert hub["macro_context"]["regime"] == "Goldilocks"


def test_degrade_on_empty():
    hub = H.build(None, None, None, today=_TODAY)
    assert hub["schema"] == H.SCHEMA
    assert hub["n_universe"] == 0 and hub["command"] == []
    assert hub["desks"]["policy"]["live"] is False
    assert hub["as_of"] == "2026-06-20"


def test_velocity_ledger(tmp_path, monkeypatch):
    # real velocity path: seed a prior-day count, confirm accel + spike computed
    monkeypatch.undo()  # remove the autouse stub for this test
    ledger = tmp_path / "news_counts.jsonl"
    ledger.write_text('{"date": "2026-06-19", "counts": {"NVDA": 1}}\n')
    monkeypatch.setattr(H, "_velocity_ledger_path", lambda: ledger)
    out = H.load_velocity({"NVDA": {"news": {"n_recent": 6}}}, _TODAY, persist=False)
    assert out["NVDA"]["prior_avg"] == 1 and out["NVDA"]["accel"] == 5.0
    assert out["NVDA"]["spike"] is True


if __name__ == "__main__":
    import inspect
    g = dict(globals())
    for k, v in sorted(g.items()):
        if k.startswith("test_") and callable(v) and "monkeypatch" not in inspect.signature(v).parameters and "tmp_path" not in inspect.signature(v).parameters:
            print("run via pytest (fixtures needed):", k)
    print("use pytest")
