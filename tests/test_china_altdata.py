"""China Alt-Data desk — convergence kernel + signal-lab contract tests (network-free)."""
from __future__ import annotations

from engine import china_altdata as ad
from engine import china_signal_lab as lab


# ---- pure sub-scores ------------------------------------------------------- #
def test_analyst_score():
    assert ad._analyst_score({"buy": 10, "hold": 0, "sell": 0}) == 1.0
    assert ad._analyst_score({"buy": 0, "hold": 0, "sell": 10}) == -1.0
    assert ad._analyst_score({"buy": 5, "hold": 0, "sell": 5}) == 0.0
    assert ad._analyst_score({"buy": 0, "hold": 0, "sell": 0}) is None


def test_value_score_cheap_positive():
    cheap = ad._value_score({"pe": {"pctile": 5}, "pb": {"pctile": 15}})   # cheap vs own band
    rich = ad._value_score({"pe": {"pctile": 95}, "pb": {"pctile": 90}})   # expensive
    assert cheap > 0 and rich < 0
    assert ad._value_score({}) is None


def test_margin_score_and_crowd_flag():
    s, crowded = ad._margin_score({"chg_pct": 40})
    assert s == 1.0 and crowded is True            # >25% financing jump -> crowded
    s2, c2 = ad._margin_score({"chg_pct": 5})
    assert 0 < s2 < 1 and c2 is False
    assert ad._margin_score({})[0] is None


def test_clip():
    assert ad._clip(2.0) == 1.0 and ad._clip(-2.0) == -1.0 and ad._clip(0.3) == 0.3


# ---- by_ticker: structure + None-safe -------------------------------------- #
def test_by_ticker_structure_and_none_safe():
    bt = ad.by_ticker()
    if bt is None:
        return
    assert bt["schema"] == ad.SCHEMA
    for k in ("top", "bottom", "triple", "crowding_flags", "n_universe", "n_triple"):
        assert k in bt
    # triple slice must all have all-three feeds
    assert all(r["n_signals"] >= 3 for r in bt["triple"])
    # top sorted by convergence descending
    convs = [r["convergence"] for r in bt["top"]]
    assert convs == sorted(convs, reverse=True)


def test_mastermind_prefers_triple_and_emits_rich_rows():
    bt = {"asof": "2026-06-20",
          "triple": [{"ticker": "AAA", "name": "Alpha"}, {"ticker": "BBB", "name": "Beta"}],
          "top": [{"ticker": "CCC", "name": "Gamma"}, {"ticker": "AAA", "name": "Alpha"}],
          "bottom": [{"ticker": "ZZZ", "name": "Zed"}], "crowding_flags": ["AAA"]}
    mm = ad.mastermind(bt)
    codes = [r["ticker"] for r in mm["convergence_top"]]
    assert codes[:2] == ["AAA", "BBB"]                  # triple first, deduped
    assert "CCC" in codes
    assert mm["convergence_top"][0]["name"] == "Alpha"  # rich rows carry the name
    assert mm["schema"] == "china_altdata.mastermind.v2"
    assert mm["convergence_bottom"][0]["ticker"] == "ZZZ"


def test_by_ticker_de_degenerated():
    bt = ad.by_ticker()
    if bt is None or len(bt["top"]) < 5:
        return
    convs = [r["convergence"] for r in bt["top"]]
    # rank-normalized convergence must NOT all pin to one value (the old 8/8==1.0 bug)
    assert len(set(round(c, 3) for c in convs)) > 3
    assert convs == sorted(convs, reverse=True)
    assert all(0 <= r["conviction100"] <= 100 for r in bt["top"])


# ---- signal lab ------------------------------------------------------------ #
def test_signal_lab_scorecard():
    sc = lab.build_china_scorecard()
    assert sc["schema"] == lab.SCHEMA
    assert set(sc["tiers"]) == set(lab.TIERS)
    assert sc["summary"]["scored"] == 3        # the 3 validated regime de-risk legs
    assert sc["summary"]["killed"] >= 2
    # every row has bilingual labels + a tier
    for tier, items in sc["tiers"].items():
        for r in items:
            assert r["name_en"] and r["name_zh"] and r["tier"] == tier
