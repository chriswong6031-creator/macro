"""tests/test_marketing_live_verify.py — post-time tape gate (engine/marketing/live_verify.py).

Covers: quote loading precedence, quote-age math, the per-kind verdict matrix
(signal underwater/runaway/adverse/earnings, mover/theme stale-claim, receipt
and chart adverse-day skips), BEAR mirroring, fail directions on missing data,
and config overrides. Pure-function tests; no network, no ledger writes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from engine.marketing import live_verify as lv


NOW = datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc)  # 11:00 ET, mid-session
NOW_MS = int(NOW.timestamp() * 1000)


def _live(quotes: dict, asof: str | None = None) -> dict:
    return {"quotes": quotes, "asof": asof or NOW.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "source": "test"}


def _q(price=None, prev=None, pct=None, ts_ms=NOW_MS) -> dict:
    return {"price": price, "prev_close": prev, "change_pct": pct, "ts_ms": ts_ms,
            "source": "quotes"}


def _signal_item(ticker="GOOG", direction="BULL", entry=200.0, pct_today=None,
                 price=None) -> tuple[dict, dict]:
    item = {
        "kind": "signal",
        "text": f"${ticker} flagged at {entry}",
        "media": [],
        "source": {"ticker": ticker, "direction": direction, "entry": entry},
    }
    quotes = {ticker: _q(price=price, prev=entry, pct=pct_today)}
    return item, _live(quotes)


# ─────────────────────────────────────────────────────────────────────────────
# Quote loading
# ─────────────────────────────────────────────────────────────────────────────

def test_load_live_quotes_precedence_snapshot_wins(tmp_path):
    (tmp_path / "site" / "live").mkdir(parents=True)
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "site" / "live" / "quotes.json").write_text(json.dumps(
        {"asof": "2026-07-23T14:00:00+00:00",
         "quotes": {"AAPL": {"price": 1.0, "prevClose": 1.0, "changePct": -9.0, "ts": 1}}}))
    (tmp_path / "data" / "marketing" / "live_quotes_snapshot.json").write_text(json.dumps(
        {"asof": "2026-07-23T14:55:00+00:00",
         "quotes": {"AAPL": {"price": 2.0, "prevClose": 2.0, "changePct": 3.0, "ts": 2}}}))
    out = lv.load_live_quotes(tmp_path)
    assert out["quotes"]["AAPL"]["change_pct"] == 3.0  # snapshot overrode display
    assert "snapshot" in out["source"]


def test_load_live_quotes_heatmap_fallback(tmp_path):
    (tmp_path / "site" / "marketdata").mkdir(parents=True)
    (tmp_path / "site" / "marketdata" / "sp500_heatmap.json").write_text(json.dumps(
        {"tiles": [{"ticker": "MSFT", "pct": -2.5}]}))
    out = lv.load_live_quotes(tmp_path)
    assert out["quotes"]["MSFT"]["change_pct"] == -2.5
    assert out["quotes"]["MSFT"]["price"] is None


def test_load_live_quotes_empty_root(tmp_path):
    out = lv.load_live_quotes(tmp_path)
    assert out["quotes"] == {}
    assert out["source"] == "none"


# ─────────────────────────────────────────────────────────────────────────────
# Signal gates
# ─────────────────────────────────────────────────────────────────────────────

def test_signal_adverse_day_quarantines():
    # The operator's example: engine said buy, the name is -7% on earnings.
    item, live = _signal_item(pct_today=-7.0)
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"
    assert "-7.0%" in v["reasons"][0]


def test_signal_small_red_day_posts():
    item, live = _signal_item(pct_today=-1.2, price=199.5)
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "post"


def test_signal_underwater_live_price_quarantines():
    item, live = _signal_item(pct_today=-3.0, price=193.0)  # -3.5% through entry 200
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"
    assert "underwater" in v["reasons"][0]


def test_signal_runaway_live_price_quarantines():
    item, live = _signal_item(pct_today=3.0, price=228.0)  # +14% past entry 200
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"
    assert "no longer actionable" in v["reasons"][0]


def test_signal_bear_mirror_adverse_is_up_move():
    item, live = _signal_item(direction="BEAR", pct_today=5.0, price=200.0)
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"


def test_signal_bear_down_move_posts():
    item, live = _signal_item(direction="BEAR", pct_today=-3.0, price=194.0)
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "post"


def test_signal_missing_quote_skips_not_posts():
    item, _ = _signal_item()
    v = lv.verify_item(item, live=_live({}), now=NOW)
    assert v["action"] == "skip"


def test_signal_stale_quote_skips():
    old_ms = NOW_MS - 90 * 60 * 1000  # 90 minutes old
    item = {"kind": "signal", "text": "$GOOG at 200",
            "source": {"ticker": "GOOG", "direction": "BULL", "entry": 200.0}}
    live = _live({"GOOG": _q(price=201.0, pct=0.5, ts_ms=old_ms)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "skip"
    assert "old" in v["reasons"][0]


def test_signal_earnings_guard_skips():
    item, live = _signal_item(ticker="GOOG", pct_today=0.5, price=201.0)
    v = lv.verify_item(item, live=live, earnings=frozenset({"GOOG"}), now=NOW)
    assert v["action"] == "skip"
    assert "earnings" in v["reasons"][0]


def test_signal_earnings_guard_disabled_by_config():
    item, live = _signal_item(ticker="GOOG", pct_today=0.5, price=201.0)
    cfg = {"publish": {"live_gate": {"earnings_guard": False}}}
    v = lv.verify_item(item, live=live, earnings=frozenset({"GOOG"}), now=NOW, cfg=cfg)
    assert v["action"] == "post"


def test_gate_disabled_passes_everything():
    item, live = _signal_item(pct_today=-9.9)
    cfg = {"publish": {"live_gate": {"enabled": False}}}
    v = lv.verify_item(item, live=live, now=NOW, cfg=cfg)
    assert v["action"] == "post"


def test_threshold_override_from_config():
    item, live = _signal_item(pct_today=-3.0, price=199.0)
    cfg = {"publish": {"live_gate": {"signal_adverse_pct": -2.0}}}
    v = lv.verify_item(item, live=live, now=NOW, cfg=cfg)
    assert v["action"] == "quarantine"


# ─────────────────────────────────────────────────────────────────────────────
# Non-signal kinds
# ─────────────────────────────────────────────────────────────────────────────

def test_education_kind_never_gated():
    item = {"kind": "education", "text": "The stop matters more than the target"}
    v = lv.verify_item(item, live=_live({}), now=NOW)
    assert v["action"] == "post"


def test_chart_adverse_day_skips_not_quarantines():
    item = {"kind": "chart", "text": "$NVDA chart", "source": {"ticker": "NVDA"}}
    live = _live({"NVDA": _q(price=100.0, pct=-8.0)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "skip"


def test_chart_missing_quote_posts():
    item = {"kind": "chart", "text": "$NVDA chart", "source": {"ticker": "NVDA"}}
    v = lv.verify_item(item, live=_live({}), now=NOW)
    assert v["action"] == "post"


def test_receipt_red_tape_skips():
    item = {"kind": "receipt", "text": "$AMD T1 hit", "source": {"ticker": "AMD"}}
    live = _live({"AMD": _q(price=100.0, pct=-6.0)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "skip"
    assert "bleeds" in v["reasons"][0]


def test_mover_claim_holds_posts():
    item = {"kind": "mover", "text": "$ISRG -14.0% today",
            "source": {"ticker": "ISRG", "baseline_pct": -14.0}}
    live = _live({"ISRG": _q(price=300.0, pct=-11.0)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "post"


def test_mover_claim_sign_flip_quarantines():
    item = {"kind": "mover", "text": "$ISRG -14.0% today",
            "source": {"ticker": "ISRG", "baseline_pct": -14.0}}
    live = _live({"ISRG": _q(price=300.0, pct=2.0)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"
    assert "stale" in v["reasons"][0]


def test_mover_claim_faded_magnitude_quarantines():
    item = {"kind": "mover", "text": "$ISRG -14.0% today",
            "source": {"ticker": "ISRG", "baseline_pct": -14.0}}
    live = _live({"ISRG": _q(price=300.0, pct=-1.0)})  # < 30% of claimed size
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "quarantine"


def test_mover_missing_quote_skips():
    item = {"kind": "mover", "text": "$ISRG -14.0% today",
            "source": {"ticker": "ISRG", "baseline_pct": -14.0}}
    v = lv.verify_item(item, live=_live({}), now=NOW)
    assert v["action"] == "skip"


def test_ticker_falls_back_to_cashtag_regex():
    item = {"kind": "chart", "text": "One chart on $TSLA worth a look", "source": {}}
    live = _live({"TSLA": _q(price=200.0, pct=-9.0)})
    v = lv.verify_item(item, live=live, now=NOW)
    assert v["action"] == "skip"  # regex found TSLA, adverse-day chart skip fired


def test_no_ticker_posts():
    item = {"kind": "watchlist", "text": "Names I'm watching this week"}
    v = lv.verify_item(item, live=_live({}), now=NOW)
    assert v["action"] == "post"


# ─────────────────────────────────────────────────────────────────────────────
# Earnings guard set loading (fail-soft)
# ─────────────────────────────────────────────────────────────────────────────

def test_earnings_guard_set_missing_file(tmp_path):
    assert lv.load_earnings_guard_set(tmp_path, now=NOW) == frozenset()


def test_earnings_guard_set_reads_parquet(tmp_path):
    pd = pytest.importorskip("pandas")
    (tmp_path / "data" / "earnings").mkdir(parents=True)
    df = pd.DataFrame(
        {
            "next_date": ["2026-07-23", "2026-07-24", "2026-07-24", "2026-08-01"],
            "next_time": ["time-after-hours", "time-pre-market",
                          "time-after-hours", "time-pre-market"],
        },
        index=["GOOG", "AAPL", "MSFT", "AMZN"],
    )
    df.to_parquet(tmp_path / "data" / "earnings" / "earnings.parquet")
    got = lv.load_earnings_guard_set(tmp_path, now=NOW)
    # GOOG reports today; AAPL tomorrow pre-market; MSFT tomorrow AH is out of
    # scope; AMZN is next week.
    assert got == frozenset({"GOOG", "AAPL"})


# ─────────────────────────────────────────────────────────────────────────────
# Market-closed (weekend) mode — the tape can't move when the market is shut, so
# a signal written off Friday's close must POST on Sat/Sun instead of skipping
# on "stale quote". Weekday behaviour must stay exactly as the tests above.
# ─────────────────────────────────────────────────────────────────────────────

SAT = datetime(2026, 7, 25, 15, 0, tzinfo=timezone.utc)   # Saturday 11:00 ET
SUN = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)   # Sunday
# A quote timestamped to Friday's close — ~19h old on Saturday: "stale" to the
# wall-clock gate, but it IS the last print.
FRI_CLOSE_MS = int(datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)


def test_market_is_closed_weekend_vs_weekday():
    assert lv._market_is_closed(SAT) is True
    assert lv._market_is_closed(SUN) is True
    assert lv._market_is_closed(NOW) is False           # Thursday
    assert lv._market_is_closed(datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc)) is False  # Friday
    # Saturday after midnight UTC is still Friday evening in ET → open-day rules.
    assert lv._market_is_closed(datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)) is False


def test_signal_stale_quote_posts_on_weekend():
    # Same stale quote that SKIPS on a weekday (test_signal_stale_quote_skips)
    # must POST on Saturday: Friday's close is the last print, nothing moved.
    item = {"kind": "signal", "text": "$ROST at 235.8",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    live = _live({"ROST": _q(price=238.9, prev=242.0, pct=-1.3, ts_ms=FRI_CLOSE_MS)},
                 asof="2026-07-24T20:00:00+00:00")
    v = lv.verify_item(item, live=live, now=SAT)
    assert v["action"] == "post"


def test_signal_no_quote_still_holds_on_weekend():
    # A name we cannot verify AT ALL (not in the weekend snapshot) is still held,
    # even on a weekend — we only relax staleness for a PRESENT last-close quote,
    # never post a signal with zero price verification.
    item = {"kind": "signal", "text": "$ROST",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    v = lv.verify_item(item, live=_live({}), now=SAT)
    assert v["action"] == "skip"


def test_signal_adverse_move_still_quarantines_on_weekend():
    # The adverse-move safety still fires against the LAST close: a BULL signal on
    # a name that closed -7% Friday must never post over the weekend.
    item = {"kind": "signal", "text": "$ROST",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    live = _live({"ROST": _q(price=219.3, pct=-7.0, ts_ms=FRI_CLOSE_MS)},
                 asof="2026-07-24T20:00:00+00:00")
    v = lv.verify_item(item, live=live, now=SAT)
    assert v["action"] == "quarantine"


def test_signal_runaway_still_quarantines_on_weekend():
    # Safety preserved: if Friday's close already ran +15% past the entry, the
    # entry is stale even on a weekend → quarantine, not post.
    item = {"kind": "signal", "text": "$ROST",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    live = _live({"ROST": _q(price=271.2, pct=2.0, ts_ms=FRI_CLOSE_MS)},
                 asof="2026-07-24T20:00:00+00:00")
    v = lv.verify_item(item, live=live, now=SAT)
    assert v["action"] == "quarantine"


def test_signal_earnings_guard_still_skips_on_weekend():
    # A Monday pre-market print is a real forward risk — the earnings guard fires
    # even on the weekend, ahead of the market-closed bypass.
    item = {"kind": "signal", "text": "$ROST",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    live = _live({"ROST": _q(price=238.9, pct=-1.3, ts_ms=FRI_CLOSE_MS)})
    v = lv.verify_item(item, live=live, earnings=frozenset({"ROST"}), now=SAT)
    assert v["action"] == "skip"


def test_mover_still_skips_on_weekend():
    # Same-day MOVE claim ("today's biggest mover") can't be true on a non-trading
    # day — held, not posted.
    item = {"kind": "mover", "text": "$ROST biggest mover today",
            "source": {"ticker": "ROST", "baseline_pct": 5.0}}
    v = lv.verify_item(item, live=_live({}), now=SAT)
    assert v["action"] == "skip"


def test_market_closed_mode_disabled_by_config_reverts_to_skip():
    item = {"kind": "signal", "text": "$ROST",
            "source": {"ticker": "ROST", "direction": "BULL", "entry": 235.8}}
    live = _live({"ROST": _q(price=238.9, pct=-1.3, ts_ms=FRI_CLOSE_MS)},
                 asof="2026-07-24T20:00:00+00:00")
    cfg = {"publish": {"live_gate": {"market_closed_mode": False}}}
    v = lv.verify_item(item, live=live, now=SAT, cfg=cfg)
    assert v["action"] == "skip"   # strict wall-clock gate restored
