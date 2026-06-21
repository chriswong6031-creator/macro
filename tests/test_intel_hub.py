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


def _radar(t, state, edge=70, lifecycle=None, wbp=None, rs=None):
    r = {"ticker": t, "state": state, "edge_score": edge}
    if lifecycle is not None:
        r["lifecycle"] = lifecycle
    if wbp is not None:
        r["within_basket_pct"] = wbp
    if rs is not None:
        r["rs_vs_spy_60d"] = rs
    return r


def _so(t, label="UPTREND", off_high=None, conv=0.8):
    s = {"ticker": t, "label": label, "conviction": conv}
    if off_high is not None:
        s["off_high"] = off_high
    return s


# --------------------------------------------------------------------------- #
# 5. V2 — edge-remaining axis, leading-gap, lifecycle stage, opportunity rank
# --------------------------------------------------------------------------- #
def test_edge_remaining_high_for_early_low_for_extended():
    # EARLY: radar forming + basket laggard + quiet tape → lots of edge left
    early = _bundle({"EARLY": _news("neutral", n=0)}, [_sig("EARLY", 80)],
                    [_radar("EARLY", "POSITIVE_DIVERGENCE", lifecycle="forming", wbp=0.15)],
                    [_so("EARLY", label="BOTTOMING", off_high=-28)])
    # LATE: radar mature + basket leader + at-highs + loud bullish tape → little edge left
    late = _bundle({"LATE": _news("pos", n=6, score=0.8)}, [_sig("LATE", 80)],
                   [_radar("LATE", "CONFIRMED_UP", lifecycle="mature", wbp=0.95)],
                   [_so("LATE", label="UPTREND", off_high=-1)])
    de = H.build(early, None, {}, today=_TODAY)["command"][0]
    dl = H.build(late, None, {}, today=_TODAY)["command"][0]
    assert de["edge_remaining"] > 0.6 and dl["edge_remaining"] < 0.4
    assert de["edge_remaining"] > dl["edge_remaining"]


def test_opportunity_ranks_emerging_above_consensus():
    # THE core reframe: a consensus name has HIGHER composite conviction but a leading-edge
    # name out-ranks it by OPPORTUNITY (the new sort key).
    b = _bundle(
        {"CONS": _news("pos", n=5, score=0.7), "EMERG": _news("neutral", n=0)},
        [_sig("CONS", 85), _sig("EMERG", 82)],
        [_radar("CONS", "CONFIRMED_UP", edge=82, lifecycle="mature", wbp=0.9),
         _radar("EMERG", "POSITIVE_DIVERGENCE", edge=82, lifecycle="forming", wbp=0.15)],
        [_so("CONS", label="UPTREND", off_high=-1), _so("EMERG", label="BOTTOMING", off_high=-26)])
    hub = H.build(b, None, {}, today=_TODAY)
    cons = next(d for d in hub["command"] if d["ticker"] == "CONS")
    emerg = next(d for d in hub["command"] if d["ticker"] == "EMERG")
    # consensus is more CONFIRMED but the emerging name has more EDGE and ranks higher
    assert cons["composite_conviction"] > emerg["composite_conviction"]
    assert emerg["opportunity_score"] > cons["opportunity_score"]
    order = [d["ticker"] for d in hub["command"]]
    assert order.index("EMERG") < order.index("CONS")
    assert emerg["stage"] in ("emerging", "early") and cons["stage"] in ("consensus", "exhausted")


def test_leading_gap_inverts_agreement():
    # leading desk (alt + radar POSITIVE_DIVERGENCE) ahead of a quiet crowd → gap >= 1
    lead = _bundle({"L": _news("neutral", n=0)}, [_sig("L", 80)],
                   [_radar("L", "POSITIVE_DIVERGENCE")])
    dl = H.build(lead, None, {}, today=_TODAY)["command"][0]
    assert dl["leading_gap"] >= 1
    # price-led: news + buy-board confirm, radar only CONFIRMED_UP (coincident) → gap <= 0
    late = _bundle({"P": _news("pos", n=5, score=0.7)}, [_sig("P", 55)],
                   [_radar("P", "CONFIRMED_UP")], [_so("P", label="UPTREND")])
    dp = H.build(late, None, {}, today=_TODAY)["command"][0]
    assert dp["leading_gap"] <= 0


def test_catalyst_fusion_and_section():
    special = {"by_ticker": {"X": {"category": "Acquisitions", "date": "2026-06-18",
                                   "brief": "Target receives all-cash bid", "source": "edgar",
                                   "confidence": "high"}}}
    b = _bundle({"X": _news("neutral", n=0)}, [_sig("X", 78)],
                [_radar("X", "POSITIVE_DIVERGENCE", lifecycle="forming", wbp=0.2)])
    hub = H.build(b, None, {}, today=_TODAY, special=special)
    d = next(x for x in hub["command"] if x["ticker"] == "X")
    assert d["catalyst"] and d["catalyst"]["days_since"] == 2 and d["catalyst"]["live"] is True
    assert "catalyst" in d["flags"]
    assert "X" in [c["ticker"] for c in hub["catalysts"]]
    assert hub["desks"]["special"]["live"] is True and hub["counts"]["catalyst"] >= 1


def test_exhausted_lands_in_fade_section_and_demotes():
    # loud-bull tape + smart money AVOID + radar NEGATIVE → exhausted, low opportunity
    b = _bundle({"FADE": _news("pos", n=6, score=0.8)}, [_sig("FADE", 20, action="AVOID")],
                [_radar("FADE", "NEGATIVE_DIVERGENCE", lifecycle="fading")],
                [_so("FADE", label="UPTREND", off_high=0)])
    hub = H.build(b, None, {}, today=_TODAY)
    d = next(x for x in hub["command"] if x["ticker"] == "FADE")
    assert d["stage"] == "exhausted"
    assert d["edge_remaining"] < 0.4 and d["opportunity_score"] < 30
    assert "FADE" in [x["ticker"] for x in hub["exhausted"]]


def test_empty_bundle_has_v2_sections():
    hub = H.build(None, None, None, today=_TODAY)
    for k in ("emerging", "exhausted", "catalysts", "discovery"):
        assert hub[k] == []
    assert hub["n_emerging"] == 0 and hub["desks"]["special"]["live"] is False


# --------------------------------------------------------------------------- #
# 6. V2 Phase-1 — discovery layer (off-desk + ignored leading signals)
# --------------------------------------------------------------------------- #
def test_discovery_off_desk_injected_as_dossier():
    # OFF is not in any feeder facet → it only enters via the discovery feed
    b = _bundle({"INUNI": _news("pos")}, [_sig("INUNI", 70)])
    cand = {"ticker": "OFF", "source": "federal_velocity", "disc_score": 0.6,
            "off_desk": True, "reason": "fed $ accel"}
    disc = {"by_ticker": {"OFF": cand}, "candidates": [cand], "off_desk": [cand],
            "n": 1, "n_off_desk": 1}
    hub = H.build(b, None, {}, today=_TODAY, discovery=disc)
    off = next((d for d in hub["command"] if d["ticker"] == "OFF"), None)
    assert off is not None and off["stage"] == "discovery" and "discovery" in off["flags"]
    assert "OFF" in [d["ticker"] for d in hub["discovery"]]            # surfaced in the section
    assert hub["n_discovery"] >= 1 and hub["counts"]["discovery_off_desk"] == 1


def test_discovery_alone_cannot_manufacture_actionable():
    # a name whose ONLY edge is a single off-tape discovery feed (no genuine non-discovery
    # evidence) must not be staged 'emerging' nor clear the actionable opportunity threshold.
    disc = {"by_ticker": {"X": {"ticker": "X", "source": "federal_velocity",
                                "disc_score": 0.85, "off_desk": False, "reason": "fed $ accel"}}}
    b = _bundle({"X": _news("neutral", n=0)})        # news-neutral only → ~0 genuine signal magnitude
    d = H.build(b, None, {}, today=_TODAY, discovery=disc)["command"][0]
    assert d["stage"] != "emerging"
    assert d["opportunity_score"] < 35               # bounded boost can't manufacture an actionable name


def test_discovery_leg_haircut_on_extended_name():
    # a discovery signal cannot claim 'room' on an already-extended name
    disc = {"by_ticker": {"E": {"ticker": "E", "source": "federal_velocity",
                                "disc_score": 0.85, "off_desk": False, "reason": "fed $"}}}
    b = _bundle({"E": _news("pos")}, [_sig("E", 70, extended=True)])
    d = H.build(b, None, {}, today=_TODAY, discovery=disc)["command"][0]
    assert d["edge_remaining"] < 0.6                 # extended → discovery leg is haircut, no false 'room'


def test_off_desk_injection_is_bounded():
    # a large lagging-confirmer off-desk feed must NOT flood the command list
    off = [{"ticker": f"OD{i:02d}", "source": "insider_cluster", "disc_score": 0.45,
            "off_desk": True, "reason": f"{i} insiders bought"} for i in range(40)]
    disc = {"by_ticker": {c["ticker"]: c for c in off}, "candidates": off, "off_desk": off,
            "n": 40, "n_off_desk": 40}
    b = _bundle({"NVDA": _news("pos")}, [_sig("NVDA", 85)],
                [{"ticker": "NVDA", "state": "CONFIRMED_UP", "edge_score": 80}])
    hub = H.build(b, None, {}, today=_TODAY, discovery=disc)
    injected = [d for d in hub["command"] if d["stage"] == "discovery"]
    assert len(injected) <= H._OFF_DESK_INJECT      # capped, not all 40
    assert hub["counts"]["discovery_off_desk"] == 40  # the count still reports the true total


def test_discovery_boosts_on_desk_name():
    # a name in the bundle with a weak facet gets a discovery boost + flag
    cand = {"ticker": "BIIB", "source": "radar_quiet", "disc_score": 0.55,
            "off_desk": False, "reason": "phase3 + congress buy"}
    disc = {"by_ticker": {"BIIB": cand}, "candidates": [cand], "n": 1}
    base = _bundle({"BIIB": _news("neutral", n=0)})
    plain = H.build(base, None, {}, today=_TODAY)["command"][0]
    boosted = H.build(base, None, {}, today=_TODAY, discovery=disc)["command"][0]
    assert "discovery" in boosted["flags"] and "discovery" not in plain["flags"]
    assert boosted["opportunity_score"] >= plain["opportunity_score"]
    assert "BIIB" in [d["ticker"] for d in H.build(base, None, {}, today=_TODAY, discovery=disc)["discovery"]]


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
