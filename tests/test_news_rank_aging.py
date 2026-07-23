"""Pure tests for the 2026 news revamp — display aging cutoff, the unified
multi-signal display ranker (news_common.rank_score), and the optional AI-feed
connector's degrade-safe contract. No network; all assertions plain `assert`.

House-law note: everything under test is DISPLAY-ONLY — rank_score and the aging
cutoff reshape display order, they never feed a trade signal.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_common as nc          # noqa: E402
from engine import news_ai_feed as aif         # noqa: E402

_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (_NOW - timedelta(days=days_ago)).isoformat()


# --------------------------------------------------------------------------- #
# display aging cutoff
# --------------------------------------------------------------------------- #
def test_display_age_drops_stale_official():
    # 41d-old official straggler (the user's complaint) is dropped; 10d is kept.
    assert nc.display_age_ok(_iso(41), "official", None, _NOW) is False
    assert nc.display_age_ok(_iso(10), "official", None, _NOW) is True


def test_display_age_official_16d_now_dropped():
    # 16d was explicitly flagged as too old — the 14d official cutoff drops it.
    assert nc.display_age_ok(_iso(16), "official", None, _NOW) is False
    assert nc.display_age_ok(_iso(13), "official", None, _NOW) is True


def test_display_age_wire_is_tight():
    assert nc.display_age_ok(_iso(6), "stock_wire", None, _NOW) is False
    assert nc.display_age_ok(_iso(3), "stock_wire", None, _NOW) is True


def test_display_age_fail_open_on_blank():
    # Unparseable / blank dates must be KEPT — never hide on a parse miss.
    assert nc.display_age_ok("", "tier1", None, _NOW) is True
    assert nc.display_age_ok("not-a-date", "official", None, _NOW) is True


def test_display_age_cfg_override():
    cfg = {"display_max_age_days": {"official": 3}}
    assert nc.display_age_ok(_iso(5), "official", cfg, _NOW) is False   # overridden to 3
    assert nc.display_age_ok(_iso(5), "official", None, _NOW) is True   # default 14


def test_display_max_age_days_unknown_tier_uses_default():
    assert nc.display_max_age_days("mystery", None) == nc.DISPLAY_MAX_AGE_DAYS["default"]


# --------------------------------------------------------------------------- #
# the unified display ranker
# --------------------------------------------------------------------------- #
def test_rank_monotonic_in_importance():
    lo = {"importance_score": 40, "seendate": _iso(0)}
    hi = {"importance_score": 90, "seendate": _iso(0)}
    assert nc.rank_score(hi, _NOW) > nc.rank_score(lo, _NOW)


def test_rank_fresher_ranks_higher():
    fresh = {"importance_score": 70, "seendate": _iso(0)}
    old = {"importance_score": 70, "seendate": _iso(6)}
    assert nc.rank_score(fresh, _NOW) > nc.rank_score(old, _NOW)


def test_rank_novelty_and_echo_lift():
    base = {"importance_score": 60, "seendate": _iso(0)}
    novel = {"importance_score": 60, "seendate": _iso(0), "novelty_z": 2.8}
    echoed = {"importance_score": 60, "seendate": _iso(0), "echo": {"n_sources": 5}}
    assert nc.rank_score(novel, _NOW) > nc.rank_score(base, _NOW)
    assert nc.rank_score(echoed, _NOW) > nc.rank_score(base, _NOW)


def test_rank_event_type_and_mag7_lift():
    base = {"importance_score": 60, "seendate": _iso(0)}
    evt = {"importance_score": 60, "seendate": _iso(0), "event": {"event_type": "guidance_cut"}}
    mag = {"importance_score": 60, "seendate": _iso(0), "tickers": ["NVDA"]}
    assert nc.rank_score(evt, _NOW) > nc.rank_score(base, _NOW)
    assert nc.rank_score(mag, _NOW) > nc.rank_score(base, _NOW)


def test_rank_uses_external_ai_importance():
    lo_ai = {"importance_score": 50, "seendate": _iso(0), "ai_importance": 5}
    hi_ai = {"importance_score": 50, "seendate": _iso(0), "ai_importance": 95}
    assert nc.rank_score(hi_ai, _NOW) > nc.rank_score(lo_ai, _NOW)


def test_rank_absent_ai_never_penalises():
    # An item WITHOUT an AI score must not rank below an identical one whose AI
    # score merely mirrors its importance (absent AI defaults to neutral).
    no_ai = {"importance_score": 70, "seendate": _iso(0)}
    assert nc.rank_score(no_ai, _NOW) > 0


def test_rank_falls_back_to_quality_for_financial_items():
    # financial/ticker items carry `quality`, not `importance_score`.
    q = {"quality": 80, "seendate": _iso(0)}
    assert nc.rank_score(q, _NOW) > nc.rank_score({"quality": 20, "seendate": _iso(0)}, _NOW)


def test_rank_null_safe_on_empty_and_garbage():
    assert nc.rank_score({}, _NOW) >= 0.0
    assert nc.rank_score({"importance_score": None, "novelty_z": "x",
                          "echo": "nope", "tickers": "nope", "seendate": None}, _NOW) >= 0.0


def test_rank_bounded_0_100():
    maxed = {"importance_score": 100, "quality": 100, "seendate": _iso(0),
             "novelty_z": 9, "echo": {"n_sources": 20}, "ai_importance": 100,
             "event": {"event_type": "guidance_cut"}, "tickers": ["NVDA", "AAPL", "MSFT"]}
    s = nc.rank_score(maxed, _NOW)
    assert 0.0 <= s <= 100.0


# --------------------------------------------------------------------------- #
# AI-feed connector — degrade-safe / key-gated contract
# --------------------------------------------------------------------------- #
def test_ai_feed_disabled_without_key(monkeypatch):
    # No key resolves -> disabled, empty fetch, empty label. Build stays keyless.
    monkeypatch.setattr(aif.config, "secret", lambda *_a, **_k: None)
    assert aif.enabled() is False
    assert aif.fetch(now=_NOW) == []
    assert aif.provider_label() == ""


def test_ai_feed_normalises_shape_and_ai_fields():
    art = {"title": "Acme beats Q2 earnings", "link": "https://reuters.com/x",
           "source": "Reuters", "publishDate": "2026-07-22T10:00:00Z",
           "tickers": ["ACME"], "sentiment": "positive", "confidence": 0.9,
           "summary": "Acme reported strong Q2 results."}
    h = aif._normalise_ai(art, _NOW)
    assert h is not None
    assert h["ai_sentiment"] == "pos"
    assert h["ai_importance"] == 90.0            # 0.9 confidence -> 0-100
    assert "ACME" in h["tickers"]
    assert h["provider"] == "ai_feed"
    # a well-formed AI item ranks (proves the connector output is ranker-ready)
    assert nc.rank_score(h, _NOW) > 0


def test_ai_feed_drops_titleless():
    assert aif._normalise_ai({"link": "https://x.com"}, _NOW) is None


def test_ai_feed_sentiment_and_importance_variants():
    # numeric sentiment + 0..1 relevance
    h = aif._normalise_ai({"title": "X moves", "url": "https://cnbc.com/x",
                           "sentiment": -0.5, "relevance": 0.4,
                           "publishDate": "2026-07-22T00:00:00Z"}, _NOW)
    assert h["ai_sentiment"] == "neg"
    assert h["ai_importance"] == 40.0
