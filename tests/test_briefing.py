"""Pure-function tests for engine/briefing.py — no network, no disk I/O.

Covers: build() ranking, divergence detection, macro_context passthrough, top-N,
n_actionable threshold, and degrade-on-empty. Inputs are built through
engine.intelligence.build() so the per-ticker `brain` blocks are real, not mocked.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import briefing as B  # noqa: E402
from engine import intelligence as I  # noqa: E402

_TODAY = date(2026, 6, 20)


# --------------------------------------------------------------------------- #
# helpers — synthetic bundle builders (go through intelligence.build for real brain blocks)
# --------------------------------------------------------------------------- #
def _bundle(news=None, alt=None, bt=None, radar=None, standout=None):
    return I.build(news, alt, bt, radar, standout, today=_TODAY)


def _news(lean="pos", n=3):
    return {"n_recent": n, "sentiment_lean": lean, "baskets": [], "sectors": []}


def _sig(t, score, action="WATCH", **kw):
    return {"ticker": t, "signal_score": score, "action": action,
            "channels": kw.get("channels", ["insider"]), **kw}


# --------------------------------------------------------------------------- #
# 1. schema + empty bundle degrades, never raises
# --------------------------------------------------------------------------- #
def test_empty_bundle_degrades():
    br = B.build(None, None, today=_TODAY)
    assert br["schema"] == B.SCHEMA
    assert br["is_context_only"] is True
    assert br["n_universe"] == 0
    assert br["n_priority"] == 0
    assert br["priority_queue"] == []
    assert br["divergences"] == []
    assert br["as_of"] == "2026-06-20"


def test_empty_tickers_dict():
    br = B.build({"tickers": {}}, {}, today=_TODAY)
    assert br["n_universe"] == 0
    assert br["n_actionable"] == 0


# --------------------------------------------------------------------------- #
# 2. ranking — higher priority (confidence × strength) sorts first
# --------------------------------------------------------------------------- #
def test_ranking_by_priority():
    bundle = _bundle(
        news={"HOT": _news("neutral"), "MILD": _news("pos")},
        alt=[_sig("HOT", 88, channels=["insider", "congress"])],   # strong + multi-facet
        radar=[{"ticker": "HOT", "state": "POSITIVE_DIVERGENCE", "edge_score": 90},
               {"ticker": "MILD", "state": "CONFIRMED_UP", "edge_score": 30}],
    )
    br = B.build(bundle, {}, today=_TODAY)
    tickers = [x["ticker"] for x in br["priority_queue"]]
    assert tickers[0] == "HOT"          # strongest, most facets → top
    assert "MILD" in tickers
    assert br["priority_queue"][0]["priority"] >= br["priority_queue"][-1]["priority"]


# --------------------------------------------------------------------------- #
# 3. divergence detection — early_edge surfaces (tape quiet, smart-money bullish)
# --------------------------------------------------------------------------- #
def test_divergence_early_edge():
    bundle = _bundle(
        news={"NVDA": _news("neutral")},
        alt=[_sig("NVDA", 80)],
        radar=[{"ticker": "NVDA", "state": "POSITIVE_DIVERGENCE", "edge_score": 75}],
    )
    br = B.build(bundle, {}, today=_TODAY)
    div = [d["ticker"] for d in br["divergences"]]
    assert "NVDA" in div
    assert br["n_divergences"] == 1


# --------------------------------------------------------------------------- #
# 4. divergence — crowded_top surfaces (tape loud-bullish, smart-money fading)
# --------------------------------------------------------------------------- #
def test_divergence_crowded_top():
    bundle = _bundle(
        news={"TSLA": _news("pos")},                  # loud bullish tape
        alt=[_sig("TSLA", 20, action="AVOID")],       # smart money fading
    )
    br = B.build(bundle, {}, today=_TODAY)
    assert "TSLA" in [d["ticker"] for d in br["divergences"]]


# --------------------------------------------------------------------------- #
# 5. agreement is NOT a divergence — everything bullish → not in the list
# --------------------------------------------------------------------------- #
def test_agreement_not_divergent():
    bundle = _bundle(
        news={"AAPL": _news("pos")},
        alt=[_sig("AAPL", 85)],
        radar=[{"ticker": "AAPL", "state": "CONFIRMED_UP", "edge_score": 60}],
    )
    br = B.build(bundle, {}, today=_TODAY)
    assert "AAPL" not in [d["ticker"] for d in br["divergences"]]


# --------------------------------------------------------------------------- #
# 6. top-N truncation — queue capped, universe count intact
# --------------------------------------------------------------------------- #
def test_top_n_truncation():
    news = {f"T{i}": _news("pos") for i in range(10)}
    bundle = _bundle(news=news)
    br = B.build(bundle, {}, today=_TODAY, top=3)
    assert br["n_universe"] == 10
    assert br["n_priority"] == 3
    assert len(br["priority_queue"]) == 3


# --------------------------------------------------------------------------- #
# 7. n_actionable — only high-confidence high-strength names count
# --------------------------------------------------------------------------- #
def test_n_actionable_threshold():
    bundle = _bundle(
        news={"STRONG": _news("neutral"), "WEAK": _news("pos")},
        alt=[_sig("STRONG", 90, channels=["insider", "congress"])],
        radar=[{"ticker": "STRONG", "state": "POSITIVE_DIVERGENCE", "edge_score": 92}],
    )
    br = B.build(bundle, {}, today=_TODAY)
    # STRONG: 3 facets agree, edge 92 → confidence≥0.6 & strength≥0.5 → actionable
    strong = next(x for x in br["priority_queue"] if x["ticker"] == "STRONG")
    assert strong["confidence"] >= 0.6 and strong["strength"] >= 0.5
    assert br["n_actionable"] >= 1
    # WEAK: news-only, neutral strength → not actionable
    weak = next(x for x in br["priority_queue"] if x["ticker"] == "WEAK")
    assert not (weak["confidence"] >= 0.6 and weak["strength"] >= 0.5)


# --------------------------------------------------------------------------- #
# 8. macro_context passes through verbatim
# --------------------------------------------------------------------------- #
def test_macro_context_passthrough():
    ctx = {"regime": "risk-off", "catalysts": [{"label": "FOMC", "date": "2026-06-25"}],
           "tape_tone": "Cautious into the print."}
    br = B.build(_bundle(news={"X": _news()}), ctx, today=_TODAY)
    assert br["macro_context"] == ctx


# --------------------------------------------------------------------------- #
# 9. item shape — every queue entry carries the brain-ready fields + facts block
# --------------------------------------------------------------------------- #
def test_item_shape_and_facts():
    bundle = _bundle(
        news={"NVDA": _news("neutral")},
        alt=[_sig("NVDA", 80, falsifier="insider buys reverse")],
        radar=[{"ticker": "NVDA", "state": "POSITIVE_DIVERGENCE", "edge_score": 75}],
        standout=[{"ticker": "NVDA", "label": "BUY ZONE", "conviction": 0.8}],
    )
    br = B.build(bundle, {}, today=_TODAY)
    item = br["priority_queue"][0]
    for k in ("ticker", "priority", "confidence", "strength", "lean", "read",
              "situation", "n_facets", "source_mix", "evidence", "falsifier", "facts"):
        assert k in item, f"missing key {k}"
    assert item["ticker"] == "NVDA"
    assert item["falsifier"] == "insider buys reverse"
    facts = item["facts"]
    assert facts["radar_edge"] == 75
    assert facts["alt_score"] == 80
    assert facts["standout_label"] == "BUY ZONE"
    assert set(item["source_mix"]) == {"news", "alt", "radar", "standout"}


# --------------------------------------------------------------------------- #
# 10. today flows into as_of; default top is applied when omitted
# --------------------------------------------------------------------------- #
def test_today_and_default_top():
    bundle = _bundle(news={f"T{i}": _news() for i in range(40)})
    br = B.build(bundle, {}, today=date(2025, 1, 15))
    assert br["as_of"] == "2025-01-15"
    assert br["n_priority"] == B.DEFAULT_TOP    # 25
    assert br["n_universe"] == 40


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
