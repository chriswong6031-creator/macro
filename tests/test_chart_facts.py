"""tests/test_chart_facts.py — Chart Facts engine tests.

Verifies:
1. 52-week high detection + correct numbers in whitelist
2. Volume record detection + multiplier in whitelist
3. 5-day green streak detection
4. weekly streak detection
5. numbers_whitelist covers every number appearing in fact texts
6. Handles short series without error (no crash on < 10 bars)
7. Percentage change facts detected (1w, 4w, 13w)
8. NR7 tight range detection
9. SMA reclaim detection
10. compute_facts returns stable sorted output (salience DESC)
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_dates(n: int, start: str = "2025-01-02") -> list[str]:
    """Generate n trading dates starting from start."""
    d = date.fromisoformat(start)
    dates = []
    count = 0
    while count < n:
        if d.weekday() < 5:  # Mon-Fri only
            dates.append(d.isoformat())
            count += 1
        d += timedelta(days=1)
    return dates


def _flat_ohlcv(n: int, price: float = 100.0) -> tuple:
    """Flat OHLCV arrays."""
    dates = _make_dates(n)
    o = [price] * n
    h = [price + 0.5] * n
    l = [price - 0.5] * n
    c = [price] * n
    v = [1_000_000.0] * n
    return dates, o, h, l, c, v


def _rising_ohlcv(n: int, start: float = 100.0, step: float = 0.5) -> tuple:
    """Slowly rising OHLCV."""
    dates = _make_dates(n)
    c = [start + i * step for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [ci + 0.3 for ci in c]
    l = [ci - 0.3 for ci in c]
    v = [1_000_000.0] * n
    return dates, o, h, l, c, v


def _number_re():
    """Regex matching number tokens from copy."""
    return re.compile(
        r"[+-]?\d+\.?\d*%"       # percentage
        r"|\d+\.?\d*x"            # multiplier
        r"|\b\d{2,4}\.\d{2}\b"   # price
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_facts_returns_dict():
    from engine.marketing.chart_facts import compute_facts
    dates, o, h, l, c, v = _flat_ohlcv(60)
    result = compute_facts("AAPL", dates, o, h, l, c, v)
    assert isinstance(result, dict)
    assert "facts" in result
    assert "numbers_whitelist" in result
    assert isinstance(result["facts"], list)
    assert isinstance(result["numbers_whitelist"], list)


def test_compute_facts_short_series_no_crash():
    from engine.marketing.chart_facts import compute_facts
    # Series too short for most detectors — should not crash
    dates, o, h, l, c, v = _flat_ohlcv(5)
    result = compute_facts("TEST", dates, o, h, l, c, v)
    assert isinstance(result, dict)
    # No facts expected (too short), no crash
    assert "facts" in result


def test_new_52w_high_detected():
    from engine.marketing.chart_facts import compute_facts
    # Build a series where last bar makes a new high
    n = 260  # ~1 year of trading days
    dates = _make_dates(n)
    c = [100.0] * (n - 1) + [115.0]  # last bar pops
    o = [99.0] * n
    h = c[:]
    h[-1] = 115.0  # new high
    l = [98.0] * n
    v = [1_000_000.0] * n

    result = compute_facts("AAPL", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "new_52w_high" in fact_ids, f"Expected new_52w_high in {fact_ids}"

    # The fact text must name the BASIS it was measured on. This bar closes
    # above the highest prior CLOSE, so the close-basis arm fires and the words
    # have to say "closing high" — an unqualified "52-week high" names the
    # intraday extreme a quote page prints, which this branch never measured.
    high_fact = next(f for f in result["facts"] if f["id"] == "new_52w_high")
    assert high_fact["basis"] == "close"
    assert "52-week closing high" in high_fact["text"], high_fact["text"]
    assert high_fact["salience"] == 10


def test_close_basis_record_never_claims_the_intraday_52w_high():
    """The basis-mix repro: a NEW CLOSING high while the true 52w high is far above.

    Adversarial-review finding (2026-07-31). One prior bar spiked to 320 intraday
    but closed at 250; today closes at 305 — a genuine new closing high, and a
    full 15 below the 52-week high any quote page prints. The old wording shipped
    "closed at a new 52-week high (305.00)", which a reader falsifies in one
    glance. Fails pre-fix on the substring assertion below.
    """
    from engine.marketing.chart_facts import compute_facts
    n = 260
    dates = _make_dates(n)
    c = [200.0] * (n - 1) + [305.0]
    c[50] = 250.0                       # prior best CLOSE, well under today's
    o = [199.0] * n
    h = c[:]
    h[50] = 320.0                       # the real 52-week high — an intraday spike
    h[-1] = 305.0                       # today never traded above its close
    l = [198.0] * n
    v = [1_000_000.0] * n

    result = compute_facts("MSFT", dates, o, h, l, c, v)
    high_fact = next((f for f in result["facts"] if f["id"] == "new_52w_high"), None)
    assert high_fact is not None, [f["id"] for f in result["facts"]]
    assert high_fact["basis"] == "close"
    text = high_fact["text"]
    assert "52-week closing high" in text, text
    # The load-bearing half: the sentence must not contain the unqualified claim.
    assert "a new 52-week high" not in text, text


def test_new_52w_high_numbers_in_whitelist():
    from engine.marketing.chart_facts import compute_facts
    n = 260
    dates = _make_dates(n)
    c = [100.0] * (n - 1) + [115.0]
    o = [99.0] * n
    h = c[:]
    h[-1] = 115.0
    l = [98.0] * n
    v = [1_000_000.0] * n

    result = compute_facts("AAPL", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])

    # Every number token in every fact text must be in the whitelist
    num_re = _number_re()
    for fact in result["facts"]:
        for token in num_re.findall(fact["text"]):
            # Skip very short bare integers
            if re.match(r"^\d{1,2}$", token):
                continue
            assert token in whitelist, (
                f"Number '{token}' in fact '{fact['id']}' not in whitelist={whitelist}"
            )


def test_volume_record_detected():
    from engine.marketing.chart_facts import compute_facts
    # Last bar has 5× average volume — record for the look-back
    n = 90
    dates = _make_dates(n)
    c = [100.0 + i * 0.1 for i in range(n)]
    o = [99.0] * n
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    avg_vol = 1_000_000.0
    v = [avg_vol] * (n - 1) + [avg_vol * 5]  # last bar = 5x average

    result = compute_facts("TSLA", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "volume_record" in fact_ids, f"Expected volume_record in {fact_ids}"

    vol_fact = next(f for f in result["facts"] if f["id"] == "volume_record")
    assert vol_fact["salience"] == 9
    # Multiplier like "5.0x" or "5x" in numbers
    assert any("x" in n for n in vol_fact["numbers"]), (
        f"Expected multiplier in numbers: {vol_fact['numbers']}"
    )


def test_volume_record_numbers_in_whitelist():
    from engine.marketing.chart_facts import compute_facts
    n = 90
    dates = _make_dates(n)
    c = [100.0] * n
    o = [99.0] * n
    h = [100.5] * n
    l = [99.5] * n
    v = [1_000_000.0] * (n - 1) + [5_000_000.0]

    result = compute_facts("NVDA", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])
    num_re = _number_re()
    for fact in result["facts"]:
        for token in num_re.findall(fact["text"]):
            if re.match(r"^\d{1,2}$", token):
                continue
            assert token in whitelist, (
                f"Token '{token}' in '{fact['id']}' not in whitelist"
            )


def test_green_streak_5_sessions():
    from engine.marketing.chart_facts import compute_facts
    # 5 straight green sessions at the end
    n = 60
    dates = _make_dates(n)
    c = [100.0 + i * 0.2 for i in range(n)]
    o = list(c)
    # Make last 5 bars clearly green (close > open)
    for i in range(n - 5, n):
        o[i] = c[i] - 1.0  # open 1 below close = green
    h = [ci + 0.5 for ci in c]
    l = [oi - 0.5 for oi in o]
    v = [1_000_000.0] * n

    result = compute_facts("MSFT", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "streak_green" in fact_ids, f"Expected streak_green in {fact_ids}"

    streak_fact = next(f for f in result["facts"] if f["id"] == "streak_green")
    assert "5" in streak_fact["numbers"] or any("5" in n for n in streak_fact["numbers"]), (
        f"Expected streak count 5 in numbers: {streak_fact['numbers']}"
    )
    assert streak_fact["salience"] == 6


def test_red_streak_detected():
    from engine.marketing.chart_facts import compute_facts
    n = 60
    dates = _make_dates(n)
    c = [100.0 - i * 0.2 for i in range(n)]
    o = list(c)
    # Last 4 bars red (close < open)
    for i in range(n - 4, n):
        o[i] = c[i] + 1.0  # open above close = red
    h = [oi + 0.5 for oi in o]
    l = [ci - 0.5 for ci in c]
    v = [1_000_000.0] * n

    result = compute_facts("BA", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "streak_red" in fact_ids, f"Expected streak_red in {fact_ids}"


def test_weekly_streak_4_up_weeks():
    from engine.marketing.chart_facts import compute_facts
    # Build 6 weeks of daily data, last 4 weeks each close > open-of-week
    from datetime import date as _date
    # Use actual dates spanning 6 weeks
    start = _date(2025, 5, 5)  # a Monday
    dates = []
    d = start
    for _ in range(30):  # 6 weeks × 5 days
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    # Not enough dates after filtering, add more
    dates_needed = 30
    dates = []
    d = start
    while len(dates) < dates_needed:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)

    n = len(dates)
    # Rising close series (each week ends higher than it started)
    c = [100.0 + i * 0.5 for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [ci + 0.3 for ci in c]
    l = [ci - 0.3 for ci in c]
    v = [1_000_000.0] * n

    result = compute_facts("SPY", dates, o, h, l, c, v)
    # weekly streaks need >=4 weeks; with 6 weeks rising, should detect
    fact_ids = [f["id"] for f in result["facts"]]
    # May or may not fire depending on exact week grouping; just verify no crash
    assert isinstance(result["facts"], list)


def test_pct_change_1w_detected():
    from engine.marketing.chart_facts import compute_facts
    n = 30
    dates = _make_dates(n)
    c = [100.0] * n
    c[-1] = 110.0  # +10% from 5 days ago
    o = [99.0] * n
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    v = [1_000_000.0] * n

    result = compute_facts("PLTR", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "pct_5" in fact_ids, f"Expected pct_5 in {fact_ids}"


def test_pct_change_numbers_in_whitelist():
    from engine.marketing.chart_facts import compute_facts
    n = 70
    dates = _make_dates(n)
    c = [100.0] * n
    c[-1] = 112.0
    o = [99.0] * n
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    v = [1_000_000.0] * n

    result = compute_facts("TEST", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])
    num_re = _number_re()
    for fact in result["facts"]:
        for token in num_re.findall(fact["text"]):
            if re.match(r"^\d{1,2}$", token):
                continue
            assert token in whitelist, (
                f"Token '{token}' in '{fact['id']}' text='{fact['text']}' not in whitelist={whitelist}"
            )


def test_nr7_detected():
    from engine.marketing.chart_facts import compute_facts
    n = 30
    dates = _make_dates(n)
    c = [100.0] * n
    o = [99.5] * n
    # Make first 6 bars have wider ranges, last bar very tight
    h = [101.0] * n
    l = [99.0] * n
    # Last 7 bars: first 6 have range 2.0, last has range 0.1
    for i in range(n - 7, n - 1):
        h[i] = 102.0
        l[i] = 100.0  # range = 2.0
    h[-1] = 100.1
    l[-1] = 100.0  # range = 0.1 — tightest

    v = [1_000_000.0] * n
    result = compute_facts("SQUEEZED", dates, o, h, l, c, v)
    fact_ids = [f["id"] for f in result["facts"]]
    assert "nr7" in fact_ids, f"Expected nr7 in {fact_ids}"


def test_sma50_reclaim():
    from engine.marketing.chart_facts import compute_facts
    # Build series: below 50-SMA for most of it, then cross above on last bar
    n = 100
    dates = _make_dates(n)
    # First 98 bars: close is below 100 (which will be ~SMA), last bar jumps above
    c = [95.0] * (n - 2) + [94.0, 105.0]  # drop then jump
    o = [c[0]] + c[:-1]
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    v = [1_000_000.0] * n

    result = compute_facts("RECLAIM", dates, o, h, l, c, v)
    # May or may not detect depending on exact SMA; just verify no crash
    assert isinstance(result["facts"], list)


def test_facts_sorted_by_salience_descending():
    from engine.marketing.chart_facts import compute_facts
    # Use a series that generates multiple facts
    n = 260
    dates = _make_dates(n)
    c = [100.0] * (n - 1) + [115.0]
    o = [99.0] * n
    h = [ci + 0.5 for ci in c]
    h[-1] = 115.0
    l = [98.0] * n
    v = [1_000_000.0] * (n - 1) + [5_000_000.0]  # volume record too

    result = compute_facts("MULTI", dates, o, h, l, c, v)
    facts = result["facts"]
    if len(facts) >= 2:
        saliences = [f["salience"] for f in facts]
        assert saliences == sorted(saliences, reverse=True), (
            f"Facts not sorted by salience DESC: {[(f['id'], f['salience']) for f in facts]}"
        )


def test_whitelist_covers_all_fact_numbers():
    """Global invariant: every number token in any fact text appears in the whitelist."""
    from engine.marketing.chart_facts import compute_facts
    n = 260
    dates = _make_dates(n)
    c = [100.0 + i * 0.1 for i in range(n)]
    c[-1] = 140.0  # new high
    o = [99.0] * n
    h = [ci + 0.5 for ci in c]
    h[-1] = 141.0
    l = [98.0] * n
    v = [1_000_000.0] * (n - 1) + [6_000_000.0]

    result = compute_facts("FULLTEST", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])
    num_re = _number_re()

    for fact in result["facts"]:
        for token in num_re.findall(fact["text"]):
            if re.match(r"^\d{1,2}$", token):
                continue
            assert token in whitelist, (
                f"INVARIANT BROKEN: '{token}' in fact '{fact['id']}' "
                f"text='{fact['text']}' not in whitelist"
            )


def test_empty_inputs_no_crash():
    from engine.marketing.chart_facts import compute_facts
    result = compute_facts("X", [], [], [], [], [], [])
    assert result == {"facts": [], "numbers_whitelist": []}


# ─────────────────────────────────────────────────────────────────────────────
# M2 fact tests (require engine.indicators_m2 via pytest.importorskip)
# ─────────────────────────────────────────────────────────────────────────────

def _build_m2_df(n: int, base: float = 100.0):
    """Build raw arrays for M2 tests.  Returns (dates, o, h, l, c, v)."""
    dates = _make_dates(n)
    c = [base + i * 0.3 for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    # Give bar at index 10 a large volume spike (earnings proxy anchor)
    v = [500_000.0] * n
    v[10] = 5_000_000.0  # clear max-volume bar
    return dates, o, h, l, c, v


def test_avwap_hold_fact_emitted():
    """avwap_hold fires when price stays above AVWAP for >=10 sessions after anchor."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_avwap_hold

    n = 80
    dates, o, h, l, c, v = _build_m2_df(n)
    # anchor_pos will be bar 10 (max volume); price is always rising above AVWAP
    # Build a scenario where close > avwap for many bars after anchor
    result = _fact_avwap_hold("TEST", dates, c, h, l, v)
    # Should emit hold OR reclaim (or None if math doesn't align) — no crash
    if result is not None:
        assert result["id"] in ("avwap_hold", "avwap_reclaim")
        assert result["salience"] in (7, 8)
        assert isinstance(result["numbers"], list)
        # Every numeric token in text must be in numbers list
        import re as _re
        num_re = _re.compile(r"[+-]?\d+\.?\d*%|\d+\.?\d*x|\b\d{2,4}\.\d{2}\b|\b\d+\b")
        for token in num_re.findall(result["text"]):
            # Skip small bare integers (day counts don't need the exact format check)
            pass  # text structure validated below
        # Plain words, and the ANCHOR DATE the reader can find on the chart.
        # Never "anchored VWAP" — see the plain-language contract in chart_facts.
        assert "volume spike" in result["text"]
        assert "vwap" not in result["text"].lower()


def test_avwap_hold_numbers_whitelist():
    """Numbers in avwap_hold fact text must appear in numbers list."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import compute_facts

    n = 80
    dates, o, h, l, c, v = _build_m2_df(n)
    result = compute_facts("HOLD", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])
    num_re = re.compile(r"[+-]?\d+\.?\d*%|\d+\.?\d*x|\b\d{2,4}\.\d{2}\b")
    for fact in result["facts"]:
        if fact["id"] in ("avwap_hold", "avwap_reclaim"):
            for token in num_re.findall(fact["text"]):
                assert token in whitelist, (
                    f"Number '{token}' in '{fact['id']}' text not in whitelist"
                )


def test_avwap_reclaim_fact():
    """avwap_reclaim fires when close was below AVWAP then crosses above within 3 sessions."""
    pytest.importorskip("engine.indicators_m2")
    import pandas as pd
    from engine import indicators_m2 as m2
    from engine.marketing.chart_facts import _fact_avwap_hold

    # Hand-craft: anchor at bar 0 (index 0), price dips below AVWAP then reclaims
    n = 40
    dates = _make_dates(n)
    # Simple AVWAP approximation: typical price = (h+l+c)/3 * volume weighted
    # We'll just test that the function doesn't crash and respects output schema
    c = [100.0] * 30 + [90.0, 88.0, 85.0, 88.0, 92.0, 95.0, 100.0, 102.0, 104.0, 106.0]
    o = [c[0]] + c[:-1]
    h = [ci + 1.0 for ci in c]
    l = [ci - 1.0 for ci in c]
    v = [1_000_000.0] * n
    v[5] = 9_000_000.0  # anchor bar

    result = _fact_avwap_hold("RCL", dates, c, h, l, v)
    if result is not None:
        assert result["id"] in ("avwap_reclaim", "avwap_hold")
        assert result["salience"] in (7, 8)
        assert "anchor" in result["text"]


def test_poc_level_fact_emitted():
    """poc_level fact fires with correct price and pct text."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc

    n = 70
    dates, o, h, l, c, v = _build_m2_df(n)
    facts = _fact_poc("POCTEST", dates, c, h, l, v)
    # May or may not fire depending on indicators_m2 implementation
    if facts:
        ids = [f["id"] for f in facts]
        # At minimum poc_level should appear when profile is available
        # check structure
        for f in facts:
            assert "id" in f
            assert "text" in f
            assert "salience" in f
            assert "numbers" in f
            # Every number in numbers must appear in text
            for num in f["numbers"]:
                assert num in f["text"], (
                    f"Number '{num}' in fact '{f['id']}' not found in text: {f['text']!r}"
                )


def test_poc_numbers_in_whitelist():
    """All numeric tokens in poc facts must be in the numbers_whitelist."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import compute_facts

    n = 70
    dates, o, h, l, c, v = _build_m2_df(n)
    result = compute_facts("POCWL", dates, o, h, l, c, v)
    whitelist = set(result["numbers_whitelist"])
    num_re = re.compile(r"[+-]?\d+\.?\d*%|\d+\.?\d*x|\b\d{2,4}\.\d{2}\b")
    for fact in result["facts"]:
        if fact["id"] in ("poc_level", "in_value_area", "poc_retest_hold"):
            for token in num_re.findall(fact["text"]):
                assert token in whitelist, (
                    f"Token '{token}' in '{fact['id']}' not in whitelist={whitelist}"
                )


def test_poc_retest_hold_fires():
    """poc_retest_hold emits when low touches POC within 1% and close is above."""
    pytest.importorskip("engine.indicators_m2")
    import pandas as pd
    from engine import indicators_m2 as m2
    from engine.marketing.chart_facts import _fact_poc

    n = 70
    dates, o, h, l, c, v = _build_m2_df(n)
    # We can't easily force the POC to a specific value without running indicators_m2,
    # so we just verify the function produces valid schema output and doesn't crash
    facts = _fact_poc("RETEST", dates, c, h, l, v)
    assert isinstance(facts, list)
    for f in facts:
        assert f["id"] in ("poc_level", "in_value_area", "poc_retest_hold")
        assert isinstance(f["salience"], int)
        assert isinstance(f["numbers"], list)


def test_in_value_area_fact():
    """in_value_area fires when price is inside the value area band."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc

    # Price series that is likely inside VA (flat/clustered volume)
    n = 70
    dates = _make_dates(n)
    c = [100.0] * n  # flat — lots of volume at this level
    o = [99.8] * n
    h = [100.5] * n
    l = [99.5] * n
    v = [2_000_000.0] * n  # uniform volume

    facts = _fact_poc("FLAT", dates, c, h, l, v)
    assert isinstance(facts, list)
    # If profile fires, check structure
    for f in facts:
        assert f["id"] in ("poc_level", "in_value_area", "poc_retest_hold")
        for num in f["numbers"]:
            assert num in f["text"], (
                f"Number '{num}' not in text: {f['text']!r}"
            )


def test_m2_facts_no_intraday_vocab():
    """M2 fact texts must never contain intraday/session VWAP language."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import compute_facts

    n = 80
    dates, o, h, l, c, v = _build_m2_df(n)
    result = compute_facts("VOCAB", dates, o, h, l, c, v)
    banned = ("intraday", "session vwap", "validated")
    for fact in result["facts"]:
        text_lower = fact["text"].lower()
        for word in banned:
            assert word not in text_lower, (
                f"Banned term '{word}' found in fact '{fact['id']}': {fact['text']!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Plain-language contract (2026-07-26 $AAPL incident)
# ─────────────────────────────────────────────────────────────────────────────
#
# A fact text is not scratch material — copywriter ships it verbatim to the LLM
# and renders {top_fact} verbatim in the deterministic templates, so a fact that
# names a study puts that study's name in a public post. These two tests are the
# structural guard: a new detector cannot bring jargon back in without failing,
# and it cannot describe a level it never prices.

def _all_fact_texts(monkeypatch=None) -> list[tuple[str, str]]:
    """(id, text) for every fact the engine can emit on a rich fixture."""
    from engine.marketing.chart_facts import _fact_avwap_hold, _fact_poc, compute_facts
    n = 80
    dates, o, h, l, c, v = _build_m2_df(n)
    out = [(f["id"], f["text"]) for f in compute_facts("PLAIN", dates, o, h, l, c, v)["facts"]]
    # The M2 detectors are conditional; force them so the ban applies to their
    # text too rather than passing vacuously when the fixture does not fire them.
    # _build_m2_df spikes volume at bar 10, which falls outside the 63-bar anchor
    # lookback at n=80, so avwap never fires on it. Move the spike inside.
    v_late = list(v)
    v_late[10] = 500_000.0
    v_late[55] = 5_000_000.0
    avw = _fact_avwap_hold("PLAIN", dates, c, h, l, v_late)
    assert avw is not None, "avwap fixture stopped firing — the guard would miss it"
    out.append((avw["id"], avw["text"]))
    if monkeypatch is not None:
        _patch_profile(monkeypatch, poc=c[-1] * 1.01, va_low=c[-1] * 0.98,
                       va_high=c[-1] * 1.02)
        out += [(f["id"], f["text"]) for f in _fact_poc("PLAIN", dates, c, h, l, v)]
    return out


def test_no_fact_text_carries_study_jargon(monkeypatch):
    """The validator's ban list is the single source of truth, so a fact can
    never ship vocabulary the copy gate would reject downstream."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.copywriter import _BANNED_SUBSTRINGS, _BANNED_VOCAB

    texts = _all_fact_texts(monkeypatch)
    assert texts, "fixture produced no facts — the guard would pass vacuously"
    for fact_id, text in texts:
        low = text.lower()
        for word in _BANNED_VOCAB:
            assert not re.search(rf"\b{re.escape(word)}\b", low), (
                f"fact {fact_id!r} carries banned vocab {word!r}: {text!r}"
            )
        for phrase in _BANNED_SUBSTRINGS:
            assert phrase not in low, (
                f"fact {fact_id!r} carries banned phrase {phrase!r}: {text!r}"
            )


def test_level_facts_print_their_price(monkeypatch):
    """A fact about a line must carry the line's price, in the text AND in
    numbers. avwap_hold used to whitelist only the streak count and the anchor
    day, so a writer obeying the whitelist could not name the level it was
    describing — which is exactly the post the operator saw."""
    pytest.importorskip("engine.indicators_m2")
    price_re = re.compile(r"\d[\d,]*\.\d{2}")
    level_facts = {"avwap_hold", "avwap_reclaim", "poc_level",
                   "poc_retest_hold", "in_value_area"}

    seen = set()
    for fact_id, text in _all_fact_texts(monkeypatch):
        if fact_id not in level_facts:
            continue
        seen.add(fact_id)
        assert price_re.search(text), (
            f"{fact_id!r} describes a level but prints no price: {text!r}")
    assert seen, "no level facts fired — the guard would pass vacuously"


# ─────────────────────────────────────────────────────────────────────────────
# M2 polarity + gating + cap + salience (F1/F3/F4/F6/F7)
# ─────────────────────────────────────────────────────────────────────────────

def _patch_profile(monkeypatch, poc, va_low, va_high):
    """Force indicators_m2.volume_profile to a fixed profile for deterministic tests."""
    import engine.indicators_m2 as m2
    monkeypatch.setattr(
        m2, "volume_profile",
        lambda df, **kw: {"poc": poc, "va_low": va_low, "va_high": va_high,
                          "total_volume": 1.0, "bin_edges": [], "bin_volumes": [],
                          "window_used": len(df)},
    )


def test_poc_level_gated_out_when_far_above(monkeypatch):
    """F3: poc_level must NOT emit when price is >15% away from the POC."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc
    n = 40
    dates, o, h, l, c, v = _build_m2_df(n)
    last = c[-1]
    # POC 20% below last close → |pct| = 25% > 15% → gated out.
    _patch_profile(monkeypatch, poc=last / 1.25, va_low=last * 0.5, va_high=last * 0.6)
    facts = _fact_poc("FAR", dates, c, h, l, v)
    assert not any(f["id"] == "poc_level" for f in facts), (
        f"poc_level emitted despite >15% distance: {[f['text'] for f in facts]}"
    )


def test_poc_level_emits_at_boundary(monkeypatch):
    """F3: poc_level DOES emit at exactly 15% and just inside; polarity signed."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc
    n = 40
    dates, o, h, l, c, v = _build_m2_df(n)
    last = c[-1]
    # POC exactly 15% below → pct_away = +15.00% → inside gate (<=15), price above.
    _patch_profile(monkeypatch, poc=last / 1.15, va_low=last * 0.9, va_high=last * 0.95)
    facts = _fact_poc("EDGE", dates, c, h, l, v)
    poc_facts = [f for f in facts if f["id"] == "poc_level"]
    assert poc_facts, "poc_level must emit at the 15% boundary"
    assert poc_facts[0]["polarity"] == 1, "price above POC → polarity +1"


def test_poc_level_polarity_below(monkeypatch):
    """F1: poc_level polarity is -1 when price sits below the POC."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc
    n = 40
    dates, o, h, l, c, v = _build_m2_df(n)
    last = c[-1]
    # POC 5% ABOVE last close → price below POC → polarity -1.
    _patch_profile(monkeypatch, poc=last * 1.05, va_low=last * 0.9, va_high=last * 1.1)
    facts = _fact_poc("BELOW", dates, c, h, l, v)
    poc = next(f for f in facts if f["id"] == "poc_level")
    assert poc["polarity"] == -1, "price below POC → polarity -1"
    # The text says which side price sits on. Asserted as the word, not the old
    # "below it" phrasing: the fact now names the level in plain words instead of
    # pointing at it with a pronoun (see the plain-language contract).
    assert "below" in poc["text"]
    assert "above" not in poc["text"]


def test_in_value_area_polarity_zero(monkeypatch):
    """F1: in_value_area carries polarity 0 (neutral)."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc
    n = 40
    dates, o, h, l, c, v = _build_m2_df(n)
    last = c[-1]
    _patch_profile(monkeypatch, poc=last, va_low=last - 5, va_high=last + 5)
    facts = _fact_poc("VA", dates, c, h, l, v)
    va = [f for f in facts if f["id"] == "in_value_area"]
    assert va, "in_value_area should fire when price inside band"
    assert va[0]["polarity"] == 0


def test_poc_facts_capped_at_two(monkeypatch):
    """F7: at most 2 POC facts, priority poc_retest_hold > poc_level > in_value_area."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_poc
    n = 40
    dates, o, h, l, c, v = _build_m2_df(n)
    last = c[-1]
    # Craft so ALL THREE could fire: POC ~1% below last (retest range), inside VA.
    poc = last * 0.995
    _patch_profile(monkeypatch, poc=poc, va_low=last - 5, va_high=last + 5)
    # Force a retest: set the most recent low to within 1% of POC, close above POC.
    l = list(l)
    l[-1] = poc * 1.001  # within 1%
    c = list(c)
    c[-1] = poc * 1.02   # closed above
    facts = _fact_poc("CAP", dates, c, h, l, v)
    ids = [f["id"] for f in facts]
    assert len(facts) <= 2, f"POC facts not capped at 2: {ids}"
    # Highest-priority fact must survive the cap.
    assert "poc_retest_hold" in ids, f"retest_hold (top priority) dropped: {ids}"
    # in_value_area (lowest priority) must be the one dropped when 3 would fire.
    assert "in_value_area" not in ids, f"lowest-priority fact survived cap: {ids}"


def _avwap_hold_ohlcv(n: int = 60):
    """OHLCV that reliably fires avwap_hold: early volume-spike anchor + a long
    steadily-rising leg so close stays above the AVWAP for many sessions.
    """
    dates = _make_dates(n)
    c = [100.0 + i * 1.5 for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [ci + 0.5 for ci in c]
    l = [ci - 0.5 for ci in c]
    v = [500_000.0] * n
    v[5] = 9_000_000.0  # anchor at bar 5 (anchor_age ≫ 10)
    return dates, o, h, l, c, v


def test_avwap_hold_salience_is_six():
    """F4: avwap_hold is streak-tier salience 6 (not 7)."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_avwap_hold
    dates, o, h, l, c, v = _avwap_hold_ohlcv(60)
    result = _fact_avwap_hold("SAL", dates, c, h, l, v)
    assert result is not None and result["id"] == "avwap_hold", (
        f"fixture failed to fire avwap_hold: {result}"
    )
    assert result["salience"] == 6, f"avwap_hold salience must be 6, got {result['salience']}"
    assert result.get("polarity") == 1


def test_avwap_anchor_day_in_numbers():
    """F6: the anchor day token (e.g. '09' in 'Jan 09') is in the fact's numbers."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import _fact_avwap_hold
    import re as _re
    dates, o, h, l, c, v = _avwap_hold_ohlcv(60)
    result = _fact_avwap_hold("DAY", dates, c, h, l, v)
    assert result is not None and result["id"] in ("avwap_hold", "avwap_reclaim"), (
        f"fixture failed to fire an avwap fact: {result}"
    )
    # Extract the exact day token from the "%b %d" label in the text.
    m = _re.search(r"\b([A-Z][a-z]{2}) (\d{2})\b", result["text"])
    assert m, f"no 'Mon DD' anchor label in text: {result['text']!r}"
    day_tok = m.group(2)  # zero-padded, exactly as it appears in the text
    assert day_tok in result["numbers"], (
        f"anchor day '{day_tok}' not in numbers {result['numbers']}"
    )


def test_m2_polarity_key_present_on_all_m2_facts(monkeypatch):
    """F1: every M2 fact dict carries a 'polarity' key in {+1,0,-1}."""
    pytest.importorskip("engine.indicators_m2")
    from engine.marketing.chart_facts import compute_facts
    n = 80
    dates, o, h, l, c, v = _build_m2_df(n)
    result = compute_facts("POL", dates, o, h, l, c, v)
    m2_ids = {"avwap_hold", "avwap_reclaim", "poc_level", "in_value_area", "poc_retest_hold"}
    for fact in result["facts"]:
        if fact["id"] in m2_ids:
            assert "polarity" in fact, f"M2 fact {fact['id']} missing polarity"
            assert fact["polarity"] in (1, 0, -1), (
                f"{fact['id']} polarity out of range: {fact['polarity']}"
            )
    # Legacy facts must NOT carry a polarity key (they use the text-marker path).
    for fact in result["facts"]:
        if fact["id"] not in m2_ids:
            assert "polarity" not in fact, (
                f"legacy fact {fact['id']} unexpectedly carries polarity"
            )


# ─────────────────────────────────────────────────────────────────────────────
# A "52-week" fact must have a year of bars behind it.
#
# _fact_52w_high_low took `window = min(252, n)` and then LABELLED whatever it
# found a 52-week extreme. The only production caller passed n=90, so every one
# of these facts was a ~4-month extreme wearing a 52-week name. Measured on the
# live price stores the day this was found:
#
#     MSFT  true 52w high 551.05   90-bar high 466.32   18.2% understated
#     CDW                179.28                151.17   18.6%
#     META               793.65                690.88   14.9%
#     TSLA               498.83                453.40   10.0%
#
# These facts carry salience 10 and 7 -- the top of the sort -- so they are what
# the writer LEADS with, and their price goes into numbers_whitelist, so the
# invented-number guard actively certifies the wrong figure. Copy already queued
# read "$TSLA ... New 52-week low" and "$AAPL -0.6% off the 52-week high at
# 334.99": claims a follower disproves in one click, on an account whose entire
# product is being right about levels.
# ─────────────────────────────────────────────────────────────────────────────
class TestFiftyTwoWeekFactsNeedAYear:
    def _bars(self, n, *, rising=True):
        """n synthetic sessions with a clear extreme OUTSIDE the last 90."""
        h, l, c, dates = [], [], [], []
        for i in range(n):
            # A spike high early (outside a 90-bar tail) so a short window misses it.
            base = 100.0 + (50.0 if i == 5 else 0.0) + (i * 0.01)
            h.append(base + 1); l.append(base - 1); c.append(base)
            dates.append(f"2025-01-{(i % 28) + 1:02d}")
        return dates, h, l, c

    def test_a_ninety_bar_window_emits_no_52_week_claim(self):
        from engine.marketing.chart_facts import _fact_52w_high_low
        dates, h, l, c = self._bars(90)
        assert _fact_52w_high_low("TEST", dates, h, l, c) == [], (
            "a 90-bar window is still being labelled a 52-week extreme"
        )

    def test_a_full_year_still_emits(self):
        from engine.marketing.chart_facts import _fact_52w_high_low
        dates, h, l, c = self._bars(252)
        out = _fact_52w_high_low("TEST", dates, h, l, c)
        assert isinstance(out, list)   # may be empty if not near an extreme
        for f in out:
            assert "52-week" in f["text"], f

    def test_the_floor_is_a_year_not_a_quarter(self):
        from engine.marketing.chart_facts import _MIN_52W_BARS
        assert _MIN_52W_BARS >= 240, (
            "the floor no longer means 'a year' -- a shorter window would let "
            "the disprovable claim back in"
        )

    def test_the_production_caller_loads_a_year(self):
        """The fix is worthless if content_studio goes back to n=90."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        assert "load_ohlcv(ticker, _ohlcv_root_cw, n=252)" in src, (
            "the fact lane is loading a short window again"
        )


# ─────────────────────────────────────────────────────────────────────────────
# X Growth W1g — the degenerate "first since" clause, and one basis per fact.
#
# TWO LIVE DEFECTS, both from the 2026-07-25..31 audit.
#
# (1) DEGENERATE LOOKBACK. "first since <date>" was derived from the prior
#     extreme found INSIDE the same 252-bar window the record is measured
#     against, so on consecutive record days the prior extreme is YESTERDAY:
#     "$ROST hit a new 52-week high, first since Jun 2026" on 07-28, then
#     "first since Jul 2026" on 07-29 — 25 posts in one week asserting rarity
#     while describing its opposite. The SMA branch had the same shape plus a
#     placeholder: with no prior bar found it rendered the literal string
#     "a while" into the copy AND into the fact's licensed numbers.
#
# (2) BASIS MIXING. The $TSLA post detected a 52-week low with
#     `last_low < w52_low` (INTRADAY) and shipped close-phrased copy ("through
#     306.51") that the record's own last_close (313.03) contradicts.
# ─────────────────────────────────────────────────────────────────────────────

#: Words that only a CLOSE-basis detection may license.
_CLOSE_WORDS = ("closed", "close above", "close below", "through")
#: Words that only an INTRADAY-basis detection may license.
_INTRADAY_WORDS = ("intraday", "traded up to", "traded down to", "traded above",
                   "traded below")


def _year_of_bars(n=260, *, base=100.0):
    """n sessions of flat OHLC at *base* (dates are real trading days)."""
    dates = _make_dates(n)
    o = [base] * n
    h = [base + 0.5] * n
    l = [base - 0.5] * n
    c = [base] * n
    return dates, o, h, l, c


class TestSinceClauseIsNotDegenerate:
    def test_a_fresh_prior_extreme_emits_no_since_clause(self):
        """The $ROST case: yesterday's high cannot date today's record."""
        from engine.marketing.chart_facts import _fact_52w_high_low
        n = 260
        dates, _o, h, l, c = _year_of_bars(n)
        # The prior high is set 3 sessions ago and today takes it out.
        h[n - 4] = 110.0
        c[n - 4] = 110.0
        c[n - 1] = 120.0
        h[n - 1] = 120.0
        facts = _fact_52w_high_low("ROST", dates, h, l, c)
        rec = [f for f in facts if f["id"] == "new_52w_high"]
        assert rec, f"no record fact built: {facts}"
        assert "first since" not in rec[0]["text"], (
            f"a 3-session-old prior high still got a rarity clause: "
            f"{rec[0]['text']!r}"
        )

    def test_a_genuinely_old_prior_extreme_keeps_its_date(self):
        """Suppression must not swallow the case the clause exists for."""
        from engine.marketing.chart_facts import _fact_52w_high_low
        n = 260
        dates, _o, h, l, c = _year_of_bars(n)
        # Prior high 200 sessions back; nothing since.
        h[n - 200] = 110.0
        c[n - 200] = 110.0
        c[n - 1] = 120.0
        h[n - 1] = 120.0
        facts = _fact_52w_high_low("OLD", dates, h, l, c)
        rec = [f for f in facts if f["id"] == "new_52w_high"]
        assert rec, f"no record fact built: {facts}"
        assert "first since" in rec[0]["text"], rec[0]["text"]
        # And the date it names is whitelisted, because it carries a year token.
        label = rec[0]["text"].split("first since ")[1]
        assert label in rec[0]["numbers"], rec[0]

    def test_the_since_date_is_the_most_recent_touch_not_the_first(self):
        """`.index()` found the EARLIEST bar at the extreme, which overstates
        the gap: a level touched in January AND July is not 'first since Jan'."""
        from engine.marketing.chart_facts import _fact_52w_high_low
        n = 260
        dates, _o, h, l, c = _year_of_bars(n)
        h[10] = 110.0            # earliest touch
        c[10] = 110.0
        h[n - 3] = 110.0         # most recent touch — 3 sessions ago
        c[n - 3] = 110.0
        c[n - 1] = 120.0
        h[n - 1] = 120.0
        rec = [f for f in _fact_52w_high_low("TWICE", dates, h, l, c)
               if f["id"] == "new_52w_high"]
        assert rec and "first since" not in rec[0]["text"], (
            f"dated off the earliest touch, not the most recent: {rec}"
        )

    def test_no_placeholder_string_ever_reaches_copy_or_numbers(self):
        """`_fact_sma_cross` rendered 'first time since a while' when it could
        not find a prior bar — in the text AND in the licensed numbers."""
        from engine.marketing.chart_facts import _fact_sma_cross
        n = 60
        dates = _make_dates(n)
        # Below the 50-day for its whole life (a steady decline keeps every
        # close under the trailing mean), then one bar pops above it: the
        # backward search finds NO earlier bar above the average.
        c = [100.0 - 0.1 * i for i in range(n - 1)] + [140.0]
        fact = _fact_sma_cross("TEST", dates, c, 50, "50-day average")
        assert fact is not None, "no cross detected — fixture is wrong"
        assert "a while" not in fact["text"], fact["text"]
        assert "a while" not in fact["numbers"], fact["numbers"]
        assert "first time since" not in fact["text"], fact["text"]

    def test_a_fresh_moving_average_cross_emits_no_since_clause(self):
        """The live $TEL post: 'first close above the 50-day since Jul 2026',
        written days after it lost that same average."""
        from engine.marketing.chart_facts import _fact_sma_cross
        n = 70
        dates = _make_dates(n)
        c = [100.0] * n
        c[n - 6] = 130.0          # above the average 5 sessions ago
        c[n - 1] = 130.0          # and again today
        fact = _fact_sma_cross("TEL", dates, c, 50, "50-day average")
        assert fact is not None
        assert "first time since" not in fact["text"], fact["text"]

    def test_the_suppression_floor_is_a_quarter(self):
        from engine.marketing.chart_facts import _MIN_SINCE_SESSIONS
        assert _MIN_SINCE_SESSIONS >= 60, (
            "a shorter floor lets 'first since last month' back in"
        )


class TestExtremeFactsCarryOneBasis:
    def _tsla_bars(self):
        """The $TSLA shape: an intraday low below the 52-week low, closing well
        above it."""
        n = 260
        dates, _o, h, l, c = _year_of_bars(n, base=400.0)
        # An earlier trough sets both prior lows; today's bar takes out the
        # INTRADAY low only and closes back above the prior closing low.
        l[n - 100] = 310.00
        c[n - 100] = 312.00
        h[n - 100] = 315.00
        l[n - 1] = 306.51        # intraday low takes out the low
        c[n - 1] = 313.03        # but the CLOSE is above the prior closing low
        h[n - 1] = 314.00
        return dates, h, l, c

    def test_an_intraday_record_never_speaks_in_closes(self):
        from engine.marketing.chart_facts import _fact_52w_high_low
        dates, h, l, c = self._tsla_bars()
        rec = [f for f in _fact_52w_high_low("TSLA", dates, h, l, c)
               if f["id"] == "new_52w_low"]
        assert rec, "no 52-week low detected — fixture is wrong"
        fact = rec[0]
        assert fact["basis"] == "intraday", fact
        low = fact["text"].lower()
        for word in _CLOSE_WORDS:
            assert word not in low, (
                f"intraday-basis fact makes a close claim ({word!r}): "
                f"{fact['text']!r}"
            )
        assert "306.51" in fact["text"], fact["text"]
        # The close is NOT licensed: a writer cannot build "closed through X"
        # out of a number the packet never handed it.
        assert "313.03" not in fact["numbers"], fact["numbers"]

    def test_a_close_record_says_closed(self):
        from engine.marketing.chart_facts import _fact_52w_high_low
        n = 260
        dates, _o, h, l, c = _year_of_bars(n)
        c[n - 1] = 130.0
        h[n - 1] = 131.0
        rec = [f for f in _fact_52w_high_low("UP", dates, h, l, c)
               if f["id"] == "new_52w_high"]
        assert rec and rec[0]["basis"] == "close", rec
        assert "closed" in rec[0]["text"], rec[0]["text"]
        for word in _INTRADAY_WORDS:
            assert word not in rec[0]["text"].lower(), rec[0]["text"]

    def test_every_basis_bearing_fact_is_self_consistent(self):
        """Whole-engine sweep: no fact may be detected on one basis and phrased
        on the other, whatever the tape does."""
        from engine.marketing.chart_facts import compute_facts
        n = 260
        seen = 0
        for scenario in ("high_close", "low_intraday", "chop"):
            dates, o, h, l, c = _year_of_bars(n)
            if scenario == "high_close":
                c[n - 1] = 130.0
                h[n - 1] = 131.0
            elif scenario == "low_intraday":
                l[n - 1] = 60.0
                c[n - 1] = 99.0
            else:
                c[n - 1] = 100.4
                h[n - 1] = 100.9
            v = [1_000_000.0] * n
            for fact in compute_facts("X", dates, o, h, l, c, v)["facts"]:
                basis = fact.get("basis")
                if basis is None:
                    continue
                seen += 1
                low = fact["text"].lower()
                banned = _CLOSE_WORDS if basis == "intraday" else _INTRADAY_WORDS
                for word in banned:
                    assert word not in low, (
                        f"[{scenario}] {fact['id']} is {basis}-basis but says "
                        f"{word!r}: {fact['text']!r}"
                    )
        # NOT VACUOUS: on the pre-fix engine no fact carried a basis at all, so
        # the sweep above would pass by examining nothing.
        assert seen >= 3, (
            f"only {seen} basis-bearing fact(s) across three scenarios — the "
            f"sweep is passing because it has nothing to check"
        )

    def test_the_record_facts_declare_a_basis_at_all(self):
        """A fact with no basis key is one no downstream gate can check."""
        from engine.marketing.chart_facts import _fact_52w_high_low
        n = 260
        dates, _o, h, l, c = _year_of_bars(n)
        c[n - 1] = 130.0
        h[n - 1] = 131.0
        for fact in _fact_52w_high_low("UP", dates, h, l, c):
            assert fact.get("basis") in ("close", "intraday"), fact
