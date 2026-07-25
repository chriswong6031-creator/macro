"""Tests for engine.marketing.weekend_levels — popular-ticker weekend posts.

Focus: level math is correct, copy is compliant (no advice lexicon, one cashtag,
≤280 chars) across every state, and the batch is fail-soft on missing data.
"""
from __future__ import annotations

import pytest

from engine.marketing import weekend_levels as wl


# ─────────────────────────────────────────────────────────────────────────────
# Level math
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_levels_basic():
    closes = [float(x) for x in range(1, 101)]  # 1..100, last=100
    lv = wl.compute_levels(closes)
    assert lv is not None
    assert lv["last"] == 100.0
    assert lv["sma20"] == pytest.approx(90.5)   # mean(81..100)
    assert lv["sma50"] == pytest.approx(75.5)   # mean(51..100)
    assert lv["hi52"] == 100.0 and lv["lo52"] == 1.0
    assert lv["above20"] and lv["above50"]
    assert lv["wk_pct"] == pytest.approx((100 / 95 - 1) * 100)
    assert lv["pct_from_hi"] == pytest.approx(0.0)


def test_compute_levels_insufficient_history_returns_none():
    assert wl.compute_levels([1.0] * 49) is None
    assert wl.compute_levels([]) is None
    assert wl.compute_levels(None) is None  # type: ignore[arg-type]


def test_compute_levels_rejects_nonpositive_last():
    closes = [1.0] * 60 + [0.0]
    assert wl.compute_levels(closes) is None


def test_classify_state_covers_the_grid():
    # leading: above both, at highs
    up = [float(x) for x in range(1, 121)]
    assert wl.classify_state(wl.compute_levels(up)) == "leading"
    # downtrend: below both, not near low
    down = [float(x) for x in range(120, 0, -1)]  # 120..1 -> last well off low? last=1 => near low
    st = wl.classify_state(wl.compute_levels(down))
    assert st in {"downtrend", "basing"}
    # basing: below both AND near the 52w low
    assert wl.classify_state(wl.compute_levels(down)) == "basing"


# ─────────────────────────────────────────────────────────────────────────────
# Copy compliance — the load-bearing safety property for a live brand account
# ─────────────────────────────────────────────────────────────────────────────

def _all_state_series() -> dict[str, list[float]]:
    """Synthetic close series engineered to land in each state."""
    up = [float(x) for x in range(1, 121)]                      # leading
    down = [float(x) for x in range(120, 0, -1)]                # basing (near low)
    # cooling: above 50 but under the 20 (recent dip after a run)
    cooling = [float(x) for x in range(1, 111)] + [95.0, 96.0, 97.0, 98.0, 99.0,
                                                   98.0, 97.0, 98.0, 99.0, 98.0]
    # reclaiming: under 50, back over the 20 (recent bounce off lows)
    reclaiming = [float(x) for x in range(120, 40, -1)] + [42.0, 44.0, 46.0, 48.0,
                                                           50.0, 52.0, 54.0, 56.0]
    return {"leading": up, "basing": down, "cooling": cooling, "reclaiming": reclaiming}


def test_render_post_is_compliant_across_states_and_tails():
    for state, closes in _all_state_series().items():
        lv = wl.compute_levels(closes)
        assert lv is not None
        for variant in range(len(wl._TAILS)):
            headline, body = wl.render_post("NVDA", lv, variant=variant)
            text = f"{headline}\n\n{body}"
            # must not raise: no lexicon, exactly one cashtag, ≤280 chars
            wl._assert_clean(text, "NVDA")
            assert text.count("$NVDA") == 1
            assert len(text) <= wl._MAX_LEN


def test_assert_clean_rejects_banned_phrase():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA is a no-brainer, load up", "NVDA")


def test_assert_clean_rejects_wrong_or_extra_cashtag():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA and $AMD both look great", "NVDA")  # two cashtags
    with pytest.raises(ValueError):
        wl._assert_clean("no cashtag here", "NVDA")


def test_assert_clean_rejects_overlength():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA " + "x" * 300, "NVDA")


# ─────────────────────────────────────────────────────────────────────────────
# Batch construction (fail-soft, outbox-shaped)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_parquet(root, ticker, closes):
    pd = pytest.importorskip("pandas")
    d = root / "data" / "stocks"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    pd.DataFrame({"close": closes}, index=idx).to_parquet(d / f"{ticker}.parquet")


def test_build_items_skips_tickers_without_data(tmp_path):
    _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
    items = wl.build_items(tmp_path, tickers=["NVDA", "ZZZZ"], as_of="2026-07-25")
    assert [i["source"]["ticker"] for i in items] == ["NVDA"]  # ZZZZ skipped, no data


def test_build_items_are_watchlist_and_compliant(tmp_path):
    for t in ("NVDA", "AAPL", "TSLA"):
        _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
    items = wl.build_items(tmp_path, tickers=["NVDA", "AAPL", "TSLA"], as_of="2026-07-25")
    assert len(items) == 3
    for it in items:
        assert it["kind"] == "watchlist"
        assert it["provenance"] == "weekend_levels"
        assert it["source"]["lane"] == "weekend_levels"
        assert len(it["text"]) <= wl._MAX_LEN
        wl._assert_clean(it["text"], it["source"]["ticker"])


def test_build_items_respects_max_and_schedule(tmp_path):
    for t in ("NVDA", "AAPL", "TSLA", "AMD"):
        _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
    sched = [("D1-S1", "2026-07-25T11:00:00Z"), ("D1-S2", "2026-07-25T13:00:00Z")]
    items = wl.build_items(tmp_path, tickers=["NVDA", "AAPL", "TSLA", "AMD"],
                           as_of="2026-07-25", schedule=sched, max_items=2)
    assert len(items) == 2
    assert items[0]["slot"] == "D1-S1" and items[0]["scheduled_at"] == "2026-07-25T11:00:00Z"
    assert items[1]["slot"] == "D1-S2"


# ─────────────────────────────────────────────────────────────────────────────
# Weekend gating + scheduling
# ─────────────────────────────────────────────────────────────────────────────

def test_should_run_only_on_weekends():
    assert wl.should_run("2026-07-25") is True    # Saturday
    assert wl.should_run("2026-07-26") is True    # Sunday
    assert wl.should_run("2026-07-24") is False   # Friday
    assert wl.should_run("2026-07-27") is False   # Monday
    assert wl.should_run("garbage") is False


def test_weekend_schedule_resolves_ladder_to_utc():
    sched = wl.weekend_schedule("2026-07-25", 3)
    assert [s for s, _ in sched] == ["D1-S1", "D1-S2", "D1-S3"]
    # S1 = 4 AM PT on 2026-07-25 (PDT, UTC-7) → 11:00Z
    assert sched[0][1] == "2026-07-25T11:00:00Z"
    # every entry resolved to a real datetime (not the "immediate" fallback)
    assert all(at.endswith("Z") and at != "immediate" for _, at in sched)
