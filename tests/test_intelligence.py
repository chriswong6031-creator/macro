"""Pure-function tests for engine/intelligence.py — no network, no disk I/O.

Covers: build(), _alt_for() via build(), edge-cases.
All assertions use plain assert. Inputs are inline dicts; no conftest, no fixtures.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intelligence as intel  # noqa: E402

_TODAY = date(2026, 6, 20)

# --------------------------------------------------------------------------- #
# helpers — synthetic data builders
# --------------------------------------------------------------------------- #

def _news(ticker: str, lean: str = "pos", n: int = 3) -> dict:
    """Minimal news_tickers entry as mastermind_by_ticker() would produce."""
    return {
        "n_recent": n,
        "sentiment_lean": lean,
        "baskets": ["ai_semis"],
        "sectors": ["XLK"],
        "is_mag7": ticker in {"NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA"},
        "top": [{"title": f"{ticker} headline", "url": f"https://reuters.com/{ticker}"}],
    }


def _scored_signal(ticker: str, score: float = 7.5) -> dict:
    """Minimal scored mastermind signal (alt_signals list element)."""
    return {
        "ticker": ticker,
        "signal_score": score,
        "conviction": "HIGH",
        "action": "BUY",
        "direction": "LONG",
        "channels": ["congress", "insider"],
        "extended": False,
        "affiliations": ["trump_org"],
    }


def _bt_record(ticker: str, channels: list | None = None, conv: float = 1.5) -> dict:
    """Minimal by_ticker.v2 record (alt_by_ticker dict value)."""
    return {
        "channels": channels if channels is not None else ["congress"],
        "weighted_score": 4.2,
        "convergence_score": conv,
        "trump_linked": False,
    }


# --------------------------------------------------------------------------- #
# 1. Both present — has_news + has_alt + n_with_both
# --------------------------------------------------------------------------- #
def test_both_present_flags_and_n_with_both():
    news_t = {"NVDA": _news("NVDA")}
    alt_s  = [_scored_signal("NVDA", score=8.1)]
    result = intel.build(news_t, alt_s, None, today=_TODAY)

    assert result["schema"] == intel.SCHEMA
    assert result["is_context_only"] is True
    assert "NVDA" in result["tickers"]

    nvda = result["tickers"]["NVDA"]
    assert nvda["has_news"] is True
    assert nvda["has_alt"] is True
    assert nvda["news"] is not None
    assert nvda["alt"] is not None
    assert nvda["alt"]["scored"] is True
    assert nvda["alt"]["signal_score"] == 8.1
    assert result["n_with_both"] == 1
    assert result["n_tickers"] == 1


# --------------------------------------------------------------------------- #
# 2. Scored mastermind wins over by_ticker when both present
# --------------------------------------------------------------------------- #
def test_scored_mastermind_wins_over_by_ticker():
    alt_s  = [_scored_signal("TSLA", score=6.0)]
    alt_bt = {"TSLA": _bt_record("TSLA")}   # also in by_ticker
    result = intel.build(None, alt_s, alt_bt, today=_TODAY)

    tsla = result["tickers"]["TSLA"]
    # scored signal should win
    assert tsla["alt"]["scored"] is True
    assert "signal_score" in tsla["alt"]
    assert tsla["alt"]["signal_score"] == 6.0
    # by_ticker-only keys should NOT be present if mastermind path taken
    # (action comes from scored path, not the default WATCH)
    assert tsla["alt"].get("action") == "BUY"


# --------------------------------------------------------------------------- #
# 3. Unscored fallback — only in alt_by_ticker with real channels
# --------------------------------------------------------------------------- #
def test_unscored_fallback_from_by_ticker():
    alt_bt = {"AMZN": _bt_record("AMZN", channels=["insider"])}
    result = intel.build(None, None, alt_bt, today=_TODAY)

    assert "AMZN" in result["tickers"]
    amzn = result["tickers"]["AMZN"]
    assert amzn["has_alt"] is True
    assert amzn["alt"]["scored"] is False
    assert amzn["alt"].get("action") == "WATCH"


# --------------------------------------------------------------------------- #
# 4. Empty-channel alt dropped — no phantom alt row
# --------------------------------------------------------------------------- #
def test_empty_channel_alt_dropped():
    # channels=[] and convergence_score=0 → no real signal → must be absent
    alt_bt = {"MSFT": {"channels": [], "convergence_score": 0,
                       "weighted_score": 0.0, "trump_linked": False}}
    # No news either → MSFT should not appear in output at all
    result = intel.build(None, None, alt_bt, today=_TODAY)
    assert "MSFT" not in result["tickers"]
    assert result["n_tickers"] == 0


# --------------------------------------------------------------------------- #
# 5. News-only — no alt source
# --------------------------------------------------------------------------- #
def test_news_only():
    news_t = {"AAPL": _news("AAPL", lean="neg")}
    result = intel.build(news_t, None, None, today=_TODAY)

    assert "AAPL" in result["tickers"]
    aapl = result["tickers"]["AAPL"]
    assert aapl["has_news"] is True
    assert aapl["has_alt"] is False
    assert aapl["alt"] is None
    assert result["n_with_both"] == 0


# --------------------------------------------------------------------------- #
# 6. Alt-only — no news source
# --------------------------------------------------------------------------- #
def test_alt_only():
    alt_s = [_scored_signal("META", score=5.5)]
    result = intel.build(None, alt_s, None, today=_TODAY)

    assert "META" in result["tickers"]
    meta = result["tickers"]["META"]
    assert meta["has_alt"] is True
    assert meta["has_news"] is False
    assert meta["news"] is None
    assert result["n_with_both"] == 0


# --------------------------------------------------------------------------- #
# 7. Empty / None inputs — never raises, valid schema
# --------------------------------------------------------------------------- #
def test_empty_inputs_never_raises():
    result = intel.build(None, None, None)
    assert isinstance(result, dict)
    assert result["schema"] == intel.SCHEMA
    assert result["is_context_only"] is True
    assert result["n_tickers"] == 0
    assert result["n_with_both"] == 0
    assert "tickers" in result
    assert "disclaimer" in result
    assert "as_of" in result


def test_empty_dicts_never_raises():
    result = intel.build({}, [], {})
    assert result["n_tickers"] == 0


# --------------------------------------------------------------------------- #
# 8. Tickers uppercase / union correct
# --------------------------------------------------------------------------- #
def test_tickers_uppercased_and_union():
    # Callers pass uppercase keys in the input dicts (the code does NOT normalise
    # dict keys, only the ticker field inside alt_signals list items).
    news_t = {"NVDA": _news("NVDA"), "AAPL": _news("AAPL")}
    alt_s  = [_scored_signal("googl")]   # ticker field in the signal is lowercased
    result = intel.build(news_t, alt_s, None, today=_TODAY)

    tickers = set(result["tickers"].keys())
    # All output keys must be uppercase (mm_index uppercases the ticker field)
    for t in tickers:
        assert t == t.upper(), f"Ticker {t!r} is not uppercased"

    # Union of all three sources
    assert "NVDA" in tickers
    assert "AAPL" in tickers
    assert "GOOGL" in tickers   # lowercased ticker field in signal gets uppercased
    assert result["n_tickers"] == 3


# --------------------------------------------------------------------------- #
# 9. n_with_both counts only tickers with both news AND alt
# --------------------------------------------------------------------------- #
def test_n_with_both_counts_correctly():
    news_t = {"NVDA": _news("NVDA"), "AAPL": _news("AAPL")}
    alt_s  = [_scored_signal("NVDA")]   # only NVDA has alt
    result = intel.build(news_t, alt_s, None, today=_TODAY)

    assert result["n_tickers"] == 2
    assert result["n_with_both"] == 1   # only NVDA has both


# --------------------------------------------------------------------------- #
# 10. today parameter flows into as_of
# --------------------------------------------------------------------------- #
def test_today_parameter_propagates():
    d = date(2025, 1, 15)
    result = intel.build(None, None, None, today=d)
    assert result["as_of"] == "2025-01-15"


# --------------------------------------------------------------------------- #
# 11. Phase 3 — 4-facet bundle (news + alt + radar + standout) + cross-facet read
# --------------------------------------------------------------------------- #
def test_synthesize_labels():
    assert intel._synthesize({"sentiment_lean": "neutral"},
                             {"signal_score": 80, "action": "WATCH"},
                             {"state": "POSITIVE_DIVERGENCE"})["label"] == "early_edge"
    assert intel._synthesize({"sentiment_lean": "pos"},
                             {"signal_score": 20, "action": "AVOID"}, None)["label"] == "crowded_top"
    assert intel._synthesize({"sentiment_lean": "pos"},
                             {"signal_score": 80, "action": "ACCUMULATE"},
                             {"state": "CONFIRMED_UP"})["label"] == "confirmed"
    assert intel._synthesize(None, None, None)["label"] == "quiet"


def test_build_four_facets():
    r = intel.build(
        {"NVDA": _news("NVDA", lean="neutral")},
        [_scored_signal("NVDA")],
        {},
        [{"ticker": "NVDA", "state": "POSITIVE_DIVERGENCE", "edge_score": 75}],
        [{"ticker": "NVDA", "state": "FRESH BUY", "label": "BUY ZONE", "conviction": 0.8}],
        today=_TODAY)
    assert r["schema"] == "intelligence.by_ticker.v2"
    v = r["tickers"]["NVDA"]
    assert v["has_news"] and v["has_alt"] and v["has_radar"] and v["has_standout"]
    assert v["radar"]["edge_score"] == 75 and v["standout"]["label"] == "BUY ZONE"
    assert "read" in v and r["n_4facet"] == 1


def test_radar_quiet_dropped():
    # a QUIET radar entry is not a signal — must not create a phantom ticker
    r = intel.build({}, None, {}, [{"ticker": "X", "state": "QUIET", "edge_score": 5}], None)
    assert "X" not in r["tickers"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
